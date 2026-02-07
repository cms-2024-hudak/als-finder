import click
import logging
import json
from als_finder.core.input_manager import load_roi, ROIError
from als_finder.providers import OpenTopographyProvider, USGSProvider

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.group()
def cli():
    """LiDAR Data Finder CLI"""
    pass

@cli.command()
@click.option('--roi', required=True, help='Path to ROI file (GeoJSON/Shapefile) or BBox string')
@click.option('--start-date', help='Start date (YYYY-MM-DD)')
@click.option('--end-date', help='End date (YYYY-MM-DD)')
@click.option('--output', default='./output', help='Output directory')
@click.option('--provider', multiple=True, default=['opentopography', 'usgs'], help='Provider(s) to search')
def search(roi, start_date, end_date, output, provider):
    """Search for available LiDAR data."""
    logger.info(f"Searching for data in ROI: {roi}")
    logger.info(f"Providers: {provider}")
    
    try:
        # Parse and validate the ROI
        roi_geom = load_roi(roi)
        logger.info(f"ROI Loaded: {roi_geom.geom_type} with bounds {roi_geom.bounds}")
        
        # Initialize Providers
        active_providers = []
        if 'opentopography' in provider:
            active_providers.append(OpenTopographyProvider())
        if 'usgs' in provider:
            active_providers.append(USGSProvider())
        
        final_results = []
        for p in active_providers:
            # Check access first
            if not p.check_access():
                logger.warning(f"Skipping {p.__class__.__name__} due to access/auth issues.")
                continue

            try:
                logger.info(f"Searching {p.__class__.__name__}...")
                results = p.search(roi_geom)
                final_results.extend(results)
            except Exception as e:
                logger.error(f"Search failed for {p.__class__.__name__}: {e}")

        # Summary Output
        logger.info(f"Total Datasets Found: {len(final_results)}")
        
        # Dump to console or file (TODO: Format this better)
        print(json.dumps(final_results, indent=2, default=str))

        if output:
            # Save manifest
            # TODO: Improve this
            pass
        
    except ROIError as e:
        logger.error(str(e))
        raise click.ClickException(str(e))

@cli.command()
@click.option('--roi', required=True, help='Path to ROI file or BBox')
@click.option('--token', envvar='OPENTOPOGRAPHY_API_KEY', help='API Key (or set OPENTOPOGRAPHY_API_KEY)')
def download(roi, token):
    """Download LiDAR data."""
    logger.info("Starting download process...")
    pass

if __name__ == '__main__':
    cli()
