import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from app import Window


def test_demo_worker_and_selection():
    app=QApplication.instance() or QApplication([])
    window=Window();window.show()
    # A previously changed segmentation setting must not break the demo.
    window.char_gap.setValue(7)
    window.line_gap.setValue(20)
    window.scale.setValue(2)
    window.minimum.setValue(.99)
    window.space.setValue(3)
    window.touching.setChecked(False)
    window.demo();app.processEvents()
    assert window.char_gap.value()==0
    assert window.line_gap.value()==2
    assert window.scale.value()==1
    assert window.minimum.value()==.58
    assert window.space.value()==.65
    assert window.touching.isChecked()
    # Selection must map from a scaled viewport back into original image coordinates.
    v=window.source
    a=v.mapFromScene(200,200);b=v.mapFromScene(300,300)
    QTest.mousePress(v.viewport(),Qt.MouseButton.LeftButton,pos=a)
    QTest.mouseMove(v.viewport(),b)
    QTest.mouseRelease(v.viewport(),Qt.MouseButton.LeftButton,pos=b)
    app.processEvents()
    assert window.selection is not None
    assert abs(window.selection[0]-200)<=2
    assert abs(window.selection[2]-100)<=3
    window.selection=None
    window.decode()
    end=time.monotonic()+20
    while window.thread is not None and time.monotonic()<end:
        app.processEvents();time.sleep(.005)
    assert window.thread is None
    assert window.text.toPlainText().startswith('NUMBERSHIDDENONFRAILWALLS\nUNLOCK')
    assert window.table.rowCount()==105
    window.text.setPlainText('Edited output')
    assert window.text.toPlainText()=='Edited output'
    window.close()


