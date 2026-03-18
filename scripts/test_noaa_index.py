import urllib.request
from html.parser import HTMLParser
import re

class NOAATableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_tr = False
        self.in_td = False
        self.current_links = []
        self.datasets = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_tr = True
            self.current_links = []
        elif tag == "td" and self.in_tr:
            self.in_td = True
        elif tag == "a" and self.in_td:
            for attr in attrs:
                if attr[0] == "href":
                    self.current_links.append(attr[1])

    def handle_endtag(self, tag):
        if tag == "td":
            self.in_td = False
        elif tag == "tr":
            self.in_tr = False
            # Find the tile index shapefile link and the bulk download link
            tile_index = next((l for l in self.current_links if "tileindex" in l.lower() and l.endswith(".zip")), None)
            laz_dir = next((l for l in self.current_links if "geoid" in l.lower() and l.endswith("/")), None)
            
            if tile_index and laz_dir:
                # Extract mission ID from the URL (usually the number directory)
                m = re.search(r'geoid\d+/(\d+)/', laz_dir)
                mission_id = m.group(1) if m else "unknown"
                self.datasets.append({
                    "id": mission_id,
                    "laz_dir": laz_dir,
                    "tile_index": tile_index
                })

def parse_noaa_index():
    url = "https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/laz/index.html"
    print(f"Streaming {url}...")
    parser = NOAATableParser()
    
    with urllib.request.urlopen(url) as response:
        # Read the whole index (it's big but manageable for a one-time build)
        html = response.read().decode('utf-8', errors='ignore')
        parser.feed(html)
            
    print(f"Found {len(parser.datasets)} valid datasets with LAZ and Tile Indices.")
    for d in parser.datasets[:5]:
        print(f" - Mission {d['id']}: {d['laz_dir']}")

if __name__ == "__main__":
    parse_noaa_index()
