# e-Maap

**Measure Compliance. Protect Consumers.**

SIH prototype: one Government Next.js application, one native Expo Citizen/Inspector app and one FastAPI modular monolith. PostgreSQL is the operational database. The original SRS is in `docs/`; `docs/e-Maap_Contract_Decisions.md` records the six approved corrections. There are still exactly twelve capabilities.

## Delivery status

Source and deterministic fixtures are included. Web production build, TypeScript checks, Android JavaScript export and 24 domain/API tests have passed in the implementation environment. API integration tests use isolated SQLite databases; this does **not** certify PostgreSQL migration execution. PDF and editable DOCX generation are exercised by the integration test. See `docs/VALIDATION.md` for the precise gates and limitations.

An installable APK has **not** been produced. Gradle's distribution download failed with `Network is unreachable`; the environment also lacks the Android SDK and JDK compiler. The generated native Android project and reproducible build configuration are included. No substitute binary is supplied.

## Prerequisites

- Python 3.12, Node.js 22 LTS or later, npm, Docker Compose.
- Linux/WSL is recommended for PaddleOCR and WeasyPrint. Install your distribution's Pango, HarfBuzz and fonts packages for PDF output (Ubuntu: `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core`).
- Android Studio with Android SDK and JDK 17 for local APK builds, or an Expo account for EAS.

## Database and backend

Run from the repository root:

```bash
cp .env.example .env
docker compose up -d
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
alembic upgrade head
python -m app.seed --reset
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On Windows use `.venv\Scripts\activate`. Run reset **only against the isolated demo database**: it deletes existing records. Reseeding creates users, package snapshots, captured image fixtures, analysis, officer decisions, reports and a verified pattern proposal. Images are explicitly fictional demo labels.

Health: `http://localhost:8000/api/v1/health`. Interactive API documentation: `http://localhost:8000/docs`. The exported schema is `docs/openapi.json`.

For actual camera photographs install OCR support in the same virtual environment:

```bash
pip install -r backend/requirements-ocr.txt
```

Keep `OCR_PROVIDER=paddle` for actual captured images. Paddle downloads model weights on first use; warm the model cache while connected. For repeatable seeded-image demonstrations set `OCR_PROVIDER=fixture`. That mode recognises only byte-identical registered fixture images and explicitly fails unknown images; it does not simulate OCR success on arbitrary uploads. The seed routine itself requests the fixture provider explicitly.

## Government website

In a second terminal:

```bash
cd apps/web
cp .env.example .env.local
npm ci
npm run dev
```

Open `http://localhost:3000`. `API_BASE_URL` is a server-side URL for the shared FastAPI backend. The Next.js route is an authenticated transport proxy, not a second application backend. Session JWTs stay in an HttpOnly cookie.

```bash
npm run typecheck
npm run lint
npm run build
npm start
```

Production hosting should use HTTPS. All visual components, styles, fonts (system stack), icons and dependencies are in normal source/npm packages; no preview-only builder is required.

## Unified Android app

```bash
cd apps/mobile
cp .env.example .env
npm ci
npx expo prebuild --platform android --no-install
npx expo run:android
npx expo start --dev-client
```

This app requires a custom native development build because its SQLite store uses SQLCipher. **Expo Go cannot run this storage configuration.** `npx expo start` starts Metro, but a compatible native build must already be installed. Camera and foreground location permissions are requested by the app. Images remain in app-private storage; metadata and the retry queue reside in SQLCipher, with its key in SecureStore. Android backup is disabled.

Set `EXPO_PUBLIC_API_BASE_URL` to your computer's LAN address, for example `http://192.168.1.10:8000/api/v1`, before building. A phone's `localhost` is the phone itself. Android Emulator uses `http://10.0.2.2:8000/api/v1`. Keep the phone and computer on the same network and permit inbound port 8000. The included native plugin enables cleartext networking only for a configured HTTP demo URL; use HTTPS outside the local demo.

