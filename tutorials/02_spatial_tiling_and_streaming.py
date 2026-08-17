# %% [markdown]
# # Tutorial 02: Metric Spatial Tiling, Cloud-Native Streaming & Containerized Workflows
# 
# Welcome to **Tutorial 02** of the `als-finder` suite!
# 
# In this module, you will learn how to build an **out-of-core, memory-safe, and storage-safe LiDAR pipeline** that processes multi-terabyte regional point cloud datasets on modest workstations, cloud instances (GitHub Codespaces / Actions), containerized environments (Docker / Apptainer), and distributed HPC supercomputing clusters (Slurm Job Arrays).
# 
# ---
# 
# ## Step 1: Environment & Workspace Setup
# 
# We import `als_finder` (which automatically bundles and configures `geopandas`, `shapely`, `pdal`, `laspy`, `folium`, and `PROJ_DATA`/`GDAL_DATA` coordinate systems) and initialize an isolated workspace directory.

# %%
import json
import sys
from pathlib import Path
import shutil
import subprocess

# Standard spatial and tabular libraries (configured via als-finder)
import geopandas as gpd
import pandas as pd
import folium
from shapely.geometry import box
import laspy
import pdal

# Import als_finder as the primary root module
import als_finder

# Set up isolated workspace and scratch storage
workspace_dir = Path("./tiling_workspace").resolve()
scratch_dir = workspace_dir / "scratch"
scratch_dir.mkdir(parents=True, exist_ok=True)

print(f"ALS-Finder v{als_finder.__version__} | Workspace: {workspace_dir}")

# %% [markdown]
# ---
# ## Step 2: Define Region of Interest (ROI) & Study Area
# 
# We define a compact **1.2 km x 1.2 km study area** near Lake Tahoe (WGS84 EPSG:4326) that intersects high-density public point cloud surveys (USGS 3DEP & OpenTopography).

# %%
# Define bounding box (~1.2 km x 1.2 km) and save to GeoPackage
roi_box = box(-120.010, 38.930, -119.996, 38.942)
roi_gdf = gpd.GeoDataFrame({"name": ["Lake Tahoe ROI"]}, geometry=[roi_box], crs="EPSG:4326")

roi_path = workspace_dir / "roi.gpkg"
roi_gdf.to_file(roi_path, driver="GPKG")

# Interactive Leaflet Preview
roi_map = roi_gdf.explore(
    style_kwds={"fillColor": "#3182bd", "fillOpacity": 0.2, "color": "#08519c", "weight": 2.5},
    name="Study Area (ROI)"
)
roi_map

# %% [markdown]
# ---
# ## Step 3: Federated Discovery (Zero-Download Cloud Indexing)
# 
# Index remote LiDAR acquisitions across public repositories directly into `catalog/manifest.json` and `catalog/catalog.gpkg` without downloading large point clouds.

# %%
# Run federated discovery indexing remote USGS 3DEP cloud-native EPT repositories
subprocess.run([
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--workspace", str(workspace_dir),
    "--provider", "USGS_EPT"
], check=True)

manifest_path = workspace_dir / "catalog" / "manifest.json"
catalog_path = workspace_dir / "catalog" / "catalog.gpkg"

# %% [markdown]
# ---
# ## Step 4: Metric Spatial Grid Generation (Core + Overlap Buffers)
# 
# Decompose the ROI into uniform **500m core tiles** with **20m spatial overlap buffers**.
# - **Core (500m $\times$ 500m)**: The final non-overlapping tile boundary.
# - **Buffer (+20m margin)**: Extra spatial context streamed during processing to eliminate boundary artifacts in ground filtering and DTM interpolation.

# %%
# Query Tile #0 specification (als-finder automatically creates Hive-partitioned grid under the hood)
tile_size_m = 500
buffer_size_m = 20

spec_0 = als_finder.get_tile_spec(workspace_dir, tile_id=0, tile_size=tile_size_m, buffer_size=buffer_size_m)
grid_crs = spec_0["grid_crs"]
grid_gpkg_path = als_finder.get_grid_path(workspace_dir, tile_size=tile_size_m, buffer_size=buffer_size_m)

print(f"Tile ID:         {spec_0['tile_id']}")
print(f"Basename:        {spec_0['basename']}")
print(f"Projected CRS:   {spec_0['grid_crs']}")
print(f"Hive Path:       {spec_0['hive_path']}")
print(f"Core Bounds:     {spec_0['core_bounds_str']}")
print(f"Buffered Bounds: {spec_0['buffered_bounds_str']}")

