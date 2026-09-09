from sqlalchemy import select
from fastapi.encoders import jsonable_encoder
from app.core.models import *
from app.core.config import PROTOTYPE
from app.core.errors import require, DomainError
from app.audit.service import audit
from app.compliance.domain import RULE_DEFINITIONS

def row(obj):
    if obj is None: return None
    return jsonable_encoder({c.name:getattr(obj,c.name) for c in obj.__table__.columns})

def records(db, model, **filters):
    return list(db.scalars(select(model).filter_by(**filters)))

def create_case(db, who, family, name, case_type=CaseType.CITIZEN_LEAD, source='CITIZEN', case_id=None):
    case=Case(id=case_id,case_type=case_type,source=source,citizen_session_id=who.subject if who and who.kind=='citizen' else None)
    db.add(case); db.flush()
    db.add(ProductSnapshot(case_id=case.id,product_name=name,manufacturer='',package_family=family))
    for group in GROUPS:
        rules=[code for code,g,*_ in RULE_DEFINITIONS if g in (group,'ALL')]
        db.add(EvidencePlanItem(case_id=case.id,declaration_group=group,rule_ids=rules,next_capture_prompt=PROTOTYPE['profiles'][str(family)]['prompts'][0]))
    audit(db,who,case.id,'CASE_CREATED','case',case.id,{'case_type':str(case_type),'source':source})
    return case

def snapshot(db, case_id): return db.scalar(select(ProductSnapshot).where(ProductSnapshot.case_id==case_id))

def summary(db, case):
    assignment=db.scalar(select(Assignment).where(Assignment.case_id==case.id))
    product=snapshot(db,case.id)
    return {'id':case.id,'reference':'EM-'+case.id[:8].upper(),'case_type':str(case.case_type),'status':str(case.status),'source':case.source,
        'product_snapshot':row(product),'shop':{'name':case.shop_name,**case.shop_location},'priority_band':case.priority_band,
        'priority_reasons':case.priority_reasons,'assignment':row(assignment),'created_at':case.created_at,'parent_case_id':case.parent_case_id}

def detail(db,case):
    result=summary(db,case)
    result.update({'evidence':[row(e) for e in records(db,EvidenceItem,case_id=case.id)],
        'history':[row(e) for e in records(db,AuditEvent,case_id=case.id)],
        'reports':[row(r) for r in records(db,Report,case_id=case.id)],
        'followups':[row(f) for f in records(db,Followup,systemic_case_id=case.id)],
        'children':[summary(db,c) for c in records(db,Case,parent_case_id=case.id)]})
    return result

def plan_response(db,case):
    p=snapshot(db,case.id); evidence=records(db,EvidenceItem,case_id=case.id)
    items=[]
    for item in records(db,EvidencePlanItem,case_id=case.id):
        items.append({**row(item),'source_evidence_ids':[e.id for e in evidence if item.declaration_group in e.source_context_json.get('search_groups',[]) and e.quality_json.get('usable')]})
    return {'case_id':case.id,'package_family':str(p.package_family),'profile':PROTOTYPE['profiles'][str(p.package_family)],
        'items':items,'configuration':PROTOTYPE,'rule_version_refs':[{'code':r.rule_code,'version':r.version} for r in db.scalars(select(Rule).where(Rule.active==True))]}

def priority(db,case):
    fs=records(db,Finding,case_id=case.id)
    severity=max([f.severity for f in fs]+[1])
    verified=len([f for f in fs if f.status in (FindingStatus.ACCEPTED,FindingStatus.CORRECTED)])
    ready=len([e for e in records(db,EvidenceItem,case_id=case.id) if e.quality_json.get('usable') and e.sync_status==SyncStatus.SYNCHRONISED])
    computed={'computed_band':'NORMAL','severity_rank':severity,'verified_history':verified,'evidence_readiness':ready,
        'factors':[f'Prototype severity rank {severity}',f'{verified} officer-verified findings',f'{ready} usable synchronised photographs']}
    old=case.priority_reasons or {}
    if old.get('override'): computed['override']=old['override']
    case.priority_reasons=computed
    return computed
