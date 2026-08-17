# Tutorial 01: Complete ALS-Finder Discovery, Inspection & Retrieval Pipeline

Welcome to **ALS-Finder**! This interactive tutorial walks you through the core discovery, spatial filtering, and data retrieval workflow:
1. **Federated Discovery**: Query remote cloud point cloud catalogs (**USGS 3DEP EPT**, **NOAA Coastal STAC**, and **OpenTopography**) across flexible spatial, temporal, and point density filters with zero upfront point cloud downloads.
2. **Interactive Leaflet Mapping**: Visualize boundaries, query areas of interest, and overlay discovered LiDAR project footprints with interactive layer controls and tooltips.
3. **Search Filtering**: Filter by exact dataset names, wildcards, regular expressions, historical date ranges, point density (USGS QL levels), and provider registries.
4. **Atomic Updates**: Sync catalogs with upstream federal registries while maintaining timestamped rollback backups.
5. **Dry-Run & Safe Subsetting**: Preview fetch matrices (`fetch_array.csv`) before downloading or streaming tightly cropped cloud subsets directly from remote servers.

---

### 🌟 Architectural Overview & Core Workspace Components

| Workspace Path | Format | Description | Underlying Engine |
| :--- | :--- | :--- | :--- |
| `catalog/manifest.json` | JSON | Master registry tracking federated endpoints, bounding boxes, and project metadata | `als_finder.cli search` |
| `catalog/catalog.gpkg` | GeoPackage | Vector polygon boundaries representing discovered LiDAR project footprints | `als_finder.cli search` |
| `catalog/catalog.csv` | CSV | Human-readable tabular summary of discovered projects, dates, and point densities | `als_finder.cli search` |
| `catalog/fetch_array.csv`| CSV | Dry-run matrix planning physical tile URLs, download targets, and estimated sizes | `als_finder.cli download` |
| `data/raw/` | LAS / LAZ | Raw point cloud subsets organized in Hive hierarchy (`provider=*/dataset=*/`) | `als_finder.cli download --execute` |

---
## Step 1: Environment & Workspace Setup

We import required scientific spatial libraries, verify that `als_finder` is installed, and set up an isolated workspace folder.

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

# Import als_finder to auto-configure PROJ_DATA and GDAL_DATA coordinate system paths
import als_finder

# Set up dedicated workspace for this tutorial
workspace_dir = Path("./demo_workspace").resolve()
workspace_dir.mkdir(parents=True, exist_ok=True)

print(f"✓ Python Interpreter: {sys.executable}")
print(f"✓ ALS-Finder Version: {als_finder.__version__}")
print(f"✓ Workspace Root:     {workspace_dir}")
```

---
## Step 2: Extract & Inspect Region of Interest (ROI) with Leaflet

`als-finder` bundles a sample vector polygon boundary: the **Lake Tahoe Basin Management Unit (LTBMU)**.
We extract it to our working directory using `get-example-roi` and visualize it on an interactive Leaflet basemap.

```python
print("> Running: als-finder get-example-roi")
result = subprocess.run([sys.executable, "-m", "als_finder.cli", "get-example-roi"], capture_output=True, text=True)
print(result.stdout.strip())

roi_path = Path("ltbmu_boundary.gpkg")
roi_gdf = gpd.read_file(roi_path)

print(f"\n✓ ROI Coordinate Reference System: {roi_gdf.crs}")
print(f"✓ ROI Bounds (WGS84 minx, miny, maxx, maxy): {roi_gdf.total_bounds}")

# Display interactive Leaflet Map of the ROI
roi_map = roi_gdf.explore(
    style_kwds={"fillColor": "#3388ff", "fillOpacity": 0.2, "color": "#0033aa", "weight": 2.5},
    name="Lake Tahoe Basin ROI Boundary",
    tooltip=False,
    popup=True
)
folium.LayerControl().add_to(roi_map)
display(roi_map)
```

---
## Step 3: Base Federated Search (All Providers & Dates)

The easiest way to search for LiDAR is to provide an Area of Interest (`--roi`) and a target `--workspace`.

`als-finder` queries all remote registries and **deduplicates identical datasets** (by comparing case-insensitive dataset names and unique survey identifiers across providers, so that the same federal survey indexed in both USGS 3DEP and OpenTopography is not duplicated, while fully preserving multi-temporal surveys that spatially overlap the same watershed).

```python
print(f"> Running: als-finder search --roi {roi_path} --workspace {workspace_dir}")

cmd_base = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--workspace", str(workspace_dir)
]

res = subprocess.run(cmd_base, capture_output=True, text=True)
print(res.stdout)

manifest_path = workspace_dir / "catalog" / "manifest.json"
assert manifest_path.exists(), "Search failed to produce manifest.json!"

with open(manifest_path) as f:
    datasets = json.load(f)
