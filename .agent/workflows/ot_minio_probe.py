import requests
import xml.etree.ElementTree as ET

url = "https://opentopography.s3.sdsc.edu/pc-bulk/?prefix=CA15_Fred/"
r = requests.get(url)
root = ET.fromstring(r.text)
ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}

laz_files = []
for content in root.findall('s3:Contents', ns):
    key = content.find('s3:Key', ns).text
    if key.endswith('.laz') or key.endswith('.zip'):
        laz_files.append(f"https://opentopography.s3.sdsc.edu/pc-bulk/{key}")

print(f"Found {len(laz_files)} assets.")
for f in laz_files[:5]:
    print(f)
