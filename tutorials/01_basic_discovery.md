# Tutorial 01: Complete ALS-Finder Discovery, Inspection & Retrieval Pipeline

Welcome to **ALS-Finder**! This tutorial walks you through the core discovery, spatial filtering, and data retrieval workflow:
1. **Federated Discovery**: Query remote cloud point cloud catalogs across **6 major public registries**: **USGS 3DEP EPT**, **NOAA Coastal STAC**, **OpenTopography**, **NASA G-LiHT**, **NEON AOP**, and **NASA Earthdata (ORNL DAAC)** across flexible spatial, temporal, and point density filters with zero upfront point cloud downloads.
2. **Command-Line First**: Execute searches, filters, and dry-run previews directly from your shell or terminal.
3. **Interactive Leaflet Mapping**: Visualize boundaries, query areas of interest, and overlay discovered LiDAR project footprints with interactive layer controls and tooltips.
4. **Search Filtering**: Filter by exact dataset names, wildcards, regular expressions, historical date ranges, point density (USGS QL levels), and provider registries.
5. **Flexible Additional Metadata**: Inspect 100% of provider-specific and raw survey metadata preserved automatically in `manifest.json` and `catalog.gpkg`.
6. **Atomic Updates**: Sync catalogs with upstream federal registries while maintaining timestamped rollback backups.

---

### 🌟 Architectural Overview & Core Workspace Components

| Workspace Path | Format | Description | Underlying Engine |
| :--- | :--- | :--- | :--- |
| `catalog/manifest.json` | JSON | Master registry tracking federated endpoints, bounding boxes, and project metadata | `als-finder search` |
| `catalog/catalog.gpkg` | GeoPackage | Vector polygon boundaries representing discovered LiDAR project footprints | `als-finder search` |
| `catalog/catalog.csv` | CSV | Human-readable tabular summary of discovered projects, dates, and point densities | `als-finder search` |
| `catalog/fetch_array.csv`| CSV | Dry-run matrix planning physical tile URLs, download targets, and estimated sizes | `als-finder fetch survey` |
| `data/tiles/` | LAZ / COPC | On-demand metric tiles streamed directly from cloud storage | `als-finder fetch tile` |

---

# Part 1: Command-Line Interface (CLI) Quickstart

The fastest way to use `als-finder` is directly from your terminal.

## Step 1: Extract Example Region of Interest (ROI)

`als-finder` bundles a sample vector polygon boundary: the **Lake Tahoe Basin Management Unit (LTBMU)**. Extract it to your current directory:

```bash
als-finder get-example-roi
```

This creates `ltbmu_boundary.gpkg` in your working directory.

---

## Step 2: Run Federated Search (All Repositories)

Search for all LiDAR surveys overlapping the Lake Tahoe ROI and catalog them into `./scratch/tahoe_workspace`:

```bash
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace
```

`als-finder` queries all 6 remote registries in parallel and deduplicates identical datasets by default using an authoritative hierarchy (`USGS` > `NOAA` > `NASA_GLIHT` > `NEON` > `Earthdata` > `OpenTopography`).

This creates three catalog files inside `./scratch/tahoe_workspace/catalog/`:
- `manifest.json`: Complete machine-readable metadata and endpoint catalog.
- `catalog.gpkg`: Vector layer with polygon footprints for every discovered survey.
- `catalog.csv`: Tabular spreadsheet summary.

---

## Step 3: Command-Line Search Filters

You can refine your searches directly using command-line flags:

### 3.1 Filter by Provider Archive (`--provider`)
Isolate a specific archive, or query a subset of providers:

```bash
# Search only USGS 3DEP cloud-native EPT repositories
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace --provider USGS_EPT

# Query both USGS and NOAA
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace --provider USGS_EPT --provider NOAA_STAC
```

### 3.2 Filter by Point Density (`--density`)
Filter by USGS 3DEP Topographic Quality Levels (`QL0` through `QL3`), closed numeric ranges (`2:10`), or open-ended minimum (`2:`) and maximum (`:10`) density bounds (`pts/m²`):

