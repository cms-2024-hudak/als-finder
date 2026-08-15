# Multi-language (Python + C++ Geospatial + R) DevContainer for ALS-Finder
FROM mambaorg/micromamba:1.5-jammy

USER root

# Install system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    tree \
    jq \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

USER $MAMBA_USER

# Environment configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install unified conda-forge environment:
# 1. Python Geospatial + Jupyter
# 2. Native C++ Binaries (GDAL, PDAL)
# 3. R Spatial Ecosystem (R-base, sf, lidR, terra, IRkernel)
RUN micromamba install -y -n base -c conda-forge \
    python=3.11 \
    gdal \
    pdal \
    python-pdal \
    geopandas \
    shapely \
    pyproj \
    pyogrio \
    fiona \
    laspy \
    laz-perf \
    pystac \
    stac-validator \
    requests \
    boto3 \
    click \
    python-dotenv \
    tqdm \
    psutil \
    pyyaml \
    pytest \
    setuptools_scm \
    pip \
    jupyterlab \
    ipykernel \
    matplotlib \
    folium \
    mapclassify \
    r-base>=4.2 \
    r-irkernel \
    r-sf \
    r-lidr \
    r-terra \
    r-jsonlite \
    r-ggplot2 \
    && micromamba clean --all --yes

# Set workspace
WORKDIR /workspace

ARG MAMBA_DOCKERFILE_ACTIVATE=1
ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.2.0

# Register R IRkernel in Jupyter
RUN R -e "IRkernel::installspec(user = FALSE)"
