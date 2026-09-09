import cv2
import numpy as np
from app.core.config import PROTOTYPE
from app.core.errors import DomainError

def decode(data):
    image=cv2.imdecode(np.frombuffer(data,dtype=np.uint8),cv2.IMREAD_COLOR)
    if image is None: raise DomainError('VALIDATION_ERROR','Upload a readable JPEG or PNG image.',422)
    h,w=image.shape[:2]
    if h*w>PROTOTYPE['upload']['max_image_pixels']: raise DomainError('FILE_TOO_LARGE','Image dimensions exceed the configured pixel limit.',413)
    return image

def analyse_quality(data):
    image=decode(data); h,w=image.shape[:2]; cfg=PROTOTYPE['capture']
    width=min(w,cfg['sample_width']); sample=cv2.resize(image,(width,max(1,round(h*width/w))))
    gray=cv2.cvtColor(sample,cv2.COLOR_BGR2GRAY)
    blur=float(cv2.Laplacian(gray,cv2.CV_64F).var())
    # Specular clipping proxy. Pure-white backgrounds can warn; never a legal finding.
    local=cv2.GaussianBlur(gray.astype(np.float32),(7,7),0)
    glare=float(np.mean((gray>=cfg['glare_luminance']) & (np.abs(gray-local)<cfg['glare_local_contrast'])))
    flags=[]
    if blur<cfg['blur_threshold']: flags.append('BLUR')
    if glare>cfg['glare_threshold']: flags.append('GLARE')
    return {'state':flags[0] if flags else 'GOOD','usable':not flags,'flags':flags,'blur_metric':round(blur,3),'glare_metric':round(glare,4),
        'width':w,'height':h,'config_version':PROTOTYPE['version'],
        'instruction':'Hold steady and focus on the text.' if 'BLUR' in flags else ('Tilt the package away from reflections and retake.' if flags else 'Capture is usable; continue to the next evidence area.')}

def region_metrics(data,bbox):
    image=decode(data); h,w=image.shape[:2]; x1,y1,x2,y2=bbox
    region=image[max(0,int(y1*h)):min(h,max(1,int(y2*h))),max(0,int(x1*w)):min(w,max(1,int(x2*w)))]
    gray=cv2.cvtColor(region,cv2.COLOR_BGR2GRAY)
    # Connected text components estimate character height, not the entire paragraph box.
    mask=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
    count,labels,stats,centroids=cv2.connectedComponentsWithStats(mask)
    heights=[int(s[cv2.CC_STAT_HEIGHT]) for s in stats[1:] if s[cv2.CC_STAT_AREA]>=3 and s[cv2.CC_STAT_HEIGHT]<region.shape[0]*0.95]
    return {'contrast_metric':float(np.std(gray)), 'text_height_px':float(np.median(heights)) if heights else None}
