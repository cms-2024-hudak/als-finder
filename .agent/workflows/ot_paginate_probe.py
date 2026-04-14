import requests
import xml.etree.ElementTree as ET

url = "https://opentopography.s3.sdsc.edu/pc-bulk/"
marker = ""
ns = {'s3': 'http://s3.amazonaws.com/doc/2006-03-01/'}

found = False
while True:
    q = f"{url}?marker={marker}" if marker else url
    r = requests.get(q)
    root = ET.fromstring(r.text)
    
    for content in root.findall('s3:Contents', ns):
        key = content.find('s3:Key', ns).text
        if "CA15_Fred" in key:
            print("FOUND CA15_Fred:", key)
            found = True
            break
            
    if found or root.find('s3:IsTruncated', ns).text == 'false':
        break
    marker = root.find('s3:NextMarker', ns).text

