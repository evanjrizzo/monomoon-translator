"""Local, template-based OCR. White pixels are foreground throughout."""
from dataclasses import dataclass
from pathlib import Path
import json
import string
import unicodedata
import cv2
import numpy as np

TEACHING_SYMBOLS = string.ascii_uppercase + string.digits + string.punctuation + '…‘’“”–'


def valid_symbol(symbol):
    return (isinstance(symbol, str) and len(symbol) == 1 and
            (symbol in string.ascii_uppercase + string.digits or
             unicodedata.category(symbol).startswith(('P', 'S'))))


def read_image(path):
    data = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if data is None:
        raise ValueError('Cannot read this image.')
    return data


def preprocess(image, threshold=-1, polarity='dark', scale=1.0, min_area=2, range_low=0, range_high=255, local_window=7):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    if gray.size * scale * scale > 40_000_000:
        raise ValueError('Scaled image exceeds 40 megapixels. Crop it or reduce scale.')
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    mode = cv2.THRESH_BINARY_INV if polarity == 'dark' else cv2.THRESH_BINARY
    if polarity in ('local light','local dark'):
        size=max(3,int(local_window)|1)
        operation=cv2.MORPH_TOPHAT if polarity=='local light' else cv2.MORPH_BLACKHAT
        contrast=cv2.morphologyEx(gray,operation,np.ones((size,size),np.uint8))
        _,mask=cv2.threshold(contrast,max(0,threshold),255,cv2.THRESH_BINARY | (cv2.THRESH_OTSU if threshold<0 else 0))
    elif polarity == 'range':
        if range_low > range_high:
            raise ValueError('Range minimum must not exceed maximum.')
        mask = cv2.inRange(gray, range_low, range_high)
    else:
        _, mask = cv2.threshold(gray, max(0, threshold), 255, mode | (cv2.THRESH_OTSU if threshold < 0 else 0))
    if min_area > 1:
        n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        keep = np.zeros(n, np.uint8)
        keep[1:] = (stats[1:, cv2.CC_STAT_AREA] >= min_area) * 255
        mask = keep[labels]
    return mask


