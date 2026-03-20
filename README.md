# als-finder

A Python tool for searching and downloading LiDAR point cloud data from open databases including OpenTopography, USGS 3DEP, and NOAA.

## Planning
See [PLAN.md](PLAN.md) for the detailed implementation roadmap.

## Usage (Planned)
```bash
python -m als_finder.cli --roi my_area.geojson --start-date 2020-01-01
```

## Setup
1.  Install dependencies: `pip install -r requirements.txt`
2.  Set up API keys:
    -   Copy `.env.template` to `.env`.
    -   Add your `OPENTOPOGRAPHY_API_KEY`.