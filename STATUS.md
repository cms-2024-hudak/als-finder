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
- [ ] Two-Stage Architecture Refactoring: Split into `search` (manifest generation) and `download` (single-tile/manifest processing).
- [ ] NOAA Provider

## Next Steps
1.  Refactor CLI to support `search` (outputting JSON manifest) and `download` (taking tile URLs).
2.  Refine USGS 3DEP search parameters to return precise tile URLs.
3.  Add NOAA Digital Coast provider.
