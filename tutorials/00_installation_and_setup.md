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

## 2. API Keys & Account Setup

Most archives (USGS 3DEP, NASA G-LiHT, NOAA) require no credentials. A few archives require free accounts:

### OpenTopography (Optional)
1. Register for a free account at [OpenTopography.org](https://opentopography.org).
2. Go to **My Account** -> **Request an API Key**.
3. Pass it once via CLI: `als-finder search --roi study_area.geojson --ot-key YOUR_KEY`

### NASA Earthdata (Optional for NASA CMS datasets)
1. Register at [urs.earthdata.nasa.gov](https://urs.earthdata.nasa.gov).
2. Generate a token under the **Generate Token** tab.
3. Pass it once via CLI: `als-finder search --roi study_area.geojson --earthdata-token YOUR_TOKEN`

### NEON AOP (Optional for higher download limits)
1. Register at [data.neonscience.org](https://data.neonscience.org).
2. Generate an API token under **My Account**.
3. Pass it once via CLI: `als-finder search --roi study_area.geojson --neon-key YOUR_KEY`

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
