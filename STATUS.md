# Current Status

## Completed
- [x] Project Structure (src/, tests/, docs/, scripts/)
- [x] Environment Setup (venv: `als-finder-env`)
- [x] Dockerization (Dockerfile, test script)
- [x] Input Manager (GeoJSON/BBox parsing, reprojecting to WGS84)
- [x] Provider Interface (BaseProvider with `search`, `download`, `check_access`)
- [x] OpenTopography Provider (Search implemented, Key Auth implemented)
- [x] CLI (Search command working)

## In Progress
- [ ] USGS Provider (Search implemented but tuning parameters for 3DEP)
- [ ] Download Logic (Concurrent downloads, file organization)
- [ ] NOAA Provider

## Next Steps
1.  Refine USGS 3DEP search parameters.
2.  Implement `download` command in CLI.
3.  Add NOAA Digital Coast provider.
