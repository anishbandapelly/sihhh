"""Deterministic demo reset. Run only against the isolated local demo database."""
import argparse,hashlib,sys
from pathlib import Path
from uuid import uuid5,NAMESPACE_DNS
from datetime import timedelta
from sqlalchemy import select,text
from app.core.models import *
from app.core.db import SessionLocal,engine,Base
from app.core.config import ROOT,settings,PROTOTYPE
from app.auth.service import hash_password,Actor
from app.cases.service import create_case,records,snapshot
from app.compliance.domain import RULE_DEFINITIONS
from app.compliance.service import run_analysis
from app.evidence.storage import storage
from app.compliance.quality import analyse_quality
from app.audit.service import audit
from app.verification.service import review_declaration,verify_finding
from app.api.schemas import DeclarationReview,Verification
from app.reports.service import queue_report,generate_report

def stable(name): return str(uuid5(NAMESPACE_DNS,'e-maap-demo:'+name))

def seed(reset=False):
    if not settings.demo_mode: raise RuntimeError('Demo seeding requires DEMO_MODE=true.')
    if reset:
        with engine.begin() as connection:
            if engine.dialect.name=='postgresql':
                connection.execute(text('TRUNCATE TABLE '+', '.join('"'+t+'"' for t in Base.metadata.tables)+' RESTART IDENTITY CASCADE'))
            else:
                for table in reversed(Base.metadata.sorted_tables): connection.execute(table.delete())
    sys.path.insert(0,str(ROOT/'scripts'))
    from generate_fixtures import generate
    generate()
    with SessionLocal() as db:
        if db.scalar(select(User.id)):
            print('Demo records already exist. Use --reset on the demo database for a deterministic reset.');return
        for name,email,role in [('Kavya Rao','government@emaap.demo',Role.GOVERNMENT_OFFICER),('Arjun Mehta','inspector@emaap.demo',Role.INSPECTOR),('Meera Nair','inspector2@emaap.demo',Role.INSPECTOR)]:
            db.add(User(id=stable(email),name=name,email=email,role=role,password_hash=hash_password('EmaapDemo!2026')))
        for code,group,field,logic,reference in RULE_DEFINITIONS:
            cfg={'group':group,'field':field,'applicable':True,'fixture_scope':'domestic general-retail SRS sample','min_address_tokens':3,
                'supported_units':['kg','g','mg','l','ml','m','cm','mm','nos','n','unit','units','piece','pieces']}
            db.add(Rule(id=stable(code),rule_code=code,version='SRS-2026-09-prototype-1',legal_reference='SRS selected Legal Metrology (Packaged Commodities) Rules reference '+reference+'; consolidated legal freeze pending',logic_key=logic,config_json=cfg))
        for code in ('PRES-01','PRES-02','PRES-03'):
            db.add(Rule(id=stable(code),rule_code=code,version='SRS-PRESENTATION-FIXTURE-1',legal_reference='SRS 15.1.1: explicit engineering presentation fixture; not a universal legal threshold',logic_key=code,config_json={'group':'PRESENTATION','fixture_only':True}))
        db.commit()
    actor=Actor(stable('inspector@emaap.demo'),'officer','INSPECTOR','Arjun Mehta')
    scenarios=[('Assigned field inspection','clean',False),('Verified recurrence · Jayanagar','missing-care-phone',True),('Verified recurrence · Basavanagudi','missing-care-phone',True),('Historical report · Malleshwaram','missing-care-phone',True),
        ('Incomplete package coverage','incomplete',False),('Conflicting quantity readings','conflict-600g',False),('Blurred capture','blurred',False),('Glare-heavy capture','glare',False),('Font size unmeasurable','font-unmeasurable',False),('Calibrated small text','font-small-calibrated',False),('Placement concern fixture','placement',False),('Readability concern fixture','readability',False),('Non-standard quantity and MRP','nonstandard',False),('Obscured care region','obscured',False),('Compliant package fixture','clean',False),('Potentially absent care declaration','absent-care',False)]
    ids=[]
    for index,(label,fixture,verified) in enumerate(scenarios):
        with SessionLocal() as db:
            case=create_case(db,None,PackageFamily.RIGID_CUBOID,'Household cleaning powder',CaseType.INSPECTION,'ROUTINE_INSPECTION',case_id=stable('inspection-'+str(index)))
            case.shop_name=['Jayanagar General Stores','Basavanagudi Mart','Malleshwaram Supplies','Rajajinagar Retail'][index%4]
            case.shop_location={'area':['Jayanagar','Basavanagudi','Malleshwaram','Rajajinagar'][index%4],'latitude':12.95+index/1000,'longitude':77.58+index/1000}
            case.created_at=now()-timedelta(days=index+1); case.status=CaseStatus.ASSIGNED
            p=snapshot(db,case.id); p.brand='Demo Care'; p.manufacturer='Demo Care Products Pvt Ltd';p.batch_lot='B241'
            p.officer_confirmed_json={k:{'officer_id':actor.subject,'value':getattr(p,k),'time':now().isoformat(),'seeded_demo_event':True} for k in ('product_name','manufacturer','batch_lot')}
            db.add(Assignment(case_id=case.id,inspector_id=actor.subject)); db.flush()
            audit(db,actor,case.id,'DEMO_SCENARIO','case',case.id,{'label':label,'fixture':fixture,'synthetic':True})
            ids.append({'case_id':case.id,'scenario':label,'fixture':fixture})
            if index==0: db.commit();continue
            roles=PROTOTYPE['profiles']['RIGID_CUBOID']['roles']+['DECLARATION_CLOSEUP']
            if fixture=='incomplete': roles=roles[:1]
            for seq,role in enumerate(roles,1):
                f='clean' if fixture=='conflict-600g' and seq==1 else fixture
                data=(ROOT/'seed/fixtures'/f'{f}.png').read_bytes(); eid=stable(f'{index}:{seq}')
                key=f'evidence/{case.id}/{eid}.png'; storage().put(key,data,'image/png')
                cal={'calibration_source':'FIXTURE_KNOWN_SCALE','reference_id':'ENGINEERING-SCALE-1','reference_length_mm':10,'reference_length_px':100,'px_per_mm':10,'reference_bbox':[0.04,0.04,0.14,0.06]} if fixture=='font-small-calibrated' else None
                db.add(EvidenceItem(id=eid,case_id=case.id,captured_by_user_id=actor.subject,sequence_no=seq,source_type=EvidenceSource.FIELD_CAPTURE,
                    source_context_json={'view_role':role,'search_groups':list(GROUPS) if role=='DECLARATION_CLOSEUP' else [],'observed_condition':'OBSCURED_DAMAGED' if fixture=='obscured' else 'CLEAR','seed_fixture':f},
                    storage_key=key,mime_type='image/png',sha256=hashlib.sha256(data).hexdigest(),captured_at=now(),synced_at=now(),sync_status=SyncStatus.SYNCHRONISED,
                    quality_json=analyse_quality(data),calibration_json=cal))
            db.flush()
            audit(db,actor,case.id,'SYNC_COMPLETED','case',case.id,{'evidence_ids':[e.id for e in records(db,EvidenceItem,case_id=case.id)]})
            run=AnalysisRun(case_id=case.id); db.add(run); db.flush(); runid=run.id; cid=case.id; case.status=CaseStatus.ANALYSING; db.commit()
        run_analysis(runid,False,'fixture')
        if verified:
            with SessionLocal() as db:
                case=db.get(Case,cid)
                for d in records(db,DeclarationResult,case_id=cid):
                    candidates=[db.get(ExtractionCandidate,i) for i in d.source_ids]
                    refs=[{'evidence_id':c.evidence_id,'candidate_id':c.id,'bbox':c.bbox} for c in candidates if c]
                    if not refs:
                        refs=[{'evidence_id':e.id,'bbox':[0,0,1,1]} for e in records(db,EvidenceItem,case_id=cid) if e.quality_json.get('usable')]
                    review_declaration(db,actor,case,d.declaration_group,DeclarationReview(action='ACCEPT',reason='Seeded demo officer reviewed the labelled fixture source.',source_refs=refs))
                for f in records(db,Finding,case_id=cid): verify_finding(db,actor,f,Verification(action='ACCEPT',reason='Seeded demo officer confirms the fixture finding; synthetic demonstration record.'))
                report,created=queue_report(db,actor,case); rid=report.id
            generate_report(rid)
    with SessionLocal() as db:
        citizen=Actor(stable('demo-citizen'),'citizen')
        case=create_case(db,citizen,PackageFamily.RIGID_CUBOID,'Household cleaning powder',case_id=stable('citizen-lead')); case.shop_name='Citizen-reported retailer';case.shop_location={'area':'Jayanagar'}
        case.public_tracking_token_hash=hashlib.sha256(b'emaap-demo-tracking-token').hexdigest()
        p=snapshot(db,case.id);p.manufacturer='Demo Care Products Pvt Ltd';p.batch_lot='B241';p.brand='Demo Care'
        audit(db,None,case.id,'CITIZEN_CONFIRMED','case',case.id,{'synthetic':True,'confirmed':True,'claim':'Possible missing consumer-care contact'})
        db.commit()
    (ROOT/'seed/demo-case-index.json').write_text(__import__('json').dumps(ids,indent=2))
    print(f'Seeded {len(scenarios)} inspection scenarios, one citizen lead, three verified recurrence cases and report jobs. Password: EmaapDemo!2026 (DEMO ONLY).')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--reset',action='store_true');args=parser.parse_args();seed(args.reset)
