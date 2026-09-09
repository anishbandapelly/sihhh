"""Dependency-free evidence, rule and control logic. No model can approve a finding."""
import re, math
from difflib import SequenceMatcher
from collections import defaultdict
from app.core.enums import EvidenceState, FindingStatus, FollowupStatus
from app.core.errors import require

RULE_DEFINITIONS = [
 ('LMPC-R01','D02','responsible_entity_name','presence','6(1)(a)'),
 ('LMPC-R02','D02','responsible_entity_address','address','6(1)(a), 10'),
 ('LMPC-R03','D01','common_generic_name','presence','6(1)(b)'),
 ('LMPC-R04','D03','quantity_value','presence','6(1)(c)'),
 ('LMPC-R05','D03','quantity_unit','quantity','6(1)(c)'),
 ('LMPC-R06','D05','manufacture_year','presence','6(1)(d)'),
 ('LMPC-R07','D05','manufacture_month','date','6(1)(d)'),
 ('LMPC-R08','D04','mrp_amount','presence','6(1)(e)'),
 ('LMPC-R09','D04','mrp_label','mrp','6(1)(e)'),
 ('LMPC-R10','D06','care_name_or_office','presence','6(2)'),
 ('LMPC-R11','D06','care_address','address','6(2)'),
 ('LMPC-R12','D06','care_phone','phone','6(2)'),
 ('LMPC-R13','D06','care_email','email','6(2)'),
 ('LMPC-R14','ALL','language','language','6(4)'),
]

def normalise(text):
    return re.sub(r'\s+', ' ', str(text).casefold().strip())

def parse_text(group, text):
    """Bounded typed parsers; raw text is retained separately on the candidate."""
    clean = re.sub(r'\s+', ' ', text).strip()
    out = {}
    if group == 'D01':
        out['common_generic_name'] = re.sub(r'^(commodity|product|generic name)\s*[:\-]?\s*', '', clean, flags=re.I)
    elif group == 'D02':
        match = re.search(r'(?:manufactured|packed|mfd|mfg|imported)\s*(?:&\s*packed\s*)?by\s*[:\-]?\s*([^;\n]+)', text, re.I)
        if match: out['responsible_entity_name'] = match.group(1).strip()
        address = re.search(r'(?:address\s*[:\-]?\s*)(.+)', clean, re.I)
        if address: out['responsible_entity_address'] = address.group(1).strip()
        elif re.search(r'\b\d{6}\b', clean): out['responsible_entity_address'] = clean
        out['role_label'] = 'IMPORTER' if re.search('import', clean, re.I) else 'MANUFACTURER_PACKER'
    elif group == 'D03':
        match = re.search(r'(\d+(?:\.\d+)?)\s*(kg|mg|g|ml|mL|l|L|cm|mm|m|nos\.?|units?|pieces?|N)\b', clean)
        if match:
            unit = match.group(2).lower().rstrip('.')
            out = {'quantity_value': float(match.group(1)), 'quantity_unit': unit,
                'quantity_kind': 'COUNT' if unit in ('nos','unit','units','piece','pieces','n') else 'MEASURE'}
    elif group == 'D04':
        match = re.search(r'(?:₹|Rs\.?|INR)\s*(\d+(?:\.\d{1,2})?)|(?:MRP|M\.?R\.?P\.?)\s*[:\-]?\s*(\d+(?:\.\d{1,2})?)', clean, re.I)
        if match: out['mrp_amount'] = float(match.group(1) or match.group(2))
        if re.search(r'₹|Rs\.?|INR', clean, re.I): out['currency'] = 'INR'
        if re.search(r'\bM\.?R\.?P\.?\b|maximum retail price', clean, re.I): out['mrp_label'] = 'MRP'
    elif group == 'D05':
        match = re.search(r'\b(\d{1,2})[/\-](\d{4})\b', clean)
        if match: out={'manufacture_month': int(match.group(1)), 'manufacture_year': int(match.group(2))}
    elif group == 'D06':
        contact = re.search(r'(?:consumer\s*care|customer\s*care)\s*[:\-]?\s*([^;\n]+)', text, re.I)
        if contact: out['care_name_or_office'] = contact.group(1).strip()
        address = re.search(r'(?:care address|address)\s*[:\-]?\s*([^;\n]+)', text, re.I)
        if address: out['care_address'] = address.group(1).strip()
        phone = re.search(r'(?:tel(?:ephone)?|phone|call|helpline)\s*[:\-]?\s*(\+?[\d ()-]{7,20})', text, re.I)
        if phone: out['care_phone'] = re.sub(r'[^\d+]', '', phone.group(1))
        email = re.search(r'[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}', text, re.I)
        if email: out['care_email'] = email.group(0).lower()
    return out

