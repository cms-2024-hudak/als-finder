# Tutorial 02: Metric Spatial Tiling, Cloud-Native Streaming & Containerized Workflows

Welcome to **Tutorial 02** of the `als-finder` suite!

In this module, you will learn how to build an **out-of-core, memory-safe, and storage-safe LiDAR pipeline** that processes multi-terabyte regional point cloud datasets on modest workstations, cloud instances (GitHub Codespaces / Actions), containerized environments (Docker / Apptainer), and distributed HPC supercomputing clusters (Slurm Job Arrays).

---

## Step 1: Environment & Workspace Setup

We import `als_finder` (which automatically bundles and configures `geopandas`, `shapely`, `pdal`, `laspy`, `folium`, and `PROJ_DATA`/`GDAL_DATA` coordinate systems) and initialize an isolated workspace directory.

```python
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

# Set up isolated workspace inside scratch/
workspace_dir = Path("./scratch/tiling_workspace").resolve()
scratch_dir = workspace_dir / "scratch"
scratch_dir.mkdir(parents=True, exist_ok=True)

print(f"ALS-Finder v{als_finder.__version__} | Workspace: {workspace_dir}")
```

---
## Step 2: Define Region of Interest (ROI) & Study Area

We define a compact **1.2 km x 1.2 km study area** near Lake Tahoe (WGS84 EPSG:4326) that intersects high-density public point cloud surveys (USGS 3DEP & OpenTopography).

```python
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
```

---
## Step 3: Federated Discovery (Zero-Download Cloud Indexing)

Index remote LiDAR acquisitions across public repositories directly into `catalog/manifest.json` and `catalog/catalog.gpkg` without downloading large point clouds.

```python
# Run federated discovery indexing remote USGS 3DEP cloud-native EPT repositories
subprocess.run([
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--workspace", str(workspace_dir),
    "--provider", "USGS_EPT"
], check=True)

manifest_path = workspace_dir / "catalog" / "manifest.json"
catalog_path = workspace_dir / "catalog" / "catalog.gpkg"
```

---
## Step 4: Metric Spatial Grid Generation (Core + Overlap Buffers)

Decompose the ROI into uniform **500m core tiles** with **20m spatial overlap buffers**.
- **Core (500m $\times$ 500m)**: The final non-overlapping tile boundary.
- **Buffer (+20m margin)**: Extra spatial context streamed during processing to eliminate boundary artifacts in ground filtering and DTM interpolation.

```python
# Query Tile #0 specification (als-finder automatically creates Hive-partitioned grid under the hood)
tile_size_m = 500
buffer_size_m = 20

spec_0 = als_finder.get_tile_spec(workspace_dir, tile_id=0, tile_size=tile_size_m, buffer_size=buffer_size_m, overwrite=True)
grid_crs = spec_0["grid_crs"]
grid_gpkg_path = als_finder.get_grid_path(workspace_dir, tile_size=tile_size_m, buffer_size=buffer_size_m)

print(f"Tile ID:             {spec_0['tile_id']}")
print(f"Basename:            {spec_0['basename']}")
print(f"Projected CRS:       {spec_0['grid_crs']}")
print(f"Hive Path:           {spec_0['hive_path']}")
print(f"Point Density:       {spec_0['point_density']} pts/m²")
print(f"Core Bounds:         {spec_0['core_bounds_str']}")
print(f"Buffered Bounds:     {spec_0['buffered_bounds_str']}")
print(f"Additional Metadata: {spec_0['additional_metadata']}")
```

---
## Step 5: Multi-Layer Leaflet Visualization (ROI + Acquisitions + Tiling Grid)

Overlay the ROI boundary, remote acquisition footprints, and metric grid tiles with interactive layer toggling.

```python
# Load layers directly via als-finder and GeoPandas
grid_gdf = als_finder.read_grid(workspace_dir, tile_size=tile_size_m, buffer_size=buffer_size_m)
catalog_gdf = gpd.read_file(catalog_path)

# Build interactive 4-layer map
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
    style_kwds={"fillOpacity": 0.20, "weight": 1.2},
    name=f"3. Metric Grid ({tile_size_m}m)",
    popup=["tile_id"]
)

# Highlight Target Tile #0 in vibrant red for the upcoming stream demonstration
target_tile_gdf = grid_gdf[grid_gdf["tile_id"] == 0]
target_tile_gdf.explore(
    m=tiling_map,
    color="#e41a1c",
    style_kwds={"fillColor": "#e41a1c", "fillOpacity": 0.55, "weight": 2.5},
    name="4. Target Stream Candidate (Tile #0)",
    popup=["tile_id", "point_density", "spatial_basename"]
)

folium.LayerControl().add_to(tiling_map)
tiling_map
```

