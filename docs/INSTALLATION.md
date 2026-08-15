# ALS-Finder: Installation & Environment Setup Guide

**Target Environments**: Desktop (Conda), Cloud / Containers (Docker/Podman), High-Performance Computing (Singularity/Apptainer)

---

## ⚡ Quick Decision Guide

| Your Environment | Recommended Method | Why? |
| :--- | :--- | :--- |
| **Instant Interactive / Browser** | [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/cms-2024-hudak/als-finder) | 1-Click zero-install cloud workspace with Python, PDAL, and R pre-configured. |
| **Local Desktop / Laptop** | **Conda / Mamba** | Automatically downloads and compiles C++ spatial dependencies (GDAL, PDAL, GEOS). |
| **Windows Native (CMD/PowerShell)** | **Conda** (or WSL2) | Windows C++ compilers are challenging with raw pip; Conda provides pre-built binaries. |
| **Servers / Cloud VMs** | **Docker** | Isolated, reproducible container runtime from GitHub Container Registry. |
| **HPC Clusters (e.g. Expanse)** | **Singularity / Apptainer** | Zero-privilege container execution optimized for Slurm job arrays and parallel storage. |

---

## 1. Conda / Mamba Installation (Recommended for Desktop)

Because `als-finder` relies on advanced C++ geospatial libraries (`geopandas`, `shapely`, `pdal`, `gdal`), Conda or Mamba is the most reliable distribution channel.

### Option A: Install from conda-forge (Official Stable)
```bash
# Create a fresh environment with als-finder from conda-forge
conda create -n als-finder -c conda-forge als-finder

# Activate environment
conda activate als-finder
```

### Option B: Install Bleeding-Edge from GitHub via Conda
```bash
# 1. Create a conda environment with all C++ and Python dependencies
conda create -n als-finder -c conda-forge python=3.11 geopandas pdal python-pdal pystac stac-validator psutil shapely pyproj tqdm pyogrio requests click python-dotenv -y

# 2. Activate the environment
conda activate als-finder

# 3. Install als-finder from GitHub
pip install git+https://github.com/cms-2024-hudak/als-finder.git
```

### Option C: Install from Local Source Clone (Development)
```bash
# 1. Clone repository
git clone https://github.com/cms-2024-hudak/als-finder.git
cd als-finder

# 2. Create environment from environment.yml
conda env create -f environment.yml

# 3. Activate and install in editable mode
conda activate als-finder
pip install -e .
```

---

## 2. Docker Installation (For Servers & Cloud VMs)

Pre-built Docker images are published to GitHub Container Registry (GHCR):

```bash
# 1. Pull latest image
docker pull ghcr.io/cms-2024-hudak/als-finder:latest

# 2. Run federated search
docker run --rm \
    -v $(pwd)/workspace:/workspace \
    ghcr.io/cms-2024-hudak/als-finder:latest \
    search --roi "-124,42,-123,43" --workspace /workspace
```

---

## 3. Singularity / Apptainer Installation (For HPC Supercomputers)

On shared HPC clusters without root privileges, convert the GHCR Docker image into a standard Singularity Image File (`.sif`):

```bash
# Build Singularity Image from GHCR
singularity build als-finder.sif docker://ghcr.io/cms-2024-hudak/als-finder:latest

# Verify execution
singularity exec als-finder.sif als-finder --version

# Run with explicit workspace and scratch bindings
singularity exec \
    --bind ${WORKSPACE}:${WORKSPACE},${SCRATCH}:${SCRATCH} \
    als-finder.sif \
    als-finder search --roi ./roi.gpkg --workspace ${WORKSPACE}
```

---

## 4. OpenTopography API Key Configuration

OpenTopography requires a free authorization key for catalog search queries:
1. Create an account at [OpenTopography.org](https://opentopography.org).
2. Navigate to **MyAccount** -> **Request API Key**.
3. Supply this key during your first search using the `--ot-key` flag. The CLI transparently saves it into a local `.env` file for all future runs:

```bash
als-finder search \
    --roi ./ltbmu_boundary.gpkg \
    --ot-key "YOUR_OPENTOPO_KEY" \
    --workspace ./my_project/
```
