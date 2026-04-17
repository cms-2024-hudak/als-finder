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

# Copy the application code
COPY --chown=$MAMBA_USER:$MAMBA_USER src/ src/
COPY --chown=$MAMBA_USER:$MAMBA_USER .agent/ .agent/
COPY --chown=$MAMBA_USER:$MAMBA_USER docs/ docs/
COPY --chown=$MAMBA_USER:$MAMBA_USER README.md .
COPY --chown=$MAMBA_USER:$MAMBA_USER setup.py .

# Install the package itself in editable mode via pip (since micromamba provides pip)
# We use the micromamba python interpreter
ARG MAMBA_DOCKERFILE_ACTIVATE=1
ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.1.0
RUN pip install --no-cache-dir -e .

# Define the entrypoint
ENTRYPOINT ["/usr/local/bin/_entrypoint.sh", "python", "-m", "als_finder.cli"]
CMD ["--help"]
