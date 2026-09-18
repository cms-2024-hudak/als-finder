# Tutorial: Scaling LiDAR Metric Extraction with als-finder and Slurm

This tutorial provides a complete, production-grade guide for integrating **`als-finder`** with **Lilian Vallet's LiDAR metric extraction workflow** ([`scratch/sample_workflow/extract_lidar_metrics.R`](file:///mnt/c/Users/gears/git/als-finder/scratch/sample_workflow/extract_lidar_metrics.R)) on High-Performance Computing (HPC) clusters managed by Slurm.

---

## 1. Architectural Overview & The Master Planning Step

### Am I correct that the first step must be a planning step stored in a shared location?

**Yes, absolutely.** In distributed HPC environments, having individual compute worker nodes query remote cloud repositories (such as USGS 3DEP AWS S3 buckets or NOAA) independently is an anti-pattern. If 500 or 1,000 parallel Slurm tasks each try to query the remote API and calculate grid boundaries, several problems occur:
1. **API Rate Limiting & Throttling:** Hundreds of workers hammer remote STAC/EPT metadata endpoints with redundant queries.
2. **Race Conditions & Discrepancies:** Slight floating-point discrepancies or CRS transformation differences could cause neighboring tiles to have mismatched bounding boxes or misaligned rasters.
3. **Wasted Cluster Core-Hours:** Computing spatial intersections across large areas takes time that compute workers shouldn't waste.

### The Decoupled Architecture:
```text
  ┌───────────────────────────────────────────────────────────────────┐
  │ PHASE 1: MASTER PRE-FLIGHT PLANNING (Run ONCE on Head/Login Node) │
  │   1. Define AOI polygon/shapefile & target year                   │
  │   2. Search remote USGS 3DEP / NOAA catalogs                      │
  │   3. Generate uniform 1000m grid with 10m buffer in grid.gpkg     │
  │   4. Export clean task manifest (tasks.tsv) to shared storage     │
  └─────────────────────────────────┬─────────────────────────────────┘
                                    │
           Stored on Shared Storage │ (/project/lidar_run/)
                                    ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │ PHASE 2: SLURM JOB ARRAY EXECUTION (Run N times across Cluster)   │
  │   #SBATCH --array=1-N%50                                          │
  │                                                                   │
  │   Compute Node 1                Compute Node 2                    │
  │   (Task 1: Tile 1175)           (Task 2: Tile 1176)               │
  │   ┌───────────────────────────┐ ┌───────────────────────────┐     │
  │   │ 1. Read row 1 from tasks  │ │ 1. Read row 2 from tasks  │     │
  │   │ 2. Stream LAZ to local    │ │ 2. Stream LAZ to local    │     │
  │   │    $SLURM_SCRATCH (NVMe)  │ │    $SLURM_SCRATCH (NVMe)  │     │
  │   │ 3. Run extract_lidar_     │ │ 3. Run extract_lidar_     │     │
  │   │    metrics.R on 1 tile    │ │    metrics.R on 1 tile    │     │
  │   │ 4. Sync *.tif to shared   │ │ 4. Sync *.tif to shared   │     │
  │   │    outputs directory      │ │    outputs directory      │     │
  │   │ 5. Purge local scratch    │ │ 5. Purge local scratch    │     │
  │   └───────────────────────────┘ └───────────────────────────┘     │
  └─────────────────────────────────┬─────────────────────────────────┘
                                    │
                                    ▼
  ┌───────────────────────────────────────────────────────────────────┐
  │ PHASE 3: SEAMLESS MOSAICKING (Run ONCE after Array Completes)     │
  │   - Build virtual raster (VRT) or merge GeoTIFFs with GDAL        │
  │   - Exact metric grid alignment guaranteed by als-finder grid     │
  └───────────────────────────────────────────────────────────────────┘
```

---

## 2. Phase 1: Shared Pre-Flight Master Planning

Run this phase **once** on the login node or a lightweight 1-core interactive job. All outputs are saved to the cluster's shared filesystem (e.g., Lustre/NFS at `/project/my_lab/lidar_workspace`).

### Step 1.1: Search Remote Datasets
Search for available point clouds covering your Area of Interest (AOI):
```bash
# Set your shared workspace path
export SHARED_DIR="/project/my_lab/sierra_lidar_2022"
mkdir -p "$SHARED_DIR"

# Search for USGS 3DEP / NOAA ALS data intersecting the AOI
als-finder search \
  --aoi "$SHARED_DIR/aoi_boundary.geojson" \
  --year-min 2020 \
  --year-max 2024 \
  --output "$SHARED_DIR/catalog.gpkg"
```

### Step 1.2: Generate the Regularized Tiling Grid
Generate a spatial grid of $1000\,\text{m} \times 1000\,\text{m}$ tiles with an integrated $10\,\text{m}$ spatial buffer. `als-finder` automatically aligns the grid to integer coordinates in the target projection (e.g., UTM Zone 11N or Web Mercator):
```bash
als-finder plan \
  --catalog "$SHARED_DIR/catalog.gpkg" \
  --tile-size 1000 \
  --buffer 10 \
  --crs EPSG:32611 \
  --output "$SHARED_DIR/grid.gpkg"
```

