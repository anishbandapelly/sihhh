import os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
os.environ['DATABASE_URL']='sqlite:///'+str(Path(tempfile.mkdtemp(prefix='emaap-tests-'))/'test.sqlite')
os.environ['STORAGE_ROOT']=tempfile.mkdtemp(prefix='emaap-test-evidence-');os.environ['OCR_PROVIDER']='fixture';os.environ['DEMO_MODE']='true'
import pytest
from fastapi.testclient import TestClient
from app.core.db import Base,engine,SessionLocal
from app.main import app
from app.seed import seed,stable
@pytest.fixture(scope='session')
def client():
 Base.metadata.create_all(engine);seed()
 with TestClient(app) as c:yield c
@pytest.fixture
def inspector(client):
 r=client.post('/api/v1/auth/login',json={'email':'inspector@emaap.demo','password':'EmaapDemo!2026'});assert r.status_code==200,r.text
 return {'Authorization':'Bearer '+r.json()['access_token']}
@pytest.fixture
def government(client):
 r=client.post('/api/v1/auth/login',json={'email':'government@emaap.demo','password':'EmaapDemo!2026'});assert r.status_code==200,r.text
 return {'Authorization':'Bearer '+r.json()['access_token']}
@pytest.fixture
def citizen(client):return {'Authorization':'Bearer '+client.post('/api/v1/auth/citizen-session').json()['access_token']}
