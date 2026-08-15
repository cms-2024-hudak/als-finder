# Tutorial 01: Big-Data LiDAR Discovery, Spatial Tiling & Single-Tile Streaming

Welcome to **ALS-Finder**! This interactive tutorial demonstrates how to search, grid, and stream massive airborne LiDAR point cloud datasets on-demand without downloading gigabytes of unneeded raw files upfront.

---

### 🌟 Key Concepts & Architectural Components

| Concept | Description | Underlying Module |
| :--- | :--- | :--- |
| **`workspace_dir`** | Isolated root directory containing catalog metadata, grids, and outputs | Filesystem path |
| **`manifest.json`** | Catalog database indexing federated remote cloud endpoints (USGS, NOAA, OpenTopography) | `als_finder.cli search` |
| **`catalog.gpkg`** | Spatial vector layer containing precise polygon footprints of discovered acquisitions | `als_finder.cli search` |
| **`grid.gpkg`** | Spatial index dividing ROI into uniform metric core tiles + edge overlap buffers | `als_finder.core.grid_manager` |
| **`get_tile_spec()`** | Zero-copy query to retrieve single-tile bounds, crop strings, and Hive paths | `als_finder.core.grid_manager` |
| **`stream_single_tile()`** | On-demand HTTP streaming of a single buffered tile with SMRF and HAG normalization | `als_finder.core.standardization` |

---

## 1. Environment & Workspace Initialization

We verify our environment, initialize `als_finder` (which configures `PROJ_DATA` and `GDAL_DATA` coordinate reference system paths), and configure an isolated workspace directory.

```bash
als-finder --version
```

### Python Setup:
```python
import os
import sys
import json
import subprocess
from pathlib import Path

import geopandas as gpd
import pandas as pd
import folium
from shapely.geometry import box

try:
    from IPython.display import display
except ImportError:
    display = print

# Import als_finder to auto-configure PROJ_DATA and GDAL_DATA paths
import als_finder
from als_finder.core.grid_manager import (
    build_workspace_grid,
    get_tile_spec,
    create_tile_grid_index,
)
from als_finder.core.standardization import stream_single_tile

# Setup demo workspace directory
workspace_dir = Path("./demo_workspace").resolve()
workspace_dir.mkdir(parents=True, exist_ok=True)

print(f"✓ Python Interpreter: {sys.executable}")
print(f"✓ ALS-Finder Version: {als_finder.__version__}")
print(f"✓ Workspace Directory: {workspace_dir}")
```

---

## 2. Extract & Inspect Region of Interest (ROI) with Leaflet

`als-finder` bundles a sample vector dataset: the **Lake Tahoe Basin Management Unit (LTBMU)** boundary.
We extract it using `get-example-roi` and visualize it on an interactive Leaflet basemap using `geopandas.GeoDataFrame.explore()`:

```bash
als-finder get-example-roi
```

### Python Inspection & Leaflet Mapping:
```python
print("Extracting sample Lake Tahoe ROI...")
result = subprocess.run([sys.executable, "-m", "als_finder.cli", "get-example-roi"], capture_output=True, text=True)
print(result.stdout.strip())

roi_path = Path("ltbmu_boundary.gpkg")
roi_gdf = gpd.read_file(roi_path)
print(f"\n✓ ROI Coordinate Reference System: {roi_gdf.crs}")
print(f"✓ ROI Total Bounds (WGS84): {roi_gdf.total_bounds}")

# Display interactive Leaflet Map of the ROI
roi_map = roi_gdf.explore(
    style_kwds={"fillColor": "#3388ff", "fillOpacity": 0.2, "color": "#0033aa", "weight": 2.5},
    name="Lake Tahoe Basin ROI",
    tooltip=False,
    popup=True
)
folium.LayerControl().add_to(roi_map)
display(roi_map)
```

---

## 3. Search Remote LiDAR Catalogs (Zero Point Cloud Download)

We query federated providers (**USGS 3DEP EPT** and **NOAA Coastal**) across the Lake Tahoe ROI for high-density point clouds (`--density QL1` = $\ge 8.0 \text{ pts/m}^2$).
This creates `catalog/manifest.json`, `catalog/catalog.gpkg`, and `catalog/catalog.csv` without fetching any point clouds:

```bash
als-finder search \
    --roi ./ltbmu_boundary.gpkg \
    --density QL1 \
    --workspace ./demo_workspace/ \
    --provider USGS_EPT \
    --provider NOAA_STAC
```

