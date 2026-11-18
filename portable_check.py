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
    from ocr import Profile,read_image,auto_recognize
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
    results={}
    expected={'relics-sign-from-app.png':'RELICSARE\nNOTENOUGH','hypnosis-board-from-app.png':'HYPNOSISTECHNIQUES','moon-board.jpg':'CANCROSSINTOACTIVEFRAME'}
    for name,required in expected.items():
        im=read_image(resource('examples',name))
        _,text,glyphs,_=auto_recognize(im,w.profile)
        assert required in text,(name,text)
        results[name]={'text':text,'glyphs':len(glyphs)}
    report={'success':True,'platform':sys.platform,'clipboard':clipboard_ok,'profiles':True,'advanced_panel':True,'ocr':results}
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
