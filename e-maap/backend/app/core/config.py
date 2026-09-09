from pathlib import Path
import json
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
PROTOTYPE = json.loads((ROOT / 'seed/prototype-config.json').read_text())

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(ROOT / '.env', '.env'), extra='ignore')
    database_url: str = 'postgresql+psycopg://emaap:emaap_local@localhost:5432/emaap'
    jwt_secret: str = 'change-this-local-demo-secret-before-any-deployment-48chars'
    jwt_ttl_minutes: int = 120
    cors_origins: str = 'http://localhost:3000'
    storage_driver: str = 'local'
    storage_root: str = str(ROOT / 'storage')
    s3_endpoint_url: str = 'http://localhost:9000'
    s3_bucket: str = 'emaap-evidence'
    s3_access_key: str = 'emaap_local'
    s3_secret_key: str = 'emaap_local_storage_password'
    ocr_provider: str = 'paddle'
    demo_mode: bool = True
    vision_fallback_enabled: bool = False
    vision_endpoint: str = ''
    vision_api_key: str = ''
    vision_model: str = ''

settings = Settings()
