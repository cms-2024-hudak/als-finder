# Tutorial 02: Metric Spatial Tiling, Cloud-Native Streaming & Containerized Workflows

Welcome to **Tutorial 02** of the `als-finder` suite!

In this module, you will learn how to build an **out-of-core, memory-safe, and storage-safe LiDAR pipeline** that processes multi-terabyte regional point cloud datasets on modest workstations, cloud instances (GitHub Codespaces / Actions), containerized environments (Docker / Apptainer), and distributed HPC supercomputing clusters (Slurm Job Arrays).

---

## Step 1: Environment & Workspace Setup

We import `als_finder` (which automatically bundles and configures `geopandas`, `shapely`, `pdal`, `laspy`, `folium`, and `PROJ_DATA`/`GDAL_DATA` coordinate systems) and connect to our persistent workspace directory.

```python
import json
import os
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

# Use the unified tutorial workspace inside scratch/
workspace_dir = Path("./scratch/tahoe_workspace").resolve()
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
## Step 4: Metric Spatial Grid Planning (`als-finder plan`)

Decompose the ROI into uniform **500m core tiles** with **50m spatial overlap buffers**.
- **Core (500m $\times$ 500m)**: The final non-overlapping tile boundary.
- **Buffer (+50m margin)**: Extra spatial context streamed during processing to eliminate boundary edge artifacts in ground filtering and DTM interpolation.

```python
# Query Tile #0 specification (als-finder automatically creates Hive-partitioned grid under the hood)
tile_size_m = 500
buffer_size_m = 50

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

You can also plan your grid and inspect summary metrics directly from the command line:

```bash
# Inspect grid layout, estimated point counts, and bounds
als-finder plan --workspace ./scratch/tahoe_workspace
```

---
## Step 5: Pre-Flight Memory Auditing & Slurm Task Lists

### The Physics of Point Cloud Memory Budgets
Why do we specify a point budget (e.g. 5,000,000 points)?
- In compressed LAZ format on disk, points consume only **~2–4 bytes per point**.
- In raw memory structures (C++ / Python / `laspy`), each point requires **~50 bytes** ($X, Y, Z$, Intensity, Classification, GPS Time, Return Number).
- During algorithmic processing (k-d trees, Delaunay triangulation, SMRF morphological dilation), intermediate working buffers expand peak RAM consumption to **~200–300 bytes per point**.
- Therefore, on a standard compute node or container capped at **1 GB to 2 GB RAM per core**, processing **4,000,000 to 5,000,000 points** (~1.0–1.5 GB peak RAM) is the safe upper threshold before the operating system's Out-Of-Memory (OOM) killer triggers.

```python
# 1. Pre-flight memory audit against standard 5M point workstation budget
cmd_audit = [
    sys.executable, "-m", "als_finder.cli", "plan",
    "--workspace", str(workspace_dir),
    "--max-points", "5000000",
    "--format", "table"
]
subprocess.run(cmd_audit, check=True)

# 2. Test memory risk detection by setting a constrained 1M point budget
print("\n--- Auditing with 1M Point Budget (Triggers Subdivision Warning) ---")
cmd_strict = [
    sys.executable, "-m", "als_finder.cli", "plan",
    "--workspace", str(workspace_dir),
    "--max-points", "1000000",
    "--json"
]
res_strict = subprocess.run(cmd_strict, capture_output=True, text=True)
audit_json = json.loads(res_strict.stdout)
print(f"Memory Risk Detected:  {audit_json.get('memory_risk_detected')}")
print(f"Subdivision Required:  {audit_json.get('subdivision_required')}")
print(f"Estimated Points (T0): {audit_json.get('sample_tile_est_points'):,}")

# 3. Generate flat leaf task list for Slurm job arrays
cmd_tasks = [
    sys.executable, "-m", "als_finder.cli", "plan",
    "--workspace", str(workspace_dir),
    "--tasks"
]
tasks_res = subprocess.run(cmd_tasks, capture_output=True, text=True)
print("\n--- Slurm Leaf Task IDs (One per Job Array Element) ---")
print(tasks_res.stdout.strip())
```

---
## Step 6: Multi-Layer Leaflet Visualization (ROI + Acquisitions + Tiling Grid)

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
## Step 7: On-Demand Tile Streaming & Format Selection (LAZ vs. COPC)

`als-finder fetch tile` streams points on demand directly from remote cloud storage. You can choose the output format:
1. **`laz` (Default)**: Standard ASPRS LASzip. Fastest write time, lowest CPU overhead, universal compatibility with `lidR`, `pdal`, `laspy`.
2. **`copc`**: Cloud-Optimized Point Cloud (`.copc.laz`). Contains an internal octree Level-of-Detail (LOD) structure for cloud hosting and 3D web viewers (`copc.io`).