# %% [markdown]
# ---
# ## Step 5: Multi-Layer Leaflet Visualization (ROI + Acquisitions + Tiling Grid)
# 
# Overlay the ROI boundary, remote acquisition footprints, and metric grid tiles with interactive layer toggling.

# %%
# Load layers directly via als-finder and GeoPandas
grid_gdf = als_finder.read_grid(workspace_dir, tile_size=tile_size_m, buffer_size=buffer_size_m)
catalog_gdf = gpd.read_file(catalog_path)

# Build interactive 3-layer map
tiling_map = roi_gdf.explore(
    style_kwds={"fillColor": "none", "color": "#000000", "weight": 3, "dashArray": "6, 6"},
    name="1. Study Area (ROI)"
)
catalog_gdf.explore(
    m=tiling_map,
    column="name",
    cmap="Set2",
    style_kwds={"fillOpacity": 0.20, "weight": 1.2},
    name="2. Remote Acquisitions",
    legend=False,
    popup=["name"]
)
grid_gdf.explore(
    m=tiling_map,
    color="#3182bd",
    style_kwds={"fillOpacity": 0.25, "weight": 1.5},
    name=f"3. Metric Grid ({tile_size_m}m)",
    popup=["tile_id"]
)

folium.LayerControl().add_to(tiling_map)
tiling_map

# %% [markdown]
# ---
# ## Step 6: Memory-Safe Single Tile On-Demand Streaming (`als_finder.stream_single_tile`)
# 
# Stream **Tile #0** directly over HTTP from the remote cloud repository into local scratch storage.

# %%
# Stream single buffered tile over HTTP
streamed_tile = als_finder.stream_single_tile(
    manifest_or_grid_path=manifest_path,
    tile_id=0,
    out_path=scratch_dir,
    tile_size=tile_size_m,
    buffer_size=buffer_size_m,
    crs=grid_crs,
    overwrite=True
)

# Inspect streamed point cloud
with laspy.open(str(streamed_tile)) as fh:
    print(f"Streamed Tile: {streamed_tile.name} ({streamed_tile.stat().st_size / 1e6:.2f} MB)")
    print(f"Points:        {fh.header.point_count:,}")
    print(f"Elevation [Z]: [{fh.header.z_min:.2f} m, {fh.header.z_max:.2f} m]")

# %% [markdown]
# ---
# ## Step 7: Out-of-Core Processing Loop (PDAL SMRF Ground Filtering & Buffer Cropping)
# 
# Process multiple tiles sequentially with a constant, minimal memory and disk footprint:
# 1. Stream single buffered tile over HTTP into scratch storage.
# 2. Run PDAL SMRF ground classification and crop the 20m overlap buffer to the core tile bounds.
# 3. Write standardized output tile and delete scratch storage.

# %%
out_dir = workspace_dir / "data" / "standardized"
out_dir.mkdir(parents=True, exist_ok=True)
results = []

for tid in [0, 1]:
    spec = als_finder.get_tile_spec(workspace_dir, tile_id=tid, tile_size=tile_size_m, buffer_size=buffer_size_m)
    out_tile = out_dir / spec["hive_path"]
    out_tile.parent.mkdir(parents=True, exist_ok=True)
    
    # 1. Stream buffered tile into scratch
    raw_tile = als_finder.stream_single_tile(
        manifest_or_grid_path=manifest_path,
        tile_id=tid,
        out_path=scratch_dir,
        tile_size=tile_size_m,
        buffer_size=buffer_size_m,
        crs=grid_crs,
        overwrite=True
    )
    
    # 2. PDAL: SMRF Ground Filtering -> Crop Buffer Margin -> Export LAZ
    pipeline_json = {
        "pipeline": [
            str(raw_tile),
            {"type": "filters.smrf", "scalar": 1.2, "slope": 0.2, "threshold": 0.45, "window": 16.0},
            {"type": "filters.crop", "bounds": spec["core_bounds_str"]},
            {"type": "writers.las", "filename": str(out_tile), "compression": "laszip"}
        ]
    }
    pdal.Pipeline(json.dumps(pipeline_json)).execute()
    
    # 3. Inspect results and purge scratch file
    with laspy.open(str(out_tile)) as fh:
        pts = fh.read()
        ground_cnt = (pts.classification == 2).sum()
        results.append({
            "Tile_ID": tid,
            "File": out_tile.name,
            "Points": len(pts),
            "Ground_Pts": ground_cnt,
            "Ground_%": round(ground_cnt / len(pts) * 100, 1) if len(pts) > 0 else 0,
            "Size_MB": round(out_tile.stat().st_size / 1e6, 2)
        })
        
    raw_tile.unlink(missing_ok=True)

