from __future__ import annotations
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from config import *
from io_utils import *
from raster_utils import *
from metrics import *

def month_name(month: int) -> str:
    return {
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Aug",
        9: "Sep",
    }.get(month, str(month))

def plot_raster(
    array: np.ndarray,
    title: str,
    output_path: Path,
    cmap: str,
    vmin: float | None = None,
    vmax: float | None = None,
) -> None:
    plt.figure(figsize=(8, 7))
    im = plt.imshow(array, cmap=cmap, vmin=vmin, vmax=vmax)
    plt.title(title)
    plt.axis("off")
    plt.colorbar(im, shrink=0.8)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

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

def get_reference_meta_from_2024(
    index: dict[tuple[int, int], Path],
    variable_name: str,
) -> dict:
    """
    Use the first available 2024 raster as the common reference grid.
    """
    candidates = [(ym, path) for ym, path in sorted(index.items()) if ym[0] == 2024]

    if not candidates:
        raise ValueError(
            f"No 2024 rasters found for {variable_name}. "
            "Cannot use 2024 as the common reference grid."
        )

    (_, _), ref_path = candidates[0]
    _, ref_meta = read_raster(ref_path)

    print(
        f"{variable_name}: using 2024 reference grid from {ref_path.name} | "
        f"shape=({ref_meta['height']}, {ref_meta['width']}), "
        f"crs={ref_meta['crs']}, res={ref_meta['res']}"
    )
    return ref_meta

def load_masked_stack(
    index: dict[tuple[int, int], Path],
    mask: np.ndarray,
    mask_meta: dict,
    vmin: float,
    vmax: float,
    variable_name: str,
) -> tuple[np.ndarray, list, dict]:
    """
    Load a variable stack using a fixed 2024 reference grid.
    All rasters are reprojected to the 2024 grid before masking and stacking.
    """
    arrays = []
    dates = []

    # Use 2024 as the fixed common grid
    ref_meta = get_reference_meta_from_2024(index, variable_name)

    # Reproject mask once to the same 2024 grid
    aligned_mask = reproject_mask_to_match(mask, mask_meta, ref_meta)

    for (year, month), tif_path in sorted(index.items()):
        arr, meta = read_raster(tif_path)
        arr = clean_array(arr, vmin, vmax)

        print(
            f"{variable_name} {year}-{month:02d}: "
            f"original shape={arr.shape}, crs={meta['crs']}, res={meta['res']}"
        )

        # Reproject all rasters except those already on the 2024 reference grid
        same_grid = (
            meta["crs"] == ref_meta["crs"]
            and meta["transform"] == ref_meta["transform"]
            and meta["width"] == ref_meta["width"]
            and meta["height"] == ref_meta["height"]
        )

        if same_grid:
            arr_aligned = arr
        else:
            arr_aligned = reproject_array_to_match(
                src_array=arr,
                src_meta=meta,
                target_meta=ref_meta,
            )

        arr_masked = apply_binary_mask(arr_aligned, aligned_mask)

        valid_count = int(np.sum(np.isfinite(arr_masked)))
        print(
            f"{variable_name} {year}-{month:02d}: "
            f"aligned shape={arr_masked.shape}, valid_pixels={valid_count}"
        )

        arrays.append(arr_masked)
        dates.append((year, month))

    if not arrays:
        raise ValueError(f"No valid rasters loaded for {variable_name}")

    stack = np.stack(arrays, axis=0)
    return stack, dates, ref_meta

