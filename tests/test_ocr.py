from pathlib import Path
import sys
import numpy as np
import cv2
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ocr import *
BASE=Path(__file__).resolve().parents[1]

def fixture():
    p=Profile('test')
    for letter in 'ABC':
        mask=np.zeros((40,35),np.uint8)
        cv2.putText(mask,letter,(2,32),cv2.FONT_HERSHEY_SIMPLEX,1,255,2)
        p.add(letter,mask)
    return p

def render(p,lines):
    out=np.zeros((len(lines)*55,400),np.uint8)
    for i,line in enumerate(lines):
        x=5
        for letter in line:
            if letter==' ':x+=30;continue
            m=p.samples[letter][0];h,w=m.shape
            out[i*55+5:i*55+5+h,x:x+w]=m;x+=w+7
    return out

def test_multiline_spaces_and_matching():
    p=fixture();text,gs=recognize(render(p,['ABC AB','CBA']),p)
    assert text=='ABC AB\nCBA'
    assert len(gs)==8
    assert all(g.confidence>.99 for g in gs)

def test_roundtrip(tmp_path):
    p=fixture();p.add('A',p.samples['A'][0]);p.save(tmp_path/'p.json')
    q=Profile.load(tmp_path/'p.json')
    assert q.name=='test' and len(q.samples['A'])==2
    assert recognize(render(p,['ABC']),q)[0]=='ABC'

def test_polarity_and_scale():
    p=fixture();mask=render(p,['BAC'])
    assert recognize(preprocess(255-mask,threshold=127,scale=2),p)[0]=='BAC'
    assert recognize(preprocess(mask,threshold=127,polarity='light'),p)[0]=='BAC'

def test_blank_and_missing_profile():
    p=fixture()
    assert recognize(np.zeros((20,30),np.uint8),p)[0]==''
    with pytest.raises(ValueError):p.add('A',np.zeros((4,4),np.uint8))
    with pytest.raises(ValueError):recognize(np.ones((4,4),np.uint8),Profile())

def test_invalid_profile(tmp_path):
    path=tmp_path/'bad.json';path.write_text('{"version":2}')
    with pytest.raises(ValueError):Profile.load(path)

def test_unknown_ambiguity():
    p=fixture();p.add('Z',p.samples['A'][0])
    assert recognize(render(p,['A']),p)[0]=='?'

def test_touching_split():
    p=fixture();a=p.samples['A'][0];b=p.samples['B'][0]
    mask=np.zeros((max(len(a),len(b)),a.shape[1]+b.shape[1]+1),np.uint8)
    mask[:len(a),:a.shape[1]]=a;mask[:len(b),a.shape[1]+1:]=b
    mask[-2,a.shape[1]-2:a.shape[1]+4]=255
    text,gs=recognize(mask,p,split=True)
    assert text=='AB'

def test_screenshot_key():
    p=Profile.load(BASE/'examples/starter-alphabet.json')
    assert set(p.samples)==set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
    for letter,samples in p.samples.items():assert Matcher(p).match(samples[0])[0][0]==letter
    key=read_image(BASE/'examples/alphabet-key.png')
    assert recognize(preprocess(key[72:112,45:840],threshold=35),p,gap_factor=3)[0]=='ABCDEFGHIJKLM'

def test_real_screenshot_pipeline():
    p=Profile.load(BASE/'examples/starter-alphabet.json')
    image=read_image(BASE/'examples/inscription.png')[610:825,:]
    mask=preprocess(image,polarity="range",range_low=31,range_high=31,min_area=8)
    text,gs=recognize(mask,p)
    assert text=="NUMBERSHIDDENONFRAILWALLS\nUNLOCKTHEDOORSALONGTHESEHALLS\nTHOSEWHOSEEKTHETRUTHBEYOND\nMUSTPASSTHETRIALOFTHEWAND"
    assert annotate(image,gs).shape==image.shape


def test_auto_read_both_real_screenshots():
    p=Profile.load(BASE/'examples/starter-alphabet.json')
    for name,expected in [('relics-sign-from-app.png','RELICSARE\nNOTENOUGH'),('inscription.png','NUMBERSHIDDENONFRAILWALLS\nUNLOCKTHEDOORSALONGTHESEHALLS\nTHOSEWHOSEEKTHETRUTHBEYOND\nMUSTPASSTHETRIALOFTHEWAND')]:
        mask,text,glyphs,band=auto_recognize(read_image(BASE/'examples'/name),p)
        assert text==expected
        assert all(g.letter!='?' for g in glyphs)
        assert band['polarity'] in ('range','local light','local dark')


def test_auto_read_blank_reports_failure():
    with pytest.raises(ValueError,match='Could not find reliable text blocks'):
        auto_recognize(np.zeros((20,20,3),np.uint8),fixture())


def test_auto_read_uneven_lighting_and_selection_border():
    p=Profile.load(BASE/'examples/starter-alphabet.json')
    image=read_image(BASE/'examples/hypnosis-board-from-app.png')
    for crop in [image,image[18:44,55:250]]:
        mask,text,glyphs,settings=auto_recognize(crop,p)
        assert text=='HYPNOSISTECHNIQUES'
        assert settings['polarity']=='local light'
        assert len(glyphs)==18


def test_full_jpeg_board_regions_and_original_coordinates():
    p=Profile.load(BASE/'examples/starter-alphabet.json')
    image=read_image(BASE/'examples/moon-board.jpg')
    assert image.shape[0]*image.shape[1]>2_000_000
    mask,text,glyphs,settings=auto_recognize(image,p)
    for line in ['RESTING','BOUNDBYFRAME','OFLINKEDSOUL','MAYLINGERINPASTFRAME','CANCROSSINTOACTIVEFRAME']:
        assert line in text.splitlines()
    assert 'LIT' in text and 'INFUSED' in text
    assert '?' in text  # The shaded small label must retain its uncertainty.
    assert settings['detected_regions']>=5
    assert mask.shape==image.shape[:2]
    assert all(1100<g.box[0]<2100 and 850<g.box[1]<1100 for g in glyphs)
    assert len(glyphs)<160  # Background dither must not become repeated Cs.
