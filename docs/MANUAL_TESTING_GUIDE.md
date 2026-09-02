# ALS-Finder Manual Testing Guide

This guide walks through testing each main capability of `als-finder`. All test outputs, catalogs, and extracted `.laz` tiles are placed strictly inside the `scratch/` directory.

---

## Step 0: Activate Your Environment

```bash
cd /mnt/c/Users/gears/git/als-finder

# Activate your Conda environment:
conda activate als-finder-env
# OR by path:
conda activate /mnt/c/Users/gears/git/als-finder/.venv
```

Confirm that the CLI tool runs:
```bash
als-finder --version
als-finder --help
```

---

## Test 1: Search Across Repositories (USGS + NASA G-LiHT + NEON)

Search for available airborne LiDAR datasets intersecting the Lake Tahoe study area:

```bash
als-finder search \
  --roi src/als_finder/data/ltbmu_boundary.gpkg \
  --workspace scratch/test_workspace \
  --provider gliht,neon,usgs
```

### What to check:
- [ ] A formatted table appears listing matching datasets, acquisition dates, estimated payload sizes (GB), pulse densities, and areas.
- [ ] `scratch/test_workspace/catalog/catalog.gpkg` is created containing the dataset footprint polygons.
- [ ] `scratch/test_workspace/catalog/manifest.json` is created containing the metadata.

---

## Test 2: Search NASA Earthdata (CMS / ORNL DAAC)

Search for NASA Carbon Monitoring System (CMS) biomass LiDAR campaigns:

```bash
als-finder search \
  --name "Maryland" \
  --workspace scratch/test_earthdata \
  --provider earthdata
```

### What to check:
- [ ] The search runs instantly without prompts (using your saved Earthdata token).
- [ ] It finds `NASA CMS Maryland High-Resolution Canopy Biomass 2021` with estimated payload size (~1229.82 GB).
- [ ] `scratch/test_earthdata/catalog/catalog.gpkg` is created.

---

## Test 3: Query Spatial Grid Planning & Specific Tile Metadata (`als-finder plan`)

Before streaming or looping through tiles, inspect grid specs, total tile count, and query any tile's exact suffix-free basename and unbuffering crop box using the unified `plan` command (or backward-compatible alias `grid-info`):

```bash
als-finder plan \
  --workspace scratch/test_workspace \
  --tile-id 15 \
  --tile-size 500 \
  --buffer-size 50
```

### What to check:
- [ ] Terminal prints formatted grid and tile information:
  ```
  ==================================================
   ALS-FINDER SPATIAL PLANNING & GRID METRICS
  ==================================================
    Master Tiles:      5,657
    Total Leaf Tasks:  5,657
    Tile ID Range:     0 to 5656
    Tile Size:         500m (core)
    Buffer Size:       50m (overlap)
    Grid CRS:          EPSG:32610
    Target Tile ID:    15
    Basename:          CA_SierraNevada_5_2022_tile_E0738000_N4331000
    Hive Directory:    provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50
    Crop PDAL Bounds:  ([738000.0, 738500.0], [4330500.0, 4331000.0])
    Crop GDAL -te:     738000.0 4330500.0 738500.0 4331000.0
    Grid File:         scratch/test_workspace/catalog/grids/tilesize=500/buffer=50/grid.gpkg
  ==================================================
  ```
- [ ] **Direct Field Extraction (`--field <key>`)**: Query specific properties directly without parsing JSON:
  ```bash
  # Returns suffix-free basename: CA_SierraNevada_5_2022_tile_E0738000_N4331000
  als-finder plan --workspace scratch/test_workspace --tile-id 15 --tile-size 500 --buffer-size 50 --field basename

  # Returns relative Hive directory: provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50
  als-finder plan --workspace scratch/test_workspace --tile-id 15 --tile-size 500 --buffer-size 50 --field hive_dir

  # Returns crop bounds for PDAL: ([738000.0, 738500.0], [4330500.0, 4331000.0])
  als-finder plan --workspace scratch/test_workspace --tile-id 15 --tile-size 500 --buffer-size 50 --field crop_pdal_bounds
  ```
