"""Offline portable-runtime check; writes only beside the application."""
import json
import sys
import tempfile
from pathlib import Path
from paths import resource,data_folder

def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage,QColor
    from app import Window
    from ocr import Profile,read_image,auto_recognize,recognize
    import cv2
    import numpy as np
    app=QApplication.instance() or QApplication([])
    w=Window();w.show();app.processEvents()
    assert w.windowTitle()=='Monomoon Translator'
    assert not w.advanced_panel.isVisible()
    w.advanced_toggle.setChecked(True);app.processEvents()
    assert w.advanced_panel.isVisible()
    w.advanced_toggle.setChecked(False)
    image=QImage(7,5,QImage.Format.Format_RGBA8888);image.fill(QColor(255,0,0));app.clipboard().setImage(image)
    w.paste_image();assert w.image.shape==(5,7,3) and np.array_equal(w.image[2,2],[0,0,255])
    clipboard_ok=True
    with tempfile.TemporaryDirectory(dir=data_folder('checks'),prefix='alphabet-') as folder:
        path=Path(folder)/'alphabet-é.json';w.profile.save(path)
        assert len(Profile.load(path).samples)==26
        starter=w.profile;w.profile=Profile('Numbers and punctuation')
        w.polarity.setCurrentText('dark');w.threshold.setValue(127);w.area.setValue(0)
        for group,symbol in ((1,'7'),(2,'?'),(2,':'),(2,'=')):
            w.symbol_group.setCurrentIndex(group);w.letter.setCurrentText(symbol)
            mask=np.zeros((45,40),np.uint8)
            cv2.putText(mask,symbol,(5,32),cv2.FONT_HERSHEY_SIMPLEX,1,255,2)
            w.add_sample(cv2.cvtColor(255-mask,cv2.COLOR_GRAY2BGR))
        w.profile.save(path);expanded=Profile.load(path)
        assert json.loads(path.read_text())['version']==2
        for symbol,values in expanded.samples.items():
            text,glyphs=recognize(np.pad(values[0],5),expanded)
            assert text==symbol and len(glyphs)==1 and glyphs[0].accepted
        assert set(expanded.samples)=={'7','?',':','='}
        w.profile=starter;w.dirty=False;w.refresh_profile()
    results={}
    expected={'relics-sign-from-app.png':'RELICSARE\nNOTENOUGH','hypnosis-board-from-app.png':'HYPNOSISTECHNIQUES','moon-board.jpg':'CANCROSSINTOACTIVEFRAME'}
    for name,required in expected.items():
        im=read_image(resource('examples',name))
        _,text,glyphs,_=auto_recognize(im,w.profile)
        assert required in text,(name,text)
        results[name]={'text':text,'glyphs':len(glyphs)}
    report={'success':True,'version':resource('VERSION').read_text().strip(),'platform':sys.platform,'clipboard':clipboard_ok,'profiles':True,'symbols':True,'profile_format':2,'advanced_panel':True,'ocr':results}
    (data_folder('logs')/'portable-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    w.grab().save(str(data_folder('logs')/'portable-preview.png'))
    w.close();print(json.dumps(report,indent=2))
    return 0
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception:
        import traceback
        details=traceback.format_exc()
        (data_folder('logs')/'portable-check-failure.txt').write_text(details,encoding='utf-8')
        print(details,file=sys.stderr);raise SystemExit(1)
