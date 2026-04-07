#!/usr/bin/env python3
"""Build 3 ARIMA models for y1, y2, y3 from an Excel file."""

from __future__ import annotations

import argparse
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller, kpss


@dataclass
class CandidateModel:
    order: Tuple[int, int, int]
    trend: str
    aic: float
    bic: float
    lb10_pvalue: float
    all_significant: bool
    params: Dict[str, float]
    pvalues: Dict[str, float]
    fitted_model: object


def load_series(path: Path, required_cols: List[str]) -> Tuple[str, pd.DataFrame]:
    xls = pd.ExcelFile(path)
    for sheet in xls.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        cols = set(df.columns.astype(str))
        if set(required_cols).issubset(cols):
            out = df[required_cols].copy()
            out = out.apply(pd.to_numeric, errors="coerce").dropna()
            if not out.empty:
                return sheet, out
    raise ValueError(
        f"No sheet with columns {required_cols}. Available sheets: {xls.sheet_names}"
    )


def stationarity_tests(y: pd.Series, max_d: int = 2) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    for d in range(max_d + 1):
        yd = y.diff(d).dropna() if d > 0 else y.copy()
        try:
            adf_p = float(adfuller(yd, regression="c", autolag="AIC")[1])
        except Exception:
            adf_p = np.nan
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                kpss_p = float(kpss(yd, regression="c", nlags="auto")[1])
        except Exception:
            kpss_p = np.nan
        rows.append({"d": d, "adf_p": adf_p, "kpss_p": kpss_p})
    return rows


def fit_candidates(
    y: pd.Series,
    max_d: int = 2,
    max_p: int = 3,
    max_q: int = 3,
    max_p_plus_q: int = 3,
) -> List[CandidateModel]:
    candidates: List[CandidateModel] = []
    for d in range(max_d + 1):
        for p in range(max_p + 1):
            for q in range(max_q + 1):
                if p + q > max_p_plus_q:
                    continue
                if (p, d, q) == (0, 0, 0):
                    continue
                trends = ["c", "n"] if d == 0 else ["n", "c"]
                for trend in trends:
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore")
                            model = ARIMA(y, order=(p, d, q), trend=trend).fit()
                        lb = acorr_ljungbox(
                            model.resid, lags=[10], return_df=True
                        )["lb_pvalue"].iloc[0]
                        pvals = model.pvalues.to_dict()
                        coef_pvals = [
                            float(v)
                            for name, v in pvals.items()
                            if name != "sigma2" and not np.isnan(v)
                        ]
                        all_significant = all(pv <= 0.05 for pv in coef_pvals)
                        candidates.append(
                            CandidateModel(
                                order=(p, d, q),
                                trend=trend,
                                aic=float(model.aic),
                                bic=float(model.bic),
                                lb10_pvalue=float(lb),
                                all_significant=all_significant,
                                params={k: float(v) for k, v in model.params.items()},
                                pvalues={k: float(v) for k, v in model.pvalues.items()},
                                fitted_model=model,
                            )
                        )
                    except Exception:
                        continue
    if not candidates:
        raise RuntimeError("No ARIMA models were fitted.")
    return candidates


def choose_best(candidates: List[CandidateModel]) -> CandidateModel:
    level1 = [
        c for c in candidates if c.lb10_pvalue > 0.05 and c.all_significant
    ]
    level2 = [c for c in candidates if c.lb10_pvalue > 0.05]
    pool = level1 or level2 or candidates
    return sorted(pool, key=lambda c: c.bic)[0]


def format_p(p: float) -> str:
    if np.isnan(p):
        return "nan"
    if p < 1e-4:
        return "<1e-4"
    return f"{p:.4f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build 3 ARIMA models for y1, y2, y3."
    )
    parser.add_argument(
        "--file",
        default="/home/fampkin/Downloads/ARIMA_example.xlsx",
        help="Path to Excel file with y1, y2, y3 columns.",
    )
    parser.add_argument(
        "--forecast-steps",
        type=int,
        default=8,
        help="How many periods ahead to forecast.",
    )
    parser.add_argument(
        "--summary-csv",
        default="arima_summary.csv",
        help="Where to save the compact model summary.",
    )
    args = parser.parse_args()

    file_path = Path(args.file).expanduser().resolve()
    required_cols = ["y1", "y2", "y3"]
    sheet, data = load_series(file_path, required_cols)

    print(f"Data file: {file_path}")
    print(f"Used sheet: {sheet}")
    print(f"Observations: {len(data)}")
    print("-" * 72)

    rows = []
    for col in required_cols:
        y = data[col].astype(float)
        tests = stationarity_tests(y, max_d=2)
        candidates = fit_candidates(y, max_d=2, max_p=3, max_q=3, max_p_plus_q=3)
        best = choose_best(candidates)
        forecast = best.fitted_model.forecast(steps=args.forecast_steps)

        print(f"Series: {col}")
        print("Stationarity checks:")
        for t in tests:
            print(
                f"  d={t['d']}: ADF p={format_p(t['adf_p'])}, "
                f"KPSS p={format_p(t['kpss_p'])}"
            )
        print(
            f"Chosen model: ARIMA{best.order}, trend='{best.trend}', "
            f"AIC={best.aic:.2f}, BIC={best.bic:.2f}, "
            f"Ljung-Box(10) p={best.lb10_pvalue:.4f}"
        )
        print("Parameters:")
        for k, v in best.params.items():
            print(f"  {k}: {v:.6f} (p={format_p(best.pvalues.get(k, np.nan))})")
        print(
            f"{args.forecast_steps}-step forecast: "
            + ", ".join(f"{float(v):.4f}" for v in forecast)
        )
        print("-" * 72)

        rows.append(
            {
                "series": col,
                "p": best.order[0],
                "d": best.order[1],
                "q": best.order[2],
                "trend": best.trend,
                "aic": round(best.aic, 4),
                "bic": round(best.bic, 4),
                "ljung_box_p_lag10": round(best.lb10_pvalue, 6),
                "params": best.params,
            }
        )

    summary = pd.DataFrame(rows)
    summary_path = Path(args.summary_csv).expanduser().resolve()
    summary.to_csv(summary_path, index=False)
    print(f"Saved summary: {summary_path}")


if __name__ == "__main__":
    main()