Only one assignment is retained as active offline work. Sign in online, open an assignment to download its configuration, then disconnect. Capture continues locally. Explicit upload/retry sends the same evidence ID and hash; a server acknowledgement is required before SYNCHRONISED. Analysis, verification, assignment changes and reports require connectivity. Inspector offline access requires the previously established Inspector credentials; Citizen mode cannot open departmental records.

## APK rebuild

Local, from the repository root after installing the Android SDK/JDK:

```bash
export ANDROID_HOME="$HOME/Android/Sdk"
export EXPO_PUBLIC_API_BASE_URL=http://192.168.1.10:8000/api/v1
bash scripts/build-apk.sh
```

Output: `e-Maap-demo.apk`. The native prototype uses the generated demo signing configuration. Use your own release signing credentials for any deployment beyond the demonstration.

Or, from `apps/mobile`, replace the placeholder backend URL in `eas.json` and run:

```bash
npx eas-cli login
npx eas-cli build --platform android --profile preview
```

The preview profile produces an APK, not an AAB. EAS requires your Expo account and may initialise its project identifier. Never commit credentials. To build the JS bundle independently: `npx expo export --platform android`.

## Demo accounts — DEMO ONLY

All use password **`EmaapDemo!2026`**:

| Role | Email |
|---|---|
| Government officer | `government@emaap.demo` |
| Inspector | `inspector@emaap.demo` |
| Second Inspector for permission tests | `inspector2@emaap.demo` |

Citizen scans use a separate scoped session. Complaint tracking also requires its private tracking token. Store the reference and token shown after submission.

## Tests and reset

```bash
source .venv/bin/activate
python -m pytest backend/tests -q
python -m unittest discover -s backend/tests -p test_domain.py -v
cd backend
python -m app.seed --reset
```

The test suite creates temporary SQLite databases and private temporary evidence directories. Application defaults and Docker remain PostgreSQL. PostgreSQL-only append-only triggers and deferred constraints must also be validated against PostgreSQL before claiming the full quality gate. Export the versioned PostgreSQL DDL with `alembic upgrade head --sql` in `backend`. Regenerate OpenAPI from the root with `python scripts/export_openapi.py`.

## Storage, configuration and bounded intelligence

Local storage is the default and needs no extra service. Optional MinIO:

```bash
docker compose --profile s3 up -d
python scripts/init-storage.py
```

Set `STORAGE_DRIVER=s3` afterward. The API controls all evidence/report downloads; no public bucket access is needed.

`seed/prototype-config.json` holds capture, OCR, fusion, presentation, upload, polling, retry and priority calibration defaults. `shared/contracts/runtime-config.ts` centralises the mobile password-derivation cost and JPEG capture quality. `backend/app/core/config.py` holds environment-driven credentials/runtime settings. Rule versions and fixture conditions live in PostgreSQL seed records. Presentation thresholds in the synthetic fixtures are **engineering fixtures, not universal statutory thresholds**; the consolidated statutory reference freeze and empirical device/OCR calibration are not certified by this build.

Optional multimodal fallback is off by default. If configured, it may produce source-linked low-confidence extraction candidates only. Deterministic code evaluates supported checks. Unsupported questions abstain. Citizen output is preliminary; only the assigned Inspector can verify a finding. Government approves systemic proposals and briefs separately from assignment actions.

## Demonstration sequence

1. Government: inspect the queue and historical report, search Repository by product/batch/rule and open exact evidence.
2. Inspector: open the assigned case, confirm profile, capture overlapping views and close-ups, inspect local quality guidance, disconnect/reconnect, upload, analyse, review source regions, confirm/correct declarations, separately decide potential findings, generate reports.
3. Government: review the existing verified pattern's factors and contributing cases. Approve it, create the systemic case, prepare and approve a brief, then assign follow-up explicitly.
4. Citizen: scan, review preliminary declarations, confirm/correct product/shop information, submit, retain reference and tracking token.
5. Listing review: upload `seed/fixtures/listing-one-side.png`. The response requires physical verification and never infers package absence from unseen areas.

The full source-to-screen/API/data/test mapping is in `docs/COMPLETION-MATRIX.md`.
