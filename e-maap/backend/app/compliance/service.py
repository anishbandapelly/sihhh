import hashlib, time
from sqlalchemy import select, delete
from app.core.models import *
from app.core.db import SessionLocal
from app.core.config import PROTOTYPE
from app.core.errors import require, DomainError
from app.cases.service import records, row, snapshot, priority
from app.audit.service import audit
from app.evidence.storage import storage
from app.evidence.service import active_evidence, update_coverage
from .domain import fuse, evaluate_rule, presentation, public_observations
from .ocr import extract, fixture_metadata
from .quality import region_metrics

def candidate_dict(c):
    return {'id':c.id,'evidence_id':c.evidence_id,'bbox':c.bbox,'value':c.normalized_value,'raw_text':c.raw_text,'confidence':c.confidence,'extractor':c.extractor}

def queue_analysis(db,who,case,citizen_only=False):
    db.execute(select(Case).where(Case.id==case.id).with_for_update())
    active=db.scalar(select(AnalysisRun).where(AnalysisRun.case_id==case.id,AnalysisRun.status.in_([AnalysisStatus.QUEUED,AnalysisStatus.RUNNING])))
    if active: return active,False
    require(case.status not in (CaseStatus.COMPLETED,CaseStatus.CLOSED),'Completed case evidence is immutable.')
    require(not any(f.status!=FindingStatus.POTENTIAL for f in records(db,Finding,case_id=case.id)),'Reanalysis is blocked after finding verification; original reports and decisions remain stable.')
    items=active_evidence(db,case.id,citizen_only)
    require(items and all(e.sync_status==SyncStatus.SYNCHRONISED for e in items),'Synchronise all retained evidence before analysis.')
    if not citizen_only:
        seal=db.scalar(select(AuditEvent).where(AuditEvent.case_id==case.id,AuditEvent.event_type=='SYNC_COMPLETED').order_by(AuditEvent.created_at.desc()))
        require(seal and set(seal.payload['evidence_ids'])=={e.id for e in items},'Confirm the complete sync manifest before analysis.')
    run=AnalysisRun(case_id=case.id); db.add(run); db.flush(); case.status=CaseStatus.ANALYSING
    audit(db,who,case.id,'ANALYSIS_QUEUED','analysis',run.id,{'citizen_only':citizen_only})
    db.commit()  # Background worker opens an independent transaction.
    return run,True

