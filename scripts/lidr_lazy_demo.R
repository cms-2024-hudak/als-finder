#!/usr/bin/env Rscript
# ==============================================================================
# als-finder: End-to-End Lazy Streaming & lidR Processing Demonstration
#
# Demonstrates memory-bounded, zero-storage-waste LiDAR processing using
# als-finder's on-demand streaming and task manifests.
#
# Usage:
#   Rscript scripts/lidr_lazy_demo.R [manifest_path] [num_tiles]
# ==============================================================================

suppressPackageStartupMessages({
  library(terra)
  library(lidR)
})

args <- commandArgs(trailingOnly = TRUE)
manifest_path <- if (length(args) >= 1) args[1] else "tasks.parquet"
max_tiles <- if (length(args) >= 2) as.integer(args[2]) else 3

# If parquet doesn't exist, fall back to tasks.csv
if (!file.exists(manifest_path) && file.exists("tasks.csv")) {
  manifest_path <- "tasks.csv"
}

if (!file.exists(manifest_path)) {
  stop(sprintf("Task manifest '%s' not found. Run 'als-finder plan --tasks-parquet' first.", manifest_path))
}

cat(sprintf("Using task manifest: %s\n", manifest_path))

is_parquet <- grepl("\\.parquet$", manifest_path, ignore.case = TRUE)

if (is_parquet) {
  suppressPackageStartupMessages({
    library(arrow)
    library(dplyr, warn.conflicts = FALSE)
  })
  ds <- open_dataset(manifest_path)
  total_tasks <- nrow(ds)
} else {
  # Base R streaming 1-row CSV reader
  read_task_csv <- function(path, task_idx) {
    header <- readLines(path, n = 1)
    line <- scan(path, what = character(), sep = "\n", skip = task_idx, nlines = 1, quiet = TRUE)
    read.csv(text = c(header, line), stringsAsFactors = FALSE)
  }
  total_tasks <- as.integer(system2("wc", args = c("-l", manifest_path), stdout = TRUE)) - 1
}

cat(sprintf("Total tasks available: %d. Processing subset of %d tiles...\n", total_tasks, min(max_tiles, total_tasks)))

dir.create("scratch_tiles", showWarnings = FALSE)
dir.create("outputs", showWarnings = FALSE)

for (tid in 1:min(max_tiles, total_tasks)) {
  # 1. Memory-bounded single-row extraction
  if (is_parquet) {
    task <- ds %>% filter(task_id == tid) %>% collect()
  } else {
    task <- read_task_csv(manifest_path, tid)
  }
  
  cat(sprintf("\n--- [%d/%d] Processing Tile %s (%s) ---\n", tid, min(max_tiles, total_tasks), task$tile_id, task$basename))
  
  # 2. Lazy on-demand fetch via CLI
  system2("als-finder", args = c(
    "fetch", "tile", as.character(task$tile_id),
    "--output", "scratch_tiles"
  ))
  
  # 3. Load point cloud
  laz_path <- file.path("scratch_tiles", paste0(task$hive_path, ".laz"))
  if (!file.exists(laz_path)) {
    warning(paste("Could not find downloaded tile:", laz_path))
    next
  }
  
  # Ingest dropping withheld points
  las <- readLAS(laz_path, filter = "-drop_withheld")
  
  # 4. Compute 30m Canopy Height Model
  chm_buffered <- rasterize_canopy(las, res = 30, p2r())
  
  # 5. Crop spatial buffer collar to core bounds
  core_box <- ext(task$core_minx, task$core_maxx, task$core_miny, task$core_maxy)
  chm_core <- crop(chm_buffered, core_box)
  
  # 6. Save deliverable retaining Hive structure
  out_dir <- file.path("outputs", task$hive_dir)
  dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
  out_tif <- file.path(out_dir, paste0(task$basename, "_chm_30m.tif"))
  writeRaster(chm_core, out_tif, overwrite = TRUE)
  cat(sprintf("  Saved: %s\n", out_tif))
  
  # 7. Ephemeral cleanup
  unlink(laz_path)
}

cat("\nDone! Pipeline finished successfully.\n")
