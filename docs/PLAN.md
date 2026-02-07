# LiDAR Data Finder - Implementation Plan

## 1. Overview
This tool provides a Python-based interface to search for and download LiDAR point cloud data from major open-access repositories. The application will be containerized using Docker to ensure reproducibility and ease of deployment.

## 2. Target Data Providers
-   **OpenTopography** (Primary, API Key required)
-   **USGS 3DEP** (AWS Public Datasets)
-   **NOAA Digital Coast** (via OpenTopography or AWS)

## 3. System Architecture

### Deployment
-   **Docker Container**: The primary delivery mechanism.
-   **Entrypoint**: A CLI tool `als-finder`.

### Modules
1.  **Core**:
    -   `InputManager`: Validates ROIs (GeoJSON/Shapefile).
    -   `Config`: Handles environment variables and CLI args.
2.  **Providers Interface**:
    -   `BaseProvider`: Abstract class.
    -   `OpenTopographyProvider`: Implements search/download for OT.
    -   `USGSProvider`: Implements search/download for USGS AWS.
3.  **Download Manager**:
    -   Handles concurrency, retries, and file organization.

## 4. System Inputs

### CLI Arguments
-   `--roi`: Path to GeoJSON/Shapefile/BBox.
-   `--start-date`, `--end-date`: ISO 8601 dates.
-   `--density`: Minimum point density (pts/m²).
-   `--output`: Host directory mounted to container.

### Docker Usage
```bash
docker run -v $(pwd)/data:/output -v $(pwd)/config:/config \
    --env-file .env \
    als-finder:latest \
    download --roi /config/roi.geojson --output /output
```

## 5. Development Standards
*See `.agent/rules/` for detailed guidelines.*
-   **Language**: Python 3.10+
-   **Style**: Black, Typed (Mypy), Google-style Docstrings.
-   **Testing**: Pytest with high coverage.
-   **Version Control**: Conventional Commits.

## 6. Implementation Stages

### Phase 1: Environment & Standards [Done]
-   [x] Project Structure
-   [x] Define Agent Rules (Git, Python, Docs)
-   [x] Dockerfile Initial Setup
-   [ ] CI/CD Workflows (GitHub Actions - planned)

### Phase 2: Core Logic
-   [x] ROI Parsing & Validation
-   [x] CLI Skeleton (Click/Argparse)

### Phase 3: Providers
-   [x] OpenTopography Client
-   [x] USGS Client

### Phase 4: Dockerization & Release
-   [x] Final Docker Optimization (Multi-stage build)
-   [ ] Documentation Complete

## 7. Output Structure
```text
output/
├── manifest.json
├── opentopography/
│   └── dataset_A/ ...
└── usgs/
    └── tile_B/ ...
```
