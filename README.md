# als-finder

**A high-performance, cloud-native CLI engine for discovering, streaming, and partitioning raw LiDAR point cloud data across the globe.**

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/cms-2024-hudak/als-finder)

`als-finder` gathers complete acquisition footprints (project boundaries), true WGS84 point densities, and metadata from **USGS 3DEP (EPT/COPC)**, **NOAA Digital Coast**, **NASA G-LiHT**, **NEON**, and **OpenTopography** into clean `.json` manifests, `QGIS`-ready `.gpkg` tables, and on-demand metric spatial tiles with automated Out-Of-Memory (OOM) protection.

---

## 🚀 Quick Install

Because `als-finder` uses advanced C++ geospatial libraries (GDAL, PDAL, GEOS), **Conda** or **Docker** is the recommended installation method:

```bash
# 1. Create environment with all C++ and Python dependencies
conda create -n als-finder -c conda-forge python=3.11 geopandas pdal python-pdal pystac stac-validator psutil shapely pyproj tqdm pyogrio requests click python-dotenv -y

# 2. Activate environment & install als-finder
conda activate als-finder
pip install git+https://github.com/cms-2024-hudak/als-finder.git
```

> [!TIP]
> 📖 **Full Installation Guide:** See [**docs/INSTALLATION.md**](docs/INSTALLATION.md) for Conda-Forge releases, Docker container runs, Singularity/Apptainer HPC setup, and Windows/WSL2 instructions.

---

## 🧭 The Big-Data Architecture: The 4-Stage ALS Lifecycle

Traditional tools force researchers to download massive, multi-gigabyte survey archives before doing any work. `als-finder` is built from the ground up for **cloud-native lazy evaluation and HPC job arrays**:

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  1. DISCOVERY   │ ──> │   2. PLANNING    │ ──> │  3. ACQUISITION  │ ──> │   4. DERIVATIVE  │
│    (search)     │     │     (plan)       │     │     (fetch)      │     │    & MOSAIC      │
└─────────────────┘     └──────────────────┘     └──────────────────┘     └──────────────────┘
 • Federated APIs        • Spatial tiling index   • On-demand streaming    • Crop buffers
 • ROI & temporal        • Memory risk audit      • OOM auto-quadrants     • gdalbuildvrt
 • Provenance catalog    • Slurm task lists       • Sidecar crop bounds    • Zero edge-effects
```

---

## ⚡ Master Tutorial: End-to-End Walkthrough

This single, comprehensive tutorial walks through the complete lifecycle using a single workspace: `scratch/test_workspace`.

### Step 0: Extract the Bundled Example Area of Interest (AOI)
`als-finder` comes with a bundled Lake Tahoe Basin Management Unit (LTBMU) boundary polygon so you can follow along immediately:

```bash
# Extract the example polygon (ltbmu_boundary.gpkg) to your current directory
als-finder get-example-roi
```

---

### Step 1: Federated Discovery (`als-finder search`)
Search across all public LiDAR registries intersecting your AOI. Using `--cloud-native` filters exclusively for streaming-ready formats (USGS EPT / COPC), and `--dedup` eliminates duplicate survey records:

```bash
als-finder search \
  --roi ./ltbmu_boundary.gpkg \
  --workspace scratch/test_workspace \
  --cloud-native \
  --dedup
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1800 |    6347.47 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.2100 |    5819.74 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
 | NASA_GLIHT      | NASA G-LiHT Sierra Nevada / Lake Tahoe | 2022-07-18   |      30.73 |  32.5000 |     126.90 |
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
 | USGS_EPT        | CA_UpperSouthAmerican_Eldorado_2019    | 2019-??-??   |    2075.29 |  43.1600 |    6454.20 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9452               | 2019-10-21   |    2075.29 |  46.7700 |    5954.91 |
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9036               | 2018-07-07   |     253.48 |   0.7800 |   43731.68 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
=================================================================================================================
 TOTAL DATASETS: 11 | ESTIMATED PAYLOAD: 9426.32 GB | QUERY TIME: 4.31s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: scratch/test_workspace/catalog/catalog.gpkg
 JSON METADATA: scratch/test_workspace/catalog/manifest.json
=================================================================================================================
```

> [!NOTE]
> **Zero Heavy Downloads:** Notice that 9.4 TB of data was discovered in 4 seconds. No heavy point cloud files were downloaded to your hard drive.

---

### Step 2: Spatial Planning & Memory Risk Audit (`als-finder plan`)
Before launching jobs, use `als-finder plan` to inspect the study area's metric grid and audit memory safety against a target point budget (e.g. 4,000,000 points $\approx$ 4 GB RAM):

```bash
als-finder plan \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --max-points 4000000
```

**Console Output:**
```text
==================================================
 ALS-FINDER SPATIAL PLANNING & GRID METRICS
