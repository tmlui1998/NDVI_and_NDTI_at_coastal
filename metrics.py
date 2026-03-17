from __future__ import annotations

import numpy as np

def summary_stats(arr: np.ndarray, prefix: str) -> dict:
    valid = np.isfinite(arr)
    if not np.any(valid):
        return {
            f"{prefix}_mean": np.nan,
            f"{prefix}_median": np.nan,
            f"{prefix}_std": np.nan,
            f"{prefix}_min": np.nan,
            f"{prefix}_max": np.nan,
            f"{prefix}_valid_pixels": 0,
        }

    return {
        f"{prefix}_mean": float(np.nanmean(arr)),
        f"{prefix}_median": float(np.nanmedian(arr)),
        f"{prefix}_std": float(np.nanstd(arr)),
        f"{prefix}_min": float(np.nanmin(arr)),
        f"{prefix}_max": float(np.nanmax(arr)),
        f"{prefix}_valid_pixels": int(np.sum(valid)),
    }

def threshold_area_km2(arr: np.ndarray, threshold: float, pixel_area_km2: float, greater_equal: bool = True) -> float:
    if greater_equal:
        mask = np.isfinite(arr) & (arr >= threshold)
    else:
        mask = np.isfinite(arr) & (arr <= threshold)
    return float(np.sum(mask) * pixel_area_km2)

def raster_mean(stack: np.ndarray) -> np.ndarray:
    return np.nanmean(stack, axis=0)

def raster_anomaly(year_mean: np.ndarray, long_term_mean: np.ndarray) -> np.ndarray:
    return year_mean - long_term_mean