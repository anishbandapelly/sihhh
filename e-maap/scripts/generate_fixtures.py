"""Create labelled engineering fixtures; no real brand or official finding is asserted."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import hashlib,json,sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.compliance.domain import parse_text

def generate():
    destination=ROOT/'seed/fixtures'; destination.mkdir(parents=True,exist_ok=True)
    font_path=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    font=ImageFont.truetype(str(font_path),24) if font_path.exists() else ImageFont.load_default(size=24)
    title_font=ImageFont.truetype(str(font_path),32) if font_path.exists() else ImageFont.load_default(size=32)
    manifest={}
    names=['clean','missing-care-phone','conflict-600g','blurred','glare','incomplete','font-unmeasurable','font-small-calibrated','placement','readability','nonstandard','listing-one-side','obscured','absent-care']
    for name in names:
        image=Image.new('RGB',(1200,1000),(225,229,233)); draw=ImageDraw.Draw(image)
        draw.rectangle((30,30,1170,970),outline=(30,50,65),width=4)
        draw.text((65,48),'SIH ENGINEERING FIXTURE · e-Maap',font=title_font,fill=(25,50,65))
        draw.text((65,94),'Fictional product. Controlled label sample; not a legal certification.',font=font,fill=(65,75,85))
        texts={
            'D01':'Commodity: Household cleaning powder',
            'D02':'Manufactured by: Demo Care Products Pvt Ltd\nAddress: 24 Industrial Road, Bengaluru 560001',
            'D03':'Net quantity: 500 g',
            'D04':'MRP: INR 125.00 (inclusive of all taxes)',
            'D05':'Manufacture date: 08/2026',
            'D06':'Consumer care: Demo Care Office\nCare address: 24 Industrial Road, Bengaluru 560001\nPhone: 18001234567; Email: care@example.test'
        }
        if name=='missing-care-phone': texts['D06']='Consumer care: Demo Care Office\nCare address: 24 Industrial Road, Bengaluru 560001\nEmail: care@example.test'
        if name=='conflict-600g': texts['D03']='Net quantity: 600 g'
        if name=='nonstandard': texts['D03']='Net quantity: one generous scoop'; texts['D04']='Selling price: 125 credits'
        if name=='listing-one-side': texts={k:v for k,v in texts.items() if k in ('D01','D03')}
        if name in ('obscured','absent-care'): texts.pop('D06')
        candidates=[]
        y=165
        for group,text in texts.items():
            current_font=font; fill=(24,32,42)
            if name=='font-small-calibrated' and group=='D04': current_font=ImageFont.truetype(str(font_path),12) if font_path.exists() else ImageFont.load_default(size=12)
            if name=='readability' and group=='D04': fill=(185,189,193)
            x=65
            if name=='placement' and group=='D04': x=490
            box=draw.multiline_textbbox((x,y),text,font=current_font,spacing=9)
            draw.multiline_text((x,y),text,font=current_font,fill=fill,spacing=9)
            bbox=[box[0]/1200,box[1]/1000,min(box[2]/1200,0.96),box[3]/1000]
            candidates.append({'declaration_group':group,'raw_text':text,'value':parse_text(group,text),'bbox':bbox,'confidence':0.98})
            y+=110 if group!='D06' else 150
        draw.text((65,905),'Batch B241 · Fixture: '+name,font=font,fill=(25,50,65))
        if name=='blurred': image=image.filter(ImageFilter.GaussianBlur(12))
        if name=='glare': ImageDraw.Draw(image).rectangle((600,100,1160,850),fill='white')
        if name=='obscured': ImageDraw.Draw(image).rectangle((65,715,1120,865),fill=(85,95,105))
        path=destination/(name+'.png');image.save(path)
        pres={}
        if name in ('font-small-calibrated','placement','readability'):
            pres['D04']={'id':'ENGINEERING-FIXTURE-ZONE-1','placement_zone':[0.02,0.1,0.80,0.9],
                'minimum_text_height_mm':2.0,'fixture_ocr_stability':0.5 if name=='readability' else 1.0,
                'scope':'Synthetic presentation fixture only; not a universal statutory limit.'}
        manifest[hashlib.sha256(path.read_bytes()).hexdigest()]={'file':path.name,'scenario':name,'candidates':candidates,'presentation':pres}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return len(manifest)

if __name__=='__main__': print(f'Generated {generate()} labelled fixture images.')