def main() -> None:
    # 1. Load masks
    land_buffer_mask, land_meta = load_mask(LAND_BUFFER_FILE)
    water_buffer_mask, water_meta = load_mask(WATER_BUFFER_FILE)
    # 2. Build file indices
    ndvi_index = build_variable_index(NDVI_DIR, NDVI_REGEX)
    ndti_index = build_variable_index(NDTI_DIR, NDTI_REGEX)

    if not ndvi_index:
        raise ValueError("No NDVI TIFFs found.")
    if not ndti_index:
        raise ValueError("No NDTI TIFFs found.")

    # 3. Load masked stacks
    ndvi_stack, ndvi_dates, ndvi_meta = load_masked_stack(
        ndvi_index,
        land_buffer_mask,
        land_meta,
        NDVI_MIN,
        NDVI_MAX,
        "ndvi"
    )

    ndti_stack, ndti_dates, ndti_meta = load_masked_stack(
        ndti_index,
        water_buffer_mask,
        water_meta,
        NDTI_MIN,
        NDTI_MAX,
        "ndti"
    )

    # 4. Multi-year mean maps
    mean_ndvi = raster_mean(ndvi_stack)
    mean_ndti = raster_mean(ndti_stack)

    plot_raster(
        mean_ndvi,
        "Multi-year Mean Coastal NDVI",
        FIG_DIR / "map_mean_ndvi_multiyear.png",
        cmap="YlGn",
        vmin=NDVI_PLOT_MIN,
        vmax=NDVI_PLOT_MAX,
    )

    plot_raster(
        mean_ndti,
        "Multi-year Mean Nearshore NDTI",
        FIG_DIR / "map_mean_ndti_multiyear.png",
        cmap="BrBG",
        vmin=NDTI_PLOT_MIN,
        vmax=NDTI_PLOT_MAX,
    )

    save_geotiff(RASTER_DIR / "map_mean_ndvi_multiyear.tif", mean_ndvi, ndvi_meta)
    save_geotiff(RASTER_DIR / "map_mean_ndti_multiyear.tif", mean_ndti, ndti_meta)

    # 5. Monthly climatology maps
    for month in [5, 6, 7, 8, 9]:
        ndvi_idx = [i for i, (_, m) in enumerate(ndvi_dates) if m == month]
        ndti_idx = [i for i, (_, m) in enumerate(ndti_dates) if m == month]

        if ndvi_idx:
            ndvi_month_mean = np.nanmean(ndvi_stack[ndvi_idx, :, :], axis=0)
            plot_raster(
                ndvi_month_mean,
                f"Mean Coastal NDVI for {month_name(month)}",
                FIG_DIR / f"map_ndvi_climatology_{month:02d}.png",
                cmap="YlGn",
                vmin=NDVI_PLOT_MIN,
                vmax=NDVI_PLOT_MAX,
            )
            save_geotiff(
                RASTER_DIR / f"map_ndvi_climatology_{month:02d}.tif",
                ndvi_month_mean,
                ndvi_meta,
            )

        if ndti_idx:
            ndti_month_mean = np.nanmean(ndti_stack[ndti_idx, :, :], axis=0)
            plot_raster(
                ndti_month_mean,
                f"Mean Nearshore NDTI for {month_name(month)}",
                FIG_DIR / f"map_ndti_climatology_{month:02d}.png",
                cmap="BrBG",
                vmin=NDTI_PLOT_MIN,
                vmax=NDTI_PLOT_MAX,
            )
            save_geotiff(
                RASTER_DIR / f"map_ndti_climatology_{month:02d}.tif",
                ndti_month_mean,
                ndti_meta,
            )

    # 6. Yearly anomaly maps
    ndvi_years = sorted({y for y, _ in ndvi_dates})
    ndti_years = sorted({y for y, _ in ndti_dates})
    common_years = sorted(set(ndvi_years) & set(ndti_years))

    for year in common_years:
        ndvi_idx = [i for i, (y, _) in enumerate(ndvi_dates) if y == year]
        ndti_idx = [i for i, (y, _) in enumerate(ndti_dates) if y == year]

        if ndvi_idx:
            ndvi_year_mean = np.nanmean(ndvi_stack[ndvi_idx, :, :], axis=0)
            ndvi_anom = raster_anomaly(ndvi_year_mean, mean_ndvi)

            plot_raster(
                ndvi_anom,
                f"NDVI Anomaly for {year}",
                FIG_DIR / f"map_ndvi_anomaly_{year}.png",
                cmap="RdYlGn",
                vmin=-0.2,
                vmax=0.2,
            )
            save_geotiff(
                RASTER_DIR / f"map_ndvi_anomaly_{year}.tif",
                ndvi_anom,
                ndvi_meta,
            )

        if ndti_idx:
            ndti_year_mean = np.nanmean(ndti_stack[ndti_idx, :, :], axis=0)
            ndti_anom = raster_anomaly(ndti_year_mean, mean_ndti)

            plot_raster(
                ndti_anom,
                f"NDTI Anomaly for {year}",
                FIG_DIR / f"map_ndti_anomaly_{year}.png",
                cmap="PuOr",
                vmin=-0.15,
                vmax=0.15,
            )
            save_geotiff(
                RASTER_DIR / f"map_ndti_anomaly_{year}.tif",
                ndti_anom,
                ndti_meta,
            )

    print("Map analysis complete.")
    print(f"Figures saved to: {FIG_DIR}")
    print(f"Rasters saved to: {RASTER_DIR}")

if __name__ == "__main__":
    main()