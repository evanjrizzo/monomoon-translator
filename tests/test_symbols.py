from pathlib import Path
import sys
import json
import cv2
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ocr import Profile,Matcher,recognize,annotate,auto_recognize,TEACHING_SYMBOLS


def symbols_profile(symbols='AB0123456789.,:;!?=\"'):
    p=Profile('Letters, numbers & punctuation')
    for symbol in symbols:
        canvas=np.zeros((45,40),np.uint8)
        cv2.putText(canvas,symbol,(5,32),cv2.FONT_HERSHEY_SIMPLEX,1,255,2)
        p.add(symbol,canvas)
    return p


def test_all_teaching_characters_roundtrip_and_old_profile(tmp_path):
    p=Profile()
    for symbol in TEACHING_SYMBOLS:
        p.add(symbol,np.full((3,4),255,np.uint8))
    path=tmp_path/'symbols.json';p.save(path);q=Profile.load(path)
    assert json.loads(path.read_text())['version']==2
    assert set(q.samples)==set(TEACHING_SYMBOLS)
    assert len(Profile.load(Path(__file__).resolve().parents[1]/'examples/starter-alphabet.json').samples)==26
    for invalid in ('','12','a',' ','\n','\x00','A\u0301'):
        with pytest.raises(ValueError):p.add(invalid,np.ones((3,3),np.uint8))


def test_mixed_letters_numbers_punctuation_and_question_confidence(tmp_path):
    p=symbols_profile()
    path=tmp_path/'profile.json';p.save(path);p=Profile.load(path)
    text='A12,345.6!?'
    image=np.zeros((50,380),np.uint8)
    x=8
    for symbol in text:
        cv2.putText(image,symbol,(x,32),cv2.FONT_HERSHEY_SIMPLEX,1,255,2)
        x+=p.samples[symbol][0].shape[1]+5
    read,glyphs=recognize(image,p)
    assert read==text
    assert all(g.accepted for g in glyphs)
    question=glyphs[-1]
    assert question.letter=='?' and question.confidence>.99
    preview=annotate(image,glyphs)
    x,y,_,_=question.box
    assert tuple(preview[y,x])==(30,180,40)
    _,automatic,auto_glyphs,_=auto_recognize(image,p)
    assert automatic==text and all(g.accepted for g in auto_glyphs)


@pytest.mark.parametrize('symbol',list(':;!?=\"'))
def test_disconnected_standalone_punctuation(symbol):
    p=symbols_profile()
    text,glyphs=recognize(np.pad(p.samples[symbol][0],5),p)
    assert text==symbol
    assert len(glyphs)==1 and glyphs[0].accepted


def test_numbers_only_profile_and_single_template():
    p=symbols_profile('0123456789')
    for symbol in p.samples:
        assert recognize(np.pad(p.samples[symbol][0],5),p)[0]==symbol
    p=symbols_profile('7')
    assert recognize(np.pad(p.samples['7'][0],5),p)[0]=='7'
