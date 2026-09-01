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

Extract a single 500m sub-tile (e.g. tile ID 15) directly from the workspace with a 30m buffer around the perimeter:

```bash
als-finder fetch-tile \
  --workspace scratch/test_workspace \
  --tile-id 15 \
  --output scratch/test_tile_15.laz \
  --overwrite
```

### What to check:
- [ ] Terminal prints: `Successfully streamed tile 15 to scratch/test_tile_15.laz`.
- [ ] The file `scratch/test_tile_15.laz` is created locally in `scratch/`.

---

## Test 4: Inspect the Extracted Point Cloud in Python

Check point counts, coordinate bounding boxes, elevation (Z) ranges, and point classifications:

```bash
python -c "
import laspy

with laspy.open('scratch/test_tile_0.laz') as reader:
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
