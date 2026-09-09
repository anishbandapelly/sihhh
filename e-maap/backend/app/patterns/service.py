from sqlalchemy import select
from app.core.models import *
from app.core.errors import require
from app.cases.service import records, snapshot, row, summary
from app.compliance.domain import verified_groups, normalise, followup_transition
from app.audit.service import audit

def correlation_records(db):
    result=[]
    for finding in db.scalars(select(Finding)):
        case=db.get(Case,finding.case_id); p=snapshot(db,case.id)
        if not p: continue
        rr=db.get(RuleResult,finding.rule_result_id); rule=db.get(Rule,rr.rule_id)
        refs=rr.inputs_json.get('source_refs',[])
        if rr.inputs_json.get('source'): refs=[{'evidence_id':rr.inputs_json['source'].get('source_evidence_id')}]
        field=bool(refs) and all((e:=db.get(EvidenceItem,r['evidence_id'])) and e.source_type==EvidenceSource.FIELD_CAPTURE for r in refs)
        result.append({'id':finding.id,'case_id':case.id,'status':str(finding.status),'rule_code':rule.rule_code,
            'verification_event':bool(records(db,VerificationEvent,finding_id=finding.id)), 'field_source':field,
            'identity_confirmed':bool(p.officer_confirmed_json.get('product_name') and p.officer_confirmed_json.get('manufacturer')),
            'product':p.product_name,'manufacturer':p.manufacturer,'batch':p.batch_lot if p.officer_confirmed_json.get('batch_lot') else None,'retailer':case.shop_name,'location':case.shop_location.get('area','')})
    return result

def correlate(db):
    for key,members in verified_groups(correlation_records(db)).items():
        signature='|'.join(key)
        decided=[p for p in db.scalars(select(PatternCandidate)) if p.status!=PatternStatus.CANDIDATE and p.match_factors.get('signature')==signature]
        if any({m['id'] for m in members}.issubset({x.finding_id for x in records(db,PatternMember,pattern_id=p.id)}) for p in decided): continue
        existing=next((p for p in db.scalars(select(PatternCandidate)) if p.status==PatternStatus.CANDIDATE and p.match_factors.get('signature')==signature),None)
        factors={'signature':signature,'product':members[0]['product'],'manufacturer':members[0]['manufacturer'],'batch_lot':members[0]['batch'] if key[3] else None,
            'matched_fields':['rule','officer-confirmed product','officer-confirmed manufacturer']+(['batch/lot'] if key[3] else []),
            'locations':sorted({m['location'] for m in members}),
            'explanation':'Repeated officer-verified findings with confirmed product identity across independent retailers.'}
        if not existing:
            existing=PatternCandidate(pattern_level='BATCH' if key[3] else 'MANUFACTURER_PRODUCT',rule_code=key[0],match_factors=factors,verified_count=0,retailer_count=0)
            db.add(existing); db.flush()
        existing.verified_count=len(members); existing.retailer_count=len({normalise(m['retailer']) for m in members}); existing.match_factors=factors
        previous={m.finding_id for m in records(db,PatternMember,pattern_id=existing.id)}
        for m in members:
            if m['id'] not in previous: db.add(PatternMember(pattern_id=existing.id,finding_id=m['id'],match_reason={'fields':factors['matched_fields'],'case_id':m['case_id']}))
    db.flush()

def matches(p,factors):
    return normalise(p.product_name)==normalise(factors.get('product','')) and normalise(p.manufacturer)==normalise(factors.get('manufacturer','')) and (not factors.get('batch_lot') or normalise(p.batch_lot or '')==normalise(factors['batch_lot']))

