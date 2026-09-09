from datetime import date, datetime, timezone
from uuid import UUID
from collections import Counter
import secrets, hashlib, hmac
from fastapi import APIRouter, Depends, UploadFile, File, Form, BackgroundTasks, Query, Header
from fastapi.responses import Response
from sqlalchemy import select
from app.core.models import *
from app.core.db import get_db
from app.core.config import PROTOTYPE
from app.core.errors import require, DomainError
from app.auth.service import actor, citizen, roles, case_access, password_matches, issue_token, rate_protect
from app.audit.service import audit
from app.cases.service import create_case, snapshot, records, summary, detail, plan_response, priority, row
from app.evidence.service import register, receive, sync_complete, capture_open, update_coverage
from app.evidence.storage import storage
from app.compliance.service import queue_analysis, run_analysis, map_response
from app.verification.service import review_declaration, verify_finding
from app.reports.service import queue_report, generate_report
from app.patterns.service import pattern_summary, pattern_decision, systemic_case, update_followup
from app.copilot.service import query as copilot_query, draft_brief, approve_brief, require_approved_brief, analyse_listing
from app.repository.service import history_query, report_search
from .schemas import *

router=APIRouter(prefix='/api/v1')
gov=roles(Role.GOVERNMENT_OFFICER)
inspector=roles(Role.INSPECTOR)
officer=roles(Role.INSPECTOR,Role.GOVERNMENT_OFFICER)

def found(db,model,identifier):
    obj=db.get(model,str(identifier))
    if obj is None: raise DomainError('NOT_FOUND','Record not found.',404)
    return obj

def ev_response(e):
    return {'id':e.id,'case_id':e.case_id,'sequence_no':e.sequence_no,'sha256':e.sha256,'captured_at':e.captured_at,
        'sync_status':str(e.sync_status),'quality':e.quality_json,'storage_available':bool(e.storage_key),'synced_at':e.synced_at}

@router.post('/auth/login',tags=['Authentication'],dependencies=[Depends(rate_protect)])
def login(body:Login,db=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==body.email.lower().strip()))
    require(user and user.active and password_matches(body.password,user.password_hash),'Email or password is incorrect.','AUTH_REQUIRED',401)
    return {'access_token':issue_token(user.id,'officer',user.role),'token_type':'bearer','role':str(user.role),'name':user.name,'id':user.id}

@router.post('/auth/citizen-session',tags=['Citizen'],dependencies=[Depends(rate_protect)])
def citizen_session():
    sid=uid()
    return {'access_token':issue_token(sid,'citizen'),'token_type':'bearer','session_id':sid}

@router.get('/me',tags=['Authentication'])
def me(who=Depends(actor)):
    return {'id':who.subject,'name':who.name,'role':who.role,'session_type':who.kind}

@router.post('/citizen/scans',tags=['Citizen'],status_code=201,dependencies=[Depends(rate_protect)])
def scan(body:ScanCreate,who=Depends(citizen),db=Depends(get_db)):
    require(body.package_family!=PackageFamily.OTHER_PACKAGE,'Select carton, bottle or pouch.','VALIDATION_ERROR',422)
    case=create_case(db,who,body.package_family,body.product_name)
    return {'scan_id':case.id,'package_family':str(body.package_family),'profile':PROTOTYPE['profiles'][str(body.package_family)],
        'capture_configuration':PROTOTYPE['capture'],'upload_configuration':PROTOTYPE['upload'],'analysis_configuration':PROTOTYPE['analysis'],
        'declarations':[{'id':g,'name':name} for g,name in GROUPS.items()]}

@router.post('/citizen/scans/{scan_id}/analysis',tags=['Citizen'],status_code=202)
def citizen_analyse(scan_id:UUID,tasks:BackgroundTasks,who=Depends(citizen),db=Depends(get_db)):
    case=case_access(db,who,scan_id,True)
    require(not case.public_tracking_token_hash,'The complaint has already been submitted.')
    run,created=queue_analysis(db,who,case,True)
    if created: tasks.add_task(run_analysis,run.id,True)
    return {'analysis_run_id':run.id,'status':str(run.status)}

