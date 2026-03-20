---
description: Build and test the Docker container
---

# Docker Build Workflow

## Steps

1.  **Validate Requirements**
    -   Ensure `requirements.txt` is up to date.
    -   Ensure `Dockerfile` exists.

2.  **Build Image**
    -   Run: `docker build -t als-finder:latest .`

3.  **Test Run**
    -   Run help command to verify entrypoint:
        `docker run --rm als-finder:latest --help`

4.  **Integration Test (Optional)**
    -   Run a small search to verify connectivity (requires API key):
        `docker run --rm --env-file .env als-finder:latest search --roi tests/sample_roi.json`
