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
    
    if not standardized_dir.exists():
        logger.error(f"Cannot generate quicklooks. Standardized directory missing: {standardized_dir}")
        return False
        
    laz_files = list(standardized_dir.rglob("*.copc.laz"))
    if not laz_files:
        logger.warning(f"No standardized .copc.laz files found for quicklook generation.")
        return False
        
    success = True
    for sample_file in laz_files:
        try:
            rel_path = sample_file.relative_to(standardized_dir)
            report_dir = reports_base_dir / rel_path.parent
            report_dir.mkdir(parents=True, exist_ok=True)
            
            output_tif = report_dir / f"{sample_file.stem}_dem.tif"
            output_png = report_dir / f"{sample_file.stem}_elevation_preview.png"
            
            # We build a PDAL pipeline that reads the COPC and writes a GDAL DEM preview
            # Using writers.gdal to rasterize elevation (Z) to visualize ground continuity
            pipeline = [
                str(sample_file.absolute()),
                {
                    "type": "writers.gdal",
                    "filename": str(output_tif.absolute()),
                    "output_type": "min", # Minimum elevation effectively shows the ground surface
                    "resolution": 2.0,    # 2 meter resolution is fast and sufficient for spot-checking
                    "data_type": "float32",
                    "window_size": 3
                }
            ]
            
            pdal_json = json.dumps(pipeline)
            
            logger.info(f"Generating 2D DEM for {sample_file.name} natively...")
            res = subprocess.run(['pdal', 'pipeline', '-s'], input=pdal_json.encode('utf-8'), capture_output=True, check=True)
            
            logger.info("Converting DEM to visible Hillshade PNG...")
            # Use gdaldem to create a hillshade PNG so it renders correctly in standard viewers and browsers
            subprocess.run([
                'gdaldem', 'hillshade', 
                str(output_tif.absolute()), 
                str(output_png.absolute()), 
                '-of', 'PNG', 
                '-z', '1.0', '-s', '1.0', '-az', '315.0', '-alt', '45.0'
            ], capture_output=True, check=True)
            
            # Clean up the intermediate TIF
            if output_tif.exists():
                output_tif.unlink()
                
            logger.info(f"[SUCCESS] Quicklook image generated: {output_png.absolute()}")
            
            # Generate a quick HTML wrapper
            html_path = report_dir / f"{sample_file.stem}_quicklook.html"
            with open(html_path, "w") as f:
                f.write(f"<html><head><title>LiDAR Quicklook: {sample_file.name}</title></head>")
                f.write("<body><h2>LiDAR QA/QC Quicklook</h2>")
                f.write(f"<p><strong>Source File:</strong> {sample_file.name}</p>")
                f.write("<h3>Elevation Minimum (Ground Approximation)</h3>")
                f.write("<p>If this image shows a continuous surface, the SMRF and coordinate projection succeeded. If it shows severe stripes or gaps, check the raw data boundaries.</p>")
                f.write(f"<img src='{output_png.name}' width='800' style='border: 1px solid black;'/>")
                f.write("</body></html>")
                
            logger.info(f"[SUCCESS] Quicklook HTML generated: {html_path.absolute()}")
        except subprocess.CalledProcessError as e:
            logger.error(f"PDAL Pipeline execution failed natively for quicklook {sample_file.name}: {e.stderr.decode('utf-8')}")
            success = False
        except Exception as e:
            logger.error(f"Quicklook generation failed natively for {sample_file.name}: {e}")
            success = False
            
    return success
