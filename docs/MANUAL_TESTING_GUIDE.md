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

## Test 3: Query Spatial Grid Information & Total Tile Count (`grid-info`)

Before streaming or looping through tiles, inspect how many tiles exist for any tile size and buffer configuration:

```bash
als-finder grid-info \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50
```

### What to check:
- [ ] Terminal prints formatted grid information:
  ```
  ==================================================
   ALS-FINDER SPATIAL GRID INFORMATION
  ==================================================
    Total Tiles:    5,657
    Tile ID Range:  0 to 5656
    Tile Size:      500m (core)
    Buffer Size:    50m (overlap)
    Grid CRS:       EPSG:32610
    Grid File:      scratch/test_workspace/catalog/grids/tilesize=500/buffer=50/grid.gpkg
  ==================================================
  ```
- [ ] **Direct Field Extraction (`--field <key>`)**: Query specific scalar properties directly without parsing JSON or tables:
  ```bash
  # Returns just the number 5657
  als-finder grid-info --workspace scratch/test_workspace --tile-size 500 --buffer-size 50 --field total_tiles

  # Returns just EPSG:32610
  als-finder grid-info --workspace scratch/test_workspace --tile-size 500 --buffer-size 50 --field grid_crs
  ```
- [ ] **Export to Shell Environment (`--format env`)**: Generate key-value pairs ready for `eval`:
  ```bash
  als-finder grid-info --workspace scratch/test_workspace --tile-size 500 --buffer-size 50 --format env
  ```
  *Output:*
  ```bash
  STATUS="success"
  TOTAL_TILES="5657"
  TILE_ID_MIN="0"
  TILE_ID_MAX="5656"
  TILE_SIZE="500"
  BUFFER_SIZE="50"
  GRID_CRS="EPSG:32610"
  SAMPLE_TILE_BOUNDS="([737450.0, 738050.0], [4328950.0, 4329550.0])"
  GRID_GPKG="scratch/test_workspace/catalog/grids/tilesize=500/buffer=50/grid.gpkg"
  ```
- [ ] **Full JSON (`--json`)**:
  ```bash
  als-finder grid-info --workspace scratch/test_workspace --tile-size 500 --buffer-size 50 --json
  ```

---

## Test 4: Pre-Flight Memory & Point Budget Risk Audit (`grid-info --max-points`)

Audit your study area against a target point budget (e.g. 4,000,000 points $\approx$ 4 GB RAM) before streaming any data:

```bash
als-finder grid-info \
  --workspace scratch/test_workspace \
  --tile-size 500 \
  --buffer-size 50 \
  --max-points 4000000
```

### What to check:
- [ ] Terminal outputs the `MEMORY RISK AUDIT (PRE-FLIGHT)` section:
  ```
  --------------------------------------------------
   MEMORY RISK AUDIT (PRE-FLIGHT):
    Max Points Budget: 4,000,000
    Est Points/Tile:   10,504,800
    Subdivision:       5657 tiles exceed budget (split into 4 quadrants each)
  ==================================================
  ```
- [ ] You can also run with `--json` for automated cluster deployment:
  ```bash
  als-finder grid-info --workspace scratch/test_workspace --tile-size 500 --buffer-size 50 --max-points 4000000 --json
  ```

---

## Test 5: Extract a Base Tile with Custom Size, Buffer & Sidecar (`fetch-tile`)

Extract a standard 500m base tile with a 50m overlap buffer and export a companion JSON metadata sidecar:

```bash
als-finder fetch-tile \
  --workspace scratch/test_workspace \
  --tile-id 15 \
  --tile-size 500 \
  --buffer-size 50 \
  --sidecar \
  --overwrite
```

### What to check:
- [ ] Terminal prints the Hive partition path and sidecar confirmation:
  ```
  Successfully streamed tile 15 to scratch/test_workspace/data/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tiles/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_0015.laz
  Wrote metadata sidecar to scratch/test_workspace/data/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tiles/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_0015.json
  ```

---

## Test 6: Extract a Quadrant Sub-Tile on Demand (`fetch-tile --tile-id 15_NW`)

Stream only the northwest 250m quadrant of Tile 15 to prevent memory overload:

```bash
als-finder fetch-tile \
  --workspace scratch/test_workspace \
  --tile-id 15_NW \
  --tile-size 500 \
  --buffer-size 50 \
  --sidecar \
  --overwrite
```

### What to check:
- [ ] Terminal confirms streaming directly to the scaled Hive hierarchy (`tilesize=250/buffer=25`):
  ```
  Successfully streamed tile 15_NW to scratch/test_workspace/data/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tiles/tilesize=250/buffer=25/CA_SierraNevada_5_2022_tile_0015_NW.laz
  Wrote metadata sidecar to scratch/test_workspace/data/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tiles/tilesize=250/buffer=25/CA_SierraNevada_5_2022_tile_0015_NW.json
  ```

---

## Test 7: Inspect Extracted Point Cloud & Quadrant Dimensions in Python

Check point counts, total footprint dimensions (core + buffer), elevation ranges, and point classifications:

```bash
.venv/bin/python -c "
import laspy
from pathlib import Path

tile_path = 'scratch/test_workspace/data/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tiles/tilesize=500/buffer=50/CA_SierraNevada_5_2022_tile_0015.laz'

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
print('Standard Basename:', spec['basename'])
print('Spatial Basename:', spec['spatial_basename'])
print('Hive Partition Path:', spec['hive_path'])
print('Grid CRS:', spec['grid_crs'])
print('Provider:', spec['provider'])
print('Dataset ID:', spec['dataset_id'])

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
