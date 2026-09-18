# Tutorial: Scaling LiDAR Metric Extraction with als-finder and Slurm

This tutorial provides a complete, production-grade guide for integrating **`als-finder`** with **Lilian Vallet's LiDAR metric extraction workflow** ([`scratch/sample_workflow/extract_lidar_metrics.R`](file:///mnt/c/Users/gears/git/als-finder/scratch/sample_workflow/extract_lidar_metrics.R)) on High-Performance Computing (HPC) clusters managed by Slurm.

---

## 1. Architectural Overview & The Master Planning Step

### Distributed Architecture Rationale: Shared Pre-Flight Planning

In distributed HPC environments, having individual compute worker nodes query remote cloud repositories independently is an anti-pattern. `als-finder` supports a broad spectrum of federal, scientific, and community providers:
- **USGS 3DEP** (USGS 3D Elevation Program AWS EPT & WESM)
- **NOAA Digital Coast** (Coastal LiDAR PDS)
- **OpenTopography** (High-resolution community & agency point clouds)
- **NEON** (National Ecological Observatory Network AOP discrete-return LiDAR)
- **NASA G-LiHT** (Goddard's LiDAR, Hyperspectral & Thermal airborne acquisitions)
- **NASA Earthdata** (Airborne & spaceborne missions)

Allowing hundreds or thousands of worker nodes to independently search and resolve spatial grids against these remote APIs introduces three critical points of failure:
1. **API Rate Limiting & Throttling:** Hundreds of workers hammer remote STAC/EPT metadata endpoints with redundant queries, causing HTTP 429/503 connection dropouts.
2. **Coordinate Discrepancies & Half-Pixel Shifts:** If workers compute their own bounding boxes or projections independently, slight floating-point differences can lead to non-overlapping seams or misaligned raster cells.
3. **Wasted Cluster Core-Hours:** Having compute nodes repeatedly perform spatial polygon intersections burns allocation hours that should be dedicated to point-cloud processing.

### The Decoupled Architecture
```text
  ┌────────────────────────────────────────────────────────────────────────┐
  │ PHASE 1: MASTER PRE-FLIGHT PLANNING (Run ONCE on Head/Login Node)      │
  │   1. Define Region of Interest (ROI) polygon/bbox and search filters   │
  │   2. Search remote catalogs across supported providers into catalog/   │
  │   3. Build regularized grid (e.g. 1000m tiles + 10m buffer) in grid.gpkg│
  │   4. Export task manifest and metadata table to shared cluster storage │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
           Shared Cluster Storage     │ (/project/my_lab/lidar_project/)
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ PHASE 2: SLURM JOB ARRAY EXECUTION (Run N times across Cluster)        │
  │   #SBATCH --array=1-N%50                                               │
  │                                                                        │
  │   Compute Node 1                       Compute Node 2                  │
  │   (Task 1: Tile 1175)                  (Task 2: Tile 1176)             │
  │   ┌────────────────────────────────┐   ┌─────────────────────────────┐ │
  │   │ 1. Read row 1 from manifest    │   │ 1. Read row 2 from manifest │ │
  │   │ 2. Stream LAZ to local         │   │ 2. Stream LAZ to local      │ │
  │   │    $SLURM_SCRATCH (NVMe SSD)   │   │    $SLURM_SCRATCH (NVMe SSD)│ │
  │   │ 3. Run extract_lidar_metrics.R │   │ 3. Run extract_lidar_       │ │
  │   │    on 1 tile (1-2 CPUs, 3.5GB) │   │    metrics.R                │ │
  │   │ 4. Sync *.tif / *.laz to shared│   │ 4. Sync *.tif / *.laz       │ │
  │   │    outputs directory           │   │    to shared storage        │ │
  │   │ 5. Purge local scratch         │   │ 5. Purge local scratch      │ │
  │   └────────────────────────────────┘   └─────────────────────────────┘ │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ PHASE 3: SEAMLESS MOSAICKING (Run ONCE after Array Completes)          │
  │   - Build virtual raster (VRT) or Cloud-Optimized GeoTIFF with GDAL    │
  │   - Exact metric grid alignment guaranteed by als-finder tiling grid   │
  └────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Phase 1: Shared Pre-Flight Master Planning

Execute this phase **once** on the login node or a lightweight 1-core interactive job. All outputs are saved to the cluster's shared filesystem (e.g., Lustre, GPFS, or NFS at `/project/my_lab/lidar_project`).

### Step 1.1: Search Remote Datasets Across Providers
Search for point clouds intersecting your Region of Interest (ROI). You can search across all supported archives simultaneously, or filter by specific providers:

```bash
# Set your shared project workspace path
export SHARED_DIR="/project/my_lab/lidar_project"
mkdir -p "$SHARED_DIR"

# Option A: Search across all supported public archives
als-finder search \
  --roi "$SHARED_DIR/aoi_boundary.geojson" \
  --date 2018:2024 \
  --workspace "$SHARED_DIR"

# Option B: Target specific providers (comma-separated: usgs, noaa, opentopography, neon, gliht, earthdata)
als-finder search \
  --roi "$SHARED_DIR/aoi_boundary.geojson" \
  --provider usgs,noaa \
  --cloud-native \
  --workspace "$SHARED_DIR"
```
This indexes all intersecting surveys and cloud-native endpoints into `$SHARED_DIR/catalog/manifest.json` and `catalog/catalog.gpkg`.

### Step 1.2: Generate the Regularized Tiling Grid
Generate a regularized spatial grid with your chosen core tile size (e.g., $1000\,\text{m}$) and overlap buffer collar (e.g., $10\,\text{m}$):
```bash
als-finder plan \
  --workspace "$SHARED_DIR" \
  --tile-size 1000 \
  --buffer-size 10
```
*Grid Alignment Guarantee:* `als-finder` automatically snaps tile origins to exact metric multiples in the target projected coordinate system. This guarantees that downstream raster cells across neighboring tiles align with zero sub-pixel shear or offset.

### Step 1.3: Export the Slurm Task Manifest
Export a task list where each line corresponds directly to a `$SLURM_ARRAY_TASK_ID`:
```bash
als-finder plan \
  --workspace "$SHARED_DIR" \
  --tasks > "$SHARED_DIR/task_list.tsv"
```

### Step 1.4: Metadata Integration (JSON Sidecar vs. Tabular CSV)

#### The JSON Sidecar (`--sidecar`)
When streaming point clouds, passing `--sidecar` creates an adjacent `tile.json` containing:
- Exact spatial bounds: `core_bounds` ($1000\,\text{m}$) and `buffered_bounds` ($1020\,\text{m}$).
- Pre-formatted CLI arguments: `crop_gdal_te` (`"xmin ymin xmax ymax"`).
- Point density & memory auditing: `est_points`, `is_hyperdense`, and `recommended_mem_gb`.
- Data provenance: `dataset_id`, `provider`, source URLs, and EPSG coordinate system.

#### Flattening Metadata Directly into CSV
If you prefer a single tabular metadata file rather than loose JSON files:
1. **Pre-Flight Manifest (`tasks.csv`):** All sidecar properties already exist inside `$SHARED_DIR/catalog/grid.gpkg`. You can query or export a comprehensive CSV table where each row provides the tile ID, dataset, core bounding coordinates, and point estimates:
   ```csv
   tile_id,basename,dataset,provider,core_minx,core_miny,core_maxx,core_maxy,gdal_te,est_points
   1175,CA_SierraNevada_8_2022_tile_E0764000_N4326000,CA_SierraNevada_8_2022,USGS_EPT,764000,4325000,765000,4326000,"764000 4325000 765000 4326000",26155656
   1176,CA_SierraNevada_8_2022_tile_E0764000_N4327000,CA_SierraNevada_8_2022,USGS_EPT,764000,4326000,765000,4327000,"764000 4326000 765000 4327000",27812010
   ```
2. **Post-Processing Tile Metrics Summary:** If your downstream workflow generates summary metrics per tile (such as mean canopy cover or 95th percentile height), the sidecar metadata can be bound directly into a master `summary_metrics.csv` table using R or Python:
   ```r
   # In R: Bind tile metadata with extracted forest statistics
   sc <- jsonlite::fromJSON(sub("\\.laz$", ".json", laz_path))
   summary_row <- data.frame(
     tile_id = sc$tile_id,
     basename = sc$basename,
     dataset = sc$dataset_id,
     provider = sc$provider,
     core_minx = sc$core_bounds[1],
     core_miny = sc$core_bounds[2],
     core_maxx = sc$core_bounds[3],
     core_maxy = sc$core_bounds[4],
     mean_canopy_cover = mean(terra::values(r_cover), na.rm=TRUE)
   )
   write.table(summary_row, file=file.path(shared_out, "regional_metrics.csv"), 
               append=TRUE, sep=",", row.names=FALSE, col.names=!file.exists(file.path(shared_out, "regional_metrics.csv")))
   ```

---

## 3. Phase 2: Slurm Job Array Architecture

Here is the complete Slurm batch submission script (`sbatch_lidar_metrics.slurm`):

### Key Engineering Practices Implemented:
1. **Node-Local Scratch (`$SLURM_SCRATCH`):** Temporary point clouds stream directly into node-local NVMe SSDs instead of overloading the shared Lustre/NFS network filesystem.
2. **Deterministic Spatial Basenames (`--spatial-name`):** Files are named with their metric coordinates (e.g. `<dataset>_tile_E0764000_N4326000.laz`), enabling instant spatial identification without parsing point headers.
3. **Buffer Dimension Tagging (`buffer=uint8`):** Points inside the buffer collar are stamped with `buffer=1` (core points `buffer=0`), allowing `extract_lidar_metrics.R`'s `remove_las_buffer()` to purge buffer collar points after ground classification and height normalization.
4. **Memory Safety & Resource Allocation:**
   - Assign **1 tile per Slurm task**.
   - Allocate 1–2 CPUs (`#SBATCH --cpus-per-task=2`).
   - Set `CHUNK_BUFFER=0` in the environment to prevent `lidR` from generating a redundant secondary buffer.
   - Restricts memory to **~3.5 GB peak per worker**, eliminating Slurm Out-Of-Memory (OOM) kills.

### Complete Slurm Script (`sbatch_lidar_metrics.slurm`):
```bash
#!/bin/bash
#SBATCH --job-name=als_metrics
#SBATCH --output=/project/my_lab/lidar_project/logs/tile_%a_%j.out
#SBATCH --error=/project/my_lab/lidar_project/logs/tile_%a_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --partition=compute
#SBATCH --array=1-1000%50

set -euo pipefail

# 1. Environment & Setup
SHARED_DIR="/project/my_lab/lidar_project"
source ~/.bashrc
conda activate als-finder-env

# 2. Identify the Assigned Tile from Manifest
TASK_FILE="$SHARED_DIR/task_list.tsv"
LINE_NUM=$((SLURM_ARRAY_TASK_ID + 1))
TASK_LINE=$(sed -n "${LINE_NUM}p" "$TASK_FILE")

TILE_ID=$(echo "$TASK_LINE" | awk '{print $1}')
echo "=== Task $SLURM_ARRAY_TASK_ID: Processing Tile $TILE_ID on $(hostname) ==="

# 3. Setup Node-Local Scratch Directory
LOCAL_DIR="${SLURM_SCRATCH:-/tmp}/${USER}_job_${SLURM_JOB_ID}_task_${SLURM_ARRAY_TASK_ID}"
LOCAL_IN="$LOCAL_DIR/data"
LOCAL_OUT="$LOCAL_DIR/output"
mkdir -p "$LOCAL_IN" "$LOCAL_OUT"

cleanup() {
    rm -rf "$LOCAL_DIR"
}
trap cleanup EXIT

# 4. Stream Tile On-Demand into Node-Local Scratch
als-finder fetch tile "$TILE_ID" \
  --workspace "$SHARED_DIR" \
  --output "$LOCAL_IN" \
  --tile-size 1000 \
  --buffer-size 10 \
  --spatial-name \
  --sidecar

# 5. Run Lilian's Metric Extraction Script (Unmodified)
export PROJECT_DIR="$LOCAL_DIR"
export DATA_FOLDER="$LOCAL_IN"
export OUTPUT_FOLDER="$LOCAL_OUT"
export PROCESSING_MODE="tiles"
export CHUNK_BUFFER="0"
export SLURM_CPUS_PER_TASK=2

Rscript /project/my_lab/scripts/extract_lidar_metrics.R

# 6. Synchronize Final Products to Shared Storage
DEST_METRICS="$SHARED_DIR/outputs/metrics"
DEST_LAZ="$SHARED_DIR/outputs/normalized_tiles"
mkdir -p "$DEST_METRICS" "$DEST_LAZ"

echo "Syncing deliverables to shared storage..."
cp "$LOCAL_OUT"/metrics/*.tif "$DEST_METRICS/" 2>/dev/null || true
cp "$LOCAL_OUT"/metrics/*.csv "$DEST_METRICS/" 2>/dev/null || true
cp "$LOCAL_OUT"/normalized_tiles/*.laz "$DEST_LAZ/" 2>/dev/null || true
cp "$LOCAL_IN"/*.json "$DEST_METRICS/" 2>/dev/null || true

echo "=== Task $SLURM_ARRAY_TASK_ID Finished Successfully ==="
```

---

## 4. Phase 3: Raster Alignment & Mosaicking

A core requirement of regional tiled processing is guaranteeing that output GeoTIFFs align without gaps, distortion, or sub-pixel shear.

### 4.1 Sub-Pixel Alignment Verification
`als-finder` enforces mathematically locked metric grid origins:
$$\text{Origin } X \pmod{\text{pixel\_res}} = 0, \quad \text{Origin } Y \pmod{\text{pixel\_res}} = 0$$
Both $1000\,\text{m}$ tile boundaries and $10\,\text{m}$ raster pixel centers align with 0 sub-pixel offset across all neighboring tiles.

### 4.2 Handling the Buffer Collar
Because `als-finder` streams a spatial buffer collar (total bounds $1020\,\text{m} \times 1020\,\text{m}$), Lilian's script generates a $102 \times 102$ cell raster.
- Neighboring tiles share a 2-pixel ($20\,\text{m}$) overlapping boundary strip.
- Because CSF ground classification and height normalization utilized the full buffer collar, pixel values in this overlapping strip are in close agreement.
- Standard tools (`gdalbuildvrt` or `gdal_merge.py`) merge these overlapping tiles seamlessly.
- **Optional 0-Overlap Core Cropping:** If strict $100 \times 100$ non-overlapping rasters are preferred, crop each tile in R using `core_bounds` from the `tile.json` sidecar before saving:
  ```r
  sidecar <- jsonlite::fromJSON(sub("\\.laz$", ".json", laz_file))
  cb <- sidecar$core_bounds  # [xmin, ymin, xmax, ymax]
  core_ext <- terra::ext(cb[1], cb[3], cb[2], cb[4])
  r_cropped <- terra::crop(r, core_ext)
  terra::writeRaster(r_cropped, out_tif, overwrite=TRUE)
  ```

### 4.3 Regional Mosaicking Command
Once all Slurm array tasks finish, stitch the output GeoTIFFs into a single seamless regional raster:
```bash
cd /project/my_lab/lidar_project/outputs/metrics

# Step 1: Build Virtual Raster (instantaneous, zero disk overhead)
gdalbuildvrt regional_canopy_cover.vrt *canopy_cover*.tif

# Step 2: Export Cloud-Optimized GeoTIFF (COG)
gdal_translate -of COG -co COMPRESS=DEFLATE regional_canopy_cover.vrt regional_canopy_cover_cog.tif
```

---

## 5. Summary of Best Practices

| Workflow Component | Recommended Setting | Engineering Rationale |
| :--- | :--- | :--- |
| **Grid Generation** | Pre-flight `als-finder plan` | Single shared master index; eliminates redundant remote API queries and race conditions. |
| **Provider Scope** | Multi-Provider (`--provider` or omit) | Unifies USGS 3DEP, NOAA, OpenTopography, NEON, G-LiHT, and Earthdata into a uniform interface. |
| **I/O Strategy** | Stream to `$SLURM_SCRATCH` | Keeps point-cloud I/O on node NVMe SSD; prevents Lustre/NFS network contention. |
| **File Naming** | `--spatial-name` | Produces `..._E0764000_N4326000.laz`, enabling self-documenting filenames. |
| **Metadata** | `--sidecar` or `tasks.csv` | Embeds exact core bounding boxes, projection, and point count estimates. |
| **lidR Buffer** | `CHUNK_BUFFER="0"` | `als-finder` handles buffering; avoids double-buffering. |
| **Resource Profile** | 1 Tile per Task / 2 CPUs | Prevents `future::multisession` memory spikes; guarantees bounded ~3.5 GB RAM per task. |
| **Buffer Stripping** | `remove_las_buffer(las)` | Unmodified R script purges buffer collar points from normalized LAZ outputs. |
