from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.evidence.storage import S3Storage
from app.core.config import settings
client=S3Storage().client
if not any(b['Name']==settings.s3_bucket for b in client.list_buckets()['Buckets']):client.create_bucket(Bucket=settings.s3_bucket)
print('Evidence bucket ready:',settings.s3_bucket)
