from __future__ import annotations
from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import statsmodels.api as sm
from config import *
from io_utils import *
from raster_utils import *

warnings.filterwarnings("ignore", category=RuntimeWarning)

def load_mask(mask_path: Path) -> tuple[np.ndarray, dict]:
    arr, meta = read_raster(mask_path)
    return to_binary_mask(arr), meta

def build_variable_index(folder: Path, regex: str) -> dict[tuple[int, int], Path]:
    tif_files = sorted(folder.glob("*.tif"))
    index: dict[tuple[int, int], Path] = {}

    for tif in tif_files:
        parsed = parse_date_from_filename(tif.name, regex)
        index[parsed] = tif

    return index

def sample_pixel_table(
    ndvi_index: dict[tuple[int, int], Path],
    ndti_index: dict[tuple[int, int], Path],
    land_mask_raw: np.ndarray,
    land_mask_meta: dict,
    water_mask_raw: np.ndarray,
    water_mask_meta: dict,
    max_pixels_per_month: int = 5000,
    random_seed: int = 42,
) -> pd.DataFrame:
    """
    Build a sampled pixel-level spatio-temporal table for GAM.

    Important note:
    NDVI and NDTI are defined on different domains (land vs water), so
    this version samples pixels where both masked rasters remain finite
    on the common output grid. This is a simplified project-level approach.
    """
    rng = np.random.default_rng(random_seed)
    common_dates = sorted(set(ndvi_index.keys()) & set(ndti_index.keys()))
    records = []

    for year, month in common_dates:
        ndvi_path = ndvi_index[(year, month)]
        ndti_path = ndti_index[(year, month)]

        ndvi_arr, ndvi_meta = read_raster(ndvi_path)
        ndti_arr, ndti_meta = read_raster(ndti_path)

        ndvi_arr = clean_array(ndvi_arr, NDVI_MIN, NDVI_MAX)
        ndti_arr = clean_array(ndti_arr, NDTI_MIN, NDTI_MAX)

        land_mask = reproject_mask_to_match(land_mask_raw, land_mask_meta, ndvi_meta)
        water_mask = reproject_mask_to_match(water_mask_raw, water_mask_meta, ndti_meta)

        ndvi_arr = apply_binary_mask(ndvi_arr, land_mask)
        ndti_arr = apply_binary_mask(ndti_arr, water_mask)

        # Reproject water-valid mask to NDVI grid as a simplified common support
        water_valid = np.where(np.isfinite(ndti_arr), 1, 0).astype("uint8")
        water_valid_on_ndvi = reproject_mask_to_match(
            water_valid,
            ndti_meta,
            ndvi_meta
        )

        ndti_fill = np.full(ndvi_arr.shape, np.nan, dtype="float32")
        ndti_global_median = np.nanmedian(ndti_arr) if np.any(np.isfinite(ndti_arr)) else np.nan
        ndti_fill[water_valid_on_ndvi > 0] = ndti_global_median

        valid = np.isfinite(ndvi_arr) & np.isfinite(ndti_fill)
        rows, cols = np.where(valid)

        if len(rows) == 0:
            print(f"No valid sampled pixels for {year}-{month:02d}")
            continue

        if len(rows) > max_pixels_per_month:
            idx = rng.choice(len(rows), size=max_pixels_per_month, replace=False)
            rows = rows[idx]
            cols = cols[idx]

        for r, c in zip(rows, cols):
            x, y = ndvi_meta["transform"] * (c + 0.5, r + 0.5)
            records.append({
                "year": year,
                "month": month,
                "time_str": f"{year}-{month:02d}",
                "x": x,
                "y": y,
                "ndvi": float(ndvi_arr[r, c]),
                "ndti": float(ndti_fill[r, c]),
            })

    return pd.DataFrame(records)