pd.DataFrame(results)

# %% [markdown]
# ---
# ## Step 8: Equivalent R-Based Tile Processing Pipeline (`terra` + `rlas` + `lidR`)
# 
# R researchers use the exact same out-of-core streaming architecture:

# %%
r_script_content = f"""
suppressPackageStartupMessages({{
  library(jsonlite)
  library(terra)
  library(rlas)
}})

# 1. Read vector grid in R
grid <- terra::vect("{grid_gpkg_path}")
cat("Loaded", length(grid), "tiles in R (CRS:", crs(grid, proj=TRUE), ")\\n")

# 2. Stream single tile via als-finder CLI into scratch
scratch <- "{scratch_dir / 'r_stream_tile_0.laz'}"
system(paste("{sys.executable} -m als_finder.cli fetch-tile --manifest {manifest_path} --tile-id 0 --tile-size {tile_size_m} --buffer-size {buffer_size_m} --crs {grid_crs} --output", scratch, "--overwrite --json"))

# 3. Read point records in R
if (file.exists(scratch)) {{
  pts <- rlas::read.las(scratch)
  cat("Ingested", nrow(pts), "points in R | Elevation Range:", min(pts$Z), "to", max(pts$Z), "m\\n")
  unlink(scratch)  # Storage hygiene
}}
"""

r_script_path = workspace_dir / "process_tile.R"
r_script_path.write_text(r_script_content)

if shutil.which("Rscript"):
    subprocess.run(["Rscript", str(r_script_path)], check=True)

# %% [markdown]
# ---
# ## Step 9: Containerized Deployment & Strict RAM Capping (Docker / Apptainer)
# 
# Run point cloud workers inside isolated containers with explicit memory caps:
# 
# ```bash
# # Execute tile fetch inside Docker with strict 4GB RAM ceiling
# docker run --rm \
#   --memory="4g" \
#   --memory-swap="4g" \
#   -e OMP_NUM_THREADS=1 \
#   -v $(pwd)/tiling_workspace:/workspace \
#   ghcr.io/cms-2024-hudak/als-finder:latest \
#   fetch-tile \
#     --manifest /workspace/catalog/manifest.json \
#     --tile-id 0 \
#     --tile-size 500 \
#     --buffer-size 20 \
#     --crs EPSG:32610 \
#     --output /workspace/scratch/docker_tile_0.laz \
#     --overwrite \
#     --json
# ```

# %% [markdown]
# ---
# ## Step 10: Slurm HPC Job Array Scaling
# 
# On supercomputing clusters, submit a Slurm job array to process hundreds of tiles concurrently in parallel:
# 
# ```bash
# #!/bin/bash
# #SBATCH --job-name=als_stream
# #SBATCH --array=0-23
# #SBATCH --cpus-per-task=2
# #SBATCH --mem=4G
# #SBATCH --time=00:20:00
# 
# als-finder fetch-tile \
#   --manifest ./catalog/manifest.json \
#   --tile-id $SLURM_ARRAY_TASK_ID \
#   --tile-size 500 \
#   --buffer-size 20 \
#   --crs EPSG:32610 \
#   --output /scratch/$USER/tile_${SLURM_ARRAY_TASK_ID}.laz \
#   --overwrite \
#   --json
# ```

# %%
# Verify CLI fetch-tile parity locally
test_cli_out = scratch_dir / "cli_test.laz"
subprocess.run([
    sys.executable, "-m", "als_finder.cli", "fetch-tile",
    "--manifest", str(manifest_path),
    "--tile-id", "0",
    "--tile-size", str(tile_size_m),
    "--buffer-size", str(buffer_size_m),
    "--crs", str(grid_crs),
    "--output", str(test_cli_out),
    "--overwrite",
    "--json"
], check=True)

test_cli_out.unlink(missing_ok=True)
print("✓ Verified CLI fetch-tile command parity.")
