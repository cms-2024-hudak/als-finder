# Tutorial 04: Cross-Language Integration (Python + R + lidR + HPC)

Welcome to **Tutorial 04** of the `als-finder` series! In this capstone module, you will learn how to:
1. Interface **R** and the `als-finder` CLI using `jsonlite` and `sf`.
2. Ingest standardized `.laz` and metric grid tiles directly into **`lidR::readLAScatalog()`** in R.
3. Compute essential ecological and forestry metrics in R: Digital Terrain Models (**DTM**), Canopy Height Models (**CHM**), and Individual Tree Detection (**ITD**).
4. Scale out on HPC clusters using **`als-finder plan --tasks`** to drive Slurm job arrays.
5. Create a seamless, unbuffered regional raster mosaic using companion metadata sidecars (`crop_gdal_te`).

---

## 1. Querying `als-finder` from R via `jsonlite`

`als-finder` CLI commands support a `--json` flag specifically designed for clean ingestion into R, Python, and automated pipelines without shell parsing hacks:

```r
library(jsonlite)
library(sf)

# 1. Query Grid Info via CLI JSON output
cmd <- "als-finder plan --workspace ./scratch/tahoe_workspace --json"
raw_json <- system(cmd, intern = TRUE)
grid_meta <- fromJSON(paste(raw_json, collapse = ""))

cat("=== Grid Metadata Queried from R ===\n")
cat("Status:", grid_meta$status, "\n")
cat("Grid CRS:", grid_meta$grid_crs, "\n")
cat("Total Tiles:", grid_meta$total_tiles, "\n")
cat("Sample Tile Bounds:", grid_meta$sample_tile_bounds, "\n")

# 2. Load the vector grid table in R using sf
grid_gpkg_path <- "scratch/tahoe_workspace/catalog/grid.gpkg"
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

tile_dir <- "scratch/tahoe_workspace/data/tiles"
laz_files <- list.files(tile_dir, pattern = "\\.laz$", full.names = TRUE, recursive = TRUE)

if (length(laz_files) > 0) {
  cat("Loading", length(laz_files), "tiles into lidR::readLAScatalog...\n")
  ctg <- readLAScatalog(tile_dir)
  
  # Set chunk options to align with als-finder 500m grid and 50m buffer
  opt_chunk_size(ctg) <- 500
  opt_chunk_buffer(ctg) <- 50
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

## 3. HPC Slurm Scaling with Dynamic Task Lists (`plan --tasks`)

On supercomputing clusters (like SDSC Expanse, NERSC Perlmutter, or university clusters), you should never hardcode array ranges. Instead, generate the exact list of leaf tile IDs directly from `als-finder plan --tasks`:

```bash
# Generate flat leaf task list (one per line, including any split quadrants like 0_NW)
als-finder plan --workspace ./scratch/tahoe_workspace --tasks > tasks.txt
cat tasks.txt
```

### Production Slurm Job Array Script (`stream_tiles.slurm`):
```bash
#!/bin/bash
#SBATCH --job-name=als_tiles
#SBATCH --array=1-16%4
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=logs/tile_%a.out

# Read the specific tile ID for this Slurm array index
TILE_ID=$(sed -n "${SLURM_ARRAY_TASK_ID}p" tasks.txt)

echo "Processing Leaf Task: ${TILE_ID}"

# 1. Stream single buffered tile (with automatic sidecar)
als-finder fetch tile "${TILE_ID}" \
  --workspace ./scratch/tahoe_workspace \
  --output /scratch/$USER/tiles/ \
  --sidecar

# 2. Run local scientific processing (e.g., Rscript or PDAL ground filter)
# ...

# 3. Clean up raw tile to maintain zero-disk footprint
rm "/scratch/$USER/tiles/*_${TILE_ID}.laz"
```

---

## 4. Seamless Unbuffered Mosaicking (1-Line GDAL VRT)

Because each tile was streamed with a 50m buffer to eliminate edge interpolation tears, the companion `.json` metadata sidecar provides the exact unbuffering bounding box (`crop_gdal_te`).

Using GDAL, you can assemble a seamless, regional raster mosaic with **zero edge-effect artifacts** and zero disk duplication:

```bash
# 1. Extract crop coordinates from sidecar
TE=$(python3 -c "import json; data=json.load(open('scratch/tahoe_workspace/data/tiles/.../tile_0.json')); print(' '.join(map(str, data['crop_gdal_te'])))")

# 2. Build unbuffered VRT for each tile (virtually crops out the 50m buffer)
gdalbuildvrt -te ${TE} tile_0_clean.vrt tile_0_dtm.tif

# 3. Combine all clean tile VRTs into a seamless regional mosaic
gdalbuildvrt regional_dtm_mosaic.vrt tile_*_clean.vrt

echo "✓ Created seamless regional raster mosaic: regional_dtm_mosaic.vrt"
```

---

## Summary & Next Steps

Congratulations! You have completed the entire **ALS-Finder Master Curriculum**:
- **Discovery**: Federated search across multi-agency LiDAR archives.
- **Planning**: Metric 500m grid partitioning, memory audits, and Slurm task lists.
- **Acquisition**: On-demand streaming of LAZ and COPC formats with automatic OOM quadrant subdivision.
- **Standardization**: SMRF ground filtering, HAG normalization, and OGC STAC generation.
- **Integration**: Native R `lidR` catalogs, Slurm job arrays, and seamless GDAL VRT mosaicking.
