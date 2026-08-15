# Tutorial 02: Metric Spatial Tiling, Cloud-Native Streaming & Containerized Workflows

Welcome to **Tutorial 02** of the `als-finder` suite!

In this module, you will learn how to build an **out-of-core, memory-safe, and storage-safe LiDAR pipeline** that processes multi-terabyte regional point cloud datasets on modest workstations, cloud instances (GitHub Codespaces / Actions), containerized environments (Docker / Apptainer), and distributed HPC supercomputing clusters (Slurm Job Arrays).

---

### 🌟 Key Concepts & Architectural Invariants

| Concept | Description | Underlying Module |
| :--- | :--- | :--- |
| **`grid_manager`** | Decomposes ROIs into uniform metric core tiles with spatial overlap buffers | `als_finder.core.grid_manager` |
| **`grid.gpkg`** | Hive-partitioned spatial vector index (`catalog/grids/tilesize=*/buffer=*/`) | `als_finder.core.grid_manager` |
| **`get_tile_spec()`** | Zero-copy query returning metric tile bounding boxes, crop strings, and Hive paths | `als_finder.core.grid_manager` |
| **`stream_single_tile()`** | On-demand HTTP streaming of a single buffered tile directly from cloud endpoints | `als_finder.core.standardization` |
| **`als-finder fetch-tile`** | CLI subcommand for distributed workers to fetch single tile payloads via JSON | `als_finder.cli fetch-tile` |
| **Edge Buffers** | Overlap margins (e.g. 20m–30m) eliminating boundary artifacts during ground filtering | `als_finder.core.grid_manager` |
| **Container Isolation** | Portable, reproducible single-tile processing inside Docker and Apptainer/Singularity | `Dockerfile` |
| **Memory Sandbox** | Strict OS virtual memory limits (`RLIMIT_AS`) and thread clamping (`OMP_NUM_THREADS=1`) | `als_finder.core.execution` |

---

## 1. Environment & Workspace Setup

We import required spatial libraries, verify that `als_finder` is installed (which automatically configures `PROJ_DATA` and `GDAL_DATA`), and initialize an isolated workspace directory.

### Terminal Command:
```bash
als-finder --version
```

### Python Interactive Setup:
```python
import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

import geopandas as gpd
import pandas as pd
import folium
from shapely.geometry import box, Polygon

try:
    from IPython.display import display
except ImportError:
    display = print

# Import als_finder to auto-configure PROJ_DATA and GDAL_DATA coordinate system paths
import als_finder
from als_finder.core.grid_manager import (
    build_workspace_grid,
    get_tile_spec,
    create_tile_grid_index,
)
from als_finder.core.standardization import stream_single_tile

# Dedicated workspace for Tutorial 02
workspace_dir = Path("./tiling_workspace").resolve()
workspace_dir.mkdir(parents=True, exist_ok=True)

print(f"✓ Python Interpreter: {sys.executable}")
print(f"✓ ALS-Finder Version: {als_finder.__version__}")
print(f"✓ Workspace Root:     {workspace_dir}")
```

---

## 2. Define a Multi-Dataset Region of Interest (ROI) & Leaflet Visualization

To demonstrate multi-dataset, multi-density cloud streaming that is safe and fast to run in any environment (including GitHub Actions / CI), we define a compact **1.2 km x 1.2 km Region of Interest** near the south-eastern shore of Lake Tahoe.

This bounding box intersects multiple high-density public point cloud acquisitions (**USGS 3DEP EPT** and **NOAA Coastal**).

### Python Execution & Leaflet Mapping:
```python
# Lake Tahoe bounding box in WGS84 coordinates: [min_lon, min_lat, max_lon, max_lat]
# Dimensions: ~1.2km East-West by ~1.2km North-South
min_lon, min_lat = -120.010, 38.930
max_lon, max_lat = -119.996, 38.942

roi_box = box(min_lon, min_lat, max_lon, max_lat)
roi_gdf = gpd.GeoDataFrame({"id": ["tahoe_micro_roi"], "name": ["Lake Tahoe Tiling Study Area"]}, geometry=[roi_box], crs="EPSG:4326")

roi_gpkg_path = workspace_dir / "roi.gpkg"
roi_gdf.to_file(roi_gpkg_path, driver="GPKG")

print(f"✓ ROI Bounding Box (WGS84): {roi_gdf.total_bounds}")
print(f"✓ ROI Area: {roi_gdf.to_crs('EPSG:32610').geometry.area.iloc[0] / 1e6:.2f} km²")

# Interactive Leaflet Map of the Study Area
roi_map = roi_gdf.explore(
    style_kwds={"fillColor": "#2b83ba", "fillOpacity": 0.25, "color": "#002b66", "weight": 2.5},
    name="Tiling Study Area (ROI)",
    tooltip=False,
    popup=True
)
folium.LayerControl().add_to(roi_map)
display(roi_map)
```

