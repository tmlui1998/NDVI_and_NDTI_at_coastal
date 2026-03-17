from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, Tuple
import numpy as np
import pandas as pd
import rasterio

def parse_date_from_filename(filename: str, pattern: str) -> Optional[Tuple[int, int]]:
    match = re.search(pattern, filename, flags=re.IGNORECASE)
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    return year, month

def read_raster(path: Path) -> tuple[np.ndarray, dict]:
    with rasterio.open(path) as src:
        arr = src.read(1).astype("float32")
        nodata = src.nodata

        if nodata is not None:
            arr[arr == nodata] = np.nan

        arr[~np.isfinite(arr)] = np.nan

        meta = {
            "crs": src.crs,
            "transform": src.transform,
            "width": src.width,
            "height": src.height,
            "bounds": src.bounds,
            "nodata": src.nodata,
            "dtype": src.dtypes[0],
            "res": src.res,
        }

    return arr, meta

def save_geotiff(path: Path, array: np.ndarray, ref_meta: dict) -> None:
    nodata_value = -9999.0
    out = array.astype("float32").copy()
    out[np.isnan(out)] = nodata_value

    profile = {
        "driver": "GTiff",
        "height": out.shape[0],
        "width": out.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": ref_meta["crs"],
        "transform": ref_meta["transform"],
        "nodata": nodata_value,
        "compress": "lzw",
    }

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(out, 1)

def save_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False)