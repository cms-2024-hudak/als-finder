# Tutorial 01: Complete ALS-Finder Discovery, Standardization, STAC & Quicklook Pipeline

Welcome to **ALS-Finder**! This comprehensive tutorial guides you through the full data-science lifecycle for regional airborne LiDAR (Light Detection and Ranging):
1. **Federated Discovery**: Query remote cloud point cloud catalogs (**USGS 3DEP EPT**, **NOAA Coastal STAC**, and **OpenTopography**) across flexible spatial, temporal, and point density filters with zero upfront binary downloads.
2. **Interactive Leaflet Mapping**: Visualize boundaries, query areas of interest, and overlay discovered LiDAR project footprints with interactive layer controls and tooltips.
3. **Dry-Run & Safe Subsetting**: Preview fetch matrices (`fetch_array.csv`) before downloading or streaming tightly cropped cloud subsets directly from remote servers.
4. **Standardization & Normalization**: Apply automated SMRF ground classification, compute Height Above Ground (HAG), harmonize coordinate reference systems, and conform ASPRS taxonomy into Cloud-Optimized Point Clouds (`.copc.laz`).
5. **OGC STAC Indexing**: Generate standards-compliant SpatioTemporal Asset Catalogs (`catalog/stac/catalog.json`) with relative links and validate with `pystac`.
6. **Visual QA/QC Quicklooks**: Render 2D DEM Hillshade and Canopy Height Model (CHM) preview PNGs to inspect data quality in seconds.
7. **The Mega-Command**: Execute the entire multi-stage pipeline in a single uninterrupted command.

---

### 🌟 Architectural Overview & Core Workspace Components

| Workspace Path | Format | Description | Underlying Engine |
| :--- | :--- | :--- | :--- |
| `catalog/manifest.json` | JSON | Master registry tracking federated endpoints, bounding boxes, and project metadata | `als_finder.cli search` |
| `catalog/catalog.gpkg` | GeoPackage | Vector polygon boundaries representing discovered LiDAR project footprints | `als_finder.cli search` |
| `catalog/catalog.csv` | CSV | Human-readable tabular summary of discovered projects, dates, and point densities | `als_finder.cli search` |
| `catalog/fetch_array.csv`| CSV | Dry-run matrix planning physical tile URLs, download targets, and estimated sizes | `als_finder.cli download` |
| `data/raw/` | LAS / LAZ | Unconformed, vendor-specific raw point clouds organized in Hive hierarchy | `als_finder.cli download --execute` |
| `data/standardized/` | COPC LAZ | Analysis-ready, taxonomically uniform, HAG-normalized Cloud Optimized Point Clouds | `als_finder.cli standardize` |
| `catalog/stac/` | STAC JSON | OGC-compliant SpatioTemporal Asset Catalog searchable hierarchy | `als_finder.cli standardize --stac` |
| `data/quicklooks/` | PNG | 2D DEM Hillshade and Canopy Height Model (CHM) color-relief preview images | `als_finder.cli standardize --quicklook` |

---

## 1. Environment & Workspace Setup

We import required scientific spatial libraries, verify that `als_finder` is installed, and set up an isolated workspace directory.

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
import pystac
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

## 2. Extract & Inspect Region of Interest (ROI) with Leaflet

`als-finder` bundles a sample vector polygon boundary: the **Lake Tahoe Basin Management Unit (LTBMU)**.
We extract it to our working directory using `get-example-roi` and visualize it on an interactive Leaflet basemap.

```bash
als-finder get-example-roi
```

