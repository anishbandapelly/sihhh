from sqlalchemy import select
from app.core.models import *
from app.core.errors import require
from app.audit.service import audit
from app.cases.service import records, row
from app.compliance.domain import evaluate_rule

FIELDS={'D01':{'common_generic_name'},'D02':{'responsible_entity_name','responsible_entity_address','role_label'},
    'D03':{'quantity_value','quantity_unit','quantity_kind'},'D04':{'mrp_amount','currency','mrp_label'},
    'D05':{'manufacture_month','manufacture_year'},'D06':{'care_name_or_office','care_address','care_phone','care_email'}}

def review_declaration(db,who,case,group,body):
    db.execute(select(Case).where(Case.id==case.id).with_for_update())
    require(case.status==CaseStatus.AWAITING_VERIFICATION,'Complete server analysis before declaration review.')
    d=db.scalar(select(DeclarationResult).where(DeclarationResult.case_id==case.id,DeclarationResult.declaration_group==group))
    require(d is not None,'There is no analysed declaration to review.','NOT_FOUND',404)
    refs=body.model_dump(mode='json')['source_refs']
    for ref in refs:
        e=db.get(EvidenceItem,ref['evidence_id'])
        require(e and e.case_id==case.id and e.source_type==EvidenceSource.FIELD_CAPTURE and e.sync_status==SyncStatus.SYNCHRONISED,
            'Declaration review must reference synchronised field evidence from this case.','FORBIDDEN_ROLE_OR_CASE',403)
        if ref.get('candidate_id'):
            c=db.get(ExtractionCandidate,ref['candidate_id'])
            require(c and c.evidence_id==e.id and c.declaration_group==group,'Candidate does not match this declaration and source.','VALIDATION_ERROR',422)
    if body.action==Action.ACCEPT:
        require(d.evidence_state in (EvidenceState.SUPPORTED,EvidenceState.POTENTIALLY_ABSENT,EvidenceState.NOT_APPLICABLE),'Resolve the conflicting or unresolved value with a grounded correction.')
    selected=body.corrected_value if body.action==Action.CORRECT else (d.fused_value if body.action==Action.ACCEPT else None)
    if selected:
        require(set(selected).issubset(FIELDS[group]),'Use only the canonical fields for this declaration.','VALIDATION_ERROR',422)
    previous=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==d.id,AuditEvent.event_type=='DECLARATION_REVIEWED').order_by(AuditEvent.created_at.desc()))
    event=audit(db,who,case.id,'DECLARATION_REVIEWED','declaration',d.id,{
        'declaration_group':group,'previous_value':previous.payload.get('selected_value') if previous else d.fused_value,
        'selected_value':selected,'source_refs':refs,'status':{'ACCEPT':'ACCEPTED','CORRECT':'CORRECTED','REJECT':'REJECTED'}[body.action],
        'action':str(body.action),'reason':body.reason,'reviewer':who.name,'original_evidence_state':str(d.evidence_state)})
    if body.action==Action.CORRECT:
        plan=db.scalar(select(EvidencePlanItem).where(EvidencePlanItem.case_id==case.id,EvidencePlanItem.declaration_group==group))
        raw='\n'.join(c.raw_text for c in db.scalars(select(ExtractionCandidate).where(ExtractionCandidate.id.in_(d.source_ids))))
        for rule in db.scalars(select(Rule).where(Rule.active==True)):
            if rule.config_json.get('group') not in (group,'ALL') or rule.rule_code.startswith('PRES'): continue
            result=evaluate_rule({'logic_key':rule.logic_key,'config':rule.config_json},{'state':'SUPPORTED','value':selected},refs,plan.absence_eligible,raw)
            result['inputs']['declaration_review_id']=event.id
            rr=RuleResult(case_id=case.id,rule_id=rule.id,declaration_result_id=d.id,result_state=result['result_state'],reason_code=result['reason_code'],inputs_json=result['inputs'],explanation=result['explanation'])
            db.add(rr); db.flush()
            if rr.result_state=='FINDING': db.add(Finding(case_id=case.id,rule_result_id=rr.id))
    return row(event)

def verify_finding(db,who,finding,body):
    db.execute(select(Finding).where(Finding.id==finding.id).with_for_update())
    db.refresh(finding)
    require(finding.status==FindingStatus.POTENTIAL,'This finding already has a decision.','DUPLICATE_DECISION',409)
    case=db.get(Case,finding.case_id)
    require(case.status==CaseStatus.AWAITING_VERIFICATION,'Finding verification is available after analysis.')
    rr=db.get(RuleResult,finding.rule_result_id)
    refs=rr.inputs_json.get('source_refs') or []
    if rr.inputs_json.get('source'): refs=[{'evidence_id':rr.inputs_json['source'].get('source_evidence_id')}]
    require(refs,'A finding must retain grounded source evidence.')
    require(all((e:=db.get(EvidenceItem,r['evidence_id'])) and e.case_id==case.id and e.source_type==EvidenceSource.FIELD_CAPTURE for r in refs),'Only Inspector field evidence can support an inspection finding.')
    event=VerificationEvent(finding_id=finding.id,officer_id=who.subject,action=body.action,corrected_value=body.corrected_value,reason=body.reason)
    db.add(event); db.flush()
    finding.status=FindingStatus({'ACCEPT':'ACCEPTED','CORRECT':'CORRECTED','REJECT':'REJECTED'}[body.action])
    finding.verified_value=body.corrected_value if body.action==Action.CORRECT else rr.inputs_json.get('value')
    audit(db,who,case.id,'FINDING_VERIFIED','finding',finding.id,{'action':str(body.action),'reason':body.reason,'source_refs':refs,'verification_event_id':event.id})
    db.flush()
    from app.patterns.service import correlate
    correlate(db)
    return {**row(finding),'verification_event':row(event)}

def report_guard(db,case):
    require(case.status in (CaseStatus.AWAITING_VERIFICATION,CaseStatus.COMPLETED),'Analysis and officer review must finish before report generation.')
    runs=records(db,AnalysisRun,case_id=case.id)
    require(any(r.status==AnalysisStatus.SUCCEEDED for r in runs),'A successful analysis is required.')
    require(not any(f.status==FindingStatus.POTENTIAL for f in records(db,Finding,case_id=case.id)),'Review all potential findings before generating the report.')
    ds=records(db,DeclarationResult,case_id=case.id)
    require(len(ds)==6,'All six declaration groups must be represented.')
    for d in ds:
        review=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==d.id,AuditEvent.event_type=='DECLARATION_REVIEWED').order_by(AuditEvent.created_at.desc()))
        require(review and review.payload['status'] in ('ACCEPTED','CORRECTED'),f'Review or resolve {GROUPS[d.declaration_group]} before completing the report.')
        require(d.evidence_state not in (EvidenceState.UNRESOLVED,EvidenceState.CONFLICTING,EvidenceState.OBSCURED_DAMAGED) or review.payload['status']=='CORRECTED',f'{GROUPS[d.declaration_group]} still needs grounded resolution.')
    return ds

