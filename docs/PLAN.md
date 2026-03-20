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

### Core Workflow (Two-Stage Batching)
To support HPC job arrays and prevent overloading provider APIs, the tool operates in two distinct stages:
1.  **Search**: Queries the provider for a given ROI, identifies all overlapping LiDAR tiles, and exports a JSON manifest containing individual tile download URLs and metadata.
2.  **Download**: Accepts a single tile URL or metadata entry (often dispatched via a Slurm Array task) and downloads that specific `.laz` file.

### Modules
1.  **Core**:
    -   `InputManager`: Validates ROIs (GeoJSON/Shapefile).
    -   `Config`: Handles environment variables and CLI args.
2.  **Providers Interface**:
    -   `BaseProvider`: Abstract class.
    -   `OpenTopographyProvider`: Implements search/download for OT.
    -   `USGSProvider`: Implements search/download for USGS AWS.
3.  **Tile Manager**:
    -   Handles the generation of the search manifest and the execution of single-tile or concurrent-tile downloads with retries.

## 4. System Inputs

### CLI Arguments

**Search Stage:**
-   `search --roi <path>`: Path to GeoJSON/Shapefile bounding box.
-   `--start-date`, `--end-date`: ISO 8601 dates.
-   `--output-manifest`: Path to save the resulting JSON array of tile URLs.

**Download Stage:**
-   `download --manifest <path>`: Download all tiles in a manifest.
-   `download --tile-url <url>`: Download a single specific tile (Ideal for HPC Job Arrays).
-   `--output-dir`: Host directory to save the `.laz` file.

### Docker Usage
```bash
# Stage 1: Search and generate manifest
docker run -v $(pwd)/data:/data als-finder:latest \
    search --roi /data/roi.geojson --output-manifest /data/tiles.json

# Stage 2: Download a single tile
docker run -v $(pwd)/data:/data als-finder:latest \
    download --tile-url "https://.../tile.laz" --output-dir /data/laz/
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

## 7. Output Structure (Aligned with `als-downscaler`)
```text
.
├── .agent/            # AI Assistant rules and workflows
├── config/            # YAML/JSON configs for pipelines
├── data/              # (Gitignored) Short-lived or small datasets
│   ├── input/         
│   └── output/        
├── docs/              # Documentation
├── infrastructure/    # Dockerfiles
├── logs/              # (Gitignored) Execution logs
├── scripts/           # Entrypoints / Testing scripts
├── src/               # Python source code
│   └── als_finder/    # Core logic modules
└── tests/             # Pytest scripts
```