def classify_line(text):
    lower = normalise(text)
    if re.search(r'consumer care|customer care|care address|helpline|telephone|email|e-mail|phone|@', lower): return 'D06'
    if re.search(r'manufacture date|packed on|packing date|mfg date|month.*year', lower): return 'D05'
    if re.search(r'manufactur|packed by|mfd|mfg by|imported by', lower): return 'D02'
    if re.search(r'net\s*(weight|wt|quantity|qty|vol)|quantity|contents?', lower): return 'D03'
    if re.search(r'\bmrp\b|m\.r\.p|retail price|selling price', lower): return 'D04'
    if re.search(r'^commodity|^product\s*:|^generic name', lower): return 'D01'
    return None

def compatible_values(a, b, cfg):
    common = set(a) & set(b)
    if not common: return True  # Complementary fields from separate label regions.
    for key in common:
        left,right=a[key],b[key]
        if isinstance(left,(int,float)) and isinstance(right,(int,float)):
            if not math.isclose(left,right,rel_tol=cfg['numeric_tolerance'],abs_tol=0.000001): return False
        elif SequenceMatcher(None,normalise(left),normalise(right)).ratio() < cfg['string_similarity']: return False
    return True

def fuse(candidates, absence_eligible, cfg, obscured=False, applicable=True):
    sources = [c for c in candidates if c.get('evidence_id') and c.get('bbox') and len(c['bbox']) == 4]
    if not applicable: return {'state': 'NOT_APPLICABLE','value': None,'selected_id': None,'flags': []}
    credible = [c for c in sources if c['confidence'] >= cfg['ocr']['accept_confidence'] and c.get('usable', True)]
    if credible:
        for i,left in enumerate(credible):
            for right in credible[i+1:]:
                values_differ = not compatible_values(left['value'],right['value'],cfg['fusion'])
                # Empty parsed values must not hide reliable contradictory printed strings.
                if not left['value'] and not right['value']:
                    values_differ = normalise(left['raw_text']) != normalise(right['raw_text'])
                if values_differ:
                    return {'state':'CONFLICTING','value':None,'selected_id':None,'flags':['POTENTIAL_DECLARATION_INCONSISTENCY']}
        selected=max(credible,key=lambda c:c['confidence'])
        merged={}
        for c in sorted(credible,key=lambda c:c['confidence']): merged.update(c['value'])
        return {'state':'SUPPORTED','value':merged,'selected_id':selected['id'],'flags':[]}
    if obscured: state='OBSCURED_DAMAGED'
    elif sources: state='UNRESOLVED'
    elif absence_eligible: state='POTENTIALLY_ABSENT'
    else: state='UNRESOLVED'
    return {'state':state,'value':None,'selected_id':None,'flags':[]}

def coverage(profile, evidence, group, manually_confirmed=False):
    usable=[e for e in evidence if e['source_type'] in ('FIELD_CAPTURE','CITIZEN_UPLOAD') and e.get('synced') and e.get('usable')]
    roles={e.get('view_role') for e in usable}
    searched=[e for e in usable if group in e.get('search_groups',[])]
    complete=set(profile['roles']).issubset(roles) and bool(searched)
    if profile['manual']:
        complete=manually_confirmed and bool(searched) and any(e['source_type']=='FIELD_CAPTURE' for e in usable)
        state='MANUAL_CONFIRMED' if complete else ('PARTIAL' if usable else 'PLANNED')
    else: state='ADEQUATE' if complete else ('PARTIAL' if usable else 'PLANNED')
    missing=[p for role,p in zip(profile['roles'],profile['prompts']) if role not in roles]
    prompt=missing[0] if missing else f'Capture a close-up of the {group} declaration area, including any continuation.'
    if profile['manual'] and not manually_confirmed: prompt='Confirm the inspected areas after all local photographs have synchronised.'
    return {'coverage_state':state,'absence_eligible':complete,'next_capture_prompt':None if complete else prompt,
        'source_evidence_ids':[e['id'] for e in searched]}