### Step 1.3: Export the Task Manifest
Export a simple tab-delimited or line-delimited task list. Slurm job array workers will look up their task using their `$SLURM_ARRAY_TASK_ID`:
```bash
als-finder export-tasks \
  --grid "$SHARED_DIR/grid.gpkg" \
  --output "$SHARED_DIR/task_list.tsv"
```
Each row in `task_list.tsv` contains:
```text
tile_id    dataset_name             min_x    min_y    max_x    max_y    epsg
1175       CA_SierraNevada_8_2022   764000   4326000  765000   4327000  32611
1176       CA_SierraNevada_8_2022   764000   4327000  765000   4328000  32611
```

---

## 3. Phase 2: Slurm Job Array Architecture

Here is the complete Slurm batch script (`sbatch_lidar_workflow.slurm`) ready to submit on the cluster.

### Key Engineering Practices Implemented:
1. **Node-Local Scratch (`$SLURM_SCRATCH`):** Remote points are streamed directly into fast node-local NVMe SSDs instead of overloading the shared Lustre/NFS network filesystem with temporary files.
2. **Deterministic Spatial Basenames (`--spatial-name`):** Files are named `CA_SierraNevada_8_2022_tile_E0764000_N4326000.laz`, enabling instant spatial identification without opening the file.
3. **Metadata Sidecar (`--sidecar`):** An accompanying `tile.json` file records exact core and buffered coordinates, source CRS, point counts, and acquisition dates.
4. **Buffer Dimension Tagging (`buffer=uint8`):** Points inside the $10\,\text{m}$ buffer collar are flagged with `buffer=1` (core points `buffer=0`), allowing `extract_lidar_metrics.R`'s `remove_las_buffer()` to cleanly drop them after terrain normalization.
5. **Memory Safety & lidR Resource Control:** 
   - Assign **1 tile per Slurm task**.
   - Allocate 1–2 CPUs (`#SBATCH --cpus-per-task=2`).
   - Set `CHUNK_BUFFER=0` in the environment so `lidR` does not attempt to add its own internal secondary buffer on top of `als-finder`'s buffer.

### Complete Slurm Script (`sbatch_lidar_workflow.slurm`):
```bash
#!/bin/bash
#SBATCH --job-name=als_metrics
#SBATCH --output=/project/my_lab/sierra_lidar_2022/logs/tile_%a_%j.out
#SBATCH --error=/project/my_lab/sierra_lidar_2022/logs/tile_%a_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --partition=compute
#SBATCH --array=1-1000%50

set -euo pipefail

# 1. Environment Setup
SHARED_DIR="/project/my_lab/sierra_lidar_2022"
MODULE_ENV="als-finder-env"

# Activate your conda/micromamba environment
source ~/.bashrc
conda activate "$MODULE_ENV"

# 2. Identify the Tile from the Task Manifest
TASK_FILE="$SHARED_DIR/task_list.tsv"
# Read line corresponding to SLURM_ARRAY_TASK_ID (skipping header)
LINE_NUM=$((SLURM_ARRAY_TASK_ID + 1))
TASK_LINE=$(sed -n "${LINE_NUM}p" "$TASK_FILE")

TILE_ID=$(echo "$TASK_LINE" | awk '{print $1}')
DATASET=$(echo "$TASK_LINE" | awk '{print $2}')

echo "=== Processing Task $SLURM_ARRAY_TASK_ID: Tile $TILE_ID ($DATASET) on $(hostname) ==="

# 3. Setup Node-Local Scratch Directory
LOCAL_DIR="${SLURM_SCRATCH:-/tmp}/${USER}_job_${SLURM_JOB_ID}_task_${SLURM_ARRAY_TASK_ID}"
LOCAL_IN="$LOCAL_DIR/data"
LOCAL_OUT="$LOCAL_DIR/output"
mkdir -p "$LOCAL_IN" "$LOCAL_OUT"

# Ensure cleanup on exit
cleanup() {
    echo "Cleaning up local scratch: $LOCAL_DIR"
    rm -rf "$LOCAL_DIR"
}
trap cleanup EXIT

# 4. Stream Tile laz from Remote EPT/COPC into Node-Local Scratch
als-finder stream \
  --grid "$SHARED_DIR/grid.gpkg" \
  --tile-id "$TILE_ID" \
  --output "$LOCAL_IN" \
  --spatial-name \
  --sidecar \
  --buffer-tagging

# 5. Run Lilian's Metric Extraction Script
# Notice: No modifications needed to extract_lidar_metrics.R!
export PROJECT_DIR="$LOCAL_DIR"
export DATA_FOLDER="$LOCAL_IN"
export OUTPUT_FOLDER="$LOCAL_OUT"
export PROCESSING_MODE="tiles"
export CHUNK_BUFFER="0"
export SLURM_CPUS_PER_TASK=2

Rscript /project/my_lab/scripts/extract_lidar_metrics.R

# 6. Copy Deliverables to Shared Storage
DEST_METRICS="$SHARED_DIR/outputs/metrics"
DEST_LAZ="$SHARED_DIR/outputs/normalized_laz"
mkdir -p "$DEST_METRICS" "$DEST_LAZ"

echo "Syncing results to shared storage..."
cp "$LOCAL_OUT"/metrics/*.tif "$DEST_METRICS/" 2>/dev/null || true
cp "$LOCAL_OUT"/metrics/*.csv "$DEST_METRICS/" 2>/dev/null || true
cp "$LOCAL_OUT"/normalized_tiles/*.laz "$DEST_LAZ/" 2>/dev/null || true
cp "$LOCAL_IN"/*.json "$DEST_METRICS/" 2>/dev/null || true

echo "=== Task $SLURM_ARRAY_TASK_ID Complete ==="
```