def tight(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError('No foreground in selection. Adjust threshold or polarity.')
    return mask[ys.min():ys.max()+1, xs.min():xs.max()+1]


def normalize(mask):
    mask = tight(mask)
    h, w = mask.shape
    ratio = min(40 / w, 40 / h)
    resized = cv2.resize(mask, (max(1, round(w*ratio)), max(1, round(h*ratio))), interpolation=cv2.INTER_NEAREST)
    out = np.zeros((48, 48), np.uint8)
    y, x = (48-resized.shape[0])//2, (48-resized.shape[1])//2
    out[y:y+resized.shape[0], x:x+resized.shape[1]] = resized
    return out


class Profile:
    def __init__(self, name='Untitled alphabet'):
        self.name = name
        self.samples = {}

    def add(self, letter, mask):
        if not valid_symbol(letter):
            raise ValueError('Choose one uppercase letter A–Z, digit 0–9, or punctuation/symbol character. Spaces and multi-character labels are not supported.')
        sample=tight(mask).copy()
        self.samples.setdefault(letter, []).append(sample)

    def save(self, path):
        version = 2 if any(k not in string.ascii_uppercase for k in self.samples) else 1
        data = {'version': version, 'name': self.name, 'samples': {k: [(m > 0).astype(int).tolist() for m in v] for k, v in self.samples.items()}}
        path = Path(path)
        temp = path.with_name(path.name + '.tmp')
        temp.write_text(json.dumps(data), encoding='utf-8')
        temp.replace(path)

    @classmethod
    def load(cls, path):
        if Path(path).stat().st_size > 20_000_000:
            raise ValueError('Profile is too large.')
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if data.get('version') not in (1, 2):
            raise ValueError('Unsupported profile version.')
        obj = cls(str(data.get('name', 'Alphabet')))
        for letter, samples in data['samples'].items():
            if len(samples) > 200:
                raise ValueError('Too many samples.')
            for sample in samples:
                m = np.asarray(sample)
                if m.ndim != 2 or not m.size or max(m.shape) > 2048 or not np.isin(m, [0, 1]).all():
                    raise ValueError('Invalid sample bitmap.')
                obj.add(letter, m.astype(np.uint8)*255)
        return obj


class Matcher:
    def __init__(self, profile):
        self.templates = [(k, normalize(m)>0, m.shape[1]/m.shape[0]) for k, values in profile.samples.items() for m in values]
        if not self.templates:
            raise ValueError('Teach at least one character or load a profile first.')

    def match(self, mask):
        raw = tight(mask)
        a = normalize(raw)>0
        aspect = raw.shape[1]/raw.shape[0]
        scores = {}
        for letter, b, ratio in self.templates:
            best = 0
            for dy, dx in ((0,0),(-1,0),(1,0),(0,-1),(0,1)):
                shifted = np.roll(b, (dy, dx), (0,1))
                dice = 2*np.count_nonzero(a & shifted)/(np.count_nonzero(a)+np.count_nonzero(shifted))
                best = max(best, dice)
            score = best * np.exp(-0.18*abs(np.log(aspect/ratio)))
            scores[letter] = max(scores.get(letter, 0), float(score))
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return ranked[:3]


def runs(values):
    edges = np.diff(np.r_[False, np.asarray(values, bool), False].astype(int))
    return list(zip(np.where(edges==1)[0], np.where(edges==-1)[0]))


def join_punctuation_parts(mask, bands, matcher, axis):
    """Reunite disconnected dots/strokes only for a strong taught symbol match.

    This handles standalone : ; ! ? = and quotation marks without increasing
    the general gap settings, which could otherwise merge whole text lines.
    """
    if not any(not k.isalnum() for k,_,_ in matcher.templates):
        return bands
    result=[]
    index=0
    while index<len(bands):
        start,end=bands[index]
        if index+1<len(bands):
            other_start,other_end=bands[index+1]
            first=mask[start:end] if axis==0 else mask[:,start:end]
            second=mask[other_start:other_end] if axis==0 else mask[:,other_start:other_end]
            crop=mask[start:other_end] if axis==0 else mask[:,start:other_end]
            # Separate text lines have independent horizontal spans. Only try
            # a vertical merge when both bands contain a single aligned mark.
            aligned=axis==1 or (len(runs(np.any(first,axis=0)))==1 and len(runs(np.any(second,axis=0)))==1)
            close=other_start-end<=max(first.shape+second.shape)*.75
            if aligned and close:
                ranked=matcher.match(crop)
                symbol,score=ranked[0]
                margin=score-ranked[1][1] if len(ranked)>1 else score
                if not symbol.isalnum() and score>=.94 and margin>=.04:
                    result.append((start,other_end));index+=2;continue
        result.append((start,end));index+=1
    return result


@dataclass
class Glyph:
    box: tuple
    letter: str
    confidence: float
    alternatives: list
    line: int
    space: bool = False
    accepted: bool = True


def split_touching(crop, matcher, expected):
    """Conservative recursive projection-valley split, accepted by match quality."""
    h, w = crop.shape
    base = matcher.match(crop)[0][1]
    if w < expected*1.45 or w < 8:
        return [(0,w)]
    ink = np.count_nonzero(crop, axis=0)
    lo, hi = max(2, int(expected*.45)), min(w-2, int(expected*1.45))
    candidates = sorted(range(lo, hi), key=lambda x: ink[x])[:12]
    best = None
    for cut in candidates:
        try:
            left = matcher.match(crop[:, :cut])[0][1]
            right = matcher.match(crop[:, cut:])[0][1]
        except ValueError:
            continue
        quality = (left+right)/2 - .08*ink[cut]/max(1,h)
        if quality > base+.045 and min(left,right) > .40 and (best is None or quality > best[0]):
            best = (quality, cut)
    if best:
        c = best[1]
        return split_touching(crop[:,:c],matcher,expected) + [(a+c,b+c) for a,b in split_touching(crop[:,c:],matcher,expected)]
    return [(0,w)]


def recognize(mask, profile, minimum=.58, split=True, gap_factor=.65, line_gap=2, char_gap=0):
    matcher = Matcher(profile)
    occupied = (np.count_nonzero(mask,axis=1)>0).astype(np.uint8)[:,None]
    if line_gap:
        occupied = cv2.morphologyEx(occupied, cv2.MORPH_CLOSE, np.ones((line_gap+1,1),np.uint8))
    line_runs = join_punctuation_parts(mask,runs(occupied.ravel()),matcher,0)
    glyphs = []
    texts = []
    for line_id,(y0,y1) in enumerate(line_runs):
        strip = mask[y0:y1]
        columns = (np.count_nonzero(strip,axis=0)>0).astype(np.uint8)[None,:]
        if char_gap:
            columns = cv2.morphologyEx(columns,cv2.MORPH_CLOSE,np.ones((1,char_gap+1),np.uint8))
        chunks = join_punctuation_parts(strip,runs(columns.ravel()),matcher,1)
        if not chunks:
            continue
        # Punctuation can be much shorter or wider than letters. Use letters
        # and digits to estimate normal spacing whenever they are available.
        ratios = [r for k,_,r in matcher.templates if k.isalnum()] or [r for _,_,r in matcher.templates]
        expected = float(np.median(ratios))*(y1-y0)
        boxes = []
        for x0,x1 in chunks:
            parts = split_touching(strip[:,x0:x1],matcher,expected) if split else [(0,x1-x0)]
            boxes.extend((x0+a,x0+b) for a,b in parts)
        prev = None
        text = ''
        for x0,x1 in boxes:
            crop = strip[:,x0:x1]
            ys,xs = np.nonzero(crop)
            if not len(xs):
                continue
            ranked = matcher.match(crop)
            letter, score = ranked[0]
            # Close alternatives indicate ambiguity, even when similarity is high.
            margin = score-ranked[1][1] if len(ranked)>1 else score
            accepted = score >= minimum and margin >= .025
            decoded = letter if accepted else '?'
            space = prev is not None and x0-prev > expected*gap_factor
            text += (' ' if space else '') + decoded
            glyphs.append(Glyph((int(x0+xs.min()),int(y0+ys.min()),int(xs.max()-xs.min()+1),int(ys.max()-ys.min()+1)),decoded,score,ranked,line_id,space,accepted))
            prev=x1
        texts.append(text)
    return '\n'.join(texts), glyphs


def annotate(image, glyphs):
    out = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim==2 else image.copy()
    for g in glyphs:
        x,y,w,h=g.box
        color=(30,180,40) if g.accepted else (0,130,255)
        cv2.rectangle(out,(x,y),(x+w,y+h),color,1)
        label=g.letter if g.letter.isascii() else f'U+{ord(g.letter):04X}'
        cv2.putText(out,label,(x,max(10,y-3)),cv2.FONT_HERSHEY_SIMPLEX,.4,color,1,cv2.LINE_AA)
    return out


def auto_recognize(image, profile, minimum=.58, detect_regions=True):
    """Choose a foreground intensity using the taught shapes as evidence.

    Uses flat colors and local contrast to handle uneven lighting. Rows with several
    consistent matches are retained, to avoid decoding scenery as text.
    """
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY) if image.ndim==3 else image
    if gray.size>2_000_000:
        if detect_regions:return recognize_regions(image,profile,minimum)
        raise ValueError('Select a text region smaller than 2 megapixels for a single reading pass.')
    Matcher(profile)  # Give a useful error for empty alphabets before searching.
    has_punctuation = any(not k.isalnum() for k in profile.samples)
    min_area = 1 if any(not k.isalnum() and np.count_nonzero(m)<2 for k,values in profile.samples.items() for m in values) else 2
    histogram=np.bincount(gray.ravel(),minlength=256)
    palette=np.argsort(histogram)[::-1][:16]
    best=None
    def consider(mask,settings):
        nonlocal best
        fraction=np.count_nonzero(mask)/mask.size
        if not .001<fraction<.35:return
        n,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
        keep=np.zeros(n,np.uint8)
        for i in range(1,n):
            x,y,w,h,area=stats[i]
            if area>=min_area and h<=max(40,gray.shape[0]*.35) and w<=max(50,gray.shape[1]*.35):keep[i]=255
        mask=keep[labels]
        _,glyphs=recognize(mask,profile,minimum=minimum,split=True,line_gap=2,char_gap=0)
        selected=[]
        for line in sorted(set(g.line for g in glyphs)):
            row=[g for g in glyphs if g.line==line]
            # Reject isolated specks and narrow frame edges against the size
            # of the letters in this row. Keep short wide glyphs such as O.
            median_h=float(np.median([g.box[3] for g in row]))
            median_w=float(np.median([g.box[2] for g in row]))
            row=[g for g in row if g.box[2]>=max(2,median_w*.3) or median_h*.5<=g.box[3]<=median_h*1.6 or (has_punctuation and g.accepted and not g.letter.isalnum())]
            if not row:continue
            accepted=[g for g in row if g.accepted]
            if len(set(g.letter for g in accepted))>=2 and len(row)>=3 and len(accepted)/len(row)>=.7 and np.mean([g.confidence for g in row])>=.70:
                selected.extend(row)
        if not selected:return
        quality=sum(g.confidence if g.accepted else -.5 for g in selected)
        if best is None or quality>best[0]:best=(quality,mask,selected,settings)
    for value in palette:
        if histogram[value]<6:continue
        low=high=int(value)
        mask=preprocess(image,polarity='range',range_low=low,range_high=high,min_area=min_area)
        consider(mask,dict(polarity='range',range_low=low,range_high=high,min_area=min_area))
    # Remove smooth lighting gradients before thresholding. Several windows
    # cover both tiny display glyphs and larger original screenshot strokes.
    for polarity in ('local light','local dark'):
        for window in (3,7,15):
            for threshold in (10,20,30):
                settings=dict(polarity=polarity,local_window=window,threshold=threshold,min_area=min_area)
                consider(preprocess(image,**settings),settings)
    if best is None:
        if detect_regions:return recognize_regions(image,profile,minimum)
        raise ValueError('Could not confidently find text. Select just the lettering and try Auto-read again, or adjust the foreground controls.')
    _,mask,glyphs,settings=best
    lines=[]
    for line in sorted(set(g.line for g in glyphs)):
        lines.append(''.join((' ' if g.space else '')+g.letter for g in glyphs if g.line==line).strip())
    return mask,'\n'.join(lines),glyphs,settings