def evaluate_rule(rule, declaration, sources, absence_eligible, raw_text=''):
    cfg=rule['config']; key=cfg.get('field'); logic=rule['logic_key']; value=declaration.get('value') or {}
    result={'result_state':'INSUFFICIENT','reason_code':None,'explanation':'Capture grounded evidence before evaluating this check.',
        'inputs':{'value':value,'source_refs':sources,'absence_eligible':absence_eligible,'raw_text':raw_text,'config':cfg}}
    if not cfg.get('applicable',True) or declaration['state']=='NOT_APPLICABLE':
        return {**result,'result_state':'N/A','explanation':cfg.get('applicability_reason','Not applicable to this fixture.')}
    if not sources: return result
    if declaration['state'] in ('UNRESOLVED','OBSCURED_DAMAGED','CONFLICTING'):
        return {**result,'result_state':'UNRESOLVED','reason_code':'POTENTIAL_DECLARATION_INCONSISTENCY' if declaration['state']=='CONFLICTING' else None,
            'explanation':'Officer review or additional evidence is required; no deterministic verdict was made.'}
    present=value.get(key) not in (None,'')
    if logic=='language':
        okay=bool(re.search(r'[A-Za-z\u0900-\u097F]',raw_text))
        return {**result,'result_state':'PASS' if okay else 'UNRESOLVED','explanation':'English or Devanagari evidence is present.' if okay else 'Script evidence needs review.'}
    if logic=='quantity' and raw_text:
        okay=value.get('quantity_unit') in cfg['supported_units'] and (value.get('quantity_value') or 0)>0
        return {**result,'result_state':'PASS' if okay else 'FINDING','reason_code':None if okay else 'NON_STANDARD_QUANTITY_EXPRESSION',
            'explanation':'Supported quantity expression.' if okay else 'Reliable printed quantity does not match this fixture’s supported representation; officer review required.'}
    if logic=='mrp' and raw_text:
        okay=bool(value.get('mrp_label')=='MRP' and value.get('currency')=='INR' and (value.get('mrp_amount') or 0)>0)
        return {**result,'result_state':'PASS' if okay else 'FINDING','reason_code':None if okay else 'NON_STANDARD_MRP_REPRESENTATION',
            'explanation':'Supported MRP representation.' if okay else 'Printed price does not match the selected fixture’s MRP structure; officer review required.'}
    if not present:
        return {**result,'result_state':'FINDING' if absence_eligible else 'INSUFFICIENT',
            'explanation':f'{key} was not found in the covered search areas; officer confirmation is required.' if absence_eligible else f'{key} is not yet evidenced. Inspect the remaining area.'}
    okay=True
    if logic=='address': okay=len(str(value[key]).split())>=cfg.get('min_address_tokens',3)
    elif logic=='date': okay=1<=value.get('manufacture_month',0)<=12 and 1900<=value.get('manufacture_year',0)<=9999
    elif logic=='phone': okay=bool(re.fullmatch(r'\+?\d{7,15}',str(value[key])))
    elif logic=='email': okay=bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',str(value[key])))
    return {**result,'result_state':'PASS' if okay else ('UNRESOLVED' if logic=='address' else 'FINDING'),
        'explanation':f'{key}: supported by the referenced region.' if okay else f'{key}: selected fixture format requires officer review.'}