- [ ] **Export to Shell Environment (`--format env`)**: Generate key-value pairs ready for `eval`:
  ```bash
  als-finder plan --workspace scratch/test_workspace --tile-id 15 --tile-size 500 --buffer-size 50 --format env
  ```
  *Output:*
  ```bash
  STATUS="success"
  TILE_ID="15"
  TOTAL_TILES="5657"
  TOTAL_LEAF_TASKS="5657"
  TILE_ID_MIN="0"
  TILE_ID_MAX="5656"
  TILE_SIZE="500"
  BUFFER_SIZE="50"
  GRID_CRS="EPSG:32610"
  UL_EASTING="738000.0"
  UL_NORTHING="4331000.0"
  BASENAME="CA_SierraNevada_5_2022_tile_E0738000_N4331000"
  HIVE_DIR="provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50"
  HIVE_PATH="provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_E0738000_N4331000"
  PATH="/mnt/c/Users/gears/git/als-finder/scratch/test_workspace/data/tiles/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_E0738000_N4331000.laz"
  CROP_PDAL_BOUNDS="([738000.0, 738500.0], [4330500.0, 4331000.0])"
  CROP_GDAL_TE="738000.0 4330500.0 738500.0 4331000.0"
  CROP_MINX="738000.0"
  CROP_MINY="4330500.0"
  CROP_MAXX="738500.0"
  CROP_MAXY="4331000.0"
  SAMPLE_TILE_BOUNDS="([737950.0, 738550.0], [4330450.0, 4331050.0])"
  GRID_GPKG="scratch/test_workspace/catalog/grids/tilesize=500/buffer=50/grid.gpkg"
  ```

---

## Test 4: Pre-Flight Memory Risk Audit & Slurm Task List (`als-finder plan --max-points --tasks`)

Audit your study area against a target point budget (e.g. 4,000,000 points $\approx$ 4 GB RAM) and generate a flat leaf task list:

```bash
# 1. Run memory risk audit
als-finder plan \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --max-points 4000000

# 2. Generate flat leaf task list for Slurm job array
als-finder plan \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --max-points 4000000 \
  --tasks | head -n 12
```

### What to check:
- [ ] Terminal outputs the `MEMORY RISK AUDIT (PRE-FLIGHT)` section:
  ```
  --------------------------------------------------
   MEMORY RISK AUDIT (PRE-FLIGHT):
    Max Points Budget: 4,000,000
    Est Points/Tile:   10,504,800
    Subdivision:       5657 tiles exceed budget (split into 4 quadrants each)
    Slurm Array Size:  --array=1-22628
  ==================================================
  ```
- [ ] `--tasks` outputs leaf tile IDs sequentially:
  ```
  0_NW
  0_NE
  0_SW
  0_SE
  1_NW
  ...
  ```

---

## Test 5: Extract a Base Tile with Positional Syntax & Sidecar (`als-finder fetch tile 15`)

Extract standard tile 15 with a 50m overlap buffer using clean positional argument syntax:

```bash
als-finder fetch tile 15 \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --sidecar \
  --overwrite
```

### What to check:
- [ ] Terminal prints the Hive partition path and sidecar confirmation:
  ```
  Successfully streamed tile 15 to scratch/test_workspace/data/tiles/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_E0738000_N4331000.laz
  Wrote metadata sidecar to scratch/test_workspace/data/tiles/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_E0738000_N4331000.json
  ```

---

## Test 6: Extract Quadrant Sub-Tile on Demand (`als-finder fetch tile 15_NW`)

Stream only the northwest 250m quadrant of Tile 15:

```bash
als-finder fetch tile 15_NW \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --sidecar \
  --overwrite
```

### What to check:
- [ ] Terminal confirms streaming directly alongside base tiles in the nominal grid hierarchy (`tilesize=500/buffer=50`), with the buffer remaining constant at 50m:
  ```
  Successfully streamed tile 15_NW to scratch/test_workspace/data/tiles/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_E0738000_N4331000_NW.laz
  Wrote metadata sidecar to scratch/test_workspace/data/tiles/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_E0738000_N4331000_NW.json
  ```

