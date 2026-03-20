# ALS-Finder Architecture Roadmap

**Purpose**: An API extraction engine designed to search, deduplicate, and securely download high-resolution LiDAR Point clouds (`.laz`) natively across isolated federal boundaries. Acts as the geospatial ingestion stage for the downstream `als-downscaler` HPC orchestration pipeline.

***

## Workflow A: Geospatial Search (`cli.py search`)
- **Inputs**: 
  - Local GeoJSON Region of Interest boundaries (`--roi`).
  - Explicit permitted query providers (USGS STAC, OpenTopography, NOAA).
- **Core Execution**:
  1. Translates the ROI limits into raw `shapely.geometry` spatial intersections.
  2. Dispatches asynchronous, federated API payload queries across the Microsoft Planetary Computer STAC (USGS 3DEP), NOAA AWS S3 Entwine index catalogs, and OpenTopography JSON-LD spatial environments.
  3. Homogenizes resulting heterogeneous JSON responses natively into an internal python schema array.
  4. Extracts dataset aliases to isolate and natively suppress functionally identical targets (Currently strictly bounded to literal string matching).
- **Outputs**: 
  - A highly structured JSON configuration manifest (`manifest.json`) securely mapping all mathematically viable `.laz` download arrays across the designated bounding box.

***

## Workflow B: Target Extraction (`cli.py download`)
- **Inputs**: 
  - The upstream generated JSON architecture manifest, or dynamic `--tile-url` injection parameters.
- **Core Execution**:
  1. Spools the native HTTP extraction clients to map against targeted provider logic (e.g., `USGSProvider`).
  2. Actively probes the payload structures: if native Azure Blob URLs block access (`409 Public Access Blocked`), proactively dispatches identical authentication queries into the Microsoft Planetary `sas` overlay to construct an ephemeral **Shared Access Signature (SAS)** API bypass token.
  3. Instantiates parallel or successive byte stream downloads into local scratch volumes.
- **Outputs**: 
  - Localized, uncompressed `.copc.laz` or legacy point cloud layers structured rigidly onto the `$SCRATCH` partitions for HPC intersection.