def presentation(check, source, fixture, cfg):
    result={'presentation_state':'N/A','explanation':'No applicable presentation fixture configured.','inputs':{'source':source,'fixture':fixture}}
    if check=='PRES-02' and (not source or source.get('source_type')!='FIELD_CAPTURE' or not source.get('calibration')):
        return {**result,'presentation_state':'UNMEASURABLE_FONT_SIZE','explanation':'Physical verification required: no valid Inspector calibration.'}
    if not fixture: return result
    if not source or not source.get('usable') or not source.get('bbox'):
        return {**result,'presentation_state':'INSUFFICIENT_PRESENTATION_EVIDENCE','explanation':'Retake the photograph before checking the label presentation.'}
    bbox=source['bbox']
    if check=='PRES-01':
        zone=fixture.get('placement_zone')
        if not zone or not source.get('geometry_valid'): return {**result,'presentation_state':'INSUFFICIENT_PRESENTATION_EVIDENCE','explanation':'Usable package geometry and a configured placement zone are required.'}
        tolerance=cfg['placement_tolerance']
        okay=all([bbox[0]>=zone[0]-tolerance,bbox[1]>=zone[1]-tolerance,bbox[2]<=zone[2]+tolerance,bbox[3]<=zone[3]+tolerance])
        return {**result,'presentation_state':'PASS' if okay else 'POTENTIAL_PLACEMENT_CONCERN','explanation':'Region compared with the explicit fixture zone; officer review required for a concern.',
            'inputs':{**result['inputs'],'normalized_bbox':bbox,'placement_zone_id':fixture['id']}}
    if check=='PRES-02':
        cal=source['calibration']; px_per_mm=cal.get('px_per_mm',0)
        height=source.get('text_height_px')
        if px_per_mm<=0 or not height:
            return {**result,'presentation_state':'UNMEASURABLE_FONT_SIZE','explanation':'Character-height measurement or calibration is missing.'}
        measured=height/px_per_mm; threshold=fixture.get('minimum_text_height_mm')
        if threshold is None: return result
        okay=measured+cfg['measurement_tolerance_mm']>=threshold
        return {**result,'presentation_state':'PASS' if okay else 'POTENTIAL_FONT_SIZE_CONCERN','explanation':'Calibrated character height compared with the versioned fixture threshold.',
            'inputs':{**result['inputs'],'measured_text_height_mm':measured,'minimum_text_height_mm':threshold,'measurement_tolerance_mm':cfg['measurement_tolerance_mm'],'px_per_mm':px_per_mm}}
    contrast=source.get('contrast_metric'); stability=source.get('ocr_stability')
    if contrast is None or stability is None: return {**result,'presentation_state':'INSUFFICIENT_PRESENTATION_EVIDENCE','explanation':'Usable local contrast and cross-view stability measurements are required.'}
    concern=contrast<cfg['readability_contrast_threshold'] and stability<cfg['ocr_stability']
    return {**result,'presentation_state':'POTENTIAL_READABILITY_CONCERN' if concern else 'PASS',
        'explanation':'Quality-passing label region assessed for contrast and reading stability; officer review required for concerns.'}

def followup_transition(previous, target):
    states=['ASSIGNED','IN_PROGRESS','COMPLETED']
    require(previous in states and target in states,'Unsupported follow-up state.')
    require(target==previous or states.index(target)==states.index(previous)+1,'Follow-up transitions must advance one step.')
    return target

def verified_groups(records):
    """One verified contribution per case/rule. Citizen and AI observations cannot count."""
    groups=defaultdict(list)
    for item in records:
        if item['status'] not in ('ACCEPTED','CORRECTED') or not item.get('verification_event') or not item.get('field_source') or not item.get('identity_confirmed'): continue
        product,manufacturer=normalise(item['product']),normalise(item['manufacturer'])
        if not product or not manufacturer: continue
        base=(item['rule_code'],product,manufacturer,'')
        keys=[base]
        if item.get('batch'): keys.append((*base[:3],normalise(item['batch'])))
        for key in keys:
            if not any(x['case_id']==item['case_id'] for x in groups[key]): groups[key].append(item)
    qualified={key:items for key,items in groups.items() if len(items)>=3 and len({normalise(i['retailer']) for i in items if i['retailer']})>=2}
    # Prefer the more specific batch proposal when it has the identical contribution set.
    return {key:items for key,items in qualified.items() if key[3] or not any(other[:3]==key[:3] and other[3] and {i['case_id'] for i in members}=={i['case_id'] for i in items} for other,members in qualified.items())}

def public_observations(items):
    """Allowlist projection. Never serialise internal models into a Citizen response."""
    labels={'SUPPORTED':'Detected','CONFLICTING':'Different readings','UNRESOLVED':'Needs a better photo','OBSCURED_DAMAGED':'Label could not be read','POTENTIALLY_ABSENT':'Possible missing information','NOT_APPLICABLE':'Not required for this sample'}
    return [{'declaration':i['title'],'value':i.get('value'),'message':labels[i['state']],
        'sources':[{'evidence_id':s['evidence_id'],'bbox':s['bbox']} for s in i.get('source_refs',[]) if s.get('source_type')=='CITIZEN_UPLOAD']}
        for i in items]
