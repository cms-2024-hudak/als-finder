# Tutorial: Scaling LiDAR Metric Extraction with als-finder and Slurm

This tutorial provides a complete, production-grade guide for integrating **`als-finder`** with **Lilian Vallet's LiDAR metric extraction workflow** ([`scratch/sample_workflow/extract_lidar_metrics.R`](file:///mnt/c/Users/gears/git/als-finder/scratch/sample_workflow/extract_lidar_metrics.R)) on High-Performance Computing (HPC) clusters managed by Slurm.

---

## 1. Prerequisites & Environment Setup

`als-finder` requires C++ geospatial libraries (GDAL, GEOS, PROJ, PDAL). Because configuring these from scratch can be challenging for users new to Python or Conda, we provide two recommended setup methods:
- **Method A: From GitHub via Conda** (Recommended for local desktop/laptop testing on Windows or Linux/WSL).
- **Method B: Containerized via Docker or Singularity / Apptainer** (Recommended for zero-install containers or unprivileged execution on HPC Slurm clusters).

---

### Method A: Conda Installation from GitHub (Windows & Linux/WSL)

#### Step 0: Check if Conda is Already Installed
First, check if Conda is already on your system by typing:
```bash
conda --version
```
- **If this prints a version number** (e.g. `conda 24.x.x`): Conda is already installed! **Skip directly to Step 1.**
- **If it says "command not found":** Follow the installation below for your operating system:

