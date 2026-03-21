# als-finder

**A high-performance, cloud-native CLI engine for discovering and downloading raw LiDAR point cloud data across the globe.**

`als-finder` gathers complete acquisition footprints (project boundaries), true WGS84 point densities, and metadata from **USGS**, **NOAA**, and **OpenTopography** into clean `.json` manifests and `QGIS`-ready `.gpkg` tables.

---

## 🔑 OpenTopography API Key Setup
To pull datasets from OpenTopography, you must provide a free authorization token. 
1. Create an account at [OpenTopography.org](https://opentopography.org).
2. Navigate to **MyAccount** -> **Request API Key**.
3. Supply this key to `als-finder` using the `--ot-key` flag during your first search. The engine will transparently cache it into a local `.env` file directly in your active working directory for all future executions:

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --ot-key "your_token_here" --workspace ./my_lidar_project/
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

`als-finder` uses a workspace approach. Instead of managing multiple output flags, you simply define your search criteria and the destination folder. The software queries all indices, deduplicates overlapping datasets, and generates a clean tracking directory automatically.

### 1. The Base Execution (All Providers & Dates)
The easiest way to search for LiDAR is to provide an Area of Interest (ROI) boundary and a target output `workspace`. An example boundary (`ltbmu_boundary.gpkg`) is bundled with the package so you can follow along with this tutorial locally:

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --workspace ./my_lidar_project/
```

**Console Output:**
```text
=======================================================================================================================================
 LiDAR Data Search Results 
=======================================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
---------------------------------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.0800 |    5849.29 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
 | OpenTopography  | USFS Freds Fire Lidar, CA 2015         | 2022-06-07   |     150.04 |  31.3700 |     641.96 |
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
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
 | NOAA_STAC       | DigitalCoast_DAV:id_2612               | 2013-10-30   |     151.38 |   0.0300 |  698668.47 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
 | OpenTopography  | Lake Tahoe Basin Lidar                 | 2011-03-01   |     184.96 |  13.2000 |    1880.65 |
 | NOAA_STAC       | DigitalCoast_DAV:id_1124               | 2009-09-01   |     141.08 |   0.0300 |  687536.10 |
 | NOAA_STAC       | DigitalCoast_DAV:id_4                  | 1998-04-08   |       2.31 |   0.0003 | 1038061.18 |
 | NOAA_STAC       | DigitalCoast_DAV:id_3                  | 1997-10-12   |       0.64 |   0.0001 | 1001673.78 |
=======================================================================================================================================
 TOTAL DATASETS: 23 | ESTIMATED PAYLOAD: 11059.03 GB | QUERY TIME: 13.50s 
---------------------------------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /home/user/my_lidar_project/catalog/catalog.gpkg
 JSON METADATA: /home/user/my_lidar_project/catalog/manifest.json
=======================================================================================================================================
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
als-finder search --roi ./examples/ltbmu_boundary.gpkg --name "CA_SierraNevada_5_2022" --workspace ./exact_sierra/
```

**Console Output:**
```text
=======================================================================================================================================
 LiDAR Data Search Results 
=======================================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
---------------------------------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
=======================================================================================================================================
 TOTAL DATASETS: 1 | ESTIMATED PAYLOAD: 1380.20 GB | QUERY TIME: 3.14s
---------------------------------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /home/user/exact_sierra/catalog/catalog.gpkg
 JSON METADATA: /home/user/exact_sierra/catalog/manifest.json
=======================================================================================================================================
```

#### Finding Names via Wildcard Strings
```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --name "*Tahoe*" --workspace ./tahoe_wildcards/
```

**Console Output:**
```text
=======================================================================================================================================
 LiDAR Data Search Results 
=======================================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
---------------------------------------------------------------------------------------------------------------------------------------
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
 | OpenTopography  | Lake Tahoe Basin Lidar                 | 2011-03-01   |     184.96 |  13.2000 |    1880.65 |
=======================================================================================================================================
 TOTAL DATASETS: 2 | ESTIMATED PAYLOAD: 403.57 GB | QUERY TIME: 4.12s 
---------------------------------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /home/user/tahoe_wildcards/catalog/catalog.gpkg
 JSON METADATA: /home/user/tahoe_wildcards/catalog/manifest.json
=======================================================================================================================================
```

#### Finding Names via Explicit Regex
Prefix the query with a tilde `~` to use a python regular expression (e.g., finding datasets starting with `CA_Sierra`):
```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --name "~^CA_Sierra.*" --workspace ./sierra_regex/
```

**Console Output:**
```text
=======================================================================================================================================
 LiDAR Data Search Results 
=======================================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
---------------------------------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.0800 |    5849.29 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
=======================================================================================================================================
 TOTAL DATASETS: 3 | ESTIMATED PAYLOAD: 3688.28 GB | QUERY TIME: 3.51s
---------------------------------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /home/user/sierra_regex/catalog/catalog.gpkg
 JSON METADATA: /home/user/sierra_regex/catalog/manifest.json
=======================================================================================================================================
```

### 3. Filtering by Chronology

#### Defining a Hard Start Date (`--date`)
If you only need modern datasets acquired *after* a specific date, strictly append the terminal bounding slash explicitly leaving the termination threshold open-ended organically:

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --date 2020-01-01/ --workspace ./recent_lidar/
```

**Console Output:**
```text
=======================================================================================================================================
 LiDAR Data Search Results 
=======================================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
---------------------------------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.0800 |    5849.29 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
 | OpenTopography  | USFS Freds Fire Lidar, CA 2015         | 2022-06-07   |     150.04 |  31.3700 |     641.96 |
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
=======================================================================================================================================
 TOTAL DATASETS: 5 | ESTIMATED PAYLOAD: 4271.48 GB | QUERY TIME: 4.89s
---------------------------------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /home/user/recent_lidar/catalog/catalog.gpkg
 JSON METADATA: /home/user/recent_lidar/catalog/manifest.json
=======================================================================================================================================
```

#### Defining a Hard End Date (`--date`)
If you only need historic acquisitions cleanly evaluated *prior* to a specific threshold, simply prefix the slash naturally dropping the starting bounds organically:

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --date /2020-01-01 --workspace ./historic_lidar/
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
 | NOAA_STAC       | DigitalCoast_DAV:id_2612               | 2013-10-30   |     151.38 |   0.0300 |  698668.47 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
 | OpenTopography  | Lake Tahoe Basin Lidar                 | 2011-03-01   |     184.96 |  13.2000 |    1880.65 |
 | NOAA_STAC       | DigitalCoast_DAV:id_1124               | 2009-09-01   |     141.08 |   0.0300 |  687536.10 |
 | NOAA_STAC       | DigitalCoast_DAV:id_4                  | 1998-04-08   |       2.31 |   0.0003 | 1038061.18 |
 | NOAA_STAC       | DigitalCoast_DAV:id_3                  | 1997-10-12   |       0.64 |   0.0001 | 1001673.78 |
=================================================================================================================
 TOTAL DATASETS: 18 | ESTIMATED PAYLOAD: 6787.54 GB | QUERY TIME: 13.05s 
-----------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /mnt/c/Users/gears/git/als-finder/scratch/historic_lidar/catalog/catalog.gpkg
 JSON METADATA: /mnt/c/Users/gears/git/als-finder/scratch/historic_lidar/catalog/manifest.json
=================================================================================================================
```

#### Defining a Temporal Range (`--date`)
You can also search within specific historical windows (e.g., target point clouds collected during a 5-year span):

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --date 2015-01-01/2019-12-31 --workspace ./historic_lidar/
```

**Console Output:**
```text
=======================================================================================================================================
 LiDAR Data Search Results 
=======================================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
---------------------------------------------------------------------------------------------------------------------------------------
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
=======================================================================================================================================
 TOTAL DATASETS: 12 | ESTIMATED PAYLOAD: 6270.20 GB | QUERY TIME: 4.41s
---------------------------------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /home/user/historic_lidar/catalog/catalog.gpkg
 JSON METADATA: /home/user/historic_lidar/catalog/manifest.json
=======================================================================================================================================
```

### 4. Filtering by Point Density & Quality Level (`--density`)
You can filter datasets based on target point densities. `als-finder` supports both numeric point density bounds (`pts/m2`) or USGS 3DEP Topographic Quality Levels (QL0-QL3).

#### Filtering via USGS Topographic Quality Level
If you need a specific USGS Quality Level (e.g., `QL1` which guarantees `≥8.0 pts/m²`):

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --density QL1 --workspace ./high_res/
```

**Console Output:**
```text
=======================================================================================================================================
 LiDAR Data Search Results 
=======================================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
---------------------------------------------------------------------------------------------------------------------------------------
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
=======================================================================================================================================
 TOTAL DATASETS: 11 | ESTIMATED PAYLOAD: 9192.89 GB | QUERY TIME: 3.98s
---------------------------------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /home/user/high_res/catalog/catalog.gpkg
 JSON METADATA: /home/user/high_res/catalog/manifest.json
=======================================================================================================================================
```

#### Filtering via Exact Point Density Ranges (`--density`)
You can isolate structural quality matrices globally cleanly intercepting densities via explicit numeric bounds. In this example, we structurally isolate payloads globally exhibiting exactly between `2.0` and `10.0` points per square meter natively using the slash syntax (`min/max`).

*Just like the `--date` flag, you can dynamically enforce open-ended parameters strictly mapping one-way thresholds (e.g., `2/` isolates datasets exclusively possessing ≥ 2 pts/m2, while `/10` evaluates payloads strictly containing ≤ 10 pts/m2).*

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --density 2/10 --workspace ./mid_res/
```

**Console Output:**
```text
=======================================================================================================================================
 LiDAR Data Search Results 
=======================================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
---------------------------------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
 | OpenTopography  | Paleo-Outburst Floods in the Truckee R | 2019-11-06   |       5.71 |   8.4000 |      91.21 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | OpenTopography  | Walker Fault System, Nevada, 2015      | 2017-07-28   |      35.77 |   7.2700 |     660.41 |
 | OpenTopography  | 2014 USFS Tahoe National Forest Lidar  | 2017-03-28   |     218.61 |   8.9300 |    3285.73 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
=======================================================================================================================================
 TOTAL DATASETS: 6 | ESTIMATED PAYLOAD: 881.36 GB | QUERY TIME: 4.54s
---------------------------------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /home/user/mid_res/catalog/catalog.gpkg
 JSON METADATA: /home/user/mid_res/catalog/manifest.json
=======================================================================================================================================
```

### 5. Filtering by Registry (`--provider`)
To only search specific registries, supply the short-hand provider flags (`usgs`, `noaa`, or `opentopography`). These map directly to the formal output Table `Provider` columns (`USGS_EPT`, `NOAA_STAC`, `OpenTopography`).

#### Single Provider
```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --provider usgs --workspace ./usgs_only/
```

**Console Output:**
```text
=======================================================================================================================================
 LiDAR Data Search Results 
=======================================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
---------------------------------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.0800 |    5849.29 |
 | USGS_EPT        | CA_SierraNevada_8_2022                 | 2022-??-??   |    1171.62 |  25.1400 |    6255.39 |
 | USGS_EPT        | NV_WestCentralEarthMRI_3_2020          | 2020-??-??   |     433.16 |   5.3400 |   10890.04 |
 | USGS_EPT        | CA_UpperSouthAmerican_Eldorado_2019    | 2019-??-??   |    2075.29 |  43.1600 |    6454.20 |
 | USGS_EPT        | USGS_LPC_CA_NoCAL_Wildfires_B1_2018    | 2018-??-??   |     643.56 |  10.8900 |    7928.51 |
 | USGS_EPT        | USGS_LPC_NV_Reno_Carson_QL1_2017_LAS_2 | 2017-??-??   |     151.15 |   9.5400 |    2126.64 |
 | USGS_EPT        | CA_PlacerCo_2012                       | 2012-??-??   |      36.96 |   3.9500 |    1254.54 |
=======================================================================================================================================
 TOTAL DATASETS: 8 | ESTIMATED PAYLOAD: 7028.40 GB | QUERY TIME: 3.01s
---------------------------------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /home/user/usgs_only/catalog/catalog.gpkg
 JSON METADATA: /home/user/usgs_only/catalog/manifest.json
=======================================================================================================================================
```

#### Multiple Providers
You can pass the flag multiple times to search a specific combination of registries (e.g., pulling only `usgs` and `opentopography`):

```bash
als-finder search --roi ./examples/ltbmu_boundary.gpkg --provider usgs --provider opentopography --workspace ./combo/
```

**Console Output:**
```text
=======================================================================================================================================
 LiDAR Data Search Results 
=======================================================================================================================================
 | Provider        | Name                                   | Date         |   Est (GB) |   pts/m2 |   Area km2 |
---------------------------------------------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 | 2022-??-??   |    1380.20 |  29.1700 |    6349.79 |
 | USGS_EPT        | CA_SierraNevada_6_2022                 | 2022-??-??   |    1136.46 |  26.0800 |    5849.29 |
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
=======================================================================================================================================
 TOTAL DATASETS: 13 | ESTIMATED PAYLOAD: 7623.49 GB | QUERY TIME: 12.81s 
---------------------------------------------------------------------------------------------------------------------------------------
 CATALOG TBL: /home/user/combo/catalog/catalog.gpkg
 JSON METADATA: /home/user/combo/catalog/manifest.json
=======================================================================================================================================
```

### 6. Updating Catalogs (Atomic Rollbacks)
The generated `manifest.json` logs your original parameters (`roi`, `dates`, `densities`, `providers`). To quickly check the federal registries for newly published data in your project area, simply run:
```bash
als-finder update --workspace ./my_lidar_project/
```
*(Note: During an `update`, `als-finder` makes a timestamped backup of your old `manifest.json`, `catalog.csv`, and `catalog.gpkg` before pulling new indexing results, ensuring your old references are never lost).*

---

## 💾 Stage 2: Downloading & Subsetting

To prevent catastrophic hard drive consumption and perfectly align local executions with High-Performance Computing (HPC) workflows, `als-finder` enforces a strict, unbreakable safety barrier between "Search" and "Download".

### The Two-Step Safety Pipeline
1. **The Search**: Run `search` to establish a project and dynamically locate the metadata array.
2. **The Subsetting Generation**: Run `download`. The pipeline will **never** physical download binary LiDAR data by default. It mathematically clips the target acquisitions against your input `--roi` polygon, generating a tiny list of intersecting `.laz` file URLs mapped strictly to a `fetch_array.csv`. 
3. **The Execution**: You explicitly execute the CSV locally by appending the `--execute` flag, or seamlessly feed the `.csv` text list into an HPC scheduler for raw distribution.

### 7.1 Generating the Fetch List
Assume you executed a tight search query dropping a bounding box strictly over an area of interest inside the `CA_SierraNevada_5_2022` USGS footprint:

```bash
als-finder search --roi "-120.01, 39.01, -119.99, 39.02" --name "CA_SierraNevada_5_2022" --workspace ./tiny_subset/
als-finder download --roi "-120.01, 39.01, -119.99, 39.02" --name "CA_SierraNevada_5_2022" --workspace ./tiny_subset/
```

```text
==================================================================================================
 LiDAR Fetch Array Matrix 
==================================================================================================
 | Provider        | Name                                   |    Tiles |    True Size |   Format |
--------------------------------------------------------------------------------------------------
 | USGS_EPT        | CA_SierraNevada_5_2022                 |      107 |     27.14 MB |     .laz |
==================================================================================================
 TOTAL ACQUISITIONS: 1 | PHYSICAL TILES: 107 | EXPECTED PAYLOAD: 27.14 MB
--------------------------------------------------------------------------------------------------
 FETCH TARGET URI: ./tiny_subset/catalog/fetch_array.csv
==================================================================================================
```

### 7.2 Executing a Local Download (`--execute`)
If you visually verify the tile payload is safe for your local hard drive capacity, you formally pull the arrays into a strict `Hive-Partitioned` database struct:

```bash
als-finder download --roi "-120.01, 39.01, -119.99, 39.02" --name "CA_SierraNevada_5_2022" --workspace ./tiny_subset/ --execute
```

**Console Output:**
```text
Executing Mode A/B: Physical Core Download Protocol
Targeting fetch array: tiny_subset/catalog/fetch_array.csv
Verified local workspace capacity: 29.71 GB available.
Physically orchestrating multi-threaded download sequence for 107 nodes...
[SUCCESS] Total Data Block Acquisition completed: 107/107 matrices mapped.
```

**Resulting Hive Workspace Structure:**
```text
tiny_subset/
├── catalog/
│   ├── catalog.gpkg
│   ├── fetch_array.csv
│   └── manifest.json
└── data/
    └── raw/
        └── provider=USGS_EPT/
            └── dataset=CA_SierraNevada_5_2022/
                ├── USGS_LPC_CA_SierraNevada_..._2022_LAS_2024.laz
                └── ... (106 more files)
```

### 7.3 HPC Array Workflows (Expanse / Slurm)
Because `als-finder` natively isolates the source URLs against precise `data/...` output routing paths inside the CSV, you never use the `--execute` flag on an HPC Head Node. You securely build your `fetch_array.csv` offline, and simply push that list natively into `sbatch`:

```bash
# Example generic fetching parallelization loop on Expanse
sbatch --array=1-1000 wget_fetcher.sh ./tiny_subset/catalog/fetch_array.csv
```

---

## ⚠️ Data Processing: Caveats to Raw Downloads

Because `als-finder` orchestrates transfers actively across deeply decentralized public multi-origin LiDAR repositories natively, the physically downloaded point clouds structurally mirror their origin locations mathematically. If you execute a payload extraction and cease computing there, you will encounter the following analytical bottlenecks:

*   **Coordinate Reference Systems (CRS) & Projections:** There is no universal geometric standard natively mapped across point clouds. Datasets sourced from USGS often arrive in rigid regional grids (e.g., `EPSG:6339` - NAD83(2011) / UTM zone 10N), whereas NOAA assets might globally orient onto `EPSG:4326`. You cannot safely merge these binaries natively without explicit, intensive mathematical reprojections organically bridging the grids.
*   **Arbitrary File Naming Conventions:** As shown physically in prior terminal blocks, originating domains enforce entirely proprietary alphanumeric naming formats. Expect to ingest wildly disparate labels physically mapping to your identical spatial envelope (e.g., `ot_39119B8203.las` bounding perfectly parallel to `USGS_LPC_CA_SierraNevada_..._2022_LAS_2024.laz`).
*   **Classification Constraints (ASPRS):** While most state-of-the-art acquisitions respect ASPRS classification protocols identifying geometric physical entities natively (e.g., Class 2 = Ground), older multi-generational matrices may allocate strictly disparate definitions to identical integer buckets natively corrupting ground-filtering integrations organically.
*   **Format Variances & Data Bloat:** Formal dataset providers often deploy mixtures of `LAS 1.2` or `1.4` formats natively spanning entirely uncompressed `.las` binary schemas organically padding disk volumes compared exclusively against mathematically lossy or natively optimal `.laz` buffers.

*Note: Formal future sequences integrating Point Data Abstraction Library (PDAL) normalization pipelines will cleanly dissolve these parameters targeting a unified `.laz` standard mathematically harmonizing CRS formats organically.*

---

## 🏛️ Acknowledgements & Authorship

This software is released under the open-source **MIT License**. Copyright **Jonathan Greenberg**. 

**Project Authors & Contributors:**
* **Jonathan Greenberg** (University of Nevada, Reno): Lead Developer and Core Project Architect.
* **Andrew Hudak** (US Forest Service): Provided critical advisory feedback and domain tracking under joint grant alignment.
* **Antigravity (Google DeepMind)**: Acted as the primary AI Software Engineer alongside Jonathan.