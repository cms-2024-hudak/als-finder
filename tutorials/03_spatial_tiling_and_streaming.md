# Tutorial 03: Metric Spatial Tiling & Cloud-Native Streaming

Welcome to **Tutorial 03** of the `als-finder` series! In this module, you will learn how to:
1. Generate uniform **projected metric vector grids** (e.g., 1200m core tiles with 30m overlap buffers) using `grid_manager.py`.
2. Inspect the spatial grid metadata for downstream pipeline integration using `als-finder grid-info`.
3. Stream isolated spatial tiles on demand from remote cloud endpoints with zero-copy SQL lookups using `als-finder fetch-tile`.
4. Understand the memory guardrails, thread clamping, and dynamic recursive sub-tiling under out-of-memory (OOM) conditions.

---

## 1. Why Spatial Tiling & Buffering are Critical

When processing large regional LiDAR datasets across HPC clusters:
- **Edge Artifacts**: Algorithms like SMRF (ground classification) and DTM/CHM interpolation fail or produce steep artifacts at the boundary of a tile if neighboring points are missing.
- **Solution**: `als-finder` generates a **Core Tile** (e.g. 1200m $\times$ 1200m) surrounded by a **Buffered Processing Tile** (e.g. $+30\text{m}$ on all sides). Points are fetched and filtered across the buffered extent, and the buffer is cleanly cropped away before the final export.

```bash
als-finder fetch-tile --help
als-finder grid-info --help
```

---

## 2. Inspecting Grid Metadata with `grid-info`

Let's query the spatial grid configuration of our discovered workspace. `als-finder grid-info --json` provides machine-readable output for programmatic tool integration:

```bash
als-finder grid-info --manifest ./demo_workspace/catalog/manifest.json --json
```

### Visualizing the Metric Vector Grid in Python:
```python
import geopandas as gpd
import matplotlib.pyplot as plt
from pathlib import Path

grid_gpkg = Path("demo_workspace/catalog/grid.gpkg")
if grid_gpkg.exists():
    grid_gdf = gpd.read_file(grid_gpkg)
    print(f"Total Grid Tiles: {len(grid_gdf)}")
    print(f"Grid Projected CRS: {grid_gdf.crs}")
    
    fig, ax = plt.subplots(figsize=(8, 8))
    grid_gdf.plot(ax=ax, color="lightblue", edgecolor="navy", alpha=0.6)
    ax.set_title(f"Generated Metric Grid ({len(grid_gdf)} Tiles)", fontsize=12)
    plt.show()
```

---

## 3. On-Demand Single Tile Streaming via `fetch-tile`

In HPC environments (such as Slurm array jobs), workers should stream only their assigned tile ID rather than downloading the entire regional catalog.

Let's stream **Tile ID 0** directly into a localized output file:

```bash
als-finder fetch-tile \
    --manifest ./demo_workspace/catalog/manifest.json \
    --tile-id 0 \
    --output ./demo_workspace/data/tiles/tile_0000.laz \
    --buffer-size 30 \
    --crs "EPSG:32610" \
    --json
```

### Inspecting Streamed Tile with `laspy`:
```python
import laspy
from pathlib import Path

tile_path = Path("demo_workspace/data/tiles/tile_0000.laz")
if tile_path.exists():
    with laspy.open(str(tile_path)) as fh:
        header = fh.header
        print(f"File: {tile_path.name}")
        print(f"Point Count: {header.point_count:,}")
        print(f"Point Format: {header.point_format.id}")
        print(f"Bounds X: [{header.x_min:.2f}, {header.x_max:.2f}]")
        print(f"Bounds Y: [{header.y_min:.2f}, {header.y_max:.2f}]")
        print(f"Bounds Z: [{header.z_min:.2f}, {header.z_max:.2f}]")
```

---

## 4. Memory Safety & Recursive Sub-Tiling Guardrails

`als-finder` protects compute nodes from out-of-memory crashes using two key architectural invariants:
1. **OS Virtual Memory Limit**: Wraps subprocesses in `execute_with_memory_limit()` using `resource.setrlimit(RLIMIT_AS)` on Linux (or `psutil` on Windows).
2. **Thread Clamping**: Forces `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `GDAL_NUM_THREADS=1` to prevent underlying C++ libraries from spawning thread stacks that exceed memory limits.
3. **Dynamic Recursive Sub-Tiling**: If an unexpectedly dense tile triggers an OOM, the engine catches `MemoryError`, automatically subdivides the tile into 4 sub-quadrants, processes each with safety bounds, and merges them cleanly.

---

### 👉 Next Step
Open [04_hpc_and_r_integration.md](file:///mnt/c/Users/gears/git/als-finder/tutorials/04_hpc_and_r_integration.md) (or `04_hpc_and_r_integration.ipynb`) to learn how to interface R (`sf`, `lidR`, `terra`) with `als-finder` and compute scientific forest metrics!