==================================================
  Master Tiles:      5,657
  Total Leaf Tasks:  22,628
  Tile ID Range:     0 to 5656
  Tile Size:         500m (core)
  Buffer Size:       50m (overlap)
  Grid CRS:          EPSG:32610
  Target Tile ID:    0
  Basename:          CA_SierraNevada_5_2022_tile_E0737500_N4329500
  Hive Directory:    provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50
  Crop PDAL Bounds:  ([737500.0, 738000.0], [4329000.0, 4329500.0])
  Crop GDAL -te:     737500.0 4329000.0 738000.0 4329500.0
  Grid File:         scratch/test_workspace/catalog/grids/tilesize=500/buffer=50/grid.gpkg
--------------------------------------------------
 MEMORY RISK AUDIT (PRE-FLIGHT):
  Max Points Budget: 4,000,000
  Est Points/Tile:   10,504,800
  Subdivision:       5657 tiles exceed budget (split into 4 quadrants each)
  Slurm Array Size:  --array=1-22628
==================================================
```

#### Extracting Fields Directly for Shell Scripts (`--field` and `--format env`):
```bash
# Query exact scalar fields:
als-finder plan --workspace scratch/test_workspace --tile-size 500 --buffer-size 50 --field total_tiles
# Output: 5657

# Export full environment variables into your active shell:
eval $(als-finder plan --workspace scratch/test_workspace --tile-id 15 --tile-size 500 --buffer-size 50 --format env)
echo "Target Basename: $BASENAME"
echo "Crop Bounds: $CROP_GDAL_TE"
```

---

### Step 3: Generating HPC Slurm Task Lists (`--tasks`)
When scheduling Slurm job arrays, you can output the pre-calculated list of all leaf tile IDs:

```bash
als-finder plan \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --max-points 4000000 \
  --tasks > slurm_tasks.txt

head -n 8 slurm_tasks.txt
```
**Output:**
```text
0_NW
0_NE
0_SW
0_SE
1_NW
1_NE
1_SW
1_SE
```

---

### Step 4: On-Demand Point Cloud Streaming (`als-finder fetch tile`)
Acquire standard tile 15 directly over HTTP using clean positional syntax. Adding `--sidecar` writes a companion `.json` metadata file:

```bash
als-finder fetch tile 15 \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --sidecar \
  --overwrite
```

**Console Output:**
```text
Successfully streamed tile 15 to scratch/test_workspace/data/tiles/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_E0738000_N4331000.laz
Wrote metadata sidecar to scratch/test_workspace/data/tiles/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_E0738000_N4331000.json
```

---

### Step 5: Automatic OOM Protection & Quadrant Streaming
If a tile is hyper-dense and would exceed your RAM limit, passing `--max-points` causes `als-finder` to automatically bisect it into 4 safe quadrants:

```bash
als-finder fetch tile 15 \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --max-points 4000000 \
  --sidecar \
  --overwrite
```

**Console Output:**
```text
Tile 15 exceeded budget. Subdivided into 4 quadrants:
  - Streamed 15_NW to .../CA_SierraNevada_5_2022_tile_E0738000_N4331000_NW.laz
  - Streamed 15_NE to .../CA_SierraNevada_5_2022_tile_E0738000_N4331000_NE.laz
  - Streamed 15_SW to .../CA_SierraNevada_5_2022_tile_E0738000_N4331000_SW.laz
  - Streamed 15_SE to .../CA_SierraNevada_5_2022_tile_E0738000_N4331000_SE.laz
```

> [!IMPORTANT]
> **Co-Located Subtiles & Constant Buffer:**
> 1. All quadrants sit directly in the parent Hive directory (`tilesize=500/buffer=50`), eliminating nested directory crawling.
> 2. The 50m buffer is **fully preserved** across all subdivisions, preventing edge-effect interpolation degradation.

---

### Step 6: Multi-Tile Batch Streaming
Stream multiple tiles in a single concise command:

```bash
als-finder fetch tile 14 16 \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --sidecar \
  --overwrite
```

**Console Output:**
```text
Successfully processed 2 target tile(s) (2 file(s) generated):
  - Tile 14 -> .../CA_SierraNevada_5_2022_tile_E0738000_N4330500.laz
  - Tile 16 -> .../CA_SierraNevada_5_2022_tile_E0738000_N4331500.laz
```

---

### Step 7: Downstream Unbuffering & 1-Line Mosaicking

Because every `.laz` file includes a companion `.json` sidecar storing exact unbuffering crop parameters (`crop_gdal_te` / `crop_pdal_bounds`), downstream processing and mosaicking are completely automated:

```bash
TILES_DIR="scratch/test_workspace/data/tiles/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50"

