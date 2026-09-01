# ALS-Finder Manual Testing Guide

This guide walks through testing each main feature of `als-finder` step-by-step:
1. **Searching for LiDAR data** across multiple archives (USGS 3DEP, NASA G-LiHT, NEON AOP, NASA Earthdata)
2. **Checking API keys and credentials**
3. **Extracting buffered spatial tiles** on demand
4. **Reading and inspecting point clouds** in Python (`laspy`) and R (`lidR`)

---

## Step 0: Activate Your Environment

Because this environment uses Conda, activate it with:

```bash
cd /mnt/c/Users/gears/git/als-finder

# Activate the project environment:
conda activate als-finder-env
# OR by path:
conda activate /mnt/c/Users/gears/git/als-finder/.venv
```

*(You can also run `.venv/bin/als-finder` directly without activating).*

Check that the command-line tool runs:
```bash
als-finder --version
als-finder --help
```

---

## Test 1: Search Across Repositories (USGS + NASA G-LiHT + NEON)

Search for available airborne LiDAR over the Lake Tahoe study area across multiple repositories at once:

```bash
als-finder search \
  --roi src/als_finder/data/ltbmu_boundary.gpkg \
  --workspace scratch/test_workspace \
  --provider gliht,neon,usgs
```

### What to check:
- [ ] A table appears listing all datasets that intersect the study area.
- [ ] `scratch/test_workspace/catalog/catalog.gpkg` is created containing the dataset footprint polygons.
- [ ] `scratch/test_workspace/catalog/manifest.json` is created with the dataset metadata.

---

## Test 2: Search NASA Earthdata (CMS / ORNL DAAC)

Search for NASA Carbon Monitoring System (CMS) LiDAR datasets:

```bash
als-finder search \
  --name "Maryland" \
  --workspace scratch/test_earthdata \
  --provider earthdata
```

### What to check:
- [ ] The search runs using your saved Earthdata token.
- [ ] It finds the `CMS_MD_BIOMASS_2021` dataset and saves the catalog.

---

## Test 3: Extract a Tile on Demand (`fetch-tile`)

Extract a single 500m sub-tile (tile ID 0) with a 30m buffer around the edges:

```bash
als-finder fetch-tile \
  --manifest tutorials/tiling_workspace/catalog/grid.gpkg \
  --tile-id 0 \
  --output scratch/test_tile_0.laz \
  --overwrite
```

### What to check:
- [ ] Output prints: `Successfully streamed tile 0 to scratch/test_tile_0.laz`.
- [ ] The file `scratch/test_tile_0.laz` is created locally.

---

## Test 4: Inspect the Extracted Tile in Python

Check the point count, elevation range, and point classifications:

```bash
python -c "
import laspy

with laspy.open('scratch/test_tile_0.laz') as reader:
    header = reader.header
    print('Point Count:', f'{header.point_count:,}')
    print('Elevation (Z Range):', round(header.z_min, 2), 'to', round(header.z_max, 2), 'meters')

    las = reader.read()
    classes = sorted(list(set(las.classification)))
    print('Point Classes Present:', classes)
"
```

---

## Test 5: Run the Automated Test Suite

Run the full pytest suite:

```bash
pytest tests/
```

### Expected Output:
```
================== 19 passed in 10.12s ==================
```
