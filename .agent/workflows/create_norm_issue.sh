gh issue create --repo cms-2024-hudak/als-finder \
  --title "feature: Implementation of Core Normalization Strategy (CRS & ASPRS)" \
  --body "### Summary
The pipeline currently discovers and physically extracts native LiDAR payloads across disparate federal registries (USGS, NOAA, OpenTopography). To build an absolutely seamless modeling engine downstream, we must structurally standardize the physical geometries and classifications before delivering them to the modeling clusters.

### Impact
If points retain native disparate projections (e.g. NAD83 UTM 10N vs WGS84 native bounds) or random provider-specific classification taxonomies (where 'Ground' might be class 2 or class 11), the downstream AI/FVS modeling clusters will suffer severe analytical drift or topological collisions.

### Requirements needed for standard metric output:
1. **Dynamic Standardized Reprojection (`-t_srs`)**:
   Establish a single, mathematically uniform projection standard globally. (Suggested metric CRS format: 'EPSG' defining meters natively across the processing bounds).
2. **ASPRS Classification Coercion**:
   Deploy PDAL filters bridging arbitrary vendor formats explicitly into the precise standard ASPRS matrix.

### Recommended Fix
Integrate PDAL (via conda/docker) seamlessly into the post-download data processing logic, dynamically invoking \`filters.reprojection\` and \`filters.assign\` mapped against provider-specific taxonomies." \
  --label "feature" --label "raster" \
  --milestone "v1.2 (Standardization Engine)"