def fit_lagged_model(monthly_csv: Path) -> tuple[object, pd.DataFrame]:
    """
    Model 2: Intra-seasonal lagged regression
    NDVI_t ~ NDTI_(t-1), using only consecutive months within the same year.
    """
    df = pd.read_csv(monthly_csv, parse_dates=["date"]).sort_values("date").reset_index(drop=True)

    lag_parts = []

    for year, sub in df.groupby(df["date"].dt.year):
        sub = sub.sort_values("date").copy()

        sub["prev_date"] = sub["date"].shift(1)
        sub["prev_ndti"] = sub["ndti_mean"].shift(1)

        sub["month_gap"] = (
            (sub["date"].dt.year - sub["prev_date"].dt.year) * 12
            + (sub["date"].dt.month - sub["prev_date"].dt.month)
        )

        # Keep only true 1-month lags inside the same seasonal sequence
        sub["ndti_lag1"] = np.where(sub["month_gap"] == 1, sub["prev_ndti"], np.nan)

        lag_parts.append(sub)

    df_lag = pd.concat(lag_parts, ignore_index=True)
    lag_df = df_lag.dropna(subset=["ndvi_mean", "ndti_lag1"]).copy()

    lag_df["month"] = lag_df["date"].dt.month
    lag_df["ndti_sq"] = lag_df["ndti_mean"] ** 2

    if lag_df.empty:
        raise ValueError("No valid intra-seasonal lag pairs found.")

    X = lag_df[["ndti_lag1","ndti_sq"]]
    X = sm.add_constant(X)

    y = lag_df["ndvi_mean"]

    model = sm.OLS(y, X).fit()
    lag_df["ndvi_pred_lag1"] = model.predict(X)

    print("MODEL 2: INTRA-SEASONAL LAGGED REGRESSION")
    print("Valid lag pairs used:")
    print(lag_df[["date", "prev_date", "ndti_lag1", "ndvi_mean"]])
    print(model.summary())

    return model, lag_df

def plot_lagged_relationship(
    lag_df: pd.DataFrame,
    model,
    output_path: Path
) -> None:
    plt.figure(figsize=(6, 6))

    x = lag_df["ndti_lag1"].to_numpy()
    y = lag_df["ndvi_mean"].to_numpy()

    # Scatter
    plt.scatter(x, y, alpha=0.7, label="Observed")

    # Quadratic curve using model coefficients
    x_curve = np.linspace(np.nanmin(x), np.nanmax(x), 200)

    beta0 = model.params["const"]
    beta1 = model.params["ndti_lag1"]
    beta2 = model.params["ndti_sq"]

    y_curve = beta0 + beta1 * x_curve + beta2 * (x_curve ** 2)

    plt.plot(x_curve, y_curve, linewidth=2, label="Quadratic fit")

    # Annotate points
    for _, row in lag_df.iterrows():
        plt.annotate(
            row["date"].strftime("%Y-%m"),
            (row["ndti_lag1"], row["ndvi_mean"]),
            fontsize=6
        )

    plt.title("Nonlinear lagged relationship: NDVI(t) vs NDTI(t-1)")
    plt.xlabel("Lagged turbidity (NDTI)")
    plt.ylabel("NDVI")
    plt.legend()
    plt.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

