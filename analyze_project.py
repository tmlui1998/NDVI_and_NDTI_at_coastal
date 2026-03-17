from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from config import (
    TABLE_DIR, FIG_DIR,
    NDVI_VEG_THRESHOLD, NDTI_HIGH_THRESHOLD
)


def plot_time_series(df: pd.DataFrame, y_col: str, title: str, ylabel: str, out_path) -> None:
    plt.figure(figsize=(11, 5))
    plt.plot(df["date"], df[y_col], marker="o")
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def plot_by_year(df: pd.DataFrame, value_col: str, title: str, ylabel: str, out_path) -> None:
    plt.figure(figsize=(10, 5))
    for year, sub in df.groupby("year"):
        sub = sub.sort_values("month")
        plt.plot(sub["month"], sub[value_col], marker="o", label=str(year))

    plt.xticks([5, 6, 7, 8, 9], ["May", "Jun", "Jul", "Aug", "Sep"])
    plt.title(title)
    plt.xlabel("Month")
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    plt.legend(title="Year", ncol=2)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def main() -> None:
    df = pd.read_csv(TABLE_DIR / "gof_monthly_coastal_table.csv", parse_dates=["date"])

    # Monthly time series
    plot_time_series(
        df,
        "ndvi_mean",
        "Monthly Coastal NDVI Mean (1 km land buffer)",
        "NDVI",
        FIG_DIR / "timeseries_ndvi_coastal_mean.png"
    )

    plot_time_series(
        df,
        "ndti_mean",
        "Monthly Nearshore NDTI Mean (1 km water buffer)",
        "NDTI",
        FIG_DIR / "timeseries_ndti_coastal_mean.png"
    )

    plot_time_series(
        df,
        "veg_area_km2",
        f"Vegetated Coastal Area (NDVI ≥ {NDVI_VEG_THRESHOLD:.2f})",
        "Area (km²)",
        FIG_DIR / "timeseries_veg_area.png"
    )

    plot_time_series(
        df,
        "high_turbidity_area_km2",
        f"High Turbidity Area (NDTI ≥ {NDTI_HIGH_THRESHOLD:.2f})",
        "Area (km²)",
        FIG_DIR / "timeseries_high_turbidity_area.png"
    )

    # Seasonal curves by year
    plot_by_year(
        df,
        "ndvi_mean",
        "Seasonal Coastal NDVI",
        "NDVI",
        FIG_DIR / "seasonal_ndvi_by_year.png"
    )

    plot_by_year(
        df,
        "ndti_mean",
        "Seasonal Nearshore NDTI",
        "NDTI",
        FIG_DIR / "seasonal_ndti_by_year.png"
    )

    # Scatter plot
    plt.figure(figsize=(6, 6))
    plt.scatter(df["ndti_mean"], df["ndvi_mean"])
    for _, row in df.iterrows():
        plt.annotate(
            row["date"].strftime("%Y-%m"),
            (row["ndti_mean"], row["ndvi_mean"]),
            fontsize=7,
            alpha=0.8
        )
    plt.xlabel("NDTI mean (1 km water buffer)")
    plt.ylabel("NDVI mean (1 km land buffer)")
    plt.title("Coastal NDVI vs Nearshore NDTI")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "scatter_ndvi_vs_ndti.png", dpi=300, bbox_inches="tight")
    plt.close()

    # Correlation summary
    corr = df["ndvi_mean"].corr(df["ndti_mean"])
    summary = pd.DataFrame([{
        "ndvi_ndti_correlation": corr,
        "veg_threshold": NDVI_VEG_THRESHOLD,
        "high_turbidity_threshold": NDTI_HIGH_THRESHOLD,
    }])
    summary.to_csv(TABLE_DIR / "analysis_summary.csv", index=False)

    print("Analysis complete.")
    print(f"Correlation NDVI vs NDTI: {corr:.4f}")


if __name__ == "__main__":
    main()