---
## Step 6: Memory-Safe Single Tile On-Demand Streaming (`als_finder.stream_single_tile`)

Stream **Tile #0** directly over HTTP from the remote cloud repository into local scratch storage.

```python
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
```

---
## Step 7: Out-of-Core Processing Loop (PDAL SMRF Ground Filtering & Buffer Cropping)

Process multiple tiles sequentially with a constant, minimal memory and disk footprint:
1. Stream single buffered tile over HTTP into scratch storage.
2. Run PDAL SMRF ground classification and crop the 20m overlap buffer to the core tile bounds.
3. Write standardized output tile and delete scratch storage.

```python
out_dir = workspace_dir / "data" / "standardized"
out_dir.mkdir(parents=True, exist_ok=True)
target_tile_ids = [0, 1]
results = []

print("==========================================================================================")
print(f" Out-of-Core Processing Loop: {len(target_tile_ids)} Tiles (PDAL SMRF Filter & Crop)")
print("==========================================================================================")

for idx, tid in enumerate(target_tile_ids):
    spec = als_finder.get_tile_spec(workspace_dir, tile_id=tid, tile_size=tile_size_m, buffer_size=buffer_size_m)
    out_tile = out_dir / spec["hive_path"]
    out_tile.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\n--- [Tile {idx + 1}/{len(target_tile_ids)}] Processing Index #{tid}: {spec['spatial_basename']} ---")
    print(f"  Provider / Dataset: {spec['provider']} / {spec['dataset_id']}")
    print(f"  Core Extent:        {spec['core_bounds_str']}")
    print(f"  Buffered Extent:    {spec['buffered_bounds_str']}")
    
    # 1. Stream buffered tile into scratch
    print(f"  > Step 1: HTTP Stream: Fetching buffered tile ({tile_size_m}m + {buffer_size_m}m buffer)...")
    raw_tile = als_finder.stream_single_tile(
        manifest_or_grid_path=manifest_path,
        tile_id=tid,
        out_path=scratch_dir,
        tile_size=tile_size_m,
        buffer_size=buffer_size_m,
        crs=grid_crs,
        overwrite=True
    )
    print(f"    Streamed Raw LAZ: {raw_tile.name} ({raw_tile.stat().st_size / 1e6:.2f} MB)")
    
    # 2. PDAL: SMRF Ground Filtering -> Crop Buffer Margin -> Export LAZ
    print("  > Step 2: Executing PDAL Pipeline: SMRF Ground Filter -> Crop Margin -> Write Standardized LAZ...")
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
        print(f"  > Step 3: Standardized Output Wrote: {out_tile.relative_to(workspace_dir)}")
        print(f"    Core Points: {len(pts):,} (Ground: {ground_cnt:,} / {ground_cnt/len(pts)*100:.1f}%) | Size: {out_tile.stat().st_size / 1e6:.2f} MB")
        
    raw_tile.unlink(missing_ok=True)
    print(f"    ✓ Purged temporary scratch file: {raw_tile.name} (Zero-disk footprint maintained)")

print("\n==========================================================================================")
print(" Standardized Tile Processing Summary Table:")
print("==========================================================================================")
print(pd.DataFrame(results).to_string(index=False))
```

---
## Step 8: Native R Spatial Processing Pipeline (`tutorials/02_spatial_tiling_and_streaming.R`)

For R researchers (`terra` + `rlas` + `lidR`), ALS-Finder provides a dedicated standalone native script: [`tutorials/02_spatial_tiling_and_streaming.R`](./02_spatial_tiling_and_streaming.R).