---

## Test 6b: Multi-Tile Positional Streaming (`als-finder fetch tile 14 16`)

Stream multiple tiles in a single concise command:

```bash
als-finder fetch tile 14 16 \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --sidecar \
  --overwrite
```

### What to check:
- [ ] Terminal streams both tiles sequentially into the same Hive directory:
  ```
  Successfully processed 2 target tile(s) (2 file(s) generated):
    - Tile 14 -> .../CA_SierraNevada_5_2022_tile_E0738000_N4330500.laz
    - Tile 16 -> .../CA_SierraNevada_5_2022_tile_E0738000_N4331500.laz
  ```

---

## Test 7: Inspect Extracted Point Cloud & Quadrant Dimensions in Python

Check point counts, total footprint dimensions (core + buffer), elevation ranges, and point classifications:

```bash
.venv/bin/python -c "
import laspy
from pathlib import Path

tile_path = 'scratch/test_workspace/data/tiles/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_E0738000_N4331000.laz'

with laspy.open(tile_path) as reader:
    header = reader.header
    width_m = round(header.x_max - header.x_min, 1)
    height_m = round(header.y_max - header.y_min, 1)

    print('Streamed Tile File:', tile_path)
    print('Point Count:', f'{header.point_count:,}')
    print(f'Tile Footprint: {width_m}m x {height_m}m (matches 500m core + 2x50m buffer = 600m)')
    print(f'Elevation Range (Z): {round(header.z_min, 2)}m to {round(header.z_max, 2)}m')

    las = reader.read()
    classes = sorted(list(set(las.classification)))
    print('Point Classes Present:', classes)
"
```

---

## Test 8: Programmatic Tile Metadata & Core Unbuffering in Python

Inspect tile metadata, Hive paths, and recover the unbuffered central core boundary to crop away boundary edge effects after point cloud metrics or classification:

```bash
.venv/bin/python -c "
import als_finder

# 1. Query tile spec for Tile 15
spec = als_finder.get_tile_spec('scratch/test_workspace', tile_id=15, tile_size=500, buffer_size=50)

print('--- Tile Spec Metadata ---')
print('Tile ID:', spec['tile_id'])
print('Basename (Suffix-Free):', spec['basename'])
print('Hive Dir:', spec['hive_dir'])
print('Hive Path:', spec['hive_path'])
print('Grid CRS:', spec['grid_crs'])
print('Crop PDAL Bounds:', spec['crop_pdal_bounds'])
print('Crop GDAL -te:', spec['crop_gdal_te'])

# 2. Inspect Central Core Area vs Streamed Buffered Area
core = spec['core_poly']
buffered = spec['buffered_poly']

print('\n--- Spatial Footprints & Unbuffering ---')
print(f'Buffered Bounds (Streamed):   X=[{buffered.bounds[0]}, {buffered.bounds[2]}], Y=[{buffered.bounds[1]}, {buffered.bounds[3]}]')
print(f'Core Bounds (Crop-back area): X=[{core.bounds[0]}, {core.bounds[2]}], Y=[{core.bounds[1]}, {core.bounds[3]}]')
print(f'Core Tile Dimensions: {round(core.bounds[2] - core.bounds[0])}m x {round(core.bounds[3] - core.bounds[1])}m')
print(f'Buffer Extension: {round((buffered.bounds[2] - core.bounds[2]))}m on all sides')
"
```

### What to check:
- [ ] Core tile bounds are printed (e.g. `X=[738000.0, 738500.0]`) showing the exact 500m central area.
- [ ] Buffered bounds are printed (e.g. `X=[737950.0, 738550.0]`) confirming the 50m overlap buffer.

---

## Test 9: Run the Full Automated Test Suite

Run all automated unit tests:

```bash
pytest tests/
```

### Expected Output:
```
================== 24 passed in 21.08s ==================
```