### Python Execution:
```python
print("Searching federated catalogs (USGS 3DEP + NOAA Coastal)...")

search_cmd = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--density", "QL1",
    "--workspace", str(workspace_dir),
    "--provider", "USGS_EPT",
    "--provider", "NOAA_STAC"
]

res = subprocess.run(search_cmd, capture_output=True, text=True)
print(res.stdout)
if res.stderr:
    print("Logs:", res.stderr)

manifest_path = workspace_dir / "catalog" / "manifest.json"
assert manifest_path.exists(), "Search stage failed to produce manifest.json!"

with open(manifest_path) as f:
    datasets = json.load(f)
print(f"✓ Successfully indexed {len(datasets)} dataset(s) in manifest.json!")
```

---

## 4. Explore Discovered Acquisitions & Interactive Leaflet Overlay

We inspect the tabular metadata summary and overlay the discovered acquisition footprints onto our ROI in Leaflet:

```python
# 1. Inspect Tabular Catalog Summary
catalog_csv = workspace_dir / "catalog" / "catalog.csv"
catalog_df = pd.read_csv(catalog_csv)
print("Top Discovered LiDAR Acquisitions:")
display(catalog_df[["Provider", "Name", "Date", "PointDensity"]].head(6))

# 2. Interactive Leaflet Multi-Layer Map
catalog_gpkg = workspace_dir / "catalog" / "catalog.gpkg"
catalog_gdf = gpd.read_file(catalog_gpkg)

# Base Leaflet map centered on ROI
coverage_map = roi_gdf.explore(
    style_kwds={"fillColor": "none", "color": "#000000", "weight": 3, "dashArray": "5, 5"},
    name="ROI (Tahoe Basin Boundary)",
    tooltip=False,
    popup=True
)

# Overlay Acquisition Footprints
catalog_gdf.explore(
    m=coverage_map,
    column="name",
    cmap="Set2",
    style_kwds={"fillOpacity": 0.4, "weight": 1.5},
    name="LiDAR Acquisitions",
    legend=True
)

folium.LayerControl().add_to(coverage_map)
display(coverage_map)
```

---

## 5. Lazy Metric Grid Generation (Core + Buffer Tiling)

Large-scale point cloud processing requires uniform metric grid tiles with spatial overlap buffers (e.g. 1200m core + 30m edge buffer) to eliminate boundary edge artifacts in ground classification (SMRF) and DTM/CHM interpolation.

`get_tile_spec()` dynamically:
1. Checks if the metric grid already exists,
2. Snaps the ROI to clean metric multiples in the projected CRS (e.g. UTM Zone 10N / `EPSG:32610`),
3. Lazily creates and exports the spatial vector grid into Hive storage: `catalog/grids/tilesize=1200/buffer=30/grid.gpkg`.

```python
# Request Tile ID #0 with 1200m core size + 30m buffer
tile_spec = get_tile_spec(workspace_dir, tile_id=0, tile_size=1200, buffer_size=30)

print("=" * 65)
print("                SINGLE TILE SPECIFICATION (TILE #0)              ")
print("=" * 65)
print(f"Tile ID:                {tile_spec['tile_id']}")
print(f"Basename:               {tile_spec['basename']}")
print(f"Projected Grid CRS:     {tile_spec['grid_crs']}")
print(f"Proposed Hive Path:     {tile_spec['hive_path']}")
print(f"Core PDAL Crop Bounds:  {tile_spec['core_bounds_str']}")
print(f"Buffered Stream Bounds: {tile_spec['buffered_bounds_str']}")
print("=" * 65)
```

---

## 6. Interactive Spatial Grid Visualization in Leaflet

Let's inspect the complete generated grid and display all tiles on our Leaflet map with Tile #0 highlighted:

```python
grid_gpkg = workspace_dir / "catalog" / "grids" / "tilesize=1200" / "buffer=30" / "grid.gpkg"
grid_gdf = gpd.read_file(grid_gpkg)
print(f"✓ Total Tiles in Projected Metric Grid: {len(grid_gdf)}")
print(f"✓ Grid Projected CRS: {grid_gdf.crs}")

# Create highlighted column for visual distinction of Tile #0
grid_gdf["highlight"] = grid_gdf["tile_id"].apply(lambda tid: "Tile #0 (Active Target)" if tid == 0 else "Grid Tiles")

grid_map = roi_gdf.explore(
    style_kwds={"fillColor": "none", "color": "#000000", "weight": 2.5},
    name="ROI Boundary"
)

grid_gdf.explore(
    m=grid_map,
    column="highlight",
    cmap=["#1f77b4", "#ff7f0e"],
    style_kwds={"fillOpacity": 0.35, "weight": 1.2},
    name="1200m Metric Grid",
    legend=True
)

folium.LayerControl().add_to(grid_map)
display(grid_map)
```

