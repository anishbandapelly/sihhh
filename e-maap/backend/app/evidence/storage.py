from pathlib import Path
import os
from app.core.config import settings
from app.core.errors import DomainError

class LocalStorage:
    def __init__(self): self.root=Path(settings.storage_root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
    def path(self,key):
        path=(self.root/key).resolve()
        if not path.is_relative_to(self.root): raise ValueError('Invalid object key')
        return path
    def put(self,key,data,mime):
        path=self.path(key); path.parent.mkdir(parents=True,exist_ok=True)
        tmp=path.with_suffix(path.suffix+'.tmp')
        with tmp.open('wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    def get(self,key): return self.path(key).read_bytes()

class S3Storage:
    def __init__(self):
        import boto3
        self.client=boto3.client('s3',endpoint_url=settings.s3_endpoint_url,aws_access_key_id=settings.s3_access_key,aws_secret_access_key=settings.s3_secret_key)
    def put(self,key,data,mime):
        self.client.put_object(Bucket=settings.s3_bucket,Key=key,Body=data,ContentType=mime)
    def get(self,key): return self.client.get_object(Bucket=settings.s3_bucket,Key=key)['Body'].read()

def storage(): return S3Storage() if settings.storage_driver=='s3' else LocalStorage()