def run_analysis(run_id,citizen_only=False,provider=None):
    with SessionLocal() as db:
        run=db.get(AnalysisRun,run_id)
        if not run or run.status!=AnalysisStatus.QUEUED: return
        run.status=AnalysisStatus.RUNNING; run.started_at=now(); db.commit()
        start=time.monotonic()
        try:
            case=db.get(Case,run.case_id)
            evidences=update_coverage(db,case,citizen_only)
            selected=[]
            for evidence in evidences:
                data=storage().get(evidence.storage_key)
                require(hashlib.sha256(data).hexdigest()==evidence.sha256,'Stored evidence failed integrity validation.','EVIDENCE_HASH_CONFLICT',409)
                if not evidence.quality_json.get('usable'): continue
                prior=records(db,ExtractionCandidate,evidence_id=evidence.id)
                if not prior:
                    for item in extract(data,provider):
                        c=ExtractionCandidate(evidence_id=evidence.id,declaration_group=item['declaration_group'],raw_text=item['raw_text'],
                            normalized_value=item['value'],bbox=item['bbox'],confidence=item['confidence'],extractor=item['extractor'])
                        db.add(c); db.flush(); prior.append(c)
                selected.extend(prior)
                require(time.monotonic()-start<=PROTOTYPE['analysis']['timeout_seconds'],'Analysis timed out. Evidence is preserved.','ANALYSIS_TEMPORARILY_UNAVAILABLE',503)
            # Candidate rows survive every run; potential result rows may be replaced before human review only.
            db.execute(delete(Finding).where(Finding.case_id==case.id,Finding.status==FindingStatus.POTENTIAL))
            db.execute(delete(RuleResult).where(RuleResult.case_id==case.id))
            db.execute(delete(DeclarationResult).where(DeclarationResult.case_id==case.id)); db.flush()
            evidence_by_id={e.id:e for e in evidences}
            plans=records(db,EvidencePlanItem,case_id=case.id)
            for plan in plans:
                candidates=[c for c in selected if c.declaration_group==plan.declaration_group]
                obscured=any(e.source_context_json.get('observed_condition')=='OBSCURED_DAMAGED' and plan.declaration_group in e.source_context_json.get('search_groups',[]) for e in evidences)
                fused=fuse([candidate_dict(c) for c in candidates],plan.absence_eligible,PROTOTYPE,obscured)
                declaration=DeclarationResult(case_id=case.id,declaration_group=plan.declaration_group,fused_value=fused['value'],evidence_state=EvidenceState(fused['state']),
                    selected_candidate_id=fused['selected_id'],source_ids=[c.id for c in candidates],review_flags_json=fused['flags'])
                db.add(declaration); db.flush()
                refs=[{'candidate_id':c.id,'evidence_id':c.evidence_id,'bbox':c.bbox,'source_type':str(evidence_by_id[c.evidence_id].source_type)} for c in candidates]
                if not refs and plan.absence_eligible:
                    refs=[{'evidence_id':e.id,'bbox':[0,0,1,1],'source_type':str(e.source_type),'source_kind':'INSPECTED_SEARCH_REGION'} for e in evidences if plan.declaration_group in e.source_context_json.get('search_groups',[]) and e.quality_json.get('usable')]
                raw='\n'.join(c.raw_text for c in candidates)
                for rule in db.scalars(select(Rule).where(Rule.active==True)):
                    if rule.config_json.get('group') not in (plan.declaration_group,'ALL'): continue
                    result=evaluate_rule({'logic_key':rule.logic_key,'config':rule.config_json},fused,refs,plan.absence_eligible,raw)
                    save_rule_result(db,case,declaration,rule,result,citizen_only)
                pres={}
                source=None; fixture=None
                if candidates:
                    best=max(candidates,key=lambda c:c.confidence); e=evidence_by_id[best.evidence_id]; data=storage().get(e.storage_key)
                    metadata=fixture_metadata(data)
                    fixture=(metadata or {}).get('presentation',{}).get(plan.declaration_group)
                    agreeing=len({str(c.normalized_value) for c in candidates})
                    source={'source_evidence_id':e.id,'bbox':best.bbox,'source_type':str(e.source_type),'calibration':e.calibration_json,
                        'usable':e.quality_json.get('usable'), 'geometry_valid':bool(fixture),
                        'ocr_stability':(1/agreeing if len(candidates)>1 else None),**region_metrics(data,best.bbox)}
                    if metadata and fixture and provider=='fixture': source['ocr_stability']=fixture.get('fixture_ocr_stability',source['ocr_stability'])
                for code,label in [('PRES-01','placement'),('PRES-02','font_size'),('PRES-03','readability')]:
                    result=presentation(code,source,fixture,PROTOTYPE['presentation']); pres[label]={**result,'rule_code':code,'rule_version':'SRS-PRESENTATION-FIXTURE-1'}
                    if fixture:
                        pr=db.scalar(select(Rule).where(Rule.rule_code==code))
                        if pr: save_rule_result(db,case,declaration,pr,{'result_state':result['presentation_state'],'reason_code':None,'inputs':result['inputs'],'explanation':result['explanation']},citizen_only)
                declaration.presentation_json=pres
            run.status=AnalysisStatus.SUCCEEDED; run.completed_at=now(); case.status=CaseStatus.AWAITING_VERIFICATION
            if citizen_only:
                # Store only the allowlisted preliminary projection, before departmental analysis can occur.
                safe=public_map(db,case)
                audit(db,None,case.id,'CITIZEN_PRELIMINARY_RESULT','case',case.id,safe)
            priority(db,case)
            audit(db,None,case.id,'ANALYSIS_SUCCEEDED','analysis',run.id,{'candidate_count':len(selected),'provider':provider or 'configured'})
            db.commit()
        except Exception as exc:
            db.rollback(); run=db.get(AnalysisRun,run_id)
            run.status=AnalysisStatus.FAILED; run.completed_at=now(); run.failure_code=getattr(exc,'code','ANALYSIS_TEMPORARILY_UNAVAILABLE')
            audit(db,None,run.case_id,'ANALYSIS_FAILED','analysis',run.id,{'code':run.failure_code,'detail':str(exc)[:500]})
            db.commit()

