# Tutorial 00: Environment Installation & Setup

Welcome to **Tutorial 00** of `als-finder`. This guide walks through setting up your local computer, lab server, or cluster environment.

---

## 1. Local Installation with Conda

Because `als-finder` uses spatial and point cloud libraries (PDAL, GDAL, GEOS), we recommend using Conda:

```bash
# 1. Create a fresh environment with spatial dependencies
conda create -n als-finder -c conda-forge python=3.11 geopandas pdal python-pdal pystac stac-validator psutil shapely pyproj tqdm pyogrio requests click python-dotenv laspy -y

# 2. Activate the environment
conda activate als-finder

# 3. Install als-finder
pip install git+https://github.com/cms-2024-hudak/als-finder.git
```

---

## 2. Supported Archives & Authentication

`als-finder` federates search and retrieval across **6 major public LiDAR repositories**:

| Provider Registry | Flag | Coverage / Focus | Primary Format | Auth Required? |
| :--- | :--- | :--- | :--- | :--- |
| **USGS 3DEP** | `USGS_EPT` | Continental US & Alaska | Cloud-Native EPT / COPC | **No** (Open Access) |
| **NOAA Digital Coast** | `NOAA_STAC` | US Coastal Zones & Great Lakes | Cloud STAC / LAZ | **No** (Open Access) |
| **NASA G-LiHT** | `NASA_GLIHT` | NASA Ecosystem & Forestry Transects | Standard LAS / LAZ | **No** (Open Access) |
| **OpenTopography** | `OpenTopography`| Academic, State & High-Res Surveys | LAZ / Point Cloud Archives | **Free API Key** |
| **NEON AOP** | `NEON` | Ecological Observatory Core Sites | Discrete Return LAZ | **Optional Token** (Higher rate limits) |
| **NASA Earthdata** | `Earthdata` | NASA Carbon Monitoring System (CMS) | Standard LAZ / NetCDF | **Free Earthdata Token** |

### API Keys & Credentials (Optional)
For the archives requiring free registration, you can supply your keys via flags or store them in a local `.env` file:

- **OpenTopography**: Register at [OpenTopography.org](https://opentopography.org) -> *My Account* -> *Request an API Key*. Pass via `--ot-key KEY` or `OPENTOPOGRAPHY_API_KEY=KEY` in `.env`.
- **NASA Earthdata**: Register at [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov) -> *Generate Token*. Pass via `--earthdata-token TOKEN` or `EARTHDATA_TOKEN=TOKEN` in `.env`.
- **NEON AOP**: Register at [data.neonscience.org](https://data.neonscience.org) -> *My Account* -> *API Tokens*. Pass via `--neon-key KEY` or `NEON_API_KEY=KEY` in `.env`.

---

## 3. Verify Installation

Confirm that the tool is installed and running:

```bash
als-finder --version
als-finder --help
```

---

### 👉 Next Step
Proceed to [Tutorial 01: Finding LiDAR Data Across Repositories](./01_basic_discovery.md) to search for data over your study area.