### Python Inspection & Leaflet Mapping:
```python
print("Extracting sample Lake Tahoe Basin ROI boundary...")
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

## 3. Base Federated Search (All Providers & Dates)

The easiest way to search for LiDAR is to provide an Area of Interest (`--roi`) and a target `--workspace`.
`als-finder` queries all remote registries, deduplicates overlapping datasets, and generates a clean tracking directory automatically without downloading any point clouds.

```bash
als-finder search \
    --roi ./ltbmu_boundary.gpkg \
    --workspace ./demo_workspace/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.2100 |    5819.74 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
 | OpenTopography  | USFS Freds Fire Lidar, CA 2015         | 2022-06-07   |     150.04 |  31.3700 |     641.96 |
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
 | USGS_EPT        | CA_UpperSouthAmerican_Eldorado_2019    | 2019-??-??   |    2075.29 |  43.1600 |    6454.20 |
 | OpenTopography  | Paleo-Outburst Floods in the Truckee R | 2019-11-06   |       5.71 |   8.4000 |      91.21 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9452               | 2019-10-21   |    2075.29 |  46.7700 |    5954.91 |
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9036               | 2018-07-07   |     253.48 |   0.7800 |   43731.68 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | OpenTopography  | Walker Fault System, Nevada, 2015      | 2017-07-28   |      35.77 |   7.2700 |     660.41 |
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
 | OpenTopography  | Lake Tahoe Basin Lidar                 | 2011-03-01   |     184.96 |  13.2000 |    1880.65 |
=================================================================================================================
 TOTAL DATASETS: 15 | ESTIMATED PAYLOAD: 9952.26 GB | QUERY TIME: 14.25s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: ./demo_workspace/catalog/catalog.gpkg
 JSON METADATA: ./demo_workspace/catalog/manifest.json
=================================================================================================================
```

### Python Execution:
```python
print("Executing Base Search across USGS 3DEP, NOAA Coastal, and OpenTopography...")

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

## 4. Explore Catalog Metadata & Interactive Leaflet Overlay

The search stage generates three primary tracking documents inside `catalog/`:
- `manifest.json`: Full master metadata database.
- `catalog.gpkg`: Vector layer with polygon boundaries of each acquisition.
- `catalog.csv`: Summary table for quick tabular inspection.

```python
# 1. Tabular Summary Table
catalog_csv = workspace_dir / "catalog" / "catalog.csv"
catalog_df = pd.read_csv(catalog_csv)
print("Discovered LiDAR Acquisitions (Top 5):")
display(catalog_df[["Provider", "Name", "Date", "PointDensity", "Area_km2", "Estimated_GB"]].head())

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

---

## 5. Advanced Search Filters (Name, Chronology, Density, Provider)

`als-finder` supports powerful filtering flags to isolate specific acquisitions before any downloading begins.

### 5.1 Filtering by Dataset Name (`--name`)

Filter by exact name, wildcard string (`*`), or regular expression (prefixed with `~`):

```bash
# Exact Name
als-finder search --roi ./ltbmu_boundary.gpkg --name "CA_SierraNevada_5_2022" --workspace ./demo_workspace/

# Wildcard String
als-finder search --roi ./ltbmu_boundary.gpkg --name "*Tahoe*" --workspace ./demo_workspace/

# Python Regular Expression
als-finder search --roi ./ltbmu_boundary.gpkg --name "~^CA_Sierra.*" --workspace ./demo_workspace/
```

### Python Execution:
```python
# Example A: Exact Name
print("--- Filtering by Exact Name ---")
cmd_name_exact = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--name", "CA_SierraNevada_5_2022",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_name_exact, capture_output=True, text=True).stdout)

# Example B: Wildcard
print("--- Filtering by Wildcard (*Tahoe*) ---")
cmd_name_wildcard = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--name", "*Tahoe*",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_name_wildcard, capture_output=True, text=True).stdout)

# Example C: Python Regular Expression (~^CA_Sierra.*)
print("--- Filtering by Regex (~^CA_Sierra.*) ---")
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

```bash
# Open-ended Start Date (Acquisitions >= 2020-01-01)
als-finder search --roi ./ltbmu_boundary.gpkg --date 2020-01-01/ --workspace ./demo_workspace/

# Bounded Historical Window (2015-01-01 to 2019-12-31)
als-finder search --roi ./ltbmu_boundary.gpkg --date 2015-01-01/2019-12-31 --workspace ./demo_workspace/
```