# 1. Process point clouds and crop away the 50m buffer
for LAZ in "$TILES_DIR"/*.laz; do
    SIDECAR="${LAZ%.laz}.json"
    CROP_BOX=$(jq -r '.crop_gdal_te' "$SIDECAR")

    # Example: compute Canopy Height Model (CHM) with buffer, then crop to core:
    # my_chm_tool "$LAZ" temp.tif
    # gdal_translate -projwin $CROP_BOX temp.tif "${LAZ%.laz}_chm.tif"
done

# 2. Build a seamless mosaic across the entire study area (works for both 500m and 250m tiles):
# gdalbuildvrt full_study_area_chm.vrt "$TILES_DIR"/*_chm.tif
```

---

### Step 8: High-Throughput Slurm Job Array Recipe

Here is the production Slurm script for running on-demand streaming across hundreds of HPC cores with zero OOM risk and instant scratch cleanup:

```bash
#!/usr/bin/env bash
#SBATCH --job-name=als_tiles
#SBATCH --array=0-5656
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:30:00

set -e

WORKSPACE="/shared/project/workspace"
FINAL_DIR="/shared/project/products/chm"
LOCAL_SCRATCH="$TMPDIR/als_work_${SLURM_ARRAY_TASK_ID}"
mkdir -p "$LOCAL_SCRATCH" "$FINAL_DIR"

# 1. Fetch on demand to local scratch (auto-subdivides if dense)
als-finder fetch tile "$SLURM_ARRAY_TASK_ID" \
    --workspace "$WORKSPACE" \
    --tile-size 500 \
    --buffer-size 50 \
    --max-points 4000000 \
    --output "$LOCAL_SCRATCH" \
    --sidecar \
    --overwrite

# 2. Process all files in scratch (whether 1 tile or 4 quadrants)
for LAZ in "$LOCAL_SCRATCH"/*.laz; do
    SIDECAR="${LAZ%.laz}.json"
    BASENAME=$(basename "$LAZ" .laz)
    CROP_BOX=$(jq -r '.crop_gdal_te' "$SIDECAR")

    # Run point cloud metric tool
    # compute_metric "$LAZ" "$LOCAL_SCRATCH/${BASENAME}_raw.tif"

    # Crop off buffer to permanent storage
    # gdal_translate -projwin $CROP_BOX "$LOCAL_SCRATCH/${BASENAME}_raw.tif" "$FINAL_DIR/${BASENAME}_chm.tif"

    # Immediate cleanup of raw point cloud
    rm -f "$LAZ" "$SIDECAR"
done

# Clean scratch
rm -rf "$LOCAL_SCRATCH"
```

---

### Step 9: Bulk Offline Survey Archiving (`als-finder fetch survey`)
For researchers who prefer to pre-download the entire raw dataset locally for air-gapped or offline processing:

```bash
als-finder fetch survey \
  --workspace scratch/test_workspace \
  --name "CA_SierraNevada_5_2022" \
  --execute
```

---

### Step 10: Workspace Maintenance (`als-finder workspace`)
Update catalog filters or clean interim scratch files:

```bash
# Update catalog criteria (e.g. restrict to QL1):
als-finder workspace update --workspace scratch/test_workspace --density QL1

# Clean scratch workspace:
als-finder workspace clean --workspace scratch/test_workspace
```

---

## 🐍 Programmatic Python API

You can also import and use `als_finder` directly in Python scripts and Jupyter Notebooks:

```python
import als_finder

# 1. Query tile specification and unbuffering bounds
spec = als_finder.get_tile_spec(
    workspace="scratch/test_workspace",
    tile_id=15,
    tile_size=500,
    buffer_size=50
)

print(f"Basename: {spec['basename']}")
print(f"Grid CRS: {spec['grid_crs']}")
print(f"Crop GDAL -te: {spec['crop_gdal_te']}")

# 2. Inspect Central Core Area vs Buffered Footprint
core = spec['core_poly']
buffered = spec['buffered_poly']

print(f"Core Tile Dimensions: {round(core.bounds[2] - core.bounds[0])}m x {round(core.bounds[3] - core.bounds[1])}m")
print(f"Buffer Extension: {round((buffered.bounds[2] - core.bounds[2]))}m on all sides")
```

---

## 🏛️ Authorship & Citation

This software is released under the open-source **MIT License**. Copyright **Jonathan Greenberg**.

**Project Authors & Contributors:**
* **Jonathan Greenberg** (University of Nevada, Reno): Lead Developer and Core Project Architect.
* **Andrew Hudak** (US Forest Service): Advisory feedback and scientific computing grant alignment.
* **Antigravity (Google DeepMind)**: AI Software Engineering Partner.