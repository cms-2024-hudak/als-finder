# als-finder

**A high-performance, cloud-native CLI engine for discovering and downloading raw LiDAR point cloud data across the globe.**

`als-finder` maps complete acquisition footprints (master project boundaries), true WGS84 point densities, and deep semantic narrative descriptions universally from **USGS**, **NOAA**, and **OpenTopography** natively into clean `.json` manifests and `QGIS`-ready `.gpkg` tables.

---

## 🔑 OpenTopography API Key Setup
To pull datasets from OpenTopography, you must provide a free authorization token. 
1. Create an account at [OpenTopography.org](https://opentopography.org).
2. Navigate to **MyAccount** -> **Request API Key**.
3. You can supply this key to `als-finder` in two standard ways:
   - **Environment Variable (All OS)**: Export it directly in your terminal:
     ```bash
     export OPENTOPOGRAPHY_API_KEY="your_token_here"
     ```
   - **Local `.env` File**: Create a `.env` file in the folder where you run the tool:
     ```env
     OPENTOPOGRAPHY_API_KEY=your_token_here
     ```

---

## 🚀 Installation

Because `als-finder` relies on advanced spatial libraries (`geopandas`, `shapely`, `pyproj`), distributing it means managing complex C++ dependencies (GDAL and GEOS). 

If you attempt a raw `pip install` on Windows or Mac without these underlying C++ compilers pre-installed, Python will throw catastrophic compiler errors ("dependency nightmares"). For this reason, we highly recommend **Docker** or **Conda**.

### 1. Docker (Recommended for HPC / Singularity)
The absolute safest way to execute spatial code without triggering dependency conflicts on your local machine:
```bash
docker pull ghcr.io/cms-2024-hudak/als-finder:latest
docker run -v $(pwd):/data ghcr.io/cms-2024-hudak/als-finder search --roi "-124,42,-123,43" -m /data/manifest.json -g /data/catalog.gpkg
```

### 2. Conda (Recommended for Local Dev)
Conda natively handles downloading and compiling the complex C-binaries (GDAL) in the background automatically:
```bash
conda install -c conda-forge als-finder
```

### 3. Pip (Base Python/Linux)
*Note: Ensure you have GDAL and GEOS globally installed on your OS prior to running.*
```bash
pip install als-finder
```

---

## ⚡ Usage

The CLI supports filtering, metadata catalog generation, and direct file downloading natively.

### 1. The Workspace Paradigm (Discovery)
Instead of forcing users to juggle multiple output flags, `als-finder` natively constructs a secure, structured workspace for your project. Simply define your ROI and the target workspace folder:

```bash
als-finder search \
    --roi /path/to/my_roi.geojson \
    --start-date 2015-01-01 \
    --end-date 2023-12-31 \
    --workspace ./my_lidar_project/
```
The script will silently generate a nested `catalog/` directory natively containing `manifest.json`, `catalog.csv`, and a QGIS-ready spatial `catalog.gpkg` index showing the explicit polygonal boundaries of available LiDAR.

### OpenTopography Authentication Validation
`als-finder` natively detects OpenTopography API keys recursively. For maximum organizational security, do not place keys in global folders! Simply drop a `.env` text file containing `OPENTOPOGRAPHY_API_KEY=your_key_here` strictly inside your `./my_lidar_project/` folder. The parser securely loads it only when interacting with that specific workspace automatically.

### 2. Updating Catalogs & Atomic Rollbacks
The generated `manifest.json` permanently logs your original search coordinates and boundaries. To query the federal registries for newly published datasets later, execute:
```bash
als-finder update --workspace ./my_lidar_project/
```
*(Note: To protect your data mathematically, an update physically generates a historical backup of the old catalog uniquely stamped with UTC extraction times before overwriting it natively).*

**Expected Metadata (Catalog & GeoPackage):**
Running the search universally yields standard attributes mapped across all 3 disparate government APIs natively:
| Field | Description |
| :--- | :--- |
| `provider` | The source database (`USGS_EPT`, `NOAA_STAC`, `OpenTopography`). |
| `dataset_id` | The unique identifier string for the acquisition. |
| `geometry` / `bounds` | The mathematically accurate acquisition boundary polygon (WGS84). |
| `area_sqkm` | Geodesic WGS84 native metric area calculation. |
| `date` | Standardized chronological timestamps proactively extracted. |
| `point_count` | Total raw LiDAR points in the acquisition. |
| `point_density` | Points-Per-Square-Meter (mathematically derived). |
| `description` | The deep semantic paragraph describing the original flight/purpose. |
| `url` | The direct cloud-streaming URL (e.g. `ept.json` or Copc link). |

### 2. Downloading LAZ Tiles (Download Mode)
Currently, `als-finder` is architected as a **cloud-native** discovery tool. The URIs it returns (e.g. USGS `ept.json` paths) are designed to be natively streamed over the internet using PDAL pipelines (like in `voxelFuel`) without ever forcing you to physically download terabytes of raw `.laz` data to your hard drive. 

If you explicitly choose to physically download the `.laz` files, you can utilize the download capabilities:
```bash
# Download all valid URLs natively mapped in your JSON catalog into Hive-style structures
als-finder download \
    --manifest ./catalog.json \
    --output-dir ./lidar_acquisitions/
```

---

## 🏛️ Acknowledgements & Authorship

This software is released under the open-source **MIT License**, with active copyright assignment physically granted to **Jonathan Greenberg**. 

**Project Authors & Contributors:**
* **Jonathan Greenberg** (University of Nevada, Reno): Lead Developer and Core Project Architect.
* **Andrew Hudak** (US Forest Service): Provided critical advisory feedback and domain tracking under joint grant alignment.
* **Antigravity (Google DeepMind)**: Acted as the primary Staff AI Software Engineer physically architecting the pipeline dependencies, cloud-native endpoints, and metadata matrices alongside Jonathan.