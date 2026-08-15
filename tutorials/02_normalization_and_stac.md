# Tutorial 02: Point Cloud Normalization & OGC STAC Catalogs

Welcome to **Tutorial 02** of the `als-finder` series! In this module, you will learn how to:
1. Understand raw LiDAR format inconsistencies (heterogeneous taxonomy, missing ground classification, variable CRS).
2. Execute the PDAL normalization engine: apply **SMRF** (Simple Morphological Filter) and **HAG** (Height Above Ground).
3. Export standardized **Cloud-Optimized Point Clouds** (`.copc.laz`).
4. Generate and validate an **OGC SpatioTemporal Asset Catalog (STAC)** (`catalog/stac/catalog.json`).
5. Render 2D QA/QC Visual Quicklooks (DEM Hillshades + Canopy Height Models).

---

## 1. Why Normalization is Required

Raw LiDAR point clouds acquired across different federal programs often suffer from:
- **Non-standardized ASPRS classification**: Points classified inconsistently by vendors.
- **Elevation vs. Height**: Raw data only stores absolute elevation ($Z$), requiring digital terrain subtraction to determine true vegetation height.
- **Non-cloud-native storage**: Standard `.las`/`.laz` files cannot be dynamically subsetted via HTTP byte-ranges without downloading the entire multi-gigabyte file.

`als-finder standardize` harmonizes these differences into a single, standardized pipeline:

```bash
als-finder standardize --help
```

---

## 2. Defining a Small Test Sub-Region

To quickly test the normalization pipeline without downloading large volumes, let's define a micro-bounding box (e.g. 200m x 200m near Lake Tahoe):

```python
import geopandas as gpd
from shapely.geometry import box

# Create a small micro-bounding box in WGS84
micro_box = box(-120.02, 38.93, -120.00, 38.95)
micro_gdf = gpd.GeoDataFrame({"id": [1]}, geometry=[micro_box], crs="EPSG:4326")
micro_gdf.to_file("micro_roi.geojson", driver="GeoJSON")

print("Micro ROI created:", micro_box.bounds)
```

---

## 3. Executing Standardization with STAC & Quicklooks

Let's execute the complete discovery, download, SMRF ground classification, and STAC generation pipeline:

```bash
als-finder download \
    --workspace ./tahoe_standardized_demo/ \
    --roi ./micro_roi.geojson \
    --execute \
    --standardize \
    --crs "EPSG:32610" \
    --stac \
    --quicklook
```

---

## 4. Inspecting the Generated OGC STAC Hierarchy

The standardization engine constructs a self-contained **PySTAC** catalog with normalized relative links and validated OGC metadata schemas.

```python
import pystac
from pathlib import Path

stac_path = Path("tahoe_standardized_demo/catalog/stac/catalog.json")
if stac_path.exists():
    cat = pystac.read_file(str(stac_path))
    print(f"Catalog Title: {cat.title}")
    print(f"Catalog Description: {cat.description}")
    print(f"Child Collections: {[c.id for c in cat.get_children()]}")
```

---

## 5. Visualizing 2D QA/QC Quicklook Previews

`als-finder` automatically generates 2D DEM Hillshade and Canopy Height Model (CHM) color-relief PNG previews to spot-check for classification or projection artifacts without 3D GIS software:

```python
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

quicklook_pngs = list(Path("tahoe_standardized_demo/data/quicklooks").rglob("*.png"))
print(f"Found {len(quicklook_pngs)} preview renders.")

if quicklook_pngs:
    fig, axes = plt.subplots(1, min(len(quicklook_pngs), 2), figsize=(14, 7))
    if not isinstance(axes, (list, tuple)) and len(quicklook_pngs) == 1:
        axes = [axes]
    for ax, p in zip(axes, quicklook_pngs[:2]):
        img = mpimg.imread(str(p))
        ax.imshow(img)
        ax.set_title(p.name, fontsize=10)
        ax.axis("off")
    plt.tight_layout()
    plt.show()
```

---

### 👉 Next Step
Open [03_spatial_tiling_and_streaming.md](file:///mnt/c/Users/gears/git/als-finder/tutorials/03_spatial_tiling_and_streaming.md) (or `03_spatial_tiling_and_streaming.ipynb`) to explore metric grid generation and zero-copy on-demand tile streaming!
