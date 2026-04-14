import sys
from pathlib import Path
sys.path.append(str(Path("src").resolve()))

from als_finder.providers.opentopography import OpenTopographyProvider
from als_finder.core.input_manager import load_roi

roi = load_roi("-120.00, 39.08, -119.95, 39.15") # East Shore Tahoe
provider = OpenTopographyProvider()
if not provider.api_key:
    # Hardcode bypass for debugging if missing
    import os
    provider.api_key = os.getenv("OPENTOPOGRAPHY_API_KEY", "dummy")

datasets = provider.search(roi=roi)
for d in datasets:
    print("------------------------------------------")
    print(d['dataset_id'], d['name'], getattr(d, 'url', d.get('url')))
    print(d['raw_metadata'])
