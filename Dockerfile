# Use Micromamba to handle complex geospatial C++ dependencies (GDAL, PDAL) smoothly
FROM mambaorg/micromamba:1.5-jammy

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copy requirements and install them via conda-forge
COPY --chown=$MAMBA_USER:$MAMBA_USER requirements.txt /tmp/requirements.txt
RUN micromamba install -y -n base -c conda-forge \
    python=3.11 \
    gdal \
    pdal \
    python-pdal \
    --file /tmp/requirements.txt && \
    micromamba clean --all --yes

# Set the working directory in the container
WORKDIR /app

# Copy build definition and source files
COPY --chown=$MAMBA_USER:$MAMBA_USER pyproject.toml setup.py README.md ./
COPY --chown=$MAMBA_USER:$MAMBA_USER src/ src/

# Install package in editable mode without re-resolving pre-installed conda dependencies
ARG MAMBA_DOCKERFILE_ACTIVATE=1
ARG VERSION=1.2.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION}
RUN pip install --no-cache-dir --no-deps -e .

# Copy documentation after install so doc edits do not bust code build cache
COPY --chown=$MAMBA_USER:$MAMBA_USER docs/ docs/

# Define the entrypoint using the console_script directly
ENTRYPOINT ["/usr/local/bin/_entrypoint.sh", "als-finder"]
CMD ["--help"]
