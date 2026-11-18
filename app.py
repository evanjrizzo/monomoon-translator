#!/usr/bin/env python3
"""Monomoon Translator desktop interface."""
import sys
from pathlib import Path
import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal, QObject, QThread, QRectF
from PySide6.QtGui import QImage, QPixmap, QPen, QColor, QAction, QKeySequence, QPainter, QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QFormLayout,QScrollArea,QSplitter,QGraphicsView,QGraphicsScene,QFileDialog,QMessageBox,
    QPushButton,QComboBox,QSpinBox,QDoubleSpinBox,QCheckBox,QPlainTextEdit,QLabel,
    QTableWidget,QTableWidgetItem,QInputDialog,QAbstractItemView,QToolButton,QTabWidget)
from paths import resource, data_folder, profile_suggestion
from ocr import Profile, read_image, preprocess, recognize, annotate, auto_recognize, TEACHING_SYMBOLS


class ImageView(QGraphicsView):
    selected = Signal(tuple)
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.start = None
        self.selection = None
        self.setMinimumSize(250,200)
    def show_image(self, array):
        rgb=cv2.cvtColor(array, cv2.COLOR_GRAY2RGB if array.ndim==2 else cv2.COLOR_BGR2RGB)
        rgb=np.ascontiguousarray(rgb)
        image=QImage(rgb.data,rgb.shape[1],rgb.shape[0],rgb.strides[0],QImage.Format.Format_RGB888).copy()
        self.scene().clear()
        self.selection=None
        self.scene().addPixmap(QPixmap.fromImage(image))
        self.setSceneRect(0,0,rgb.shape[1],rgb.shape[0])
        self.fit()
    def fit(self):
        self.fitInView(self.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)
    def wheelEvent(self,event):
        factor=1.2 if event.angleDelta().y()>0 else 1/1.2
        if .03 < self.transform().m11()*factor < 50:
            self.scale(factor,factor)
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.start=self.mapToScene(event.position().toPoint())
            if self.selection:
                self.scene().removeItem(self.selection)
            self.selection=self.scene().addRect(QRectF(self.start,self.start),QPen(QColor('#00cfff'),1))
        else:
            super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.start is not None:
            self.selection.setRect(QRectF(self.start,self.mapToScene(event.position().toPoint())).normalized().intersected(self.sceneRect()))
        else:
            super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if self.start is not None and event.button()==Qt.MouseButton.LeftButton:
            r=self.selection.rect().toAlignedRect()
            self.start=None
            if r.width()>1 and r.height()>1:
                self.selected.emit((r.x(),r.y(),r.width(),r.height()))
        else:
            super().mouseReleaseEvent(event)


