import hashlib
from uuid import uuid4
from datetime import datetime,timezone
from pathlib import Path
from app.core.db import SessionLocal
from app.core.models import EvidenceItem
from app.seed import stable
ROOT=Path(__file__).resolve().parents[2]
def assigned(client,inspector):return next(r['case']['id'] for r in client.get('/api/v1/assignments/me',headers=inspector).json()['items'] if r['case']['status']=='ASSIGNED')
def test_roles_and_T15_repository(client,government,inspector,citizen):
 for h in (citizen,inspector):assert client.get('/api/v1/government/repository',headers=h).status_code==403
 r=client.get('/api/v1/government/repository',headers=government);assert r.status_code==200,r.text;assert r.json()['total']>0
 assert client.get('/api/v1/assignments/me',headers=citizen).status_code==403
 other=client.post('/api/v1/auth/login',json={'email':'inspector2@emaap.demo','password':'EmaapDemo!2026'}).json()['access_token'];assert client.get('/api/v1/cases/'+assigned(client,inspector),headers={'Authorization':'Bearer '+other}).status_code==403

def test_T5_T6_hash_and_retry(client,inspector):
 cid=assigned(client,inspector);data=(ROOT/'seed/fixtures/clean.png').read_bytes();eid=str(uuid4());body={'id':eid,'sequence_no':1,'sha256':hashlib.sha256(data).hexdigest(),'mime_type':'image/png','captured_at':datetime.now(timezone.utc).isoformat(),'source_context_json':{'view_role':'CORNER_A','search_groups':['D01']}};path='/api/v1/cases/'+cid+'/evidence'
 r=client.post(path,headers=inspector,json=body);assert r.status_code==200,r.text
 assert client.put('/api/v1/evidence/'+eid+'/content',headers=inspector,files={'image':('x.png',b'altered','image/png')}).status_code==409
 for _ in range(2):
  assert client.post(path,headers=inspector,json=body).status_code==200
  r=client.put('/api/v1/evidence/'+eid+'/content',headers=inspector,files={'image':('x.png',data,'image/png')});assert r.status_code==200,r.text;assert r.json()['sync_status']=='SYNCHRONISED'
 with SessionLocal() as db:assert len(db.query(EvidenceItem).filter_by(id=eid).all())==1

def test_T7_report_requires_human_review(client,inspector):
 cid=next(r['case']['id'] for r in client.get('/api/v1/assignments/me',headers=inspector).json()['items'] if r['case']['status']=='AWAITING_VERIFICATION');assert client.post('/api/v1/cases/'+cid+'/reports',headers=inspector).status_code==400

def test_T9_T10_grounding_and_approval(client,government):
 cid=client.get('/api/v1/government/cases',headers=government).json()['items'][0]['id'];ctx={'context_type':'case','context_id':cid}
 r=client.post('/api/v1/copilot/query',headers=government,json={**ctx,'prompt_key_or_text':'Conclude criminal intent'});assert r.status_code==200,r.text;assert r.json()['evidence_gap']
 r=client.post('/api/v1/copilot/inspection-brief',headers=government,json=ctx);assert r.status_code==200,r.text;b=r.json();assert b['status']=='DRAFT'
 r=client.post('/api/v1/cases/'+cid+'/assign',headers=government,json={'inspector_id':stable('inspector@emaap.demo'),'reason':'Test','brief_id':b['id']});assert r.status_code==400,r.text
 r=client.post('/api/v1/inspection-briefs/'+b['id']+'/approval',headers=government,json={'decision':'APPROVE','reason':'Sources checked'});assert r.status_code==200,r.text;assert r.json()['status']=='APPROVED'

def test_T17_listing_and_citizen_isolation(client,government,citizen):
 data=(ROOT/'seed/fixtures/listing-one-side.png').read_bytes();r=client.post('/api/v1/copilot/analyse-image',headers=government,files={'image':('listing.png',data,'image/png')},data={'input_kind':'LISTING_SCREENSHOT','listing_text':'Supplied price Rs 10'});assert r.status_code==200,r.text;assert r.json()['absence_eligible'] is False;assert r.json()['physical_verification_required']
 scan=client.post('/api/v1/citizen/scans',headers=citizen,json={'package_family':'RIGID_CUBOID'}).json();other={'Authorization':'Bearer '+client.post('/api/v1/auth/citizen-session').json()['access_token']};assert client.get('/api/v1/citizen/scans/'+scan['scan_id']+'/result',headers=other).status_code==403;assert client.get('/api/v1/cases/'+scan['scan_id'],headers=citizen).status_code==403

