#!/usr/bin/env python3
"""AI Model Lab KDE v3.2 — Qt6 frontend for standalone local AI laboratory."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from collections import deque

try:
    from PySide6.QtCore import Qt, QThread, Signal, QTimer, QProcess
    from PySide6.QtGui import QPainter, QColor, QPen, QFont, QDesktopServices, QTextCursor, QIcon, QAction, QBrush
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
        QHBoxLayout, QGridLayout, QTabWidget, QTreeWidget, QTreeWidgetItem, QGroupBox,
        QComboBox, QLineEdit, QSpinBox, QFileDialog, QMessageBox, QTextEdit, QSplitter,
        QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QAbstractItemView,
        QScrollArea, QCheckBox, QDoubleSpinBox, QSystemTrayIcon, QMenu, QDialog, QPlainTextEdit, QDialogButtonBox, QStyle
    )
    from PySide6.QtCore import QUrl
except ImportError:
    try:
        from PyQt6.QtCore import Qt, QThread, pyqtSignal as Signal, QTimer, QProcess, QUrl
        from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QDesktopServices, QTextCursor, QIcon, QAction, QBrush
        from PyQt6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
            QHBoxLayout, QGridLayout, QTabWidget, QTreeWidget, QTreeWidgetItem, QGroupBox,
            QComboBox, QLineEdit, QSpinBox, QFileDialog, QMessageBox, QTextEdit, QSplitter,
            QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QAbstractItemView,
            QScrollArea, QCheckBox, QDoubleSpinBox, QSystemTrayIcon, QMenu, QDialog, QPlainTextEdit, QDialogButtonBox, QStyle
        )
    except ImportError:
        print('Нужен Qt6 Python. В CachyOS: sudo pacman -S pyside6', file=sys.stderr)
        raise SystemExit(2)

import core
import multi

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
QTreeWidget,QTableWidget,QTextEdit,QPlainTextEdit,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {{ background:#141e2b;
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
        self.editor_loading = False
        self.editor_dirty = False
        self.editor_current_alias = None
        self._tree_loading = False
        self.exit_requested = False
        self.tray = None
        self.log_offsets = {}
        self.selected_log_alias = ''
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self.update_live_log)
        self.log_timer.start(1000)
        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.timeout.connect(self.auto_save_pending)
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

        self.setup_tray()
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

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        icon_file = core.ROOT / 'assets' / 'ai-model-lab.svg'
        icon = QIcon(str(icon_file))
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip('AI Model Lab — локальные ИИ-серверы')
        menu = QMenu(self)
        action_show = menu.addAction('Открыть AI Model Lab')
        action_show.triggered.connect(self.show_from_tray)
        menu.addAction('Тесты', lambda: self.show_tab_from_tray(2))
        menu.addAction('Управление', lambda: self.show_tab_from_tray(1))
        menu.addSeparator()
        quit_action = menu.addAction('Закрыть приложение (серверы оставить)')
        quit_action.triggered.connect(self.quit_from_tray)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_from_tray()

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_tab_from_tray(self, index):
        self.show_from_tray()
        self.tabs.setCurrentIndex(index)

    def quit_from_tray(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, 'Активный тест', 'Сначала останови тест, чтобы не потерять отчёт.')
            self.show_tab_from_tray(2)
            return
        self.exit_requested = True
        self.close()

    def choose_log(self):
        aliases = list(multi.all_states())
        selected = self.selected_alias()
        if selected:
            self.selected_log_alias = selected
        if self.selected_log_alias not in aliases and aliases:
            self.selected_log_alias = aliases[0]

    def open_full_log(self):
        self.choose_log()
        path = multi.log_path(self.selected_log_alias) if self.selected_log_alias else None
        if not path or not path.is_file():
            QMessageBox.information(self, 'Логи', 'Для выбранной модели журнала пока нет.')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f'Журнал {self.selected_log_alias} — {path.name}')
        dialog.resize(950, 680)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(str(path)))
        view = QPlainTextEdit()
        view.setReadOnly(True)
        size = path.stat().st_size
        with path.open('rb') as stream:
            if size > 2_000_000:
                stream.seek(-2_000_000, 2)
            content = stream.read().decode('utf-8', 'replace')
        view.setPlainText(('Показаны последние 2 МБ (файл больше 2 МБ).\n\n' if size > 2_000_000 else '') + content)
        view.moveCursor(QTextCursor.MoveOperation.End)
        layout.addWidget(view, 1)
        row = QHBoxLayout()
        row.addWidget(btn('Открыть файл внешним редактором', lambda: self.open_url(path.as_uri())))
        row.addWidget(btn('Закрыть', dialog.accept))
        layout.addLayout(row)
        dialog.exec()

    # ---------- Models tab ----------
    def build_models(self):
        w = QWidget(); l = QVBoxLayout(w)
        split = QSplitter(Qt.Orientation.Horizontal); l.addWidget(split, 1)
        left_wrap = QWidget(); left_layout = QVBoxLayout(left_wrap)
        left_layout.setContentsMargins(0, 0, 0, 0); left_layout.setSpacing(6)
        self.tree = QTreeWidget(); self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(['Модель', 'Статус', 'Контекст', 'Назначение'])
        self.tree.setRootIsDecorated(False)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tree.header().setStretchLastSection(False)
        for i, width in enumerate(self.settings_data.get('ui_columns', [250, 145, 100, 340])):
            if i < self.tree.columnCount():
                self.tree.setColumnWidth(i, max(65, int(width)))
        self.tree.header().setSectionsMovable(False)
        self.tree.header().sectionResized.connect(self.defer_column_save)
        self.tree.itemDoubleClicked.connect(self.open_selected_in_editor)
        self.tree.currentItemChanged.connect(self.on_model_selected)
        self.tree.setUniformRowHeights(True)
        left_layout.addWidget(self.tree, 3)
        self.status_label = QLabel('Статус: ожидание'); self.status_label.setObjectName('Subheader')
        self.status_label.setWordWrap(True); left_layout.addWidget(self.status_label)
        logs_group = QGroupBox('Живой журнал выбранной модели'); logs_layout = QVBoxLayout(logs_group)
        self.live_logs = QPlainTextEdit(); self.live_logs.setReadOnly(True)
        self.live_logs.setMaximumBlockCount(1000); self.live_logs.setMinimumHeight(120)
        logs_layout.addWidget(self.live_logs)
        log_buttons = QHBoxLayout()
        log_buttons.addWidget(btn('Открыть полный лог', self.open_full_log))
        log_buttons.addWidget(btn('Показать последнюю запись', self.reset_log_view))
        logs_layout.addLayout(log_buttons)
        left_layout.addWidget(logs_group, 2)
        split.addWidget(left_wrap)
        right = QWidget(); r = QVBoxLayout(right)
        box = QGroupBox('Выбранная модель'); f = QVBoxLayout(box)
        self.model_info = QPlainTextEdit(); self.model_info.setReadOnly(True)
        self.model_info.setMinimumHeight(200)
        f.addWidget(self.model_info, 1)
        self.model_action_btn = QPushButton('● Статус модели')
        self.model_action_btn.clicked.connect(self.model_action)
        f.addWidget(self.model_action_btn)
        f.addWidget(btn('✎ Редактировать параметры', self.open_selected_in_editor))
        f.addWidget(btn('🌐 Открыть WebUI', lambda: self.open_url('http://127.0.0.1:3000')))
        f.addWidget(btn('🏢 Открыть Agent Office', self.open_office))
        r.addWidget(box)
        hint = QLabel('Каждая модель: свой порт и GPU. Двойной щелчок → редактор.\nШирина колонок сохраняется автоматически.')
        hint.setWordWrap(True); r.addWidget(hint)
        split.addWidget(right); split.setSizes([650, 560])
        self.column_timer = QTimer(self); self.column_timer.setSingleShot(True)
        self.column_timer.timeout.connect(self.persist_columns)
        self.populate_model_tree()
        if self.tree.topLevelItemCount(): self.tree.setCurrentItem(self.tree.topLevelItem(0))
        return w

    def defer_column_save(self, *args):
        if hasattr(self, 'column_timer') and not self._tree_loading:
            self.column_timer.start(700)

    def persist_columns(self):
        settings = core.settings()
        settings['ui_columns'] = [self.tree.columnWidth(i) for i in range(self.tree.columnCount())]
        core.atomic_json(core.SETTINGS, settings)
        self.settings_data = settings

    def populate_model_tree(self):
        selected = self.selected_alias() if self.tree.topLevelItemCount() else None
        self._tree_loading = True
        self.tree.clear()
        for p in self.cfg.get('models', []):
            it = QTreeWidgetItem([p.get('name', p['id']), '—', f"{int(p['context']) // 1024}K", p.get('purpose', '—')])
            it.setData(0, Qt.ItemDataRole.UserRole, p['id'])
            self.tree.addTopLevelItem(it)
        self._tree_loading = False
        if selected: self.select_tree_alias(self.tree, selected)
        self.update_model_status_cells()

    def update_model_status_cells(self):
        palette = {'running': ('● Запущена', '#63d6ac'), 'starting': ('● Загрузка', '#ffc578'),
                   'error': ('● Ошибка', '#e58f9b'), 'external': ('● Порт занят', '#ffc578'), 'port_conflict': ('● Порт занят', '#ffc578'),
                   'stopped': ('● Остановлена', '#a1b4cf'), 'unstarted': ('○ Не запущена', '#91a4bc')}
        states = multi.all_states()
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            alias = it.data(0, Qt.ItemDataRole.UserRole)
            status, color = palette.get(states.get(alias, {}).get('state', 'unstarted'), ('○ Не запущена', '#91a4bc'))
            it.setText(1, status)
            it.setForeground(1, QBrush(QColor(color)))

    def on_model_selected(self, *_):
        p = self.selected_model_profile()
        if not p: return
        try: path = str(core.resolve_gguf(p)); presence = '✓ GGUF найден'
        except Exception as exc: path = str(exc); presence = '⚠ Проверить GGUF'
        state = multi.inspect(p['id'])
        self.model_info.setPlainText(
            f"{p['name']}\n\nНазначение: {p.get('purpose', '—')}\n"
            f"Alias: {p['id']}\nКонтекст: {int(p['context']):,} токенов\n"
            f"GPU: {p.get('gpu') or 'автоматически'} · порт API: {p.get('port', 8080)}\n"
            f"Статус: {state.get('state')}\n"
            f"KV: {p.get('cache_type_k','q8_0')} / {p.get('cache_type_v','q8_0')}\n\n"
            f"{presence}\n{path}")
        self.reset_log_view()
        self.refresh_model_action_button()

    def refresh_model_action_button(self):
        selected = self.selected_alias()
        if not selected: return
        state = multi.inspect(selected)
        status = state.get('state')
        if self.model_action_busy:
            text, style = '⏳ Выполняется операция…', 'background:#675225;border:1px solid #d0a13c;'
        elif status == 'running':
            text, style = '🟢 Запущена — остановить эту модель', 'background:#255b47;border:1px solid #56b790;'
        elif status == 'starting':
            text, style = '🟡 Модель загружается — остановить', 'background:#5a4a20;border:1px solid #d6b15b;'
        elif status in ('external','port_conflict'):
            owner = state.get('other_alias') or 'другим сервером'
            text, style = f'🟠 Порт занят ({owner}) — настроить', 'background:#5a3f20;border:1px solid #d18d4b;'
        elif status == 'error':
            text, style = '🔴 Ошибка — попробовать запустить снова', 'background:#63333b;border:1px solid #ae5364;'
        else:
            p = self.selected_model_profile()
            text, style = f"⚪ Запустить на GPU {p.get('gpu') or 'авто'} · :{p.get('port',8080)}", 'background:#245e9a;border:1px solid #438de1;'
        self.model_action_btn.setText(text)
        self.model_action_btn.setStyleSheet(style + 'font-weight:700;')

    def model_action(self):
        selected = self.selected_alias()
        if not selected or self.model_action_busy: return
        state = multi.inspect(selected)
        if state.get('state') in ('running', 'starting') and state.get('managed'):
            self.confirm_action(f'Остановить только {selected}?', lambda: multi.stop(selected), after=self.finish_model_action)
        elif state.get('state') in ('external','port_conflict'):
            QMessageBox.information(self, 'Порт занят', f"На порту {state.get('port')} работает другая модель или сервер. Откроется редактор — укажи свободный порт.")
            self.open_selected_in_editor()
        else:
            self.model_action_busy = True
            self.refresh_model_action_button()
            self.async_call('Загрузка ' + selected, lambda: multi.launch(selected), after=self.finish_model_action)

    def finish_model_action(self, ok, text):
        self.model_action_busy = False
        self.refresh_status()

    def reset_log_view(self):
        self.selected_log_alias = self.selected_alias() or ''
        self.live_logs.clear()
        self.log_offsets.pop(self.selected_log_alias, None)
        self.update_live_log()

    def build_services(self):
        w = QWidget(); l = QVBoxLayout(w)
        label = QLabel('Все llama.cpp запускаются независимо по портам/GPU. Остановка одного не затрагивает другие серверы.')
        label.setWordWrap(True); l.addWidget(label)
        self.instances_table = QTableWidget(0, 5)
        self.instances_table.setHorizontalHeaderLabels(['Модель','GPU','Порт','Статус','PID'])
        self.instances_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.instances_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.instances_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        l.addWidget(self.instances_table, 1)
        row = QHBoxLayout()
        row.addWidget(btn('▶ Запустить модель на вкладке «Модели»', lambda: self.tabs.setCurrentIndex(0)))
        row.addWidget(btn('⏹ Остановить выбранный экземпляр', self.stop_selected_instance, danger=True))
        row.addWidget(btn('⏹ Остановить все llama.cpp', self.stop_all_llama, danger=True))
        l.addLayout(row)
        self.service_labels = {}
        services = [
            ('webui', 'Open WebUI · :3000', core.webui_start, core.webui_stop, lambda: self.open_url('http://127.0.0.1:3000')),
            ('office', 'Agent Office', core.office_start, lambda: core.stop('office'), self.open_office),
            ('comfy', 'ComfyUI · :8188', core.comfy_start, lambda: core.stop('comfy'), lambda: self.open_url('http://127.0.0.1:8188')),
        ]
        for sid, name, start, stop, open_action in services:
            group = QGroupBox(name); item = QHBoxLayout(group)
            lab = QLabel('Проверяется…'); self.service_labels[sid] = lab
            item.addWidget(lab, 1)
            item.addWidget(btn('▶ Запустить', lambda s=start,n=name: self.async_call('Запуск '+n,s), True))
            item.addWidget(btn('⏹ Остановить', lambda s=stop,n=name: self.confirm_action('Остановить '+n+'?',s), danger=True))
            item.addWidget(btn('Открыть',open_action))
            l.addWidget(group)
        l.addWidget(btn('⏹ Остановить ВСЕ управляемые AI-сервисы', self.stop_all, danger=True))
        return w

    def update_instances_table(self):
        current = self.instances_table.currentRow()
        states = multi.all_states()
        items = list(states.items())
        self.instances_table.setRowCount(len(items))
        for i,(alias,s) in enumerate(items):
            p = self.profile_lookup(alias) or {}
            fields = [alias, p.get('gpu') or s.get('gpu') or 'авто', s.get('port',p.get('port',8080)),s.get('state'),s.get('pid','—') if s.get('managed') else '—']
            for j,value in enumerate(fields): self.instances_table.setItem(i,j,cell(value))
        if 0 <= current < self.instances_table.rowCount(): self.instances_table.selectRow(current)

    def stop_selected_instance(self):
        row = self.instances_table.currentRow()
        item = self.instances_table.item(row, 0) if row >= 0 else None
        if not item: return
        alias = item.text()
        self.confirm_action(f'Остановить только {alias}?', lambda: multi.stop(alias))

    def stop_all_llama(self):
        self.confirm_action('Остановить все llama-server, запущенные AI Lab?', multi.stop_all)

    def stop_all(self):
        def work():
            return '\n'.join((multi.stop_all(), core.stop('office'), core.stop('comfy'), core.webui_stop()))
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
        form.addWidget(QLabel('Экземпляр модели'), 1, 0)
        self.test_instance = QComboBox()
        form.addWidget(self.test_instance, 1, 1, 1, 3)
        form.addWidget(QLabel('Android-проект'), 2, 0)
        self.project = QLineEdit(self.settings_data.get('android_project', ''))
        form.addWidget(self.project, 2, 1, 1, 2)
        form.addWidget(btn('Обзор', self.browse_project), 2, 3)
        form.addWidget(QLabel('Лимит времени, с'), 3, 0)
        self.timeout = QSpinBox()
        self.timeout.setRange(30, 7200)
        self.timeout.setValue(int(self.settings_data.get('benchmark_timeout', 1800)))
        form.addWidget(self.timeout, 3, 1)
        form.addWidget(QLabel('Лимит инструментов Pi'), 3, 2)
        self.budget = QSpinBox()
        self.budget.setRange(1, 200)
        self.budget.setValue(int(self.settings_data.get('tool_budget', 24)))
        form.addWidget(self.budget, 3, 3)
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

    def refresh_test_instances(self):
        previous = self.test_instance.currentData() if self.test_instance.count() else None
        self.test_instance.clear()
        for alias, state in multi.active_instances().items():
            if state.get('state') == 'running':
                self.test_instance.addItem(f"{alias} · GPU {state.get('gpu') or 'авто'} · :{state.get('port')}", (alias, state['port']))
        if previous:
            for i in range(self.test_instance.count()):
                if self.test_instance.itemData(i) == previous:
                    self.test_instance.setCurrentIndex(i)
                    break

    def launch_test(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            return
        selection = self.test_instance.currentData()
        alias, port = selection if selection else (None, None)
        if not alias:
            QMessageBox.warning(self, 'Нет модели', 'Сначала запусти llama-server с нужной моделью.')
            return
        kind = self.test_kind.currentData()
        actual = 'speed' if kind.startswith('speed') else ('context' if kind.startswith('context') else kind)
        if actual in ('p1', 'p2'):
            try:
                if port != 8080:
                    raise RuntimeError('Android Pi local-lab сейчас настроен на порт 8080. API-тесты доступны на любом порту, Android — только на 8080 до изменения Pi provider.')
                core.preflight_android()
            except Exception as exc:
                QMessageBox.warning(self, 'Проверка контекста', str(exc))
                return
            if not Path(self.project.text()).is_dir():
                QMessageBox.warning(self, 'Android-проект', 'Выбери существующий каталог.')
                return
            if QMessageBox.question(self, 'Доступ Pi', 'Испытание читает Android-проект через Pi read/grep/find/ls.\nЭто НЕ ОС-песочница. Продолжить?') != QMessageBox.StandardButton.Yes:
                return
        profile = self.profile_lookup(alias) or {}
        args = [
            str(core.ROOT / 'bench.py'), '--kind', actual, '--model', alias, '--port', str(port), '--gpu', str(profile.get('gpu','')), '--timeout', str(self.timeout.value()),
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
    # ---------- Profile editor ----------
    def profile_lookup(self, alias):
        return next((p for p in self.cfg.get('models',[]) if p.get('id') == alias), None)

    def build_settings(self):
        w=QWidget(); l=QVBoxLayout(w)
        common=QGroupBox('Общие настройки программы'); f=QFormLayout(common)
        self.set_inputs={}
        for key,label in [('android_project','Каталог Android-проекта'),('office_dir','Каталог Agent Office'),
                          ('office_url','URL Agent Office'),('comfy_dir','Каталог ComfyUI'),
                          ('webui_service','Служба WebUI'),('gpu_index','GPU для графика nvidia-smi')]:
            inp=QLineEdit(str(self.settings_data.get(key,''))); self.set_inputs[key]=inp; f.addRow(label,inp)
        l.addWidget(common)
        split=QSplitter(Qt.Orientation.Horizontal); l.addWidget(split,1)
        left=QWidget(); lv=QVBoxLayout(left)
        controls=QHBoxLayout()
        controls.addWidget(btn('＋ Добавить',self.add_model,True))
        controls.addWidget(btn('⧉ Клонировать',self.clone_model))
        controls.addWidget(btn('－ Удалить',self.delete_model,danger=True))
        lv.addLayout(controls)
        self.settings_tree=QTreeWidget(); self.settings_tree.setColumnCount(2)
        self.settings_tree.setHeaderLabels(['ID','Название'])
        self.settings_tree.itemSelectionChanged.connect(self.load_selected_editor_model)
        lv.addWidget(self.settings_tree,1); split.addWidget(left)
        right=QWidget(); rv=QVBoxLayout(right)
        self.editor_tabs=QTabWidget(); self.edit_fields={}
        self.build_model_editor_form()
        rv.addWidget(self.editor_tabs,1)
        sr=QHBoxLayout()
        self.autosave_checkbox=QCheckBox('Автосохранение профиля')
        self.autosave_checkbox.setChecked(bool(self.settings_data.get('autosave_profiles',False)))
        self.autosave_checkbox.stateChanged.connect(self.toggle_autosave)
        sr.addWidget(self.autosave_checkbox)
        sr.addWidget(btn('💾 Сохранить профиль',self.save_current_model,True))
        sr.addWidget(btn('💾 Сохранить настройки программы',self.save_all_settings))
        rv.addLayout(sr)
        self.editor_hint=QLabel('Изменения профиля не сохранены' )
        self.editor_hint.setObjectName('Subheader'); rv.addWidget(self.editor_hint)
        split.addWidget(right); split.setSizes([360,840])
        note=QLabel('Сохранение не переписывает ~/.pi/agent/models.json. Для Android Pi проверь отдельно contextWindow, maxTokens и API-адрес.')
        note.setWordWrap(True); l.addWidget(note)
        self.populate_settings_tree()
        if self.settings_tree.topLevelItemCount():
            self.settings_tree.setCurrentItem(self.settings_tree.topLevelItem(0))
        return w

    def editor_scroll_tab(self, name, widget):
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(widget)
        self.editor_tabs.addTab(scroll,name)

    def build_model_editor_form(self):
        ef=self.edit_fields
        def text(key): ef[key]=QLineEdit(); return ef[key]
        def spin(key,lo,hi,default):
            ef[key]=QSpinBox(); ef[key].setRange(lo,hi); ef[key].setValue(default); return ef[key]
        def dbl(key,lo,hi,default):
            ef[key]=QDoubleSpinBox(); ef[key].setDecimals(3); ef[key].setRange(lo,hi); ef[key].setValue(default); return ef[key]
        def check(key,label): ef[key]=QCheckBox(label); return ef[key]
        def combo(key,items): ef[key]=QComboBox(); ef[key].addItems(items); return ef[key]

        basic=QWidget(); f=QFormLayout(basic)
        f.addRow('ID / alias',text('id')); f.addRow('Название',text('name'))
        ef['purpose']=QPlainTextEdit(); ef['purpose'].setMaximumHeight(90); f.addRow('Назначение',ef['purpose'])
        f.addRow('Контекст (токены)',spin('context',4096,524288,32768))
        f.addRow('Порт API',spin('port',1024,65535,8080))
        f.addRow('GPU (0, 1 или UUID)',text('gpu'))
        self.gpu_info=QLabel('\n'.join(multi.available_gpu_ids()) or 'GPU не обнаружены через nvidia-smi')
        self.gpu_info.setWordWrap(True); f.addRow('Найденные GPU',self.gpu_info)
        f.addRow('Путь GGUF (относительный)',text('path'))
        f.addRow('Шаблон GGUF',text('match'))
        f.addRow('Доп. аргументы llama.cpp',text('extra_args'))
        self.editor_scroll_tab('Основные',basic)

        sampling=QWidget(); f=QFormLayout(sampling)
        for key,label,lo,hi,default in [
            ('temp','Temperature',0,5,.7),('top_p','Top P',0,1,.8),('min_p','Min P',0,1,0),
            ('repeat_penalty','Repeat penalty',.5,5,1)]: f.addRow(label,dbl(key,lo,hi,default))
        f.addRow('Top K',spin('top_k',0,1000,20))
        self.editor_scroll_tab('Sampling',sampling)

        memory=QWidget(); f=QFormLayout(memory)
        f.addRow('GPU layers (-ngl)',spin('ngl',0,999,99))
        f.addRow('CPU MoE layers',spin('n_cpu_moe',0,128,0))
        f.addRow('Parallel slots (-np)',spin('parallel',1,64,1))
        f.addRow('Batch (-b)',spin('batch',1,65536,1024))
        f.addRow('Micro batch (-ub)',spin('ubatch',1,65536,256))
        f.addRow('',check('flash_attn','Flash Attention (-fa on)'))
        f.addRow('',check('no_kv_offload','KV cache в RAM (--no-kv-offload)'))
        cache_options=['q8_0','f16','q4_0','q4_1','q5_0','q5_1','iq4_nl']
        f.addRow('KV K',combo('cache_type_k',cache_options))
        f.addRow('KV V',combo('cache_type_v',cache_options))
        self.editor_scroll_tab('Память / KV',memory)

        multi_tab=QWidget(); f=QFormLayout(multi_tab)
        f.addRow('MMProj GGUF',text('mmproj'))
        f.addRow('Image min tokens',spin('image_min_tokens',0,65535,0))
        f.addRow('',check('thinking_off','Отключить thinking (если поддерживается)'))
        f.addRow('',check('jinja','Использовать --jinja'))
        f.addRow('',check('reasoning_off','Использовать --reasoning off'))
        self.editor_scroll_tab('Мультимодальность',multi_tab)

        for widget in ef.values():
            if isinstance(widget,(QLineEdit, QPlainTextEdit)):
                widget.textChanged.connect(self.mark_editor_dirty)
            elif isinstance(widget,(QSpinBox,QDoubleSpinBox)):
                widget.valueChanged.connect(self.mark_editor_dirty)
            elif isinstance(widget,QComboBox):
                widget.currentIndexChanged.connect(self.mark_editor_dirty)
            elif isinstance(widget,QCheckBox):
                widget.stateChanged.connect(self.mark_editor_dirty)

    def populate_settings_tree(self):
        self.settings_tree.clear()
        for p in self.cfg.get('models',[]):
            it=QTreeWidgetItem([p['id'],p.get('name',p['id'])]); it.setData(0,Qt.ItemDataRole.UserRole,p['id'])
            self.settings_tree.addTopLevelItem(it)
        self.settings_tree.header().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.settings_tree.header().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)

    def load_selected_editor_model(self):
        if self.editor_loading: return
        items=self.settings_tree.selectedItems()
        if not items: return
        alias=items[0].data(0,Qt.ItemDataRole.UserRole)
        if self.editor_dirty and self.editor_current_alias and alias!=self.editor_current_alias:
            if not self.confirm_discard_or_save():
                self.editor_loading=True
                self.select_tree_alias(self.settings_tree,self.editor_current_alias)
                self.editor_loading=False
                return
        profile=self.profile_lookup(alias)
        if not profile: return
        self.editor_loading=True
        try:
            ef=self.edit_fields
            def set_line(k,value): ef[k].setText(str(value or ''))
            for k in ('id','name','path','match','gpu','mmproj'):
                set_line(k,profile.get(k,''))
            ef['purpose'].setPlainText(profile.get('purpose',''))
            for key,default in [('context',32768),('port',8080),('ngl',99),('n_cpu_moe',0),('parallel',1),
                                ('batch',1024),('ubatch',256),('image_min_tokens',0)]:
                ef[key].setValue(int(profile.get(key,default) or default) if key not in ('n_cpu_moe','image_min_tokens') else int(profile.get(key,0) or 0))
            sampling=profile.get('sampling',{}) or {}
            for key,default in [('temp',.7),('top_p',.8),('top_k',20),('min_p',0),('repeat_penalty',1)]:
                ef[key].setValue(sampling.get(key,default))
            for key,default in [('flash_attn',True),('no_kv_offload',True),('thinking_off',False),('jinja',True),('reasoning_off',True)]:
                ef[key].setChecked(bool(profile.get(key,default)))
            for key in ('cache_type_k','cache_type_v'):
                idx=ef[key].findText(profile.get(key,'q8_0'))
                ef[key].setCurrentIndex(idx if idx>=0 else 0)
            extra=profile.get('extra_args',[])
            set_line('extra_args', extra if isinstance(extra,str) else ' '.join(extra))
            self.editor_current_alias=alias
            self.editor_dirty=False
            self.editor_hint.setText('Профиль загружен · настройки сохранены только после кнопки')
        finally:
            self.editor_loading=False

    def mark_editor_dirty(self,*_):
        if self.editor_loading or not self.editor_current_alias: return
        self.editor_dirty=True
        self.editor_hint.setText('● Есть несохранённые изменения')
        if self.autosave_checkbox.isChecked(): self.auto_timer.start(800)

    def toggle_autosave(self,*_):
        settings=core.settings(); settings['autosave_profiles']=self.autosave_checkbox.isChecked()
        core.atomic_json(core.SETTINGS,settings); self.settings_data=settings
        if self.autosave_checkbox.isChecked() and self.editor_dirty: self.auto_timer.start(800)

    def auto_save_pending(self):
        if self.editor_dirty and self.autosave_checkbox.isChecked(): self.save_current_model(silent=True)

    def confirm_discard_or_save(self):
        dialog=QMessageBox(self)
        dialog.setWindowTitle('Несохранённый профиль')
        dialog.setText('Сохранить изменения перед переключением модели?')
        yes=dialog.addButton('Сохранить',QMessageBox.ButtonRole.AcceptRole)
        no=dialog.addButton('Не сохранять',QMessageBox.ButtonRole.DestructiveRole)
        cancel=dialog.addButton('Отмена',QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton()==yes: return self.save_current_model(silent=True)
        if dialog.clickedButton()==no: self.editor_dirty=False;return True
        return False

    def collect_editor_model(self):
        ef=self.edit_fields
        alias=multi.validate_alias(ef['id'].text().strip())
        original=self.profile_lookup(self.editor_current_alias) or {}
        profile=dict(original)
        for k in ('name','path','match','gpu','mmproj','purpose','extra_args'):
            value=ef[k].toPlainText().strip() if k=='purpose' else ef[k].text().strip()
            profile[k]=value
        profile['id']=alias
        for k in ('context','port','ngl','n_cpu_moe','parallel','batch','ubatch','image_min_tokens'):
            profile[k]=int(ef[k].value())
        for k in ('flash_attn','no_kv_offload','thinking_off','jinja','reasoning_off'):
            profile[k]=ef[k].isChecked()
        for k in ('cache_type_k','cache_type_v'): profile[k]=ef[k].currentText()
        profile['sampling']={k:ef[k].value() for k in ('temp','top_p','top_k','min_p','repeat_penalty')}
        # Validate, but don't require file existence during editing/import.
        multi.port_of(profile); multi.gpu_of(profile)
        if not profile['path'] and not profile['match']:
            raise ValueError('Укажи путь к GGUF или шаблон для поиска')
        if profile['ubatch']>profile['batch']:
            raise ValueError('Micro batch не может быть больше batch')
        return profile

    def persist_profiles(self):
        """Back up previous models.json in the same app folder before every edit."""
        import datetime as dt
        import shutil
        backups=core.DATA/'backups'
        backups.mkdir(parents=True,exist_ok=True)
        if core.MODELS.is_file():
            stamp=dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            dest=backups/f'models_{stamp}.json'
            shutil.copy2(core.MODELS,dest)
            dest.chmod(0o600)
        core.atomic_json(core.MODELS,self.cfg)
        previous=sorted(backups.glob('models_*.json'))
        for old in previous[:-20]: old.unlink(missing_ok=True)

    def save_current_model(self, silent=False):
        alias=self.editor_current_alias
        if not alias: return False
        try:
            updated=self.collect_editor_model()
            if updated['id']!=alias and multi.inspect(alias).get('managed'):
                raise ValueError('Нельзя менять alias работающей модели — сначала останови её')
            if any(p['id']==updated['id'] and p['id']!=alias for p in self.cfg.get('models',[])):
                raise ValueError('Этот ID уже используется')
            new_models=[updated if p['id']==alias else p for p in self.cfg.get('models',[])]
            if len(new_models)!=len(self.cfg.get('models',[])):
                raise ValueError('Исходный профиль не найден')
            obj={**self.cfg,'models':new_models}
            self.cfg=obj
            self.persist_profiles()
            self.editor_dirty=False;self.editor_current_alias=updated['id']
            self.populate_settings_tree();self.populate_model_tree()
            self.select_alias_in_trees(updated['id'])
            self.editor_hint.setText('✓ Профиль сохранён в models.json')
            if not silent: QMessageBox.information(self,'Профиль','Изменения сохранены. Для уже запущенной модели применятся после перезапуска.')
            return True
        except Exception as exc:
            QMessageBox.warning(self,'Ошибка профиля',str(exc))
            return False

    def next_port(self):
        used={int(p.get('port',8080)) for p in self.cfg.get('models',[])}
        for port in range(8081,8400):
            if port not in used and not core.port_open(port): return port
        raise RuntimeError('Нет свободного порта для нового профиля')

    def unique_alias(self,base):
        ids={p['id'] for p in self.cfg.get('models',[])}
        name=base;idx=2
        while name in ids:
            name=f'{base}-{idx}';idx+=1
        return name

    def add_model(self):
        if self.editor_dirty and not self.confirm_discard_or_save(): return
        alias=self.unique_alias('new-model')
        profile={'id':alias,'name':'Новая модель','purpose':'Укажи назначение','context':32768,
                 'port':self.next_port(),'gpu':'','path':'','match':'*.gguf',
                 'sampling':{'temp':.7,'top_p':.8,'top_k':20,'min_p':0,'repeat_penalty':1}}
        self.cfg['models'].append(profile)
        self.persist_profiles()
        self.populate_settings_tree();self.populate_model_tree()
        self.select_alias_in_trees(alias)
        self.tabs.setCurrentIndex(4)

    def clone_model(self):
        if self.editor_dirty and not self.confirm_discard_or_save(): return
        items=self.settings_tree.selectedItems()
        if not items:return
        original=self.profile_lookup(items[0].data(0,Qt.ItemDataRole.UserRole))
        if not original:return
        clone=json.loads(json.dumps(original))
        clone['id']=self.unique_alias(original['id']+'-copy')
        clone['name']=original.get('name',original['id'])+' (копия)'
        clone['port']=self.next_port()
        self.cfg['models'].append(clone)
        self.persist_profiles()
        self.populate_settings_tree();self.populate_model_tree()
        self.select_alias_in_trees(clone['id'])
        self.tabs.setCurrentIndex(4)
        QMessageBox.information(self,'Копия модели',f"Создан {clone['id']} на порту {clone['port']}.\nПроверь GPU: сейчас он скопирован из исходного профиля.")

    def delete_model(self):
        items=self.settings_tree.selectedItems()
        if not items:return
        alias=items[0].data(0,Qt.ItemDataRole.UserRole)
        def actual_delete():
            self.cfg['models']=[p for p in self.cfg.get('models',[]) if p.get('id')!=alias]
            self.persist_profiles()
            self.editor_dirty=False;self.editor_current_alias=None
            self.populate_settings_tree();self.populate_model_tree()
            if self.settings_tree.topLevelItemCount():
                self.settings_tree.setCurrentItem(self.settings_tree.topLevelItem(0))
        state=multi.inspect(alias)
        if state.get('managed') and state.get('alive'):
            answer=QMessageBox.question(self,'Удаление работающей модели',
                f'Модель {alias} работает. Сначала остановить её, затем удалить профиль?\nРаботающие другие модели не пострадают.')
            if answer==QMessageBox.StandardButton.Yes:
                self.async_call('Остановка перед удалением '+alias,
                                lambda:multi.stop(alias),
                                after=lambda ok,txt:actual_delete() if ok and not multi.inspect(alias).get('alive') else None)
            return
        if QMessageBox.question(self,'Удаление',f'Удалить профиль {alias}? GGUF-файл останется на диске.')==QMessageBox.StandardButton.Yes:
            actual_delete()

    def select_tree_alias(self,tree,alias):
        for i in range(tree.topLevelItemCount()):
            item=tree.topLevelItem(i)
            if item.data(0,Qt.ItemDataRole.UserRole)==alias:
                tree.setCurrentItem(item);tree.scrollToItem(item);return

    def select_alias_in_trees(self,alias):
        self.select_tree_alias(self.tree,alias)
        self.select_tree_alias(self.settings_tree,alias)

    def open_selected_in_editor(self,*_):
        alias=self.selected_alias()
        if not alias:return
        self.tabs.setCurrentIndex(4)
        self.select_tree_alias(self.settings_tree,alias)
        self.editor_tabs.setCurrentIndex(0)

    def save_all_settings(self):
        data=core.settings()
        data.update({k:w.text().strip() for k,w in self.set_inputs.items()})
        core.atomic_json(core.SETTINGS,data)
        self.settings_data=data
        QMessageBox.information(self,'Настройки','Настройки программы сохранены. Профили сохраняются отдельно.')

    # ---------- Status and logs ----------
    def append_log(self,text):
        if hasattr(self,'test_output'):self.test_output.append('\n'+text)

    def update_live_log(self):
        if not hasattr(self,'live_logs'):return
        alias=self.selected_log_alias or self.selected_alias()
        if not alias:return
        path=multi.log_path(alias)
        if not path or not path.is_file():return
        key=str(path)
        try:
            size=path.stat().st_size
            offset=self.log_offsets.get(key,max(0,size-50000))
            if offset>size:offset=0
            if offset==size:return
            with path.open('rb') as stream:
                stream.seek(offset)
                data=stream.read(min(128000,size-offset))
                next_offset=stream.tell()
            self.log_offsets[key]=next_offset
            if data:
                self.live_logs.moveCursor(QTextCursor.MoveOperation.End)
                self.live_logs.insertPlainText(data.decode('utf-8','replace'))
                self.live_logs.moveCursor(QTextCursor.MoveOperation.End)
        except OSError:pass

    def refresh_status(self):
        gpu=core.gpu_metrics(); ram=core.ram_metrics()
        if gpu:
            self.graph_gpu.add(gpu.get('gpu'))
            self.graph_vram.maximum=max(22,float(gpu.get('vram_total',22))/1024)
            self.graph_vram.add(gpu.get('vram',0)/1024)
        if ram:
            self.graph_ram.maximum=max(1,ram.get('ram_total',64))
            self.graph_ram.add(ram.get('ram'))
        all_gpus = core.all_gpu_metrics()
        details = [f"GPU {g['index']}: {g['gpu']:.0f}% · VRAM {g['vram']/1024:.1f}/{g['vram_total']/1024:.1f} GiB · {g['temp']:.0f}°C · {g['power']:.0f} W"
                   for g in all_gpus]
        if not details: details = ['Нет данных NVIDIA']
        details.append(f"RAM {ram.get('ram',0):.1f}/{ram.get('ram_total',0):.1f} GiB · Swap {ram.get('swap',0):.1f} GiB")
        self.metrics_label.setText('\n'.join(details))
        state=core.get_status()
        names={'webui':'работает' if state['webui'] else 'не отвечает',
               'office':'управляемый' if state['office'] else 'не подтверждён',
               'comfy':'работает' if state['comfy'] else 'не отвечает'}
        for sid,lab in self.service_labels.items():
            lab.setText(names.get(sid,'—'))
            active=(sid=='webui' and state['webui']) or (sid=='office' and state['office']) or (sid=='comfy' and state['comfy'])
            lab.setStyleSheet('color: #63d6ac;' if active else 'color: #e9b5a0;')
        running=[k for k,v in multi.all_states().items() if v.get('state')=='running' and v.get('managed')]
        self.setWindowTitle(f'AI Model Lab — KDE · работающих моделей: {len(running)}')
        self.status_label.setText('Работают: '+(', '.join(running) if running else 'нет'))
        self.update_model_status_cells()
        self.update_instances_table()
        self.refresh_model_action_button()
        self.refresh_test_instances()

    def closeEvent(self,event):
        if self.exit_requested:
            if any(job.isRunning() for job in self.jobs):
                QMessageBox.information(self,'Идёт операция','Дождись завершения загрузки или остановки серверов. Можно свернуть программу в трей.')
                self.exit_requested=False;event.ignore();return
            if self.editor_dirty and not self.confirm_discard_or_save():
                self.exit_requested=False;event.ignore();return
            if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:
                QMessageBox.information(self,'Активный тест','Сначала останови активное испытание.')
                self.exit_requested=False;event.ignore();return
            if self.tray:self.tray.hide()
            event.accept();return
        dialog=QMessageBox(self)
        dialog.setWindowTitle('Закрыть AI Model Lab?')
        dialog.setText('Как закрыть приложение? Работающие серверы не будут остановлены автоматически.')
        tray_btn=None
        if self.tray and self.tray.isVisible():
            tray_btn=dialog.addButton('Свернуть в трей',QMessageBox.ButtonRole.AcceptRole)
        exit_btn=dialog.addButton('Закрыть приложение (серверы оставить)',QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn=dialog.addButton('Отмена',QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        clicked=dialog.clickedButton()
        if tray_btn and clicked==tray_btn:
            event.ignore();self.hide()
            self.tray.showMessage('AI Model Lab','Приложение работает в трее; серверы продолжают работу.',QSystemTrayIcon.MessageIcon.Information,3000)
        elif clicked==exit_btn:
            if any(job.isRunning() for job in self.jobs):
                QMessageBox.information(self,'Идёт операция','Пока идёт операция, приложение можно свернуть в трей.')
                event.ignore();return
            if self.editor_dirty and not self.confirm_discard_or_save():
                event.ignore();return
            if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:
                QMessageBox.information(self,'Активный тест','Сначала останови активное испытание.')
                event.ignore();return
            self.exit_requested=True
            if self.tray:self.tray.hide()
            event.accept()
        else:event.ignore()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('AI Model Lab')
    app.setOrganizationName('AI Model Lab Local')
    window = Window()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