print(f"✓ Successfully indexed {len(datasets)} dataset(s) across federated catalogs!")
```

---
## Step 4: Explore Catalog Metadata & Interactive Leaflet Overlay

The search stage generates three primary tracking documents inside `catalog/`:
- `manifest.json`: Full master metadata database.
- `catalog.gpkg`: Vector layer with polygon boundaries of each acquisition.
- `catalog.csv`: Summary table for quick tabular inspection.

```python
# 1. Tabular Summary Table
catalog_csv = workspace_dir / "catalog" / "catalog.csv"
catalog_df = pd.read_csv(catalog_csv)
print("Discovered LiDAR Acquisitions (Top 5):")
display(catalog_df[["Provider", "Name", "Date", "PointDensity", "AreaSqKm", "SizeMB"]].head())

# 2. Interactive Leaflet Multi-Layer Map
catalog_gpkg = workspace_dir / "catalog" / "catalog.gpkg"
catalog_gdf = gpd.read_file(catalog_gpkg)

# Base Leaflet map centered on the ROI
coverage_map = roi_gdf.explore(
    style_kwds={"fillColor": "none", "color": "#000000", "weight": 3, "dashArray": "5, 5"},
    name="ROI (Lake Tahoe Basin Boundary)",
    tooltip=False,
    popup=True
)

# Overlay Acquisition Footprints
catalog_gdf.explore(
    m=coverage_map,
    column="name",
    cmap="tab20",
    style_kwds={"fillOpacity": 0.4, "weight": 1.5},
    name="Discovered LiDAR Footprints",
    legend=True
)

folium.LayerControl().add_to(coverage_map)
display(coverage_map)
```

### 4.3 Inspecting Flexible "Additional Metadata" Across Providers

In addition to standard columns (Name, Date, Point Density), `als-finder` automatically captures 100% of provider-specific and un-standardized metadata attributes in `additional_metadata` (stored in `manifest.json` and as `additional_metadata_json` in `catalog.gpkg`).

```python
# Inspect rich additional metadata from discovered datasets
with open(manifest_path) as f:
    manifest_data = json.load(f)

for ds in manifest_data.get("datasets", []):
    name = ds.get("name")
    prov = ds.get("provider")
    extra = ds.get("additional_metadata") or ds.get("raw_metadata") or {}
    print(f"\nDataset: {name} [{prov}]")
    print(f"  Available Extra Metadata Keys ({len(extra)}): {list(extra.keys())}")
    # Display sample key-values
    for k in list(extra.keys())[:3]:
        print(f"    - {k}: {extra[k]}")
```

---
## Step 5: Advanced Search Filters (Name, Chronology, Density, Provider)

`als-finder` supports powerful filtering flags to isolate specific acquisitions before any downloading begins.

### 5.1 Filtering by Dataset Name (`--name`)

Filter by exact name, wildcard string (`*`), or regular expression (prefixed with `~`):

```python
# Example A: Exact Name
print('> Running: als-finder search --roi ltbmu_boundary.gpkg --name "CA_SierraNevada_5_2022" --workspace demo_workspace')
cmd_name_exact = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--name", "CA_SierraNevada_5_2022",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_name_exact, capture_output=True, text=True).stdout)

# Example B: Wildcard
print('> Running: als-finder search --roi ltbmu_boundary.gpkg --name "*Tahoe*" --workspace demo_workspace')
cmd_name_wildcard = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--name", "*Tahoe*",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_name_wildcard, capture_output=True, text=True).stdout)

# Example C: Python Regular Expression (~^CA_Sierra.*)
print('> Running: als-finder search --roi ltbmu_boundary.gpkg --name "~^CA_Sierra.*" --workspace demo_workspace')
cmd_name_regex = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--name", "~^CA_Sierra.*",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_name_regex, capture_output=True, text=True).stdout)
```

### 5.2 Filtering by Chronology (`--date`)

Search within specific historical windows or isolate datasets collected after a specific date using the slash syntax:

```python
# Example A: Open-ended Start Date (Acquisitions >= 2020-01-01)
print('> Running: als-finder search --roi ltbmu_boundary.gpkg --date 2020-01-01/ --workspace demo_workspace')
cmd_date_open = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--date", "2020-01-01/",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_date_open, capture_output=True, text=True).stdout)

# Example B: Bounded Historical Window (2015-01-01 to 2019-12-31)
print('> Running: als-finder search --roi ltbmu_boundary.gpkg --date 2015-01-01/2019-12-31 --workspace demo_workspace')
cmd_date_range = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--date", "2015-01-01/2019-12-31",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_date_range, capture_output=True, text=True).stdout)
```

### 5.3 Filtering by Point Density & Quality Level (`--density`)

`als-finder` supports both USGS 3DEP Topographic Quality Levels (`QL0` through `QL3`) or explicit numeric ranges (`pts/m2`).

```python
# Example A: USGS QL1 Quality Level (>= 8.0 pts/m2)
print('> Running: als-finder search --roi ltbmu_boundary.gpkg --density QL1 --workspace demo_workspace')
cmd_density_ql1 = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--density", "QL1",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_density_ql1, capture_output=True, text=True).stdout)

