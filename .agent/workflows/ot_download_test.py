import sys
import os
import logging
from pathlib import Path
sys.path.append(str(Path("src").resolve()))

logging.basicConfig(level=logging.INFO)
from als_finder.providers.opentopography import OpenTopographyProvider
from shapely.geometry import box

# Create instance with dummy key for API syntax test
provider = OpenTopographyProvider(api_key=os.getenv("OPENTOPOGRAPHY_API_KEY", "dummy_key"))

output_dir = Path("/mnt/c/Users/gears/git/als-finder/scratch/opentopo_test")
output_dir.mkdir(parents=True, exist_ok=True)
roi = box(-120.00, 39.08, -119.95, 39.15)

try:
    provider.download(dataset_id="OTLAS.062022.26910.1", output_dir=output_dir, roi=roi)
except Exception as e:
    logging.error(f"Download formally aborted: {e}")