@router.get('/citizen/analysis/{run_id}',tags=['Citizen'])
def citizen_analysis_status(run_id:UUID,who=Depends(citizen),db=Depends(get_db)):
    run=found(db,AnalysisRun,run_id); case_access(db,who,run.case_id,True)
    event=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==run.id,AuditEvent.event_type=='ANALYSIS_QUEUED'))
    require(event and event.payload.get('citizen_only'),'This analysis is not a citizen scan.','FORBIDDEN_ROLE_OR_CASE',403)
    return {'id':run.id,'status':str(run.status),'retryable':run.status==AnalysisStatus.FAILED,'message':'Try another photo or retry the scan.' if run.status==AnalysisStatus.FAILED else 'Reading your package photos.'}

@router.get('/citizen/scans/{scan_id}/result',tags=['Citizen'])
def citizen_result(scan_id:UUID,who=Depends(citizen),db=Depends(get_db)):
    case=case_access(db,who,scan_id,True)
    result=db.scalar(select(AuditEvent).where(AuditEvent.case_id==case.id,AuditEvent.event_type=='CITIZEN_PRELIMINARY_RESULT').order_by(AuditEvent.created_at.desc()))
    require(result is not None,'The preliminary result is not ready.')
    # This payload was constructed with an explicit public allowlist; never return the audit row.
    return result.payload

@router.post('/citizen/complaints',tags=['Citizen'],dependencies=[Depends(rate_protect)])
def complaint(body:ComplaintCreate,who=Depends(citizen),db=Depends(get_db)):
    case=case_access(db,who,body.scan_id,True)
    if not case.public_tracking_token_hash:
        result=db.scalar(select(AuditEvent.id).where(AuditEvent.case_id==case.id,AuditEvent.event_type=='CITIZEN_PRELIMINARY_RESULT'))
        require(result is not None,'Review the preliminary result before submitting.')
        p=snapshot(db,case.id)
        require(body.product_snapshot.package_family==p.package_family,'The confirmed package must use the captured profile.','VALIDATION_ERROR',422)
        for k,v in body.product_snapshot.model_dump().items(): setattr(p,k,v)
        case.shop_name=body.shop_name; case.shop_location=body.shop_location; case.status=CaseStatus.INTAKE
        audit(db,who,case.id,'CITIZEN_CONFIRMED','case',case.id,{'product':body.product_snapshot.model_dump(mode='json'),'declaration_corrections':body.declaration_corrections,'confirmed':True})
    token=secrets.token_urlsafe(32); case.public_tracking_token_hash=hashlib.sha256(token.encode()).hexdigest()
    return {'reference':'EM-'+case.id,'tracking_token':token,'status':PUBLIC_STATUS[str(case.status)],'message':'Your report has been submitted for review.'}

@router.get('/citizen/complaints/{reference}/status',tags=['Citizen'])
def tracking(reference:str,x_tracking_token:str=Header(default=''),who=Depends(citizen),db=Depends(get_db)):
    try: identifier=str(UUID(reference.removeprefix('EM-')))
    except ValueError: raise DomainError('NOT_FOUND','Reference not found.',404)
    case=found(db,Case,identifier)
    require(case.public_tracking_token_hash and hmac.compare_digest(hashlib.sha256(x_tracking_token.encode()).hexdigest(),case.public_tracking_token_hash),'Use the tracking token issued with this complaint.','FORBIDDEN_ROLE_OR_CASE',403)
    return {'reference':reference,'status':PUBLIC_STATUS[str(case.status)],'updated_at':case.updated_at}

@router.get('/assignments/me',tags=['Inspector'])
def my_assignments(who=Depends(inspector),db=Depends(get_db)):
    return {'items':[{'assignment':row(a),'case':summary(db,db.get(Case,a.case_id))} for a in db.scalars(select(Assignment).where(Assignment.inspector_id==who.subject))],
        'followups':[row(f) for f in db.scalars(select(Followup).where(Followup.assigned_to==who.subject))]}

@router.get('/cases/{case_id}',tags=['Cases'])
def case_detail(case_id:UUID,who=Depends(officer),db=Depends(get_db)):
    return detail(db,case_access(db,who,case_id))

@router.get('/cases/{case_id}/evidence-plan',tags=['Inspector'])
def evidence_plan(case_id:UUID,who=Depends(inspector),db=Depends(get_db)):
    case=case_access(db,who,case_id)
    return plan_response(db,case)

