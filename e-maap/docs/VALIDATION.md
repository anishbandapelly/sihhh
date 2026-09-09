# Validation record

This is a prototype implementation record, not a claim of production or legal certification.

| Gate | Result |
|---|---|
| Python source compilation | Passed |
| Backend dependencies | Installed |
| Unit/domain/API tests | 24 passed using isolated SQLite; includes Inspector-to-report and Citizen-to-tracking paths |
| API process / health | Uvicorn started; real HTTP health returned database connected against the isolated test DB |
| Actual PDF and DOCX output | Generated and downloaded by API integration test; byte signatures checked |
| OpenAPI | Exported from actual FastAPI application; 42 paths |
| PostgreSQL DDL generation | Alembic offline generation passed; 373 lines |
| PostgreSQL empty-DB migration and seed | Not executed: no PostgreSQL/Docker; system package installer fails permission operations |
| Web dependencies / TypeScript | Installed / passed |
| Web production build | Passed, Next.js 16.3.4 |
| Web lint | Passed with no errors or warnings |
| Mobile dependencies / TypeScript | Installed / passed |
| Android native prebuild | Passed; generated project included |
| Android JS/Hermes export | Passed |
| Installable APK | Blocked: Gradle distribution download reports Network is unreachable; SDK and javac absent |
| Device QA | Not executed: no emulator/device/APK available |
| PaddleOCR on real camera fixtures | Not validated; deterministic provider tested only on labelled synthetic fixtures |
| VUI-01–08 full visual/device acceptance | Not certified |

The native app has not been installed on a physical phone here. Camera, permission, keyboard, SQLCipher startup, source-image display, secure storage and reconnect behavior still require that gate. JS export does not substitute for native validation.

API tests exercise server RBAC, role-negative repository access, another Inspector's case denial, content-hash rejection, evidence retry uniqueness, human report gates, grounded abstention, persisted brief approval, source-linked declaration review, actual report downloads, verified pattern approval and follow-up transitions, citizen-owned scan isolation, preliminary result submission/tracking, and listing evidence gaps. Pure domain tests separately exercise coverage, uncertainty, conflicts and presentation checks. PostgreSQL triggers are generated but have not been exercised by SQLite.

Known product validation work: real OCR/model-weight startup, rule-source consolidation freeze, empirical threshold calibration and real phone usability review. These are not silently replaced with fixture results.
