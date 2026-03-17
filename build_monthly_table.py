from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from config import *
from io_utils import *
from raster_utils import *
from metrics import summary_stats, threshold_area_km2

def load_mask(mask_path: Path) -> tuple[np.ndarray, dict]:
    arr, meta = read_raster(mask_path)
    return to_binary_mask(arr), meta

def build_variable_index(folder: Path, regex: str) -> dict[tuple[int, int], Path]:
    tif_files = sorted(folder.glob("*.tif"))
    index: dict[tuple[int, int], Path] = {}

    for tif in tif_files:
        parsed = parse_date_from_filename(tif.name, regex)
        if parsed is None:
            print(f"Skipping unmatched file: {tif.name}")
            continue
        index[parsed] = tif

    return index

def main() -> None:
    land_buffer_mask_raw, land_meta = load_mask(LAND_BUFFER_FILE)
    water_buffer_mask_raw, water_meta = load_mask(WATER_BUFFER_FILE)

    ndvi_index = build_variable_index(NDVI_DIR, NDVI_REGEX)
    ndti_index = build_variable_index(NDTI_DIR, NDTI_REGEX)

    common_dates = sorted(set(ndvi_index.keys()) & set(ndti_index.keys()))
    if not common_dates:
        raise ValueError("No matching NDVI/NDTI month pairs found.")

    records = []

    for year, month in common_dates:
        ndvi_path = ndvi_index[(year, month)]
        ndti_path = ndti_index[(year, month)]

        ndvi_arr, ndvi_meta = read_raster(ndvi_path)
        ndti_arr, ndti_meta = read_raster(ndti_path)

        ndvi_arr = clean_array(ndvi_arr, NDVI_MIN, NDVI_MAX)
        ndti_arr = clean_array(ndti_arr, NDTI_MIN, NDTI_MAX)

        land_buffer_mask = reproject_mask_to_match(
            land_buffer_mask_raw, land_meta, ndvi_meta
        )
        water_buffer_mask = reproject_mask_to_match(
            water_buffer_mask_raw, water_meta, ndti_meta
        )

        ndvi_coastal = apply_binary_mask(ndvi_arr, land_buffer_mask)
        ndti_coastal = apply_binary_mask(ndti_arr, water_buffer_mask)

        ndvi_px_area = pixel_area_km2(ndvi_meta)
        ndti_px_area = pixel_area_km2(ndti_meta)

        row = {
            "date": pd.Timestamp(year=year, month=month, day=1),
            "year": year,
            "month": month,
            "ndvi_file": ndvi_path.name,
            "ndti_file": ndti_path.name,
        }

        row.update(summary_stats(ndvi_coastal, "ndvi"))
        row.update(summary_stats(ndti_coastal, "ndti"))

        row["veg_area_km2"] = threshold_area_km2(
            ndvi_coastal, NDVI_VEG_THRESHOLD, ndvi_px_area, greater_equal=True
)
        row["high_turbidity_area_km2"] = threshold_area_km2(
            ndti_coastal, NDTI_HIGH_THRESHOLD, ndti_px_area, greater_equal=True
        )

        records.append(row)

    df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    save_csv(df, TABLE_DIR / "gof_monthly_coastal_table.csv")

    annual_df = df.groupby("year", as_index=False).agg({
        "ndvi_mean": "mean",
        "ndti_mean": "mean",
        "veg_area_km2": "mean",
        "high_turbidity_area_km2": "mean",
    }).rename(columns={
        "ndvi_mean": "growing_season_ndvi_mean",
        "ndti_mean": "growing_season_ndti_mean",
        "veg_area_km2": "mean_veg_area_km2",
        "high_turbidity_area_km2": "mean_high_turbidity_area_km2",
    })

    save_csv(annual_df, TABLE_DIR / "gof_annual_coastal_summary.csv")

    print("Saved:")
    print(TABLE_DIR / "gof_monthly_coastal_table.csv")
    print(TABLE_DIR / "gof_annual_coastal_summary.csv")

if __name__ == "__main__":
    main()