@router.post('/assignments/{assignment_id}/download',tags=['Inspector'])
def download_assignment(assignment_id:UUID,who=Depends(inspector),db=Depends(get_db)):
    assignment=found(db,Assignment,assignment_id)
    require(assignment.inspector_id==who.subject,'This assignment is not authorised.','FORBIDDEN_ROLE_OR_CASE',403)
    case=case_access(db,who,assignment.case_id)
    if assignment.status==AssignmentStatus.ASSIGNED: assignment.status=AssignmentStatus.DOWNLOADED
    assignment.downloaded_at=now()
    audit(db,who,case.id,'ASSIGNMENT_DOWNLOADED','assignment',assignment.id,{'configuration_version':PROTOTYPE['version']})
    return {'assignment':row(assignment),'case':summary(db,case),'capture':plan_response(db,case)}

@router.patch('/cases/{case_id}/capture-profile',tags=['Inspector'])
def profile(case_id:UUID,body:ProfileChange,who=Depends(inspector),db=Depends(get_db)):
    case=case_access(db,who,case_id); capture_open(db,case)
    require(not records(db,EvidenceItem,case_id=case.id,source_type=EvidenceSource.FIELD_CAPTURE),'Select and confirm the capture profile before field evidence registration.')
    p=snapshot(db,case.id); before=row(p); p.package_family=body.package_family
    if body.product_snapshot:
        for k,v in body.product_snapshot.model_dump().items(): setattr(p,k,v)
        p.package_family=body.package_family
        p.officer_confirmed_json={k:{'value':getattr(p,k),'officer_id':who.subject,'time':now().isoformat()} for k in ('product_name','manufacturer','batch_lot') if getattr(p,k)}
    for plan in records(db,EvidencePlanItem,case_id=case.id):
        plan.coverage_state=CoverageState.PLANNED; plan.absence_eligible=False; plan.next_capture_prompt=PROTOTYPE['profiles'][str(body.package_family)]['prompts'][0]
    audit(db,who,case.id,'CAPTURE_PROFILE_CONFIRMED','case',case.id,{'before':before,'after':row(p),'reason':body.reason})
    return plan_response(db,case)

@router.post('/cases/{case_id}/coverage-confirmations',tags=['Inspector'])
def manual_coverage(case_id:UUID,body:CoverageConfirmation,who=Depends(inspector),db=Depends(get_db)):
    case=case_access(db,who,case_id); capture_open(db,case)
    require(snapshot(db,case.id).package_family==PackageFamily.OTHER_PACKAGE,'Manual completeness is reserved for Other Package mode.')
    require(all(area.strip() for area in body.inspected_areas),'Describe the inspected areas.','VALIDATION_ERROR',422)
    for eid in body.evidence_ids:
        e=found(db,EvidenceItem,eid)
        require(e.case_id==case.id and e.source_type==EvidenceSource.FIELD_CAPTURE and e.sync_status==SyncStatus.SYNCHRONISED and e.quality_json.get('usable'),'Use usable synchronised field photographs from this case.')
    for pid in body.plan_item_ids:
        plan=found(db,EvidencePlanItem,pid); require(plan.case_id==case.id,'Plan item belongs to another case.','FORBIDDEN_ROLE_OR_CASE',403)
        audit(db,who,case.id,'MANUAL_COVERAGE_CONFIRMED','evidence_plan',plan.id,{'evidence_ids':[str(i) for i in body.evidence_ids],'inspected_areas':body.inspected_areas,'reason':body.reason,'officer':who.name})
    update_coverage(db,case)
    return plan_response(db,case)

@router.post('/cases/{case_id}/evidence',tags=['Evidence'])
def create_evidence(case_id:UUID,body:EvidenceCreate,who=Depends(actor),db=Depends(get_db)):
    require(who.role==Role.INSPECTOR or who.kind=='citizen','Only a capture pathway can register field evidence.','FORBIDDEN_ROLE_OR_CASE',403)
    case=case_access(db,who,case_id,who.kind=='citizen')
    return ev_response(register(db,who,case,body))

@router.put('/evidence/{evidence_id}/content',tags=['Evidence'])
async def upload_evidence(evidence_id:UUID,image:UploadFile=File(...),who=Depends(actor),db=Depends(get_db)):
    e=found(db,EvidenceItem,evidence_id)
    require(who.role==Role.INSPECTOR or who.kind=='citizen','This upload route is restricted to capture pathways.','FORBIDDEN_ROLE_OR_CASE',403)
    case_access(db,who,e.case_id,who.kind=='citizen')
    require((who.kind=='citizen' and e.source_type==EvidenceSource.CITIZEN_UPLOAD) or (who.role==Role.INSPECTOR and e.source_type==EvidenceSource.FIELD_CAPTURE),'Evidence source does not match the capture pathway.','FORBIDDEN_ROLE_OR_CASE',403)
    data=await image.read(PROTOTYPE['upload']['max_image_bytes']+1)
    return ev_response(receive(db,who,e,data))

