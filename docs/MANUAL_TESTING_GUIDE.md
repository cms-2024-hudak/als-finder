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

## Test 3: Extract a Single Sub-Tile on Demand (`fetch-tile`)

Extract a single spatial sub-tile (e.g. tile ID 15) directly from the workspace. By default (without `--output`), `als-finder` automatically saves the tile into the standardized Hive directory partition:

```bash
als-finder fetch-tile \
  --workspace scratch/test_workspace \
  --tile-id 15 \
  --overwrite
```

### What to check:
- [ ] Terminal prints the Hive partition path:
  `Successfully streamed tile 15 to scratch/test_workspace/data/provider=USGS_EPT/dataset=CA_SierraNevada_5_2022/tiles/tilesize=1200/buffer=30/CA_SierraNevada_5_2022_tile_0015.laz`

---

## Test 4: Inspect the Extracted Point Cloud in Python

Check point counts, coordinate bounding boxes, elevation (Z) ranges, and point classifications:

```bash
.venv/bin/python -c "
import laspy
from pathlib import Path

# Find the streamed LAZ file in the Hive structure
tile_files = list(Path('scratch/test_workspace/data').rglob('*.laz'))
assert tile_files, 'No LAZ files found in data/'

tile_path = tile_files[0]
print('Reading Tile:', tile_path)

with laspy.open(tile_path) as reader:
    header = reader.header
    print('Point Count:', f'{header.point_count:,}')
    print('Elevation Range (Z):', round(header.z_min, 2), 'to', round(header.z_max, 2), 'meters')

    las = reader.read()
    classes = sorted(list(set(las.classification)))
    print('Point Classes Present:', classes)
"
```

---

## Test 5: Run the Full Automated Test Suite

Run all automated unit tests:

```bash
pytest tests/
```

### Expected Output:
```
================== 19 passed in 10.41s ==================
```
