import requests
import json

url = "https://portal.opentopography.org/dataSearch"
payload = {
    "action": "submit",
    "dataset": "OTLAS.062022.26910.1",
    "minx": "-120.00",
    "miny": "39.08",
    "maxx": "-119.95",
    "maxy": "39.15",
    "format": "laz"
}

s = requests.Session()
r = s.post(url, data=payload, allow_redirects=False)

print(f"Status Code: {r.status_code}")
print(f"Headers: {r.headers}")
if r.status_code == 302:
    print(f"Redirect Location: {r.headers.get('Location')}")
else:
    print(r.text[:500])