@router.get('/evidence/{evidence_id}/content',tags=['Evidence'])
def evidence_bytes(evidence_id:UUID,who=Depends(actor),db=Depends(get_db)):
    e=found(db,EvidenceItem,evidence_id); case_access(db,who,e.case_id,who.kind=='citizen')
    if who.kind=='citizen': require(e.source_type==EvidenceSource.CITIZEN_UPLOAD,'This photograph is restricted.','FORBIDDEN_ROLE_OR_CASE',403)
    require(e.storage_key and e.sync_status==SyncStatus.SYNCHRONISED,'The original photograph has not synchronised.')
    data=storage().get(e.storage_key)
    require(hashlib.sha256(data).hexdigest()==e.sha256,'Stored evidence failed its integrity check.','EVIDENCE_HASH_CONFLICT',409)
    return Response(data,media_type=e.mime_type,headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

@router.post('/cases/{case_id}/sync-complete',tags=['Inspector'])
def complete_sync(case_id:UUID,body:SyncComplete,who=Depends(inspector),db=Depends(get_db)):
    case=case_access(db,who,case_id)
    return sync_complete(db,who,case,[str(i) for i in body.evidence_ids])

@router.post('/cases/{case_id}/analysis',tags=['Compliance'],status_code=202)
def analyse(case_id:UUID,tasks:BackgroundTasks,who=Depends(officer),db=Depends(get_db)):
    case=case_access(db,who,case_id); run,created=queue_analysis(db,who,case)
    if created: tasks.add_task(run_analysis,run.id)
    return {'analysis_run_id':run.id,'status':str(run.status)}

@router.get('/analysis/{analysis_run_id}',tags=['Compliance'])
def analysis_status(analysis_run_id:UUID,who=Depends(officer),db=Depends(get_db)):
    run=found(db,AnalysisRun,analysis_run_id); case_access(db,who,run.case_id)
    return {**row(run),'retryable':run.status==AnalysisStatus.FAILED}

@router.get('/cases/{case_id}/compliance-map',tags=['Compliance'])
def compliance_map(case_id:UUID,who=Depends(officer),db=Depends(get_db)):
    return map_response(db,case_access(db,who,case_id))

@router.post('/cases/{case_id}/declarations/{declaration_group}/verification',tags=['Verification'])
def declaration_verify(case_id:UUID,declaration_group:str,body:DeclarationReview,who=Depends(inspector),db=Depends(get_db)):
    require(declaration_group in GROUPS,'Unknown declaration group.','VALIDATION_ERROR',422)
    return review_declaration(db,who,case_access(db,who,case_id),declaration_group,body)

@router.post('/findings/{finding_id}/verification',tags=['Verification'])
def finding_verify(finding_id:UUID,body:Verification,who=Depends(inspector),db=Depends(get_db)):
    f=found(db,Finding,finding_id); case_access(db,who,f.case_id)
    return verify_finding(db,who,f,body)

@router.post('/cases/{case_id}/reports',tags=['Reports'],status_code=202)
def report_create(case_id:UUID,tasks:BackgroundTasks,who=Depends(inspector),db=Depends(get_db)):
    case=case_access(db,who,case_id); report,created=queue_report(db,who,case)
    if created: tasks.add_task(generate_report,report.id)
    return {'report_id':report.id,'status':str(report.status)}

@router.get('/reports/{report_id}',tags=['Reports'])
def report_get(report_id:UUID,format:str|None=None,who=Depends(officer),db=Depends(get_db)):
    report=found(db,Report,report_id); case_access(db,who,report.case_id)
    if format:
        require(format in ('pdf','docx'),'Choose PDF or DOCX.','VALIDATION_ERROR',422)
        require(report.status==ReportStatus.READY,'Report generation is not complete.')
        key=report.storage_key if format=='pdf' else report.editable_storage_key
        return Response(storage().get(key),media_type='application/pdf' if format=='pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',headers={'Content-Disposition':f'attachment; filename="e-Maap-{report.id[:8]}.{format}"','Cache-Control':'private, no-store'})
    return {**row(report),'pdf_url':f'/reports/{report.id}?format=pdf' if report.status==ReportStatus.READY else None,'docx_url':f'/reports/{report.id}?format=docx' if report.status==ReportStatus.READY else None}

@router.get('/government/dashboard',tags=['Government'])
def dashboard(who=Depends(gov),db=Depends(get_db)):
    cases=list(db.scalars(select(Case)))
    patterns=[pattern_summary(db,p) for p in db.scalars(select(PatternCandidate).order_by(PatternCandidate.created_at.desc()))]
    ranked=[]
    for c in cases:
        priority(db,c); ranked.append(summary(db,c))
    order={'HIGH':0,'NORMAL':1,'LOW':2}
    ranked.sort(key=lambda c:(order[c['priority_band']],-c['priority_reasons'].get('severity_rank',0),-c['priority_reasons'].get('verified_history',0),-c['priority_reasons'].get('evidence_readiness',0)))
    return {'counts':{'awaiting_review':sum(c.status in (CaseStatus.INTAKE,CaseStatus.UNDER_REVIEW,CaseStatus.AWAITING_VERIFICATION) for c in cases),
        'active_inspections':sum(c.status in (CaseStatus.ASSIGNED,CaseStatus.CAPTURING,CaseStatus.SYNCING,CaseStatus.ANALYSING) for c in cases),
        'verified_findings':len(list(db.scalars(select(Finding).where(Finding.status.in_([FindingStatus.ACCEPTED,FindingStatus.CORRECTED]))))),
        'pattern_proposals':sum(p['status']=='CANDIDATE' for p in patterns)},'priority_queue':ranked[:8],'patterns':patterns,
        'locations':[{'name':name or 'Not recorded','count':count} for name,count in Counter(c.shop_location.get('area','') for c in cases).items()],
        'inspectors':[{'id':u.id,'name':u.name} for u in db.scalars(select(User).where(User.active==True,User.role==Role.INSPECTOR))]}

@router.get('/government/cases',tags=['Government'])
def government_cases(q:str='',status:CaseStatus|None=None,who=Depends(gov),db=Depends(get_db)):
    statement=select(Case).order_by(Case.created_at.desc())
    if status: statement=statement.where(Case.status==status)
    cases=list(db.scalars(statement))
    if q: cases=[c for c in cases if q.casefold() in ((snapshot(db,c.id).product_name if snapshot(db,c.id) else '')+' '+c.shop_name).casefold()]
    return {'items':[summary(db,c) for c in cases]}

@router.patch('/cases/{case_id}/priority',tags=['Government'])
def override(case_id:UUID,body:PriorityOverride,who=Depends(gov),db=Depends(get_db)):
    case=case_access(db,who,case_id); computed=priority(db,case); before=case.priority_band
    entry=audit(db,who,case.id,'PRIORITY_OVERRIDDEN','case',case.id,{'previous_band':before,'computed':computed,'overridden_band':body.priority_band,'reason':body.reason})
    case.priority_band=body.priority_band
    case.priority_reasons={**computed,'override':{'band':body.priority_band,'reason':body.reason,'officer':who.name,'officer_id':who.subject,'time':entry.created_at.isoformat()}}
    return summary(db,case)

@router.post('/cases/{case_id}/assign',tags=['Assignments'])
def assign(case_id:UUID,body:AssignmentCreate,who=Depends(gov),db=Depends(get_db)):
    case=case_access(db,who,case_id); require_approved_brief(db,body.brief_id,case)
    require(case.case_type!=CaseType.SYSTEMIC,'Use coordinated follow-up for a systemic parent.')
    require(case.status in (CaseStatus.INTAKE,CaseStatus.UNDER_REVIEW,CaseStatus.ASSIGNED),'Assignment cannot change while field work is active or complete.')
    user=found(db,User,body.inspector_id); require(user.active and user.role==Role.INSPECTOR,'Select an active Inspector.','VALIDATION_ERROR',422)
    assignment=db.scalar(select(Assignment).where(Assignment.case_id==case.id))
    if assignment: assignment.inspector_id=user.id; assignment.status=AssignmentStatus.ASSIGNED; assignment.downloaded_at=None
    else: assignment=Assignment(case_id=case.id,inspector_id=user.id); db.add(assignment); db.flush()
    case.status=CaseStatus.ASSIGNED
    audit(db,who,case.id,'CASE_ASSIGNED','assignment',assignment.id,{'inspector_id':user.id,'brief_id':str(body.brief_id) if body.brief_id else None,'reason':body.reason})
    return row(assignment)

@router.get('/patterns',tags=['Patterns'])
def patterns(who=Depends(gov),db=Depends(get_db)):
    return {'items':[pattern_summary(db,p) for p in db.scalars(select(PatternCandidate).order_by(PatternCandidate.created_at.desc()))]}

@router.get('/patterns/{pattern_id}',tags=['Patterns'])
def pattern_detail(pattern_id:UUID,who=Depends(gov),db=Depends(get_db)):
    return pattern_summary(db,found(db,PatternCandidate,pattern_id),True)

@router.post('/patterns/{pattern_id}/decision',tags=['Patterns'])
def decide_pattern(pattern_id:UUID,body:Decision,who=Depends(gov),db=Depends(get_db)):
    return pattern_decision(db,who,found(db,PatternCandidate,pattern_id),body)

@router.post('/patterns/{pattern_id}/systemic-case',tags=['Patterns'])
def create_systemic(pattern_id:UUID,who=Depends(gov),db=Depends(get_db)):
    return summary(db,systemic_case(db,who,found(db,PatternCandidate,pattern_id)))

@router.post('/systemic-cases/{case_id}/followups',tags=['Assignments'])
def create_followup(case_id:UUID,body:FollowupCreate,who=Depends(gov),db=Depends(get_db)):
    case=case_access(db,who,case_id); require(case.case_type==CaseType.SYSTEMIC,'Follow-up requires an approved systemic parent.')
    require_approved_brief(db,body.brief_id,case)
    user=found(db,User,body.assigned_to); require(user.active and user.role==Role.INSPECTOR,'Select an active Inspector.','VALIDATION_ERROR',422)
    followup=Followup(systemic_case_id=case.id,assigned_to=user.id,note=body.note,due_at=body.due_at); db.add(followup); db.flush()
    audit(db,who,case.id,'FOLLOWUP_ASSIGNED','followup',followup.id,{'assigned_to':user.id,'brief_id':str(body.brief_id) if body.brief_id else None,'note':body.note})
    return row(followup)

@router.patch('/followups/{followup_id}',tags=['Assignments'])
def followup_update(followup_id:UUID,body:FollowupUpdate,who=Depends(officer),db=Depends(get_db)):
    return update_followup(db,who,found(db,Followup,followup_id),body)

@router.post('/copilot/query',tags=['Copilot'])
def copilot(body:CopilotQuery,who=Depends(gov),db=Depends(get_db)):
    return copilot_query(db,who,body)

@router.post('/copilot/inspection-brief',tags=['Copilot'])
def brief(body:BriefCreate,who=Depends(gov),db=Depends(get_db)):
    return draft_brief(db,who,body)

@router.post('/inspection-briefs/{draft_id}/approval',tags=['Copilot'])
def brief_approval(draft_id:UUID,body:Decision,who=Depends(gov),db=Depends(get_db)):
    return approve_brief(db,who,str(draft_id),body)

@router.post('/copilot/analyse-image',tags=['Copilot'])
async def listing(image:UploadFile=File(...),input_kind:str=Form(...),case_id:UUID|None=Form(None),product_name:str|None=Form(None),listing_text:str=Form(''),source_label:str=Form('Officer upload'),who=Depends(gov),db=Depends(get_db)):
    require(input_kind in ('LABEL_IMAGE','LISTING_SCREENSHOT'),'Choose label image or listing screenshot.','VALIDATION_ERROR',422)
    data=await image.read(PROTOTYPE['upload']['max_image_bytes']+1)
    require(len(data)<=PROTOTYPE['upload']['max_image_bytes'],'Image exceeds the configured limit.','FILE_TOO_LARGE',413)
    case=case_access(db,who,case_id) if case_id else None
    return analyse_listing(db,who,data,input_kind,case,product_name,listing_text,source_label)

@router.get('/government/repository',tags=['Repository'])
def repository(q:str='',status:CaseStatus|None=None,manufacturer:str='',batch_lot:str='',retailer:str='',location:str='',rule_code:str='',finding_status:FindingStatus|None=None,source:str='',brand:str='',date_from:date|None=None,date_to:date|None=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),who=Depends(gov),db=Depends(get_db)):
    return history_query(db,{k:v for k,v in locals().items() if k not in ('who','db')})

@router.get('/government/reports',tags=['Repository'])
def reports(q:str='',case_id:UUID|None=None,status:ReportStatus|None=None,date_from:date|None=None,date_to:date|None=None,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),who=Depends(gov),db=Depends(get_db)):
    return report_search(db,{k:v for k,v in locals().items() if k not in ('who','db')})
