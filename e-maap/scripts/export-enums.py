from pathlib import Path
import sys,json
from enum import StrEnum
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from app.core import enums
(ROOT/'shared/enums/canonical.json').write_text(json.dumps({name:[str(x) for x in value] for name,value in vars(enums).items() if isinstance(value,type) and issubclass(value,StrEnum) and value is not StrEnum},indent=2)+'\n')
