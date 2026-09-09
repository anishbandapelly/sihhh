"""Package the complete source, excluding installed dependencies and local secrets."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / 'e-Maap-prototype-source.zip'
EXCLUDED = {'.git', '.venv', 'node_modules', '.next', '.expo', '.gradle',
            '__pycache__', '.pytest_cache', 'dist', 'build', 'storage'}

with ZipFile(OUTPUT, 'w', ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in EXCLUDED for part in relative.parts):
            continue
        if path.name.startswith('.env') and path.name != '.env.example':
            continue
        if path.name == 'local.properties' or path.suffix in ('.pyc', '.tsbuildinfo', '.db', '.sqlite'):
            continue
        archive.write(path, Path('e-maap') / relative)

with ZipFile(OUTPUT) as archive:
    assert archive.testzip() is None
    required = ['README.md', 'apps/web/package.json', 'apps/mobile/App.tsx',
                'apps/mobile/android/gradle/wrapper/gradle-wrapper.jar',
                'backend/app/main.py', 'docs/openapi.json', 'docker-compose.yml']
    assert all('e-maap/' + name in archive.namelist() for name in required)
    print(f'{len(archive.namelist())} files; {OUTPUT.stat().st_size:,} bytes')
print(OUTPUT)
print('SHA-256:', hashlib.sha256(OUTPUT.read_bytes()).hexdigest())
