# Tutorial 04: Cross-Language Integration (Python + R + lidR + HPC)

Welcome to **Tutorial 04** of the `als-finder` series! In this capstone module, you will learn how to:
1. Interface **R** and the `als-finder` CLI using `jsonlite` and `sf`.
2. Ingest standardized `.copc.laz` and metric grid tiles directly into **`lidR::readLAScatalog()`** in R.
3. Compute essential ecological and forestry metrics in R: Digital Terrain Models (**DTM**), Canopy Height Models (**CHM**), and Individual Tree Detection (**ITD**).
4. Simulate distributed **HPC Slurm Job Arrays** using bash task loops in the cloud.

---

## 1. Querying `als-finder` from R via `jsonlite`

`als-finder` CLI commands support a `--json` flag specifically designed for clean ingestion into R, Python, and automated pipelines without shell parsing hacks:

```r
library(jsonlite)
library(sf)

# 1. Query Grid Info via CLI JSON output
cmd <- "als-finder grid-info --manifest ./demo_workspace/catalog/manifest.json --json"
raw_json <- system(cmd, intern = TRUE)
grid_meta <- fromJSON(paste(raw_json, collapse = ""))

cat("=== Grid Metadata Queried from R ===\n")
cat("Status:", grid_meta$status, "\n")
cat("Grid CRS:", grid_meta$grid_crs, "\n")
cat("Sample Tile Bounds:", grid_meta$sample_tile_bounds, "\n")

# 2. Load the vector grid table in R using sf
grid_gpkg_path <- "demo_workspace/catalog/grid.gpkg"
if (file.exists(grid_gpkg_path)) {
  grid_sf <- st_read(grid_gpkg_path, layer = "grid", quiet = TRUE)
  cat("Successfully loaded", nrow(grid_sf), "grid tiles into R sf dataframe.\n")
}
```

---

## 2. Ingesting Standardized Tiles into `lidR`

The R `lidR` package provides a high-performance framework for airborne LiDAR analysis.
Because `als-finder` organizes files into uniform metric grids with standardized ASPRS classification and spatial buffers, `lidR` can build an out-of-core spatial catalog seamlessly:

```r
library(lidR)
library(terra)

tile_dir <- "demo_workspace/data/tiles"
laz_files <- list.files(tile_dir, pattern = "\\.laz$", full.names = TRUE)

if (length(laz_files) > 0) {
  cat("Loading", length(laz_files), "tiles into lidR::readLAScatalog...\n")
  ctg <- readLAScatalog(tile_dir)
  
  # Set chunk options to align with als-finder 1200m grid
  opt_chunk_size(ctg) <- 1200
  opt_chunk_buffer(ctg) <- 30
  opt_progress(ctg) <- FALSE
  
  cat("Catalog CRS:", st_crs(ctg)$proj4string, "\n")
  cat("Total Points:", sum(ctg$Number.of.point.records), "\n")
  
  # 1. Generate 1m Digital Terrain Model (DTM)
  cat("Generating 1m DTM (TIN interpolation)...\n")
  dtm <- rasterize_terrain(ctg, res = 1.0, algorithm = tin())
  
  # 2. Generate 1m Canopy Height Model (CHM)
  cat("Generating 1m CHM (Pit-free algorithm)...\n")
  chm <- rasterize_canopy(ctg, res = 1.0, algorithm = p2r())
  
  # 3. Individual Tree Detection (ITD)
  cat("Running Individual Tree Detection (lmf)...\n")
  trees <- locate_trees(chm, lmf(ws = 5.0))
  cat("Detected", length(trees), "individual tree stems!\n")
}
```

---

## 3. Simulating an HPC Slurm Job Array

On high-performance supercomputing clusters (like SDSC Expanse), you submit a Slurm job array where each worker processes an isolated task ID (`$SLURM_ARRAY_TASK_ID`).

Here is how you can simulate a 4-task parallel job array directly in your cloud environment using a bash loop:

```bash
MANIFEST="./demo_workspace/catalog/manifest.json"
OUT_DIR="./demo_workspace/data/array_tiles"
mkdir -p "${OUT_DIR}"

echo "Simulating Slurm Job Array (Tasks 0 to 3)..."
for TASK_ID in 0 1 2 3; do
    echo "[Worker ${TASK_ID}] Streaming Tile ${TASK_ID}..."
    als-finder fetch-tile \
        --manifest "${MANIFEST}" \
        --tile-id "${TASK_ID}" \
        --output "${OUT_DIR}/tile_${TASK_ID}.laz" \
        --buffer-size 30 \
        --crs "EPSG:32610" \
        --json > /dev/null
done

echo "Array simulation complete! Resulting tiles:"
ls -lh "${OUT_DIR}"
```

---

### 👉 Summary & Next Steps
You have completed the entire **ALS-Finder Tutorial Curriculum**! 
You are now equipped to deploy `als-finder` across your own research projects, cloud environments, and HPC computing clusters.