def test_complete_inspector_and_government_action_path(client,inspector,government):
 from app.core.models import Assignment,CaseStatus
 from app.cases.service import create_case
 from app.core.enums import PackageFamily,CaseType
 with SessionLocal() as db:
  c=create_case(db,None,PackageFamily.RIGID_CUBOID,'End-to-end demonstration',CaseType.INSPECTION,'ROUTINE_INSPECTION');c.status=CaseStatus.ASSIGNED;db.add(Assignment(case_id=c.id,inspector_id=stable('inspector@emaap.demo')));db.commit();cid=c.id
 profile={'package_family':'RIGID_CUBOID','reason':'Package inspected','product_snapshot':{'product_name':'End-to-end demonstration','manufacturer':'Demo Care Products Pvt Ltd','package_family':'RIGID_CUBOID'}}
 r=client.patch('/api/v1/cases/'+cid+'/capture-profile',headers=inspector,json=profile);assert r.status_code==200,r.text
 data=(ROOT/'seed/fixtures/clean.png').read_bytes();ids=[]
 for sequence,role in enumerate(['CORNER_A','CORNER_B','TOP_BASE'],1):
  eid=str(uuid4());ids.append(eid);body={'id':eid,'sequence_no':sequence,'sha256':hashlib.sha256(data).hexdigest(),'mime_type':'image/png','captured_at':datetime.now(timezone.utc).isoformat(),'source_context_json':{'view_role':role,'search_groups':['D01','D02','D03','D04','D05','D06']}}
  r=client.post('/api/v1/cases/'+cid+'/evidence',headers=inspector,json=body);assert r.status_code==200,r.text
  r=client.put('/api/v1/evidence/'+eid+'/content',headers=inspector,files={'image':('clean.png',data,'image/png')});assert r.status_code==200,r.text
 r=client.post('/api/v1/cases/'+cid+'/sync-complete',headers=inspector,json={'evidence_ids':ids});assert r.status_code==200,r.text
 r=client.post('/api/v1/cases/'+cid+'/analysis',headers=inspector);assert r.status_code==202,r.text
 run=client.get('/api/v1/analysis/'+r.json()['analysis_run_id'],headers=inspector);assert run.json()['status']=='SUCCEEDED',run.text
 mapped=client.get('/api/v1/cases/'+cid+'/compliance-map',headers=inspector).json();assert len(mapped['items'])==6
 for d in mapped['items']:
  assert d['source_refs'];refs=[{k:v for k,v in ref.items() if k in ('evidence_id','bbox','candidate_id')} for ref in d['source_refs']]
  r=client.post('/api/v1/cases/'+cid+'/declarations/'+d['declaration_group']+'/verification',headers=inspector,json={'action':'ACCEPT','reason':'Original label and extracted value checked','source_refs':refs});assert r.status_code==200,r.text
  for finding in d['findings']:
   r=client.post('/api/v1/findings/'+finding['id']+'/verification',headers=inspector,json={'action':'ACCEPT','reason':'Source and rule checked'});assert r.status_code==200,r.text
 r=client.post('/api/v1/cases/'+cid+'/reports',headers=inspector);assert r.status_code==202,r.text
 report_id=r.json()['report_id'];r=client.get('/api/v1/reports/'+report_id,headers=government);assert r.json()['status']=='READY',r.text
 for fmt,magic in [('pdf',b'%PDF'),('docx',b'PK')]:
  r=client.get('/api/v1/reports/'+report_id+'?format='+fmt,headers=government);assert r.status_code==200,r.text;assert r.content.startswith(magic)
 patterns=client.get('/api/v1/patterns',headers=government).json()['items'];assert patterns
 p=patterns[0];r=client.post('/api/v1/patterns/'+p['id']+'/decision',headers=government,json={'decision':'APPROVE','reason':'Verified recurrence reviewed'});assert r.status_code==200,r.text
 r=client.post('/api/v1/patterns/'+p['id']+'/systemic-case',headers=government);assert r.status_code==200,r.text;parent=r.json()['id']
 r=client.post('/api/v1/systemic-cases/'+parent+'/followups',headers=government,json={'assigned_to':stable('inspector@emaap.demo'),'note':'Physically inspect the common source'});assert r.status_code==200,r.text;fid=r.json()['id']
 for status in ['IN_PROGRESS','COMPLETED']:
  r=client.patch('/api/v1/followups/'+fid,headers=inspector,json={'status':status,'note':'Field progress recorded'});assert r.status_code==200,r.text

