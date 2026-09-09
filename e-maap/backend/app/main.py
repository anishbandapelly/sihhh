from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.models import AnalysisRun, AnalysisStatus, Report, ReportStatus, now
from app.core.errors import DomainError
from app.api.routes import router

@asynccontextmanager
async def lifespan(app):
    if not settings.demo_mode and settings.jwt_secret.startswith('change-this'):
        raise RuntimeError('Set a deployment JWT_SECRET before disabling DEMO_MODE.')
    # Jobs interrupted by a process restart must visibly fail and be retried.
    try:
        with SessionLocal() as db:
            for run in db.scalars(select(AnalysisRun).where(AnalysisRun.status.in_([AnalysisStatus.QUEUED,AnalysisStatus.RUNNING]))):
                run.status=AnalysisStatus.FAILED; run.failure_code='SERVER_RESTARTED'; run.completed_at=now()
            for report in db.scalars(select(Report).where(Report.status.in_([ReportStatus.QUEUED,ReportStatus.GENERATING]))):
                report.status=ReportStatus.FAILED; report.failure_code='SERVER_RESTARTED'
            db.commit()
    except Exception:
        # /health reports a database problem; migration/setup errors are not hidden.
        pass
    yield

app=FastAPI(title='e-Maap API',version='1.0.0',description='Bounded SIH prototype. Source evidence, declaration review and legal finding verification remain distinct.',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[s.strip() for s in settings.cors_origins.split(',')],allow_credentials=False,allow_methods=['GET','POST','PUT','PATCH'],allow_headers=['Authorization','Content-Type','X-Tracking-Token'])
app.include_router(router)

@app.exception_handler(DomainError)
async def domain_error(request:Request,exc:DomainError):
    return JSONResponse(status_code=exc.status,content={'code':exc.code,'message':exc.message,'retryable':exc.retryable})

@app.exception_handler(RequestValidationError)
async def validation_error(request:Request,exc:RequestValidationError):
    return JSONResponse(status_code=422,content={'code':'VALIDATION_ERROR','message':'Check the highlighted request fields.','field_errors':[{'field':'.'.join(str(x) for x in e['loc']),'message':e['msg']} for e in exc.errors()],'retryable':False})

@app.exception_handler(IntegrityError)
async def integrity_error(request:Request,exc:IntegrityError):
    return JSONResponse(status_code=409,content={'code':'DUPLICATE_DECISION','message':'The record changed or this operation conflicts with an existing record. Refresh before retrying.','retryable':False})

@app.get('/api/v1/health',tags=['Operations'])
def health():
    try:
        with SessionLocal() as db: db.execute(text('SELECT 1'))
        return {'status':'ok','database':'connected','ocr_provider':settings.ocr_provider,'demo_mode':settings.demo_mode}
    except Exception:
        return JSONResponse(status_code=503,content={'status':'unavailable','database':'not_connected','message':'Start PostgreSQL and apply the Alembic migration.'})
