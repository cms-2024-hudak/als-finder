# ALS-Finder: Institutional Memory & Operational Rules

## 1. System Persona & Engineering Standards
- **Role**: Staff Software Engineer — Scientific Computing Infrastructure.
- **Clean Code & Modularity**: Keep logic in `src/als_finder/core/`. Do NOT put pipeline, spatial math, or PDAL logic inside `cli.py` (`cli.py` is strictly an argument parser and command dispatcher).
- **Paths**: Never hardcode absolute paths (`/home/...` or `C:\...`). Always use `pathlib.Path` resolved relative to `--workspace` or project roots.
- **Stdout vs Stderr**: Reserve `stdout` exclusively for clean, machine-readable JSON payloads (`--json`). Direct all logs, warnings, and progress indicators strictly to `stderr`.
- **Typing & Docs**: PEP 484 type hints on all functions and classes; Google-style docstrings.

## 2. Hard-Won Lessons & Scientific Constraints (What the User Taught Us)
- **Zero Unprojected Metric Math**: Never compute tile grids, buffers, distances, or morphological filters in unprojected degree space (`EPSG:4326`). Always project to local UTM (auto-detected via `estimate_utm_crs()`) or an explicit metric CRS before spatial slicing.
- **EPT CRS Bounding Gotcha**: EPT point clouds on AWS/Entwine are indexed in specific coordinate systems (often EPSG:3857 or state-plane). Transforming ROI bounding boxes to the EPT's native coordinate system is mandatory to avoid 0-point empty tile downloads.
- **In-Stream Buffer Point Tagging for lidR**: When streaming tiles for downstream canopy metric tools (like `lidR` in R), points falling within the core tile are tagged with `buffer = 0`, and points in the spatial overlap collar are tagged with `buffer = 1` using native LAS Extra Bytes (`uint8`). This eliminates edge artifacts in CHMs and DTMs without manual cropping.
- **Single-Row SQL Lookups on HPC**: Do not load entire `grid.gpkg` or `catalog.gpkg` GeoDataFrames into worker memory during Slurm tasks. Use zero-copy single-row SQL queries via `pyogrio` (`SELECT * FROM grid WHERE tile_id = ?`).
- **Memory Guardrails & Thread Clamping**: Underlying C++ libraries (OpenBLAS, GDAL, OMP) spawn excessive child threads, triggering virtual memory exhaustion (`RLIMIT_AS`). Always clamp threads (`OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `GDAL_NUM_THREADS=1`) and wrap PDAL/GDAL subprocesses in `execute_with_memory_limit()`.
- **Adaptive OOM Quadrant Bisection**: High-overlap flightlines or steep terrain create hyper-dense tiles (10M+ points) that crash 4GB/8GB Slurm workers. The grid planner automatically bisects high-point tiles into 4 co-located quadrants (`_NW`, `_NE`, `_SW`, `_SE`) with buffered margins.
- **Hive Partitioning Alignment**: Paths follow canonical STAC/COPC standard keys: `provider=<org>/year=<yyyy>/state=<state>/dataset=<id>/tile=<id>.laz`.

## 3. Environment & Runtime Bootstrap
- **Conda Environment**: `als-finder-env` or `als-tutorial`
  ```bash
  conda create -n als-finder-env -c conda-forge python=3.11 pdal python-pdal gdal geopandas pyogrio pyarrow boto3 pydantic requests click tabulate -y
  conda activate als-finder-env
  pip install -e .
  ```
- **HPC / Singularity Execution**:
  ```bash
  singularity exec --bind ${WORKSPACE}:${WORKSPACE},${SCRATCH}:${SCRATCH} als-finder.sif als-finder fetch tile ${SLURM_ARRAY_TASK_ID} --workspace ${WORKSPACE}
  ```
- **Required Environment Variables (Sanitized)**:
  - `OPENTOPOGRAPHY_API_KEY=<redacted>` (for OpenTopography high-rate queries)
  - `EARTHDATA_USERNAME=<redacted>` / `EARTHDATA_PASSWORD=<redacted>` (for NASA DAAC / G-LiHT)
  - `AWS_ACCESS_KEY_ID=<redacted>` / `AWS_SECRET_ACCESS_KEY=<redacted>` (optional, for direct NOAA S3 enumeration)