def test_citizen_scan_confirm_complaint_tracking(client,citizen):
 scan=client.post('/api/v1/citizen/scans',headers=citizen,json={'package_family':'RIGID_CUBOID','product_name':'Citizen demo'}).json();cid=scan['scan_id'];data=(ROOT/'seed/fixtures/clean.png').read_bytes();eid=str(uuid4());body={'id':eid,'sequence_no':1,'sha256':hashlib.sha256(data).hexdigest(),'mime_type':'image/png','captured_at':datetime.now(timezone.utc).isoformat(),'source_context_json':{'view_role':'CORNER_A','search_groups':['D01']}}
 assert client.post('/api/v1/cases/'+cid+'/evidence',headers=citizen,json=body).status_code==200
 assert client.put('/api/v1/evidence/'+eid+'/content',headers=citizen,files={'image':('clean.png',data,'image/png')}).status_code==200
 r=client.post('/api/v1/citizen/scans/'+cid+'/analysis',headers=citizen);assert r.status_code==202,r.text
 r=client.get('/api/v1/citizen/scans/'+cid+'/result',headers=citizen);assert r.status_code==200,r.text;assert 'rule_results' not in r.text
 r=client.post('/api/v1/citizen/complaints',headers=citizen,json={'scan_id':cid,'product_snapshot':{'product_name':'Citizen demo','package_family':'RIGID_CUBOID'},'shop_name':'Demo retailer','confirmed':True});assert r.status_code==200,r.text;receipt=r.json()
 r=client.get('/api/v1/citizen/complaints/'+receipt['reference']+'/status',headers={**citizen,'X-Tracking-Token':receipt['tracking_token']});assert r.status_code==200,r.text

def test_priority_override_retains_computation_and_roles(client,government,inspector,citizen):
 cid=client.get('/api/v1/government/cases',headers=government).json()['items'][0]['id'];path='/api/v1/cases/'+cid+'/priority';body={'priority_band':'HIGH','reason':'Officer identified a time-sensitive follow-up'}
 for headers in [inspector,citizen]:assert client.patch(path,headers=headers,json=body).status_code==403
 r=client.patch(path,headers=government,json=body);assert r.status_code==200,r.text;reasons=r.json()['priority_reasons'];assert 'computed_band' in reasons;assert reasons['override']['reason']==body['reason']
 history=client.get('/api/v1/cases/'+cid,headers=government).json()['history'];assert any(h['event_type']=='PRIORITY_OVERRIDDEN' for h in history)

def test_declaration_correction_is_not_finding_verification(client,inspector):
 rows=client.get('/api/v1/assignments/me',headers=inspector).json()['items']
 for row in rows:
  if row['case']['status']!='AWAITING_VERIFICATION':continue
  cid=row['case']['id'];mapped=client.get('/api/v1/cases/'+cid+'/compliance-map',headers=inspector).json();d=next((d for d in mapped['items'] if d['declaration_group']=='D03' and d['source_refs']),None)
  if d:break
 assert d
 refs=[{k:v for k,v in ref.items() if k in ('evidence_id','bbox','candidate_id')} for ref in d['source_refs']]
 r=client.post('/api/v1/cases/'+cid+'/declarations/D03/verification',headers=inspector,json={'action':'CORRECT','reason':'Read quantity directly from original region','corrected_value':{'quantity_value':500,'quantity_unit':'g','quantity_kind':'MEASURE'},'source_refs':refs});assert r.status_code==200,r.text
 after=client.get('/api/v1/cases/'+cid+'/compliance-map',headers=inspector).json();d=next(d for d in after['items'] if d['declaration_group']=='D03');assert d['verification_status']=='CORRECTED';assert all(f['status']=='POTENTIAL' for f in d['findings'])

def test_T1_complete_search_absence_keeps_inspected_sources(client,inspector):
 import json
 scenarios=json.loads((ROOT/'seed/demo-case-index.json').read_text());cid=next(x['case_id'] for x in scenarios if x['fixture']=='absent-care')
 r=client.get('/api/v1/cases/'+cid+'/compliance-map',headers=inspector);assert r.status_code==200,r.text;d=next(x for x in r.json()['items'] if x['declaration_group']=='D06');assert d['evidence_state']=='POTENTIALLY_ABSENT';assert d['source_refs'];assert d['absence_eligible']