---

## 3. Federated Discovery (Zero-Download Cloud Indexing)

We search remote catalogs across **USGS 3DEP EPT** and **NOAA Coastal**.
This creates `catalog/manifest.json` and `catalog/catalog.gpkg` without downloading binary point clouds.

### Terminal Command:
```bash
als-finder search \
    --roi ./tiling_workspace/roi.gpkg \
    --workspace ./tiling_workspace/ \
    --provider USGS_EPT \
    --provider NOAA_STAC
```

### Python Interactive Execution:
```python
print(f"> Running: als-finder search --roi {roi_gpkg_path} --workspace {workspace_dir}")

cmd_search = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_gpkg_path),
    "--workspace", str(workspace_dir),
    "--provider", "USGS_EPT",
    "--provider", "NOAA_STAC"
]

res_search = subprocess.run(cmd_search, capture_output=True, text=True)
print(res_search.stdout)

manifest_path = workspace_dir / "catalog" / "manifest.json"
assert manifest_path.exists(), "Search failed to produce manifest.json!"

with open(manifest_path) as f:
    manifest_data = json.load(f)
print(f"✓ Successfully indexed {len(manifest_data.get('datasets', []))} intersecting dataset(s) in catalog!")
```

---

## 4. Metric Spatial Grid Generation (Core + Buffer Tiling)

Why are metric spatial tiling and edge buffers critical?
- **Edge Artifacts**: Spatial filters (like SMRF ground classification) and raster interpolation (DTM/CHM generation) produce severe edge artifacts if neighboring point context is missing at tile boundaries.
- **The Core + Buffer Solution**: `als-finder` generates a **Core Tile** (e.g. 500m $\times$ 500m) surrounded by a **Processing Buffer** (e.g. $+20\text{m}$ on all sides). Points are streamed across the buffered footprint, processed safely, and the outer buffer is cleanly cropped away.

`get_tile_spec()` automatically:
1. Detects whether the metric grid already exists,
2. Snaps the ROI bounds to metric multiples in the projected coordinate system (UTM Zone 10N / `EPSG:32610`),
3. Lazily builds and exports the spatial vector grid into Hive-partitioned storage: `catalog/grids/tilesize=500/buffer=20/grid.gpkg`.

### Python Interactive Execution:
```python
# Request specification for Tile #0 with 500m core tile size + 20m overlap buffer
tile_size_m = 500
buffer_size_m = 20

tile_spec_0 = get_tile_spec(workspace_dir, tile_id=0, tile_size=tile_size_m, buffer_size=buffer_size_m)

print("=" * 70)
print("                  METRIC TILE SPECIFICATION (TILE #0)                  ")
print("=" * 70)
print(f"Tile ID:                {tile_spec_0['tile_id']}")
print(f"Standardized Basename:  {tile_spec_0['basename']}")
print(f"Projected Grid CRS:     {tile_spec_0['grid_crs']}")
print(f"Hive Storage Path:      {tile_spec_0['hive_path']}")
print(f"Core PDAL Crop Bounds:  {tile_spec_0['core_bounds_str']}")
print(f"Buffered Stream Bounds: {tile_spec_0['buffered_bounds_str']}")
print("=" * 70)
```

---

## 5. Multi-Layer Leaflet Visualization (ROI + Acquisitions + Tiling Grid)