---

## 7. On-Demand Single-Tile Streaming (`stream_single_tile`)

Now we stream **only Tile #0** directly over HTTP. Under the hood:
1. Streams points from remote EPT cloud endpoints bounded by `buffered_bounds_str`,
2. Applies on-the-fly SMRF ground classification and HAG (Height Above Ground) tree height normalization,
3. Crops the overlap buffer and writes the standardized `.laz` tile inside an OS-level virtual memory sandbox.

```python
import laspy

out_tile_path = workspace_dir / "output_tiles" / tile_spec["basename"]
out_tile_path.parent.mkdir(parents=True, exist_ok=True)

print(f"Streaming single tile #{tile_spec['tile_id']} over HTTP...")
streamed_path = stream_single_tile(
    manifest_or_grid_path=manifest_path,
    tile_id=0,
    out_path=out_tile_path,
    buffer_size=30,
    crs=tile_spec["grid_crs"],
    overwrite=True
)

size_mb = streamed_path.stat().st_size / (1024 * 1024)
print(f"\n✓ Successfully streamed and standardized single tile!")
print(f"  Output File: {streamed_path}")
print(f"  File Size:   {size_mb:.2f} MB")

# Inspect the standardized point cloud header using laspy
with laspy.open(str(streamed_path)) as fh:
    header = fh.header
    print(f"\n  Point Count:  {header.point_count:,}")
    print(f"  Point Format: {header.point_format.id}")
    print(f"  Bounds X:     [{header.x_min:.2f}, {header.x_max:.2f}]")
    print(f"  Bounds Y:     [{header.y_min:.2f}, {header.y_max:.2f}]")
    print(f"  Bounds Z:     [{header.z_min:.2f}, {header.z_max:.2f}]")
```

---

## 8. CLI Equivalent for HPC Job Arrays

On high-performance compute clusters (such as SDSC Expanse or Slurm HPC clusters), distributed worker nodes execute this single-tile streaming workflow in parallel using `$SLURM_ARRAY_TASK_ID`:

```bash
# Slurm Worker single-tile execution command:
als-finder fetch-tile \
  --manifest demo_workspace/catalog/manifest.json \
  --tile-id $SLURM_ARRAY_TASK_ID \
  --buffer-size 30 \
  --crs EPSG:32610 \
  --output demo_workspace/scratch/tile_${SLURM_ARRAY_TASK_ID}.laz \
  --json
```

### Python Verification:
```python
# Execute the CLI fetch-tile command to verify command-line parity
cli_out = workspace_dir / "output_tiles" / "tile_cli_test.laz"
fetch_cmd = [
    sys.executable, "-m", "als_finder.cli", "fetch-tile",
    "--manifest", str(manifest_path),
    "--tile-id", "0",
    "--buffer-size", "30",
    "--output", str(cli_out),
    "--json"
]

print("Running CLI fetch-tile command...")
res = subprocess.run(fetch_cmd, capture_output=True, text=True)
print("CLI JSON Response:")
print(res.stdout)
```

---

## 9. Memory Safety & Recursive Sub-Tiling Guardrails

`als-finder` protects compute nodes from out-of-memory crashes using three key architectural invariants:
1. **OS Virtual Memory Limit**: Wraps subprocesses in `execute_with_memory_limit()` using `resource.setrlimit(RLIMIT_AS)` on Linux.
2. **Thread Clamping**: Enforces `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `GDAL_NUM_THREADS=1` to prevent underlying C++ libraries from spawning thread stacks that exceed memory limits.
3. **Dynamic Recursive Sub-Tiling**: If an unexpectedly dense tile triggers an OOM, the engine catches `MemoryError`, automatically subdivides the tile into 4 sub-quadrants, processes each with safety bounds, and merges them cleanly.

---

## Summary

You have successfully executed the complete end-to-end cloud-native LiDAR streaming pipeline:
1. **Search & Discovery**: Lightweight metadata query producing `manifest.json` and `catalog.gpkg`.
2. **Interactive Leaflet Mapping**: Visual inspection of ROI and acquisition footprints.
3. **Dynamic Metric Gridding**: ROI snapped and decomposed into uniform 1200m core tiles + 30m overlap buffers in Hive storage.
4. **On-Demand Streaming**: Single tiles fetched over HTTP with on-the-fly SMRF and HAG standardization.
5. **HPC Ready**: Slurm array task compatibility with zero-disk master node footprint.

---

### 👉 Next Step
Proceed to [Tutorial 02: Point Cloud Normalization & STAC Catalogs](./02_normalization_and_stac.md) to explore full regional STAC generation and 2D QA/QC Quicklooks!