# Example B: Numeric Density Range (2.0 to 10.0 pts/m2)
print('> Running: als-finder search --roi ltbmu_boundary.gpkg --density 2/10 --workspace demo_workspace')
cmd_density_range = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--density", "2/10",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_density_range, capture_output=True, text=True).stdout)
```

### 5.4 Filtering by Specific Provider (`--provider`)

Supply specific provider flags (`USGS_EPT`, `NOAA_STAC`, or `OpenTopography`):

```python
print('> Running: als-finder search --roi ltbmu_boundary.gpkg --provider USGS_EPT --workspace demo_workspace')
cmd_provider = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--provider", "USGS_EPT",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_provider, capture_output=True, text=True).stdout)
```

---
## Step 6: Atomic Rollback Updates (`als-finder update`)

The generated `manifest.json` logs your original search parameters. To quickly check upstream federal registries for newly published data in your project area, run `update`.

*`als-finder` automatically makes a timestamped backup of your old `manifest.json`, `catalog.csv`, and `catalog.gpkg` before updating, ensuring old references are never lost.*

```python
print(f"> Running: als-finder update --workspace {workspace_dir}")
cmd_update = [
    sys.executable, "-m", "als_finder.cli", "update",
    "--workspace", str(workspace_dir)
]
res_update = subprocess.run(cmd_update, capture_output=True, text=True)
print(res_update.stdout)
```

---
## Step 7: Downloading & Subsetting (Stage 2)

To prevent accidentally downloading terabytes of point cloud data and to support High-Performance Computing (HPC) workflows, `als-finder` decouples search from download:
1. **Dry-Run Matrix Generation**: Running `download` without `--execute` creates `catalog/fetch_array.csv` containing tile URLs, download targets, and estimated sizes.
2. **Physical Execution**: Passing `--execute` streams/downloads the conformed files into a strict `Hive-Partitioned` directory hierarchy (`data/raw/provider=*/dataset=*/`).
3. **Dynamic EPT Spatial Subsetting**: When querying cloud-native EPT sources with a spatial `--roi`, `als-finder` streams only points intersecting your boundary, creating a single conformed spatial subset file (`[dataset]_subset.laz`).

```python
# Define a small micro-bounding box near Lake Tahoe for safe, rapid physical download testing
micro_roi = "-119.9915, 38.9285, -119.9885, 38.9315"
micro_workspace = Path("./tiny_subset").resolve()
micro_workspace.mkdir(parents=True, exist_ok=True)

# Step 7.1: Dry-Run Search and Fetch Matrix Generation
print(f'> Running: als-finder search --roi "{micro_roi}" --name "CA_SierraNevada_5_2022" --workspace tiny_subset')
cmd_search_micro = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", micro_roi,
    "--name", "CA_SierraNevada_5_2022",
    "--workspace", str(micro_workspace)
]
subprocess.run(cmd_search_micro)

print(f'> Running: als-finder download --roi "{micro_roi}" --name "CA_SierraNevada_5_2022" --workspace tiny_subset')
cmd_dry_run = [
    sys.executable, "-m", "als_finder.cli", "download",
    "--roi", micro_roi,
    "--name", "CA_SierraNevada_5_2022",
    "--workspace", str(micro_workspace)
]
res_dry = subprocess.run(cmd_dry_run, capture_output=True, text=True)
print(res_dry.stdout)

# Step 7.2: Physical Download Execution
print(f'> Running: als-finder download --roi "{micro_roi}" --name "CA_SierraNevada_5_2022" --workspace tiny_subset --execute')
cmd_exec_download = [
    sys.executable, "-m", "als_finder.cli", "download",
    "--roi", micro_roi,
    "--name", "CA_SierraNevada_5_2022",
    "--workspace", str(micro_workspace),
    "--execute"
]
res_exec = subprocess.run(cmd_exec_download, capture_output=True, text=True)
print(res_exec.stdout)

raw_laz_files = list(micro_workspace.glob("data/raw/**/*.laz"))
print(f"\n✓ Downloaded Raw Subsets: {len(raw_laz_files)} file(s)")
for p in raw_laz_files:
    size_mb = p.stat().st_size / (1024 * 1024)
    print(f"  {p.relative_to(micro_workspace)} ({size_mb:.2f} MB)")
```

---
## Summary & Next Steps

You have completed the core discovery, spatial filtering, and data retrieval workflow:
1. **Federated Discovery**: Queried multi-agency registries with zero upfront data footprint.
2. **Interactive Leaflet Mapping**: Visualized project boundaries and coverage maps.
3. **Search Filtering**: Filtered by name, dates, density (QL levels), and providers.
4. **Controlled Subsetting**: Previewed download arrays and fetched raw spatial subsets.

👉 **Next Step**: Proceed to [Tutorial 02: Point Cloud Normalization & STAC Catalogs](./02_normalization_and_stac.md) to explore SMRF ground classification, HAG normalization, and OGC STAC schema generation!