```bash
# Filter for High-Density QL1 data (>= 8.0 pts/m²)
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace --density QL1

# Filter for closed density range between 2.0 and 10.0 pts/m²
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace --density 2:10

# Filter with minimum density ONLY (>= 2.0 pts/m²)
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace --density 2:

# Filter with maximum density ONLY (<= 10.0 pts/m²)
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace --density :10
```

### 3.3 Filter by Historical Date Ranges (`--date`)
Query specific temporal windows using colons (`:`), open-ended bounds (`2020:`), or a single year (`2022`):

```bash
# Data collected between 2018 and 2022
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace --date 2018-01-01:2022-12-31

# All data collected since 2020 (open-ended)
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace --date 2020:

# All data collected within a single calendar year
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace --date 2022
```

### 3.4 Filter by Dataset Name Pattern (`--name`)
Filter using wildcards or regex substrings:

```bash
als-finder search --roi ltbmu_boundary.gpkg --workspace ./scratch/tahoe_workspace --name "*SierraNevada*"
```

---

## Step 4: Dry-Run Survey Acquisition Matrix

To safely preview physical downloads and remote URLs without pulling gigabytes of point clouds, run `fetch survey` (which is a **dry-run by default**):

```bash
als-finder fetch survey --workspace ./scratch/tahoe_workspace
```

This generates `scratch/tahoe_workspace/catalog/fetch_array.csv`, logging every file URL, target filename, and estimated byte count.

---

## Step 5: Atomic Catalog Updates (`als-finder update`)

To check upstream federal registries for newly published data over your project area, run `update`.
*`als-finder` automatically creates a timestamped backup of your old catalog files before updating, ensuring previous project states can always be rolled back.*

```bash
als-finder workspace update --workspace ./scratch/tahoe_workspace
```

---

# Part 2: Python Data Inspection & Leaflet Mapping

Now that your catalog is built, you can inspect metadata and visualize coverage interactively in Python or Jupyter.

## Step 6: Load Catalog and Explore Footprints with Leaflet

```python
import json
from pathlib import Path
import geopandas as gpd
import pandas as pd
import folium

workspace_dir = Path("./scratch/tahoe_workspace").resolve()
catalog_csv = workspace_dir / "catalog" / "catalog.csv"
catalog_gpkg = workspace_dir / "catalog" / "catalog.gpkg"
roi_path = Path("ltbmu_boundary.gpkg")

# 1. Tabular Summary
df = pd.read_csv(catalog_csv)
print("\n--- Discovered LiDAR Acquisitions ---")
print(df[["Provider", "Name", "Date", "PointDensity", "AreaSqKm", "SizeMB"]].to_string(index=False))

# 2. Interactive Multi-Layer Leaflet Map
roi_gdf = gpd.read_file(roi_path)
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
coverage_map
```

---

## Step 7: Inspect Additional Metadata & Raw Provider Attributes

`als-finder` preserves 100% of vendor and archive metadata fields in `additional_metadata`:

```python
manifest_path = workspace_dir / "catalog" / "manifest.json"
with open(manifest_path) as f:
    manifest = json.load(f)

for ds in manifest.get("datasets", [])[:3]:
    print("=" * 60)
    print(f"Dataset:  {ds['name']}")
    print(f"Provider: {ds['provider']}")
    print(f"URL:      {ds.get('url')}")
    print(f"Density:  {ds.get('point_density')} pts/m²")
    print("Additional Metadata Keys:")
    extra = ds.get("additional_metadata", {})
    for k, v in list(extra.items())[:5]:
        print(f"  {k}: {v}")
```

---

## Summary & Next Steps

You have completed the discovery phase:
1. **Command-Line First**: Extracted the Lake Tahoe ROI and executed federated searches with CLI flags.
2. **Archival Deduplication**: Automatic prioritization across USGS, NOAA, G-LiHT, NEON, Earthdata, and OpenTopography.
3. **Filtering**: Refined searches by archive, density (QL1), date ranges, and name patterns.
4. **Interactive Mapping**: Visualized spatial boundaries and survey footprints in Leaflet.

👉 **Next Step**: Proceed to [Tutorial 02: Spatial Tiling & Lazy Point Cloud Streaming](./02_spatial_tiling_and_streaming.md) to explore metric spatial grids, pre-flight memory audits, and zero-copy streaming into R `lidR` and PDAL pipelines!
