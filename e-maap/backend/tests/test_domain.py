"""Executable without third-party dependencies: python -m unittest discover -s backend/tests -p test_domain.py."""
import sys,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
from app.compliance.domain import coverage,fuse,evaluate_rule,presentation,verified_groups,public_observations,followup_transition,classify_line,parse_text
from app.core.errors import DomainError
CFG=json.loads((ROOT/'seed/prototype-config.json').read_text())
def candidate(value,identifier='a',confidence=.99):return dict(id=identifier,evidence_id='image-'+identifier,bbox=[.1,.1,.9,.2],confidence=confidence,value=value,raw_text=str(value),usable=True)
class AcceptanceDomain(unittest.TestCase):
 def test_T1_coverage_precedes_absence(self):
  p=CFG['profiles']['RIGID_CUBOID'];r=coverage(p,[dict(id='one',source_type='FIELD_CAPTURE',synced=True,usable=True,view_role=p['roles'][0],search_groups=['D03'])],'D03');self.assertFalse(r['absence_eligible']);self.assertTrue(r['next_capture_prompt']);self.assertEqual(fuse([],r['absence_eligible'],CFG)['state'],'UNRESOLVED')
 def test_T2_unusable_capture_cannot_satisfy_coverage(self):
  p=CFG['profiles']['RIGID_CUBOID'];e=[dict(id=r,source_type='FIELD_CAPTURE',synced=True,usable=False,view_role=r,search_groups=['D01']) for r in p['roles']];self.assertFalse(coverage(p,e,'D01')['absence_eligible'])
 def test_T3_source_before_rule(self):
  r=evaluate_rule({'logic_key':'presence','config':{'field':'x'}},{'state':'SUPPORTED','value':{'x':'AI guess'}},[],True);self.assertEqual(r['result_state'],'INSUFFICIENT')
 def test_T4_conflicts_never_silently_collapse(self):
  c=[candidate({'quantity_value':500}),candidate({'quantity_value':600},'b')];self.assertEqual(fuse(c,True,CFG)['state'],'CONFLICTING');self.assertEqual(len(c),2)
 def test_T8_only_verified_field_records_count(self):
  base=dict(rule_code='LMPC-R12',product='Soap',manufacturer='Demo',batch='A',verification_event=True,field_source=True,identity_confirmed=True,status='ACCEPTED');records=[dict(base,id=str(i),case_id=str(i),retailer=str(i%2)) for i in range(3)];self.assertEqual(len(verified_groups(records)),1)
  for key,value in [('status','POTENTIAL'),('verification_event',False),('field_source',False),('identity_confirmed',False)]:
   changed=[dict(r,**{key:value}) if i==2 else r for i,r in enumerate(records)];self.assertFalse(verified_groups(changed),key)
 def test_T11_other_requires_manual_confirmation(self):
  p=CFG['profiles']['OTHER_PACKAGE'];e=[dict(id=r,source_type='FIELD_CAPTURE',synced=True,usable=True,view_role=r,search_groups=['D01']) for r in p['roles']];self.assertFalse(coverage(p,e,'D01')['absence_eligible']);self.assertTrue(coverage(p,e,'D01',True)['absence_eligible'])
 def test_T12_placement_needs_geometry_and_fixture(self):
  s=dict(source_type='FIELD_CAPTURE',bbox=[.8,.2,.98,.3],usable=True,geometry_valid=True);f=dict(id='fixture',placement_zone=[0,0,.7,1]);self.assertEqual(presentation('PRES-01',s,f,CFG['presentation'])['presentation_state'],'POTENTIAL_PLACEMENT_CONCERN');self.assertEqual(presentation('PRES-01',s,None,CFG['presentation'])['presentation_state'],'N/A')
 def test_T13_physical_font_requires_inspector_calibration(self):
  s=dict(source_type='CITIZEN_UPLOAD',bbox=[0,0,1,1],usable=True,text_height_px=10,calibration={'px_per_mm':10});f=dict(minimum_text_height_mm=2);self.assertEqual(presentation('PRES-02',s,f,CFG['presentation'])['presentation_state'],'UNMEASURABLE_FONT_SIZE');s['source_type']='FIELD_CAPTURE';self.assertEqual(presentation('PRES-02',s,f,CFG['presentation'])['presentation_state'],'POTENTIAL_FONT_SIZE_CONCERN')
 def test_T14_capture_quality_is_not_readability_finding(self):
  s=dict(source_type='FIELD_CAPTURE',bbox=[0,0,1,1],usable=False,contrast_metric=2,ocr_stability=.2);self.assertEqual(presentation('PRES-03',s,{'id':'fixture'},CFG['presentation'])['presentation_state'],'INSUFFICIENT_PRESENTATION_EVIDENCE');s['usable']=True;self.assertEqual(presentation('PRES-03',s,{'id':'fixture'},CFG['presentation'])['presentation_state'],'POTENTIAL_READABILITY_CONCERN')
 def test_T16_bounded_nonstandard_quantity(self):
  r=evaluate_rule({'logic_key':'quantity','config':{'field':'quantity_unit','supported_units':['g','kg']}},{'state':'SUPPORTED','value':{}},[{'evidence_id':'x','bbox':[0,0,1,1]}],False,'A handful');self.assertEqual(r['reason_code'],'NON_STANDARD_QUANTITY_EXPRESSION')
 def test_T17_listing_never_establishes_absence(self):
  p=CFG['profiles']['RIGID_CUBOID'];e=[dict(id=r,source_type='LISTING_UPLOAD',synced=True,usable=True,view_role=r,search_groups=['D01']) for r in p['roles']];self.assertFalse(coverage(p,e,'D01',True)['absence_eligible'])
 def test_citizen_projection_excludes_internal_sources_and_fields(self):
  out=public_observations([dict(title='Quantity',state='SUPPORTED',value={'quantity_value':500},verified_findings=['secret'],source_refs=[dict(evidence_id='private',bbox=[0,0,1,1],source_type='FIELD_CAPTURE'),dict(evidence_id='public',bbox=[0,0,1,1],source_type='CITIZEN_UPLOAD')])]);self.assertNotIn('secret',str(out));self.assertNotIn('private',str(out));self.assertEqual(out[0]['sources'][0]['evidence_id'],'public')
 def test_followup_cannot_skip_or_reopen(self):
  self.assertEqual(followup_transition('ASSIGNED','IN_PROGRESS'),'IN_PROGRESS')
  for prev,next_ in [('ASSIGNED','COMPLETED'),('COMPLETED','ASSIGNED')]:
   with self.assertRaises(DomainError):followup_transition(prev,next_)
 def test_manufacture_date_is_not_manufacturer(self):
  self.assertEqual(classify_line('Manufacture date 06/2026'),'D05');self.assertEqual(parse_text('D05','Manufacture date 06/2026')['manufacture_month'],6)
if __name__=='__main__':unittest.main()
