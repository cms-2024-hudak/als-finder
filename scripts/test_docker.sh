# Build the image
docker build -t als-finder:latest .

# Run a search (using the LTBMU ROI)
# We need to map the output directory to verify results
mkdir -p data
# Use the local data/ltbmu_roi.geojson created by the user or agent
# Copy relevant data if needed (Docker volume mount handles access)

docker run --rm \
    --env-file .env \
    -v $(pwd)/data:/data \
    als-finder:latest search \
    --roi /data/ltbmu_roi.geojson \
    --provider opentopography \
    --provider usgs
