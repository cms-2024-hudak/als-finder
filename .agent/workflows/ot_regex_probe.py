import requests
import re

url = "https://portal.opentopography.org/lidarDataset?en=OTLAS.062022.26910.1"
print(f"Fetching {url}...")

r = requests.get(url)
print(f"Status: {r.status_code}")

forms = re.findall(r'<form[^>]*>(.*?)</form>', r.text, flags=re.IGNORECASE | re.DOTALL)
for f in forms:
    if 'dataSearch' in f.lower():
        inputs = re.findall(r'<input[^>]+name="([^"]+)"[^>]+value="([^"]*)"', f)
        print("Inputs found:", dict(inputs))

        post_url = "https://portal.opentopography.org/dataSearch"
        payload = dict(inputs)
        payload.update({
            "minx": "-120.00",
            "miny": "39.08",
            "maxx": "-119.95",
            "maxy": "39.15",
            "format": "laz"
        })
        
        # We need cookies!
        s = requests.Session()
        s.cookies.update(r.cookies)
        r2 = s.post(post_url, data=payload, allow_redirects=False)
        print("Post Status:", r2.status_code)
        if 'Location' in r2.headers:
            print("Redirect:", r2.headers['Location'])
