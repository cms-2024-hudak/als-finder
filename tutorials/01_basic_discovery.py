# %% [markdown]
# # Tutorial 01: Basic Discovery & Federated Ingestion (Interactive Script)
# 
# Welcome to the **Interactive Python (Percent Script)** format!
# - Press **Shift + Enter** on any cell (`# %%`) to run it immediately in the side pane.
# - Plots and tables will render inline in the Interactive Window.

# %% [markdown]
# ### Step 1: Extract Bundled Lake Tahoe ROI

# %%
import sys
import subprocess
print("Extracting sample Lake Tahoe ROI...")
result = subprocess.run([sys.executable, "-m", "als_finder.cli", "get-example-roi"], capture_output=True, text=True)
print(result.stdout)

# %% [markdown]
# ### Step 2: Inspect ROI Bounds with GeoPandas

# %%
import geopandas as gpd

roi_gdf = gpd.read_file("ltbmu_boundary.gpkg")
print(f"ROI CRS: {roi_gdf.crs}")
print(f"Total Bounds (WGS84): {roi_gdf.total_bounds}")
display(roi_gdf)

# %% [markdown]
# ### Step 3: Run Federated Search

# %%
import als_finder
print("Running search across USGS 3DEP and NOAA Coastal...")

cmd = [
    sys.executable, "-m", "als_finder.cli", "search",
    "--roi", "./ltbmu_boundary.gpkg",
    "--density", "QL1",
    "--workspace", "./demo_workspace/",
    "--provider", "USGS_EPT",
    "--provider", "NOAA_STAC"
]
subprocess.run(cmd)

# %% [markdown]
# ### Step 4: Inspect Discovered Catalog & Plot Spatial Coverage

# %%
import pandas as pd
import matplotlib.pyplot as plt

# 1. Read CSV Summary Table
catalog_df = pd.read_csv("demo_workspace/catalog/catalog.csv")
print("Top Discovered Acquisitions:")
display(catalog_df[["Provider", "Name", "Date", "PointDensity"]].head())

# 2. Visualize Coverage Overlapping Lake Tahoe
catalog_gdf = gpd.read_file("demo_workspace/catalog/catalog.gpkg")

fig, ax = plt.subplots(figsize=(8, 8))
roi_gdf.plot(ax=ax, color="none", edgecolor="black", linewidth=2.5, label="ROI (Tahoe)")
catalog_gdf.plot(ax=ax, column="name", alpha=0.45, legend=True, cmap="tab10")
ax.set_title("LiDAR Acquisitions Intersecting Lake Tahoe Basin (QL1)", fontsize=13, fontweight="bold")
plt.xlabel("Longitude (deg W)")
plt.ylabel("Latitude (deg N)")
plt.grid(True, linestyle="--", alpha=0.5)
plt.tight_layout()
plt.show()
