from datetime import datetime, time, timedelta, timezone
import sqlalchemy as sa
from sqlalchemy import select
from app.core.models import *
from app.cases.service import snapshot, records, summary, row

def history_query(db,filters):
    statement=select(Case).join(ProductSnapshot,ProductSnapshot.case_id==Case.id)
    q=filters.get('q')
    if q:
        term='%'+q.replace('%','\\%').replace('_','\\_')+'%'
        statement=statement.where(sa.or_(*[column.ilike(term,escape='\\') for column in (ProductSnapshot.product_name,ProductSnapshot.brand,ProductSnapshot.manufacturer,ProductSnapshot.batch_lot,ProductSnapshot.barcode)]))
    for name,column in [('manufacturer',ProductSnapshot.manufacturer),('batch_lot',ProductSnapshot.batch_lot),('retailer',Case.shop_name),('brand',ProductSnapshot.brand)]:
        if filters.get(name): statement=statement.where(column.ilike('%'+filters[name]+'%'))
    for name,column in [('status',Case.status),('source',Case.source)]:
        if filters.get(name): statement=statement.where(column==filters[name])
    if filters.get('location'): statement=statement.where(sa.cast(Case.shop_location,sa.Text).ilike('%'+filters['location']+'%'))
    if filters.get('date_from'): statement=statement.where(Case.created_at>=datetime.combine(filters['date_from'],time.min,tzinfo=timezone.utc))
    if filters.get('date_to'): statement=statement.where(Case.created_at<datetime.combine(filters['date_to']+timedelta(days=1),time.min,tzinfo=timezone.utc))
    if filters.get('rule_code'):
        sub=select(RuleResult.case_id).join(Rule,Rule.id==RuleResult.rule_id).where(Rule.rule_code==filters['rule_code'])
        statement=statement.where(Case.id.in_(sub))
    if filters.get('finding_status'): statement=statement.where(Case.id.in_(select(Finding.case_id).where(Finding.status==filters['finding_status'])))
    total=db.scalar(select(sa.func.count()).select_from(statement.subquery()))
    page=filters.get('page',1); size=filters.get('page_size',20)
    cases=list(db.scalars(statement.order_by(Case.created_at.desc(),Case.id).offset((page-1)*size).limit(size)))
    items=[]
    for case in cases:
        issues=[]; statuses=set()
        for f in records(db,Finding,case_id=case.id):
            rr=db.get(RuleResult,f.rule_result_id); rule=db.get(Rule,rr.rule_id)
            issues.append(rule.rule_code); statuses.add(str(f.status))
        items.append({'case_id':case.id,'scanned_at':case.created_at,'product_snapshot':row(snapshot(db,case.id)),
            'retailer':case.shop_name,'location':case.shop_location,'case_status':str(case.status),'issue_summary':sorted(set(issues)),
            'verification_status':sorted(statuses),'report_refs':[row(r) for r in records(db,Report,case_id=case.id)]})
    return {'items':items,'total':total,'page':page,'page_size':size}

def report_search(db,filters):
    statement=select(Report,ProductSnapshot).join(ProductSnapshot,Report.case_id==ProductSnapshot.case_id)
    if filters.get('q'): statement=statement.where(ProductSnapshot.product_name.ilike('%'+filters['q']+'%'))
    if filters.get('case_id'): statement=statement.where(Report.case_id==str(filters['case_id']))
    if filters.get('status'): statement=statement.where(Report.status==filters['status'])
    if filters.get('date_from'): statement=statement.where(Report.generated_at>=datetime.combine(filters['date_from'],time.min,tzinfo=timezone.utc))
    if filters.get('date_to'): statement=statement.where(Report.generated_at<datetime.combine(filters['date_to']+timedelta(days=1),time.min,tzinfo=timezone.utc))
    total=db.scalar(select(sa.func.count()).select_from(statement.subquery()))
    page=filters.get('page',1); size=filters.get('page_size',20)
    result=db.execute(statement.order_by(Report.generated_at.desc()).offset((page-1)*size).limit(size)).all()
    return {'items':[{'report_id':r.id,'case_id':r.case_id,'product_name':p.product_name,'generated_at':r.generated_at,'status':str(r.status),'pdf_available':r.status==ReportStatus.READY and bool(r.storage_key),'editable_available':r.status==ReportStatus.READY and bool(r.editable_storage_key)} for r,p in result], 'total':total,'page':page,'page_size':size}
