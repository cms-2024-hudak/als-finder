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

## ⚡ Usage & Full Tutorial

`als-finder` is architected around a **Workspace Paradigm**. Instead of juggling multiple disparate output flags, you simply define your geometry and the destination folder. The software mathematically queries all indices, explicitly deduplicates inputs, and constructs a secure GeoPackage directory structure automatically.

### 1. The Base Execution (All Providers & Dates)
The simplest way to discover LiDAR is dropping an Area-of-Interest (ROI) and a target `workspace` isolated natively on your drive. An example boundary (`ltbmu_boundary.gpkg`) is explicitly bundled natively with all distributions (pip, conda, docker, git) so you can directly reproduce this tutorial locally:

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --workspace ./my_lidar_project/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.0800 |    5849.29 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
 | OpenTopography  | USFS Freds Fire Lidar, CA 2015         | 2022-06-07   |     150.04 |  31.3700 |     641.96 |
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
 | USGS_EPT        | CA_UpperSouthAmerican_Eldorado_2019    | 2019-??-??   |    2075.29 |  43.1600 |    6454.20 |
 | OpenTopography  | Paleo-Outburst Floods in the Truckee R | 2019-11-06   |       5.71 |   8.4000 |      91.21 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9452               | 2019-10-21   |    2075.29 |  10.4100 |   26768.13 |
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9036               | 2018-07-07   |        N/A |      N/A |  159752.00 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9067               | 2018-07-07   |     723.53 |   1.2600 |   77212.96 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9269               | 2018-01-22   |      40.74 |   0.0300 |  182391.32 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | OpenTopography  | Walker Fault System, Nevada, 2015      | 2017-07-28   |      35.77 |   7.2700 |     660.41 |
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
 | NOAA_STAC       | DigitalCoast_DAV:id_8979               | 2017-03-03   |       2.94 |   0.0033 |  120829.31 |
 | NOAA_STAC       | DigitalCoast_DAV:id_6259               | 2016-04-28   |     233.77 |   0.0300 | 1135103.73 |
 | NOAA_STAC       | DigitalCoast_DAV:id_5022               | 2015-06-19   |      63.84 |   0.0200 |  363554.90 |
 | NOAA_STAC       | DigitalCoast_DAV:id_2612               | 2013-10-30   |     151.38 |   0.0300 |  698668.47 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
 | OpenTopography  | Lake Tahoe Basin Lidar                 | 2011-03-01   |     184.96 |  13.2000 |    1880.65 |
 | NOAA_STAC       | DigitalCoast_DAV:id_1124               | 2009-09-01   |     141.08 |   0.0300 |  687536.10 |
 | NOAA_STAC       | DigitalCoast_DAV:id_4                  | 1998-04-08   |       2.31 |   0.0003 | 1038061.18 |
 | NOAA_STAC       | DigitalCoast_DAV:id_3                  | 1997-10-12   |       0.64 |   0.0001 | 1001673.78 |
=================================================================================================================
 TOTAL DATASETS: 24 | ESTIMATED PAYLOAD: 10463.93 GB 
=================================================================================================================
```
*(Notice the `NOAA_STAC id_9036` footprint. If a dataset is cataloged but physically `404` deleted internally off AWS S3 by NOAA, `als-finder` dynamically falls back to a secure `N/A` without catastrophically crashing the orchestration pipeline).*

### 2. Filtering by Dataset Name (`--name`)
If you specifically know the title format of your target distributions, you can aggressively intercept queries before discovery utilizing wildcards `*`, exact phrases, or fully-compiled Regular Expressions (prefixed with `~`).

#### Finding Names via Wildcard Strings
```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --name "*Tahoe*" --workspace ./tahoe_wildcards/
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
 TOTAL DATASETS: 2 | ESTIMATED PAYLOAD: 403.57 GB 
=================================================================================================================
```

#### Finding Names via Explicit Regex
Prefix the query mathematically with a tilde `~` to securely compile advanced Python regex matchers (e.g. isolating exact `CA_Sierra` string structures):
```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --name "~^CA_Sierra.*" --workspace ./sierra_regex/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.0800 |    5849.29 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
=================================================================================================================
 TOTAL DATASETS: 3 | ESTIMATED PAYLOAD: 3688.28 GB 
=================================================================================================================
```

### 3. Filtering by Chronology

#### Defining a Hard Start Date (`--start-date`)
If you only need modern datasets acquired *after* a specific project mapping date, isolate the bounds strictly mathematically:

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --start-date 2020-01-01 --workspace ./recent_lidar/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.0800 |    5849.29 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
 | OpenTopography  | USFS Freds Fire Lidar, CA 2015         | 2022-06-07   |     150.04 |  31.3700 |     641.96 |
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
=================================================================================================================
 TOTAL DATASETS: 5 | ESTIMATED PAYLOAD: 4271.48 GB 
=================================================================================================================
```