def test_paste_image_shortcut_and_text_paste():
    from PySide6.QtGui import QImage,QColor
    import numpy as np
    app=QApplication.instance() or QApplication([])
    w=Window();w.show();w.activateWindow();app.processEvents()
    image=QImage(7,5,QImage.Format.Format_RGBA8888)
    image.fill(QColor(255,0,0))
    image.setPixelColor(0,0,QColor(0,0,0,0))
    app.clipboard().setImage(image)
    w.roi=(1,1,2,2);w.selection=(1,1,2,2)
    w.source.setFocus();app.processEvents()
    QTest.keyClick(w.source,Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert w.image is not None
    assert w.image.shape==(5,7,3)
    assert np.array_equal(w.image[2,2],[0,0,255])
    assert np.array_equal(w.image[0,0],[255,255,255])
    assert w.roi is None and w.selection is None
    # The NumPy source owns its pixels after the clipboard has changed.
    app.clipboard().setText('hello')
    assert np.array_equal(w.image[2,2],[0,0,255])
    w.text.setFocus();app.processEvents()
    QTest.keyClick(w.text,Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert w.text.toPlainText()=='hello'
    w.text.document().setModified(False)
    w.close()


def test_paste_rejects_nonimage_and_accepts_local_file():
    from PySide6.QtCore import QMimeData,QUrl
    import numpy as np
    app=QApplication.instance() or QApplication([])
    w=Window();errors=[];w.error=errors.append
    w.set_source_image(np.zeros((5,5,3),np.uint8),'Original')
    original=w.image.copy()
    app.clipboard().setText('not an image')
    w.paste_image()
    assert errors and np.array_equal(w.image,original)
    mime=QMimeData()
    path=Path(__file__).resolve().parents[1]/'examples/inscription.png'
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    app.clipboard().setMimeData(mime)
    w.paste_image()
    assert w.image.shape[:2]==(848,727)
    app.clipboard().clear();w.close()


def test_startup_alphabet_auto_read_and_selected_region():
    import numpy as np
    from ocr import read_image,Profile
    app=QApplication.instance() or QApplication([])
    w=Window();w.show();app.processEvents()
    assert len(w.profile.samples)==26
    sign=read_image(Path(__file__).resolve().parents[1]/'examples/relics-sign-from-app.png')
    w.set_source_image(sign,'New screenshot')
    w.profile=Profile()
    w.use_starter_profile()
    assert np.array_equal(w.image,sign)
    w.selection=(40,35,205,75)
    w.decode(automatic=True)
    end=time.monotonic()+20
    while w.thread is not None and time.monotonic()<end:
        app.processEvents();time.sleep(.005)
    assert w.thread is None
    assert w.roi==w.selection
    assert w.text.toPlainText()=='RELICSARE\nNOTENOUGH'
    assert w.polarity.currentText() in ('range','local light','local dark')
    w.close()


def test_main_read_button_uses_selection_and_automatic_lighting():
    from ocr import read_image
    app=QApplication.instance() or QApplication([])
    w=Window();w.show();app.processEvents()
    w.load_image(Path(__file__).resolve().parents[1]/'examples/hypnosis-board-from-app.png')
    w.selection=(55,18,195,26)
    w.polarity.setCurrentText('dark')
    QTest.mouseClick(w.decode_button,Qt.MouseButton.LeftButton)
    end=time.monotonic()+20
    while w.thread is not None and time.monotonic()<end:
        app.processEvents();time.sleep(.005)
    assert w.thread is None
    assert w.roi==(55,18,195,26)
    assert w.text.toPlainText()=='HYPNOSISTECHNIQUES'
    assert w.polarity.currentText()=='local light'
    w.close()


def test_full_jpeg_worker_no_region_required():
    app=QApplication.instance() or QApplication([])
    w=Window();w.show();app.processEvents()
    w.load_image(Path(__file__).resolve().parents[1]/'examples/moon-board.jpg')
    errors=[];w.error=errors.append
    assert w.roi is None
    w.decode()
    end=time.monotonic()+45
    while w.thread is not None and time.monotonic()<end:
        app.processEvents();time.sleep(.005)
    assert w.thread is None and not errors
    assert 'MAYLINGERINPASTFRAME' in w.text.toPlainText()
    assert w.last_region_count>=5
    w.close()


def test_simple_interface_and_advanced_tooltips():
    from PySide6.QtWidgets import QPushButton
    app=QApplication.instance() or QApplication([])
    w=Window();w.show();app.processEvents()
    assert w.windowTitle()=='Monomoon Translator'
    assert not w.advanced_panel.isVisible()
    assert not w.threshold.isVisible() and not w.table.isVisible()
    assert w.auto_button.isVisible() and not w.auto_button.isEnabled()
    assert all(button.toolTip().strip() for button in w.findChildren(QPushButton))
    QTest.mouseClick(w.advanced_toggle,Qt.MouseButton.LeftButton);app.processEvents()
    assert w.advanced_panel.isVisible() and w.letter.isVisible()
    w.advanced_tabs.setCurrentIndex(1);app.processEvents()
    assert w.threshold.isVisible()
    QTest.mouseClick(w.advanced_toggle,Qt.MouseButton.LeftButton);app.processEvents()
    assert not w.advanced_panel.isVisible()
    w.close()


def test_teach_numbers_punctuation_save_load_and_validation(tmp_path,monkeypatch):
    import numpy as np
    from PySide6.QtWidgets import QFileDialog
    from ocr import Profile,Matcher
    app=QApplication.instance() or QApplication([])
    w=Window();w.show();w.advanced_toggle.setChecked(True);app.processEvents()
    assert w.advanced_tabs.tabText(0)=='Alphabet teaching'
    w.profile=Profile('Public profile');errors=[];w.error=errors.append
    image=np.full((15,15,3),255,np.uint8);image[3:12,5:9]=0
    w.set_source_image(image,'Test glyph');w.selection=(1,1,13,13)
    w.symbol_group.setCurrentIndex(1);w.letter.setCurrentText('7');w.teach()
    assert '7' in w.profile.samples
    w.symbol_group.setCurrentIndex(2);w.letter.setCurrentText('?');w.teach()
    assert '?' in w.profile.samples and not errors
    path=tmp_path/'symbols.json'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *args,**kwargs:(str(path),'Alphabet (*.json)'))
    assert w.save_profile()
    w.profile=Profile();monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args,**kwargs:(str(path),'Alphabet (*.json)'))
    w.load_profile();assert set(w.profile.samples)=={'7','?'}
    w.letter.setCurrentText('two');w.teach();assert errors and set(w.profile.samples)=={'7','?'}
    w.letter.setCurrentText('?');w.remove_sample();assert '?' not in w.profile.samples
    w.dirty=False;w.close()