### Python Execution:
```python
# Example A: Open-ended Start Date (Acquisitions >= 2020-01-01)
print("--- Filtering by Start Date (2020-01-01/) ---")
cmd_date_open = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--date", "2020-01-01/",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_date_open, capture_output=True, text=True).stdout)

# Example B: Bounded Historical Window (2015-01-01 to 2019-12-31)
print("--- Filtering by Date Range (2015-01-01 to 2019-12-31) ---")
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

```bash
# USGS QL1 Quality Level (>= 8.0 pts/m2)
als-finder search --roi ./ltbmu_boundary.gpkg --density QL1 --workspace ./demo_workspace/

# Numeric Density Range (2.0 to 10.0 pts/m2)
als-finder search --roi ./ltbmu_boundary.gpkg --density 2/10 --workspace ./demo_workspace/
```

### Python Execution:
```python
# Example A: USGS QL1 Quality Level (>= 8.0 pts/m2)
print("--- Filtering by Quality Level (QL1) ---")
cmd_density_ql1 = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--density", "QL1",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_density_ql1, capture_output=True, text=True).stdout)

# Example B: Numeric Density Range (2.0 to 10.0 pts/m2)
print("--- Filtering by Numeric Density Range (2/10 pts/m2) ---")
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

```bash
als-finder search --roi ./ltbmu_boundary.gpkg --provider USGS_EPT --workspace ./demo_workspace/
```

### Python Execution:
```python
print("--- Filtering by Provider (USGS_EPT only) ---")
cmd_provider = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", str(roi_path),
    "--provider", "USGS_EPT",
    "--workspace", str(workspace_dir)
]
print(subprocess.run(cmd_provider, capture_output=True, text=True).stdout)
```

---

## 6. Atomic Rollback Updates (`als-finder update`)

The generated `manifest.json` logs your original search parameters. To quickly check upstream federal registries for newly published data in your project area, run `update`.

> [!TIP]
> `als-finder` automatically makes a timestamped backup of your old `manifest.json`, `catalog.csv`, and `catalog.gpkg` before updating, ensuring old references are never lost.

```bash
als-finder update --workspace ./demo_workspace/
```

### Python Execution:
```python
print("Testing atomic catalog update...")
cmd_update = [
    sys.executable, "-m", "als_finder.cli", "update",
    "--workspace", str(workspace_dir)
]
res_update = subprocess.run(cmd_update, capture_output=True, text=True)
print(res_update.stdout)
```

---

## 7. Downloading & Subsetting (Stage 2)

To prevent accidentally downloading terabytes of point cloud data and to support High-Performance Computing (HPC) workflows, `als-finder` decouples search from download:
1. **Dry-Run Matrix Generation**: Running `download` without `--execute` creates `catalog/fetch_array.csv` containing tile URLs, download targets, and estimated sizes.
2. **Physical Execution**: Passing `--execute` streams/downloads the conformed files into a strict `Hive-Partitioned` directory hierarchy (`data/raw/provider=*/dataset=*/`).
3. **Dynamic EPT Spatial Subsetting**: When querying cloud-native EPT sources with a spatial `--roi`, `als-finder` streams only points intersecting your boundary, creating a single conformed spatial subset file (`[dataset]_subset.laz`).

```bash
# Dry-run preview
als-finder download --roi "-119.9915, 38.9285, -119.9885, 38.9315" --name "CA_SierraNevada_5_2022" --workspace ./tiny_subset/

# Physical download execution
als-finder download --roi "-119.9915, 38.9285, -119.9885, 38.9315" --name "CA_SierraNevada_5_2022" --workspace ./tiny_subset/ --execute
```

