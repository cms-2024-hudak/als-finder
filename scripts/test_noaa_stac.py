import boto3
from botocore import UNSIGNED
from botocore.config import Config
import json
from shapely.geometry import box

def check_noaa_stac(roi_bounds):
    print("Initializing S3 client...")
    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    paginator = s3.get_paginator("list_objects_v2")
    
    print("Listing STAC items in noaa-nos-coastal-lidar-pds...")
    pages = paginator.paginate(Bucket="noaa-nos-coastal-lidar-pds", Prefix="entwine/stac/")
    
    roi_box = box(*roi_bounds)
    matching_datasets = []
    
    count = 0
    # Just check the first 50 as a proof of concept
    for page in pages:
        for obj in page.get("Contents", []):
            if not obj["Key"].endswith(".json") or obj["Key"].endswith("catalog.json"):
                continue
                
            count += 1
            if count > 50:
                break
                
            try:
                res = s3.get_object(Bucket="noaa-nos-coastal-lidar-pds", Key=obj["Key"])
                data = json.loads(res["Body"].read())
                
                # Check spatial extent
                bbox = data.get("extent", {}).get("spatial", {}).get("bbox", [[]])[0]
                if not bbox or len(bbox) != 4:
                    continue
                    
                item_box = box(*bbox)
                if roi_box.intersects(item_box):
                    print(f"Match found: {data.get('id')} - {data.get('title')}")
                    # Find LAZ data URL
                    for link in data.get("links", []):
                        if link.get("rel") == "item":
                            matching_datasets.append({
                                "id": data.get("id"),
                                "url": link.get("href")
                            })
                            
            except Exception as e:
                print(f"Error parsing {obj['Key']}: {e}")
                
        if count > 50:
            break
            
    print(f"Checked {count} files. Found {len(matching_datasets)} matches.")
    return matching_datasets

if __name__ == "__main__":
    # Test Oregon BBox
    check_noaa_stac([-123.5, 44.5, -122.5, 45.5])