### Key Highlights of the R Pipeline:
1. **Index-Driven Ingestion**: Query the tile directly by integer `tile_id` (no manual file naming).
2. **Dynamic Output Naming**: Extract `spatial_basename` and `hive_path` directly from `grid.gpkg`.
3. **Handling ASPRS 'Withheld' Points**: Flags flight line edge turns / scanner blunders and filters them cleanly.
4. **Raster Generation**: Rasterizes a 2m Canopy Surface Model (DSM) and saves it to structured directories.

```python
r_companion_script = Path("./tutorials/02_spatial_tiling_and_streaming.R").resolve()

if shutil.which("Rscript") and r_companion_script.exists():
    print(f"> Executing Native R Tutorial: Rscript {r_companion_script.name}...")
    subprocess.run(["Rscript", str(r_companion_script)], check=True)
else:
    print(f"Native R script ready at: {r_companion_script}")
```

---
## Step 9: Containerized Deployment & Strict RAM Capping (Docker / Apptainer)

Run point cloud workers inside isolated containers with explicit memory caps:

```bash
# Execute tile fetch inside Docker with strict 4GB RAM ceiling
docker run --rm \
  --memory="4g" \
  --memory-swap="4g" \
  -e OMP_NUM_THREADS=1 \
  -v $(pwd)/tiling_workspace:/workspace \
  ghcr.io/cms-2024-hudak/als-finder:latest \
  fetch tile 0 \
    --manifest /workspace/catalog/manifest.json \
    --tile-size 500 \
    --buffer-size 20 \
    --crs EPSG:32610 \
    --output /workspace/scratch/docker_tile_0.laz \
    --overwrite \
    --json
```

```python
# Test Containerized Execution (Docker) if Docker daemon is accessible
docker_bin = shutil.which("docker")
docker_output_laz = scratch_dir / "docker_tile_0.laz"

if docker_bin:
    print("> Executing Containerized Tile Stream inside Docker (4GB RAM Cap)...")
    docker_cmd = [
        "docker", "run", "--rm",
        "--memory=4g", "--memory-swap=4g",
        "-e", "OMP_NUM_THREADS=1",
        "-v", f"{Path.cwd() / 'src'}:/app/src",
        "-v", f"{workspace_dir}:/workspace",
        "als-finder:latest",
        "fetch", "tile", "0",
        "--manifest", "/workspace/catalog/manifest.json",
        "--tile-size", str(tile_size_m),
        "--buffer-size", str(buffer_size_m),
        "--crs", str(grid_crs),
        "--output", "/workspace/scratch/docker_tile_0.laz",
        "--overwrite", "--json"
    ]
    try:
        docker_res = subprocess.run(docker_cmd, capture_output=True, text=True)
        if docker_res.returncode == 0 and docker_output_laz.exists():
            print(f"✓ Docker Container Stream Success: {docker_output_laz.name} ({docker_output_laz.stat().st_size / 1e6:.2f} MB)")
            docker_output_laz.unlink(missing_ok=True)
        else:
            print(f"Docker run completed with code {docker_res.returncode}")
    except Exception as e:
        print(f"Docker execution notice: {e}")
else:
    print("Docker is not active in this environment; container recipe is ready for cloud/HPC deployment.")
```

---
## Step 10: Slurm HPC Job Array Scaling

On supercomputing clusters, submit a Slurm job array to process hundreds of tiles concurrently in parallel:

```bash
#!/bin/bash
#SBATCH --job-name=als_stream
#SBATCH --array=0-23
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:20:00

als-finder fetch tile $SLURM_ARRAY_TASK_ID \
  --manifest ./catalog/manifest.json \
  --tile-size 500 \
  --buffer-size 20 \
  --crs EPSG:32610 \
  --output /scratch/$USER/tile_${SLURM_ARRAY_TASK_ID}.laz \
  --overwrite \
  --json
```

```python
# Verify CLI fetch tile parity locally
test_cli_out = scratch_dir / "cli_test.laz"
subprocess.run([
    sys.executable, "-m", "als_finder.cli", "fetch", "tile", "0",
    "--manifest", str(manifest_path),
    "--tile-size", str(tile_size_m),
    "--buffer-size", str(buffer_size_m),
    "--crs", str(grid_crs),
    "--output", str(test_cli_out),
    "--overwrite",
    "--json"
], check=True)

test_cli_out.unlink(missing_ok=True)
print("✓ Verified CLI fetch tile command parity.")
```
