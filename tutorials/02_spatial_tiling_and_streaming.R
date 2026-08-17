# ==============================================================================
# Tutorial 02: Native R Spatial Tiling, Cloud Streaming & Raster Processing
# ==============================================================================
# This script demonstrates native R spatial analysis using ALS-Finder:
# 1. Load the vector grid directly into R using `terra`.
# 2. Extract total tile counts and loop bounds (`length(grid)` and `grid$tile_id`).
# 3. Query tile metadata purely by integer index (`tile_id`).
# 4. Stream point cloud tiles on-demand via the ALS-Finder CLI into scratch.
# 5. Understand and filter ASPRS 'withheld' points cleanly.
# 6. Dynamically name and organize output raster products using grid metadata.
# 7. Bridge standardized outputs with `lidR::LAScatalog`.
# ==============================================================================

suppressPackageStartupMessages({
  library(terra)
  library(rlas)
})

cat("======================================================================\n")
cat(" ALS-Finder Tutorial 02: Native R Spatial Tiling & Streaming\n")
cat("======================================================================\n")

# --- Step 1: Workspace & Grid Configuration ---
workspace_dir <- file.path(".", "tiling_workspace")
if (!dir.exists(workspace_dir)) {
  workspace_dir <- file.path(".", "demo_workspace")
}

manifest_path  <- file.path(workspace_dir, "catalog", "manifest.json")
grid_gpkg_path <- file.path(workspace_dir, "catalog", "grids", "tilesize=500", "buffer=30", "grid.gpkg")

if (!file.exists(grid_gpkg_path)) {
  grid_gpkg_path <- file.path(workspace_dir, "catalog", "grid.gpkg")
}

# --- Step 2: Load Vector Grid in R & Determine Total Tile Count ---
grid <- terra::vect(grid_gpkg_path)

# Extract total tile count and integer indices for looping
total_tiles  <- length(grid)        # Total number of tiles in the study area
all_tile_ids <- grid$tile_id        # Vector of integer IDs: c(0, 1, 2, ..., n-1)

cat("\n✓ Loaded Vector Grid in R:\n")
cat("  Total Tiles to Process:", total_tiles, "\n")
cat("  Tile ID Range:          0 to", max(all_tile_ids), "\n")
cat("  Coordinate Reference:   ", terra::crs(grid, proj = TRUE), "\n")

# --- Step 3: Out-of-Core Processing Loop (Example: First 2 Tiles) ---
# In production, loop over all tiles: `for (target_tile_id in all_tile_ids)`
subset_tile_ids <- head(all_tile_ids, 2)

scratch_dir <- file.path(workspace_dir, "scratch")
dir.create(scratch_dir, showWarnings = FALSE, recursive = TRUE)

out_raster_dir <- file.path(workspace_dir, "data", "products", "dsm")
dir.create(out_raster_dir, showWarnings = FALSE, recursive = TRUE)

# Resolve ALS-Finder CLI binary
cli_bin <- Sys.which("als-finder")
if (cli_bin == "" && file.exists(".venv/bin/als-finder")) {
  cli_bin <- ".venv/bin/als-finder"
} else if (cli_bin == "") {
  cli_bin <- "python3 -m als_finder.cli"
}

