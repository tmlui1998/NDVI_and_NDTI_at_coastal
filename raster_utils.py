from __future__ import annotations

import numpy as np
from rasterio.enums import Resampling
from rasterio.warp import reproject

def clean_array(arr: np.ndarray, vmin: float, vmax: float) -> np.ndarray:
    out = arr.copy()
    out[(out < vmin) | (out > vmax)] = np.nan
    return out

def assert_same_grid(meta_a: dict, meta_b: dict, name_a: str, name_b: str) -> None:
    same = (
        meta_a["crs"] == meta_b["crs"]
        and meta_a["transform"] == meta_b["transform"]
        and meta_a["width"] == meta_b["width"]
        and meta_a["height"] == meta_b["height"]
    )
    if not same:
        raise ValueError(
            f"Grid mismatch between {name_a} and {name_b}. "
            "They must have the same CRS, transform, width, and height."
        )

def to_binary_mask(mask_array: np.ndarray) -> np.ndarray:
    out = mask_array.copy()
    out = np.where(np.isfinite(out) & (out > 0), 1, 0).astype("uint8")
    return out

def apply_binary_mask(data: np.ndarray, mask: np.ndarray) -> np.ndarray:
    masked = data.copy()
    masked[mask == 0] = np.nan
    return masked

def count_valid_pixels(arr: np.ndarray) -> int:
    return int(np.sum(np.isfinite(arr)))

def pixel_area_km2(meta: dict) -> float:
    res_x, res_y = meta["res"]
    return abs(res_x * res_y) / 1_000_000.0

def reproject_mask_to_match(mask_array: np.ndarray, mask_meta: dict, target_meta: dict) -> np.ndarray:
    """
    Reproject a binary mask to exactly match the target raster grid.
    Uses nearest-neighbor resampling so 0/1 values stay binary.
    """
    destination = np.zeros((target_meta["height"], target_meta["width"]), dtype=np.uint8)

    reproject(
        source=mask_array.astype(np.uint8),
        destination=destination,
        src_transform=mask_meta["transform"],
        src_crs=mask_meta["crs"],
        dst_transform=target_meta["transform"],
        dst_crs=target_meta["crs"],
        resampling=Resampling.nearest,
    )

    return np.where(destination > 0, 1, 0).astype(np.uint8)

def reproject_array_to_match(
    src_array: np.ndarray,
    src_meta: dict,
    target_meta: dict,
    resampling=Resampling.bilinear,
) -> np.ndarray:
    """
    Reproject a raster array to exactly match the target raster grid.
    Use bilinear for continuous variables like NDVI/NDTI.
    """
    destination = np.full(
        (target_meta["height"], target_meta["width"]),
        np.nan,
        dtype=np.float32
    )

    reproject(
        source=src_array.astype(np.float32),
        destination=destination,
        src_transform=src_meta["transform"],
        src_crs=src_meta["crs"],
        dst_transform=target_meta["transform"],
        dst_crs=target_meta["crs"],
        src_nodata=np.nan,
        dst_nodata=np.nan,
        resampling=resampling,
    )

    return destination