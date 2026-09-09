import hashlib
from sqlalchemy import select
from app.core.models import *
from app.core.errors import require
from app.core.config import PROTOTYPE
from app.cases.service import records, row, snapshot, summary
from app.compliance.service import map_response
from app.compliance.domain import parse_text, classify_line, evaluate_rule, fuse
from app.compliance.quality import analyse_quality
from app.compliance.ocr import extract
from app.audit.service import audit
from app.evidence.storage import storage

def context(db,kind,identifier):
    if kind=='case':
        case=db.get(Case,str(identifier)); require(case is not None,'Case not found.','NOT_FOUND',404)
        return case,summary(db,case)
    pattern=db.get(PatternCandidate,str(identifier)); require(pattern is not None,'Pattern not found.','NOT_FOUND',404)
    from app.patterns.service import pattern_summary
    return pattern,pattern_summary(db,pattern,True)

def query(db,who,body):
    record,data=context(db,body.context_type,body.context_id)
    key=body.prompt_key_or_text.upper().strip()
    sources=[{'source_type':body.context_type,'source_id':str(body.context_id),'title':data.get('reference') or data.get('match_factors',{}).get('product','Selected context'),
        'verification_label':str(record.status)}]
    gap=None
    if body.context_type=='pattern':
        p=data
        if key in ('SUMMARY','PRIORITY','RELATED','GAPS','WHY_CONNECTED'):
            answer=f"{p['verified_count']} officer-verified findings across {p['retailer_count']} retailers. {p['awaiting_count']} cases await verification; {p['citizen_lead_count']} citizen leads are separate. Matching factors: {', '.join(p['match_factors']['matched_fields'])}. Proposal status: {p['status']}."
            sources.extend({'source_type':'case','source_id':m['case']['id'],'title':m['case']['product_snapshot']['product_name'],'verification_label':m['finding']['status']} for m in p['members'])
            if key=='GAPS': gap='The relationship is a proposal. Confirm the common source through an officer-approved field investigation.'
        else: answer='The permitted records do not establish the requested conclusion.'; gap='No supported tool or source establishes this answer. No legal conclusion has been inferred.'
    else:
        case=record; mapped=map_response(db,case); items=mapped['items']
        findings=[f for i in items for f in i['findings']]
        verified=[f for f in findings if f['status'] in ('ACCEPTED','CORRECTED')]
        gaps=[i['title'] for i in items if i['evidence_state'] in ('UNRESOLVED','CONFLICTING','OBSCURED_DAMAGED','POTENTIALLY_ABSENT')]
        if key=='SUMMARY': answer=f"{data['product_snapshot']['product_name']} at {case.shop_name or 'retailer not yet confirmed'}. {len(verified)} officer-verified findings; {sum(f['status']=='POTENTIAL' for f in findings)} potential findings awaiting a separate officer decision. {len(gaps)} declaration groups need review or more evidence."
        elif key=='PRIORITY': answer='; '.join(case.priority_reasons.get('factors',['Priority factors are not yet available.']))
        elif key=='GAPS': answer='Inspect: '+', '.join(gaps) if gaps else 'No unresolved declaration is shown in the current map. Review the sources before completing the inspection.'
        elif key=='RELATED':
            from app.patterns.service import correlation_records
            p=snapshot(db,case.id)
            related=[r for r in correlation_records(db) if r['case_id']!=case.id and r['status'] in ('ACCEPTED','CORRECTED') and r['verification_event'] and r['product'].casefold()==p.product_name.casefold() and r['manufacturer'].casefold()==p.manufacturer.casefold()]
            answer=f'{len(related)} related officer-verified finding records share the product and manufacturer. Open their sources to inspect the relationship.'
            sources.extend({'source_type':'case','source_id':r['case_id'],'title':r['product']+' · '+r['retailer'],'verification_label':r['status']} for r in related)
        else: answer='The permitted records do not establish the requested conclusion.'; gap='This request needs evidence or a legal interpretation outside the supported tools.'
        if key in ('SUMMARY','GAPS'):
            sources.extend({'source_type':'evidence','source_id':s['evidence_id'],'title':i['title'],'verification_label':i['evidence_state']} for i in items for s in i['source_refs'][:1])
            if gaps: gap='Physical/source review required for: '+', '.join(gaps)+'.'
    answer_data={'answer':answer,'evidence_gap':gap,'source_cards':sources,'verification_labels':sorted({s['verification_label'] for s in sources}),'proposed_action_draft':None}
    audit(db,who,record.id if body.context_type=='case' else None,'COPILOT_ANSWER','case' if body.context_type=='case' else 'pattern',record.id,{'prompt_key':key,**answer_data})
    return answer_data