### Python Execution:
```python
# Define a small micro-bounding box near Lake Tahoe for safe, rapid physical download testing
micro_roi = "-119.9915, 38.9285, -119.9885, 38.9315"
micro_workspace = Path("./tiny_subset").resolve()
micro_workspace.mkdir(parents=True, exist_ok=True)

# Step 7.1: Dry-Run Search and Fetch Matrix Generation
print("--- 7.1 Dry-Run Fetch Array Generation ---")
cmd_search_micro = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", micro_roi,
    "--name", "CA_SierraNevada_5_2022",
    "--workspace", str(micro_workspace)
]
subprocess.run(cmd_search_micro)

cmd_dry_run = [
    sys.executable, "-m", "als_finder.cli", "download",
    "--roi", micro_roi,
    "--name", "CA_SierraNevada_5_2022",
    "--workspace", str(micro_workspace)
]
res_dry = subprocess.run(cmd_dry_run, capture_output=True, text=True)
print(res_dry.stdout)

# Step 7.2: Physical Download Execution
print("--- 7.2 Physical Download Execution (--execute) ---")
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

## 8. Normalization & Standardization (Stage 3)

Raw LiDAR point clouds from different federal programs suffer from:
- **Coordinate Reference System (CRS) Discrepancies**: Mixing UTM zones, State Planes, or WGS84.
- **Taxonomic Inconsistencies**: Non-standard ASPRS class mappings across vendors.
- **Elevation vs. Vegetation Height**: Raw data only stores absolute elevation ($Z$), requiring digital terrain subtraction to compute true canopy height.

`als-finder standardize` harmonizes these raw downloads:
1. **Format Upgrade**: Converts point clouds to Cloud-Optimized Point Clouds (`.copc.laz`).
2. **CRS Reprojection**: Harmonizes coordinates into Web Mercator (`EPSG:3857`), target EPSG, or `auto-utm-centroid`.
3. **Taxonomic Standardization**: Wipes vendor noise and conforms bare earth (Class 2) and vegetation classes.
4. **Dynamic Sub-Tiling & RAM Safety**: Automatically subdivides dense tiles on `MemoryError` and clamps thread allocations.

```bash
als-finder standardize --workspace ./tiny_subset/
```

### Python Execution:
```python
print("Executing Standardization Engine...")

cmd_standardize = [
    sys.executable, "-m", "als_finder.cli", "standardize",
    "--workspace", str(micro_workspace)
]
res_std = subprocess.run(cmd_standardize, capture_output=True, text=True)
print(res_std.stdout)

std_copc_files = list(micro_workspace.glob("data/standardized/**/*.copc.laz"))
print(f"\n✓ Standardized COPC Files: {len(std_copc_files)} file(s)")
for p in std_copc_files:
    size_mb = p.stat().st_size / (1024 * 1024)
    print(f"  {p.relative_to(micro_workspace)} ({size_mb:.2f} MB)")
```

---

## 9. SpatioTemporal Asset Catalogs (Stage 4: `--stac`)

Appending `--stac` generates an OGC-compliant `PySTAC` catalog hierarchy (`catalog/stac/catalog.json`).
Each COPC point cloud becomes a searchable STAC Item with exact 3D bounding boxes, acquisition timestamps, and relative asset references.

```bash
als-finder standardize --workspace ./tiny_subset/ --stac
```

### Python Query:
```python
print("Generating OGC STAC Catalog Hierarchy...")

cmd_stac = [
    sys.executable, "-m", "als_finder.cli", "standardize",
    "--workspace", str(micro_workspace),
    "--stac"
]
subprocess.run(cmd_stac)

stac_root = micro_workspace / "catalog" / "stac" / "catalog.json"
assert stac_root.exists(), "STAC catalog generation failed!"

# Inspect STAC catalog using PySTAC
stac_cat = pystac.Catalog.from_file(str(stac_root))
print(f"\n✓ STAC Catalog ID:          {stac_cat.id}")
print(f"✓ STAC Catalog Title:       {stac_cat.title}")
print(f"✓ STAC Catalog Description: {stac_cat.description}")

