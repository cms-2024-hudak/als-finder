# Tutorial 00: Environment Installation & Setup

Welcome to **Tutorial 00** of the `als-finder` suite. This guide helps you configure your local desktop, server, or HPC environment.

> [!TIP]
> **Zero-Install Cloud Alternative**: If you want to skip local installation entirely, you can run all tutorials in your browser with 1 click via [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/cms-2024-hudak/als-finder).

---

## 1. Local Desktop Installation (Conda)

Because `als-finder` depends on C++ spatial engines (PDAL, GDAL, GEOS), we strongly recommend using Conda or Mamba:

```bash
# 1. Create a fresh environment with all spatial dependencies
conda create -n als-finder -c conda-forge python=3.11 geopandas pdal python-pdal pystac stac-validator psutil shapely pyproj tqdm pyogrio requests click python-dotenv -y

# 2. Activate the environment
conda activate als-finder

# 3. Install als-finder from GitHub
pip install git+https://github.com/cms-2024-hudak/als-finder.git
```

---

## 2. OpenTopography API Key Setup

1. Register for a free account at [OpenTopography.org](https://opentopography.org).
2. Go to **MyAccount** -> **Request API Key**.
3. Pass it once to `als-finder` using the `--ot-key` flag:

```bash
als-finder get-example-roi
als-finder search --roi ./ltbmu_boundary.gpkg --ot-key "YOUR_API_KEY" --workspace ./test_workspace/
```
The CLI automatically saves your key to `.env` in your workspace for all subsequent commands.

---

## 3. Verify Installation

Run the CLI check to confirm everything is configured:

```bash
als-finder --version
als-finder --help
```

---

### 👉 Next Step
Proceed to [Tutorial 01: Basic Discovery & Federated Ingestion](./01_basic_discovery.md) to start searching for LiDAR data!