def draft_brief(db,who,body):
    from app.api.schemas import CopilotQuery
    answer=query(db,who,CopilotQuery(context_type=body.context_type,context_id=body.context_id,prompt_key_or_text='SUMMARY'))
    _,data=context(db,body.context_type,body.context_id)
    content=body.content or ('INSPECTION BRIEF — DRAFT\n\n'+answer['answer']+'\n\nEvidence to obtain\nConfirm the product, batch, manufacturer and retailer. Capture the profile overviews and targeted declaration regions. Preserve GPS, capture time and integrity metadata.\n\n'+(answer['evidence_gap'] or 'Review the existing sources and record remaining evidence needs.')+'\n\nAny field assignment requires separate officer approval.')
    creator=who.subject
    if body.draft_id:
        previous=db.get(AuditEvent,str(body.draft_id))
        require(previous and previous.event_type=='BRIEF_DRAFTED' and previous.payload['context_id']==str(body.context_id),'Draft does not belong to the selected context.','VALIDATION_ERROR',422)
        creator=previous.payload['creator']
    event=audit(db,who,str(body.context_id) if body.context_type=='case' else None,'BRIEF_DRAFTED','brief',uid(),
        {'context_type':body.context_type,'context_id':str(body.context_id),'status':'DRAFT','content':content,'source_refs':answer['source_cards'],
         'creator':creator,'last_editor':who.subject,'previous_draft_id':str(body.draft_id) if body.draft_id else None})
    return {'id':event.id,**event.payload,'created_at':event.created_at}

def approve_brief(db,who,draft_id,body):
    event=db.scalar(select(AuditEvent).where(AuditEvent.id==draft_id).with_for_update())
    require(event and event.event_type=='BRIEF_DRAFTED','Draft not found.','NOT_FOUND',404)
    existing=db.scalar(select(AuditEvent.id).where(AuditEvent.event_type=='BRIEF_DECISION',AuditEvent.entity_id==draft_id))
    require(not existing,'This draft already has an officer decision.','DUPLICATE_DECISION',409)
    require(not any(e.payload.get('previous_draft_id')==draft_id for e in db.scalars(select(AuditEvent).where(AuditEvent.event_type=='BRIEF_DRAFTED'))),'A newer edited draft exists; approve that version.')
    decision=audit(db,who,event.case_id,'BRIEF_DECISION','brief',draft_id,{'status':'APPROVED' if body.decision=='APPROVE' else 'REJECTED','reason':body.reason,'approved_by':who.subject,'draft_id':draft_id})
    return {'id':draft_id,**event.payload,**decision.payload,'approval_timestamp':decision.created_at}

def require_approved_brief(db,brief_id,case):
    if not brief_id: return
    draft=db.get(AuditEvent,str(brief_id))
    require(draft and draft.event_type=='BRIEF_DRAFTED','Brief not found.','NOT_FOUND',404)
    decision=db.scalar(select(AuditEvent).where(AuditEvent.entity_id==str(brief_id),AuditEvent.event_type=='BRIEF_DECISION'))
    require(decision and decision.payload['status']=='APPROVED','Approve this exact brief version before assigning work.')
    require(not any(e.payload.get('previous_draft_id')==str(brief_id) for e in db.scalars(select(AuditEvent).where(AuditEvent.event_type=='BRIEF_DRAFTED'))),'An edited draft requires fresh approval.')
    context_id=draft.payload['context_id']
    valid=context_id==case.id or (draft.payload['context_type']=='pattern' and case.priority_reasons.get('pattern_id')==context_id)
    require(valid,'This brief belongs to a different context.','FORBIDDEN_ROLE_OR_CASE',403)