print("\nIndexed STAC Items:")
for item in stac_cat.get_all_items():
    print(f"  • Item ID:          {item.id}")
    print(f"    Bounding Box:     {item.bbox}")
    print(f"    Acquisition Date: {item.datetime}")
    if "data" in item.assets:
        print(f"    Asset HREF:       {item.assets['data'].href}")
```

---

## 10. Visual QA/QC Quicklooks (Stage 5: `--quicklook`)

Appending `--quicklook` generates 2D preview images using tiered resolution streaming without downloading the entire point cloud:
1. **DEM Hillshade**: Shaded physical relief of the bare earth terrain (Class 2).
2. **Canopy Height Model (CHM)**: Color-relief tree canopy height map computed via `filters.hag_nn`.
3. **HTML Master Index**: Interactive side-by-side preview gallery saved to `catalog/quicklooks_index.html`.

```bash
als-finder standardize --workspace ./tiny_subset/ --quicklook
```

### Python Execution:
```python
print("Generating QA/QC Visual Quicklooks...")

cmd_quicklook = [
    sys.executable, "-m", "als_finder.cli", "standardize",
    "--workspace", str(micro_workspace),
    "--quicklook"
]
subprocess.run(cmd_quicklook)

quicklook_pngs = list(micro_workspace.glob("data/quicklooks/**/*.png"))
print(f"\n✓ Generated Quicklook Images: {len(quicklook_pngs)} image(s)")
for p in quicklook_pngs:
    print(f"  • {p.name} ({p.stat().st_size / 1024:.1f} KB)")

# Display preview renders in Python if matplotlib is available
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

if quicklook_pngs:
    fig, axes = plt.subplots(1, min(len(quicklook_pngs), 2), figsize=(14, 6))
    if not isinstance(axes, (list, tuple)) and len(quicklook_pngs) == 1:
        axes = [axes]
    for ax, p in zip(axes, quicklook_pngs[:2]):
        img = mpimg.imread(str(p))
        ax.imshow(img)
        ax.set_title(p.name, fontsize=11, fontweight="bold")
        ax.axis("off")
    plt.tight_layout()
    plt.show()
```

---

## 11. The Mega-Command (End-to-End Execution)

Once you have finalized your search parameters and target `--roi`, you can chain the entire lifecycle—from federated discovery to raw subsetting, format standardization, STAC indexing, and Quicklook generation—into a single uninterrupted command:

```bash
als-finder download \
    --roi "-119.9915, 38.9285, -119.9885, 38.9315" \
    --name "CA_SierraNevada_5_2022" \
    --workspace ./mega_workspace/ \
    --execute \
    --standardize \
    --stac \
    --quicklook
```

### Python Execution:
```python
mega_workspace = Path("./mega_demo_workspace").resolve()

cmd_mega = [
    sys.executable, "-m", "als_finder.cli", "download",
    "--roi", "-119.9915, 38.9285, -119.9885, 38.9315",
    "--name", "CA_SierraNevada_5_2022",
    "--workspace", str(mega_workspace),
    "--execute",
    "--standardize",
    "--stac",
    "--quicklook"
]

print("Executing Mega-Command end-to-end...")
res_mega = subprocess.run(cmd_mega, capture_output=True, text=True)
print(res_mega.stdout)
print("✓ Mega-Command completed successfully!")
```

---

## Summary & Next Steps

You have completed the full `als-finder` discovery, standardization, and indexing workflow:
1. **Federated Discovery**: Queried multi-agency registries with zero upfront data footprint.
2. **Interactive Leaflet Mapping**: Visualized project boundaries and coverage maps.
3. **Controlled Subsetting**: Previewed download arrays and fetched spatial subsets.
4. **Standardization Engine**: Harmonized CRS, ASPRS classes, and created conformed COPC files.
5. **OGC STAC Catalogs**: Indexed point clouds into a standards-compliant metadata hierarchy.
6. **Visual Quicklooks**: Created 2D DEM Hillshades and Canopy Height Models.
7. **End-to-End Automation**: Executed the entire pipeline in a single Mega-Command.
