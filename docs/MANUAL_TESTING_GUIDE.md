# ALS-Finder Manual Verification & Testing Guide

This guide provides an end-to-end walkthrough for manually testing the core features of `als-finder`:
1. **Multi-Provider Discovery** (USGS 3DEP, NASA G-LiHT, NEON AOP, NASA Earthdata CMR / ORNL DAAC, OpenTopography)
2. **Dynamic Credential Resolution & Auto-Caching**
3. **Lazy On-Demand Tile Streaming** (`als-finder fetch-tile`)
4. **Cross-Language Point Cloud Ingestion** (Python `laspy` and R `lidR`)

---

## 🛠️ Step 0: Environment Setup & Activation

Because the project environment was created with Conda, activate it using `conda activate`:

```bash
cd /mnt/c/Users/gears/git/als-finder

# Option A: Activate by named Conda environment
conda activate als-finder-env

# Option B: Or activate via local prefix directory
conda activate /mnt/c/Users/gears/git/als-finder/.venv
```

*(Note: You can also execute `.venv/bin/als-finder` directly without activating).*

Verify CLI availability:
```bash
als-finder --version
als-finder --help
```

---

## 🔍 Test 1: Multi-Provider Search (USGS + NASA G-LiHT + NEON)

Search across multiple federal archives concurrently for the Lake Tahoe Region of Interest:

```bash
als-finder search \
  --roi src/als_finder/data/ltbmu_boundary.gpkg \
  --workspace scratch/test_workspace \
  --provider gliht,neon,usgs
```

### What to Verify:
- [ ] Console displays the unified table of discovered datasets across providers.
- [ ] `scratch/test_workspace/catalog/catalog.gpkg` is created and contains the spatial footprint polygons.
- [ ] `scratch/test_workspace/catalog/manifest.json` is generated with sanitized metadata.

---

## 🛰️ Test 2: NASA Earthdata CMR STAC Search (Authenticated)

Query the NASA Common Metadata Repository (CMR) for NASA Carbon Monitoring System (CMS) airborne point clouds using your cached Earthdata Login token:

```bash
als-finder search \
  --name "Maryland" \
  --workspace scratch/test_earthdata \
  --provider earthdata
```

### What to Verify:
- [ ] Successfully queries ORNL DAAC STAC without credential errors.
- [ ] Discovers the `CMS_MD_BIOMASS_2021` airborne LiDAR dataset.

---

## ⚡ Test 3: Lazy On-Demand Tile Streaming (`fetch-tile`)

Extract a single 500m spatial sub-tile on demand from remote cloud octrees / swaths into a local `.laz` file:

```bash
als-finder fetch-tile \
  --manifest tutorials/tiling_workspace/catalog/grid.gpkg \
  --tile-id 0 \
  --output scratch/test_tile_0.laz \
  --overwrite
```

### What to Verify:
- [ ] Output prints: `Successfully streamed tile 0 to scratch/test_tile_0.laz`.
- [ ] File `scratch/test_tile_0.laz` is created in under 20 seconds without downloading the full multi-GB regional dataset.

---

## 📊 Test 4: Inspect Streamed Tile in Python (`laspy`)

Verify the geometry, point count, and attributes of the streamed sub-tile:

```bash
python -c "
import laspy

with laspy.open('scratch/test_tile_0.laz') as reader:
    header = reader.header
    print('LAS Version:', header.version)
    print('Point Count:', f'{header.point_count:,}')
    print('Elevation Range (Z):', round(header.z_min, 2), 'to', round(header.z_max, 2), 'm')

    las = reader.read()
    classes = sorted(list(set(las.classification)))
    print('ASPRS Classes Present:', classes)
"
```

---

## 🧪 Test 5: Automated Unit Test Suite

Run the full pytest suite to verify all 19 provider, CLI, and grid manager tests:

```bash
pytest tests/
```

### Expected Output:
```
================== 19 passed in 10.12s ==================
```
