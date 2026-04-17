import logging
import json
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

def generate_quicklooks(workspace: Path) -> bool:
    """
    Generates a rapid 2D quicklook visualization (PNG) directly from standardized COPC files
    to allow the user to visually QA/QC for structural errors (e.g. SMRF failures or projection issues)
    without needing to load the entire point cloud into 3D software.
    """
    standardized_dir = workspace / "data" / "standardized"
    reports_base_dir = workspace / "data" / "quicklooks"
    catalog_dir = workspace / "catalog"
    
    if not standardized_dir.exists():
        logger.error(f"Cannot generate quicklooks. Standardized directory missing: {standardized_dir}")
        return False
        
    laz_files = list(standardized_dir.rglob("*.copc.laz"))
    if not laz_files:
        logger.warning(f"No standardized .copc.laz files found for quicklook generation.")
        return False
        
    success = True
    processed_reports = []
    
    for sample_file in laz_files:
        try:
            rel_path = sample_file.relative_to(standardized_dir)
            report_dir = reports_base_dir / rel_path.parent
            report_dir.mkdir(parents=True, exist_ok=True)
            
            output_tif = report_dir / f"{sample_file.stem}_dem.tif"
            output_png = report_dir / f"{sample_file.stem}_elevation_preview.png"
            
            # --- 1. Elevation DEM (Hillshade) ---
            pipeline = [
                {
                    "type": "readers.copc",
                    "filename": str(sample_file.absolute()),
                    "resolution": 2.0  # Only stream the low-res octree nodes necessary for a 2m grid! Extremely fast.
                },
                {
                    "type": "writers.gdal",
                    "filename": str(output_tif.absolute()),
                    "output_type": "min",
                    "resolution": 2.0,
                    "data_type": "float32",
                    "window_size": 3
                }
            ]
            pdal_json = json.dumps(pipeline)
            logger.info(f"Generating 2D DEM for {sample_file.name} natively...")
            subprocess.run(['pdal', 'pipeline', '-s'], input=pdal_json.encode('utf-8'), capture_output=True, check=True)
            
            logger.info("Converting DEM to visible Hillshade PNG...")
            subprocess.run([
                'gdaldem', 'hillshade', 
                str(output_tif.absolute()), str(output_png.absolute()), 
                '-of', 'PNG', '-z', '1.0', '-s', '1.0', '-az', '315.0', '-alt', '45.0'
            ], capture_output=True, check=True)
            
            if output_tif.exists(): output_tif.unlink()
            
            # --- 2. Canopy Height Model (CHM) ---
            color_ramp_path = report_dir / "chm_color_ramp.txt"
            with open(color_ramp_path, "w") as f:
                f.write("0 0 0 128\n")       # 0m: dark blue (bare ground)
                f.write("2 0 255 0\n")       # 2m: green (low vegetation)
                f.write("15 255 255 0\n")    # 15m: yellow (mid story)
                f.write("30 255 128 0\n")    # 30m: orange (tall canopy)
                f.write("50 255 0 0\n")      # 50m+: red (very tall canopy)
                f.write("nv 255 255 255\n")  # no data: white
                
            output_chm_tif = report_dir / f"{sample_file.stem}_chm.tif"
            output_chm_png = report_dir / f"{sample_file.stem}_chm_preview.png"
            
            chm_pipeline = [
                {
                    "type": "readers.copc",
                    "filename": str(sample_file.absolute()),
                    "resolution": 2.0  # Only stream the low-res octree nodes necessary for a 2m grid! Extremely fast.
                },
                {"type": "filters.hag_nn"},
                {
                    "type": "writers.gdal",
                    "filename": str(output_chm_tif.absolute()),
                    "dimension": "HeightAboveGround",
                    "output_type": "max",
                    "resolution": 2.0,
                    "data_type": "float32",
                    "window_size": 3
                }
            ]
            logger.info(f"Generating 2D Canopy Height Model for {sample_file.name} natively...")
            subprocess.run(['pdal', 'pipeline', '-s'], input=json.dumps(chm_pipeline).encode('utf-8'), capture_output=True, check=True)
            
            logger.info("Converting CHM to visible color-relief PNG...")
            subprocess.run([
                'gdaldem', 'color-relief', 
                str(output_chm_tif.absolute()), str(color_ramp_path.absolute()), 
                str(output_chm_png.absolute()), '-of', 'PNG'
            ], capture_output=True, check=True)
            
            if output_chm_tif.exists(): output_chm_tif.unlink()
            if color_ramp_path.exists(): color_ramp_path.unlink()
            
            # --- 3. Extract Metadata ---
            logger.info(f"Extracting metadata for {sample_file.name}...")
            summary_res = subprocess.run(['pdal', 'info', '--summary', str(sample_file.absolute())], capture_output=True, check=True, text=True)
            summary_data = json.loads(summary_res.stdout).get('summary', {})
            num_points = summary_data.get('summary', {}).get('num_points', 'Unknown')
            if summary_data.get('bounds') and summary_data['bounds'].get('X'):
                maxx = summary_data['bounds']['X'].get('max', 0)
                minx = summary_data['bounds']['X'].get('min', 0)
                maxy = summary_data['bounds']['Y'].get('max', 0)
                miny = summary_data['bounds']['Y'].get('min', 0)
                area_sqm = (maxx - minx) * (maxy - miny)
                density = round(num_points / area_sqm, 2) if area_sqm > 0 else 'Unknown'
            else:
                density = 'Unknown'
            
            # Generate individual HTML wrapper
            html_path = report_dir / f"{sample_file.stem}_quicklook.html"
            with open(html_path, "w") as f:
                f.write(f"<html><head><title>LiDAR Quicklook: {sample_file.name}</title></head>")
                f.write("<body style='font-family: sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px;'>")
                f.write("<h2>LiDAR QA/QC Quicklook</h2>")
                f.write(f"<p><strong>Source File:</strong> {sample_file.name}</p>")
                f.write("<h3>Dataset Metadata</h3>")
                f.write("<table border='1' cellpadding='5' style='border-collapse: collapse;'>")
                f.write(f"<tr><td>Total Points</td><td>{num_points}</td></tr>")
                f.write(f"<tr><td>Estimated Density</td><td>{density} pts/m²</td></tr>")
                f.write("</table>")
                
                f.write("<div style='display: flex; gap: 20px; margin-top: 20px;'>")
                f.write("<div>")
                f.write("<h3>Elevation Minimum (Ground Hillshade)</h3>")
                f.write("<p style='max-width: 500px;'>If this image shows a continuous surface, the SMRF and coordinate projection succeeded. If it shows severe stripes or gaps, check the raw data boundaries.</p>")
                f.write(f"<img src='{output_png.name}' width='500' style='border: 1px solid #ccc;'/>")
                f.write("</div><div>")
                f.write("<h3>Canopy Height Model (Max Height Above Ground)</h3>")
                f.write("<p style='max-width: 500px;'>Calculated natively via <code>filters.hag_nn</code>. Blue = Bare Earth, Green = Low Veg, Yellow = Mid, Red = Tall Canopy.</p>")
                f.write(f"<img src='{output_chm_png.name}' width='500' style='border: 1px solid #ccc;'/>")
                f.write("</div></div>")
                f.write("</body></html>")
                
            logger.info(f"[SUCCESS] Quicklook HTML generated: {html_path.absolute()}")
            
            import os
            processed_reports.append({
                "dataset": sample_file.parent.name,
                "provider": sample_file.parent.parent.name,
                "file": sample_file.name,
                "html": os.path.relpath(html_path, catalog_dir).replace('\\', '/'),
                "dem_png": os.path.relpath(output_png, catalog_dir).replace('\\', '/'),
                "chm_png": os.path.relpath(output_chm_png, catalog_dir).replace('\\', '/'),
                "points": num_points
            })
            
        except subprocess.CalledProcessError as e:
            logger.error(f"PDAL Pipeline execution failed natively for quicklook {sample_file.name}: {e.stderr.decode('utf-8')}")
            success = False
        except Exception as e:
            logger.error(f"Quicklook generation failed natively for {sample_file.name}: {e}")
            success = False
            
    # --- 4. Generate Master Catalog ---
    if processed_reports:
        master_index_path = catalog_dir / "quicklooks_index.html"
        logger.info(f"Generating Master Quicklook Catalog at {master_index_path}...")
        with open(master_index_path, "w") as f:
            f.write("<html><head><title>Master QA/QC Catalog</title>")
            f.write("<style>body { font-family: sans-serif; padding: 20px; } .card { border: 1px solid #ddd; padding: 15px; margin-bottom: 20px; border-radius: 5px; } .img-container { display: flex; gap: 15px; margin-top: 10px; } img { max-width: 400px; border: 1px solid #eee; }</style>")
            f.write("</head><body>")
            f.write("<h1>LiDAR QA/QC Master Catalog</h1>")
            f.write("<p>Aggregated quicklooks for all downloaded and normalized subsets in this workspace.</p>")
            
            for rep in processed_reports:
                f.write("<div class='card'>")
                f.write(f"<h3><a href='{rep['html']}'>{rep['dataset']}</a></h3>")
                f.write(f"<p><strong>Provider:</strong> {rep['provider']} | <strong>Points:</strong> {rep['points']} | <strong>File:</strong> {rep['file']}</p>")
                f.write("<div class='img-container'>")
                f.write(f"<div><strong>Ground DEM</strong><br><img src='{rep['dem_png']}' /></div>")
                f.write(f"<div><strong>Canopy Height</strong><br><img src='{rep['chm_png']}' /></div>")
                f.write("</div></div>")
                
            f.write("</body></html>")
            
    return success