def save_rule_result(db,case,declaration,rule,result,citizen_only):
    rr=RuleResult(case_id=case.id,rule_id=rule.id,declaration_result_id=declaration.id,result_state=result['result_state'],reason_code=result.get('reason_code'),inputs_json=result['inputs'],explanation=result['explanation'])
    db.add(rr); db.flush()
    if result.get('reason_code'):
        declaration.review_flags_json=list(set(declaration.review_flags_json+[result['reason_code']]))
    if not citizen_only and (rr.result_state=='FINDING' or rr.result_state.startswith('POTENTIAL_')):
        db.add(Finding(case_id=case.id,rule_result_id=rr.id,severity=PROTOTYPE['priority']['severity_rank'].get(rule.rule_code,1)))

def map_response(db,case):
    items=[]
    for d in records(db,DeclarationResult,case_id=case.id):
        candidates=[db.get(ExtractionCandidate,i) for i in d.source_ids]
        refs=[]
        for c in candidates:
            if not c: continue
            e=db.get(EvidenceItem,c.evidence_id)
            refs.append({**candidate_dict(c),'candidate_id':c.id,'source_type':str(e.source_type),'quality':e.quality_json,
                'provenance':{'sha256':e.sha256,'captured_at':e.captured_at,'synced_at':e.synced_at,'latitude':e.latitude,'longitude':e.longitude,'accuracy_m':e.accuracy_m}})
        rules=[]; findings=[]
        for rr in records(db,RuleResult,declaration_result_id=d.id):
            r=db.get(Rule,rr.rule_id); rules.append({**row(rr),'rule_code':r.rule_code,'rule_version':r.version,'legal_reference':r.legal_reference})
            for f in records(db,Finding,rule_result_id=rr.id):
                findings.append({**row(f),'rule_code':r.rule_code,'rule_version':r.version,'explanation':rr.explanation,'evidence_refs':rr.inputs_json.get('source_refs',[]),
                    'verification_events':[row(v) for v in records(db,VerificationEvent,finding_id=f.id)]})
        review=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==d.id,AuditEvent.event_type=='DECLARATION_REVIEWED').order_by(AuditEvent.created_at.desc()))
        plan=db.scalar(select(EvidencePlanItem).where(EvidencePlanItem.case_id==case.id,EvidencePlanItem.declaration_group==d.declaration_group))
        if not refs and plan.absence_eligible:
            for eid in [e.id for e in active_evidence(db,case.id) if d.declaration_group in e.source_context_json.get('search_groups',[]) and e.quality_json.get('usable')]:
                e=db.get(EvidenceItem,eid)
                if e:
                    refs.append({'evidence_id':e.id,'bbox':[0,0,1,1],'source_type':str(e.source_type),'raw_text':'Covered search area; no declaration text established','quality':e.quality_json,
                        'provenance':{'sha256':e.sha256,'captured_at':e.captured_at,'synced_at':e.synced_at,'latitude':e.latitude,'longitude':e.longitude,'accuracy_m':e.accuracy_m}})
        items.append({'id':d.id,'declaration_group':d.declaration_group,'title':GROUPS[d.declaration_group],'evidence_state':str(d.evidence_state),
            'fused_value':d.fused_value,'reviewed_value':review.payload.get('selected_value') if review else None,'candidate_count':len(candidates),'source_refs':refs,
            'applicable_rules':rules,'findings':findings,'verification_status':review.payload['status'] if review else 'UNREVIEWED',
            'review':row(review),'presentation':d.presentation_json,'review_flags':d.review_flags_json,'next_capture_prompt':plan.next_capture_prompt,'absence_eligible':plan.absence_eligible})
    return {'case_id':case.id,'items':sorted(items,key=lambda d:d['declaration_group']),'status':'READY' if items else 'PROCESSING'}

def public_map(db,case):
    internal=map_response(db,case)
    minimal=[{'title':i['title'],'value':i['fused_value'],'state':i['evidence_state'],'source_refs':i['source_refs']} for i in internal['items']]
    return {'scan_id':case.id,'notice':'Preliminary results only. Possible issues require review; this is not an official legal finding.',
        'declarations':public_observations(minimal),'physical_verification_required':True}