**For Linux / WSL2 Users:**
Copy and paste these terminal commands (only the lines of code, without the ```` ```bash ```` markers):
```bash
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash Miniforge3-$(uname)-$(uname -m).sh -b -p "$HOME/miniforge3"
"$HOME/miniforge3/bin/conda" init bash
source ~/.bashrc
```

**For Windows Users:**
1. Download the [Miniforge3 Windows Installer (.exe)](https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe).
2. Run the installer (choose "Just Me", accept defaults).
3. From your Windows Start Menu, open **Miniforge Prompt** (or use PowerShell).

---

#### Step 1: Create a Dedicated Test Environment
We will create an isolated environment named `als-tutorial` to ensure existing packages or system libraries do not conflict.

Run this command in your terminal (Linux/WSL) or Miniforge Prompt (Windows):
```bash
conda create -n als-tutorial -c conda-forge -y \
  python=3.11 pip \
  gdal proj openssl libcurl \
  geopandas pdal python-pdal laspy pyogrio \
  shapely pyproj pystac stac-validator \
  requests click python-dotenv tqdm psutil git
```

Once creation finishes, activate the environment:
```bash
conda activate als-tutorial
```

#### Step 2: Install als-finder from GitHub
With your `als-tutorial` environment active, install `als-finder` using the active environment's Python (`python -m pip`):

```bash
python -m pip install git+https://github.com/cms-2024-hudak/als-finder.git
```
*(Alternatively, you can install the official release via `python -m pip install als-finder==1.2.0`).*

#### Step 3: Verify the Installation
```bash
als-finder --version
als-finder --help
```
You should see:
```text
als-finder, version 1.2.0
Usage: als-finder [OPTIONS] COMMAND [ARGS]...
```

---

### Method B: Containerized Execution (Docker & Singularity / Apptainer)

Containers bundle the entire operating system, GDAL, PDAL, Python, and `als-finder` into a single immutable image with zero manual environment configuration.

#### Option B.1: Docker (Local Workstations & Development)
Ensure Docker Desktop is running on your machine:

**On Linux / WSL2 / macOS:**
```bash
# 1. Pull the pre-built image from GitHub Packages
docker pull ghcr.io/cms-2024-hudak/als-finder:latest

# 2. Verify the container
docker run --rm ghcr.io/cms-2024-hudak/als-finder:latest --version

# 3. Mount current directory to /workspace and run commands
docker run --rm -v "$(pwd)":/workspace ghcr.io/cms-2024-hudak/als-finder:latest search --help
```

**On Windows (PowerShell):**
```powershell
# 1. Pull the pre-built image
docker pull ghcr.io/cms-2024-hudak/als-finder:latest

# 2. Verify the container
docker run --rm ghcr.io/cms-2024-hudak/als-finder:latest --version

# 3. Mount current directory to /workspace and run commands
docker run --rm -v "${PWD}:/workspace" ghcr.io/cms-2024-hudak/als-finder:latest search --help
```

#### Option B.2: Singularity / Apptainer (HPC Clusters like Expanse, Perlmutter, Bridges)
On shared HPC supercomputers, users do not have root/fakeroot privileges and cannot build containers from scratch or definition files. However, HPC environments allow unprivileged users to pull pre-built Docker images directly from a registry into an immutable Singularity Image File (`.sif`) using **`singularity pull`** (or **`apptainer pull`**):

```bash
# 1. Pull and convert the Docker image into a .sif file (no root or fakeroot needed)
singularity pull als-finder.sif docker://ghcr.io/cms-2024-hudak/als-finder:latest

# If your cluster uses Apptainer (the modern Singularity fork):
# apptainer pull als-finder.sif docker://ghcr.io/cms-2024-hudak/als-finder:latest

# 2. Verify execution
singularity exec als-finder.sif als-finder --version

# 3. Run inside Slurm batch jobs by mounting shared cluster storage and local scratch:
singularity exec \
  --bind /project:/project,/scratch:/scratch \
  als-finder.sif \
  als-finder fetch tile 15 --workspace /project/my_lab/lidar_project
```

---

## 2. Architectural Overview & The Master Planning Step

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
  │   3. Build regularized grid (1200m tiles + 30m buffer) in grid.gpkg    │
  │   4. Export rich task manifest (tasks.csv) to shared cluster storage   │
  └───────────────────────────────────┬────────────────────────────────────┘
                                      │
           Shared Cluster Storage     │ (/project/my_lab/lidar_project/)
                                      ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ PHASE 2: SLURM JOB ARRAY EXECUTION (Run N times across Cluster)        │
  │   #SBATCH --array=1-N%50                                               │
  │                                                                        │
  │   Compute Node 1                       Compute Node 2                  │
  │   (Task 1: Tile 0)                     (Task 2: Tile 1)                │
  │   ┌────────────────────────────────┐   ┌─────────────────────────────┐ │
  │   │ 1. Read row 1 from tasks.csv   │   │ 1. Read row 2 from tasks.csv│ │
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

## 3. Phase 1: Shared Pre-Flight Master Planning

Execute this phase **once** on the login node or a lightweight 1-core interactive job. All outputs are saved to the cluster's shared filesystem (e.g., Lustre, GPFS, or NFS at `/project/my_lab/lidar_project`).

### Step 1.1: Search Remote Datasets Across Providers
Search for point clouds intersecting your Region of Interest (ROI):

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

### Step 1.2: Selecting the Optimal Tile & Buffer Size for 30 m Rasters

When the primary objective is generating **30 m ecological or topographic rasters** (e.g., Landsat/SRTM scale), selecting the tile size and buffer requires careful consideration:

#### Why a 10 m Buffer is Inadequate for 30 m Rasters:
- A $10\,\text{m}$ buffer is only **$\frac{1}{3}$ of a single $30\,\text{m}$ pixel**.
- When computing $30\,\text{m}$ metrics or performing Cloth Simulation Filter (CSF) ground classification and Delaunay TIN terrain interpolation, border pixels in the core tile will lack sufficient surrounding points, causing edge nulls, distorted slope interpolation, and boundary seams.
- **Rule of Thumb:** The spatial buffer must be at least **1 full pixel width ($30\,\text{m}$)**, and ideally **1 to 2 pixels ($30\,\text{m}$ to $60\,\text{m}$)**.

#### The Metric Divisibility Advantage: 1200 m vs. 1000 m:
- $1000\,\text{m} / 30\,\text{m} = \mathbf{33.333\dots\text{ pixels}}$ (fractional!). A $1000\,\text{m}$ tile inevitably slices through boundary pixels, causing fractional cell clipping at tile seams.
- **$1200\,\text{m}$** divides **evenly** into integer pixels across all common remote sensing resolutions:
  - **$30\,\text{m}$ rasters:** Exactly **$40 \times 40$ pixels** ($1200 / 30 = 40$).
  - **$10\,\text{m}$ rasters:** Exactly **$120 \times 120$ pixels** ($1200 / 10 = 120$).
  - **$5\,\text{m}$ rasters:** Exactly **$240 \times 240$ pixels** ($1200 / 5 = 240$).
  - **$1\,\text{m}$ rasters:** Exactly **$1200 \times 1200$ pixels** ($1200 / 1 = 1200$).

#### Recommended Grid Configuration:
- **Tile Size:** `1200` meters (40 core pixels at $30\,\text{m}$)
- **Buffer Size:** `30` meters (1 pixel buffer collar $\rightarrow$ total bounds $1260\,\text{m} = 42$ pixels) or `60` meters (2 pixel buffer collar $\rightarrow$ total bounds $1320\,\text{m} = 44$ pixels).

```bash
# Generate the 1200m / 30m regularized grid (default in als-finder v1.3+)
als-finder plan \
  --workspace "$SHARED_DIR" \
  --tile-size 1200 \
  --buffer-size 30
```

### Step 1.3: Exporting the All-Inclusive Task Manifest (`tasks.csv`)

Rather than having Slurm workers open and parse individual JSON sidecar files during runtime, `als-finder` can export a single, self-contained **rich CSV manifest** containing all spatial bounds, CRS codes, point estimates, and basenames:

```bash
als-finder plan \
  --workspace "$SHARED_DIR" \
  --tasks-csv > "$SHARED_DIR/tasks.csv"
```

Each row of `tasks.csv` provides a complete task definition:
```csv
task_id,tile_id,basename,dataset_id,provider,grid_crs,tile_size,buffer_size,core_minx,core_miny,core_maxx,core_maxy,buffered_minx,buffered_miny,buffered_maxx,buffered_maxy,crop_gdal_te,point_density,est_points,recommended_mem_gb,hive_path
1,0,CA_SierraNevada_8_2022_tile_E0763200_N4326000,CA_SierraNevada_8_2022,USGS_EPT,EPSG:32610,1200,30,763200.0,4324800.0,764400.0,4326000.0,763170.0,4324770.0,764430.0,4326030.0,"763200.0 4324800.0 764400.0 4326000.0",10.0,15876000,6.0,provider=USGS_EPT/...
2,1,CA_SierraNevada_8_2022_tile_E0763200_N4327200,CA_SierraNevada_8_2022,USGS_EPT,EPSG:32610,1200,30,763200.0,4326000.0,764400.0,4327200.0,763170.0,4325970.0,764430.0,4327230.0,"763200.0 4326000.0 764400.0 4327200.0",10.0,15876000,6.0,provider=USGS_EPT/...
```

#### Why the Enriched CSV Pattern Is Superior for Slurm & R:
1. **Zero JSON Dependencies in Workers:** Workers do not need `jsonlite` in R or `jq` in bash.
2. **Instant 1-Row Read:** In R, the worker loads its assignment in a single operation: `task <- read.csv("tasks.csv")[task_id, ]`.
3. **Native Cropping & Vectorization:** The worker accesses `task$core_minx` through `task$core_maxy` directly for cropping rasters without guessing or calculating extents.
4. **Direct Prepending to Metrics Outputs:** When Lilian's script finishes extracting forest statistics, it can immediately prepend the task metadata to its results:
   ```r
   out_row <- cbind(task, data.frame(
     mean_canopy_cover = mean(terra::values(r_cover), na.rm=TRUE),
     p95_height = quantile(terra::values(r_height), 0.95, na.rm=TRUE)
   ))
   write.csv(out_row, file=paste0(task$basename, "_summary.csv"), row.names=FALSE)
   ```
5. **Portability Sidecar Retained:** `--sidecar` is still available during streaming if individual `.laz` files need companion `tile.json` metadata for standalone use outside the cluster.

---

## 4. Phase 2: Slurm Job Array Architecture

Here is the complete Slurm batch submission script (`sbatch_lidar_metrics.slurm`):

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

# 2. Extract Assigned Task Row from Enriched CSV
TASK_FILE="$SHARED_DIR/tasks.csv"
LINE_NUM=$((SLURM_ARRAY_TASK_ID + 1))
TASK_LINE=$(sed -n "${LINE_NUM}p" "$TASK_FILE")

TILE_ID=$(echo "$TASK_LINE" | cut -d',' -f2)
BASENAME=$(echo "$TASK_LINE" | cut -d',' -f3)

echo "=== Task $SLURM_ARRAY_TASK_ID: Processing Tile $TILE_ID ($BASENAME) on $(hostname) ==="

# 3. Setup Node-Local Scratch Directory
LOCAL_DIR="${SLURM_SCRATCH:-/tmp}/${USER}_job_${SLURM_JOB_ID}_task_${SLURM_ARRAY_TASK_ID}"
LOCAL_IN="$LOCAL_DIR/data"
LOCAL_OUT="$LOCAL_DIR/output"
mkdir -p "$LOCAL_IN" "$LOCAL_OUT"

cleanup() {
    rm -rf "$LOCAL_DIR"
}
trap cleanup EXIT

# 4. Stream Tile On-Demand into Node-Local Scratch (1200m core + 30m buffer)
als-finder fetch tile "$TILE_ID" \
  --workspace "$SHARED_DIR" \
  --output "$LOCAL_IN" \
  --tile-size 1200 \
  --buffer-size 30 \
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

echo "=== Task $SLURM_ARRAY_TASK_ID Finished Successfully ==="
```

---

## 5. Phase 3: Raster Alignment & Mosaicking

### 4.1 Sub-Pixel Alignment Verification
Because `als-finder` enforces coordinate origins snapped to exact integer multiples of the resolution:
$$\text{Origin } X \pmod{\text{pixel\_res}} = 0, \quad \text{Origin } Y \pmod{\text{pixel\_res}} = 0$$
Both $1200\,\text{m}$ tile boundaries and $30\,\text{m}$ (or $10\,\text{m}$) raster pixel centers align across all neighboring tiles with zero sub-pixel shear or offset.

### 4.2 Buffer Overlap & Zero-Overlap Core Cropping
- **Raw Raster with Buffer:** With a $30\,\text{m}$ buffer collar, the raster is $42 \times 42$ cells ($1260\,\text{m} \times 1260\,\text{m}$), leaving a 1-pixel overlap with neighbors.
- **Exact Core Crop (40 x 40 cells):** Using the core bounding coordinates directly from `tasks.csv`, each tile can be cropped to exactly $40 \times 40$ pixels ($1200\,\text{m} \times 1200\,\text{m}$):
  ```r
  # In R: Read core bounds directly from the task row
  task <- read.csv("tasks.csv")[task_id, ]
  core_box <- terra::ext(task$core_minx, task$core_maxx, task$core_miny, task$core_maxy)
  r_core <- terra::crop(r, core_box)
  terra::writeRaster(r_core, out_tif, overwrite=TRUE)
  ```

### 4.3 Regional Mosaicking Command
Once all Slurm array tasks finish, stitch the output GeoTIFFs into a seamless regional raster:
```bash
cd /project/my_lab/lidar_project/outputs/metrics

# Step 1: Build Virtual Raster (instantaneous, zero disk overhead)
gdalbuildvrt regional_canopy_cover_30m.vrt *canopy_cover*.tif

# Step 2: Export Cloud-Optimized GeoTIFF (COG)
gdal_translate -of COG -co COMPRESS=DEFLATE regional_canopy_cover_30m.vrt regional_canopy_cover_30m_cog.tif
```

---

## 6. Summary of Best Practices

| Workflow Component | Recommended Setting | Engineering Rationale |
| :--- | :--- | :--- |
| **Grid Generation** | Pre-flight `als-finder plan` | Single shared master index; eliminates redundant remote API queries and race conditions. |
| **Tile Sizing** | `tile-size 1200` | Evenly divides into $30\,\text{m}$ ($40\text{ px}$), $10\,\text{m}$ ($120\text{ px}$), and $1\,\text{m}$ ($1200\text{ px}$) without fractional cuts. |
| **Buffer Sizing** | `buffer-size 30` (or `60`) | Guarantees $\ge 1$ full pixel margin for $30\,\text{m}$ rasters; prevents edge nulls and TIN artifacts. |
| **Task Manifest** | `als-finder plan --tasks-csv` | Produces an all-inclusive tabular manifest; eliminates JSON parsing overhead in workers. |
| **I/O Strategy** | Stream to `$SLURM_SCRATCH` | Keeps point-cloud I/O on node NVMe SSD; prevents Lustre/NFS network contention. |
| **File Naming** | `--spatial-name` | Produces `..._E0764400_N4326000.laz`, enabling self-documenting filenames. |
| **lidR Buffer** | `CHUNK_BUFFER="0"` | `als-finder` handles buffering; avoids double-buffering. |
| **Resource Profile** | 1 Tile per Task / 2 CPUs | Prevents `future::multisession` memory spikes; guarantees bounded ~3.5 GB RAM per task. |
| **Buffer Stripping** | `remove_las_buffer(las)` | Unmodified R script purges buffer collar points from normalized LAZ outputs. |
