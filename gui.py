#!/usr/bin/env python3
"""AI Model Lab KDE v3.1 — Qt6 frontend for standalone local AI laboratory."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from collections import deque

try:
    from PySide6.QtCore import Qt, QThread, Signal, QTimer, QProcess
    from PySide6.QtGui import QPainter, QColor, QPen, QFont, QDesktopServices, QTextCursor
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
        QHBoxLayout, QGridLayout, QTabWidget, QTreeWidget, QTreeWidgetItem, QGroupBox,
        QComboBox, QLineEdit, QSpinBox, QFileDialog, QMessageBox, QTextEdit, QSplitter,
        QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QAbstractItemView,
        QScrollArea, QCheckBox, QDoubleSpinBox
    )
    from PySide6.QtCore import QUrl
except ImportError:
    try:
        from PyQt6.QtCore import Qt, QThread, pyqtSignal as Signal, QTimer, QProcess, QUrl
        from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QDesktopServices, QTextCursor
        from PyQt6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
            QHBoxLayout, QGridLayout, QTabWidget, QTreeWidget, QTreeWidgetItem, QGroupBox,
            QComboBox, QLineEdit, QSpinBox, QFileDialog, QMessageBox, QTextEdit, QSplitter,
            QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QAbstractItemView,
            QScrollArea, QCheckBox, QDoubleSpinBox
        )
    except ImportError:
        print('Нужен Qt6 Python. В CachyOS: sudo pacman -S pyside6', file=sys.stderr)
        raise SystemExit(2)

import core

COLORS = {
    'bg': '#111723', 'surface': '#1a2333', 'panel': '#222d40', 'line': '#33445d', 'text': '#e9f0fb',
    'muted': '#a1b4cf', 'accent': '#62a9ff', 'good': '#63d6ac', 'warn': '#ffc578', 'bad': '#e58f9b'
}
STYLE = f'''
QMainWindow,QWidget {{ background:{COLORS['bg']};color:{COLORS['text']};font-size:13px; }}
QLabel#Header {{ font-size:24px;font-weight:700; }}
QLabel#Subheader {{ font-size:13px;color:{COLORS['muted']}; }}
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
QTreeWidget,QTableWidget,QTextEdit,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {{ background:#141e2b;
        border:1px solid #31415a;border-radius:6px;padding:5px;selection-background-color:#2b6197; }}
QHeaderView::section {{ background:#25344a;color:#dfe9f7;border:0px;padding:7px; }}
QScrollBar:vertical {{ background:#1e2a3a;width:10px; }}
QScrollBar::handle:vertical {{ background:#536983;border-radius:4px; }}
QScrollBar:horizontal {{ background:#1e2a3a;height:10px; }}
QScrollBar::handle:horizontal {{ background:#536983;border-radius:4px; }}
'''


def btn(text, callback, primary=False, danger=False):
    b = QPushButton(text)
    if primary:
        b.setObjectName('Primary')
    if danger:
        b.setObjectName('Danger')
    b.clicked.connect(callback)
    return b


def cell(text):
    item = QTableWidgetItem(str(text if text is not None else '—'))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class Worker(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(str(self.fn()))
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')


class Sparkline(QWidget):
    def __init__(self, title, unit, max_value=None):
        super().__init__()
        self.title = title
        self.unit = unit
        self.maximum = max_value
        self.samples = deque(maxlen=60)
        self.setMinimumSize(220, 96)

    def add(self, value):
        if value is not None:
            self.samples.append(float(value))
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#1a2333'))
        p.setPen(QColor('#aec4df'))
        p.setFont(QFont('Sans', 9))
        text = '—' if not self.samples else f'{self.samples[-1]:.1f} {self.unit}'
        p.drawText(12, 19, f'{self.title}  {text}')
        left, top, right, bottom = 13, 35, self.width() - 13, self.height() - 14
        p.setPen(QPen(QColor('#384e68'), 1))
        p.drawLine(left, bottom, right, bottom)
        values = list(self.samples)
        if len(values) < 2:
            return
        vmax = max(self.maximum or max(values) * 1.12, 0.1)
        points = []
        for i, v in enumerate(values):
            x = left + (right - left) * i / max(59, len(values) - 1)
            y = bottom - min(v / vmax, 1) * (bottom - top)
            points.append((int(x), int(y)))
        p.setPen(QPen(QColor('#69b6ff'), 2))
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            p.drawLine(x1, y1, x2, y2)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        core.prepare()
        self.cfg = core.config()
        self.settings_data = core.settings()
        self.jobs = []
        self.proc = None
        self.model_action_busy = False
        self.last_log_path = None
        self.last_log_text = ''

        self.setWindowTitle('AI Model Lab — KDE · локальная лаборатория')
        self.resize(1320, 900)
        self.setMinimumSize(980, 680)
        self.setStyleSheet(STYLE)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 15, 18, 15)
        layout.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        h = QLabel('AI Model Lab')
        h.setObjectName('Header')
        titles.addWidget(h)
        t = QLabel('Модели · отдельные сервисы · тесты · GPU и история')
        t.setObjectName('Subheader')
        titles.addWidget(t)
        header.addLayout(titles)
        header.addStretch()
        header.addWidget(btn('🧪 Тесты', lambda: self.tabs.setCurrentIndex(2), True))
        header.addWidget(btn('⚙ Управление', lambda: self.tabs.setCurrentIndex(1), True))
        header.addWidget(btn('↻ Обновить', self.refresh_status))
        layout.addLayout(header)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self.graph_gpu = Sparkline('GPU', '%', 100)
        self.graph_vram = Sparkline('VRAM', 'GiB', 22)
        self.graph_ram = Sparkline('RAM', 'GiB', 64)
        self.graph_speed = Sparkline('Скорость · история', 'tok/s')
        for g in (self.graph_gpu, self.graph_vram, self.graph_ram, self.graph_speed):
            metrics.addWidget(g, 1)
        self.metrics_label = QLabel('Нет данных GPU')
        self.metrics_label.setWordWrap(True)
        metrics.addWidget(self.metrics_label, 1)
        layout.addLayout(metrics)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.tab_models = self.build_models()
        self.tabs.addTab(self.tab_models, '🧠 Модели')
        self.tab_services = self.build_services()
        self.tabs.addTab(self.tab_services, '⚙ Управление')
        self.tab_tests = self.build_tests()
        self.tabs.addTab(self.tab_tests, '🧪 Тесты')
        self.tab_results = self.build_results()
        self.tabs.addTab(self.tab_results, '📊 Отчёты')
        self.tab_settings = self.build_settings()
        self.tabs.addTab(self.tab_settings, '🔧 Настройки')

        self.message = QLabel('Готово. Все новые отчёты: ' + str(core.REPORTS))
        self.message.setObjectName('Subheader')
        layout.addWidget(self.message)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(3000)

        self.refresh_reports()
        self.refresh_status()

    # ---------- Shared helpers ----------
    def set_message(self, text):
        self.message.setText(text)
        self.status_label.setText(text)

    def async_call(self, description, fn, after=None):
        self.set_message('⏳ ' + description)
        job = Worker(fn, self)
        self.jobs.append(job)

        def ok(text):
            self.set_message(text.split('\n')[0][:250])
            self.append_log('✅ ' + description + '\n' + text)
            if after:
                after(True, text)
            self.refresh_status()

        def fail(err):
            self.set_message('Ошибка: ' + err)
            self.append_log('❌ ' + description + '\n' + err)
            QMessageBox.warning(self, 'AI Model Lab', err)
            if after:
                after(False, err)

        def cleanup():
            if job in self.jobs:
                self.jobs.remove(job)

        job.done.connect(ok)
        job.failed.connect(fail)
        job.finished.connect(cleanup)
        job.start()

    def confirm_action(self, message, fn, after=None):
        if QMessageBox.question(self, 'Подтверждение', message + '\nАктивные тесты могут быть прерваны.') == QMessageBox.StandardButton.Yes:
            self.async_call(message, fn, after=after)

    def selected_alias(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def selected_model_profile(self):
        alias = self.selected_alias()
        return next((m for m in self.cfg.get('models', []) if m.get('id') == alias), None)

    def open_url(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def open_office(self):
        url = core.office_url()
        if url:
            self.open_url(url)
        else:
            QMessageBox.information(self, 'Agent Office', 'Не удалось определить веб-адрес. Укажи office_url в настройках или проверь журнал Agent Office.')

    # ---------- Models tab ----------
    def build_models(self):
        w = QWidget()
        l = QVBoxLayout(w)

        split = QSplitter(Qt.Orientation.Horizontal)
        l.addWidget(split, 1)

        left_wrap = QWidget()
        left_layout = QVBoxLayout(left_wrap)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(['Модель', 'Контекст', 'Назначение'])
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setUniformRowHeights(True)
        self.tree.itemDoubleClicked.connect(self.open_selected_in_editor)
        left_layout.addWidget(self.tree, 3)

        self.status_label = QLabel('Статус: ожидание')
        self.status_label.setObjectName('Subheader')
        left_layout.addWidget(self.status_label)

        logs_group = QGroupBox('Живые логи managed llama.cpp')
        logs_layout = QVBoxLayout(logs_group)
        self.live_logs = QTextEdit()
        self.live_logs.setReadOnly(True)
        self.live_logs.setMinimumHeight(150)
        self.live_logs.setPlaceholderText('После запуска модели здесь появятся последние строки журнала llama.cpp')
        logs_layout.addWidget(self.live_logs)
        left_layout.addWidget(logs_group, 2)

        split.addWidget(left_wrap)

        right = QWidget()
        r = QVBoxLayout(right)
        box = QGroupBox('Выбранная модель')
        f = QVBoxLayout(box)
        self.model_info = QTextEdit()
        self.model_info.setReadOnly(True)
        self.model_info.setMinimumHeight(210)
        self.model_info.setPlaceholderText('Выбери профиль модели')
        f.addWidget(self.model_info)

        self.model_action_btn = QPushButton('● Статус модели')
        self.model_action_btn.clicked.connect(self.model_action)
        f.addWidget(self.model_action_btn)
        self.edit_model_btn = btn('✎ Редактировать выбранную модель', self.open_selected_in_editor)
        f.addWidget(self.edit_model_btn)
        f.addWidget(btn('🌐 Открыть WebUI', lambda: self.open_url('http://127.0.0.1:3000')))
        f.addWidget(btn('🏢 Открыть Agent Office', self.open_office))
        r.addWidget(box)
        r.addWidget(QLabel('Контекст 128K подтверждён для Blend Q4/Qwen3.8/Coder. Другие профили экспериментальные.\nДвойной щелчок по модели открывает её редактирование.'))
        r.addStretch()
        split.addWidget(right)
        split.setSizes([700, 520])

        self.populate_model_tree()
        self.tree.currentItemChanged.connect(self.on_model_selected)
        if self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        return w

    def populate_model_tree(self):
        self.tree.clear()
        for p in self.cfg.get('models', []):
            it = QTreeWidgetItem([p.get('name', p['id']), f"{int(p['context']) // 1024}K", p.get('purpose', '—')])
            it.setData(0, Qt.ItemDataRole.UserRole, p['id'])
            self.tree.addTopLevelItem(it)

    def on_model_selected(self, *_):
        p = self.selected_model_profile()
        if not p:
            self.model_info.setPlainText('Выбери профиль модели')
            return
        try:
            path = str(core.resolve_gguf(p))
            presence = '✓ GGUF найден'
        except Exception as exc:
            path = str(exc)
            presence = '⚠ Проверить GGUF'
        text = (
            f"{p['name']}\n\n"
            f"Назначение: {p.get('purpose', '—')}\n"
            f"Alias: {p['id']}\n"
            f"Контекст: {int(p['context']):,} токенов\n"
            f"KV: RAM, q8_0 · thinking off {'включен' if p.get('thinking_off') else 'не задан'}\n"
            f"Путь: {p.get('path', 'поиск по шаблону')}\n"
            f"Шаблон: {p.get('match', '—')}\n"
            f"Доп. параметры: n_cpu_moe={p.get('n_cpu_moe', '—')}, mmproj={p.get('mmproj', '—')}\n\n"
            f"{presence}\n{path}"
        )
        self.model_info.setPlainText(text)
        self.refresh_model_action_button()

    def refresh_model_action_button(self):
        selected = self.selected_alias()
        state = core.get_status()
        if self.model_action_busy:
            text = '⏳ Выполняется операция…'
            style = 'background:#7a5b20;border:1px solid #d0a13c;font-weight:700;'
        elif state.get('llama') and state.get('alias') == selected:
            text = '🟢 Модель запущена — остановить'
            style = 'background:#255b47;border:1px solid #56b790;font-weight:700;'
        elif state.get('llama') and state.get('alias') and selected and state.get('alias') != selected:
            text = f"🟡 Работает {state.get('alias')} — переключить на {selected}"
            style = 'background:#5a4a20;border:1px solid #d6b15b;font-weight:700;'
        elif state.get('llama_external'):
            text = '🟠 Порт 8080 занят внешним сервером'
            style = 'background:#5a3f20;border:1px solid #d18d4b;font-weight:700;'
        else:
            text = '⚪ Модель не запущена — запустить'
            style = 'background:#245e9a;border:1px solid #438de1;font-weight:700;'
        self.model_action_btn.setText(text)
        self.model_action_btn.setStyleSheet(style)

    def model_action(self):
        selected = self.selected_alias()
        if not selected:
            return
        state = core.get_status()
        if state.get('llama') and state.get('alias') == selected:
            self.model_action_busy = True
            self.refresh_model_action_button()
            self.confirm_action('Остановить текущий llama-server?', lambda: core.stop('llama'), after=self.finish_model_action)
            return
        if state.get('llama') and state.get('alias') and state.get('alias') != selected:
            def task():
                msg = core.stop('llama')
                if core.verified('llama') or core.port_open(8080):
                    raise RuntimeError('Сервер всё ещё работает — переключение отменено. ' + msg)
                return msg + '\n' + core.start_model(selected)
            self.model_action_busy = True
            self.refresh_model_action_button()
            self.confirm_action(f"Остановить {state.get('alias')} и запустить {selected}?", task, after=self.finish_model_action)
            return
        if state.get('llama_external'):
            QMessageBox.warning(self, 'Внешний сервер', 'На порту 8080 запущен неуправляемый сервер. AI Lab не останавливает его автоматически.')
            return
        self.model_action_busy = True
        self.refresh_model_action_button()
        self.async_call('Загрузка ' + selected, lambda: core.start_model(selected), after=self.finish_model_action)

    def finish_model_action(self, ok, _text):
        self.model_action_busy = False
        self.refresh_status()

    # ---------- Services tab ----------
    def build_services(self):
        w = QWidget()
        l = QVBoxLayout(w)
        label = QLabel('Каждый сервис управляется отдельно. Порт 8080 не освобождается автоматически; сторонние процессы не завершаются.')
        label.setWordWrap(True)
        l.addWidget(label)
        self.service_labels = {}
        services = [
            ('llama', 'llama.cpp · модель', self.model_action, lambda: core.stop('llama'), None),
            ('webui', 'Open WebUI · :3000', core.webui_start, core.webui_stop, lambda: self.open_url('http://127.0.0.1:3000')),
            ('office', 'Agent Office', core.office_start, lambda: core.stop('office'), self.open_office),
            ('comfy', 'ComfyUI · :8188', core.comfy_start, lambda: core.stop('comfy'), lambda: self.open_url('http://127.0.0.1:8188')),
        ]
        for sid, name, start, stop, open_action in services:
            group = QGroupBox(name)
            row = QHBoxLayout(group)
            lab = QLabel('Проверяется…')
            self.service_labels[sid] = lab
            row.addWidget(lab, 1)
            if sid == 'llama':
                row.addWidget(btn('Старт / стоп выбранной модели', start, True))
            else:
                row.addWidget(btn('▶ Запустить', lambda s=start, n=name: self.async_call('Запуск ' + n, s), True))
            row.addWidget(btn('⏹ Остановить', lambda s=stop, n=name: self.confirm_action('Остановить ' + n + '?', s), danger=True))
            if open_action:
                row.addWidget(btn('Открыть', open_action))
            l.addWidget(group)
        l.addWidget(btn('⏹ ОСТАНОВИТЬ ВСЕ управляемые сервисы', self.stop_all, False, True))
        note = QLabel('«Все» = управляемые llama/Agent Office/ComfyUI и systemd-user Open WebUI. Pi и OpenCode не завершаются.')
        note.setWordWrap(True)
        l.addWidget(note)
        l.addStretch()
        return w

    def stop_all(self):
        def work():
            return '\n'.join((core.stop('llama'), core.stop('office'), core.stop('comfy'), core.webui_stop()))
        self.confirm_action('Остановить ВСЕ управляемые AI-сервисы?', work)

    # ---------- Tests tab ----------
    def build_tests(self):
        w = QWidget()
        l = QVBoxLayout(w)
        options = QGroupBox('Встроенные бенчмарки (файлы и отчёты внутри AI Model Lab)')
        form = QGridLayout(options)
        form.addWidget(QLabel('Испытание'), 0, 0)
        self.test_kind = QComboBox()
        for key, name in [
            ('speed', 'Скорость API — до 256 токенов'), ('speed512', 'Скорость API — до 512 токенов'),
            ('qa', 'Логика / арифметика (3 задачи)'), ('context8', 'Длинный контекст (около 8K)'),
            ('context32', 'Длинный контекст (около 32K)'), ('p1', 'Android LP-P1: STB UI → VOD'),
            ('p2', 'Android LP-P2: выбор плеера')
        ]:
            self.test_kind.addItem(name, key)
        form.addWidget(self.test_kind, 0, 1, 1, 3)
        form.addWidget(QLabel('Android-проект'), 1, 0)
        self.project = QLineEdit(self.settings_data.get('android_project', ''))
        form.addWidget(self.project, 1, 1, 1, 2)
        form.addWidget(btn('Обзор', self.browse_project), 1, 3)
        form.addWidget(QLabel('Лимит времени, с'), 2, 0)
        self.timeout = QSpinBox()
        self.timeout.setRange(30, 7200)
        self.timeout.setValue(int(self.settings_data.get('benchmark_timeout', 1800)))
        form.addWidget(self.timeout, 2, 1)
        form.addWidget(QLabel('Лимит инструментов Pi'), 2, 2)
        self.budget = QSpinBox()
        self.budget.setRange(1, 200)
        self.budget.setValue(int(self.settings_data.get('tool_budget', 24)))
        form.addWidget(self.budget, 2, 3)
        row = QHBoxLayout()
        self.run_btn = btn('▶ Запустить испытание', self.launch_test, True)
        row.addWidget(self.run_btn)
        self.cancel_btn = btn('⏹ Прервать испытание', self.cancel_test, False, True)
        self.cancel_btn.setEnabled(False)
        row.addWidget(self.cancel_btn)
        row.addWidget(btn('📁 Папка отчётов', lambda: self.open_url(core.REPORTS.as_uri())))
        l.addWidget(options)
        l.addLayout(row)
        warn = QLabel('⚠ Android: Pi получает только инструменты чтения, но это НЕ файловая песочница. Не запускай на секретных репозиториях без отдельной изоляции.')
        warn.setWordWrap(True)
        l.addWidget(warn)
        self.test_output = QTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setPlaceholderText('Здесь будет вывод теста, результаты записываются в папку data/reports/')
        l.addWidget(self.test_output, 1)
        return w

    def browse_project(self):
        chosen = QFileDialog.getExistingDirectory(self, 'Выбрать Android-проект', self.project.text() or str(Path.home()))
        if chosen:
            self.project.setText(chosen)

    def launch_test(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            return
        current = core.get_status()
        alias = current.get('alias')
        if not alias:
            QMessageBox.warning(self, 'Нет модели', 'Сначала запусти llama-server с нужной моделью.')
            return
        kind = self.test_kind.currentData()
        actual = 'speed' if kind.startswith('speed') else ('context' if kind.startswith('context') else kind)
        if actual in ('p1', 'p2'):
            try:
                core.preflight_android()
            except Exception as exc:
                QMessageBox.warning(self, 'Проверка контекста', str(exc))
                return
            if not Path(self.project.text()).is_dir():
                QMessageBox.warning(self, 'Android-проект', 'Выбери существующий каталог.')
                return
            if QMessageBox.question(self, 'Доступ Pi', 'Испытание читает Android-проект через Pi read/grep/find/ls.\nЭто НЕ ОС-песочница. Продолжить?') != QMessageBox.StandardButton.Yes:
                return
        args = [
            str(core.ROOT / 'bench.py'), '--kind', actual, '--model', alias, '--timeout', str(self.timeout.value()),
            '--budget', str(self.budget.value()), '--project', self.project.text(),
            '--output-tokens', str(512 if kind == 'speed512' else 256),
            '--target-tokens', str(32768 if kind == 'context32' else 8192)
        ]
        self.test_output.append('▶ Тест ' + kind + ' · ' + alias)
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(core.ROOT))
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.test_pipe)
        self.proc.finished.connect(self.test_finished)
        self.proc.start(sys.executable, args)
        if not self.proc.waitForStarted(2500):
            self.test_output.append('Не удалось запустить benchmark runner.')
            return
        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.tabs.setCurrentIndex(2)

    def test_pipe(self):
        if self.proc:
            raw = bytes(self.proc.readAllStandardOutput()).decode('utf-8', 'replace')
            self.test_output.moveCursor(QTextCursor.MoveOperation.End)
            self.test_output.insertPlainText(raw)
            self.test_output.ensureCursorVisible()

    def test_finished(self, exit_code, exit_status):
        self.test_pipe()
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.test_output.append(f'\nПроцесс завершился: exit={exit_code}')
        self.refresh_reports()

    def cancel_test(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            if QMessageBox.question(self, 'Прервать тест', 'Прервать текущий эксперимент? Успевшие записаться события сохранятся.') == QMessageBox.StandardButton.Yes:
                self.proc.terminate()

    # ---------- Reports tab ----------
    def build_results(self):
        w = QWidget()
        l = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(btn('↻ Обновить отчёты', self.refresh_reports))
        row.addWidget(btn('🔎 Сравнить два выбранных', self.compare_reports))
        row.addStretch()
        l.addLayout(row)
        self.reports = QTableWidget(0, 6)
        self.reports.setHorizontalHeaderLabels(['Дата/папка', 'Модель', 'Тест', 'Статус', 'Время, с', 'VRAM, MiB'])
        self.reports.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.reports.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.reports.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.reports.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        l.addWidget(self.reports, 1)
        row2 = QHBoxLayout()
        row2.addWidget(btn('Показать summary.json', self.show_report))
        row2.addWidget(btn('Открыть папку отчёта', self.open_report_dir))
        row2.addStretch()
        l.addLayout(row2)
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        self.report_text.setMinimumHeight(130)
        l.addWidget(self.report_text, 1)
        return w

    def selected_reports(self):
        indices = sorted({index.row() for index in self.reports.selectedIndexes()})
        files = []
        for i in indices:
            item = self.reports.item(i, 0)
            if item:
                files.append(Path(item.data(Qt.ItemDataRole.UserRole)))
        return files

    def refresh_reports(self):
        if not hasattr(self, 'reports'):
            return
        roots = sorted(core.REPORTS.glob('*/summary.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
        self.reports.setRowCount(len(roots))
        if hasattr(self, 'graph_speed'):
            self.graph_speed.samples.clear()
            for path in reversed(roots):
                historical = core.load_json(path, {}) or {}
                if historical.get('kind') != 'speed':
                    continue
                cases = (historical.get('result') or {}).get('cases') or []
                if cases and isinstance(cases[0].get('tokens_per_wall_s'), (int, float)):
                    self.graph_speed.add(cases[0]['tokens_per_wall_s'])
        for i, path in enumerate(roots):
            info = core.load_json(path, {}) or {}
            result = info.get('result') or {}
            hw = info.get('hardware') or {}
            values = [path.parent.name, info.get('model'), info.get('kind'), result.get('status'), info.get('elapsed_s'), (hw.get('vram_mib') or {}).get('max')]
            for j, value in enumerate(values):
                self.reports.setItem(i, j, cell(value))
            self.reports.item(i, 0).setData(Qt.ItemDataRole.UserRole, str(path))

    def show_report(self):
        files = self.selected_reports()
        if not files:
            return
        self.report_text.setPlainText(files[0].read_text(encoding='utf-8'))

    def open_report_dir(self):
        files = self.selected_reports()
        if files:
            self.open_url(files[0].parent.as_uri())

    def compare_reports(self):
        files = self.selected_reports()
        if len(files) != 2:
            QMessageBox.information(self, 'Сравнение', 'Выбери ровно два отчёта (Ctrl + щелчок).')
            return
        a, b = (core.load_json(p, {}) for p in files)
        ra = a.get('result', {})
        rb = b.get('result', {})
        equal = ra.get('prompt_sha256') and ra.get('prompt_sha256') == rb.get('prompt_sha256')
        kind_ok = a.get('kind') == b.get('kind')
        self.report_text.setPlainText(
            'СРАВНЕНИЕ\n\n' + '\n'.join(f"{k}: {a.get(k)} | {b.get(k)}" for k in ('model', 'kind', 'elapsed_s')) +
            f"\n\nStatus: {ra.get('status')} | {rb.get('status')}\n"
            f"VRAM peak: {(a.get('hardware', {}).get('vram_mib') or {}).get('max')} | {(b.get('hardware', {}).get('vram_mib') or {}).get('max')} MiB\n"
            f"Энергия: {a.get('hardware', {}).get('gpu_energy_wh_estimate')} | {b.get('hardware', {}).get('gpu_energy_wh_estimate')} Wh\n"
            f"\nСопоставимость по SHA256: {'ДА' if equal else 'НЕТ'}; тип задания: {'одинаковый' if kind_ok else 'РАЗНЫЙ'}\n"
            'Разная версия промпта или разные условия не дают сравнивать качество напрямую.'
        )

    # ---------- Settings tab ----------
    def build_settings(self):
        w = QWidget()
        l = QVBoxLayout(w)

        common = QGroupBox('Общие настройки программы')
        form = QFormLayout(common)
        self.set_inputs = {}
        fields = [
            ('android_project', 'Каталог Android-проекта'), ('office_dir', 'Каталог Agent Office'),
            ('office_url', 'URL Agent Office (необязательно)'), ('comfy_dir', 'Каталог ComfyUI'),
            ('webui_service', 'Служба WebUI'), ('gpu_index', 'Индекс GPU для nvidia-smi')
        ]
        for key, label in fields:
            v = QLineEdit(str(self.settings_data.get(key, '')))
            self.set_inputs[key] = v
            form.addRow(label, v)
        l.addWidget(common)

        split = QSplitter(Qt.Orientation.Horizontal)
        l.addWidget(split, 1)

        left = QWidget()
        lv = QVBoxLayout(left)
        model_bar = QHBoxLayout()
        model_bar.addWidget(btn('＋ Добавить', self.add_model, True))
        model_bar.addWidget(btn('－ Удалить', self.delete_model, danger=True))
        model_bar.addStretch()
        lv.addLayout(model_bar)
        self.settings_tree = QTreeWidget()
        self.settings_tree.setColumnCount(2)
        self.settings_tree.setHeaderLabels(['ID', 'Название'])
        self.settings_tree.itemSelectionChanged.connect(self.load_selected_editor_model)
        lv.addWidget(self.settings_tree, 1)
        split.addWidget(left)

        editor_wrap = QWidget()
        ev = QVBoxLayout(editor_wrap)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.editor_layout = QFormLayout(scroll_content)
        self.edit_fields = {}
        self.build_model_editor_form()
        scroll.setWidget(scroll_content)
        ev.addWidget(scroll)
        save_row = QHBoxLayout()
        save_row.addWidget(btn('💾 Сохранить модель', self.save_current_model, True))
        save_row.addWidget(btn('💾 Сохранить всё (на диск)', self.save_all_settings))
        save_row.addStretch()
        ev.addLayout(save_row)
        split.addWidget(editor_wrap)
        split.setSizes([340, 780])

        hint = QLabel('Изменяются только файлы в каталоге AI Model Lab. Двойной щелчок по модели на вкладке «Модели» открывает редактирование профиля.')
        hint.setWordWrap(True)
        l.addWidget(hint)

        self.populate_settings_tree()
        if self.settings_tree.topLevelItemCount():
            self.settings_tree.setCurrentItem(self.settings_tree.topLevelItem(0))
        return w

    def build_model_editor_form(self):
        ef = self.edit_fields
        ef['id'] = QLineEdit()
        ef['name'] = QLineEdit()
        ef['purpose'] = QTextEdit()
        ef['purpose'].setMaximumHeight(70)
        ef['context'] = QSpinBox(); ef['context'].setRange(4096, 524288)
        ef['path'] = QLineEdit()
        ef['match'] = QLineEdit()
        ef['thinking_off'] = QCheckBox('Включать --chat-template-kwargs enable_thinking=false')
        ef['n_cpu_moe'] = QSpinBox(); ef['n_cpu_moe'].setRange(0, 128); ef['n_cpu_moe'].setSpecialValueText('не задан')
        ef['mmproj'] = QLineEdit()
        ef['image_min_tokens'] = QSpinBox(); ef['image_min_tokens'].setRange(0, 65535); ef['image_min_tokens'].setSpecialValueText('не задан')
        ef['temp'] = QDoubleSpinBox(); ef['temp'].setRange(0.0, 5.0); ef['temp'].setSingleStep(0.05)
        ef['top_p'] = QDoubleSpinBox(); ef['top_p'].setRange(0.0, 1.0); ef['top_p'].setSingleStep(0.05)
        ef['top_k'] = QSpinBox(); ef['top_k'].setRange(0, 1000)
        ef['min_p'] = QDoubleSpinBox(); ef['min_p'].setRange(0.0, 1.0); ef['min_p'].setSingleStep(0.01)
        ef['repeat_penalty'] = QDoubleSpinBox(); ef['repeat_penalty'].setRange(0.5, 5.0); ef['repeat_penalty'].setSingleStep(0.05)

        self.editor_layout.addRow('ID / alias', ef['id'])
        self.editor_layout.addRow('Название', ef['name'])
        self.editor_layout.addRow('Назначение', ef['purpose'])
        self.editor_layout.addRow('Контекст', ef['context'])
        self.editor_layout.addRow('Относительный путь GGUF', ef['path'])
        self.editor_layout.addRow('Шаблон поиска GGUF', ef['match'])
        self.editor_layout.addRow('', ef['thinking_off'])
        self.editor_layout.addRow('n_cpu_moe', ef['n_cpu_moe'])
        self.editor_layout.addRow('mmproj', ef['mmproj'])
        self.editor_layout.addRow('image_min_tokens', ef['image_min_tokens'])
        self.editor_layout.addRow('Sampling temp', ef['temp'])
        self.editor_layout.addRow('Sampling top_p', ef['top_p'])
        self.editor_layout.addRow('Sampling top_k', ef['top_k'])
        self.editor_layout.addRow('Sampling min_p', ef['min_p'])
        self.editor_layout.addRow('Sampling repeat_penalty', ef['repeat_penalty'])

    def populate_settings_tree(self):
        self.settings_tree.clear()
        for p in self.cfg.get('models', []):
            it = QTreeWidgetItem([p.get('id', ''), p.get('name', '')])
            it.setData(0, Qt.ItemDataRole.UserRole, p.get('id'))
            self.settings_tree.addTopLevelItem(it)
        self.settings_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.settings_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def load_selected_editor_model(self):
        items = self.settings_tree.selectedItems()
        if not items:
            return
        alias = items[0].data(0, Qt.ItemDataRole.UserRole)
        p = next((m for m in self.cfg.get('models', []) if m.get('id') == alias), None)
        if not p:
            return
        ef = self.edit_fields
        ef['id'].setText(p.get('id', ''))
        ef['name'].setText(p.get('name', ''))
        ef['purpose'].setPlainText(p.get('purpose', ''))
        ef['context'].setValue(int(p.get('context', 32768)))
        ef['path'].setText(p.get('path', ''))
        ef['match'].setText(p.get('match', ''))
        ef['thinking_off'].setChecked(bool(p.get('thinking_off', False)))
        ef['n_cpu_moe'].setValue(int(p.get('n_cpu_moe', 0) or 0))
        ef['mmproj'].setText(p.get('mmproj', ''))
        ef['image_min_tokens'].setValue(int(p.get('image_min_tokens', 0) or 0))
        sampling = p.get('sampling', {}) or {}
        ef['temp'].setValue(float(sampling.get('temp', 0.7)))
        ef['top_p'].setValue(float(sampling.get('top_p', 0.8)))
        ef['top_k'].setValue(int(sampling.get('top_k', 20)))
        ef['min_p'].setValue(float(sampling.get('min_p', 0.0)))
        ef['repeat_penalty'].setValue(float(sampling.get('repeat_penalty', 1.0)))

    def open_selected_in_editor(self, *_):
        alias = self.selected_alias()
        if not alias:
            return
        self.tabs.setCurrentIndex(4)
        for i in range(self.settings_tree.topLevelItemCount()):
            it = self.settings_tree.topLevelItem(i)
            if it.data(0, Qt.ItemDataRole.UserRole) == alias:
                self.settings_tree.setCurrentItem(it)
                self.settings_tree.scrollToItem(it)
                break

    def collect_editor_model(self):
        ef = self.edit_fields
        alias = ef['id'].text().strip()
        if not alias:
            raise ValueError('ID модели не может быть пустым')
        model = {
            'id': alias,
            'name': ef['name'].text().strip() or alias,
            'context': int(ef['context'].value()),
            'purpose': ef['purpose'].toPlainText().strip(),
        }
        if ef['path'].text().strip():
            model['path'] = ef['path'].text().strip()
        if ef['match'].text().strip():
            model['match'] = ef['match'].text().strip()
        if ef['thinking_off'].isChecked():
            model['thinking_off'] = True
        if ef['n_cpu_moe'].value() > 0:
            model['n_cpu_moe'] = int(ef['n_cpu_moe'].value())
        if ef['mmproj'].text().strip():
            model['mmproj'] = ef['mmproj'].text().strip()
        if ef['image_min_tokens'].value() > 0:
            model['image_min_tokens'] = int(ef['image_min_tokens'].value())
        sampling = {
            'temp': float(ef['temp'].value()),
            'top_p': float(ef['top_p'].value()),
            'top_k': int(ef['top_k'].value()),
            'min_p': float(ef['min_p'].value()),
            'repeat_penalty': float(ef['repeat_penalty'].value()),
        }
        model['sampling'] = sampling
        return model

    def save_current_model(self):
        items = self.settings_tree.selectedItems()
        if not items:
            QMessageBox.warning(self, 'Модель', 'Сначала выбери модель в списке слева.')
            return
        original_alias = items[0].data(0, Qt.ItemDataRole.UserRole)
        try:
            new_model = self.collect_editor_model()
            models = self.cfg.get('models', [])
            ids = [m['id'] for m in models if m['id'] != original_alias]
            if new_model['id'] in ids:
                raise ValueError('Модель с таким ID уже существует')
            for i, p in enumerate(models):
                if p['id'] == original_alias:
                    models[i] = new_model
                    break
            self.cfg['models'] = models
            self.populate_settings_tree()
            self.populate_model_tree()
            self.select_alias_in_trees(new_model['id'])
            self.on_model_selected()
            QMessageBox.information(self, 'Модель', 'Профиль обновлён в памяти. Нажми «Сохранить всё (на диск)», чтобы записать файл.')
        except Exception as exc:
            QMessageBox.warning(self, 'Ошибка модели', str(exc))

    def add_model(self):
        base = 'new-model'
        existing = {p['id'] for p in self.cfg.get('models', [])}
        alias = base
        idx = 1
        while alias in existing:
            idx += 1
            alias = f'{base}-{idx}'
        new_model = {
            'id': alias,
            'name': 'Новая модель',
            'context': 32768,
            'purpose': 'Заполни назначение модели',
            'path': '',
            'match': '*.gguf',
            'thinking_off': False,
            'sampling': {'temp': 0.7, 'top_p': 0.8, 'top_k': 20, 'min_p': 0.0, 'repeat_penalty': 1.0}
        }
        self.cfg.setdefault('models', []).append(new_model)
        self.populate_settings_tree()
        self.populate_model_tree()
        self.select_alias_in_trees(alias)
        self.tabs.setCurrentIndex(4)
        self.load_selected_editor_model()

    def delete_model(self):
        items = self.settings_tree.selectedItems()
        if not items:
            return
        alias = items[0].data(0, Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, 'Удаление', f'Удалить профиль {alias}?') != QMessageBox.StandardButton.Yes:
            return
        self.cfg['models'] = [m for m in self.cfg.get('models', []) if m.get('id') != alias]
        self.populate_settings_tree()
        self.populate_model_tree()
        if self.settings_tree.topLevelItemCount():
            self.settings_tree.setCurrentItem(self.settings_tree.topLevelItem(0))
        self.on_model_selected()

    def save_all_settings(self):
        try:
            old = core.load_json(core.SETTINGS, {}) or {}
            old.update({k: widget.text().strip() for k, widget in self.set_inputs.items()})
            core.atomic_json(core.SETTINGS, old)
            core.atomic_json(core.MODELS, self.cfg)
            self.settings_data = old
            QMessageBox.information(self, 'Настройки', 'Сохранено в каталоге приложения.')
        except Exception as exc:
            QMessageBox.warning(self, 'Ошибка сохранения', str(exc))

    def select_alias_in_trees(self, alias):
        for tree in (self.tree, self.settings_tree):
            for i in range(tree.topLevelItemCount()):
                it = tree.topLevelItem(i)
                if it.data(0, Qt.ItemDataRole.UserRole) == alias:
                    tree.setCurrentItem(it)
                    tree.scrollToItem(it)
                    break

    # ---------- Status / logs ----------
    def append_log(self, text):
        if hasattr(self, 'test_output'):
            self.test_output.append('\n' + text)

    def update_live_log(self):
        meta = core.verified('llama')
        path = None
        if meta and meta.get('log'):
            path = Path(meta['log'])
        else:
            logs = sorted(core.LOGS.glob('llama_*.log'), key=lambda p: p.stat().st_mtime, reverse=True)
            path = logs[0] if logs else None
        if not path or not path.is_file():
            self.live_logs.setPlainText('Нет журнала llama.cpp')
            return
        try:
            raw = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            return
        tail = '\n'.join(raw.splitlines()[-120:])
        if path != self.last_log_path or tail != self.last_log_text:
            self.live_logs.setPlainText(tail)
            self.live_logs.moveCursor(QTextCursor.MoveOperation.End)
            self.last_log_path = path
            self.last_log_text = tail

    def refresh_status(self):
        gpu = core.gpu_metrics()
        ram = core.ram_metrics()
        if gpu:
            self.graph_gpu.add(gpu.get('gpu'))
            self.graph_vram.maximum = max(22, float(gpu.get('vram_total', 22)) / 1024)
            self.graph_vram.add(gpu.get('vram', 0) / 1024)
        if ram:
            self.graph_ram.maximum = max(1, ram.get('ram_total', 64))
            self.graph_ram.add(ram.get('ram'))
        self.metrics_label.setText(
            f"🌡 {gpu.get('temp', '—')} °C · ⚡ {gpu.get('power', '—')} W\n"
            f"GPU: {gpu.get('gpu', '—')}% · VRAM: {round(gpu.get('vram', 0) / 1024, 2)} / {round(gpu.get('vram_total', 0) / 1024, 2)} GiB\n"
            f"RAM: {round(ram.get('ram', 0), 1)} / {round(ram.get('ram_total', 0), 1)} GiB · Swap {ram.get('swap', '—')} GiB"
        )
        state = core.get_status()
        names = {
            'llama': ('работает ' + state.get('alias', '')) if state['llama'] else ('внешний сервер' if state.get('llama_external') else 'остановлен'),
            'webui': 'работает' if state['webui'] else 'не отвечает',
            'office': 'запущен (AI Lab)' if state['office'] else 'не подтверждён',
            'comfy': 'работает' if state['comfy'] else 'не отвечает'
        }
        for sid, lab in self.service_labels.items():
            lab.setText(names.get(sid, '—'))
            active = (sid == 'llama' and state['llama']) or (sid == 'webui' and state['webui']) or (sid == 'office' and state['office']) or (sid == 'comfy' and state['comfy'])
            lab.setStyleSheet('color: #63d6ac;' if active else 'color: #e9b5a0;')
        self.setWindowTitle(f"AI Model Lab — KDE · {state.get('alias') or 'модель не выбрана'} · {state.get('ctx') or '?'} ctx")
        status_text = f"llama: {names['llama']}"
        if state.get('llama') and state.get('ctx'):
            status_text += f" · контекст {state.get('ctx')}"
        self.status_label.setText(status_text)
        self.refresh_model_action_button()
        self.update_live_log()

    def closeEvent(self, event):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, 'Активный тест', 'Сначала останови текущий тест — чтобы корректно записать отчёт.')
            event.ignore()
            return
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('AI Model Lab')
    app.setOrganizationName('AI Model Lab Local')
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