```python
# 1. Stream standard LAZ tile
streamed_laz = als_finder.stream_single_tile(
    manifest_or_grid_path=manifest_path,
    tile_id=0,
    out_path=scratch_dir,
    tile_size=tile_size_m,
    buffer_size=buffer_size_m,
    crs=grid_crs,
    tile_format="laz",
    overwrite=True
)

# 2. Stream Cloud-Optimized Point Cloud (COPC) tile
streamed_copc = als_finder.stream_single_tile(
    manifest_or_grid_path=manifest_path,
    tile_id=0,
    out_path=scratch_dir,
    tile_size=tile_size_m,
    buffer_size=buffer_size_m,
    crs=grid_crs,
    tile_format="copc",
    overwrite=True
)

# Verify COPC octree VLRs using laspy
with laspy.open(str(streamed_copc)) as fh:
    copc_vlrs = [vlr for vlr in fh.header.vlrs if vlr.record_id == 1 and "copc" in vlr.user_id.lower()]
    print(f"Streamed LAZ:  {streamed_laz.name} ({streamed_laz.stat().st_size / 1e6:.2f} MB)")
    print(f"Streamed COPC: {streamed_copc.name} ({streamed_copc.stat().st_size / 1e6:.2f} MB)")
    print(f"Points Count:  {fh.header.point_count:,}")
    print(f"COPC Octree Header Present: {len(copc_vlrs) > 0}")

# 3. Inspect Companion Metadata Sidecar
sidecar_file = streamed_laz.with_suffix(".json")
with open(sidecar_file) as f:
    sidecar_meta = json.load(f)

print(f"\n--- Companion Sidecar Metadata ({sidecar_file.name}) ---")
print(f"Parent Tile ID:   {sidecar_meta['tile_id']}")
print(f"Projected CRS:    {sidecar_meta['crs']}")
print(f"GDAL Crop Target: {sidecar_meta['crop_gdal_te']}")
print(f"Buffered Margin:  {sidecar_meta['buffered_bounds']}")
```

---
## Step 8: Hierarchical Adaptive Sub-Tiling & Automatic OOM Prevention

When high-density acquisitions exceed your memory budget, `als-finder` can bisect the tile into 4 spatial quadrants:
- Addressing: `0_NW`, `0_NE`, `0_SW`, `0_SE`
- Unbuffering: Each child quadrant retains the exact same buffer width (+50m) and precise unbuffering crop coordinates.

```python
# 1. Fetch a specific quadrant directly via CLI
cmd_quad = [
    sys.executable, "-m", "als_finder.cli", "fetch", "tile", "0_NW",
    "--workspace", str(workspace_dir),
    "--output", str(scratch_dir),
    "--overwrite"
]
subprocess.run(cmd_quad, check=True)

# 2. Demonstrate automatic OOM subdivision (enforcing 1M point budget on 1.6M tile)
print("\n--- Automatic OOM Subdivision (Splits Tile 0 into 4 Quadrants) ---")
cmd_auto_oom = [
    sys.executable, "-m", "als_finder.cli", "fetch", "tile", "0",
    "--workspace", str(workspace_dir),
    "--max-points", "1000000",
    "--output", str(scratch_dir),
    "--overwrite"
]
subprocess.run(cmd_auto_oom, check=True)

child_quads = list(scratch_dir.glob("*_0_*.laz"))
print(f"\n✓ Generated {len(child_quads)} Sub-Quadrant Files:")
for q in sorted(child_quads):
    print(f"  {q.name} ({q.stat().st_size / 1e6:.2f} MB)")
```

---
## Step 9: Out-of-Core Processing Loop (PDAL SMRF Ground Filtering & Buffer Cropping)

Process multiple tiles sequentially with a constant, minimal memory and disk footprint:
1. Stream single buffered tile over HTTP into scratch storage.
2. Run PDAL SMRF ground classification and crop the 50m overlap buffer to the core tile bounds.
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
    out_tile = out_tile.with_suffix(".laz")
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
## Step 10: Slurm HPC Job Array Scaling

On supercomputing clusters, submit a Slurm job array where each task streams an isolated tile:

```bash
#!/bin/bash
#SBATCH --job-name=als_stream
#SBATCH --array=0-15
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:20:00

# Map Slurm array index to tile ID
TASK_ID=$SLURM_ARRAY_TASK_ID

als-finder fetch tile "${TASK_ID}" \
  --workspace ./scratch/tahoe_workspace \
  --output /scratch/$USER/tiles/ \
  --sidecar \
  --overwrite
```

---
## Summary & Next Steps

You have mastered the cloud-native streaming and adaptive tiling architecture:
1. **Grid Planning**: Built metric 500m tiles with 50m buffers in true ground UTM coordinates.
2. **Memory Auditing**: Tested point budgets against system RAM to eliminate out-of-memory risks.
3. **Format Selection**: Streamed both standard compressed LAZ and Cloud-Optimized Point Clouds (COPC).
4. **Adaptive Sub-Tiling**: Explored hierarchical quadrant addressing (`0_NW`) and automated OOM bisection.
5. **Zero-Disk Processing**: Built an out-of-core pipeline cleaning temporary raw data after each step.

👉 **Next Step**: Proceed to [Tutorial 03: Point Cloud Normalization & OGC STAC Catalogs](./03_normalization_and_stac.md) to explore full-survey standardization and SpatioTemporal Asset Catalogs!
