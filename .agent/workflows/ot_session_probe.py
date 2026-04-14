import requests
from bs4 import BeautifulSoup

s = requests.Session()
url = "https://portal.opentopography.org/lidarDataset?en=OTLAS.062022.26910.1"

print(f"Loading {url}...")
r = s.get(url)
soup = BeautifulSoup(r.text, 'html.parser')

inputs = {}
for form in soup.find_all('form'):
    if 'dataSearch' in form.get('action', ''):
        for inp in form.find_all('input'):
            if inp.get('name'):
                inputs[inp['name']] = inp.get('value', '')

print(f"Form Fields Found: {inputs.keys()}")

inputs['minx'] = "-120.00"
inputs['miny'] = "39.08"
inputs['maxx'] = "-119.95"
inputs['maxy'] = "39.15"

post_url = "https://portal.opentopography.org/dataSearch"
r_post = s.post(post_url, data=inputs, allow_redirects=False)

print(f"POST Status: {r_post.status_code}")
if r_post.status_code in [301, 302, 303]:
    print(f"Redirecting to: {r_post.headers.get('Location')}")
else:
    print(r_post.text[:500])
