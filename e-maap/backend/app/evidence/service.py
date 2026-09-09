import hashlib, hmac
from sqlalchemy import select
from app.core.models import *
from app.core.errors import require, DomainError
from app.core.config import PROTOTYPE
from app.audit.service import audit
from app.cases.service import records, snapshot, row
from app.compliance.domain import coverage
from app.compliance.quality import analyse_quality
from .storage import storage

def capture_open(db,case):
    require(case.status not in (CaseStatus.COMPLETED,CaseStatus.CLOSED),'A completed inspection is immutable. Open a separately assigned follow-up.')
    require(not any(f.status!=FindingStatus.POTENTIAL for f in records(db,Finding,case_id=case.id)), 'Evidence cannot change after finding verification.')
    require(not any(r.status in (AnalysisStatus.QUEUED,AnalysisStatus.RUNNING) for r in records(db,AnalysisRun,case_id=case.id)), 'Wait for analysis to finish before changing evidence.')

def register(db,who,case,payload):
    existing=db.get(EvidenceItem,str(payload.id))
    if existing:
        expected=EvidenceSource.CITIZEN_UPLOAD if who.kind=='citizen' else EvidenceSource.FIELD_CAPTURE
        require(existing.source_type==expected,'Evidence belongs to a different capture pathway.','FORBIDDEN_ROLE_OR_CASE',403)
        require(existing.case_id==case.id and existing.sha256==payload.sha256 and existing.sequence_no==payload.sequence_no,'Evidence ID is already registered with different content.','EVIDENCE_HASH_CONFLICT',409)
        return existing
    capture_open(db,case)
    is_citizen=who.kind=='citizen'
    if is_citizen:
        require(case.public_tracking_token_hash is None,'This complaint has already been submitted.')
        require(payload.calibration_json is None,'Citizen imagery cannot claim Inspector calibration.','FORBIDDEN_ROLE_OR_CASE',403)
    product=snapshot(db,case.id); profile=PROTOTYPE['profiles'][str(product.package_family)]
    context=payload.source_context_json.model_dump(mode='json')
    require(context['view_role'] in profile['roles']+['DECLARATION_CLOSEUP'],'Choose a view from the assigned capture profile.','VALIDATION_ERROR',422)
    replacement=context.get('replacement_for')
    if replacement:
        previous=db.get(EvidenceItem,replacement)
        require(previous and previous.case_id==case.id,'Replacement must reference evidence from this case.','VALIDATION_ERROR',422)
    data=payload.model_dump(exclude={'quality','source_context_json','id'},mode='python')
    data['calibration_json']=payload.calibration_json.model_dump(mode='json') if payload.calibration_json else None
    if data['calibration_json']: data['calibration_json']['px_per_mm']=payload.calibration_json.px_per_mm
    item=EvidenceItem(id=str(payload.id),case_id=case.id,captured_by_user_id=who.user_id,
        source_type=EvidenceSource.CITIZEN_UPLOAD if is_citizen else EvidenceSource.FIELD_CAPTURE,
        source_context_json=context,quality_json={'on_device':payload.quality},**data)
    db.add(item); case.status=CaseStatus.CAPTURING; db.flush()
    assignment=db.scalar(select(Assignment).where(Assignment.case_id==case.id))
    if assignment: assignment.status=AssignmentStatus.IN_PROGRESS
    audit(db,who,case.id,'EVIDENCE_REGISTERED','evidence',item.id,{'sha256':item.sha256,'sequence_no':item.sequence_no,'source_type':str(item.source_type),'source_context':context})
    return item

def receive(db,who,item,data):
    require(len(data)<=PROTOTYPE['upload']['max_image_bytes'],'Image exceeds the configured upload limit.','FILE_TOO_LARGE',413)
    actual=hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(actual,item.sha256):
        audit(db,who,item.case_id,'EVIDENCE_HASH_CONFLICT','evidence',item.id,{'registered':item.sha256,'received':actual})
        db.commit()  # A rejected integrity attempt must survive the request rollback.
        raise DomainError('EVIDENCE_HASH_CONFLICT','Image bytes differ from the registered fingerprint. Preserve the original and review this item.',409)
    if item.sync_status==SyncStatus.SYNCHRONISED:
        stored=storage().get(item.storage_key)
        if not hmac.compare_digest(hashlib.sha256(stored).hexdigest(),item.sha256):
            audit(db,who,item.case_id,'STORAGE_INTEGRITY_FAILURE','evidence',item.id,{'expected':item.sha256,'actual':hashlib.sha256(stored).hexdigest()}); db.commit()
            raise DomainError('EVIDENCE_HASH_CONFLICT','Stored evidence failed its integrity check.',409)
        return item
    quality=analyse_quality(data)
    item.quality_json={**quality,'on_device':item.quality_json.get('on_device',{})}
    key=f'evidence/{item.case_id}/{item.id}.{"png" if item.mime_type=="image/png" else "jpg"}'
    storage().put(key,data,item.mime_type)
    item.storage_key=key; item.synced_at=now(); item.sync_status=SyncStatus.SYNCHRONISED
    audit(db,who,item.case_id,'EVIDENCE_SYNCHRONISED','evidence',item.id,{'sha256':actual,'quality':quality})
    return item

def active_evidence(db,case_id,citizen_only=False):
    items=records(db,EvidenceItem,case_id=case_id)
    source=EvidenceSource.CITIZEN_UPLOAD if citizen_only else EvidenceSource.FIELD_CAPTURE
    items=[e for e in items if e.source_type==source]
    replaced={e.source_context_json.get('replacement_for') for e in items if e.sync_status==SyncStatus.SYNCHRONISED}
    return [e for e in items if e.id not in replaced]

def update_coverage(db,case,citizen_only=False):
    product=snapshot(db,case.id); profile=PROTOTYPE['profiles'][str(product.package_family)]
    evidences=active_evidence(db,case.id,citizen_only)
    data=[{'id':e.id,'source_type':str(e.source_type),'synced':e.sync_status==SyncStatus.SYNCHRONISED,
        'usable':e.quality_json.get('usable',False),**e.source_context_json} for e in evidences]
    for plan in records(db,EvidencePlanItem,case_id=case.id):
        confirmed=db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id==plan.id,AuditEvent.event_type=='MANUAL_COVERAGE_CONFIRMED')) is not None
        result=coverage(profile,data,plan.declaration_group,confirmed)
        plan.coverage_state=CoverageState(result['coverage_state']); plan.absence_eligible=result['absence_eligible']; plan.next_capture_prompt=result['next_capture_prompt']
    return evidences

def sync_complete(db,who,case,ids):
    require(len(set(ids))==len(ids),'The sync manifest contains duplicate IDs.','VALIDATION_ERROR',422)
    items=active_evidence(db,case.id)
    require(set(ids)=={e.id for e in items},'The complete retained local evidence manifest is required.')
    require(items and all(e.sync_status==SyncStatus.SYNCHRONISED for e in items),'Wait for server acknowledgement of every retained item.')
    case.status=CaseStatus.SYNCING
    update_coverage(db,case)
    audit(db,who,case.id,'SYNC_COMPLETED','case',case.id,{'evidence_ids':ids})
    return {'case_id':case.id,'status':'SYNCHRONISED','acknowledged_evidence_ids':ids}