def analyse_listing(db,who,data,input_kind,case=None,product_name=None,listing_text='',source_label='Officer upload',provider=None):
    quality=analyse_quality(data); eid=uid(); source_type='LISTING_UPLOAD' if input_kind=='LISTING_SCREENSHOT' else 'GOVERNMENT_UPLOAD'
    candidates=extract(data,provider) if quality['usable'] else []
    evidence=None
    if case:
        db.execute(select(Case).where(Case.id==case.id).with_for_update())
        sequence=max([e.sequence_no for e in records(db,EvidenceItem,case_id=case.id)]+[0])+1
        key=f'evidence/{case.id}/{eid}.png'; storage().put(key,data,'image/png')
        evidence=EvidenceItem(id=eid,case_id=case.id,captured_by_user_id=who.subject,sequence_no=sequence,source_type=EvidenceSource(source_type),
            source_context_json={'input_kind':input_kind,'source_label':source_label,'listing_text':listing_text,'product_name':product_name},storage_key=key,mime_type='image/png',sha256=hashlib.sha256(data).hexdigest(),captured_at=now(),synced_at=now(),sync_status=SyncStatus.SYNCHRONISED,quality_json=quality)
        db.add(evidence); db.flush()
    observations=[]; concerns=[]; refs=[]
    for c in candidates:
        reference={'evidence_id':eid,'bbox':c['bbox'],'source_type':source_type,'source_label':source_label}
        refs.append(reference)
        observations.append({'declaration_group':c['declaration_group'],'raw_text':c['raw_text'],'value':c['value'],'source_ref':reference,'verification_label':'UNVERIFIED_IMAGE_OBSERVATION'})
        if case:
            db.add(ExtractionCandidate(evidence_id=eid,declaration_group=c['declaration_group'],raw_text=c['raw_text'],normalized_value=c['value'],bbox=c['bbox'],confidence=c['confidence'],extractor=c['extractor']))
        for rule in db.scalars(select(Rule).where(Rule.active==True)):
            if rule.config_json.get('group')!=c['declaration_group']: continue
            fused=fuse([{**c,'id':uid(),'evidence_id':eid}],False,PROTOTYPE)
            result=evaluate_rule({'logic_key':rule.logic_key,'config':rule.config_json},fused,[reference],False,c['raw_text'])
            if result['result_state']=='FINDING': concerns.append({'rule_code':rule.rule_code,'rule_version':rule.version,'reason_code':result['reason_code'],'explanation':result['explanation'],'source_refs':[reference],'verification_label':'POTENTIAL_OFFICER_REVIEW'})
    supplied=[]
    for line in listing_text.splitlines():
        group=classify_line(line)
        if group: supplied.append({'declaration_group':group,'raw_text':line,'value':parse_text(group,line),'source_type':'SUPPLIED_TEXT','verification_label':'UNVERIFIED_SUPPLIED_TEXT'})
    missing=[GROUPS[g] for g in GROUPS if g not in {c['declaration_group'] for c in candidates}]
    result={'input_kind':input_kind,'source_label':source_label,'quality':quality,'visible_observations':observations,'supplied_text_observations':supplied,
        'possible_concerns':concerns,'evidence_gap':'INSUFFICIENT ONLINE IMAGE EVIDENCE. Unseen package areas cannot establish absence.'+(' Not visible: '+', '.join(missing)+'.' if missing else ' Complete physical package coverage has not been established.'),
        'physical_verification_required':True,'absence_eligible':False,'source_refs':refs,'attached_case_id':case.id if case else None}
    audit(db,who,case.id if case else None,'LISTING_REVIEWED','evidence',eid,result)
    return result
