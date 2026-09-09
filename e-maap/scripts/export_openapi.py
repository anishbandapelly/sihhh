from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.main import app
(ROOT/'docs/openapi.json').write_text(json.dumps(app.openapi(),indent=2)+'\n')
