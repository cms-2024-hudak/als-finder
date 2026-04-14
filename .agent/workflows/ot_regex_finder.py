import requests
import xml.etree.ElementTree as ET

url = "https://opentopography.s3.sdsc.edu/pc-bulk/"
marker = ""
ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}

found = set()
pages = 0
while True:
    q = f"{url}?marker={marker}" if marker else url
    r = requests.get(q)
    pages += 1
    root = ET.fromstring(r.text)
    
    for content in root.findall('s3:Contents', ns):
        key = content.find('s3:Key', ns).text
        folder = key.split('/')[0]
        if "fred" in folder.lower() or "tahoe" in folder.lower() or "ca15" in folder.lower() or "otlas" in folder.lower():
            found.add(folder)
            
    if root.find('s3:IsTruncated', ns).text == 'false':
        break
    marker = root.find('s3:NextMarker', ns).text
    if pages > 20: # fail safe
        break

print("Found Folders:", found)
