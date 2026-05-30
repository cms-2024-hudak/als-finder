# als-finder

**A high-performance, cloud-native CLI engine for discovering and downloading raw LiDAR point cloud data across the globe.**

`als-finder` gathers complete acquisition footprints (project boundaries), true WGS84 point densities, and metadata from **USGS**, **NOAA**, and **OpenTopography** into clean `.json` manifests and `QGIS`-ready `.gpkg` tables.

## 📖 Table of Contents
- [🔑 OpenTopography API Key Setup](#-opentopography-api-key-setup)
- [🚀 Installation](#-installation)
- [⚡ Usage & Full Tutorial (Stage 1)](#-usage--full-tutorial)
- [💾 Stage 2: Downloading & Subsetting](#-stage-2-downloading--subsetting)
- [⚠️ Data Processing: Caveats to Raw Downloads](#-data-processing-caveats-to-raw-downloads)
- [🛠️ Stage 3: Normalization & Standardization](#-stage-3-normalization--standardization)
- [🌐 Stage 4: SpatioTemporal Asset Catalogs (`--stac`)](#-stage-4-spatiotemporal-asset-catalogs--stac)
- [📸 Stage 5: Visual QA/QC Quicklooks (`--quicklook`)](#-stage-5-visual-qaqc-quicklooks--quicklook)
- [🏛️ Acknowledgements & Authorship](#-acknowledgements--authorship)

---

## 🔑 OpenTopography API Key Setup
To pull datasets from OpenTopography, you must provide a free authorization token. 
1. Create an account at [OpenTopography.org](https://opentopography.org).
2. Navigate to **MyAccount** -> **Request API Key**.
3. Supply this key to `als-finder` using the `--ot-key` flag during your first search. The engine will transparently cache it into a local `.env` file directly in your active working directory for all future executions:

```bash
# 1. Extract the example ROI to your local directory
als-finder get-example-roi

# 2. Run your search with the key
als-finder search --roi ./ltbmu_boundary.gpkg --ot-key "your_token_here" --workspace ./my_lidar_project/
```

---

## 🚀 Installation

Because `als-finder` relies on advanced spatial libraries (`geopandas`, `shapely`, `pyproj`), distributing it means managing complex C++ dependencies (GDAL and GEOS). 

> [!IMPORTANT]
> **Windows Native (CMD/PowerShell) Users:**
> Do **NOT** attempt to use `pip install als-finder[all]` on native Windows. The C++ dependencies for PDAL and GDAL cannot be easily compiled via Pip on Windows. If you are not using WSL2, you **must** use the **Conda** installation method below, which handles the Windows C++ binaries for you perfectly.

If you attempt a raw `pip install` on Mac or Linux without these underlying C++ compilers pre-installed, Python will throw compiler errors due to missing C++ dependencies. For this reason, we highly recommend **Conda** (for desktop environments) or **Docker/Singularity** (for server and HPC execution).

### 1. Conda (Recommended & Official)
Conda natively handles downloading and compiling the complex C-binaries (GDAL, PDAL) in the background automatically. This is our general recommendation for most scientific desktop users. Since the package is currently run from source, you must clone the repository and use the provided `environment.yml` to create the environment:

```bash
# 1. Clone the repository and navigate into it
git clone https://github.com/cms-2024-hudak/als-finder.git
cd als-finder

# 2. Create the environment from the environment.yml
conda env create -f environment.yml

# 3. Activate the newly created environment
conda activate als-finder
```

### 2. Docker / Singularity (Recommended for Server & HPC Environments)
The absolute safest way to execute spatial code without triggering dependency conflicts on local servers, cloud instances, or high-performance supercomputers is through containers.

**Option A: Pull Pre-Built Image**
```bash
docker pull ghcr.io/cms-2024-hudak/als-finder:latest

# Basic Run (Bypasses OpenTopography)
docker run -v $(pwd):/app/data ghcr.io/cms-2024-hudak/als-finder:latest search --roi "-124,42,-123,43" --workspace /app/data/my_lidar_project/

# Run with OpenTopography API Key enabled
docker run -e OPENTOPOGRAPHY_API_KEY="your_api_key_here" -v $(pwd):/app/data ghcr.io/cms-2024-hudak/als-finder:latest search --roi "-124,42,-123,43" --workspace /app/data/my_lidar_project/
```

**Option B: Singularity / Apptainer Build (For HPCs)**
If you are deploying `als-finder` on an HPC cluster where root privileges are not available to run Docker, you can compile a standard **Singularity Image File (.sif)** directly from our public GitHub Container Registry (GHCR):
```bash
# Pull and build the Singularity image natively
singularity build als-finder.sif docker://ghcr.io/cms-2024-hudak/als-finder:latest

# Execute the container natively on the HPC cluster
singularity run als-finder.sif search --roi "-124,42,-123,43" --workspace ./my_lidar_project
```

**Option C: Build Docker from Source**
If your enterprise firewall blocks GHCR or you are modifying the source code:
```bash
git clone https://github.com/cms-2024-hudak/als-finder.git
cd als-finder
docker build -t als-finder:latest .

# Run with environment variables from a .env file
docker run --env-file .env -v $(pwd):/app/data als-finder:latest search --roi "-124,42,-123,43" --workspace /app/data/my_lidar_project/
```

### 3. Pip (Advanced / System-Level)
> [!WARNING]
> **Important Note for Pip Users**
> While PyPI hosts the `pdal` Python package (which provides the Python bindings), its wheels **do not bundle the core PDAL C++ library**. If you wish to use pure `pip` to install the complete package (including the Stage 3 Normalization engine), you **MUST** pre-install the C++ PDAL binaries on your host operating system. Otherwise, compiling or running the Python `pdal` bindings will fail.

**A. Install System Binaries First**

**Ubuntu/Debian/WSL2:**
```bash
sudo apt-get update
sudo apt-get install -y libpdal-dev pdal
```

**MacOS:**
```bash
brew install pdal
```

**Windows (Native):**
*(Not supported via Pip. Use the Conda installation method above.)*

**B. Install the Python Wrappers**
Once the C++ dependencies are satisfied on your host OS, you can safely install the python wrappers into a clean environment:

```bash
# 1. Create a clean virtual environment sandbox
python3 -m venv .venv

# 2. Activate the environment
source .venv/bin/activate  # On Windows, use `.venv\Scripts\activate`

# 3. Install the complete package with normalization engines
pip install "als-finder[all]"
```

*(Note: If you only need the Stage 1 search engine and do not want to compile C++ binaries, you can run `pip install als-finder` without the `[all]` tag.)*

---

## ⚡ Usage & Full Tutorial

> [!NOTE]
> **Dynamic Outputs:** Because `als-finder` queries live upstream APIs and registries (USGS, NOAA, OpenTopography) which are constantly updated with new LiDAR acquisitions, the exact dataset counts, dates, and sizes shown in the tutorial console outputs below may not perfectly match what you see when you run the commands today.

`als-finder` uses a workspace approach. Instead of managing multiple output flags, you simply define your search criteria and the destination folder. The software queries all indices, deduplicates overlapping datasets, and generates a clean tracking directory automatically.

### 1. The Base Execution (All Providers & Dates)
The easiest way to search for LiDAR is to provide an Area of Interest (ROI) boundary and a target output `workspace`. An example boundary (`ltbmu_boundary.gpkg`) is bundled with the package so you can follow along with this tutorial locally:

```bash
# 1. Extract the natively bundled test polygon to your current directory
als-finder get-example-roi

# 2. Run the search using the newly extracted local file
als-finder search --roi ./ltbmu_boundary.gpkg --workspace ./my_lidar_project/
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
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

*Note on column values:*
* **Date**: If a provider only reports the collection year, missing months or days are displayed as `??` (e.g., `2022-??-??`).
* **Est (GB)**: This is an estimated payload size. Because registries don't always publish exact file sizes, this is approximated using the total project area and point density.
* **pts/m2**: Point density. Depending on the provider, this may be an exact metadata value or an estimated average across the entire project footprint.

### 2. Filtering by Dataset Name (`--name`)
If you know the title of your target dataset, you can filter the search using wildcards `*`, exact names, or regular expressions (prefixed with `~`).

#### Finding Names via Exact String
You can find a specific point cloud acquisition by using its exact title:
```bash
als-finder search --roi ./ltbmu_boundary.gpkg --name "CA_SierraNevada_5_2022" --workspace ./my_lidar_project/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
=================================================================================================================
 TOTAL DATASETS: 1 | ESTIMATED PAYLOAD: 1380.20 GB | QUERY TIME: 13.21s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

#### Finding Names via Wildcard Strings
```bash
als-finder search --roi ./ltbmu_boundary.gpkg --name "*Tahoe*" --workspace ./my_lidar_project/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
 | OpenTopography  | Lake Tahoe Basin Lidar                 | 2011-03-01   |     184.96 |  13.2000 |    1880.65 |
=================================================================================================================
 TOTAL DATASETS: 2 | ESTIMATED PAYLOAD: 403.57 GB | QUERY TIME: 13.98s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

#### Finding Names via Explicit Regex
Prefix the query with a tilde `~` to use a python regular expression (e.g., finding datasets starting with `CA_Sierra`):
```bash
als-finder search --roi ./ltbmu_boundary.gpkg --name "~^CA_Sierra.*" --workspace ./my_lidar_project/
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
=================================================================================================================
 TOTAL DATASETS: 3 | ESTIMATED PAYLOAD: 3688.28 GB | QUERY TIME: 13.32s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

### 3. Filtering by Chronology

#### Defining a Hard Start Date (`--date`)
If you only need modern datasets acquired *after* a specific date, strictly append the terminal bounding slash explicitly leaving the termination threshold open-ended organically:

```bash
als-finder search --roi ./ltbmu_boundary.gpkg --date 2020-01-01/ --workspace ./my_lidar_project/
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
=================================================================================================================
 TOTAL DATASETS: 5 | ESTIMATED PAYLOAD: 4271.49 GB | QUERY TIME: 12.98s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

#### Defining a Hard End Date (`--date`)
If you only need historic acquisitions prior to a specific date, omit the starting date:

```bash
als-finder search --roi ./ltbmu_boundary.gpkg --date /2020-01-01 --workspace ./my_lidar_project/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
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
 TOTAL DATASETS: 10 | ESTIMATED PAYLOAD: 5680.78 GB | QUERY TIME: 12.94s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

#### Defining a Temporal Range (`--date`)
You can also search within specific historical windows (e.g., target point clouds collected during a 5-year span):

```bash
als-finder search --roi ./ltbmu_boundary.gpkg --date 2015-01-01/2019-12-31 --workspace ./my_lidar_project/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_UpperSouthAmerican_Eldorado_2019    | 2019-??-??   |    2075.29 |  43.1600 |    6454.20 |
 | OpenTopography  | Paleo-Outburst Floods in the Truckee R | 2019-11-06   |       5.71 |   8.4000 |      91.21 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9452               | 2019-10-21   |    2075.29 |  46.7700 |    5954.91 |
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9036               | 2018-07-07   |     253.48 |   0.7800 |   43731.68 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | OpenTopography  | Walker Fault System, Nevada, 2015      | 2017-07-28   |      35.77 |   7.2700 |     660.41 |
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
=================================================================================================================
 TOTAL DATASETS: 8 | ESTIMATED PAYLOAD: 5458.85 GB | QUERY TIME: 13.15s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

### 4. Filtering by Point Density & Quality Level (`--density`)
You can filter datasets based on target point densities. `als-finder` supports both numeric point density bounds (`pts/m2`) or USGS 3DEP Topographic Quality Levels (QL0-QL3).

#### Filtering via USGS Topographic Quality Level
If you need a specific USGS Quality Level (e.g., `QL1` which guarantees `≥8.0 pts/m²`):

```bash
als-finder search --roi ./ltbmu_boundary.gpkg --density QL1 --workspace ./my_lidar_project/
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
 | USGS_EPT        | CA_UpperSouthAmerican_Eldorado_2019    | 2019-??-??   |    2075.29 |  43.1600 |    6454.20 |
 | OpenTopography  | Paleo-Outburst Floods in the Truckee R | 2019-11-06   |       5.71 |   8.4000 |      91.21 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9452               | 2019-10-21   |    2075.29 |  46.7700 |    5954.91 |
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
 | OpenTopography  | Lake Tahoe Basin Lidar                 | 2011-03-01   |     184.96 |  13.2000 |    1880.65 |
=================================================================================================================
 TOTAL DATASETS: 11 | ESTIMATED PAYLOAD: 9192.89 GB | QUERY TIME: 12.69s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

#### Filtering via Exact Point Density Ranges (`--density`)
You can isolate structural quality matrices globally cleanly intercepting densities via explicit numeric bounds. In this example, we structurally isolate payloads globally exhibiting exactly between `2.0` and `10.0` points per square meter natively using the slash syntax (`min/max`).

*Just like the `--date` flag, you can dynamically enforce open-ended parameters strictly mapping one-way thresholds (e.g., `2/` isolates datasets exclusively possessing ≥ 2 pts/m2, while `/10` evaluates payloads strictly containing ≤ 10 pts/m2).*

```bash
als-finder search --roi ./ltbmu_boundary.gpkg --density 2/10 --workspace ./my_lidar_project/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
 | OpenTopography  | Paleo-Outburst Floods in the Truckee R | 2019-11-06   |       5.71 |   8.4000 |      91.21 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | OpenTopography  | Walker Fault System, Nevada, 2015      | 2017-07-28   |      35.77 |   7.2700 |     660.41 |
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
=================================================================================================================
 TOTAL DATASETS: 6 | ESTIMATED PAYLOAD: 881.36 GB | QUERY TIME: 12.02s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

### 5. Filtering by Registry (`--provider`)
To only search specific registries, supply the exact provider flags (`USGS_EPT`, `NOAA_STAC`, or `OpenTopography`). These map directly to the formal output Table `Provider` columns.

#### Single Provider
```bash
als-finder search --roi ./ltbmu_boundary.gpkg --provider USGS_EPT --workspace ./my_lidar_project/
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
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
 | USGS_EPT        | CA_UpperSouthAmerican_Eldorado_2019    | 2019-??-??   |    2075.29 |  43.1600 |    6454.20 |
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
=================================================================================================================
 TOTAL DATASETS: 8 | ESTIMATED PAYLOAD: 7028.40 GB | QUERY TIME: 3.06s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

#### Multiple Providers
You can pass the flag multiple times, or use a clean **comma-separated list** to search a specific combination of registries (e.g., pulling only `USGS_EPT` and `OpenTopography`):

```bash
als-finder search --roi ./ltbmu_boundary.gpkg --provider USGS_EPT,OpenTopography --workspace ./my_lidar_project/
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
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | OpenTopography  | Walker Fault System, Nevada, 2015      | 2017-07-28   |      35.77 |   7.2700 |     660.41 |
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
 | OpenTopography  | Lake Tahoe Basin Lidar                 | 2011-03-01   |     184.96 |  13.2000 |    1880.65 |
=================================================================================================================
 TOTAL DATASETS: 13 | ESTIMATED PAYLOAD: 7623.49 GB | QUERY TIME: 8.13s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/my_lidar_project/catalog/manifest.json
=================================================================================================================
```

### 6. Updating Catalogs (Atomic Rollbacks)
The generated `manifest.json` logs your original parameters (`roi`, `dates`, `densities`, `providers`). To quickly check the federal registries for newly published data in your project area, simply run:
```bash
als-finder update --workspace ./my_lidar_project/
```
*(Note: During an `update`, `als-finder` makes a timestamped backup of your old `manifest.json`, `catalog.csv`, and `catalog.gpkg` before pulling new indexing results, ensuring your old references are never lost).*

---

## 💾 Stage 2: Downloading & Subsetting

To prevent accidentally downloading massive datasets and to better support High-Performance Computing (HPC) workflows, `als-finder` separates the "Search" and "Download" phases.

### The Two-Step Safety Pipeline
1. **The Search**: Run `search` to establish a project and locate the metadata records.
2. **The Subsetting Generation**: Run `download`. The pipeline will **never** physically download binary LiDAR data by default. It spatially intersects the target acquisitions against your input `--roi` polygon, generating a tiny list of overlapping `.laz` file URLs mapped to a `fetch_array.csv`. 
3. **Execution**: You can run the download locally by appending the `--execute` flag, or use the generated `.csv` to distribute the download tasks across an HPC cluster.

### 7.1 Generating the Fetch List
Assume you executed a tight search query dropping a bounding box strictly over an area of interest inside the `CA_SierraNevada_5_2022` USGS footprint:

```bash
als-finder search --roi "-119.9915, 38.9285, -119.9885, 38.9315" --name "CA_SierraNevada_5_2022" --workspace ./tiny_subset/
als-finder download --roi "-119.9915, 38.9285, -119.9885, 38.9315" --name "CA_SierraNevada_5_2022" --workspace ./tiny_subset/
```

```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
=================================================================================================================
 TOTAL DATASETS: 1 | ESTIMATED PAYLOAD: 1380.20 GB | QUERY TIME: 8.51s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/tiny_subset/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/tiny_subset/catalog/manifest.json
=================================================================================================================

==================================================================================================
 LiDAR Fetch Array Matrix 
==================================================================================================
 | Provider        | Name                                   |    Tiles |    True Size |   Format |
--------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 |        1 |      0.00 MB |     .laz |
==================================================================================================
 TOTAL ACQUISITIONS: 1 | PHYSICAL TILES: 1 | EXPECTED PAYLOAD: 0.00 MB
--------------------------------------------------------------------------------------------------
 FETCH TARGET URI: tiny_subset/catalog/fetch_array.csv
================================================================================

[NOTICE] Dry-run only. Review the table above, refine your search if necessary, or run the exact same command with the --execute flag to begin physical download.
```

### 7.2 Executing a Local Download (`--execute`)
If you visually verify the tile payload is safe for your local hard drive capacity, you formally pull the arrays into a strict `Hive-Partitioned` database struct:

```bash
als-finder download --roi "-119.9915, 38.9285, -119.9885, 38.9315" --name "CA_SierraNevada_5_2022" --workspace ./tiny_subset/ --execute
```

**Console Output:**
```text
Downloading payloads: 17.7MiB [00:09, 1.96MiB/s]
```

**Resulting Hive Workspace Structure:**
```text
tiny_subset/
├── catalog/
│   ├── catalog.csv
│   ├── catalog.gpkg
│   ├── fetch_array.csv
│   └── manifest.json
└── data/
    └── raw/
        └── provider=USGS_EPT/
            └── dataset=CA_SierraNevada_5_2022/
                └── CA_SierraNevada_5_2022_subset.laz
```

### 💡 Understanding the Download Structure
* **Dynamic EPT Spatial Subsetting (Default for EPT):** When downloading cloud-native datasets (like `USGS_EPT` or `NOAA_STAC` with EPT endpoints) and supplying a spatial `--roi` boundary, `als-finder` does not download thousands of massive, multi-gigabyte source tiles. Instead, it streams only the points intersecting your boundary directly from the cloud bucket, writing a single conformed spatial subset file (`[dataset_name]_subset.laz`) to save time and disk space.
* **Traditional Tile Downloads (OpenTopography / Full Downloads):** If you target providers that distribute traditional static files (like `OpenTopography` ZIP catalogs) or use the `--full` flag to download the entire uncropped acquisition, the directory will instead contain the individual raw tile files downloaded in their original provider-supplied grid tiles (e.g., `tile_1.laz`, `tile_2.laz`, etc.).

---

## ⚠️ Data Processing: Caveats to Raw Downloads

Because `als-finder` pulls data directly from decentralized public repositories (USGS, NOAA, OpenTopography), the raw `.laz` and `.las` files in your `data/raw/` folder are completely unconformed. If you stop at Stage 2, you will encounter severe analytical bottlenecks:

*   **Coordinate Reference Systems (CRS):** USGS data might be in `EPSG:6339` (UTM), while NOAA data might be in `EPSG:4326` (WGS84). You cannot safely merge them.
*   **Classification Constraints (ASPRS):** Different vendors use different classification integer mappings.
*   **Format Bloat:** Some files are uncompressed `.las`, some are legacy `.laz`.

To solve this completely, `als-finder` includes an automated harmonization engine using PDAL.

---

## 🛠️ Stage 3: Normalization & Standardization

The `als-finder standardize` command standardizes your raw downloads into a strictly uniform, analysis-ready format. It executes the following pipeline on every single file in the `data/raw/` directory:

1. **Format Upgrade:** Converts everything to Cloud Optimized Point Cloud (`.copc.laz`) for blazing-fast spatial indexing and tiered resolution rendering.
2. **CRS Reprojection:** Runs in the `EPSG:3857` (Web Mercator) coordinate reference system by default. Standardizing the database on Web Mercator matches the cloud-native default standard for point clouds (used by Entwine/EPT/Hobu/Potree) and guarantees that final COPC files are instantly web-visualizable and uniform. Alternatively, you can preserve the original native projection by passing `--crs native`, explicitly reproject to a specific target projection (e.g. `--crs EPSG:5070`), or dynamically calculate highly accurate local metric UTM zones per acquisition by passing `--crs auto-utm-centroid` (which determines the UTM zone from the intersection centroid of the acquisition boundary and your ROI).
3. **Taxonomic Standardization:** Wipes inconsistent agency/vendor secondary classifications, drops invalid points/noise, and applies a taxonomic conforms filter. By default, it runs in a taxonomic-uniform `vendor` mode, which preserves reliable agency bare-earth (Class 2) and isolated noise (Class 7/18) classifications while mapping all other secondary classes (such as vegetation, buildings, and water) to Class 1 (Unclassified) to achieve absolute taxonomic uniformity across diverse datasets.

```bash
# Standardize using default taxonomic-uniform vendor classification and standard Web Mercator coordinate systems
als-finder standardize --workspace ./tiny_subset/
```

### Spatial Scaling & Resource Safety

To prevent Out-Of-Memory (OOM) crashes in massive datasets, `als-finder` includes:
*   **Dynamic Spatial Sub-Tiling:** If a tile raises a `MemoryError`, the engine dynamically splits the tile into quadrants and processes them recursively.
*   **RAM-Aware Worker Capping:** Automatically scales the number of parallel thread workers using the system's available RAM and the chosen classifier's memory profile.

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

By simply appending the `--stac` flag to your `standardize` command, the engine parses the normalized COPC files and generates formal `PySTAC` JSON Items. These can be dragged and dropped into QGIS or fed into cloud STAC APIs for immediate geographic indexing.

```bash
als-finder standardize --workspace ./tiny_subset/ --stac
```

This populates a new directory natively in your catalog: `tiny_subset/catalog/stac/`.

### Why STAC?
If you download 5,000 LiDAR tiles across 10 years and 8 different providers, manually finding the exact 4 tiles that cover a specific watershed on a specific date is nearly impossible without loading multi-gigabyte point clouds into GIS software. By generating a STAC catalog, `als-finder` creates lightweight JSON files that store the exact 3D bounding box, coordinate system, and acquisition date for every single point cloud, linking them together into a searchable hierarchy.

**1. The QGIS "Drag and Drop" Map Demo:**
You can use the **QGIS STAC API Browser Plugin** and point it to the `catalog/stac/catalog.json` file. QGIS will instantly draw colored boxes over a basemap showing the exact footprint of every single LiDAR tile you downloaded, allowing you to visually browse your local database instantly.

**2. The Zero-Setup Web STAC Browser Demo:**
To browse and visualize a STAC catalog on the web without installing any GIS software or running local servers, you can test our pre-loaded, live demo dataset:
1. Open the public **[Radiant Earth STAC Browser](https://radiantearth.github.io/stac-browser/)** in your web browser.
2. Copy and paste the following pre-hosted catalog URL into the search bar:
   ```text
   https://cms-2024-hudak.github.io/als-finder/demo/catalog/stac/catalog.json
   ```
3. **Explore in 3D:** Click **Browse** to open the catalog. You can zoom in on the Leaflet map to inspect the conformed Sierra Nevada dataset footprint, drill down into the collection item, and click **Open in copc.io** to stream, rotate, and interact with the point cloud natively in full 3D!

**3. The Python Data Science Query:**
You can programmatically query your new local database without needing a SQL server using `pystac`:

```python
import pystac

# Load the local master catalog
catalog = pystac.Catalog.from_file("tiny_subset/catalog/stac/catalog.json")

# Instantly iterate through thousands of LiDAR files locally
for item in catalog.get_all_items():
    print(f"Point Cloud: {item.id}")
    print(f"Bounding Box: {item.bbox}")
    print(f"Acquisition Date: {item.datetime}")
    print(f"File Path: {item.assets['data'].href}")
```

---

## 📸 Stage 5: Visual QA/QC Quicklooks (`--quicklook`)

Appending the `--quicklook` flag generates a preview image of the point cloud. It uses `readers.copc` to stream only the lowest-resolution spatial tiers, generating previews in seconds without downloading the full dataset.

```bash
als-finder standardize --workspace ./tiny_subset/ --quicklook
```

**What it generates:**
1. **Ground Hillshade (DEM):** A shaded physical relief of the bare earth (Class 2).
2. **Canopy Height Model (CHM):** A color-coded canopy height map (Blue=Earth, Green=Low Veg, Red=Tall Canopy) calculated using `filters.hag_nn`.
3. **Master Catalog:** A simple HTML grid saved to `catalog/quicklooks_index.html` displaying side-by-side previews, origin acquisition dates, and physical vs. estimated point densities for every tile.

---

## ⚡ The Mega Command (End-to-End Execution)

If you have already defined your `--roi` and are ready to execute the entire lifecycle from public registry discovery to standard COPC, STAC indexing, and Quicklook generation in a single, uninterrupted end-to-end command, you can chain the pipeline together:

```bash
# Discover, download, standardize, generate STAC metadata, and render quicklook previews in one step
als-finder download --roi "-120.505, 39.015, -120.495, 39.016" --name "CA_SierraNevada_4_2022" --workspace ./my_lidar_project/ --execute --standardize --stac --quicklook
```

*Note: Passing `--execute` and `--standardize` together to the `download` command tells the engine to first discover datasets, construct the spatial `fetch_array.csv`, download the raw binary files, and then immediately transition into format standardization, STAC schema generation, and QA/QC Quicklook image generation natively.*

---

## 🏛️ Acknowledgements & Authorship

This software is released under the open-source **MIT License**. Copyright **Jonathan Greenberg**. 

**Project Authors & Contributors:**
* **Jonathan Greenberg** (University of Nevada, Reno): Lead Developer and Core Project Architect.
* **Andrew Hudak** (US Forest Service): Provided critical advisory feedback and domain tracking under joint grant alignment.
* **Antigravity (Google DeepMind)**: Acted as the primary AI Software Engineer alongside Jonathan.