We inspect the generated vector grid and overlay the metric tiles and acquisition footprints onto our Leaflet basemap, highlighting the active target tile (Tile #0).

### Python Interactive Mapping:
```python
grid_gpkg_path = workspace_dir / "catalog" / "grids" / f"tilesize={tile_size_m}" / f"buffer={buffer_size_m}" / "grid.gpkg"
grid_gdf = gpd.read_file(grid_gpkg_path)
catalog_gpkg_path = workspace_dir / "catalog" / "catalog.gpkg"
catalog_gdf = gpd.read_file(catalog_gpkg_path)

print(f"✓ Total Metric Tiles: {len(grid_gdf)}")
print(f"✓ Grid Coordinate System: {grid_gdf.crs}")

# Create visual distinction for Tile #0
grid_gdf["status"] = grid_gdf["tile_id"].apply(lambda tid: "Tile #0 (Target)" if tid == 0 else "Adjacent Tiles")

# Build interactive Leaflet Map
tiling_map = roi_gdf.explore(
    style_kwds={"fillColor": "none", "color": "#000000", "weight": 3, "dashArray": "6, 6"},
    name="1. Study Area (ROI Boundary)"
)

catalog_gdf.explore(
    m=tiling_map,
    column="name",
    cmap="Set2",
    style_kwds={"fillOpacity": 0.25, "weight": 1.2},
    name="2. Remote Acquisition Footprints",
    legend=True
)

grid_gdf.explore(
    m=tiling_map,
    column="status",
    cmap=["#1f77b4", "#e31a1c"],
    style_kwds={"fillOpacity": 0.35, "weight": 1.5},
    name=f"3. Metric Grid ({tile_size_m}m Core Tiles)",
    legend=True
)

folium.LayerControl().add_to(tiling_map)
display(tiling_map)
```

---

## 6. Memory-Safe Single Tile "Hello World" Streaming (`fetch-tile`)

Now we stream **only Tile #0** directly over HTTP from the remote cloud EPT repository.
Under the hood:
1. The engine constructs a dynamic PDAL pipeline with `readers.ept` constrained to `buffered_bounds_str`.
2. Streams only points inside the spatial window with zero full-file download overhead.
3. Writes the buffered `.laz` file to disk.

### Terminal Command:
```bash
als-finder fetch-tile \
    --manifest ./tiling_workspace/catalog/manifest.json \
    --tile-id 0 \
    --tile-size 500 \
    --buffer-size 20 \
    --crs EPSG:32610 \
    --output ./tiling_workspace/scratch/tile_0000_raw.laz \
    --json
```

### Python Interactive Streaming:
```python
import laspy

# Stream single tile using Python API
output_tile_0 = workspace_dir / "scratch" / "tile_0000_raw.laz"
output_tile_0.parent.mkdir(parents=True, exist_ok=True)

print(f"> Streaming single Tile #0 over HTTP into: {output_tile_0.name}...")
streamed_tile = stream_single_tile(
    manifest_or_grid_path=manifest_path,
    tile_id=0,
    out_path=output_tile_0,
    tile_size=tile_size_m,
    buffer_size=buffer_size_m,
    crs=tile_spec_0["grid_crs"],
    overwrite=True
)

size_mb = streamed_tile.stat().st_size / (1024 * 1024)
print(f"\n✓ Successfully streamed single tile #{tile_spec_0['tile_id']}!")
print(f"  File Location: {streamed_tile}")
print(f"  File Size:     {size_mb:.2f} MB")

# Inspect the streamed point cloud header using laspy
with laspy.open(str(streamed_tile)) as fh:
    header = fh.header
    print(f"\n  Point Count:   {header.point_count:,}")
    print(f"  Point Format:  {header.point_format.id}")
    print(f"  X Range (m):   [{header.x_min:,.2f}, {header.x_max:,.2f}]")
    print(f"  Y Range (m):   [{header.y_min:,.2f}, {header.y_max:,.2f}]")
    print(f"  Elevation (m): [{header.z_min:,.2f}, {header.z_max:,.2f}]")
```

---

## 7. Memory-Safe Sequential Tile Loop (PDAL Python Workflow)

In a high-throughput pipeline (or a sequential worker on a low-memory laptop), we process tiles in an out-of-core loop:
1. **Stream Single Buffered Tile** over HTTP into local scratch storage.
2. **Apply Ground Classification (SMRF)**: Execute a PDAL pipeline applying `filters.smrf` to classify bare-earth points (Class 2).
3. **Crop Overlap Buffer**: Apply `filters.crop` with `core_bounds_str` to discard edge margins and prevent boundary seams.
4. **Export Conformed Output**: Write the final standardized `.laz` tile.
5. **Purge Scratch Memory/Storage**: Immediately delete raw streamed files to maintain a **constant, minimal disk footprint**.

### Python Execution:
```python
import pdal

# Define target tiles to loop through (e.g. first 2 tiles in our micro-grid)
target_tile_ids = [0, 1] if len(grid_gdf) >= 2 else [0]
standardized_out_dir = workspace_dir / "output_standardized_tiles"
standardized_out_dir.mkdir(parents=True, exist_ok=True)

processing_records = []

print(f"=== Starting Out-Of-Core PDAL Processing Loop ({len(target_tile_ids)} tiles) ===\n")

for tid in target_tile_ids:
    spec = get_tile_spec(workspace_dir, tile_id=tid, tile_size=tile_size_m, buffer_size=buffer_size_m)
    raw_scratch_path = workspace_dir / "scratch" / f"streamed_raw_tile_{tid:04d}.laz"
    final_tile_path = standardized_out_dir / spec["basename"]
    
    print(f"--- Processing Tile ID #{tid} ---")
    print(f"  Target File:     {spec['basename']}")
    print(f"  Core Bounds:     {spec['core_bounds_str']}")
    print(f"  Buffered Bounds: {spec['buffered_bounds_str']}")
    
    # 1. Stream buffered tile from remote cloud
    stream_single_tile(
        manifest_or_grid_path=manifest_path,
        tile_id=tid,
        out_path=raw_scratch_path,
        tile_size=tile_size_m,
        buffer_size=buffer_size_m,
        crs=spec["grid_crs"],
        overwrite=True
    )
    
    # 2. Construct PDAL Pipeline: Ground Classification (SMRF) + Core Buffer Cropping
    pdal_pipeline_json = {
        "pipeline": [
            str(raw_scratch_path),
            {
                "type": "filters.smrf",
                "scalar": 1.2,
                "slope": 0.2,
                "threshold": 0.45,
                "window": 16.0
            },
            {
                "type": "filters.crop",
                "bounds": spec["core_bounds_str"]
            },
            {
                "type": "writers.las",
                "filename": str(final_tile_path),
                "compression": "laszip"
            }
        ]
    }
    
    pipeline = pdal.Pipeline(json.dumps(pdal_pipeline_json))
    pipeline.execute()
    
    # 3. Read summary metrics from the processed tile
    with laspy.open(str(final_tile_path)) as fh:
        hdr = fh.header
        pts = fh.read()
        ground_pts = (pts.classification == 2).sum()
        ground_pct = (ground_pts / len(pts) * 100) if len(pts) > 0 else 0
        
    final_size_mb = final_tile_path.stat().st_size / (1024 * 1024)
    print(f"  ✓ Standardized Output: {final_tile_path.name} ({final_size_mb:.2f} MB)")
    print(f"  ✓ Processed Points:    {hdr.point_count:,} (Ground: {ground_pts:,} / {ground_pct:.1f}%)")
    
    # 4. Storage Safety: Delete raw scratch file
    if raw_scratch_path.exists():
        raw_scratch_path.unlink()
        print(f"  ✓ Scratch Storage Cleared: {raw_scratch_path.name} deleted\n")
        
    processing_records.append({
        "Tile_ID": tid,
        "Filename": spec["basename"],
        "Total_Points": hdr.point_count,
        "Ground_Points": ground_pts,
        "Ground_Ratio_%": round(ground_pct, 1),
        "Size_MB": round(final_size_mb, 2)
    })

print("=== Processing Loop Complete ===")
summary_df = pd.DataFrame(processing_records)
display(summary_df)
```

---

## 8. Equivalent R-Based Tile Processing Pipeline (`sf` + `lidR` + `terra`)

For researchers working in R, the exact same memory-safe and storage-safe paradigm applies:
1. R queries `als-finder grid-info --json` or reads `grid.gpkg` using `sf`.
2. R loops through tile IDs, calls `als-finder fetch-tile` via system subprocess to stream isolated tiles into scratch storage.
3. Ingests the tile into **`lidR`** (`readLAS`), performs ground classification (`classify_ground(las, csf())` or `smrf()`), clips the buffer, and computes a 1-meter Digital Terrain Model (**DTM**).
4. Deletes the scratch tile immediately after processing.

### R Script Implementation (`process_tile.R`):
```r
# ==============================================================================
# R Equivalent Pipeline: Memory-Safe Single-Tile Streaming & DTM Generation
# ==============================================================================
library(jsonlite)
library(sf)

# 1. Query Grid Info via als-finder CLI JSON API
grid_info_raw <- system("als-finder grid-info --manifest ./tiling_workspace/catalog/manifest.json --json", intern = TRUE)
grid_meta <- fromJSON(paste(grid_info_raw, collapse = ""))
cat("✓ Grid System CRS:", grid_meta$grid_crs, "\n")

# 2. Load the vector grid table in R using sf
grid_gpkg <- "./tiling_workspace/catalog/grids/tilesize=500/buffer=20/grid.gpkg"
if (file.exists(grid_gpkg)) {
  grid_sf <- st_read(grid_gpkg, layer = "grid", quiet = TRUE)
  cat("✓ Total Tiles Loaded in R sf:", nrow(grid_sf), "\n")
}

# 3. Simulate processing Tile ID #0 in R
scratch_tile <- "./tiling_workspace/scratch/tile_0_r_stream.laz"
fetch_cmd <- paste(
  "als-finder fetch-tile",
  "--manifest ./tiling_workspace/catalog/manifest.json",
  "--tile-id 0",
  "--buffer-size 20",
  "--output", scratch_tile,
  "--json"
)

cat("Fetching Tile #0 via als-finder CLI...\n")
system(fetch_cmd)

if (file.exists(scratch_tile)) {
  cat("✓ Streamed Tile in R Scratch. Size:", file.info(scratch_tile)$size / 1e6, "MB\n")
  
  # Check if lidR and terra are available for scientific processing
  if (requireNamespace("lidR", quietly = TRUE) && requireNamespace("terra", quietly = TRUE)) {
    library(lidR)
    library(terra)
    
    las <- readLAS(scratch_tile)
    cat("  Point Count in R:", length(las$X), "\n")
    
    # Ground classification via CSF algorithm
    las <- classify_ground(las, csf())
    
    # 1-meter Digital Terrain Model (DTM) via TIN interpolation
    dtm <- rasterize_terrain(las, res = 1.0, algorithm = tin())
    cat("  ✓ Successfully generated 1m DTM in R!\n")
  }
  
  # Storage Safety: Clean up scratch tile
  unlink(scratch_tile)
  cat("✓ Cleaned up scratch tile in R.\n")
}
```

---

## 9. Containerized Workflows & Enforcing Strict Memory Limits (Docker & Apptainer)

Running point cloud pipelines inside isolated containers guarantees 100% reproducible GDAL/PDAL/PROJ dependencies. More importantly, container runtimes allow you to **strictly cap RAM and CPU usage** so that large spatial jobs cannot starve the host system or exceed cluster allocations.

### 9.1 Docker Memory Limiting Flags

Docker provides kernel Cgroup controls to enforce memory safety:

| Docker Flag | Purpose | Recommended Spatial Setting |
| :--- | :--- | :--- |
| **`-m` / `--memory="4g"`** | **Hard RAM Limit**: Maximum physical memory the container can consume before kernel enforcement. | Set to per-worker allocation (e.g. `4g` or `8g`). |
| **`--memory-swap="4g"`** | **Strict Swap Disabling**: Setting swap equal to `--memory` prevents slow disk swapping and enforces a true hard RAM ceiling. | Equal to `--memory` to prevent silent swap thrashing. |
| **`--memory-reservation="2g"`** | **Soft Memory Limit**: Memory threshold that Docker attempts to preserve under host memory pressure. | `50%` of hard limit. |
| **`--cpus="2"`** | **CPU Core Throttling**: Restricts container to exact core count. | Aligned with worker cores. |
| **`-e OMP_NUM_THREADS=1`** | **Thread Clamping**: Prevents C++ PDAL/OpenMP libraries from spawning multi-threaded memory allocations. | `1` per worker. |

### 9.2 Complete Docker Execution Example with Strict 4GB RAM Limit:

```bash
docker run --rm \
  --memory="4g" \
  --memory-swap="4g" \
  --memory-reservation="2g" \
  --cpus="2" \
  -e OMP_NUM_THREADS=1 \
  -e OPENBLAS_NUM_THREADS=1 \
  -e GDAL_NUM_THREADS=1 \
  -v $(pwd)/tiling_workspace:/workspace \
  ghcr.io/cms-2024-hudak/als-finder:latest \
  fetch-tile \
    --manifest /workspace/catalog/manifest.json \
    --tile-id 0 \
    --buffer-size 20 \
    --output /workspace/scratch/docker_tile_0.laz \
    --json
```

> [!TIP]
> **Monitoring Container Memory Live:** While a container is processing dense tiles, you can open a secondary terminal and run `docker stats` to inspect real-time memory usage, cache consumption, and percentage of the allocated memory ceiling.

### 9.3 HPC Supercomputing via Apptainer / Singularity

On supercomputing clusters (like SDSC Expanse or NCSA Delta) where root Docker is disabled, Apptainer/Singularity executes the exact same OCI container image while Slurm enforces memory limits (`#SBATCH --mem=4G`):

```bash
# Execute tile fetch inside Singularity on HPC compute nodes with node-local memory safety
singularity exec \
  --bind ./tiling_workspace:/workspace \
  docker://ghcr.io/cms-2024-hudak/als-finder:latest \
  als-finder fetch-tile \
    --manifest /workspace/catalog/manifest.json \
    --tile-id $SLURM_ARRAY_TASK_ID \
    --buffer-size 20 \
    --output /scratch/$USER/tile_${SLURM_ARRAY_TASK_ID}.laz \
    --json
```

---

## 10. HPC Slurm Job Array Scaling (`als-finder fetch-tile`)

On high-performance supercomputing clusters (such as SDSC Expanse), you do not run a sequential `for` loop. Instead, you submit a **Slurm Job Array** where compute nodes process tiles concurrently in parallel using `$SLURM_ARRAY_TASK_ID`:

```bash
#!/bin/bash
#SBATCH --job-name=als_stream
#SBATCH --array=0-23
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00

# Each worker streams ONLY its assigned tile ID directly into node-local scratch storage
als-finder fetch-tile \
  --manifest ./tiling_workspace/catalog/manifest.json \
  --tile-id $SLURM_ARRAY_TASK_ID \
  --buffer-size 20 \
  --crs EPSG:32610 \
  --output /scratch/$USER/tile_${SLURM_ARRAY_TASK_ID}.laz \
  --json
```

### Python CLI Parity Verification:
```python
cli_test_tile = workspace_dir / "scratch" / "cli_array_test.laz"

fetch_cmd_cli = [
    sys.executable, "-m", "als_finder.cli", "fetch-tile",
    "--manifest", str(manifest_path),
    "--tile-id", "0",
    "--buffer-size", str(buffer_size_m),
    "--output", str(cli_test_tile),
    "--json"
]

print(f"> Running CLI fetch-tile: {' '.join(fetch_cmd_cli)}")
res_cli = subprocess.run(fetch_cmd_cli, capture_output=True, text=True)
print("\nCLI JSON Response:")
print(res_cli.stdout)

if cli_test_tile.exists():
    cli_test_tile.unlink()
    print("✓ Verified CLI fetch-tile parity and purged test scratch file.")
```

---

## Summary

You have completed the **Metric Spatial Tiling, Cloud-Native Streaming & Containerized Workflows** tutorial:
1. **Zero-Download Federated Discovery**: Indexed remote cloud point cloud catalogs over the ROI.
2. **Metric Spatial Grid Generation**: Decomposed the ROI into uniform 500m core tiles with 20m overlap buffers in Hive storage.
3. **Multi-Layer Leaflet Mapping**: Visualized the study area, remote project footprints, and metric grid with layer toggling.
4. **Memory-Safe Single-Tile Streaming**: Streamed isolated tiles over HTTP with zero upfront dataset downloads.
5. **Out-of-Core Processing Loop (PDAL)**: Applied SMRF ground classification and buffer cropping in a storage-safe loop.
6. **Cross-Language Parity (R/lidR)**: Verified equivalent out-of-core tile processing in R.
7. **Containerized Deployment**: Demonstrated memory-capped Docker containers and Apptainer/Singularity on HPC.
8. **HPC Slurm Ready**: Demonstrated direct parity with Slurm distributed job arrays.