for (target_tile_id in subset_tile_ids) {
  cat(sprintf("\n--- Processing Tile Index #%d of %d ---\n", target_tile_id + 1, total_tiles))
  
  # Extract tile metadata row directly from grid.gpkg
  tile_row <- grid[grid$tile_id == target_tile_id, ]
  
  cat("  Provider:          ", as.character(tile_row$provider), "\n")
  cat("  Dataset ID:        ", as.character(tile_row$dataset_id), "\n")
  cat("  Nominal Density:   ", tile_row$point_density, "pts/m²\n")
  cat("  Spatial Basename:  ", as.character(tile_row$spatial_basename), "\n")
  cat("  Standard Hive Path:", as.character(tile_row$hive_path), "\n")
  
  # Define scratch stream path using spatial basename from grid
  streamed_laz <- file.path(scratch_dir, as.character(tile_row$spatial_basename))
  
  # Stream single tile on-demand over HTTP
  cli_cmd <- sprintf(
    "%s fetch-tile --manifest %s --tile-id %d --tile-size %d --buffer-size %d --crs %s --output %s --overwrite --json",
    cli_bin,
    shQuote(manifest_path),
    target_tile_id,
    as.integer(tile_row$tile_size),
    as.integer(tile_row$buffer_size),
    as.character(tile_row$grid_crs),
    shQuote(streamed_laz)
  )
  system(cli_cmd)
  
  if (file.exists(streamed_laz)) {
    # --- Step 4: Read Point Records & Handle 'Withheld' Points ---
    # In ASPRS LAS standards, bit flag 4 is the 'Withheld' flag.
    # USGS 3DEP and survey vendors flag flight-line turns, scanner mirror turnarounds,
    # and atmospheric noise as 'withheld' so they are excluded from terrain models.
    hdr <- rlas::read.lasheader(streamed_laz)
    pts <- suppressWarnings(rlas::read.las(streamed_laz))
    
    withheld_count <- sum(pts$Withheld)
    clean_pts <- pts[!pts$Withheld, ]
    
    cat(sprintf("  Streamed Points:   %s (Withheld: %s / %.2f%%)\n",
                format(hdr$`Number of point records`, big.mark = ","),
                format(withheld_count, big.mark = ","),
                withheld_count / nrow(pts) * 100))
    cat(sprintf("  Valid Analysis:    %s points\n", format(nrow(clean_pts), big.mark = ",")))
    cat(sprintf("  Elevation (Z):     %.2f m to %.2f m (Mean: %.2f m)\n",
                min(clean_pts$Z), max(clean_pts$Z), mean(clean_pts$Z)))
    
    # --- Step 5: Dynamically Name & Save Output DSM Raster ---
    raster_filename <- sub("\\.laz$", "_dsm.tif", as.character(tile_row$spatial_basename))
    out_raster_path <- file.path(out_raster_dir, raster_filename)
    
    r_template <- terra::rast(
      xmin = min(clean_pts$X), xmax = max(clean_pts$X),
      ymin = min(clean_pts$Y), ymax = max(clean_pts$Y),
      res  = 2.0,
      crs  = as.character(tile_row$grid_crs)
    )
    
    dsm_raster <- terra::rasterize(
      as.matrix(clean_pts[, c("X", "Y")]),
      r_template,
      values = clean_pts$Z,
      fun = "max"
    )
    
    terra::writeRaster(dsm_raster, out_raster_path, overwrite = TRUE)
    cat("  ✓ Raster Saved:    ", out_raster_path, "\n")
    
    # --- Step 6: Zero-Disk Storage Hygiene ---
    unlink(streamed_laz)
  }
}

# --- Step 7: Interoperability with lidR::LAScatalog ---
cat("\n======================================================================\n")
cat(" lidR LAScatalog Interoperability\n")
cat("======================================================================\n")
cat("Once standardized tiles are saved in `data/standardized/`, R researchers\n")
cat("can construct a native `lidR::LAScatalog` across the whole study area:\n\n")
cat("  library(lidR)\n")
cat("  ctg <- readLAScatalog('data/standardized/')\n")
cat("  opt_chunk_size(ctg)   <- 0   # Process by existing tile boundaries\n")
cat("  opt_chunk_buffer(ctg) <- 0   # Buffers already handled by ALS-Finder\n")
cat("  opt_output_files(ctg) <- 'data/products/chm/{ORIGINALFILENAME}_chm'\n")
cat("  chm <- rasterize_canopy(ctg, res = 1.0, algorithm = p2r())\n\n")
cat("✓ Native R Spatial Tiling Pipeline Execution Complete.\n")
cat("======================================================================\n")
