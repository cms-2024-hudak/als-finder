import urllib.request
import json
import concurrent.futures
from time import time

def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        return json.loads(urllib.request.urlopen(req, timeout=5).read().decode())
    except:
        return None

def test_fetch_all():
    catalog_url = "https://noaa-nos-coastal-lidar-pds.s3.us-east-1.amazonaws.com/entwine/stac/catalog.json"
    print(f"Fetching {catalog_url}...")
    catalog = fetch_json(catalog_url)
    if not catalog: return
    
    links = [l['href'] for l in catalog.get('links', []) if l.get('rel') == 'item']
    print(f"Found {len(links)} items to fetch.")
    
    base_url = catalog_url.rsplit('/', 1)[0]
    full_urls = [base_url + "/" + link.lstrip('./') for link in links]
    
    print("Starting concurrent fetch of first 100 as test...")
    t0 = time()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_json, url): url for url in full_urls[:100]}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res: results.append(res)
            
    print(f"Fetched {len(results)} items in {time() - t0:.2f} seconds.")
    if results:
        print("Sample item:", results[0].get('id'), "bbox:", results[0].get('bbox'))

if __name__ == "__main__":
    test_fetch_all()
