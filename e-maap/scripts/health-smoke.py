"""Starts a real API process against an existing validation database, checks health, stops it."""
import subprocess,sys,time,urllib.request,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--app-dir',str(root/'backend'),'--host','127.0.0.1','--port','8011'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
try:
 deadline=time.monotonic()+15
 while True:
  try:
   result=json.loads(urllib.request.urlopen('http://127.0.0.1:8011/api/v1/health',timeout=1).read());assert result['status']=='ok';print(json.dumps(result));break
  except OSError:
   if time.monotonic()>deadline:raise
   time.sleep(.2)
finally:p.terminate();p.wait(timeout=10)