---

## 4. Phase 3: Raster Alignment & Mosaicking

A critical requirement when generating tiled rasters is ensuring they seamlessly stitch together into a seamless regional mosaic without gaps, edge distortion, or sub-pixel shifts.

### 4.1 Grid Snapping & Origin Alignment
`als-finder`'s regular grid is mathematically locked:
- **Tile Dimensions:** Exactly $1000\,\text{m} \times 1000\,\text{m}$.
- **Resolution:** Exactly $10\,\text{m}$ per pixel.
- **Snapping:** Tile origins are snapped to exact multiples of $1000\,\text{m}$ (e.g., $E=764000, N=4326000$).
- **Sub-pixel Alignment:** Because both $1000$ and the tile bounds are divisible by $10$, every raster cell edge aligns with 0 sub-pixel offset across all neighboring tiles.

### 4.2 Handling the 10 m Buffer Collar
Because `als-finder` streams a $10\,\text{m}$ buffer on each side (total bounding box $1020\,\text{m} \times 1020\,\text{m}$), Lilian's script produces a $102 \times 102$ cell raster.
- Neighboring tiles share a 2-pixel ($20\,\text{m}$) overlapping boundary strip.
- Because ground classification (CSF) and height normalization used the buffer, pixel values in the overlap agree closely.
- **Method A (Standard GDAL Mosaic):** `gdal_merge.py` or `gdalbuildvrt` can mosaic these tiles directly. GDAL resolves overlapping pixels by taking the first or last tile, or a blend.
- **Method B (Exact 0-Overlap Core Cropping):** If you prefer strict non-overlapping $100 \times 100$ cell rasters ($1000\,\text{m} \times 1000\,\text{m}$), use the `tile.json` sidecar created by `als-finder`:
  ```r
  # Optional 2-line crop in R using sidecar bounds
  sidecar <- jsonlite::fromJSON(sub("\\.laz$", ".json", laz_file))
  cb <- sidecar$core_bounds  # [xmin, ymin, xmax, ymax]
  core_ext <- terra::ext(cb[1], cb[3], cb[2], cb[4])
  r_cropped <- terra::crop(r, core_ext)
  terra::writeRaster(r_cropped, out_tif, overwrite=TRUE)
  ```

### 4.3 Mosaicking All Tiles After Job Completion
Once the Slurm array completes, stitch the output GeoTIFFs into a single seamless regional layer:
```bash
cd /project/my_lab/sierra_lidar_2022/outputs/metrics

# Option 1: Fast Zero-Disk Virtual Raster (VRT)
gdalbuildvrt canopy_cover_mosaic.vrt *canopy_cover*.tif

# Option 2: Cloud-Optimized GeoTIFF (COG)
gdal_translate -of COG -co COMPRESS=DEFLATE canopy_cover_mosaic.vrt canopy_cover_2022_sierra.tif
```

---

## 5. Summary of Best Practices for Lilian's Workflow

| Parameter | Recommended Setting | Why? |
| :--- | :--- | :--- |
| **Grid Generation** | Pre-flight `als-finder plan` | Single shared master index; no duplicate remote queries or race conditions. |
| **Storage Strategy** | Stream to `$SLURM_SCRATCH` | Keeps heavy I/O on node NVMe SSD; shared Lustre only stores final light products. |
| **File Naming** | `--spatial-name` | Produces `..._E0764000_N4326000.laz`, making files self-documenting. |
| **Metadata** | `--sidecar` | Writes `tile.json` containing core bounds, EPSG, date, and point counts. |
| **lidR Buffer** | `CHUNK_BUFFER="0"` | `als-finder` provides the 10m buffer; avoids double-buffering. |
| **Slurm CPUs per Task** | 1 or 2 CPUs | Prevents `future::multisession` memory spikes; ensures predictable ~3.5 GB RAM per job. |
| **Buffer Stripping** | `remove_las_buffer(las)` | Unmodified R script removes all buffer collar points from normalized LAZ. |
