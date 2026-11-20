#!/usr/bin/env python3
"""AI Model Lab KDE v3 — Qt6 frontend for standalone local AI laboratory."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
from collections import deque

try:
    from PySide6.QtCore import Qt, QThread, Signal, QTimer, QProcess
    from PySide6.QtGui import QPainter, QColor, QPen, QFont, QDesktopServices, QTextCursor
    from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QLabel,QPushButton,QVBoxLayout,
        QHBoxLayout,QGridLayout,QTabWidget,QTreeWidget,QTreeWidgetItem,QGroupBox,QComboBox,
        QLineEdit,QSpinBox,QFileDialog,QMessageBox,QTextEdit,QSplitter,QTableWidget,
        QTableWidgetItem,QHeaderView,QFormLayout,QFrame,QAbstractItemView,QScrollArea)
    from PySide6.QtCore import QUrl
except ImportError:
    try:
        from PyQt6.QtCore import Qt, QThread, pyqtSignal as Signal, QTimer, QProcess, QUrl
        from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QDesktopServices, QTextCursor
        from PyQt6.QtWidgets import (QApplication,QMainWindow,QWidget,QLabel,QPushButton,QVBoxLayout,
            QHBoxLayout,QGridLayout,QTabWidget,QTreeWidget,QTreeWidgetItem,QGroupBox,QComboBox,
            QLineEdit,QSpinBox,QFileDialog,QMessageBox,QTextEdit,QSplitter,QTableWidget,
            QTableWidgetItem,QHeaderView,QFormLayout,QFrame,QAbstractItemView,QScrollArea)
    except ImportError:
        print('Нужен Qt6 Python. В CachyOS: sudo pacman -S python-pyside6',file=sys.stderr)
        raise SystemExit(2)
import core

COLORS={'bg':'#111723','surface':'#1a2333','panel':'#222d40','line':'#33445d','text':'#e9f0fb',
        'muted':'#a1b4cf','accent':'#62a9ff','good':'#63d6ac','warn':'#ffc578'}
STYLE=f'''
QMainWindow,QWidget {{ background:{COLORS['bg']};color:{COLORS['text']};font-size:13px; }}
QLabel#Header {{ font-size:24px;font-weight:700; }}
QLabel#Subheader {{ font-size:13px;color:{COLORS['muted']}; }}
QLabel#Metric {{ font-size:18px;font-weight:700; }}
QGroupBox {{ border:1px solid {COLORS['line']};border-radius:10px;margin-top:16px;padding:12px;
           background:{COLORS['surface']};font-weight:600; }}
QGroupBox::title {{ subcontrol-origin:margin;left:12px;padding:0 6px; }}
QPushButton {{ background:{COLORS['panel']};border:1px solid {COLORS['line']};
             padding:8px 13px;border-radius:7px;min-height:21px; }}
QPushButton:hover {{ background:#324563;border-color:{COLORS['accent']}; }}
QPushButton:disabled {{ color:#6e7d93;background:#202736;border-color:#253449; }}
QPushButton#Primary {{ background:#245e9a;border:1px solid #438de1;font-weight:700; }}
QPushButton#Danger {{ background:#63333b;border:1px solid #ae5364; }}
QTabWidget::pane {{ border:1px solid {COLORS['line']};border-radius:8px; }}
QTabBar::tab {{ padding:11px 17px;background:{COLORS['surface']};color:{COLORS['muted']}; }}
QTabBar::tab:selected {{ color:white;background:#2a405c;border-bottom:2px solid #62a9ff; }}
QTreeWidget,QTableWidget,QTextEdit,QLineEdit,QComboBox,QSpinBox {{ background:#141e2b;
        border:1px solid #31415a;border-radius:6px;padding:5px;selection-background-color:#2b6197; }}
QHeaderView::section {{ background:#25344a;color:#dfe9f7;border:0px;padding:7px; }}
QScrollBar:vertical {{ background:#1e2a3a;width:10px; }}
QScrollBar::handle:vertical {{ background:#536983;border-radius:4px; }}
'''


def btn(text, callback, primary=False, danger=False):
    b=QPushButton(text)
    if primary: b.setObjectName('Primary')
    if danger: b.setObjectName('Danger')
    b.clicked.connect(callback)
    return b


def cell(text):
    item=QTableWidgetItem(str(text if text is not None else '—'))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class Worker(QThread):
    done=Signal(str)
    failed=Signal(str)
    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn=fn
    def run(self):
        try:self.done.emit(str(self.fn()))
        except Exception as exc:self.failed.emit(f'{type(exc).__name__}: {exc}')


class Sparkline(QWidget):
    def __init__(self, title, unit, max_value=None):
        super().__init__()
        self.title=title;self.unit=unit;self.maximum=max_value
        self.samples=deque(maxlen=60)
        self.setMinimumSize(230,96)
    def add(self,value):
        if value is not None:self.samples.append(float(value));self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#1a2333'))
        p.setPen(QColor('#aec4df'));p.setFont(QFont('Sans',9))
        text='—' if not self.samples else f'{self.samples[-1]:.1f} {self.unit}'
        p.drawText(12,19,f'{self.title}  {text}')
        left,top,right,bottom=13,35,self.width()-13,self.height()-14
        p.setPen(QPen(QColor('#384e68'),1));p.drawLine(left,bottom,right,bottom)
        values=list(self.samples)
        if len(values)<2:return
        vmax=max(self.maximum or max(values)*1.12,0.1)
        points=[]
        for i,v in enumerate(values):
            x=left+(right-left)*i/max(59,len(values)-1)
            y=bottom-min(v/vmax,1)*(bottom-top)
            points.append((int(x),int(y)))
        p.setPen(QPen(QColor('#69b6ff'),2))
        for (x1,y1),(x2,y2) in zip(points,points[1:]):p.drawLine(x1,y1,x2,y2)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        core.prepare()
        self.cfg=core.config();self.settings_data=core.settings()
        self.jobs=[];self.proc=None;self.latest_speed='—'
        self.setWindowTitle('AI Model Lab — KDE · локальная лаборатория')
        self.resize(1260,820)
        self.setMinimumSize(960,640)
        self.setStyleSheet(STYLE)
        frame=QWidget();self.setCentralWidget(frame)
        layout=QVBoxLayout(frame);layout.setContentsMargins(18,15,18,15);layout.setSpacing(12)
        header=QHBoxLayout()
        titles=QVBoxLayout()
        h=QLabel('AI Model Lab');h.setObjectName('Header');titles.addWidget(h)
        t=QLabel('Модели · отдельные сервисы · тесты · GPU и история');t.setObjectName('Subheader');titles.addWidget(t)
        header.addLayout(titles);header.addStretch()
        header.addWidget(btn('🧪 Тесты',lambda:self.tabs.setCurrentIndex(2),True))
        header.addWidget(btn('⚙ Управление',lambda:self.tabs.setCurrentIndex(1),True))
        header.addWidget(btn('↻ Обновить',self.refresh_status))
        layout.addLayout(header)
        metrics=QHBoxLayout();metrics.setSpacing(8)
        self.graph_gpu=Sparkline('GPU', '%',100)
        self.graph_vram=Sparkline('VRAM','GiB',22)
        self.graph_ram=Sparkline('RAM','GiB',64)
        self.graph_speed=Sparkline('Скорость · история','tok/s')
        for g in (self.graph_gpu,self.graph_vram,self.graph_ram,self.graph_speed):
            metrics.addWidget(g,1)
        self.metrics_label=QLabel('Нет данных GPU');self.metrics_label.setWordWrap(True)
        metrics.addWidget(self.metrics_label,1)
        layout.addLayout(metrics)
        self.tabs=QTabWidget()
        layout.addWidget(self.tabs,1)
        self.tab_models=self.build_models();self.tabs.addTab(self.tab_models,'🧠 Модели')
        self.tab_services=self.build_services();self.tabs.addTab(self.tab_services,'⚙ Управление')
        self.tab_tests=self.build_tests();self.tabs.addTab(self.tab_tests,'🧪 Тесты')
        self.tab_results=self.build_results();self.tabs.addTab(self.tab_results,'📊 Отчёты')
        self.tab_settings=self.build_settings();self.tabs.addTab(self.tab_settings,'🔧 Настройки')
        self.message=QLabel('Готово. Все новые отчёты: '+str(core.REPORTS));self.message.setObjectName('Subheader')
        layout.addWidget(self.message)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh_status);self.timer.start(4000)
        self.refresh_reports();self.refresh_status()

    def build_models(self):
        w=QWidget();l=QVBoxLayout(w)
        split=QSplitter(Qt.Orientation.Horizontal)
        self.tree=QTreeWidget();self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(['Модель','Контекст','Назначение'])
        for p in self.cfg.get('models',[]):
            it=QTreeWidgetItem([p.get('name',p['id']),f"{p['context']//1024}K",p.get('purpose','—')]);it.setData(0,Qt.ItemDataRole.UserRole,p['id']);self.tree.addTopLevelItem(it)
        self.tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        split.addWidget(self.tree)
        right=QWidget();r=QVBoxLayout(right)
        box=QGroupBox('Выбранная модель');f=QVBoxLayout(box)
        self.model_info=QLabel('Выбери профиль');self.model_info.setWordWrap(True)
        self.model_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f.addWidget(self.model_info)
        f.addWidget(btn('▶ Запустить модель',self.start_selected,True))
        f.addWidget(btn('⇄ Переключить на выбранную модель',self.switch_model))
        f.addWidget(btn('⏹ Остановить управляемый llama.cpp',lambda:self.confirm_action('Остановить текущий llama-server?',lambda:core.stop('llama')),danger=True))
        f.addWidget(btn('🌐 Открыть WebUI',lambda:self.open_url('http://127.0.0.1:3000')))
        f.addWidget(btn('🏢 Открыть Agent Office',self.open_office))
        r.addWidget(box)
        r.addWidget(QLabel('Контекст 128K подтверждён для Blend Q4/Qwen3.8/Coder. Другие профили экспериментальные.'))
        r.addStretch()
        split.addWidget(right);split.setSizes([790,390]);l.addWidget(split)
        self.tree.currentItemChanged.connect(self.on_model_selected)
        if self.tree.topLevelItemCount():self.tree.setCurrentItem(self.tree.topLevelItem(0))
        return w

    def selected_alias(self):
        it=self.tree.currentItem()
        return it.data(0,Qt.ItemDataRole.UserRole) if it else None

    def on_model_selected(self,*_):
        p=core.model_by_id(self.selected_alias())
        if not p:return
        try: path=str(core.resolve_gguf(p));presence='✓ GGUF найден'
        except Exception as exc: path=str(exc);presence='⚠ Проверить GGUF'
        self.model_info.setText(f"{p['name']}\n\nНазначение: {p.get('purpose','—')}\n"
            f"Alias: {p['id']}\nКонтекст: {p['context']:,} токенов\n"
            f"KV: RAM, q8_0 · thinking off (если поддерживается)\n\n{presence}\n{path}")

    def async_call(self,description,fn):
        self.message.setText('⏳ '+description)
        job=Worker(fn,self)
        self.jobs.append(job)
        def ok(text):
            self.message.setText(text.split('\n')[0][:250]);self.append_log('✅ '+description+'\n'+text);self.refresh_status()
        def fail(err):
            self.message.setText('Ошибка: '+err);self.append_log('❌ '+description+'\n'+err);QMessageBox.warning(self,'AI Model Lab',err)
        def cleanup():
            if job in self.jobs:self.jobs.remove(job)
        job.done.connect(ok);job.failed.connect(fail);job.finished.connect(cleanup);job.start()

    def confirm_action(self,message,fn):
        if QMessageBox.question(self,'Подтверждение',message+ '\nАктивные тесты могут быть прерваны.')==QMessageBox.StandardButton.Yes:
            self.async_call(message,fn)

    def start_selected(self):
        alias=self.selected_alias()
        if alias:self.async_call('Загрузка '+alias,lambda:core.start_model(alias))

    def switch_model(self):
        alias=self.selected_alias()
        if not alias:return
        current=core.verified('llama')
        if not current:
            if core.port_open(8080):
                QMessageBox.warning(self,'Внешний сервер','На порту 8080 запущен неуправляемый сервер. AI Lab не останавливает его автоматически.')
                return
            self.start_selected();return
        if current.get('alias')==alias:
            QMessageBox.information(self,'Модель','Выбранная модель уже работает.');return
        if QMessageBox.question(self,'Смена модели',
           f"Остановить {current.get('alias')} и запустить {alias}? Активный бенчмарк прервётся.")!=QMessageBox.StandardButton.Yes:
            return
        def task():
            msg=core.stop('llama')
            if core.verified('llama') or core.port_open(8080):
                raise RuntimeError('Сервер всё ещё работает — переключение отменено. '+msg)
            return msg+'\n'+core.start_model(alias)
        self.async_call('Смена модели на '+alias,task)

    def open_url(self,url):
        QDesktopServices.openUrl(QUrl(url))

    def open_office(self):
        url=core.office_url()
        if url:self.open_url(url)
        else:QMessageBox.information(self,'Agent Office','Не удалось определить веб-адрес. Укажи office_url в настройках или проверь журнал Agent Office.')

    def build_services(self):
        w=QWidget();l=QVBoxLayout(w)
        label=QLabel('Каждый сервис управляется отдельно. Порт 8080 не освобождается автоматически; сторонние процессы не завершаются.');label.setWordWrap(True);l.addWidget(label)
        self.service_labels={}
        services=[('llama','llama.cpp · модель',self.start_selected,lambda:core.stop('llama'),None),
                  ('webui','Open WebUI · :3000',core.webui_start,core.webui_stop,lambda:self.open_url('http://127.0.0.1:3000')),
                  ('office','Agent Office',core.office_start,lambda:core.stop('office'),self.open_office),
                  ('comfy','ComfyUI · :8188',core.comfy_start,lambda:core.stop('comfy'),lambda:self.open_url('http://127.0.0.1:8188'))]
        for sid,name,start,stop,open_action in services:
            group=QGroupBox(name);row=QHBoxLayout(group)
            lab=QLabel('Проверяется...');self.service_labels[sid]=lab;row.addWidget(lab,1)
            if sid=='llama':
                row.addWidget(btn('▶ Выбранная модель',start,True))
            else:row.addWidget(btn('▶ Запустить',lambda s=start,n=name:self.async_call('Запуск '+n,s),True))
            row.addWidget(btn('⏹ Остановить',lambda s=stop,n=name:self.confirm_action('Остановить '+n+'?',s),danger=True))
            if open_action:row.addWidget(btn('Открыть',open_action))
            l.addWidget(group)
        l.addWidget(btn('⏹ ОСТАНОВИТЬ ВСЕ управляемые сервисы',self.stop_all,False,True))
        note=QLabel('«Все» = управляемые llama/Agent Office/ComfyUI и systemd-user Open WebUI. Pi и OpenCode не завершаются.');note.setWordWrap(True);l.addWidget(note)
        l.addStretch();return w

    def stop_all(self):
        def work():
            return '\n'.join((core.stop('llama'),core.stop('office'),core.stop('comfy'),core.webui_stop()))
        self.confirm_action('Остановить ВСЕ управляемые AI-сервисы?',work)

    def build_tests(self):
        w=QWidget();l=QVBoxLayout(w)
        options=QGroupBox('Встроенные бенчмарки (файлы и отчёты внутри AI Model Lab)');form=QGridLayout(options)
        form.addWidget(QLabel('Испытание'),0,0)
        self.test_kind=QComboBox()
        for key,name in [('speed','Скорость API — до 256 токенов'),('speed512','Скорость API — до 512 токенов'),
                         ('qa','Логика / арифметика (3 задачи)'),('context8','Длинный контекст (около 8K)'),
                         ('context32','Длинный контекст (около 32K)'),('p1','Android LP-P1: STB UI → VOD'),
                         ('p2','Android LP-P2: выбор плеера')]:self.test_kind.addItem(name,key)
        form.addWidget(self.test_kind,0,1,1,3)
        form.addWidget(QLabel('Android-проект'),1,0)
        self.project=QLineEdit(self.settings_data.get('android_project',''));form.addWidget(self.project,1,1,1,2)
        form.addWidget(btn('Обзор',self.browse_project),1,3)
        form.addWidget(QLabel('Лимит времени, с'),2,0)
        self.timeout=QSpinBox();self.timeout.setRange(30,7200);self.timeout.setValue(int(self.settings_data.get('benchmark_timeout',1800)));form.addWidget(self.timeout,2,1)
        form.addWidget(QLabel('Лимит инструментов Pi'),2,2)
        self.budget=QSpinBox();self.budget.setRange(1,200);self.budget.setValue(int(self.settings_data.get('tool_budget',24)));form.addWidget(self.budget,2,3)
        row=QHBoxLayout();self.run_btn=btn('▶ Запустить испытание',self.launch_test,True);row.addWidget(self.run_btn)
        self.cancel_btn=btn('⏹ Прервать испытание',self.cancel_test,False,True);self.cancel_btn.setEnabled(False);row.addWidget(self.cancel_btn)
        row.addWidget(btn('📁 Папка отчётов',lambda:self.open_url(core.REPORTS.as_uri())))
        l.addWidget(options);l.addLayout(row)
        warn=QLabel('⚠ Android: Pi получает только инструменты чтения, но это НЕ файловая песочница. Не запускай на секретных репозиториях без отдельной изоляции.');warn.setWordWrap(True);l.addWidget(warn)
        self.test_output=QTextEdit();self.test_output.setReadOnly(True);self.test_output.setPlaceholderText('Здесь будет вывод теста, результаты записываются в папку data/reports/');l.addWidget(self.test_output,1)
        return w

    def browse_project(self):
        chosen=QFileDialog.getExistingDirectory(self,'Выбрать Android-проект',self.project.text() or str(Path.home()))
        if chosen:self.project.setText(chosen)

    def launch_test(self):
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:return
        current=core.get_status()
        alias=current.get('alias')
        if not alias:
            QMessageBox.warning(self,'Нет модели','Сначала запусти llama-server с нужной моделью.');return
        kind=self.test_kind.currentData()
        actual='speed' if kind.startswith('speed') else ('context' if kind.startswith('context') else kind)
        if actual in ('p1','p2'):
            try:core.preflight_android()
            except Exception as exc:QMessageBox.warning(self,'Проверка контекста',str(exc));return
            if not Path(self.project.text()).is_dir():QMessageBox.warning(self,'Android-проект','Выбери существующий каталог.');return
            if QMessageBox.question(self,'Доступ Pi','Испытание читает Android-проект через Pi read/grep/find/ls.\nЭто НЕ ОС-песочница. Продолжить?')!=QMessageBox.StandardButton.Yes:return
        args=[str(core.ROOT/'bench.py'),'--kind',actual,'--model',alias,'--timeout',str(self.timeout.value()),
              '--budget',str(self.budget.value()),'--project',self.project.text(),
              '--output-tokens',str(512 if kind=='speed512' else 256),
              '--target-tokens',str(32768 if kind=='context32' else 8192)]
        self.test_output.append('▶ Тест '+kind+' · '+alias)
        self.proc=QProcess(self)
        self.proc.setWorkingDirectory(str(core.ROOT))
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.test_pipe)
        self.proc.finished.connect(self.test_finished)
        self.proc.start(sys.executable,args)
        if not self.proc.waitForStarted(2500):
            self.test_output.append('Не удалось запустить benchmark runner.');return
        self.run_btn.setEnabled(False);self.cancel_btn.setEnabled(True)
        self.tabs.setCurrentIndex(2)

    def test_pipe(self):
        if self.proc:
            raw=bytes(self.proc.readAllStandardOutput()).decode('utf-8','replace')
            self.test_output.moveCursor(QTextCursor.MoveOperation.End)
            self.test_output.insertPlainText(raw)
            self.test_output.ensureCursorVisible()

    def test_finished(self,exit_code,exit_status):
        self.test_pipe()
        self.run_btn.setEnabled(True);self.cancel_btn.setEnabled(False)
        self.test_output.append(f'\nПроцесс завершился: exit={exit_code}')
        self.refresh_reports()

    def cancel_test(self):
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:
            if QMessageBox.question(self,'Прервать тест','Прервать текущий эксперимент? Успевшие записаться события сохранятся.')==QMessageBox.StandardButton.Yes:
                self.proc.terminate()  # bench.py forwards SIGTERM to child process group

    def build_results(self):
        w=QWidget();l=QVBoxLayout(w)
        row=QHBoxLayout();row.addWidget(btn('↻ Обновить отчёты',self.refresh_reports));row.addWidget(btn('🔎 Сравнить два выбранных',self.compare_reports));row.addStretch();l.addLayout(row)
        self.reports=QTableWidget(0,6);self.reports.setHorizontalHeaderLabels(['Дата/папка','Модель','Тест','Статус','Время, с','VRAM, MiB'])
        self.reports.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.reports.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.reports.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.reports.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        l.addWidget(self.reports,1)
        row2=QHBoxLayout();row2.addWidget(btn('Показать summary.json',self.show_report));row2.addWidget(btn('Открыть папку отчёта',self.open_report_dir));row2.addStretch();l.addLayout(row2)
        self.report_text=QTextEdit();self.report_text.setReadOnly(True);self.report_text.setMinimumHeight(130);l.addWidget(self.report_text,1)
        return w

    def selected_reports(self):
        indices=sorted({index.row() for index in self.reports.selectedIndexes()})
        files=[]
        for i in indices:
            item=self.reports.item(i,0)
            if item: files.append(Path(item.data(Qt.ItemDataRole.UserRole)))
        return files

    def refresh_reports(self):
        if not hasattr(self,'reports'):return
        roots=sorted(core.REPORTS.glob('*/summary.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]
        self.reports.setRowCount(len(roots))
        if hasattr(self,'graph_speed'):
            self.graph_speed.samples.clear()
            for path in reversed(roots):
                historical=core.load_json(path,{}) or {}
                if historical.get('kind')!='speed': continue
                cases=(historical.get('result') or {}).get('cases') or []
                if cases and isinstance(cases[0].get('tokens_per_wall_s'),(int,float)):
                    self.graph_speed.add(cases[0]['tokens_per_wall_s'])
        for i,path in enumerate(roots):
            info=core.load_json(path,{}) or {};result=info.get('result') or {};hw=info.get('hardware') or {}
            values=[path.parent.name,info.get('model'),info.get('kind'),result.get('status'),
                    info.get('elapsed_s'),(hw.get('vram_mib') or {}).get('max')]
            for j,value in enumerate(values):self.reports.setItem(i,j,cell(value))
            self.reports.item(i,0).setData(Qt.ItemDataRole.UserRole,str(path))

    def show_report(self):
        files=self.selected_reports()
        if not files:return
        self.report_text.setPlainText(files[0].read_text(encoding='utf-8'))

    def open_report_dir(self):
        files=self.selected_reports()
        if files:self.open_url(files[0].parent.as_uri())

    def compare_reports(self):
        files=self.selected_reports()
        if len(files)!=2:
            QMessageBox.information(self,'Сравнение','Выбери ровно два отчёта (Ctrl + щелчок).');return
        a,b=(core.load_json(p,{}) for p in files)
        ra=a.get('result',{});rb=b.get('result',{})
        equal=ra.get('prompt_sha256') and ra.get('prompt_sha256')==rb.get('prompt_sha256')
        kind_ok=a.get('kind')==b.get('kind')
        self.report_text.setPlainText(
            'СРАВНЕНИЕ\n\n'+ '\n'.join(
                f"{k}: {a.get(k)} | {b.get(k)}" for k in ('model','kind','elapsed_s'))+
            f"\n\nStatus: {ra.get('status')} | {rb.get('status')}\n"
            f"VRAM peak: {(a.get('hardware',{}).get('vram_mib') or {}).get('max')} | {(b.get('hardware',{}).get('vram_mib') or {}).get('max')} MiB\n"
            f"Энергия: {a.get('hardware',{}).get('gpu_energy_wh_estimate')} | {b.get('hardware',{}).get('gpu_energy_wh_estimate')} Wh\n"
            f"\nСопоставимость по SHA256: {'ДА' if equal else 'НЕТ'}; тип задания: {'одинаковый' if kind_ok else 'РАЗНЫЙ'}\n"
            'Разная версия промпта или разные условия не дают сравнивать качество напрямую.' )

    def build_settings(self):
        w=QWidget();l=QVBoxLayout(w)
        box=QGroupBox('Настройки программы');form=QFormLayout(box)
        self.set_inputs={}
        fields=[('android_project','Каталог Android-проекта'),('office_dir','Каталог Agent Office'),
                ('office_url','URL Agent Office (необязательно)'),('comfy_dir','Каталог ComfyUI'),
                ('webui_service','Служба WebUI')]
        for key,label in fields:
            v=QLineEdit(str(self.settings_data.get(key,'')));self.set_inputs[key]=v;form.addRow(label,v)
        l.addWidget(box)
        box2=QGroupBox('Профили моделей — models.json');vb=QVBoxLayout(box2)
        self.profile_box=QTextEdit();self.profile_box.setAcceptRichText(False)
        self.profile_box.setPlainText(json.dumps(self.cfg,ensure_ascii=False,indent=2))
        vb.addWidget(self.profile_box)
        vb.addWidget(btn('💾 Сохранить настройки и профили',self.save_settings,True));l.addWidget(box2,1)
        hint=QLabel('Изменяются только файлы в каталоге AI Model Lab. Конфигурация Pi не переписывается автоматически.');l.addWidget(hint)
        return w

    def save_settings(self):
        try:
            new=json.loads(self.profile_box.toPlainText())
            ids=[p['id'] for p in new['models']]
            if len(ids)!=len(set(ids)) or not ids:raise ValueError('Повторяются ID моделей')
            for p in new['models']:
                if not 4096<=int(p['context'])<=524288:raise ValueError('Некорректный context у '+p['id'])
            old=core.load_json(core.SETTINGS,{}) or {}
            old.update({k:widget.text().strip() for k,widget in self.set_inputs.items()})
            core.atomic_json(core.SETTINGS,old);core.atomic_json(core.MODELS,new)
            self.cfg=new;self.settings_data=old
            QMessageBox.information(self,'Настройки','Сохранено в каталоге приложения. Для новых моделей обнови окно.')
        except (ValueError,KeyError,TypeError) as e:QMessageBox.warning(self,'Ошибка настройки',str(e))

    def append_log(self,text):
        if hasattr(self,'test_output'):
            self.test_output.append('\n'+text)

    def refresh_status(self):
        gpu=core.gpu_metrics();ram=core.ram_metrics()
        if gpu:
            self.graph_gpu.add(gpu.get('gpu'))
            self.graph_vram.maximum=max(22,float(gpu.get('vram_total',22))/1024)
            self.graph_vram.add(gpu.get('vram',0)/1024)
        if ram:
            self.graph_ram.maximum=max(1,ram.get('ram_total',64))
            self.graph_ram.add(ram.get('ram'))
        self.metrics_label.setText(f"🌡 {gpu.get('temp','—')} °C · ⚡ {gpu.get('power','—')} W\n"
            f"GPU: {gpu.get('gpu','—')}% · VRAM: {round(gpu.get('vram',0)/1024,2)} / {round(gpu.get('vram_total',0)/1024,2)} GiB\n"
            f"RAM: {round(ram.get('ram',0),1)} / {round(ram.get('ram_total',0),1)} GiB · Swap {ram.get('swap','—')} GiB")
        state=core.get_status()
        names={'llama':('работает '+state.get('alias','')) if state['llama'] else ('внешний сервер' if state.get('llama_external') else 'не работает'),
               'webui':'работает' if state['webui'] else 'не отвечает',
               'office':'запущен (AI Lab)' if state['office'] else 'не подтверждён',
               'comfy':'работает' if state['comfy'] else 'не отвечает'}
        for sid,lab in self.service_labels.items():
            lab.setText(names.get(sid,'—'))
            lab.setStyleSheet('color: #63d6ac;' if (sid=='llama' and state['llama']) or (sid=='webui' and state['webui']) or (sid=='office' and state['office']) or (sid=='comfy' and state['comfy']) else 'color: #e9b5a0;')
        self.setWindowTitle(f"AI Model Lab — KDE · {state.get('alias') or 'модель не выбрана'} · {state.get('ctx') or '?'} ctx")

    def closeEvent(self,event):
        if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:
            QMessageBox.information(self,'Активный тест','Сначала останови текущий тест — чтобы корректно записать отчёт.')
            event.ignore();return
        event.accept()   # All launched servers are detached and remain running


def main():
    app=QApplication(sys.argv)
    app.setApplicationName('AI Model Lab')
    app.setOrganizationName('AI Model Lab Local')
    window=Window();window.show()
    sys.exit(app.exec())

if __name__=='__main__':main()