def pattern_summary(db,p,details=False):
    awaiting=set(); leads=set(); factors=p.match_factors
    for product in db.scalars(select(ProductSnapshot)):
        if not matches(product,factors): continue
        case=db.get(Case,product.case_id)
        if case.source=='CITIZEN' and case.public_tracking_token_hash: leads.add(case.id)
        for finding in records(db,Finding,case_id=case.id):
            rr=db.get(RuleResult,finding.rule_result_id); rule=db.get(Rule,rr.rule_id)
            if finding.status==FindingStatus.POTENTIAL and rule.rule_code==p.rule_code: awaiting.add(case.id)
    result={**row(p),'awaiting_count':len(awaiting),'citizen_lead_count':len(leads),'priority_reason':f'{p.verified_count} officer-verified findings across {p.retailer_count} retailers; {p.rule_code}'}
    if details:
        members=[]
        for member in records(db,PatternMember,pattern_id=p.id):
            f=db.get(Finding,member.finding_id); case=db.get(Case,f.case_id)
            members.append({'finding':row(f),'case':summary(db,case),'match_reason':member.match_reason})
        result.update({'members':members,'awaiting_case_ids':sorted(awaiting),'citizen_lead_case_ids':sorted(leads)})
    return result

def pattern_decision(db,who,p,body):
    db.execute(select(PatternCandidate).where(PatternCandidate.id==p.id).with_for_update()); db.refresh(p)
    require(p.status==PatternStatus.CANDIDATE,'This pattern already has an officer decision.','DUPLICATE_DECISION',409)
    p.status=PatternStatus.APPROVED if body.decision=='APPROVE' else PatternStatus.REJECTED
    p.reviewed_by=who.subject; p.reviewed_at=now()
    audit(db,who,None,'PATTERN_DECISION','pattern',p.id,{'decision':body.decision,'reason':body.reason,'verified_count':p.verified_count,'finding_ids':[m.finding_id for m in records(db,PatternMember,pattern_id=p.id)]})
    return pattern_summary(db,p,True)

def systemic_case(db,who,p):
    db.execute(select(PatternCandidate).where(PatternCandidate.id==p.id).with_for_update())
    require(p.status==PatternStatus.APPROVED,'Approve the pattern before creating a systemic case.')
    prior=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==p.id,AuditEvent.event_type=='SYSTEMIC_CASE_CREATED'))
    if prior: return db.get(Case,prior.payload['case_id'])
    case=Case(case_type=CaseType.SYSTEMIC,source='VERIFIED_PATTERN',status=CaseStatus.UNDER_REVIEW,shop_name='Coordinated investigation',priority_band='HIGH',priority_reasons={'computed_band':'HIGH','factors':[f'{p.verified_count} verified findings',f'{p.retailer_count} retailers'], 'pattern_id':p.id})
    db.add(case); db.flush()
    db.add(ProductSnapshot(case_id=case.id,product_name=p.match_factors['product'],manufacturer=p.match_factors['manufacturer'],batch_lot=p.match_factors.get('batch_lot'),package_family=PackageFamily.OTHER_PACKAGE))
    for m in records(db,PatternMember,pattern_id=p.id):
        f=db.get(Finding,m.finding_id); child=db.get(Case,f.case_id)
        require(child.parent_case_id is None,'A contributing case already belongs to a systemic investigation; review grouping.')
        child.parent_case_id=case.id
    audit(db,who,case.id,'SYSTEMIC_CASE_CREATED','pattern',p.id,{'case_id':case.id})
    return case

def update_followup(db,who,f,body):
    require(who.role==Role.GOVERNMENT_OFFICER or (who.role==Role.INSPECTOR and f.assigned_to==who.subject),'This follow-up is not assigned to you.','FORBIDDEN_ROLE_OR_CASE',403)
    previous=str(f.status); target=followup_transition(previous,str(body.status))
    if target!=previous:
        f.status=FollowupStatus(target); f.note=body.note; f.updated_at=now()
        audit(db,who,f.systemic_case_id,'FOLLOWUP_TRANSITION','followup',f.id,{'from':previous,'to':target,'note':body.note})
    return row(f)