def plot_model_performance(lag_df: pd.DataFrame, model, output_path: Path):
    y = lag_df["ndvi_mean"]
    y_pred = model.predict()

    plt.figure(figsize=(6, 6))
    plt.scatter(y, y_pred)

    min_val = min(y.min(), y_pred.min())
    max_val = max(y.max(), y_pred.max())

    plt.plot([min_val, max_val], [min_val, max_val], '--')

    plt.xlabel("Observed NDVI")
    plt.ylabel("Predicted NDVI")
    plt.title("Model performance")

    plt.grid(True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()

def plot_residuals(lag_df: pd.DataFrame, model, output_path: Path):
    x = lag_df["ndti_lag1"]
    y = lag_df["ndvi_mean"]
    y_pred = model.predict()

    residuals = y - y_pred

    plt.figure(figsize=(6, 6))
    plt.scatter(x, residuals)

    plt.axhline(0, linestyle="--")

    plt.xlabel("Lagged turbidity (NDTI)")
    plt.ylabel("Residuals")
    plt.title("Residual diagnostics")

    plt.grid(True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()

def get_reference_meta_from_2024(
    index: dict[tuple[int, int], Path],
    variable_name: str,
) -> dict:
    """
    Use the first available 2024 raster as the fixed common reference grid.
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

def load_masked_stack_for_persistence(
    index: dict[tuple[int, int], Path],
    mask_raw: np.ndarray,
    mask_meta: dict,
    vmin: float,
    vmax: float,
    variable_name: str,
) -> tuple[np.ndarray, dict]:
    """
    Load rasters, reproject all of them to the 2024 reference grid,
    reproject mask to the same grid, apply mask, and stack safely.
    """
    arrays = []

    # Fixed common grid = first available 2024 raster
    ref_meta = get_reference_meta_from_2024(index, variable_name)

    # Reproject mask once to the same 2024 grid
    aligned_mask = reproject_mask_to_match(mask_raw, mask_meta, ref_meta)

    for (year, month), tif_path in sorted(index.items()):
        arr, meta = read_raster(tif_path)
        arr = clean_array(arr, vmin, vmax)

        print(
            f"{variable_name} {year}-{month:02d}: "
            f"original shape={arr.shape}, crs={meta['crs']}, res={meta['res']}"
        )

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

    if not arrays:
        raise ValueError("No rasters available for persistence analysis.")

    stack = np.stack(arrays, axis=0)
    return stack, ref_meta

def hotspot_persistence(
    stack: np.ndarray,
    percentile: float = 80.0
) -> tuple[np.ndarray, float]:
    """
    Model 3: Hotspot persistence
    Count number of months where a pixel exceeds the long-term percentile threshold.
    """
    vals = stack[np.isfinite(stack)]
    if vals.size == 0:
        persistence = np.full(stack.shape[1:], np.nan, dtype="float32")
        return persistence, np.nan

    threshold = np.percentile(vals, percentile)
    hotspot = np.isfinite(stack) & (stack >= threshold)
    persistence = hotspot.sum(axis=0).astype("float32")

    no_data = ~np.any(np.isfinite(stack), axis=0)
    persistence[no_data] = np.nan

    return persistence, float(threshold)

def plot_persistence(array: np.ndarray, title: str, output_path: Path) -> None:
    plt.figure(figsize=(8, 7))
    im = plt.imshow(array, cmap="viridis", vmin=0, vmax=5)
    plt.title(title)
    plt.axis("off")
    plt.colorbar(im, shrink=0.8, label="Hotspot months")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()


def main() -> None:
    model_dir = FIG_DIR / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    # Load masks and file indices
    land_mask_raw, land_mask_meta = load_mask(LAND_BUFFER_FILE)
    water_mask_raw, water_mask_meta = load_mask(WATER_BUFFER_FILE)

    ndvi_index = build_variable_index(NDVI_DIR, NDVI_REGEX)
    ndti_index = build_variable_index(NDTI_DIR, NDTI_REGEX)

    # Model 2: Lagged turbidity effect
    monthly_csv = TABLE_DIR / "gof_monthly_coastal_table.csv"
    if monthly_csv.exists():
        print("Fitting intra-seasonal lagged regression...")
        lag_model, lag_df = fit_lagged_model(monthly_csv)

        with open(TABLE_DIR / "model2_intra_seasonal_lagged_regression_summary.txt", "w", encoding="utf-8") as f:
            f.write(lag_model.summary().as_text())

        save_csv(lag_df, TABLE_DIR / "model2_intra_seasonal_lagged_pairs_used.csv")
        plot_lagged_relationship(
            lag_df,
            lag_model,
            model_dir / "model2_intra_seasonal_lagged_ndvi_vs_ndti.png"
        )

        plot_model_performance(
            lag_df,
            lag_model,
            model_dir / "model2_observed_vs_predicted.png"
        )

        plot_residuals(
            lag_df,
            lag_model,
            model_dir / "model2_residuals.png"
        )
    else:
        print(f"Monthly table not found: {monthly_csv}")

    # Model 3: Hotspot persistence
    print("Computing hotspot persistence maps...")
    ndvi_stack, ndvi_meta = load_masked_stack_for_persistence(
        ndvi_index, land_mask_raw, land_mask_meta, NDVI_MIN, NDVI_MAX, "ndvi"
    )
    ndti_stack, ndti_meta = load_masked_stack_for_persistence(
        ndti_index, water_mask_raw, water_mask_meta, NDTI_MIN, NDTI_MAX, "ndti"
    )

    ndvi_persist, ndvi_thr = hotspot_persistence(ndvi_stack, percentile=80)
    ndti_persist, ndti_thr = hotspot_persistence(ndti_stack, percentile=80)

    save_geotiff(RASTER_DIR / "ndvi_hotspot_persistence.tif", ndvi_persist, ndvi_meta)
    save_geotiff(RASTER_DIR / "ndti_hotspot_persistence.tif", ndti_persist, ndti_meta)

    plot_persistence(
        ndvi_persist,
        f"NDVI hotspot persistence (P80 threshold = {ndvi_thr:.3f})",
        model_dir / "ndvi_hotspot_persistence.png"
    )
    plot_persistence(
        ndti_persist,
        f"NDTI hotspot persistence (P80 threshold = {ndti_thr:.3f})",
        model_dir / "ndti_hotspot_persistence.png"
    )

    pd.DataFrame([{
        "ndvi_hotspot_threshold_p80": ndvi_thr,
        "ndti_hotspot_threshold_p80": ndti_thr,
        "n_months_ndvi": ndvi_stack.shape[0],
        "n_months_ndti": ndti_stack.shape[0],
    }]).to_csv(TABLE_DIR / "hotspot_persistence_summary.csv", index=False)

    print("Done.")
    print(f"Model outputs saved under: {model_dir}")
    print(f"Tables saved under: {TABLE_DIR}")
    print(f"Rasters saved under: {RASTER_DIR}")

if __name__ == "__main__":
    main()