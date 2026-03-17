from pathlib import Path

# PROJECT PATHS
PROJECT_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_DIR / "data"
NDVI_DIR = DATA_DIR / "ndvi"
NDTI_DIR = DATA_DIR / "ndti"
MASK_DIR = DATA_DIR / "masks"

OUTPUT_DIR = PROJECT_DIR / "output"
TABLE_DIR = OUTPUT_DIR / "tables"
FIG_DIR = OUTPUT_DIR / "figures"
RASTER_DIR = OUTPUT_DIR / "rasters"

for folder in [TABLE_DIR, FIG_DIR, RASTER_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# FILE PATTERNS
NDVI_REGEX = r"GOF_NDVI_(\d{4})-(\d{2})\.tif$"
NDTI_REGEX = r"GOF_NDTI_(\d{4})-(\d{2})\.tif$"

# MASK FILES
LAND_MASK_FILE = MASK_DIR / "GOF_land_mask.tif"
WATER_MASK_FILE = MASK_DIR / "GOF_water_mask.tif"
LAND_BUFFER_FILE = MASK_DIR / "GOF_land_coastal_buffer_1km.tif"
WATER_BUFFER_FILE = MASK_DIR / "GOF_water_coastal_buffer_1km.tif"

# VALID RANGES
NDVI_MIN = -1.0
NDVI_MAX = 1.0

NDTI_MIN = -1.0
NDTI_MAX = 1.0

# SETTINGS
NDVI_VEG_THRESHOLD = 0.40
NDTI_HIGH_THRESHOLD = 0.10

# PLOT
NDVI_PLOT_MIN = 0.0
NDVI_PLOT_MAX = 0.8

NDTI_PLOT_MIN = -0.2
NDTI_PLOT_MAX = 0.4