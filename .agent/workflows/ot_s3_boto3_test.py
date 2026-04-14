import boto3
from botocore import UNSIGNED
from botocore.config import Config

s3 = boto3.client('s3', endpoint_url='https://opentopography.s3.sdsc.edu', config=Config(signature_version=UNSIGNED))
res = s3.list_objects_v2(Bucket='pc-bulk', Prefix='CA15_Fred/', MaxKeys=5)

for content in res.get('Contents', []):
    print(content['Key'], content['Size'])