class Worker(QObject):
    done=Signal(object)
    failed=Signal(str)
    finished=Signal()
    def __init__(self, image, profile, options, settings, automatic=False):
        super().__init__()
        self.image,self.profile,self.options,self.settings=image,profile,options,settings
        self.automatic=automatic
    def run(self):
        try:
            if self.automatic:
                self.done.emit(auto_recognize(self.image,self.profile,minimum=self.settings['minimum']))
            else:
                mask=preprocess(self.image,**self.options)
                text,glyphs=recognize(mask,self.profile,**self.settings)
                self.done.emit((mask,text,glyphs))
        except Exception as e:
            self.failed.emit(str(e))
        finally:
            self.finished.emit()


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Monomoon Translator')
        self.setWindowIcon(QIcon(str(resource('assets','monomoon-translator.svg'))))
        self.resize(1200,820)
        self.image=None;self.roi=None;self.selection=None
        self.profile=Profile()
        try:self.profile=Profile.load(resource('examples','starter-alphabet.json'))
        except (OSError,ValueError,KeyError):pass
        self.dirty=False;self.thread=None;self.glyphs=[];self.result_image=None;self.last_region_count=0
        root=QWidget();self.setCentralWidget(root);layout=QVBoxLayout(root)
        def button(title,callback,hint):
            b=QPushButton(title);b.setToolTip(hint);b.clicked.connect(callback);return b
        bar=QHBoxLayout();layout.addLayout(bar)
        bar.addWidget(button('Open image',self.open_image,'Choose a screenshot or image file from your computer.'))
        bar.addWidget(button('Paste image',self.paste_image,'Paste an image from the clipboard. You can also click Source and press Ctrl+V.'))
        self.auto_button=button('Read screenshot',lambda:self.decode(automatic=not self.manual_settings.isChecked()),'Find and decode text with the loaded alphabet. If you drew a rectangle, only that area is read.')
        self.auto_button.setStyleSheet('font-weight:bold; padding:7px 14px;')
        self.decode_button=self.auto_button;self.auto_button.setEnabled(False);bar.addWidget(self.auto_button)
        bar.addWidget(button('Clear selection',self.reset_roi,'Clear the selected text area so the next read searches the whole image.'))
        bar.addWidget(button('Fit images',lambda:(self.source.fit(),self.preview_view.fit()),'Reset zoom and fit each image into its panel. Scroll over either image to zoom in or out.'))
        bar.addStretch()
        self.advanced_toggle=QToolButton();self.advanced_toggle.setText('Advanced');self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow);self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.setToolTip('Show or hide image settings, alphabet training, saved profiles, examples, and detailed match scores.')
        self.advanced_toggle.toggled.connect(self.toggle_advanced);bar.addWidget(self.advanced_toggle)
        self.region_label=QLabel('Paste or open a screenshot, then click Read screenshot. Drag around words to limit the search.')
        self.region_label.setWordWrap(True);layout.addWidget(self.region_label)
        split=QSplitter();layout.addWidget(split,1)
        self.advanced_panel=QWidget();advanced_layout=QVBoxLayout(self.advanced_panel);advanced_layout.setContentsMargins(0,0,0,0)
        self.advanced_tabs=QTabWidget();advanced_layout.addWidget(self.advanced_tabs)
        self.advanced_panel.setMinimumWidth(400);self.advanced_panel.setMaximumWidth(440);split.addWidget(self.advanced_panel)
        def advanced_tab(title):
            controls=QWidget();form=QFormLayout(controls)
            scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(controls)
            self.advanced_tabs.addTab(scroll,title)
            return form
        self.alphabet_form=advanced_tab('Alphabet teaching')
        self.image_form=advanced_tab('Image settings')
        self.matches_form=advanced_tab('Matches')
        about_form=advanced_tab('About')
        about=QPlainTextEdit();about.setReadOnly(True);about.setMinimumHeight(410)
        about.setPlainText('Monomoon Translator '+resource('VERSION').read_text().strip()+'\n\nUnofficial community tool for fictional-alphabet OCR. Not affiliated with or endorsed by the game developers.\n\nAI disclosure: developed with substantial assistance from OpenAI Codex for code, documentation, packaging, and automated tests. Recognition uses local OpenCV template matching, not an online AI service.\n\nImages, profiles, and decoded text stay on your computer. No telemetry, account, or API key is used. App data defaults to the data folder beside the app.\n\nThe included key contains A–Z only. Teach numbers and punctuation from a known key before reading them. Review uncertain results before sharing.\n\nApplication code: MIT license. Game images and third-party libraries keep their own rights and licenses.\n\nDownloads, instructions, and issue reports:\nhttps://github.com/evanjrizzo/monomoon-translator')
        about.setToolTip('Version, AI-use disclosure, privacy, licensing, and project information.');about_form.addRow(about)
        form=self.alphabet_form
        self.profile_label=QLabel();self.profile_label.setTextFormat(Qt.TextFormat.PlainText);self.profile_label.setWordWrap(True);form.addRow('Alphabet',self.profile_label)
        for title,callback,hint in [
            ('Load included demo',self.demo,'Open the included inscription with its trained alphabet and example settings. This replaces the source image.'),
            ('Use game alphabet',self.use_starter_profile,'Restore the included A–Z game alphabet while keeping the current source image.'),
            ('New alphabet',self.new_profile,'Start an empty alphabet to teach symbols for a different fictional writing system.'),
            ('Load alphabet',self.load_profile,'Open a saved alphabet JSON file. This changes the letter templates, not the screenshot.'),
            ('Save alphabet',self.save_profile,'Save all taught letters and samples. The default folder travels with this app.')]:form.addRow(button(title,callback,hint))
        form=self.image_form
        self.manual_settings=QCheckBox('Use manual image settings');self.manual_settings.setToolTip('Normally the app finds the best settings automatically. Check this to use the image controls below for the next read.');form.addRow(self.manual_settings)
        self.threshold=QSpinBox();self.threshold.setRange(-1,255);self.threshold.setValue(-1);self.threshold.setSpecialValueText('Automatic')
        self.polarity=QComboBox();self.polarity.addItems(['dark','light','range','local light','local dark'])
        self.range_low=QSpinBox();self.range_low.setRange(0,255)
        self.range_high=QSpinBox();self.range_high.setRange(0,255);self.range_high.setValue(255)
        self.local_window=QSpinBox();self.local_window.setRange(3,101);self.local_window.setSingleStep(2);self.local_window.setValue(7)
        self.scale=QDoubleSpinBox();self.scale.setRange(.25,6);self.scale.setSingleStep(.25);self.scale.setValue(1)
        self.area=QSpinBox();self.area.setRange(0,1000);self.area.setValue(2)
        self.minimum=QDoubleSpinBox();self.minimum.setRange(0,1);self.minimum.setSingleStep(.05);self.minimum.setValue(.58)
        self.space=QDoubleSpinBox();self.space.setRange(.1,5);self.space.setValue(.65);self.space.setSingleStep(.1)
        self.line_gap=QSpinBox();self.line_gap.setRange(0,40);self.line_gap.setValue(2)
        self.char_gap=QSpinBox();self.char_gap.setRange(0,20)
        for label,w,hint in [
            ('Threshold',self.threshold,'Brightness cutoff from 0 to 255. Automatic estimates it. Used by manual reading and sample teaching.'),
            ('Foreground',self.polarity,'Choose dark or light letters, a specific brightness range, or local contrast correction for uneven lighting.'),
            ('Range minimum',self.range_low,'Lowest letter brightness included when Foreground is range.'),
            ('Range maximum',self.range_high,'Highest letter brightness included when Foreground is range.'),
            ('Lighting window',self.local_window,'Local light/dark modes remove smooth lighting changes. Use a window wider than the letter strokes.'),
            ('Scale',self.scale,'Resize the text area before manual reading. Larger values enlarge pixels; automatic reading chooses its own scale.'),
            ('Remove specks',self.area,'Discard connected marks smaller than this many pixels. Lower it if meaningful dots disappear.'),
            ('Minimum score',self.minimum,'Matches below this similarity score become ?. A score is a shape match, not a probability.'),
            ('Word gap',self.space,'Gap required for a space, relative to letter width. Smaller values insert more spaces during manual reading.'),
            ('Join line gaps',self.line_gap,'Bridge small blank horizontal bands inside multipart letters. Too high can merge separate text lines.'),
            ('Join letter gaps',self.char_gap,'Bridge blank columns inside disconnected letters. Start at zero; too high joins neighboring letters.')]:
            w.setToolTip(hint);form.addRow(label,w)
        self.touching=QCheckBox('Split touching letters');self.touching.setChecked(True);self.touching.setToolTip('Try splitting unusually wide symbols when the separate pieces match taught letters better.');form.addRow(self.touching)
        form.addRow(button('Preview image settings',self.preview,'Show the current foreground mask. White pixels are the shapes the matcher sees. This does not decode text.'))
        form.addRow(button('Use selection as text area',self.set_roi,'Keep the drawn source rectangle as the text area. Read also uses a new selection automatically.'))
        form=self.alphabet_form
        help_text=QLabel('Select one glyph in Source, then choose the letter, number, or punctuation it represents. Save your alphabet to keep new samples.');help_text.setWordWrap(True);form.addRow(help_text)
        self.symbol_group=QComboBox();self.symbol_group.addItems(['Letters A–Z','Numbers 0–9','Punctuation / symbols'])
        self.symbol_group.setToolTip('Choose which kind of character to teach. This does not remove existing samples.')
        form.addRow('Character type',self.symbol_group)
        self.letter=QComboBox();self.letter.setEditable(True);self.letter.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.letter.setToolTip('Choose one character or type a single punctuation/symbol character, including Unicode punctuation. Spaces and multi-character labels are not supported.')
        self.symbol_group.currentIndexChanged.connect(self.teaching_group_changed);self.teaching_group_changed(0);form.addRow('Teach as',self.letter)
        form.addRow(button('Teach selected glyph',self.teach,'Select ONE glyph in Source, choose its character, then add it as a template using the current image settings.'))
        form.addRow(button('Import cropped glyph',self.import_glyph,'Choose a file containing one cropped fictional glyph and add it under the chosen character.'))
        form.addRow(button('Remove last sample',self.remove_sample,'Remove the most recently taught sample for the character selected in Teach as.'))
        self.samples_label=QLabel();self.samples_label.setTextFormat(Qt.TextFormat.PlainText);self.samples_label.setWordWrap(True);form.addRow(self.samples_label)
        form=self.matches_form
        form.addRow(QLabel('Match details: click a row to highlight its symbol.'))
        self.table=QTableWidget(0,4);self.table.setMinimumHeight(200);self.table.setHorizontalHeaderLabels(['Line','Read','Score','Alternatives'])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.cellClicked.connect(self.highlight)
        self.table.setToolTip('Inspect match confidence and alternatives. Click a row to highlight the corresponding symbol in the preview.');form.addRow(self.table)
        right=QSplitter(Qt.Orientation.Vertical);split.addWidget(right)
        views=QSplitter();right.addWidget(views)
        self.source=ImageView();self.preview_view=ImageView()
        paste_action=QAction('Paste image',self.source);paste_action.setToolTip('Paste a screenshot from the clipboard into Source.')
        paste_action.setShortcuts(QKeySequence.StandardKey.Paste);paste_action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);paste_action.triggered.connect(self.paste_image)
        self.source.addAction(paste_action);self.source.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.source.setToolTip('Click here and press Ctrl+V to paste. Drag around words to select them. Scroll to zoom; use the scrollbars to move around.')
        self.preview_view.setToolTip('Recognized symbols are marked here. Green boxes are accepted; orange boxes need review. Scroll to zoom.')
        for title,view in [('Source',self.source),('Recognized text',self.preview_view)]:
            panel=QWidget();vl=QVBoxLayout(panel);vl.setContentsMargins(0,0,0,0);vl.addWidget(QLabel(title));vl.addWidget(view);views.addWidget(panel)
        text_panel=QWidget();text_layout=QVBoxLayout(text_panel);text_layout.setContentsMargins(0,0,0,0)
        text_layout.addWidget(QLabel('Translation: click below to edit or add spaces'))
        self.text=QPlainTextEdit();self.text.setPlaceholderText('Your translation will appear here. Orange boxes and ? mark uncertain symbols.');self.text.setToolTip('Edit the recognized text, add spaces, or correct letters. Text edits do not retrain the alphabet.')
        text_layout.addWidget(self.text);right.addWidget(text_panel)
        self.source.selected.connect(self.select);right.setSizes([520,180]);split.setSizes([400,1200])
        export=QHBoxLayout();layout.addLayout(export)
        export.addWidget(button('Copy text',lambda:QApplication.clipboard().setText(self.text.toPlainText()),'Copy the edited translation to the clipboard so you can paste it into a message or document.'))
        export.addWidget(button('Save text',self.export_text,'Save the edited translation as a UTF-8 text file. The default exports folder is inside this app.'))
        export.addWidget(button('Save marked image',self.export_image,'Save the recognition preview with its letter boxes as a PNG image.'))
        export.addStretch();self.advanced_panel.hide();self.refresh_profile();self.source.setFocus()
    def teaching_group_changed(self,index):
        previous=self.letter.currentText()
        symbols=(TEACHING_SYMBOLS[:26],TEACHING_SYMBOLS[26:36],TEACHING_SYMBOLS[36:])[index]
        self.letter.clear();self.letter.addItems(list(symbols))
        if previous in symbols:self.letter.setCurrentText(previous)
    def toggle_advanced(self,checked):
        self.advanced_panel.setVisible(checked)
        self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
    def error(self,message):QMessageBox.warning(self,'Monomoon Translator',str(message))
    def options(self):return dict(threshold=self.threshold.value(),polarity=self.polarity.currentText(),scale=self.scale.value(),min_area=self.area.value(),range_low=self.range_low.value(),range_high=self.range_high.value(),local_window=self.local_window.value())
    def refresh_profile(self):
        self.profile_label.setText(self.profile.name+(' *' if self.dirty else ''))
        self.samples_label.setText('Samples: '+'  '.join(f'{k}:{len(v)}' for k,v in sorted(self.profile.samples.items())) if self.profile.samples else 'No samples yet.')
    def guard_profile(self):
        if not self.dirty:return True
        answer=QMessageBox.question(self,'Unsaved alphabet','Save alphabet changes?',QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        if answer==QMessageBox.StandardButton.Save:return self.save_profile()
        return answer==QMessageBox.StandardButton.Discard
    def open_image(self):
        path,_=QFileDialog.getOpenFileName(self,'Open screenshot','','Images (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)')
        if path:self.load_image(path)
    def load_image(self,path):
        try:self.set_source_image(read_image(path),str(path))
        except Exception as e:self.error(e)
    def set_source_image(self,image,label):
        if image.shape[0]*image.shape[1]>40_000_000:
            raise ValueError('Image exceeds 40 megapixels. Crop it first.')
        self.image=image
        self.auto_button.setEnabled(True)
        self.source.show_image(image)
        self.selection=None
        self.roi=None
        self.glyphs=[]
        self.result_image=None
        self.table.setRowCount(0)
        self.region_label.setText('Whole image: drag around words to narrow the search, or click Read screenshot.')
        self.preview()
        self.source.setFocus()
        self.statusBar().showMessage(label)
    def paste_image(self):
        if self.thread is not None:return
        clipboard=QApplication.clipboard()
        mime=clipboard.mimeData()
        # Some file managers copy a local image path rather than image pixels.
        if mime is not None and not mime.hasImage() and mime.hasUrls():
            urls=mime.urls()
            if len(urls)==1 and urls[0].isLocalFile():
                self.load_image(urls[0].toLocalFile())
                return
        image=clipboard.image()
        if image.isNull():
            self.error('No image on the clipboard. Copy an image or screenshot first, then paste it here.')
            return
        try:
            if image.width()*image.height()>40_000_000:
                raise ValueError('Image exceeds 40 megapixels. Crop it first.')
            # Draw onto white to flatten transparency and use a known byte layout.
            rgb=QImage(image.size(),QImage.Format.Format_RGB888)
            rgb.fill(Qt.GlobalColor.white)
            painter=QPainter(rgb)
            painter.drawImage(0,0,image)
            painter.end()
            rows=np.frombuffer(rgb.constBits(),dtype=np.uint8,count=rgb.sizeInBytes()).reshape(rgb.height(),rgb.bytesPerLine())
            pixels=rows[:,:rgb.width()*3].reshape(rgb.height(),rgb.width(),3)
            self.set_source_image(cv2.cvtColor(pixels,cv2.COLOR_RGB2BGR),'Pasted image from clipboard')
        except Exception as e:self.error(e)
    def use_starter_profile(self):
        if not self.guard_profile():return
        try:self.profile=Profile.load(resource('examples','starter-alphabet.json'))
        except Exception as e:return self.error(e)
        self.dirty=False
        self.refresh_profile()
        self.statusBar().showMessage('Screenshot alphabet loaded. Your source image is unchanged.')
    def new_profile(self):
        if not self.guard_profile():return
        name,ok=QInputDialog.getText(self,'New alphabet','Alphabet name:')
        if ok:self.profile=Profile(name or 'Untitled alphabet');self.dirty=False;self.refresh_profile()
    def load_profile(self):
        if not self.guard_profile():return
        path,_=QFileDialog.getOpenFileName(self,'Load alphabet',str(data_folder('profiles')),'Alphabet (*.json)')
        if path:
            try:self.profile=Profile.load(path);self.dirty=False;self.refresh_profile()
            except Exception as e:self.error(e)
    def save_profile(self):
        path,_=QFileDialog.getSaveFileName(self,'Save alphabet',str(profile_suggestion(self.profile.name)),'Alphabet (*.json)')
        if not path:return False
        try:self.profile.save(path);self.dirty=False;self.refresh_profile();return True
        except Exception as e:self.error(e);return False
    def select(self,box):
        self.selection=box
        self.region_label.setText('Text selected. Click Read screenshot to read this area.')
        self.statusBar().showMessage(f'Selected source x={box[0]}, y={box[1]}, width={box[2]}, height={box[3]}')
    def set_roi(self):
        if self.selection is None:return self.error('Drag a rectangle on the source first.')
        self.roi=self.selection;self.region_label.setText('Region: '+str(self.roi));self.preview()
    def reset_roi(self):
        self.roi=None
        self.selection=None
        if self.source.selection is not None:
            self.source.scene().removeItem(self.source.selection)
            self.source.selection=None
        self.region_label.setText('Whole image: drag around words to narrow the search, or click Read screenshot.')
        self.preview()
    def region(self):
        if self.image is None:raise ValueError('Open an image first.')
        if self.roi:
            x,y,w,h=self.roi;return self.image[y:y+h,x:x+w]
        return self.image
    def preview(self):
        if self.image is None:return
        try:self.preview_view.show_image(preprocess(self.region(),**self.options()))
        except Exception as e:self.error(e)
    def teach(self):
        if self.selection is None:return self.error('Select one glyph on the source first, excluding its printed label.')
        x,y,w,h=self.selection
        self.add_sample(self.image[y:y+h,x:x+w])
    def add_sample(self,image):
        try:
            self.profile.add(self.letter.currentText(),preprocess(image,**self.options()));self.dirty=True;self.refresh_profile()
            self.statusBar().showMessage('Added sample for '+self.letter.currentText())
        except Exception as e:self.error(e)
    def import_glyph(self):
        path,_=QFileDialog.getOpenFileName(self,'Import one cropped glyph','','Images (*.png *.jpg *.bmp *.webp)')
        if path:
            try:self.add_sample(read_image(path))
            except Exception as e:self.error(e)
    def remove_sample(self):
        key=self.letter.currentText()
        if self.profile.samples.get(key):
            self.profile.samples[key].pop()
            if not self.profile.samples[key]:del self.profile.samples[key]
            self.dirty=True;self.refresh_profile()
    def decode(self,automatic=True):
        if self.thread is not None:return
        if not self.profile.samples:
            return self.error('Load an alphabet first, or click Use screenshot alphabet for your game screenshots.')
        if self.text.document().isModified():
            answer=QMessageBox.question(self,'Replace edited text','Decoding will replace your edited text. Continue?')
            if answer!=QMessageBox.StandardButton.Yes:return
        if self.selection is not None:
            self.roi=self.selection
            self.region_label.setText('Region: '+str(self.roi))
        if automatic:
            self.scale.setValue(1)
        try:image=self.region().copy()
        except Exception as e:return self.error(e)
        # Snapshot inputs so editing controls during recognition cannot change results.
        self.job_roi=self.roi;self.job_scale=self.scale.value()
        self.job_source=cv2.resize(image,None,fx=self.job_scale,fy=self.job_scale,interpolation=cv2.INTER_NEAREST) if image.size*self.job_scale**2<120_000_000 else None
        profile=Profile(self.profile.name);profile.samples={k:[m.copy() for m in v] for k,v in self.profile.samples.items()}
        self.thread=QThread(self)
        self.worker=Worker(image,profile,self.options(),dict(minimum=self.minimum.value(),split=self.touching.isChecked(),gap_factor=self.space.value(),line_gap=self.line_gap.value(),char_gap=self.char_gap.value()),automatic=automatic)
        self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self.result);self.worker.failed.connect(self.error);self.worker.finished.connect(self.thread.quit);self.worker.finished.connect(self.worker.deleteLater);self.thread.finished.connect(self.job_finished)
        self.centralWidget().setEnabled(False);self.statusBar().showMessage('Decoding…');self.thread.start()
    def job_finished(self):
        self.thread.deleteLater();self.thread=None;self.centralWidget().setEnabled(True)
    def result(self,result):
        mask,text,self.glyphs=result[:3]
        self.last_region_count=0
        if len(result)==4:
            settings=result[3]
            self.last_region_count=settings.get('detected_regions',0)
            self.polarity.setCurrentText(settings['polarity'])
            if 'range_low' in settings:self.range_low.setValue(settings['range_low'])
            if 'range_high' in settings:self.range_high.setValue(settings['range_high'])
            if 'local_window' in settings:self.local_window.setValue(settings['local_window'])
            if 'threshold' in settings:self.threshold.setValue(settings['threshold'])
            self.area.setValue(settings.get('min_area',2))
            self.line_gap.setValue(2)
            self.char_gap.setValue(0)
        self.result_image=annotate(self.job_source if self.job_source is not None else mask,self.glyphs)
        self.preview_view.show_image(self.result_image);self.text.setPlainText(text)
        self.table.setRowCount(len(self.glyphs))
        for row,g in enumerate(self.glyphs):
            for col,value in enumerate([str(g.line+1),g.letter,f'{g.confidence:.0%}',' / '.join(f'{k} {v:.0%}' for k,v in g.alternatives)]):self.table.setItem(row,col,QTableWidgetItem(value))
        self.table.resizeColumnsToContents()
        blocks=f'{self.last_region_count} text blocks; ' if self.last_region_count else ''
        self.statusBar().showMessage(f'{blocks}{len(self.glyphs)} glyphs; {sum(not g.accepted for g in self.glyphs)} uncertain. Text is editable.')
    def highlight(self,row,column):
        if row>=len(self.glyphs):return
        x,y,w,h=self.glyphs[row].box
        self.preview_view.centerOn(x+w/2,y+h/2)
        if self.preview_view.selection:self.preview_view.scene().removeItem(self.preview_view.selection)
        self.preview_view.selection=self.preview_view.scene().addRect(x,y,w,h,QPen(QColor('#00cfff'),2))
    def export_text(self):
        path,_=QFileDialog.getSaveFileName(self,'Export edited text',str(data_folder('exports')/'decoded.txt'),'Text (*.txt)')
        if path:
            try:Path(path).write_text(self.text.toPlainText(),encoding='utf-8');self.text.document().setModified(False)
            except Exception as e:self.error(e)
    def export_image(self):
        if self.result_image is None:return self.error('Decode an image first.')
        path,_=QFileDialog.getSaveFileName(self,'Export annotated preview',str(data_folder('exports')/'annotated.png'),'PNG (*.png)')
        if path:
            try:
                ok,buf=cv2.imencode('.png',self.result_image)
                if not ok:raise ValueError('Could not encode image.')
                buf.tofile(path)
            except Exception as e:self.error(e)
    def demo(self):
        if not self.guard_profile():return
        base=resource('examples')
        try:self.profile=Profile.load(base/'starter-alphabet.json')
        except Exception as e:return self.error(e)
        self.dirty=False
        self.refresh_profile()
        self.threshold.setValue(30)
        self.polarity.setCurrentText('range')
        self.range_low.setValue(31)
        self.range_high.setValue(31)
        self.area.setValue(8)
        self.scale.setValue(1)
        self.minimum.setValue(.58)
        self.space.setValue(.65)
        self.line_gap.setValue(2)
        self.char_gap.setValue(0)
        self.touching.setChecked(True)
        self.manual_settings.setChecked(False)
        self.load_image(base/'inscription.png')
        self.roi=(0,610,727,215)
        self.region_label.setText('Region: '+str(self.roi))
        self.preview()
    def closeEvent(self,event):
        if self.thread is not None:
            self.statusBar().showMessage('Wait for recognition to finish before closing.');event.ignore();return
        if not self.guard_profile():event.ignore();return
        if self.text.document().isModified():
            answer=QMessageBox.question(self,'Edited text','Close without exporting edited text?',QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:event.ignore();return
        event.accept()


def main():
    if '--self-test' in sys.argv:
        from portable_check import main as check
        sys.exit(check())
    app=QApplication(sys.argv);app.setDesktopFileName('local.monomoon-translator');app.setApplicationName('Monomoon Translator');app.setStyle('Fusion')
    window=Window();window.show()
    if len(sys.argv)>1:window.load_image(sys.argv[1])
    sys.exit(app.exec())

if __name__=='__main__':main()