#### Defining a Temporal Range (`--start-date` & `--end-date`)
You can explicitly isolate historical windows (e.g., exclusively target point clouds mapping a specific 5-year observation cycle):

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --start-date 2015-01-01 --end-date 2019-12-31 --workspace ./historic_lidar/
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
 | NOAA_STAC       | DigitalCoast_DAV:id_9452               | 2019-10-21   |    2075.29 |  10.4100 |   26768.13 |
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9067               | 2018-07-07   |     723.53 |   1.2600 |   77212.96 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9269               | 2018-01-22   |      40.74 |   0.0300 |  182391.32 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | OpenTopography  | Walker Fault System, Nevada, 2015      | 2017-07-28   |      35.77 |   7.2700 |     660.41 |
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
 | NOAA_STAC       | DigitalCoast_DAV:id_8979               | 2017-03-03   |       2.94 |   0.0033 |  120829.31 |
 | NOAA_STAC       | DigitalCoast_DAV:id_6259               | 2016-04-28   |     233.77 |   0.0300 | 1135103.73 |
 | NOAA_STAC       | DigitalCoast_DAV:id_5022               | 2015-06-19   |      63.84 |   0.0200 |  363554.90 |
=================================================================================================================
 TOTAL DATASETS: 12 | ESTIMATED PAYLOAD: 6270.20 GB 
=================================================================================================================
```

### 4. Filtering by Point Density & Quality Level (`--density`)
You can natively isolate datasets bounded by mathematical spatial resolutions. `als-finder` supports both raw point density bounds (`pts/m2`) or explicit **USGS 3DEP Topographic Quality Levels (QL0-QL3)**.

#### Filtering via USGS Topographic Quality Level (`--ql`)
If you require strict federal fidelity (e.g., `QL1` representing `≥8.0 pts/m²`):

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --density QL1 --workspace ./high_res/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.0800 |    5849.29 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
 | OpenTopography  | USFS Freds Fire Lidar, CA 2015         | 2022-06-07   |     150.04 |  31.3700 |     641.96 |
 | USGS_EPT        | CA_UpperSouthAmerican_Eldorado_2019    | 2019-??-??   |    2075.29 |  43.1600 |    6454.20 |
 | OpenTopography  | Paleo-Outburst Floods in the Truckee R | 2019-11-06   |       5.71 |   8.4000 |      91.21 |
 | NOAA_STAC       | DigitalCoast_DAV:id_9452               | 2019-10-21   |    2075.29 |  10.4100 |   26768.13 |
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
 | OpenTopography  | Lake Tahoe Basin Lidar                 | 2011-03-01   |     184.96 |  13.2000 |    1880.65 |
=================================================================================================================
 TOTAL DATASETS: 11 | ESTIMATED PAYLOAD: 9192.89 GB 
=================================================================================================================
```

#### Filtering via Exact Point Density Ranges (`--density`)
You can supply an explicit bounds using a standard ISO-8601 interval vector string (`min/max`):

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --density 2/10 --workspace ./mid_res/
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
 TOTAL DATASETS: 6 | ESTIMATED PAYLOAD: 881.36 GB 
=================================================================================================================
```

### 5. Filtering by Registry (`--provider`)
To exclusively target high-density scientific sets hosted via USGS EPT bounds, supply explicit string overrides:

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --provider usgs --workspace ./usgs_only/
```

**Console Output:**
```text
=================================================================================================================
 LiDAR Data Search Results 
=================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
-----------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.0800 |    5849.29 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
 | USGS_EPT        | CA_UpperSouthAmerican_Eldorado_2019    | 2019-??-??   |    2075.29 |  43.1600 |    6454.20 |
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
=================================================================================================================
 TOTAL DATASETS: 8 | ESTIMATED PAYLOAD: 7028.40 GB 
=================================================================================================================
```

### 6. Updating Catalogs (Atomic Rollbacks)
The generated `manifest.json` permanently logs your original parameters (`roi`, `dates`, `densities`, `providers`). To explicitly query the federal registries for *newly published data* structurally merging onto your bounds later, rely on the implicit sequence:
```bash
als-finder update --workspace ./my_lidar_project/
```
*(Note: To explicitly guard your indexing traces natively, an `update` mathematically generates a historical backup of the old `manifest.json`, `catalog.csv`, and `catalog.gpkg` logically stamped with immutable UTC bounds before overwriting the primary vectors).*

---

## 🏛️ Acknowledgements & Authorship

This software is released under the open-source **MIT License**, with active copyright assignment physically granted to **Jonathan Greenberg**. 

**Project Authors & Contributors:**
* **Jonathan Greenberg** (University of Nevada, Reno): Lead Developer and Core Project Architect.
* **Andrew Hudak** (US Forest Service): Provided critical advisory feedback and domain tracking under joint grant alignment.
* **Antigravity (Google DeepMind)**: Acted as the primary Staff AI Software Engineer physically architecting the pipeline dependencies, cloud-native endpoints, and metadata matrices alongside Jonathan.