def detect_text_regions(image,profile):
    """Propose aligned text rows from glyph-shaped connected components."""
    height,width=image.shape[:2]
    factor=1
    while height*width/(factor*factor)>1_000_000:factor*=2
    small=cv2.resize(image,(max(1,width//factor),max(1,height//factor)),interpolation=cv2.INTER_AREA)
    matcher=Matcher(profile)
    seeds=[]
    for window,threshold in ((7,12),(7,25),(15,20)):
        mask=preprocess(small,polarity='local light',local_window=window,threshold=threshold,min_area=4)
        _,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
        for x,y,w,h,area in stats[1:]:
            if not (5<=h<=80 and 4<=w<=100 and area>=10 and area/(h*w)<.85 and .25<w/h<4):continue
            ranked=matcher.match(mask[y:y+h,x:x+w])
            if ranked[0][1]<.65 or (len(ranked)>1 and ranked[0][1]-ranked[1][1]<.04):continue
            item=(int(x),int(y),int(w),int(h),ranked[0][0],ranked[0][1])
            duplicate=next((i for i,a in enumerate(seeds) if abs(a[0]+a[2]/2-x-w/2)<max(2,w*.25) and abs(a[1]+a[3]/2-y-h/2)<max(2,h*.25)),None)
            if duplicate is None:seeds.append(item)
            elif item[5]>seeds[duplicate][5]:seeds[duplicate]=item
    rows=[]
    for seed in sorted(seeds,key=lambda a:a[1]+a[3]/2):
        cy=seed[1]+seed[3]/2
        possible=[r for r in rows if abs(np.median([a[1]+a[3]/2 for a in r])-cy)<max(2,min(seed[3],np.median([a[3] for a in r]))*.45)]
        if possible:min(possible,key=lambda r:abs(np.median([a[1]+a[3]/2 for a in r])-cy)).append(seed)
        else:rows.append([seed])
    proposals=[]
    for row in rows:
        row.sort(key=lambda a:a[0]);median_w=float(np.median([a[2] for a in row]));groups=[]
        for seed in row:
            if groups and seed[0]-groups[-1][-1][0]-groups[-1][-1][2]<median_w*3:groups[-1].append(seed)
            else:groups.append([seed])
        for group in groups:
            if len(group)<3 or len(set(a[4] for a in group))<2:continue
            x=min(a[0] for a in group);y=min(a[1] for a in group)
            x1=max(a[0]+a[2] for a in group);y1=max(a[1]+a[3] for a in group)
            pad=max(2,round(np.median([a[3] for a in group])*.3))
            proposals.append([max(0,x-pad),max(0,y-2),min(small.shape[1],x1+pad),min(small.shape[0],y1+2)])
    # Share column boundaries between neighboring rows. This recovers short
    # letters and low-contrast prefixes that did not qualify as initial seeds.
    columns=[]
    for i,box in enumerate(proposals):
        group={i}
        for j,other in enumerate(proposals):
            overlap=max(0,min(box[2],other[2])-max(box[0],other[0]))
            if overlap>=min(box[2]-box[0],other[2]-other[0])*.5 and abs((box[1]+box[3]-other[1]-other[3])/2)<max(box[3]-box[1],other[3]-other[1])*3:
                group.add(j)
        touching=[c for c in columns if c & group]
        for c in touching:group.update(c);columns.remove(c)
        columns.append(group)
    result=[]
    for column in sorted(columns,key=lambda ids:min(proposals[i][0] for i in ids)):
        left=min(proposals[i][0] for i in column);right=max(proposals[i][2] for i in column)
        for i in sorted(column,key=lambda i:proposals[i][1]):
            _,top,_,bottom=proposals[i]
            expanded=(left*factor,top*factor,min(width,right*factor),min(height,bottom*factor))
            result.append(expanded)
            original=tuple(v*factor for v in proposals[i])
            if original!=expanded:result.append(original)
    return result


def recognize_regions(image,profile,minimum=.58):
    regions=detect_text_regions(image,profile)
    readings=[]
    for x0,y0,x1,y1 in regions[:40]:
        try:mask,text,glyphs,settings=auto_recognize(image[y0:y1,x0:x1],profile,minimum=minimum,detect_regions=False)
        except ValueError:continue
        if not text:continue
        for g in glyphs:
            x,y,w,h=g.box;g.box=(x+x0,y+y0,w,h)
        bounds=(min(g.box[0] for g in glyphs),min(g.box[1] for g in glyphs),max(g.box[0]+g.box[2] for g in glyphs),max(g.box[1]+g.box[3] for g in glyphs))
        duplicate=False
        for previous in readings:
            a,b,c,d=previous[0];x,y,u,v=bounds
            intersection=max(0,min(c,u)-max(a,x))*max(0,min(d,v)-max(b,y))
            if intersection>.5*min((c-a)*(d-b),(u-x)*(v-y)):
                duplicate=True;break
        if not duplicate:readings.append((bounds,text,glyphs,settings,(x0,y0,x1,y1),mask))
    if not readings:
        raise ValueError('Could not find reliable text blocks. Select a tighter text region and try Read screenshot again.')
    # Preserve column order, with side-by-side labels ordered left to right.
    for i in range(1,len(readings)):
        j=i
        while j>0:
            a=readings[j-1][0];b=readings[j][0]
            if abs((a[1]+a[3]-b[1]-b[3])/2)<max(a[3]-a[1],b[3]-b[1])*.5 and a[0]>b[0]:
                readings[j-1],readings[j]=readings[j],readings[j-1];j-=1
            else:break
    all_glyphs=[];texts=[];combined=np.zeros(image.shape[:2],np.uint8)
    for _,text,glyphs,settings,(x0,y0,x1,y1),mask in readings:
        for g in glyphs:g.line+=len(texts)
        texts.extend(text.splitlines());all_glyphs.extend(glyphs)
        combined[y0:y1,x0:x1]=np.maximum(combined[y0:y1,x0:x1],mask)
    settings=dict(readings[-1][3],detected_regions=len(texts))
    return combined,'\n'.join(texts),all_glyphs,settings
