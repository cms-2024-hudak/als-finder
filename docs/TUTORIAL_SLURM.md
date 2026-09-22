# Tutorial: Scaling LiDAR Metric Extraction with als-finder and Slurm

This tutorial provides a complete, production-grade guide for integrating **`als-finder`** with **standard LiDAR metric extraction workflows in R/lidR** (such as [`scratch/sample_workflow/extract_lidar_metrics.R`](file:///mnt/c/Users/gears/git/als-finder/scratch/sample_workflow/extract_lidar_metrics.R)) on High-Performance Computing (HPC) clusters managed by Slurm.

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

Run this command in your terminal (Linux/WSL) or Miniforge Prompt (Windows) — it works identically on all systems:
```bash
conda create -n als-tutorial -c conda-forge -y python=3.11 pip gdal proj boto3 geopandas pdal python-pdal laspy pyogrio shapely pyproj pystac stac-validator requests click python-dotenv tqdm psutil git
```

Once creation finishes, activate the environment:
```bash
conda activate als-tutorial
```

#### Step 2: Install als-finder from GitHub
With your `als-tutorial` environment active, install the latest `als-finder` from GitHub:

```bash
python -m pip install --no-cache-dir git+https://github.com/cms-2024-hudak/als-finder.git
```

> [!TIP]
> **How to Update to the Latest GitHub Version**
> If you already have `als-finder` installed and want to pull newly pushed bugfixes or commits from GitHub, running a standard `pip install` will say *"Requirement already satisfied"* and skip updating because the package version is already registered.
>
> Run this command to force `pip` to overwrite with the newest GitHub commits without touching your Conda-managed geospatial dependencies (GDAL, PDAL, GeoPandas):
> ```bash
> python -m pip install --force-reinstall --no-deps git+https://github.com/cms-2024-hudak/als-finder.git
> ```
> *(If you ever need a 100% fresh start: `conda deactivate && conda env remove -n als-tutorial -y`)*

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

**On Linux / WSL2 / macOS (Bash):**
```bash
# 1. Pull the pre-built image from GitHub Packages
docker pull ghcr.io/cms-2024-hudak/als-finder:latest

# 2. Verify the container
docker run --rm ghcr.io/cms-2024-hudak/als-finder:latest --version

# 3. Mount current directory to /workspace and run commands
docker run --rm -v "$(pwd)":/workspace ghcr.io/cms-2024-hudak/als-finder:latest search --help
```

**On Windows (Miniforge Prompt / Command Prompt):**
```cmd
:: 1. Pull the pre-built image from GitHub Packages
docker pull ghcr.io/cms-2024-hudak/als-finder:latest

:: 2. Verify the container
docker run --rm ghcr.io/cms-2024-hudak/als-finder:latest --version

:: 3. Mount current directory to /workspace and run commands
docker run --rm -v "%cd%:/workspace" ghcr.io/cms-2024-hudak/als-finder:latest search --help
```
*(If using PowerShell on Windows instead: use `-v "${PWD}:/workspace"` for the mount).*

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

Pre-flight planning organizes the catalog, regularizes the spatial tiling grid, and generates the worker task manifest.

To make all tutorial commands **100% identical and portable across Windows, Linux, WSL, and macOS**, we will work in a local project folder and use relative paths (`.`):

### Step 1.0: Setup Project Directory & Extract Sample ROI
Run these commands in your terminal (Linux/WSL) or Miniforge Prompt (Windows):

```bash
mkdir lidar_project
cd lidar_project
als-finder get-example-roi
```
*(This extracts the bundled Lake Tahoe Region of Interest: `ltbmu_boundary.gpkg`).*

> [!TIP]
> **HPC / Cluster Deployment Note:**
> On a shared supercomputer (e.g. Slurm on Lustre/GPFS), perform these same steps once on the login node inside your shared allocation folder (e.g., `cd /project/my_lab/lidar_project`). All worker nodes will then share the same catalog and task manifest.

### Step 1.1: Provider Authentication & Free API Keys (Optional)

`als-finder` searches open federal and scientific repositories. Major federal archives (USGS 3DEP and NOAA) require no authentication, while academic and community archives offer free API keys:

| Provider | Access Level | How to Obtain & Configure |
| :--- | :--- | :--- |
| **USGS 3DEP** | **Open / Anonymous** | No key or account required. Works out of the box. |
| **NOAA Digital Coast** | **Open / Anonymous** | No key or account required. Works out of the box. |
| **OpenTopography** | **Free Academic Key** | 1. Create a free account at [portal.opentopography.org/myopentopo](https://portal.opentopography.org/myopentopo).<br>2. Navigate to **My Account** $\rightarrow$ **OpenTopography API Key** $\rightarrow$ **Request an API Key**.<br>3. Pass it once via CLI: `als-finder search --roi ltbmu_boundary.gpkg --ot-key <YOUR_KEY> --workspace .`<br>*(als-finder will automatically save it to `.env` in your workspace so you never need to type it again).* |
| **NASA Earthdata** | **Free NASA Account** | 1. Register a free account at [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov).<br>2. Generate a Bearer Token under your profile.<br>3. Pass once: `als-finder search --roi ltbmu_boundary.gpkg --earthdata-token <YOUR_TOKEN> --workspace .` |
| **NEON** | **Optional Token** | Optional free token at [data.neonscience.org](https://data.neonscience.org) (increases rate limits from 100 to 1,000 req/min). Pass via `--neon-key <KEY>`. |

> [!NOTE]
> **Graceful Degradation:**
> If you do not configure an OpenTopography or NASA key, `als-finder` automatically prints an informative notice, gracefully skips those providers, and successfully catalogs all datasets from open providers (such as USGS and NOAA).

### Step 1.2: Search Remote Datasets Across Providers
Search for point clouds intersecting your Region of Interest into the current workspace (`.`):

```bash
# Option A: Target open federal archives directly (no API keys required)
als-finder search --roi ltbmu_boundary.gpkg --provider usgs,noaa --workspace .

# Option B: Search across all archives (will include OpenTopography if --ot-key was configured)
als-finder search --roi ltbmu_boundary.gpkg --date 2018:2024 --workspace .
```

### Step 1.3: Selecting the Optimal Tile & Buffer Size for 30 m Rasters

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
# Generate the 1200m / 30m regularized grid
als-finder plan --workspace . --tile-size 1200 --buffer-size 30
```

### Step 1.4: Exporting the All-Inclusive Task Manifest (`tasks.csv`)

Rather than having Slurm workers open and parse individual JSON sidecar files during runtime, `als-finder` can export a single, self-contained **rich CSV manifest** containing all spatial bounds, CRS codes, point estimates, and basenames:

```bash
als-finder plan --workspace . --tasks-csv > tasks.csv
head -n 5 tasks.csv
```

Each row of `tasks.csv` provides a complete task definition:
```csv
task_id,tile_id,basename,dataset_id,provider,grid_crs,tile_size,buffer_size,core_minx,core_miny,core_maxx,core_maxy,buffered_minx,buffered_miny,buffered_maxx,buffered_maxy,crop_gdal_te,point_density,est_points,recommended_mem_gb,hive_path
1,0,CA_SierraNevada_5_2022_tile_E0736800_N4329600,CA_SierraNevada_5_2022,USGS_EPT,EPSG:32610,1200,30,736800.0,4328400.0,738000.0,4329600.0,736770.0,4328370.0,738030.0,4329630.0,"736800.0 4328400.0 738000.0 4329600.0",29.18,46326168,17.4,provider=USGS_EPT/...
2,1,CA_SierraNevada_5_2022_tile_E0736800_N4330800,CA_SierraNevada_5_2022,USGS_EPT,EPSG:32610,1200,30,736800.0,4329600.0,738000.0,4330800.0,736770.0,4329570.0,738030.0,4330830.0,"736800.0 4329600.0 738000.0 4330800.0",29.18,46326168,17.4,provider=USGS_EPT/...
```

#### Why the Enriched CSV Pattern Is Superior for Slurm & R:
1. **Zero JSON Dependencies in Workers:** Workers do not need `jsonlite` in R or `jq` in bash.
2. **Instant 1-Row Read:** In R, the worker loads its assignment in a single operation: `task <- read.csv("tasks.csv")[task_id, ]`.
3. **Native Cropping & Vectorization:** The worker accesses `task$core_minx` through `task$core_maxy` directly for cropping rasters without guessing or calculating extents.
4. **Direct Prepending to Metrics Outputs:** When your R metric extraction script finishes computing forest statistics, it can immediately prepend the task metadata to its results:
   ```r
   out_row <- cbind(task, data.frame(
     mean_canopy_cover = mean(terra::values(r_cover), na.rm=TRUE),
     p95_height = quantile(terra::values(r_height), 0.95, na.rm=TRUE)
   ))
   write.csv(out_row, file=paste0(task$basename, "_summary.csv"), row.names=FALSE)
   ```
5. **Portability Sidecar Retained:** `--sidecar` is still available during streaming if individual `.laz` files need companion `tile.json` metadata for standalone use outside the cluster.

---

### Step 1.5: Test Single-Tile Streaming Locally (Optional Verification)
Before submitting a large Slurm array, you can test data streaming on a single tile (e.g. Tile 0) on your local machine:

```bash
als-finder fetch tile 0 --workspace . --output ./scratch_tiles --tile-size 1200 --buffer-size 30 --spatial-name
```
*(This streams Tile 0 into `scratch_tiles/` with exact 1200m core bounds and 30m spatial buffer in ~3 seconds).*

---

### Step 1.6: Controlling Worker Memory Usage & High-Density Tiles (`--max-points`)

Now that you understand the standard uniform grid workflow, what happens if your study area contains **high-density LiDAR**?

Notice the `est_points` and `recommended_mem_gb` columns in your `tasks.csv`:
- In our Lake Tahoe search, the 2022 Sierra Nevada USGS dataset has a point density of **$29.18\,\text{pts/m}^2$**.
- A $1200\,\text{m}$ core tile with a $30\,\text{m}$ buffer ($1260\,\text{m} \times 1260\,\text{m}$) contains **$\sim 46{,}326{,}000\text{ points}$**.
- Loading 46 million points into R via `lidR::readLAS` requires approximately **$14\text{--}18\,\text{GB}$ of RAM**. On standard compute nodes allocated $8\,\text{GB}$ or $12\,\text{GB}$ of RAM per worker, this will trigger an **Out-Of-Memory (OOM) crash** (`slurmstepd: error: Detected 1 oom-kill event`).

---

#### Understanding the Suggested Max Points Formula

How does `als-finder` calculate `recommended_mem_gb` and determine an appropriate point budget?

In R, the `lidR` package stores point cloud structures as S4 `LAS` objects containing coordinates, attributes, classifications, and spatial index trees:
1. **Base Memory per Point ($\approx 250\text{ bytes}$):**
   Double-precision $(X, Y, Z)$ coordinates (24 bytes) + intensity, return counts, classification flags, scan angles, user data (16 bytes) + internal R data.table vector overhead and kd-tree spatial indexing ($\sim 200\text{ bytes}$).
2. **Peak Working Memory Multiplier ($1.5\times$):**
   When `lidR` interpolates a Canopy Height Model (CHM), builds Delaunay triangulations, or calculates grid metrics, R allocates intermediate raster matrices and temporary arrays before garbage collection.
3. **The Memory Equation:**
   $$\text{Peak RAM (GB)} \approx \frac{\text{Point Count} \times 250\,\text{bytes} \times 1.5}{10^9} = \frac{\text{Point Count} \times 375}{10^9}$$

Based on your cluster's Slurm node partitions, use this sizing guide to set `--max-points`:

| Slurm Worker Allocation (`--mem`) | Safe Point Budget (`--max-points`) | Est. Peak RAM in R | Headroom for OS & Caching |
| :--- | :--- | :--- | :--- |
| **8 GB** | `10000000` (10M pts) | $\approx 3.75\,\text{GB}$ | $4.25\,\text{GB}$ (Recommended for standard 8 GB nodes) |
| **12 GB** | `15000000` (15M pts) | $\approx 5.6\,\text{GB}$ | $6.4\,\text{GB}$ (Safe) |
| **16 GB** | `25000000` (25M pts) | $\approx 9.4\,\text{GB}$ | $6.6\,\text{GB}$ (Safe) |
| **32 GB** | `50000000` (50M pts) | $\approx 18.7\,\text{GB}$ | $13.3\,\text{GB}$ (Safe) |

---

#### Option A: Dynamic Multi-Level Quadrant Subdivision (`--max-points`)

Rather than re-engineering your entire grid by hand, you can pass `--max-points` directly to `als-finder plan`. `als-finder` audits every tile against the budget and dynamically subdivides tiles that exceed the limit.

Because $1200\,\text{m}$ divides cleanly into halves ($600\,\text{m}$) and quarters ($300\,\text{m}$), all sub-tiles remain **exact integer multiples of $30\,\text{m}$ pixels** ($40 \times 40 \rightarrow 20 \times 20 \rightarrow 10 \times 10$ pixels), ensuring zero edge misalignment or resampling distortion.

##### 1. One-Level Subdivision Example (`--max-points 15000000`):
With a 15M budget, a 46M-point tile ($1200\,\text{m}$) is split into 4 quadrants ($600\,\text{m}$ core, $660\,\text{m}$ buffered $\approx 12.7\text{M points} \le 15\text{M}$):

```bash
als-finder plan --workspace . --tile-size 1200 --buffer-size 30 --max-points 15000000
```
*Output:*
```text
==================================================
 ALS-FINDER SPATIAL PLANNING & GRID METRICS
==================================================
  Master Tiles:      1,039
  Total Leaf Tasks:  4,156
  Tile ID Range:     0 to 1038
  Tile Size:         1200m (core)
  Buffer Size:       30m (overlap)
  Grid CRS:          EPSG:32610
--------------------------------------------------
 MEMORY RISK AUDIT (PRE-FLIGHT):
  Max Points Budget: 15,000,000
  Est Points/Tile:   46,326,168
  Subdivision:       1039 tiles exceed budget (split into 4 quadrants each)
  Slurm Array Size:  --array=1-4156
==================================================
```
Generating leaf tasks produces Level-1 tokens (`0_NW`, `0_NE`, `0_SW`, `0_SE`):
```bash
als-finder plan --workspace . --tile-size 1200 --buffer-size 30 --max-points 15000000 --tasks | head -n 4
```
```text
0_NW
0_NE
0_SW
0_SE
```

##### 2. Two-Level Subdivision Example (`--max-points 10000000`):
If your cluster nodes only have $8\,\text{GB}$ of RAM, set `--max-points 10000000`. Because $12.7\text{M points}$ (Level 1) still exceeds 10M, `als-finder` automatically recurses into **Level 2** ($300\,\text{m}$ core, $360\,\text{m}$ buffered $\approx 3.78\text{M points}$), creating 16 sub-quadrants:

```bash
als-finder plan --workspace . --tile-size 1200 --buffer-size 30 --max-points 10000000
```
*Output:*
```text
==================================================
 ALS-FINDER SPATIAL PLANNING & GRID METRICS
==================================================
  Master Tiles:      1,039
  Total Leaf Tasks:  16,624
  Tile ID Range:     0 to 1038
--------------------------------------------------
 MEMORY RISK AUDIT (PRE-FLIGHT):
  Max Points Budget: 10,000,000
  Est Points/Tile:   46,326,168
  Subdivision:       1039 tiles exceed budget (0 split into 4 quadrants, 1039 split into 16 sub-quadrants)
  Slurm Array Size:  --array=1-16624
==================================================
```
Inspecting the leaf tasks reveals the hierarchical two-level tokens:
```bash
als-finder plan --workspace . --tile-size 1200 --buffer-size 30 --max-points 10000000 --tasks | head -n 8
```
```text
0_NW_NW
0_NW_NE
0_NW_SW
0_NW_SE
0_NE_NW
0_NE_NE
0_NE_SW
0_NE_SE
```

##### 3. Heterogeneous Regional Surveys (Mixed Densities):
If an ROI covers mixed survey vintages (e.g. legacy $5\,\text{pts/m}^2$, standard $12\,\text{pts/m}^2$, and recent $30\,\text{pts/m}^2$):
- **Sparse tiles** ($\le 6.3\,\text{pts/m}^2$) stay whole as Level 0 ($1200\,\text{m}$).
- **Moderate tiles** ($6.3\text{--}22.9\,\text{pts/m}^2$) split once into 4 quadrants ($600\,\text{m}$, e.g. `14_NW`).
- **Dense tiles** ($> 22.9\,\text{pts/m}^2$) split twice into 16 sub-quadrants ($300\,\text{m}$, e.g. `0_NW_SE`).

Every worker streams its assigned sub-tile on-demand using its exact task ID (e.g. `als-finder fetch tile 0_NW_SE ...`), automatically inheriting the correct scaled core bounding box while preserving the full $30\,\text{m}$ buffer.

---

#### Option B: Sizing the Nominal Grid to $600\,\text{m}$
If an entire study area consists of uniform high-density lidar ($\ge 25\,\text{pts/m}^2$), you can avoid subdivision entirely by generating the nominal grid at $600\,\text{m}$ ($20 \times 20$ pixels at $30\,\text{m}$):
```bash
als-finder plan --workspace . --tile-size 600 --buffer-size 30 --overwrite
als-finder plan --workspace . --tasks-csv > tasks.csv
```
Every tile is then naturally capped at $\sim 12.7\,\text{M points}$ ($\sim 4.8\,\text{GB}$ in R) and executes smoothly on standard 8 GB nodes.

---

## Phase 2: Executing the Processing Loop (Slurm Array & R)

At scale, processing hundreds or thousands of spatial tiles is simply **one big loop**. Whether you run that loop across hundreds of compute nodes on a Slurm cluster or across multiple CPU cores on a local workstation, the control flow is identical.

`als-finder plan --tasks-csv > tasks.csv` provides the **universal iterator**. Every row is an independent, self-contained unit of work containing all coordinate bounds, CRS definitions, point density estimates, and output basenames:

```
                  ┌─────────────────────────────────┐
                  │            tasks.csv            │
                  │  (Universal Task Table: 1..N)   │
                  └─────────────────────────────────┘
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         ▼                                                   ▼
┌───────────────────────────────────┐       ┌───────────────────────────────────┐
│     APPROACH A: SLURM ARRAY       │       │        APPROACH B: R LOOP         │
│      (Distributed Cluster)        │       │   (Local Multicore Workstation)   │
├───────────────────────────────────┤       ├───────────────────────────────────┤
│ • Iterator: $SLURM_ARRAY_TASK_ID  │       │ • Iterator: 1:nrow(tasks)         │
│ • Parallelism: Cluster nodes      │       │ • Parallelism: mclapply / future  │
│ • Extract row: sed -n "${ID}p"    │       │ • Extract row: task <- tasks[i, ] │
│ • Stream: als-finder fetch tile   │       │ • Stream: system2("als-finder")   │
│ • Process: Rscript worker.R       │       │ • Process: lidR / terra in R      │
│ • Crop core: task$core_minx..maxy │       │ • Crop core: task$core_minx..maxy │
└───────────────────────────────────┘       └───────────────────────────────────┘
```

---

### Step 2.0: Environment Setup for R (`r-base`, `r-lidr`, `r-terra`)

Before running your R metric extraction scripts or looping over tiles, install R and its core geospatial stack directly into your active `als-tutorial` Conda environment.

This guarantees that R, `lidR`, `terra`, and their underlying C++ libraries (GDAL, PROJ, GEOS, UDUNITS) share the exact same environment as `als-finder`, completely eliminating missing shared object errors (`libudunits2.so`) or C++ compilation issues:

```bash
# Ensure your environment is active
conda activate als-tutorial

# Install R, lidR, and terra with all pre-compiled C++ geospatial bindings
conda install -c conda-forge -y r-base r-lidr r-terra
```

Once installed, verify that `lidR` and `terra` load cleanly:
```bash
R -e "library(terra); library(lidR); cat('R geospatial stack verified successfully!\n')"
```

---

### Step 2.1: The Fundamental Loop (First Principles)

Before diving into distributed Slurm arrays or cluster schedulers, let's look at the basic loop. Every tile processing pipeline—regardless of language or environment—performs the same sequence:
1. Read the tile assignment and metadata from `tasks.csv`.
2. Stream the buffered tile lazily on-demand with `als-finder fetch tile`.
3. Compute metrics in R (e.g. canopy height model, cover).
4. Crop the buffer using the exact `core_minx`..`core_maxy` bounding box from `tasks.csv`.
5. Remove the temporary `.laz` file to keep disk footprint near zero.

#### The Loop in R:
```r
library(terra)
library(lidR)

# 1. Load the full task manifest (contains all 1,039 tiles)
tasks <- read.csv("tasks.csv")
cat(sprintf("Loaded master task table with %d total tiles.\n", nrow(tasks)))

# 2. For local testing, subset to just a few tiles (e.g., the first 3 tiles)
# (When ready to run everything, simply use: test_tasks <- tasks)
test_tasks <- head(tasks, 3)
cat(sprintf("Looping through a subset of %d test tiles...\n", nrow(test_tasks)))

dir.create("scratch_tiles", showWarnings = FALSE)
dir.create("outputs", showWarnings = FALSE)

# 3. Iterate through each tile in the subset
for (i in 1:nrow(test_tasks)) {
  task <- test_tasks[i, ]
  cat(sprintf("\n--- [%d/%d] Processing Tile %s (%s) ---\n", i, nrow(test_tasks), task$tile_id, task$basename))
  
  # A. Stream buffered tile on-demand via als-finder
  system2("als-finder", args = c(
    "fetch", "tile", as.character(task$tile_id),
    "--workspace", ".",
    "--output", "scratch_tiles",
    "--spatial-name"
  ))
  
  # B. Load point cloud in lidR
  laz_path <- file.path("scratch_tiles", paste0(task$basename, ".laz"))
  if (!file.exists(laz_path)) {
    warning(paste("Could not find downloaded tile:", laz_path))
    next
  }
  las <- readLAS(laz_path)
  
  # C. Compute canopy metric (e.g., 30m Canopy Height Model)
  chm_buffered <- rasterize_canopy(las, res = 30, p2r())
  
  # D. Crop buffer collar using the exact core bounding box from tasks.csv!
  core_box <- ext(task$core_minx, task$core_maxx, task$core_miny, task$core_maxy)
  chm_core <- crop(chm_buffered, core_box)
  
  # E. Save final deliverable
  out_tif <- file.path("outputs", paste0(task$basename, "_chm_30m.tif"))
  writeRaster(chm_core, out_tif, overwrite = TRUE)
  
  # F. Delete scratch point cloud immediately (keeps local disk usage bounded)
  unlink(laz_path)
}

cat("Processing loop completed successfully!\n")
```

#### The Equivalent Loop in Bash:
```bash
# Read tasks.csv line-by-line (skipping header)
tail -n +2 tasks.csv | while IFS=',' read -r task_id tile_id basename hive_dir hive_path dataset_id provider grid_crs tile_size buffer_size core_minx core_miny core_maxx core_maxy buffered_minx buffered_miny buffered_maxx buffered_maxy crop_gdal_te point_density est_points recommended_mem_gb; do
  echo "=== Processing Tile $tile_id ($basename) ==="
  
  # 1. Stream on-demand into local scratch
  als-finder fetch tile "$tile_id" --workspace . --output ./scratch_tiles --spatial-name
  
  # 2. Run your per-tile metric script
  Rscript process_single_tile.R "$basename" "$core_minx" "$core_miny" "$core_maxx" "$core_maxy"
  
  # 3. Clean up scratch
  rm -f "./scratch_tiles/${basename}.laz"
done
```

---

### Step 2.2: Parallelizing Locally in R (`parallel::mclapply`)

If you are running on a local multi-core workstation (e.g. 8 cores) and want to speed up execution before moving to HPC, simply wrap the loop body in a function and run it with `parallel::mclapply`:

```r
library(parallel)

process_one_tile <- function(task) {
  # (Same steps A through F from the loop above)
  laz_path <- file.path("scratch_tiles", paste0(task$basename, ".laz"))
  
  system2("als-finder", args = c(
    "fetch", "tile", as.character(task$tile_id),
    "--workspace", ".",
    "--output", "scratch_tiles",
    "--spatial-name"
  ))
  
  las <- readLAS(laz_path)
  chm_buffered <- rasterize_canopy(las, res = 30, p2r())
  core_box <- ext(task$core_minx, task$core_maxx, task$core_miny, task$core_maxy)
  chm_core <- crop(chm_buffered, core_box)
  
  writeRaster(chm_core, file.path("outputs", paste0(task$basename, "_chm_30m.tif")), overwrite=TRUE)
  unlink(laz_path)
  return(task$tile_id)
}

tasks <- read.csv("tasks.csv")
# Subset to 4 tiles for local testing
test_tasks <- head(tasks, 4)
num_cores <- min(4, detectCores() - 1)

# Run tiles concurrently across CPU cores
results <- mclapply(1:nrow(test_tasks), function(i) process_one_tile(test_tasks[i, ]), mc.cores = num_cores)
```

---

### Step 2.3: Scaling to Distributed HPC Clusters via Slurm (`sbatch_lidar_metrics.slurm`)

On a supercomputing cluster, instead of running a local R loop, **Slurm acts as the parallel loop engine**. Each array task (`SLURM_ARRAY_TASK_ID`) extracts its assigned row from `tasks.csv` and processes it independently:

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

# 5. Run LiDAR Metric Extraction Script (extract_lidar_metrics.R)
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
