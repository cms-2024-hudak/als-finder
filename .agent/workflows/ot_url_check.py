import requests

minx, miny, maxx, maxy = -120.301, 38.991, -119.957, 39.191
url = f"https://portal.opentopography.org/API/otCatalog?productFormat=PointCloud&minx={minx}&miny={miny}&maxx={maxx}&maxy={maxy}&detail=true&outputFormat=json"
r = requests.get(url)
data = r.json()
print(f"Found {len(data['Datasets'])} datasets.")

for d in data['Datasets']:
    meta = d['Dataset']
    ident = meta['identifier']['value'] if isinstance(meta.get('identifier'), dict) else meta.get('identifier')
    print(f"ID: {ident}")
    distribution = meta.get('distribution', [])
    for dist in distribution:
        print(f"  Dist: {dist.get('contentUrl')} ({dist.get('@type')})")
