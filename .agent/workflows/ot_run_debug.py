import sys
from pathlib import Path
from shapely.geometry import box
sys.path.insert(0, str(Path('src').resolve()))
from als_finder.providers.opentopography import OpenTopographyProvider

p = OpenTopographyProvider()
roi = box(-120.25, 38.80, -120.21, 38.85)
d = {'alternateName': 'TAHOE'}
print("Starting Extract...")
urls = p.get_fetch_urls(d, roi, Path('scratch/TEST_HIVE/'))
print("Extracted URL Count:", len(urls))
for u in urls:
    print(u)
