# ALS-Finder: Advanced Tutorial Reference Archive

This document preserves the complete technical narrative, terminal CLI commands, Python code snippets, and architectural details for advanced pipeline stages (Normalization, STAC, Visual Quicklooks, and Mega-Command Automation) to be resurrected in subsequent tutorial modules (Tutorial 02, 03, etc.).

---

## 🛠️ Stage 3: Normalization & Standardization

The `als-finder standardize` command standardizes raw downloads into a strictly uniform, analysis-ready format. It executes the following pipeline on every single file in the `data/raw/` directory:

1. **Format Upgrade:** Converts everything to Cloud Optimized Point Cloud (`.copc.laz`) for fast spatial indexing and tiered resolution rendering.
2. **CRS Reprojection:** Runs in the `EPSG:3857` (Web Mercator) coordinate reference system by default. Standardizing on Web Mercator matches the cloud-native default standard for point clouds (used by Entwine/EPT/Hobu/Potree) and guarantees that final COPC files are instantly web-visualizable. Alternatively, you can preserve the original native projection by passing `--crs native`, explicitly reproject to a specific target projection (e.g. `--crs EPSG:5070`), or dynamically calculate local metric UTM zones per acquisition by passing `--crs auto-utm-centroid`.
3. **Taxonomic Standardization:** Wipes inconsistent agency/vendor secondary classifications, drops invalid points/noise, and applies a taxonomic conforms filter. By default, it runs in a taxonomic-uniform `vendor` mode, which preserves reliable agency bare-earth (Class 2) and isolated noise (Class 7/18) classifications while mapping all other secondary classes (such as vegetation, buildings, and water) to Class 1 (Unclassified).

### Terminal Command:
```bash
# Standardize using default taxonomic-uniform vendor classification and standard Web Mercator coordinate systems
als-finder standardize --workspace ./tiny_subset/
```

### Python Execution:
```python
import sys
import subprocess
from pathlib import Path

micro_workspace = Path("./tiny_subset").resolve()

cmd_standardize = [
    sys.executable, "-m", "als_finder.cli", "standardize",
    "--workspace", str(micro_workspace)
]
res_std = subprocess.run(cmd_standardize, capture_output=True, text=True)
print(res_std.stdout)

std_copc_files = list(micro_workspace.glob("data/standardized/**/*.copc.laz"))
print(f"✓ Standardized COPC Files: {len(std_copc_files)} file(s)")
```

### Spatial Scaling & Resource Safety:
- **Dynamic Spatial Sub-Tiling:** If a tile raises a `MemoryError`, the engine dynamically splits the tile into quadrants and processes them recursively.
- **RAM-Aware Worker Capping:** Automatically scales the number of parallel thread workers using the system's available RAM and the chosen classifier's memory profile.

**Resulting Hive Workspace Structure:**
```text
tiny_subset/
└── data/
    ├── raw/
    └── standardized/
        └── provider=USGS_EPT/
            └── dataset=CA_SierraNevada_5_2022/
                ├── CA_SierraNevada_5_2022.copc.laz
                └── ... (Uniformly conformed COPCs)
```

---

## 🌐 Stage 4: SpatioTemporal Asset Catalogs (`--stac`)

By appending the `--stac` flag to your `standardize` command, the engine parses the normalized COPC files and generates formal `PySTAC` JSON Items. These can be dragged and dropped into QGIS or fed into cloud STAC APIs for immediate geographic indexing.

### Terminal Command:
```bash
als-finder standardize --workspace ./tiny_subset/ --stac
```

This populates a new directory natively in your catalog: `tiny_subset/catalog/stac/`.

### Why STAC?
If you download 5,000 LiDAR tiles across 10 years and 8 different providers, manually finding the exact tiles that cover a specific watershed on a specific date is nearly impossible without loading multi-gigabyte point clouds into GIS software. By generating a STAC catalog, `als-finder` creates lightweight JSON files that store the exact 3D bounding box, coordinate system, and acquisition date for every single point cloud.

### 1. QGIS "Drag and Drop" Map Demo:
Use the **QGIS STAC API Browser Plugin** and point it to the `catalog/stac/catalog.json` file. QGIS will draw colored bounding boxes over a basemap showing the exact footprint of every single LiDAR tile downloaded.

### 2. Zero-Setup Web STAC Browser Demo:
1. Open the public **[Radiant Earth STAC Browser](https://radiantearth.github.io/stac-browser/)**.
2. Copy and paste the pre-hosted catalog URL into the search bar:
   ```text
   https://cms-2024-hudak.github.io/als-finder/demo/catalog/stac/catalog.json
   ```
3. Click **Browse** to inspect the conformed Sierra Nevada dataset footprint and click **Open in copc.io** to interact with the point cloud in full 3D!

### 3. Programmatic Python Query with `pystac`:
```python
import pystac
from pathlib import Path

stac_path = Path("tiny_subset/catalog/stac/catalog.json")
if stac_path.exists():
    catalog = pystac.Catalog.from_file(str(stac_path))
    for item in catalog.get_all_items():
        print(f"Point Cloud: {item.id}")
        print(f"Bounding Box: {item.bbox}")
        print(f"Acquisition Date: {item.datetime}")
        if "data" in item.assets:
            print(f"File Path: {item.assets['data'].href}")
```

---

## 📸 Stage 5: Visual QA/QC Quicklooks (`--quicklook`)

Appending the `--quicklook` flag generates preview images of the point cloud using tiered resolution streaming without downloading the entire dataset.

### Terminal Command:
```bash
als-finder standardize --workspace ./tiny_subset/ --quicklook
```

**Generated Assets:**
1. **Ground Hillshade (DEM):** A shaded physical relief of the bare earth (Class 2).
2. **Canopy Height Model (CHM):** A color-coded canopy height map (Blue=Earth, Green=Low Veg, Red=Tall Canopy) calculated using `filters.hag_nn`.
3. **Master Catalog:** A simple HTML grid saved to `catalog/quicklooks_index.html` displaying side-by-side previews, origin acquisition dates, and point densities for every tile.

### Python Display Snippet:
```python
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from pathlib import Path

quicklook_pngs = list(Path("tiny_subset/data/quicklooks").rglob("*.png"))
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

## ⚡ The Mega-Command (End-to-End Execution)

If you have already defined your `--roi` and are ready to execute the entire lifecycle from public registry discovery to standard COPC, STAC indexing, and Quicklook generation in a single, uninterrupted end-to-end command:

### Terminal Command:
```bash
als-finder download \
    --roi "-120.505, 39.015, -120.495, 39.016" \
    --name "CA_SierraNevada_4_2022" \
    --workspace ./my_lidar_project/ \
    --execute \
    --standardize \
    --stac \
    --quicklook
```

### Python Execution:
```python
import sys
import subprocess
from pathlib import Path

cmd_mega = [
    sys.executable, "-m", "als_finder.cli", "download",
    "--roi", "-120.505, 39.015, -120.495, 39.016",
    "--name", "CA_SierraNevada_4_2022",
    "--workspace", "./my_lidar_project/",
    "--execute",
    "--standardize",
    "--stac",
    "--quicklook"
]

res_mega = subprocess.run(cmd_mega, capture_output=True, text=True)
print(res_mega.stdout)
```
