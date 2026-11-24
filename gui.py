#!/usr/bin/env python3
"""AI Model Lab KDE — Qt6 frontend for standalone local AI laboratory."""
from __future__ import annotations
import json
import sys
import shutil
import subprocess
from pathlib import Path
from collections import deque

try:
    from PySide6.QtCore import Qt, QThread, Signal, QTimer, QProcess, QPoint
    from PySide6.QtGui import QPainter, QColor, QPen, QFont, QDesktopServices, QTextCursor, QIcon, QAction, QBrush
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
        QHBoxLayout, QGridLayout, QTabWidget, QTreeWidget, QTreeWidgetItem, QGroupBox,
        QComboBox, QLineEdit, QSpinBox, QFileDialog, QMessageBox, QTextEdit, QSplitter,
        QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QAbstractItemView,
        QScrollArea, QCheckBox, QDoubleSpinBox, QSystemTrayIcon, QMenu, QDialog, QPlainTextEdit, QDialogButtonBox, QStyle, QToolButton, QInputDialog, QWidgetAction
    )
    from PySide6.QtCore import QUrl
except ImportError:
    try:
        from PyQt6.QtCore import Qt, QThread, pyqtSignal as Signal, QTimer, QProcess, QUrl, QPoint
        from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QDesktopServices, QTextCursor, QIcon, QAction, QBrush
        from PyQt6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
            QHBoxLayout, QGridLayout, QTabWidget, QTreeWidget, QTreeWidgetItem, QGroupBox,
            QComboBox, QLineEdit, QSpinBox, QFileDialog, QMessageBox, QTextEdit, QSplitter,
            QTableWidget, QTableWidgetItem, QHeaderView, QFormLayout, QAbstractItemView,
            QScrollArea, QCheckBox, QDoubleSpinBox, QSystemTrayIcon, QMenu, QDialog, QPlainTextEdit, QDialogButtonBox, QStyle, QToolButton
        )
    except ImportError:
        print('Qt6 Python required. On CachyOS/Arch run: sudo pacman -S pyside6', file=sys.stderr)
        raise SystemExit(2)

import core
import multi
import model_catalog
import model_maintenance
import model_folders
import client_launcher
import custom_services
import shutdown_manager
import service_browser
import version_info
from i18n import T, set_language, get_language, available_languages

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
QPushButton,QToolButton {{ background:{COLORS['panel']};border:1px solid {COLORS['line']};
             padding:8px 13px;border-radius:7px;min-height:21px; }}
QPushButton:hover,QToolButton:hover {{ background:#324563;border-color:{COLORS['accent']}; }}
QPushButton:disabled,QToolButton:disabled {{ color:#6e7d93;background:#202736;border-color:#253449; }}
QPushButton#Primary {{ background:#245e9a;border:1px solid #438de1;font-weight:700; }}
QPushButton#Danger {{ background:#63333b;border:1px solid #ae5364; }}
QPushButton#Slim {{ padding:5px 10px; min-height:18px; font-size:12px; border-radius:6px; }}
QTabWidget::pane {{ border:1px solid {COLORS['line']};border-radius:8px; }}
QTabBar::tab {{ padding:11px 17px;background:{COLORS['surface']};color:{COLORS['muted']}; }}
QTabBar::tab:selected {{ color:white;background:#2a405c;border-bottom:2px solid #62a9ff; }}
QTreeWidget,QTableWidget,QTextEdit,QPlainTextEdit,QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox {{ background:#141e2b;
        border:1px solid #31415a;border-radius:6px;padding:5px;selection-background-color:#2b6197; }}
QHeaderView::section {{ background:#25344a;color:#dfe9f7;border-right:2px solid #56708c;
                           border-bottom:2px solid #56708c;padding:8px; }}
QTreeWidget::item {{ border-right:1px solid #2b3e57;border-bottom:1px solid #25364b; }}
QTreeWidget::item:selected {{ background:#235b94;color:#ffffff;border-bottom:1px solid #83c6ff; }}
QTreeWidget::item:selected:!active {{ background:#285176;color:#ffffff;border-bottom:1px solid #6eaddd; }}
QTreeWidget::item:hover:!selected {{ background:#223950; }}
QScrollBar:vertical {{ background:#1e2a3a;width:10px; }}
QScrollBar::handle:vertical {{ background:#536983;border-radius:4px; }}
QScrollBar:horizontal {{ background:#1e2a3a;height:10px; }}
QScrollBar::handle:horizontal {{ background:#536983;border-radius:4px; }}
'''


def btn(text, callback, primary=False, danger=False, slim=False):
    b = QPushButton(text)
    names = []
    if primary:
        names.append('Primary')
    if danger:
        names.append('Danger')
    if slim:
        names.append('Slim')
    if names:
        b.setObjectName(' '.join(names))
        # fallback for styles that rely on substring matching
        b.setProperty('class', ' '.join(names))
    b.clicked.connect(callback)
    return b


def slim_btn(text, callback, primary=False, danger=False):
    b = btn(text, callback, primary=primary, danger=danger)
    b.setProperty('slim', True)
    b.setStyleSheet('padding:5px 10px; min-height:18px; font-size:12px; border-radius:6px;')
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
        self.setMinimumSize(185, 100)
        self.setMaximumHeight(132)

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



FOLDER_ROLE = int(Qt.ItemDataRole.UserRole) + 1


class ModelTreeItem(QTreeWidgetItem):
    """Numeric sort inside folders; folders sort alphabetically."""
    def __lt__(self, other):
        tree = self.treeWidget()
        column = tree.sortColumn() if tree else 0
        if column in (2, 4, 5) and self.parent() is not None:
            try:
                return int(self.data(column, Qt.ItemDataRole.UserRole)) < int(
                    other.data(column, Qt.ItemDataRole.UserRole))
            except (ValueError, TypeError):
                pass
        return self.text(column).casefold() < other.text(column).casefold()


class ModelFolderTree(QTreeWidget):
    """Drag a *profile* onto a folder; never mutate items or GGUF on drop."""
    modelDropped = Signal(str, str)

    def dropEvent(self, event):
        source = self.currentItem()
        pos = event.position().toPoint()
        target = self.itemAt(pos)
        if source is None or source.parent() is None or target is None:
            event.ignore()
            return
        folder_item = target if target.parent() is None else target.parent()
        folder = folder_item.data(0, FOLDER_ROLE)
        alias = source.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(alias, str) or not isinstance(folder, str):
            event.ignore()
            return
        event.acceptProposedAction()
        self.modelDropped.emit(alias, folder)


class ColumnFilterPopup(QDialog):
    """Small anchored, searchable checkbox list for header-column filtering."""
    def __init__(self, title, values, selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T('Фильтр: ') + title)
        self.setWindowFlags(Qt.WindowType.Popup)
        self.setMinimumWidth(270)
        self.sort_order = None
        self.values = list(values)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(QLabel(T('Фильтр: ') + title))
        self.search = QLineEdit()
        self.search.setPlaceholderText(T('Найти значение…'))
        layout.addWidget(self.search)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(90)
        scroll.setMaximumHeight(245)
        panel = QWidget()
        inner = QVBoxLayout(panel)
        inner.setSpacing(3)
        self.checks = {}
        for value in self.values:
            checkbox = QCheckBox(str(value))
            checkbox.setChecked(selected is None or value in selected)
            inner.addWidget(checkbox)
            self.checks[value] = checkbox
        inner.addStretch(1)
        scroll.setWidget(panel)
        layout.addWidget(scroll)
        self.search.textChanged.connect(self.search_values)
        row = QHBoxLayout()
        row.addWidget(btn(T('Все'), lambda: self.check_all(True), slim=True))
        row.addWidget(btn(T('Ничего'), lambda: self.check_all(False), slim=True))
        layout.addLayout(row)
        row_sort = QHBoxLayout()
        row_sort.addWidget(btn(T('↑ Сортировать'), lambda: self.choose_sort(Qt.SortOrder.AscendingOrder), slim=True))
        row_sort.addWidget(btn(T('↓ Сортировать'), lambda: self.choose_sort(Qt.SortOrder.DescendingOrder), slim=True))
        layout.addLayout(row_sort)
        row_buttons = QHBoxLayout()
        row_buttons.addWidget(btn(T('Сбросить'), self.clear_filter, slim=True))
        row_buttons.addWidget(btn(T('Применить'), self.accept, primary=True, slim=True))
        layout.addLayout(row_buttons)

    def search_values(self, text):
        query = text.strip().casefold()
        for value, widget in self.checks.items():
            widget.setVisible(query in value.casefold())

    def check_all(self, checked):
        for widget in self.checks.values():
            if widget.isVisible():
                widget.setChecked(checked)

    def clear_filter(self):
        for widget in self.checks.values():
            widget.setChecked(True)
        self.accept()

    def choose_sort(self, order):
        self.sort_order = order
        self.accept()

    def selected_values(self):
        selected = {value for value, widget in self.checks.items() if widget.isChecked()}
        return None if len(selected) == len(self.values) else selected


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        core.prepare()
        self.cfg = core.config()
        self.settings_data = core.settings()
        set_language(self.settings_data.get("language", "ru"))
        self.browser_mode_controls = {sid: [] for sid in service_browser.SERVICES}
        self.jobs = []
        self.proc = None
        self.model_action_busy = False
        self.editor_loading = False
        self.editor_dirty = False
        self.editor_current_alias = None
        self._tree_loading = False
        self.exit_requested = False
        self.shutdown_job = None
        self.shutdown_report = None
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

        self.setWindowTitle(T('AI Model Lab — KDE · локальная лаборатория'))
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
        t = QLabel(T('Модели · отдельные сервисы · тесты · GPU и история'))
        t.setObjectName('Subheader')
        titles.addWidget(t)
        header.addLayout(titles)
        header.addStretch()
        self.language_combo = QComboBox()
        self.language_combo.setToolTip(T('Язык интерфейса'))
        for code, display in available_languages():
            self.language_combo.addItem(display, code)
        idx = self.language_combo.findData(get_language())
        self.language_combo.setCurrentIndex(max(idx, 0))
        self.language_combo.currentIndexChanged.connect(self.switch_language)
        header.addWidget(self.language_combo)
        header.addWidget(btn(T('↻ Обновить'), self.refresh_status))
        layout.addLayout(header)

        # A fixed minimum-content width prevents four plots and per-GPU telemetry
        # from collapsing into unreadable slivers on narrow windows.
        self.metrics_scroll = QScrollArea()
        self.metrics_scroll.setWidgetResizable(True)
        self.metrics_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.metrics_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.metrics_scroll.setMinimumHeight(151)
        self.metrics_scroll.setMaximumHeight(167)
        metrics_widget = QWidget()
        metrics_widget.setMinimumWidth(1130)
        metrics = QHBoxLayout(metrics_widget)
        metrics.setContentsMargins(1, 1, 1, 1)
        metrics.setSpacing(8)
        self.graph_gpu = Sparkline('GPU', '%', 100)
        self.graph_vram = Sparkline('VRAM', 'GiB', 22)
        self.graph_ram = Sparkline('RAM', 'GiB', 64)
        self.graph_speed = Sparkline(T('Скорость · история'), 'tok/s')
        for g in (self.graph_gpu, self.graph_vram, self.graph_ram, self.graph_speed):
            metrics.addWidget(g, 1)
        self.metrics_label = QLabel(T('Нет данных GPU'))
        self.metrics_label.setWordWrap(True)
        self.metrics_label.setMinimumWidth(240)
        metrics.addWidget(self.metrics_label, 1)
        self.metrics_scroll.setWidget(metrics_widget)
        layout.addWidget(self.metrics_scroll)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.tab_models = self.build_models()
        self.tabs.addTab(self.tab_models, T('🧠 Модели'))
        self.tab_services = self.build_services()
        self.tabs.addTab(self.tab_services, T('⚙ Управление'))
        self.tab_tests = self.build_tests()
        self.tabs.addTab(self.tab_tests, T('🧪 Тесты'))
        self.tab_results = self.build_results()
        self.tabs.addTab(self.tab_results, T('📊 Отчёты'))
        self.tab_settings = self.build_settings()
        self.tabs.addTab(self.tab_settings, T('🔧 Настройки'))

        # Persistent build identity, visible even when the selected tab changes.
        footer = QHBoxLayout()
        self.message = QLabel(T('Готово. Все новые отчёты: ') + str(core.REPORTS))
        self.message.setObjectName('Subheader')
        footer.addWidget(self.message, 1)
        build = version_info.read_build_info()
        self.version_label = QLabel(version_info.short_label(build))
        self.version_label.setObjectName('Subheader')
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.version_label.setToolTip(version_info.detail_label(build, T))
        footer.addWidget(self.version_label)
        layout.addLayout(footer)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(3000)

        self.setup_tray()
        self.apply_retention_cleanup(startup=True)
        self.refresh_reports()
        self.refresh_status()


    def switch_language(self, _index):
        """Persist locale and rebuild widgets. Detached model servers are unaffected."""
        language = self.language_combo.currentData()
        if not language or language == get_language():
            return
        running_benchmark = self.proc and self.proc.state() != QProcess.ProcessState.NotRunning
        if running_benchmark or any(job.isRunning() for job in self.jobs):
            QMessageBox.information(self, T('Смена языка'),
                T('Сначала заверши текущий тест или операцию запуска/остановки.'))
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(self.language_combo.findData(get_language()))
            self.language_combo.blockSignals(False)
            return
        if self.editor_dirty and not self.confirm_discard_or_save():
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(self.language_combo.findData(get_language()))
            self.language_combo.blockSignals(False)
            return
        state = core.settings()
        state['language'] = language
        core.atomic_json(core.SETTINGS, state)
        self.settings_data = state
        set_language(language)
        old_tab = self.tabs.currentIndex()
        alias = self.selected_alias()
        old_geometry = self.geometry()
        new_window = Window()
        new_window.setGeometry(old_geometry)
        if alias:
            new_window.select_tree_alias(new_window.tree, alias)
            new_window.select_tree_alias(new_window.settings_tree, alias)
        new_window.tabs.setCurrentIndex(old_tab)
        app = QApplication.instance()
        app._ai_lab_window = new_window
        new_window.show()
        self.exit_requested = True
        # Closing a Qt window normally hides it without destroying its timers.
        for timer_name in ('timer', 'log_timer', 'auto_timer', 'column_timer'):
            timer = getattr(self, timer_name, None)
            if timer is not None:
                timer.stop()
        self.close()
        self.deleteLater()

    def protected_log_paths(self):
        paths = []
        try:
            for state in multi.active_instances().values():
                if state.get('log'):
                    paths.append(state.get('log'))
        except Exception:
            pass
        paths.extend(custom_services.active_log_paths())
        for service_name in ('office', 'comfy'):
            meta = core.verified(service_name)
            if meta and meta.get('log'):
                paths.append(meta['log'])
        return paths

    def apply_retention_cleanup(self, startup=False):
        logs_days = int(self.settings_data.get('logs_retention_days', 30) or 0)
        reports_days = int(self.settings_data.get('reports_retention_days', 90) or 0)
        stats = core.cleanup_artifacts(logs_days, reports_days, self.protected_log_paths())
        if not startup and (stats['logs_deleted'] or stats['report_dirs_deleted'] or stats['errors']):
            msg = T(f"Удалено логов: {stats['logs_deleted']}; отчётов: {stats['report_dirs_deleted']}")
            if stats['errors']:
                msg += T("\nОшибки: ") + '; '.join(stats['errors'][:4])
            QMessageBox.information(self, T('Очистка'), msg)
        return stats

    def cleanup_old_artifacts(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, T('Очистка'), T('Сначала останови запущенный тест, чтобы не трогать формируемый отчёт.'))
            return
        logs_days = int(self.logs_retention.value()) if hasattr(self, 'logs_retention') else int(self.settings_data.get('logs_retention_days', 30) or 0)
        reports_days = int(self.reports_retention.value()) if hasattr(self, 'reports_retention') else int(self.settings_data.get('reports_retention_days', 90) or 0)
        question = T(f'Удалить артефакты старше указанного срока?\nЛоги: {logs_days} дн.\nОтчёты: {reports_days} дн.\nЖурналы активных моделей сохранятся.')
        if QMessageBox.question(self, T('Очистка логов и отчётов'), question) != QMessageBox.StandardButton.Yes:
            return
        self.settings_data['logs_retention_days'] = logs_days
        self.settings_data['reports_retention_days'] = reports_days
        core.atomic_json(core.SETTINGS, self.settings_data)
        stats = self.apply_retention_cleanup(startup=False)
        self.refresh_reports()
        self.refresh_status()
        self.set_message(T(f"Очистка завершена: логов {stats['logs_deleted']}, отчётов {stats['report_dirs_deleted']}"))

    def clear_all_logs(self):
        if QMessageBox.question(self, T('Очистить все логи'), T('Удалить ВСЕ старые логи AI Model Lab, кроме журналов активных процессов?')) != QMessageBox.StandardButton.Yes:
            return
        stats = core.cleanup_artifacts(0, 0, [])
        protected = {str(Path(p).resolve()) for p in self.protected_log_paths() if p}
        deleted = 0
        for path in core.LOGS.glob('*.log'):
            try:
                if str(path.resolve()) in protected:
                    continue
                path.unlink(missing_ok=True)
                deleted += 1
            except OSError:
                pass
        self.set_message(T(f'Удалено логов: {deleted}'))
        QMessageBox.information(self, T('Логи'), T(f'Удалено логов: {deleted}. Журналы активных моделей сохранены.'))

    def clear_all_reports(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, T('Очистка отчётов'), T('Сначала останови запущенный тест, чтобы не повредить формируемый отчёт.'))
            return
        if QMessageBox.question(self, T('Очистить все отчёты'), T('Удалить ВСЕ папки отчётов из AI Model Lab?')) != QMessageBox.StandardButton.Yes:
            return
        deleted = 0
        for summary in list(core.REPORTS.glob('*/summary.json')):
            try:
                import shutil
                shutil.rmtree(summary.parent)
                deleted += 1
            except OSError:
                pass
        self.refresh_reports()
        self.set_message(T(f'Удалено отчётов: {deleted}'))
        QMessageBox.information(self, T('Отчёты'), T(f'Удалено папок отчётов: {deleted}'))

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
            self.set_message(T('Ошибка: ') + err)
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
        if QMessageBox.question(self, T('Подтверждение'), message + T('\nАктивные тесты могут быть прерваны.')) == QMessageBox.StandardButton.Yes:
            self.async_call(message, fn, after=after)

    def selected_alias(self):
        it = self.tree.currentItem()
        return it.data(0, Qt.ItemDataRole.UserRole) if it else None

    def selected_model_profile(self):
        alias = self.selected_alias()
        return next((m for m in self.cfg.get('models', []) if m.get('id') == alias), None)

    def open_url(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def show_missing_client_help(self, client):
        commands = {
            'pi': ('Pi', 'npm install -g @mariozechner/pi-coding-agent',
                   'https://www.npmjs.com/package/@mariozechner/pi-coding-agent'),
            'opencode': ('OpenCode', 'npm install -g @opencode/cli',
                         'https://opencode.ai/docs/'),
        }
        name, command, url = commands.get(client, (client, '', ''))
        msg = QMessageBox(self)
        msg.setWindowTitle(T(f'Установка {name}'))
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(T(f'Клиент {name} не найден в PATH приложения.'))
        msg.setInformativeText(
            T(f'Установка через Node.js/npm:\n{command}\n\n'
            f'Документация: {url}\n\n'
            'Если приложение уже установлено, проверь путь к исполняемому файлу '
            'и переменную PATH среды KDE. Для запуска клиента сервер модели должен работать.')
        )
        copy_cmd = msg.addButton(T('Копировать команду'), QMessageBox.ButtonRole.ActionRole)
        docs = msg.addButton(T('Открыть документацию'), QMessageBox.ButtonRole.ActionRole)
        msg.addButton(T('Закрыть'), QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        if msg.clickedButton() is copy_cmd:
            QApplication.clipboard().setText(command)
        elif msg.clickedButton() is docs:
            self.open_url(url)

    def create_browser_mode_combo(self, sid):
        """A per-service preference, shared across Models and Management tabs."""
        combo = QComboBox()
        combo.setMinimumWidth(238)
        combo.addItem(T('Во вкладке'), 'tab')
        combo.addItem(T('В отдельном окне браузера'), 'window')
        combo.addItem(T('В отдельном окне без панелей'), 'app')
        index = combo.findData(service_browser.get_mode(sid, self.settings_data))
        combo.setCurrentIndex(max(0, index))
        combo.setToolTip(T('Окно без панелей требует Chromium, Chrome, Brave, Vivaldi или Edge. Настройка сохраняется для каждого сервиса.'))
        combo.currentIndexChanged.connect(
            lambda _index, service=sid, widget=combo: self.change_browser_mode(service, widget)
        )
        self.browser_mode_controls[sid].append(combo)
        return combo

    def change_browser_mode(self, sid, source):
        mode = source.currentData()
        try:
            state = service_browser.set_mode(sid, mode)
        except Exception as exc:
            QMessageBox.warning(self, T('Настройки браузера'), str(exc))
            return
        self.settings_data = state
        for combo in self.browser_mode_controls.get(sid, []):
            if combo is source:
                continue
            combo.blockSignals(True)
            combo.setCurrentIndex(max(0, combo.findData(mode)))
            combo.blockSignals(False)

    def open_service(self, sid):
        """Open a ready service; start and wait asynchronously when stopped."""
        if sid in self.service_busy:
            return
        titles = {'webui': 'Open WebUI', 'office': 'Agent Office', 'comfy': 'ComfyUI'}
        title = titles.get(sid, sid)
        mode = service_browser.get_mode(sid, self.settings_data)
        self.service_busy.add(sid)
        self.update_builtin_services(core.get_status())

        def completed(ok, url):
            self.service_busy.discard(sid)
            self.update_builtin_services(core.get_status())
            if not ok:
                return
            try:
                self.set_message(service_browser.open_browser(url.strip(), mode))
            except Exception as exc:
                QMessageBox.warning(self, T('Не удалось открыть браузер'), str(exc))

        self.async_call(T('Подготовка сервиса ') + title,
                        lambda: service_browser.ensure_ready(sid), after=completed)

    def open_webui(self):
        self.open_service('webui')

    def open_office(self):
        self.open_service('office')

    def copy_selected_api(self):
        alias = self.selected_alias()
        if not alias:
            return
        try:
            info = client_launcher.effective_instance(alias)
            QApplication.clipboard().setText(info['url'])
            self.set_message(T('API скопирован: ') + info['url'])
        except Exception as exc:
            QMessageBox.warning(self, T('API модели'), str(exc))

    def open_preferred_client(self):
        if hasattr(self, 'client_combo'):
            client = self.client_combo.currentData()
            if client:
                self.open_model_client(client)

    def refresh_preferred_client_button(self):
        """Selection is editable independently of server readiness."""
        if not hasattr(self, 'client_combo'):
            return
        profile = self.selected_model_profile()
        chosen = client_launcher.preferred_client(profile)
        self.client_combo.blockSignals(True)
        idx = self.client_combo.findData(chosen)
        self.client_combo.setCurrentIndex(max(idx, 0))
        self.client_combo.blockSignals(False)
        self.update_client_hint()

    def update_client_hint(self):
        if not hasattr(self, 'client_combo'):
            return
        client = self.client_combo.currentData()
        try:
            client_launcher.find_executable(client)
            description = T(f'{client.capitalize()} найден. Выбор клиента сохраняется сразу и не запускает модель.')
        except (FileNotFoundError, ValueError):
            description = T(f'{client.capitalize()} пока не найден. Выбор сохранится; установка — кнопка «?». ')
        self.client_hint.setText(description)

    def on_client_preference_changed(self, _index):
        """Persist just one field, without requiring a running llama-server."""
        alias = self.selected_alias()
        client = self.client_combo.currentData()
        if not alias or client not in client_launcher.CLIENTS:
            return
        profile = self.profile_lookup(alias)
        if profile is None:
            return
        previous = profile.get('preferred_client')
        try:
            updated = core.update_model_client_preference(alias, client)
            self.cfg = updated
        except Exception as exc:
            QMessageBox.warning(self, T('Не удалось сохранить клиент'), str(exc))
            self.refresh_preferred_client_button()
            return
        # Keep the open editor in sync without losing unsaved changes to other fields.
        if getattr(self, 'editor_current_alias', None) == alias and hasattr(self, 'edit_fields'):
            editor_choice = self.edit_fields.get('preferred_client')
            if editor_choice:
                editor_choice.blockSignals(True)
                idx = editor_choice.findData(client)
                editor_choice.setCurrentIndex(max(0, idx))
                editor_choice.blockSignals(False)
        self.update_client_hint()
        self.model_info.setPlainText(self.model_info.toPlainText().replace(
            T('Клиент по умолчанию: ') + str(previous or client_launcher.preferred_client({'id': alias})),
            T('Клиент по умолчанию: ') + client))
        self.set_message(T(f'{alias}: клиент по умолчанию — {client} (сохранено в models.json)'))

    def open_model_client(self, client):
        alias = self.selected_alias()
        if not alias:
            return
        try:
            client_launcher.find_executable(client)
        except FileNotFoundError:
            self.show_missing_client_help(client)
            return
        try:
            info = client_launcher.effective_instance(alias)
            folder = client_launcher.workspace_dir()
            terminal = shutil.which('konsole')
            if not terminal:
                raise FileNotFoundError(T('Не найдена Konsole. Для CachyOS: sudo pacman -S konsole'))
            argv = [terminal, '--noclose', '-e', sys.executable, '-u',
                    str(core.ROOT / 'client_launcher.py'), '--client', client,
                    '--model', alias]
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            self.set_message(T(f"Открываю {client} → {alias} :{info['port']} · папка {folder}"))
        except RuntimeError as exc:
            QMessageBox.information(self, T('Запуск клиента'),
                                    T(f'{exc}\n\nПредпочитаемый клиент можно выбрать и сохранить без запуска модели.'))
        except Exception as exc:
            QMessageBox.warning(self, T('Открытие ИИ-клиента'), str(exc))

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        icon_file = core.ROOT / 'assets' / 'ai-model-lab.svg'
        icon = QIcon(str(icon_file))
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(T('AI Model Lab — локальные ИИ-серверы'))
        menu = QMenu(self)
        action_show = menu.addAction(T('Открыть AI Model Lab'))
        action_show.triggered.connect(self.show_from_tray)
        menu.addAction(T('Тесты'), lambda: self.show_tab_from_tray(2))
        menu.addAction(T('Управление'), lambda: self.show_tab_from_tray(1))
        menu.addSeparator()
        quit_action = menu.addAction(T('Закрыть приложение (серверы оставить)'))
        quit_action.triggered.connect(self.quit_from_tray)
        shutdown_action = menu.addAction(T('Закрыть и остановить все управляемые AI-сервисы'))
        shutdown_action.triggered.connect(self.request_full_exit)
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
            QMessageBox.information(self, T('Активный тест'), T('Сначала останови тест, чтобы не потерять отчёт.'))
            self.show_tab_from_tray(2)
            return
        self.exit_requested = True
        self.close()

    def request_full_exit(self):
        """User-confirmed full exit, never kill arbitrary third-party processes."""
        if self.shutdown_job and self.shutdown_job.isRunning():
            return
        if any(job.isRunning() for job in self.jobs):
            QMessageBox.information(self, T('Идёт операция'),
                                    T('Дождись завершения запуска или остановки сервера.'))
            return
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.information(self, T('Активный тест'),
                                    T('Сначала останови активное испытание.'))
            self.show_tab_from_tray(2)
            return
        if self.editor_dirty and not self.confirm_discard_or_save():
            return
        detail = T('Остановить все управляемые модели llama.cpp, Open WebUI, Agent Office, ComfyUI и пользовательские сервисы, затем закрыть AI Model Lab?')
        warning = T('Сторонние процессы, внешние серверы, отдельные сессии Pi и OpenCode останутся работать.')
        if QMessageBox.question(self, T('Полный выход'), detail + '\n\n' + warning) != QMessageBox.StandardButton.Yes:
            return
        self.shutdown_report = None
        self.set_message(T('Остановка управляемых AI-сервисов…'))
        job = Worker(lambda: json.dumps(shutdown_manager.stop_all_managed(), ensure_ascii=False), self)
        self.shutdown_job = job
        job.done.connect(self.on_shutdown_result)
        job.failed.connect(self.on_shutdown_failed)
        job.finished.connect(self.on_shutdown_finished)
        job.start()

    def on_shutdown_result(self, json_text):
        try:
            self.shutdown_report = json.loads(json_text)
        except ValueError as exc:
            self.shutdown_report = {'success': False, 'failed': [str(exc)], 'external': []}

    def on_shutdown_failed(self, message):
        self.shutdown_report = {'success': False, 'failed': [message], 'external': []}

    def on_shutdown_finished(self):
        report = self.shutdown_report or {'success': False, 'failed': ['Нет результата завершения'], 'external': []}
        self.shutdown_job = None
        if not report.get('success'):
            errors = '\n'.join(report.get('failed', [])) or T('Не все процессы остановлены.')
            dialog = QMessageBox(self)
            dialog.setWindowTitle(T('Неполное завершение'))
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setText(T('Не все сервисы удалось остановить. Что сделать?'))
            dialog.setInformativeText(errors)
            gui_only = dialog.addButton(
                T('Закрыть только интерфейс (сервисы оставить)'),
                QMessageBox.ButtonRole.AcceptRole)
            inspect = dialog.addButton(T('Оставить окно открытым'),
                                       QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(inspect)
            dialog.exec()
            if dialog.clickedButton() == gui_only:
                # Do not repeat termination or touch unowned processes.
                # closeEvent still checks active tests/unsaved edits.
                self.exit_requested = True
                self.close()
                return
            self.set_message(T('Остановка завершилась с ошибками — проверь сервисы.'))
            self.refresh_status()
            return
        external = report.get('external', [])
        if external:
            QMessageBox.information(self, T('Полный выход'),
                T('Управляемые процессы остановлены. Неуправляемые экземпляры оставлены работать:') +
                '\n\n' + '\n'.join(external))
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
        self.show_log_dialog(self.selected_log_alias)

    def show_log_dialog(self, alias):
        path = multi.log_path(alias) if alias else None
        if not path or not path.is_file():
            QMessageBox.information(self, T('Логи'), T('Для выбранной модели журнала пока нет.'))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(T(f'Журнал {alias} — {path.name}'))
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
        view.setPlainText((T('Показаны последние 2 МБ (файл больше 2 МБ).\n\n') if size > 2_000_000 else '') + content)
        view.moveCursor(QTextCursor.MoveOperation.End)
        layout.addWidget(view, 1)
        row = QHBoxLayout()
        row.addWidget(btn(T('Открыть файл внешним редактором'), lambda: self.open_url(path.as_uri())))
        row.addWidget(btn(T('Закрыть'), dialog.accept))
        layout.addLayout(row)
        dialog.exec()

    # ---------- Models tab ----------
    def build_models(self):
        w = QScrollArea()
        w.setWidgetResizable(True)
        content = QWidget()
        content.setMinimumHeight(610)
        l = QVBoxLayout(content)
        split = QSplitter(Qt.Orientation.Horizontal)
        l.addWidget(split, 1)
        w.setWidget(content)
        left_wrap = QWidget(); left_layout = QVBoxLayout(left_wrap)
        left_layout.setContentsMargins(0, 0, 0, 0); left_layout.setSpacing(6)
        self.tree = ModelFolderTree(); self.tree.setColumnCount(7)
        self.tree.setHeaderLabels([T('Модель'), T('Статус'), T('Контекст'), 'GPU', T('Порт'), 'PID', T('Назначение')])
        self.tree.setRootIsDecorated(True)
        self.tree.setToolTip(T('Заголовок — фильтр и сортировка. ПКМ — действия. Перетащи модель на папку.'))
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setAllColumnsShowFocus(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.tree.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tree.header().setStretchLastSection(False)
        widths = self.settings_data.get('ui_columns', [])
        # v3.2 persisted four columns; migrate without applying the old fourth
        # column (purpose) to the new fourth column (GPU).
        if len(widths) != 7:
            widths = [255, 155, 100, 200, 85, 90, 390]
        self.tree.header().setMinimumSectionSize(60)
        for i, width in enumerate(widths):
            self.tree.header().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
            self.tree.setColumnWidth(i, max(60, int(width)))
        self.tree.header().setSectionsMovable(False)
        self.tree.header().sectionResized.connect(self.defer_column_save)
        self.tree.itemDoubleClicked.connect(self.open_selected_in_editor)
        self.tree.currentItemChanged.connect(self.on_model_selected)
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumHeight(240)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.model_tree_context_menu)
        self.tree.modelDropped.connect(self.on_model_folder_dropped)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.viewport().setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.header().sectionClicked.connect(self.open_model_column_filter)
        self.column_filters = {}
        self.column_sort = (0, Qt.SortOrder.AscendingOrder)
        self.folder_expansion = {}
        left_layout.addWidget(self.tree, 4)
        actions = QGridLayout()
        actions.setHorizontalSpacing(5)
        actions.setVerticalSpacing(5)
        controls = [
            (T('＋ Добавить'), self.add_model),
            (T('⧉ Клонировать'), self.clone_selected_model),
            (T('－ Удалить'), self.delete_selected_model),
            (T('✎ Изменить'), self.open_selected_in_editor),
            (T('🔎 Найти GGUF'), self.import_local_models),
            (T('🛠 Профили'), self.maintain_model_profiles),
        ]
        for n, (title, handler) in enumerate(controls):
            action = slim_btn(title, handler, primary=(n == 0), danger=(n == 2))
            action.setMinimumWidth(0)
            actions.addWidget(action, n // 3, n % 3)
        left_layout.addLayout(actions)
        self.status_label = QLabel(T('Статус: ожидание')); self.status_label.setObjectName('Subheader')
        self.status_label.setWordWrap(True); left_layout.addWidget(self.status_label)
        logs_group = QGroupBox(T('Живой журнал выбранной модели')); logs_layout = QVBoxLayout(logs_group)
        self.live_logs = QPlainTextEdit(); self.live_logs.setReadOnly(True)
        self.live_logs.setMaximumBlockCount(1000); self.live_logs.setMinimumHeight(140)
        logs_layout.addWidget(self.live_logs)
        log_buttons = QHBoxLayout()
        log_buttons.addWidget(btn(T('Открыть полный лог'), self.open_full_log))
        log_buttons.addWidget(btn(T('Показать последнюю запись'), self.reset_log_view))
        logs_layout.addLayout(log_buttons)
        left_layout.addWidget(logs_group, 2)
        split.addWidget(left_wrap)
        right = QWidget(); r = QVBoxLayout(right)
        box = QGroupBox(T('Выбранная модель')); f = QVBoxLayout(box)
        self.model_info = QPlainTextEdit(); self.model_info.setReadOnly(True)
        self.model_info.setMinimumHeight(210)
        f.addWidget(self.model_info, 1)
        self.model_action_btn = QPushButton(T('● Статус модели'))
        self.model_action_btn.clicked.connect(self.model_action)
        f.addWidget(self.model_action_btn)
        client_row = QHBoxLayout()
        self.client_open_btn = btn(T('⌘ Открыть в'), self.open_preferred_client, primary=True)
        self.client_open_btn.setToolTip(T('Запустить выбранный клиент для работающей модели'))
        client_row.addWidget(self.client_open_btn, 1)
        self.client_combo = QComboBox()
        self.client_combo.addItem('Pi', 'pi')
        self.client_combo.addItem('OpenCode', 'opencode')
        self.client_combo.setMinimumWidth(125)
        self.client_combo.setToolTip(T('Предпочитаемый клиент: выбор сохраняется даже если модель остановлена'))
        self.client_combo.currentIndexChanged.connect(self.on_client_preference_changed)
        client_row.addWidget(self.client_combo, 1)
        self.client_install_btn = btn('?', lambda: self.show_missing_client_help(self.client_combo.currentData()))
        self.client_install_btn.setToolTip(T('Инструкция по установке выбранного клиента'))
        self.client_install_btn.setFixedWidth(34)
        client_row.addWidget(self.client_install_btn)
        f.addLayout(client_row)
        self.client_hint = QLabel(T('Выбор клиента сохраняется независимо от состояния модели'))
        self.client_hint.setWordWrap(True)
        self.client_hint.setStyleSheet('color:#a1b4cf;font-size:11px;')
        f.addWidget(self.client_hint)
        f.addWidget(btn(T('✎ Редактировать параметры'), self.open_selected_in_editor))
        for sid, caption, action in (
            ('webui', T('🌐 Открыть WebUI'), self.open_webui),
            ('office', T('🏢 Открыть Agent Office'), self.open_office),
        ):
            line = QHBoxLayout()
            line.addWidget(btn(caption, action), 2)
            line.addWidget(self.create_browser_mode_combo(sid), 1)
            f.addLayout(line)
        r.addWidget(box)
        hint = QLabel(T('Каждая модель: свой порт и GPU. Двойной щелчок → редактор.\nШирина колонок сохраняется автоматически.'))
        hint.setWordWrap(True); r.addWidget(hint)
        split.addWidget(right)
        split.setChildrenCollapsible(False)
        left_wrap.setMinimumWidth(405)
        right.setMinimumWidth(330)
        split.setSizes([680, 510])
        self.column_timer = QTimer(self); self.column_timer.setSingleShot(True)
        self.column_timer.timeout.connect(self.persist_columns)
        self.populate_model_tree()
        first = self.first_visible_model_item()
        if first is not None:
            self.tree.setCurrentItem(first)
        return w

    def defer_column_save(self, *args):
        if hasattr(self, 'column_timer') and not self._tree_loading:
            self.column_timer.start(700)

    def persist_columns(self):
        settings = core.settings()
        settings['ui_columns'] = [self.tree.columnWidth(i) for i in range(self.tree.columnCount())]
        core.atomic_json(core.SETTINGS, settings)
        self.settings_data = settings

    def save_model_folder_change(self, updated, *, preferred_alias=None):
        """Only profile metadata changes; preserve GGUF, running services and backups."""
        if core.config() != self.cfg:
            raise RuntimeError(T('models.json изменён извне; открой приложение заново.'))
        if updated == self.cfg:
            return
        model_catalog.save_config(core.MODELS, updated)
        self.cfg = updated
        self.populate_settings_tree()
        self.populate_model_tree()
        if preferred_alias:
            self.select_tree_alias(self.tree, preferred_alias)
        self.apply_model_filters()

    def selected_folder_name(self):
        item = self.tree.currentItem()
        if item is None:
            return None
        root = item if item.parent() is None else item.parent()
        return root.data(0, FOLDER_ROLE)

    def create_model_folder(self):
        if self.editor_dirty and not self.confirm_discard_or_save():
            return
        name, ok = QInputDialog.getText(
            self, T('Новая виртуальная папка'), T('Название папки:'))
        if not ok:
            return
        try:
            updated = model_folders.create_folder(self.cfg, name)
            self.save_model_folder_change(updated)
        except Exception as exc:
            QMessageBox.warning(self, T('Создание папки'), str(exc))

    def rename_model_folder(self, folder=None):
        old = folder if isinstance(folder, str) else self.selected_folder_name()
        if old in (None, model_folders.ALL_FOLDERS, model_folders.UNFILED):
            return
        if self.editor_dirty and not self.confirm_discard_or_save():
            return
        new_name, ok = QInputDialog.getText(
            self, T('Переименовать папку'), T('Новое название:'), text=old)
        if not ok:
            return
        try:
            updated = model_folders.rename_folder(self.cfg, old, new_name)
            self.save_model_folder_change(updated)
        except Exception as exc:
            QMessageBox.warning(self, T('Переименование папки'), str(exc))

    def delete_model_folder(self, folder=None):
        old = folder if isinstance(folder, str) else self.selected_folder_name()
        if old in (None, model_folders.ALL_FOLDERS, model_folders.UNFILED):
            return
        if self.editor_dirty and not self.confirm_discard_or_save():
            return
        count = model_folders.folder_counts(self.cfg).get(old, 0)
        answer = QMessageBox.question(
            self, T('Удаление папки'),
            T(f'Удалить виртуальную папку «{old}»?\n'
              f'{count} моделей перейдут в «Без папки».\n'
              'Сами профили и GGUF на диске не удаляются.'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.save_model_folder_change(model_folders.delete_folder(self.cfg, old))
        except Exception as exc:
            QMessageBox.warning(self, T('Удаление папки'), str(exc))

    def assign_model_folder(self, alias, folder):
        if self.editor_dirty and not self.confirm_discard_or_save():
            return
        try:
            updated = model_folders.move_model(self.cfg, alias, folder)
            self.save_model_folder_change(updated, preferred_alias=alias)
        except Exception as exc:
            QMessageBox.warning(self, T('Перемещение модели'), str(exc))

    def on_model_folder_dropped(self, alias, folder):
        self.assign_model_folder(alias, folder)

    def move_selected_model_folder(self):
        alias = self.selected_alias()
        if not alias:
            return
        folders = [model_folders.UNFILED] + model_folders.list_folders(self.cfg)
        labels = [T('Без папки')] + folders[1:]
        current = model_folders.effective_folder(
            self.selected_model_profile(), self.cfg)
        index = folders.index(current) if current in folders else 0
        chosen, ok = QInputDialog.getItem(
            self, T('Переместить модель'), T('Папка:'), labels, index, False)
        if ok:
            self.assign_model_folder(alias, folders[labels.index(chosen)])

    def toggle_model_favorite(self, alias):
        if self.editor_dirty and not self.confirm_discard_or_save():
            return
        try:
            updated = json.loads(json.dumps(self.cfg))
            p = next((p for p in updated['models'] if p.get('id') == alias), None)
            if p is None:
                raise ValueError(T('Не найден профиль модели'))
            p['favorite'] = not bool(p.get('favorite', False))
            self.save_model_folder_change(updated, preferred_alias=alias)
        except Exception as exc:
            QMessageBox.warning(self, T('Избранное'), str(exc))

    def model_tree_context_menu(self, point):
        """Context options depend on clicked folder or model; no extra toolbar."""
        item = self.tree.itemAt(point)
        menu = QMenu(self.tree)
        if item is None:
            menu.addAction(T('📁 Создать папку'), self.create_model_folder)
        elif item.parent() is None:
            folder = item.data(0, FOLDER_ROLE)
            menu.addAction(T('📁 Создать папку'), self.create_model_folder)
            if folder != model_folders.UNFILED:
                menu.addSeparator()
                menu.addAction(T('✎ Переименовать папку'),
                               lambda checked=False, f=folder: self.rename_model_folder(f))
                menu.addAction(T('－ Удалить папку'),
                               lambda checked=False, f=folder: self.delete_model_folder(f))
            menu.addSeparator()
            menu.addAction(
                T('Свернуть папку') if item.isExpanded() else T('Развернуть папку'),
                lambda: item.setExpanded(not item.isExpanded()))
        else:
            self.tree.setCurrentItem(item)
            alias = item.data(0, Qt.ItemDataRole.UserRole)
            profile = self.profile_lookup(alias) or {}
            marked = bool(profile.get('favorite'))
            menu.addAction(
                T('☆ Убрать из избранного') if marked else T('★ В избранное'),
                lambda checked=False, a=alias: self.toggle_model_favorite(a))
            submenu = menu.addMenu(T('📁 Переместить в папку'))
            for folder in [model_folders.UNFILED] + model_folders.list_folders(self.cfg):
                title = T('Без папки') if folder == model_folders.UNFILED else folder
                submenu.addAction(
                    title,
                    lambda checked=False, a=alias, f=folder: self.assign_model_folder(a, f))
            menu.addAction(T('📁 Создать папку'), self.create_model_folder)
            menu.addSeparator()
            menu.addAction(T('✎ Изменить'), self.open_selected_in_editor)
            menu.addAction(T('⧉ Клонировать'), self.clone_selected_model)
            menu.addAction(T('－ Удалить'), self.delete_selected_model)
        menu.exec(self.tree.viewport().mapToGlobal(point))

    def iter_model_items(self):
        """Yield only real model rows; never try to inspect a virtual folder."""
        for i in range(self.tree.topLevelItemCount()):
            folder_item = self.tree.topLevelItem(i)
            for j in range(folder_item.childCount()):
                yield folder_item.child(j)

    def first_visible_model_item(self):
        return next((item for item in self.iter_model_items()
                     if not item.isHidden() and not item.parent().isHidden()), None)

    def apply_model_filters(self, *_):
        if not hasattr(self, 'tree') or not hasattr(self, 'column_filters'):
            return
        shown = 0
        active = bool(self.column_filters)
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            count = 0
            for j in range(group.childCount()):
                model = group.child(j)
                visible = all(
                    model.text(column) in accepted
                    for column, accepted in self.column_filters.items())
                model.setHidden(not visible)
                count += int(visible)
            group.setHidden(active and count == 0)
            shown += count
        if hasattr(self, 'status_label'):
            # Status label is owned by the existing runtime; do not overwrite it.
            self.tree.setToolTip(T(f'Видимых моделей: {shown} / {len(self.cfg.get("models", []))}'))
        current = self.tree.currentItem()
        if current is None or current.isHidden() or (current.parent() and current.parent().isHidden()):
            first = self.first_visible_model_item()
            if first:
                self.tree.setCurrentItem(first)

    def open_model_column_filter(self, column):
        """Header click opens searchable, multi-select filter + explicit sort."""
        if not 0 <= column < self.tree.columnCount():
            return
        values = sorted({item.text(column) for item in self.iter_model_items()},
                        key=lambda text: text.casefold())
        headers = [T('Модель'), T('Статус'), T('Контекст'), 'GPU',
                   T('Порт'), 'PID', T('Назначение')]
        popup = ColumnFilterPopup(headers[column], values,
                                  self.column_filters.get(column), self)
        from_pos = self.tree.header().sectionViewportPosition(column)
        popup.move(self.tree.header().mapToGlobal(
            QPoint(max(0, from_pos), self.tree.header().height())))
        if popup.exec() != QDialog.DialogCode.Accepted:
            return
        selection = popup.selected_values()
        if selection is None:
            self.column_filters.pop(column, None)
        else:
            self.column_filters[column] = selection
        if popup.sort_order is not None:
            self.column_sort = (column, popup.sort_order)
            self.tree.sortItems(column, popup.sort_order)
        for idx, title in enumerate(headers):
            self.tree.headerItem().setText(
                idx, title + (' ●' if idx in self.column_filters else ' ▾'))
        self.apply_model_filters()

    def populate_model_tree(self):
        """Group model rows under collapsible folders; identities never change."""
        selected = self.selected_alias() if self.tree.topLevelItemCount() else None
        expanded = {}
        if self.tree.topLevelItemCount():
            for i in range(self.tree.topLevelItemCount()):
                group = self.tree.topLevelItem(i)
                expanded[group.data(0, FOLDER_ROLE)] = group.isExpanded()
        self._tree_loading = True
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        grouped = {}
        for profile in self.cfg.get('models', []):
            group = model_folders.effective_folder(profile, self.cfg)
            grouped.setdefault(group, []).append(profile)
        folder_names = model_folders.list_folders(self.cfg)
        if grouped.get(model_folders.UNFILED):
            folder_names.append(model_folders.UNFILED)
        for folder in folder_names:
            profiles = grouped.get(folder, [])
            label = T('Без папки') if folder == model_folders.UNFILED else folder
            root = ModelTreeItem([f'📁 {label} ({len(profiles)})', '', '', '', '', '', ''])
            root.setData(0, FOLDER_ROLE, folder)
            root.setFlags((root.flags() | Qt.ItemFlag.ItemIsDropEnabled)
                          & ~Qt.ItemFlag.ItemIsDragEnabled)
            root.setForeground(0, QBrush(QColor('#9ac9ff')))
            self.tree.addTopLevelItem(root)
            for profile in profiles:
                context = int(profile.get('context', 32768) or 32768)
                favorite = bool(profile.get('favorite'))
                name = ('★ ' if favorite else '') + profile.get('name', profile['id'])
                item = ModelTreeItem([name, '—', f'{context // 1024}K',
                                      '—', '—', '—',
                                      T(profile.get('purpose', '—'))])
                item.setData(0, Qt.ItemDataRole.UserRole, profile['id'])
                item.setData(2, Qt.ItemDataRole.UserRole, context)
                item.setFlags((item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
                              & ~Qt.ItemFlag.ItemIsDropEnabled)
                if favorite:
                    item.setForeground(0, QBrush(QColor('#ffd478')))
                item.setToolTip(0, T('★ Избранное' if favorite else 'Профиль модели') +
                                '\n' + T('Папка: ') + label)
                root.addChild(item)
            root.setExpanded(expanded.get(folder, True))
        self._tree_loading = False
        if hasattr(self, 'column_sort'):
            column, order = self.column_sort
            self.tree.sortItems(column, order)
        if selected:
            self.select_tree_alias(self.tree, selected)
        self.update_model_status_cells()

    def update_model_status_cells(self):
        palette = {
            'running': (T('● Запущена'), '#63d6ac'),
            'starting': (T('● Загрузка'), '#ffc578'),
            'error': (T('● Ошибка'), '#e58f9b'),
            'external': (T('● Порт занят'), '#ffc578'),
            'port_conflict': (T('● Порт занят'), '#ffc578'),
            'invalid_profile': (T('⚠ Исправить ID'), '#e58f9b'),
            'stopped': (T('● Остановлена'), '#a1b4cf'),
            'unstarted': (T('○ Не запущена'), '#91a4bc'),
        }
        states = multi.all_states()
        # The tree remains structurally stable during status changes.
        for item in self.iter_model_items():
            alias = item.data(0, Qt.ItemDataRole.UserRole)
            profile = self.profile_lookup(alias) or {}
            state = states.get(alias, {})
            status, color = palette.get(state.get('state', 'unstarted'),
                                        (T('○ Не запущена'), '#91a4bc'))
            item.setText(1, status)
            item.setForeground(1, QBrush(QColor(color)))
            live = bool(state.get('managed') and state.get('alive'))
            gpu = str(state.get('gpu') or profile.get('gpu') or T('авто'))
            item.setText(3, gpu if len(gpu) < 23 else gpu[:18] + '…')
            item.setToolTip(3, T('GPU: ') + gpu)
            port = state.get('port') if live else profile.get('port', 8080)
            item.setText(4, str(port))
            item.setText(5, str(state.get('pid')) if live and state.get('pid') else '—')
            item.setToolTip(4, T('Фактический порт процесса') if live
                            else T('Порт профиля'))
            try:
                numeric_port = int(port)
            except (TypeError, ValueError):
                numeric_port = -1
            item.setData(4, Qt.ItemDataRole.UserRole, numeric_port)
            item.setData(5, Qt.ItemDataRole.UserRole,
                         int(state.get('pid') or 0) if live else -1)
            for column in (3, 4, 5):
                item.setForeground(column, QBrush(QColor(
                    '#e9f0fb' if live else '#8295b1')))
        if hasattr(self, 'column_sort'):
            column, order = self.column_sort
            self.tree.sortItems(column, order)
        self.apply_model_filters()

    def on_model_selected(self, *_):
        p = self.selected_model_profile()
        if not p: return
        try: path = str(core.resolve_gguf(p)); presence = T('✓ GGUF найден')
        except Exception as exc: path = str(exc); presence = T('⚠ Проверить GGUF')
        state = multi.inspect(p['id'])
        purpose_display = T(p.get('purpose', '—'))
        self.model_info.setPlainText(
            T(f"{p['name']}\n\nНазначение: {purpose_display}\n"
            f"Alias: {p['id']}\nКлиент по умолчанию: {client_launcher.preferred_client(p)}\nКонтекст: {int(p['context']):,} токенов\n"
            f"GPU: {p.get('gpu') or 'автоматически'} · порт API: {p.get('port', 8080)}\n"
            f"Статус: {state.get('state')}\n"
            f"KV: {p.get('cache_type_k','q8_0')} / {p.get('cache_type_v','q8_0')}\n\n"
            f"{presence}\n{path}"))
        self.reset_log_view()
        self.refresh_model_action_button()
        self.refresh_preferred_client_button()

    def refresh_model_action_button(self):
        selected = self.selected_alias()
        if not selected: return
        state = multi.inspect(selected)
        status = state.get('state')
        if self.model_action_busy:
            text, style = T('⏳ Выполняется операция…'), 'background:#675225;border:1px solid #d0a13c;'
        elif status == 'running':
            text, style = T('🟢 Запущена — остановить эту модель'), 'background:#255b47;border:1px solid #56b790;'
        elif status == 'starting':
            text, style = T('🟡 Модель загружается — остановить'), 'background:#5a4a20;border:1px solid #d6b15b;'
        elif status in ('external','port_conflict'):
            owner = state.get('other_alias') or T('другим сервером')
            text, style = T(f'🟠 Порт занят ({owner}) — настроить'), 'background:#5a3f20;border:1px solid #d18d4b;'
        elif status == 'error':
            text, style = T('🔴 Ошибка — попробовать запустить снова'), 'background:#63333b;border:1px solid #ae5364;'
        else:
            p = self.selected_model_profile()
            text, style = T(f"⚪ Запустить на GPU {p.get('gpu') or 'авто'} · :{p.get('port',8080)}"), 'background:#245e9a;border:1px solid #438de1;'
        self.model_action_btn.setText(text)
        self.model_action_btn.setStyleSheet(style + 'font-weight:700;')

    def model_action(self):
        selected = self.selected_alias()
        if not selected or self.model_action_busy: return
        state = multi.inspect(selected)
        if state.get('state') in ('running', 'starting') and state.get('managed'):
            self.confirm_action(T(f'Остановить только {selected}?'), lambda: multi.stop(selected), after=self.finish_model_action)
        elif state.get('state') in ('external','port_conflict'):
            QMessageBox.information(self, T('Порт занят'), T(f"На порту {state.get('port')} работает другая модель или сервер. Откроется редактор — укажи свободный порт."))
            self.open_selected_in_editor()
        else:
            self.model_action_busy = True
            self.refresh_model_action_button()
            self.async_call(T('Загрузка ') + selected, lambda: multi.launch(selected), after=self.finish_model_action)

    def finish_model_action(self, ok, text):
        self.model_action_busy = False
        self.refresh_status()

    def reset_log_view(self):
        self.selected_log_alias = self.selected_alias() or ''
        self.live_logs.clear()
        self.log_offsets.pop(self.selected_log_alias, None)
        self.update_live_log()

    def clone_selected_model(self):
        alias = self.selected_alias()
        if not alias:
            return
        self.select_tree_alias(self.settings_tree, alias)
        self.clone_model()

    def delete_selected_model(self):
        alias = self.selected_alias()
        if not alias:
            return
        self.select_tree_alias(self.settings_tree, alias)
        self.delete_model()

    def build_services(self):
        w = QScrollArea()
        w.setWidgetResizable(True)
        content = QWidget()
        content.setMinimumHeight(640)
        l = QVBoxLayout(content)
        w.setWidget(content)
        label = QLabel(T('Все llama.cpp запускаются независимо по портам/GPU. Остановка одного не затрагивает другие серверы.'))
        label.setWordWrap(True); l.addWidget(label)
        self.instances_table = QTableWidget(0, 6)
        self.instances_table.setHorizontalHeaderLabels([T('Модель'), 'GPU', T('Порт'), T('Статус'), 'PID', T('Время работы')])
        self.instances_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.instances_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.instances_table.setMinimumHeight(190)
        self.instances_table.setMaximumHeight(270)
        self.instances_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.instances_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.instances_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.no_instances = QLabel(T('Нет активных экземпляров llama.cpp'))
        self.no_instances.setObjectName('Subheader')
        l.addWidget(self.no_instances)
        l.addWidget(self.instances_table)
        row = QHBoxLayout()
        row.addWidget(btn(T('📄 Лог выбранного'), self.open_selected_instance_log))
        row.addWidget(btn(T('⏹ Остановить выбранный экземпляр'), self.stop_selected_instance, danger=True))
        row.addWidget(btn(T('⏹ Остановить все llama.cpp'), self.stop_all_llama, danger=True))
        l.addLayout(row)
        self.service_labels = {}
        self.service_buttons = {}
        self.service_open_buttons = {}
        self.service_busy = set()
        self.builtin_services = [
            ('webui', 'Open WebUI · :3000', core.webui_start, core.webui_stop, self.open_webui),
            ('office', 'Agent Office', core.office_start, lambda: core.stop('office'), self.open_office),
            ('comfy', 'ComfyUI · :8188', core.comfy_start, lambda: core.stop('comfy'), lambda: self.open_service('comfy')),
        ]
        for sid, name, _start, _stop, open_action in self.builtin_services:
            group = QGroupBox(name)
            item = QHBoxLayout(group)
            lab = QLabel(T('Проверяется…'))
            self.service_labels[sid] = lab
            item.addWidget(lab, 1)
            toggle = btn(T('▶ Запустить'), lambda _checked=False, sid=sid: self.toggle_builtin_service(sid), primary=True)
            self.service_buttons[sid] = toggle
            item.addWidget(toggle)
            open_button = btn(T('Открыть'), open_action)
            self.service_open_buttons[sid] = open_button
            item.addWidget(open_button)
            item.addWidget(self.create_browser_mode_combo(sid))
            l.addWidget(group)

        custom_box = QGroupBox(T('Пользовательские AI-сервисы'))
        custom_layout = QVBoxLayout(custom_box)
        note = QLabel(T('Добавляй свои фоновые приложения: команда запуска, рабочая папка и адрес проверки готовности. Запуск без shell; остановка только подтверждённого PID.'))
        note.setWordWrap(True)
        custom_layout.addWidget(note)
        self.custom_services_table = QTableWidget(0, 5)
        self.custom_services_table.setHorizontalHeaderLabels([T('Сервис'), T('Статус'), 'PID', T('Управление'), T('Открыть')])
        self.custom_services_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.custom_services_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.custom_services_table.setMinimumHeight(150)
        self.custom_services_table.setMaximumHeight(340)
        self.custom_services_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.custom_services_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.custom_services_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.custom_services_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.custom_services_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        custom_layout.addWidget(self.custom_services_table)
        controls = QHBoxLayout()
        controls.addWidget(slim_btn(T('＋ Добавить сервис'), self.add_custom_service, primary=True))
        controls.addWidget(slim_btn(T('✎ Изменить сервис'), self.edit_custom_service))
        controls.addWidget(slim_btn(T('－ Удалить сервис'), self.delete_custom_service, danger=True))
        controls.addStretch()
        custom_layout.addLayout(controls)
        l.addWidget(custom_box)
        l.addWidget(btn(T('⏹ Остановить ВСЕ управляемые AI-сервисы'), self.stop_all, danger=True))
        self.refresh_custom_services()
        return w

    def builtin_state(self, sid, snapshot=None):
        snapshot = snapshot if snapshot is not None else core.get_status()
        if sid == 'webui':
            # A listening :3000 is not proof that AI Lab owns it.
            if core.verified('webui'):
                return 'running'
            try:
                service = core.settings().get('webui_service', 'open-webui.service')
                result = subprocess.run(['systemctl', '--user', 'is-active', service],
                                        text=True, capture_output=True, timeout=1.3)
                if result.returncode == 0 and result.stdout.strip() == 'active':
                    return 'running'
            except (OSError, subprocess.TimeoutExpired):
                pass
            return 'external' if snapshot.get('webui') else 'stopped'
        if sid == 'office':
            if core.verified('office'):
                return 'running'
            legacy = core.HOME / '.local/state/agent-office.pid'
            try:
                pid = int(legacy.read_text().strip())
                if pid > 1 and 'run.py' in core.cmdline(pid) and Path(f'/proc/{pid}/cwd').resolve() == core.office_path().resolve():
                    return 'external'
            except (OSError, ValueError):
                pass
            return 'stopped'
        if sid == 'comfy':
            if core.verified('comfy'):
                return 'running'
            return 'external' if snapshot.get('comfy') else 'stopped'
        return 'stopped'

    def update_builtin_services(self, snapshot):
        for sid, lab in self.service_labels.items():
            button = self.service_buttons[sid]
            if sid in self.service_busy:
                label, caption, color, enabled = T('⏳ Выполняется…'), T('⏳ Выполняется…'), '#ffc578', False
            else:
                state = self.builtin_state(sid, snapshot)
                if state == 'running':
                    label, caption, color, enabled = T('● Работает'), T('■ Остановить'), '#63d6ac', True
                elif state == 'external':
                    label, caption, color, enabled = T('● Внешний процесс'), T('Запущено извне'), '#ffc578', False
                else:
                    label, caption, color, enabled = T('○ Остановлен'), T('▶ Запустить'), '#a1b4cf', True
            lab.setText(label)
            lab.setStyleSheet('color:' + color + ';')
            button.setText(caption)
            button.setEnabled(enabled)
            if hasattr(self, 'service_open_buttons'):
                self.service_open_buttons[sid].setEnabled(sid not in self.service_busy)
            button.setStyleSheet('background:#63333b;border:1px solid #ae5364;' if 'Остановить' in caption or 'Stop' in caption else '')

    def toggle_builtin_service(self, sid):
        if sid in self.service_busy:
            return
        entry = next((v for v in self.builtin_services if v[0] == sid), None)
        if not entry:
            return
        _, name, start, stop, _ = entry
        state = self.builtin_state(sid)
        if state == 'external':
            QMessageBox.warning(self, T('Сервис запущен извне'), T('Этот процесс не управляется AI Model Lab. Автоматическая остановка запрещена.'))
            return
        if state == 'running' and QMessageBox.question(self, T('Подтверждение'), T(f'Остановить {name}?')) != QMessageBox.StandardButton.Yes:
            return
        self.service_busy.add(sid)
        self.update_builtin_services(core.get_status())
        task = stop if state == 'running' else start
        self.async_call(T(('Остановка ' if state == 'running' else 'Запуск ')) + name,
                        task, after=lambda ok, msg, sid=sid: self.builtin_done(sid))

    def builtin_done(self, sid):
        self.service_busy.discard(sid)
        self.refresh_status()

    def selected_custom_service(self):
        row = self.custom_services_table.currentRow()
        it = self.custom_services_table.item(row, 0) if row >= 0 else None
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def refresh_custom_services(self):
        if not hasattr(self, 'custom_services_table'):
            return
        selected = self.selected_custom_service()
        profiles = custom_services.list_profiles()
        self.custom_services_table.setRowCount(len(profiles))
        for row, p in enumerate(profiles):
            status = custom_services.inspect(p['id'])
            state = status['state']
            label = {
                'running': T('● Работает'), 'starting': T('● Загружается'),
                'error': T('● Ошибка'), 'stopped': T('○ Остановлен'),
            }.get(state, T('○ Остановлен'))
            for column, value in enumerate((p['name'], label, status.get('pid') if status.get('managed') else '—')):
                item = cell(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, p['id'])
                self.custom_services_table.setItem(row, column, item)
            action = btn(T('■ Остановить') if status.get('managed') else T('▶ Запустить'),
                         lambda _checked=False, sid=p['id']: self.toggle_custom_service(sid))
            action.setEnabled(p['id'] not in getattr(self, 'custom_busy', set()))
            self.custom_services_table.setCellWidget(row, 3, action)
            open_btn = btn(T('Открыть'), lambda _checked=False, url=p.get('open_url', ''): self.open_url(url))
            open_btn.setEnabled(bool(p.get('open_url')))
            self.custom_services_table.setCellWidget(row, 4, open_btn)
            if p['id'] == selected:
                self.custom_services_table.selectRow(row)

    def toggle_custom_service(self, sid):
        if not hasattr(self, 'custom_busy'):
            self.custom_busy = set()
        if sid in self.custom_busy:
            return
        current = custom_services.inspect(sid)
        is_running = bool(current.get('managed'))
        if is_running and QMessageBox.question(self, T('Подтверждение'), T(f'Остановить сервис {sid}?')) != QMessageBox.StandardButton.Yes:
            return
        self.custom_busy.add(sid)
        self.refresh_custom_services()
        fn = (lambda: custom_services.stop(sid)) if is_running else (lambda: custom_services.start(sid))
        self.async_call(T(('Остановка сервиса ' if is_running else 'Запуск сервиса ')) + sid,
                        fn, after=lambda ok, msg, sid=sid: self.custom_service_done(sid))

    def custom_service_done(self, sid):
        self.custom_busy.discard(sid)
        self.refresh_custom_services()

    def edit_service_dialog(self, original=None):
        p = original or {'id': '', 'name': '', 'command': [], 'cwd': '', 'health_url': '', 'open_url': ''}
        dialog = QDialog(self)
        dialog.setWindowTitle(T('Настройка AI-сервиса'))
        dialog.resize(660, 340)
        form = QFormLayout(dialog)
        fields = {}
        for key, title in [('id', 'ID / alias'), ('name', T('Название')), ('command', T('Команда запуска (аргументы)')),
                           ('cwd', T('Рабочий каталог')), ('health_url', T('URL проверки готовности (localhost)')),
                           ('open_url', T('URL для открытия'))]:
            val = ' '.join(__import__('shlex').quote(arg) for arg in p.get('command', [])) if key == 'command' else p.get(key, '')
            widget = QLineEdit(str(val or ''))
            if key == 'id' and original:
                widget.setReadOnly(True)
            if key == 'command':
                widget.setPlaceholderText('python3 -u main.py --port 8090')
            if key == 'health_url':
                widget.setPlaceholderText('http://127.0.0.1:8090/health')
            if key == 'open_url':
                widget.setPlaceholderText('http://127.0.0.1:8090')
            form.addRow(title, widget)
            fields[key] = widget
        explanation = QLabel(T('Команда запускается напрямую, без shell. Указывай только доверенные локальные программы. Запуск с правами пользователя.'))
        explanation.setWordWrap(True)
        form.addRow(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        form.addRow(buttons)
        buttons.rejected.connect(dialog.reject)
        def save():
            try:
                data = custom_services.validate({k: widget.text().strip() for k, widget in fields.items()})
                profiles = custom_services.list_profiles()
                if original:
                    profiles = [data if item['id'] == original['id'] else item for item in profiles]
                else:
                    profiles.append(data)
                custom_services.save_profiles(profiles)
                dialog.accept()
            except Exception as exc:
                QMessageBox.warning(dialog, T('Ошибка настройки'), str(exc))
        buttons.accepted.connect(save)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_custom_services()
            self.set_message(T('Профиль сервиса сохранён'))

    def add_custom_service(self):
        self.edit_service_dialog()

    def edit_custom_service(self):
        ident = self.selected_custom_service()
        p = custom_services.profile_of(ident) if ident else None
        if p:
            self.edit_service_dialog(p)

    def delete_custom_service(self):
        ident = self.selected_custom_service()
        if not ident:
            return
        if custom_services.inspect(ident)['managed']:
            QMessageBox.information(self, T('Сервис работает'), T('Сначала останови сервис, затем удаляй профиль.'))
            return
        if QMessageBox.question(self, T('Удаление'), T(f'Удалить профиль сервиса {ident}? Файлы приложения не удаляются.')) != QMessageBox.StandardButton.Yes:
            return
        profiles = [p for p in custom_services.list_profiles() if p['id'] != ident]
        custom_services.save_profiles(profiles)
        self.refresh_custom_services()

    def update_instances_table(self):
        from datetime import datetime
        previous = self.instances_table.item(self.instances_table.currentRow(), 0)
        selected_alias = previous.text() if previous else None
        items = list(multi.active_instances().items())
        self.instances_table.setRowCount(len(items))
        self.no_instances.setVisible(not items)
        for i, (alias, state) in enumerate(items):
            p = self.profile_lookup(alias) or {}
            since = str(state.get('started_at') or '')
            uptime = '—'
            if since:
                try:
                    elapsed = max(0, int((datetime.now() - datetime.fromisoformat(since)).total_seconds()))
                    uptime = f'{elapsed // 3600:02}:{(elapsed // 60) % 60:02}:{elapsed % 60:02}'
                except (ValueError, TypeError):
                    pass
            fields = [alias, state.get('gpu') or p.get('gpu') or T('авто'),
                      state.get('port', p.get('port', 8080)), state.get('state'),
                      state.get('pid') or '—', uptime]
            for j, value in enumerate(fields):
                self.instances_table.setItem(i, j, cell(value))
            if alias == selected_alias:
                self.instances_table.selectRow(i)

    def open_selected_instance_log(self):
        row = self.instances_table.currentRow()
        item = self.instances_table.item(row, 0) if row >= 0 else None
        if not item:
            return
        self.selected_log_alias = item.text()
        self.show_log_dialog(item.text())

    def stop_selected_instance(self):
        row = self.instances_table.currentRow()
        item = self.instances_table.item(row, 0) if row >= 0 else None
        if not item: return
        alias = item.text()
        self.confirm_action(T(f'Остановить только {alias}?'), lambda: multi.stop(alias))

    def stop_all_llama(self):
        self.confirm_action(T('Остановить все llama-server, запущенные AI Lab?'), multi.stop_all)

    def stop_all(self):
        def work():
            messages = [multi.stop_all(), core.stop('office'), core.stop('comfy'), core.webui_stop()]
            for profile in custom_services.list_profiles():
                if custom_services.inspect(profile['id']).get('managed'):
                    messages.append(custom_services.stop(profile['id']))
            return '\n'.join(messages)
        self.confirm_action(T('Остановить ВСЕ управляемые AI-сервисы?'), work)

    # ---------- Tests tab ----------
    def build_tests(self):
        w = QScrollArea()
        w.setWidgetResizable(True)
        content = QWidget()
        content.setMinimumHeight(580)
        l = QVBoxLayout(content)
        w.setWidget(content)
        options = QGroupBox(T('Встроенные бенчмарки (файлы и отчёты внутри AI Model Lab)'))
        form = QGridLayout(options)
        form.addWidget(QLabel(T('Испытание')), 0, 0)
        self.test_kind = QComboBox()
        for key, name in [
            ('speed', T('Скорость API — до 256 токенов')), ('speed512', T('Скорость API — до 512 токенов')),
            ('qa', T('Логика / арифметика (3 задачи)')), ('context8', T('Длинный контекст (около 8K)')),
            ('context32', T('Длинный контекст (около 32K)')), ('p1', 'Android LP-P1: STB UI → VOD'),
            ('p2', T('Android LP-P2: выбор плеера'))
        ]:
            self.test_kind.addItem(name, key)
        form.addWidget(self.test_kind, 0, 1, 1, 3)
        form.addWidget(QLabel(T('Экземпляр модели')), 1, 0)
        self.test_instance = QComboBox()
        form.addWidget(self.test_instance, 1, 1, 1, 3)
        form.addWidget(QLabel(T('Android-проект')), 2, 0)
        self.project = QLineEdit(self.settings_data.get('android_project', ''))
        form.addWidget(self.project, 2, 1, 1, 2)
        form.addWidget(btn(T('Обзор'), self.browse_project), 2, 3)
        form.addWidget(QLabel(T('Лимит времени, с')), 3, 0)
        self.timeout = QSpinBox()
        self.timeout.setRange(30, 7200)
        self.timeout.setValue(int(self.settings_data.get('benchmark_timeout', 1800)))
        form.addWidget(self.timeout, 3, 1)
        form.addWidget(QLabel(T('Лимит инструментов Pi')), 3, 2)
        self.budget = QSpinBox()
        self.budget.setRange(1, 200)
        self.budget.setValue(int(self.settings_data.get('tool_budget', 24)))
        form.addWidget(self.budget, 3, 3)
        row = QHBoxLayout()
        self.run_btn = btn(T('▶ Запустить испытание'), self.launch_test, True)
        row.addWidget(self.run_btn)
        self.cancel_btn = btn(T('⏹ Прервать испытание'), self.cancel_test, False, True)
        self.cancel_btn.setEnabled(False)
        row.addWidget(self.cancel_btn)
        row.addWidget(btn(T('📁 Папка отчётов'), lambda: self.open_url(core.REPORTS.as_uri())))
        l.addWidget(options)
        l.addLayout(row)
        warn = QLabel(T('⚠ Android: Pi получает только инструменты чтения, но это НЕ файловая песочница. Не запускай на секретных репозиториях без отдельной изоляции.'))
        warn.setWordWrap(True)
        l.addWidget(warn)
        self.test_output = QTextEdit()
        self.test_output.setReadOnly(True)
        self.test_output.setPlaceholderText(T('Здесь будет вывод теста, результаты записываются в папку data/reports/'))
        l.addWidget(self.test_output, 1)
        return w

    def browse_project(self):
        chosen = QFileDialog.getExistingDirectory(self, T('Выбрать Android-проект'), self.project.text() or str(Path.home()))
        if chosen:
            self.project.setText(chosen)

    def refresh_test_instances(self):
        previous = self.test_instance.currentData() if self.test_instance.count() else None
        self.test_instance.clear()
        for alias, state in multi.active_instances().items():
            if state.get('state') == 'running':
                self.test_instance.addItem(T(f"{alias} · GPU {state.get('gpu') or 'авто'} · :{state.get('port')}"), (alias, state['port']))
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
            QMessageBox.warning(self, T('Нет модели'), T('Сначала запусти llama-server с нужной моделью.'))
            return
        kind = self.test_kind.currentData()
        actual = 'speed' if kind.startswith('speed') else ('context' if kind.startswith('context') else kind)
        if actual in ('p1', 'p2'):
            try:
                if port != 8080:
                    raise RuntimeError(T('Android Pi local-lab сейчас настроен на порт 8080. API-тесты доступны на любом порту, Android — только на 8080 до изменения Pi provider.'))
                core.preflight_android()
            except Exception as exc:
                QMessageBox.warning(self, T('Проверка контекста'), str(exc))
                return
            if not Path(self.project.text()).is_dir():
                QMessageBox.warning(self, T('Android-проект'), T('Выбери существующий каталог.'))
                return
            if QMessageBox.question(self, T('Доступ Pi'), T('Испытание читает Android-проект через Pi read/grep/find/ls.\nЭто НЕ ОС-песочница. Продолжить?')) != QMessageBox.StandardButton.Yes:
                return
        profile = self.profile_lookup(alias) or {}
        args = [
            str(core.ROOT / 'bench.py'), '--kind', actual, '--model', alias, '--port', str(port), '--gpu', str(profile.get('gpu','')), '--timeout', str(self.timeout.value()),
            '--budget', str(self.budget.value()), '--project', self.project.text(),
            '--output-tokens', str(512 if kind == 'speed512' else 256),
            '--target-tokens', str(32768 if kind == 'context32' else 8192)
        ]
        self.test_output.append(T('▶ Тест ') + kind + ' · ' + alias)
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(str(core.ROOT))
        self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self.test_pipe)
        self.proc.finished.connect(self.test_finished)
        self.proc.start(sys.executable, args)
        if not self.proc.waitForStarted(2500):
            self.test_output.append(T('Не удалось запустить benchmark runner.'))
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
        self.test_output.append(T(f'\nПроцесс завершился: exit={exit_code}'))
        self.refresh_reports()

    def cancel_test(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            if QMessageBox.question(self, T('Прервать тест'), T('Прервать текущий эксперимент? Успевшие записаться события сохранятся.')) == QMessageBox.StandardButton.Yes:
                self.proc.terminate()

    # ---------- Reports tab ----------
    def build_results(self):
        w = QScrollArea()
        w.setWidgetResizable(True)
        content = QWidget()
        content.setMinimumHeight(560)
        l = QVBoxLayout(content)
        w.setWidget(content)
        row = QHBoxLayout()
        row.addWidget(btn(T('↻ Обновить отчёты'), self.refresh_reports))
        row.addWidget(btn(T('🔎 Сравнить два выбранных'), self.compare_reports))
        row.addWidget(slim_btn(T('🧹 Очистить старые'), self.cleanup_old_artifacts))
        row.addWidget(slim_btn(T('🗑 Очистить все отчёты'), self.clear_all_reports, danger=True))
        row.addStretch()
        l.addLayout(row)
        self.reports = QTableWidget(0, 6)
        self.reports.setHorizontalHeaderLabels([T('Дата/папка'), T('Модель'), T('Тест'), T('Статус'), T('Время, с'), 'VRAM, MiB'])
        self.reports.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.reports.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.reports.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.reports.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        l.addWidget(self.reports, 1)
        row2 = QHBoxLayout()
        row2.addWidget(btn(T('Показать summary.json'), self.show_report))
        row2.addWidget(btn(T('Открыть папку отчёта'), self.open_report_dir))
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
            QMessageBox.information(self, T('Сравнение'), T('Выбери ровно два отчёта (Ctrl + щелчок).'))
            return
        a, b = (core.load_json(p, {}) for p in files)
        ra = a.get('result', {})
        rb = b.get('result', {})
        equal = ra.get('prompt_sha256') and ra.get('prompt_sha256') == rb.get('prompt_sha256')
        kind_ok = a.get('kind') == b.get('kind')
        self.report_text.setPlainText(
            T('СРАВНЕНИЕ\n\n') + '\n'.join(f"{k}: {a.get(k)} | {b.get(k)}" for k in ('model', 'kind', 'elapsed_s')) +
            T(f"\n\nStatus: {ra.get('status')} | {rb.get('status')}\n"
            f"VRAM peak: {(a.get('hardware', {}).get('vram_mib') or {}).get('max')} | {(b.get('hardware', {}).get('vram_mib') or {}).get('max')} MiB\n"
            f"Энергия: {a.get('hardware', {}).get('gpu_energy_wh_estimate')} | {b.get('hardware', {}).get('gpu_energy_wh_estimate')} Wh\n"
            f"\nСопоставимость по SHA256: {'ДА' if equal else 'НЕТ'}; тип задания: {'одинаковый' if kind_ok else 'РАЗНЫЙ'}\n"
            'Разная версия промпта или разные условия не дают сравнивать качество напрямую.')
        )

    # ---------- Settings tab ----------
    # ---------- Profile editor ----------
    def profile_lookup(self, alias):
        return next((p for p in self.cfg.get('models',[]) if p.get('id') == alias), None)

    def build_settings(self):
        w = QScrollArea()
        w.setWidgetResizable(True)
        content = QWidget()
        content.setMinimumHeight(840)
        l = QVBoxLayout(content)
        w.setWidget(content)

        common = QGroupBox(T('Общие настройки программы и хранение данных'))
        grid = QGridLayout(common)
        self.set_inputs = {}
        common_fields = [
            ('android_project',T('Каталог Android-проекта')),('office_dir',T('Каталог Agent Office')),
            ('office_url','URL Agent Office'),('comfy_dir',T('Каталог ComfyUI')),
            ('webui_service',T('Служба WebUI')),('gpu_index',T('GPU для графика nvidia-smi')),
            ('client_workspace',T('Рабочая папка OpenCode / Pi'))
        ]
        for row, (key, label) in enumerate(common_fields):
            grid.addWidget(QLabel(label), row, 0)
            inp = QLineEdit(str(self.settings_data.get(key) or (str(Path.home()) if key == 'client_workspace' else '')))
            self.set_inputs[key] = inp
            if key == 'client_workspace':
                grid.addWidget(inp, row, 1, 1, 2)
                grid.addWidget(slim_btn(T('Обзор…'), self.browse_client_workspace), row, 3)
            else:
                grid.addWidget(inp, row, 1, 1, 3)

        retain_row = len(common_fields)
        grid.addWidget(QLabel(T('Хранить логи, дней (0 = без удаления)')), retain_row, 0)
        self.logs_retention = QSpinBox(); self.logs_retention.setRange(0, 3650)
        self.logs_retention.setValue(int(self.settings_data.get('logs_retention_days', 30)))
        grid.addWidget(self.logs_retention, retain_row, 1)
        grid.addWidget(QLabel(T('Хранить отчёты, дней (0 = без удаления)')), retain_row, 2)
        self.reports_retention = QSpinBox(); self.reports_retention.setRange(0, 3650)
        self.reports_retention.setValue(int(self.settings_data.get('reports_retention_days', 90)))
        grid.addWidget(self.reports_retention, retain_row, 3)

        cleanup_row = retain_row + 1
        grid.addWidget(slim_btn(T('🧹 Очистить старые логи и отчёты'), self.cleanup_old_artifacts), cleanup_row, 0)
        grid.addWidget(slim_btn(T('🧾 Очистить все логи'), self.clear_all_logs, danger=True), cleanup_row, 1)
        grid.addWidget(slim_btn(T('📊 Очистить все отчёты'), self.clear_all_reports, danger=True), cleanup_row, 2)
        grid.addWidget(slim_btn(T('💾 Сохранить настройки программы'), self.save_all_settings, primary=True), cleanup_row, 3)
        l.addWidget(common)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setMinimumHeight(500)
        l.addWidget(split, 1)

        left = QWidget(); lv = QVBoxLayout(left)
        self.settings_tree = QTreeWidget(); self.settings_tree.setColumnCount(2)
        self.settings_tree.setHeaderLabels(['ID',T('Название')])
        self.settings_tree.itemSelectionChanged.connect(self.load_selected_editor_model)
        lv.addWidget(self.settings_tree, 1)
        controls = QHBoxLayout()
        controls.setSpacing(6)
        controls.addWidget(slim_btn(T('＋ Добавить'), self.add_model, primary=True))
        controls.addWidget(slim_btn(T('⧉ Клонировать'), self.clone_model))
        controls.addWidget(slim_btn(T('－ Удалить'), self.delete_model, danger=True))
        controls.addStretch()
        lv.addLayout(controls)
        split.addWidget(left)

        right = QWidget(); rv = QVBoxLayout(right)
        self.editor_tabs = QTabWidget(); self.edit_fields = {}
        self.build_model_editor_form()
        rv.addWidget(self.editor_tabs, 1)
        sr = QHBoxLayout()
        self.autosave_checkbox = QCheckBox(T('Автосохранение профиля'))
        self.autosave_checkbox.setChecked(bool(self.settings_data.get('autosave_profiles', False)))
        self.autosave_checkbox.stateChanged.connect(self.toggle_autosave)
        sr.addWidget(self.autosave_checkbox)
        sr.addWidget(btn(T('💾 Сохранить профиль'), self.save_current_model, True))
        rv.addLayout(sr)
        self.editor_hint = QLabel(T('Изменения профиля не сохранены'))
        self.editor_hint.setObjectName('Subheader'); rv.addWidget(self.editor_hint)
        split.addWidget(right); split.setSizes([360, 840])
        note = QLabel(T('Сохранение не переписывает ~/.pi/agent/models.json. Для Android Pi проверь отдельно contextWindow, maxTokens и API-адрес. Очистка логов не удаляет журналы активных процессов.'))
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
        f.addRow('ID / alias',text('id')); f.addRow(T('Название'),text('name'))
        ef['preferred_client'] = QComboBox()
        ef['preferred_client'].addItem(T('Pi — легковесный агент'), 'pi')
        ef['preferred_client'].addItem(T('OpenCode — агент разработки'), 'opencode')
        f.addRow(T('Клиент по умолчанию'), ef['preferred_client'])
        ef['purpose']=QPlainTextEdit(); ef['purpose'].setMaximumHeight(90); f.addRow(T('Назначение'),ef['purpose'])
        f.addRow(T('Контекст (токены)'),spin('context',4096,524288,32768))
        f.addRow(T('Порт API'),spin('port',1024,65535,8080))
        ef['gpu'] = QComboBox()
        ef['gpu'].setEditable(True)
        ef['gpu'].setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        ef['gpu'].setToolTip(T('Для двух одинаковых GPU рекомендуется полный NVIDIA UUID. Также допустим индекс 0, 1…'))
        self.populate_gpu_choices()
        f.addRow(T('GPU (UUID или индекс)'), ef['gpu'])
        self.gpu_info=QPlainTextEdit()
        self.gpu_info.setReadOnly(True)
        self.gpu_info.setMinimumHeight(105)
        self.gpu_info.setMaximumHeight(145)
        self.gpu_info.setPlainText('\n'.join(multi.available_gpu_ids()) or T('GPU не обнаружены через nvidia-smi'))
        self.gpu_info.setToolTip(T('Фактические индексы, имена, UUID и VRAM из nvidia-smi'))
        f.addRow(T('Найденные GPU'),self.gpu_info)
        f.addRow('', btn(T('↻ Обновить список GPU'), self.refresh_gpu_inventory))
        f.addRow(T('Путь GGUF (относительный)'),text('path'))
        f.addRow(T('Шаблон GGUF'),text('match'))
        f.addRow(T('Доп. аргументы llama.cpp'),text('extra_args'))
        self.editor_scroll_tab(T('Основные'),basic)

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
        f.addRow('',check('no_kv_offload',T('KV cache в RAM (--no-kv-offload)')))
        cache_options=['q8_0','f16','q4_0','q4_1','q5_0','q5_1','iq4_nl']
        f.addRow('KV K',combo('cache_type_k',cache_options))
        f.addRow('KV V',combo('cache_type_v',cache_options))
        self.editor_scroll_tab(T('Память / KV'),memory)

        multi_tab=QWidget(); f=QFormLayout(multi_tab)
        f.addRow('MMProj GGUF',text('mmproj'))
        f.addRow('Image min tokens',spin('image_min_tokens',0,65535,0))
        f.addRow('',check('thinking_off',T('Отключить thinking (если поддерживается)')))
        f.addRow('',check('jinja',T('Использовать --jinja')))
        f.addRow('',check('reasoning_off',T('Использовать --reasoning off')))
        self.editor_scroll_tab(T('Мультимодальность'),multi_tab)

        for widget in ef.values():
            if isinstance(widget,(QLineEdit, QPlainTextEdit)):
                widget.textChanged.connect(self.mark_editor_dirty)
            elif isinstance(widget,(QSpinBox,QDoubleSpinBox)):
                widget.valueChanged.connect(self.mark_editor_dirty)
            elif isinstance(widget,QComboBox):
                widget.currentIndexChanged.connect(self.mark_editor_dirty)
                if widget.isEditable():
                    widget.editTextChanged.connect(self.mark_editor_dirty)
            elif isinstance(widget,QCheckBox):
                widget.stateChanged.connect(self.mark_editor_dirty)

    def populate_gpu_choices(self):
        picker = self.edit_fields['gpu']
        picker.clear()
        picker.addItem(T('Авто (llama.cpp выберет GPU)'), '')
        for entry in multi.gpu_inventory():
            idx, name, uuid, memory = entry['index'], entry['name'], entry['uuid'], entry['memory']
            picker.addItem(f"GPU {idx}: {name} ({memory}) · {uuid}", uuid)
            picker.setItemData(picker.count() - 1, T('Назначить только этот GPU по UUID'), Qt.ItemDataRole.ToolTipRole)
            picker.addItem(T(f"GPU {idx}: индекс {idx} (менее стабильно)"), str(idx))

    def refresh_gpu_inventory(self):
        selected = self.editor_gpu_value()
        self.populate_gpu_choices()
        index = self.edit_fields['gpu'].findData(selected)
        if index >= 0:
            self.edit_fields['gpu'].setCurrentIndex(index)
        else:
            self.edit_fields['gpu'].setEditText(selected)
        self.gpu_info.setPlainText('\n'.join(multi.available_gpu_ids()) or T('GPU не обнаружены через nvidia-smi'))

    def editor_gpu_value(self):
        picker = self.edit_fields['gpu']
        index = picker.currentIndex()
        if index >= 0 and picker.currentText() == picker.itemText(index):
            return str(picker.itemData(index) or '')
        return picker.currentText().strip()

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
            for k in ('id','name','path','match','mmproj'):
                set_line(k,profile.get(k,''))
            current_gpu = str(profile.get('gpu') or '')
            choice = ef['gpu'].findData(current_gpu)
            if choice >= 0:
                ef['gpu'].setCurrentIndex(choice)
            else:
                ef['gpu'].setEditText(current_gpu)
            ef['purpose'].setPlainText(profile.get('purpose',''))
            preferred = client_launcher.preferred_client(profile)
            choice = ef['preferred_client'].findData(preferred)
            ef['preferred_client'].setCurrentIndex(max(choice, 0))
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
            self.editor_hint.setText(T('Профиль загружен · настройки сохранены только после кнопки'))
        finally:
            self.editor_loading=False

    def mark_editor_dirty(self,*_):
        if self.editor_loading or not self.editor_current_alias: return
        self.editor_dirty=True
        self.editor_hint.setText(T('● Есть несохранённые изменения'))
        if self.autosave_checkbox.isChecked(): self.auto_timer.start(800)

    def toggle_autosave(self,*_):
        settings=core.settings(); settings['autosave_profiles']=self.autosave_checkbox.isChecked()
        core.atomic_json(core.SETTINGS,settings); self.settings_data=settings
        if self.autosave_checkbox.isChecked() and self.editor_dirty: self.auto_timer.start(800)

    def auto_save_pending(self):
        if self.editor_dirty and self.autosave_checkbox.isChecked(): self.save_current_model(silent=True)

    def confirm_discard_or_save(self):
        dialog=QMessageBox(self)
        dialog.setWindowTitle(T('Несохранённый профиль'))
        dialog.setText(T('Сохранить изменения перед переключением модели?'))
        yes=dialog.addButton(T('Сохранить'),QMessageBox.ButtonRole.AcceptRole)
        no=dialog.addButton(T('Не сохранять'),QMessageBox.ButtonRole.DestructiveRole)
        cancel=dialog.addButton(T('Отмена'),QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton()==yes: return self.save_current_model(silent=True)
        if dialog.clickedButton()==no: self.editor_dirty=False;return True
        return False

    def collect_editor_model(self):
        ef=self.edit_fields
        alias=multi.validate_alias(ef['id'].text().strip())
        original=self.profile_lookup(self.editor_current_alias) or {}
        profile=dict(original)
        for k in ('name','path','match','mmproj','purpose','extra_args'):
            value=ef[k].toPlainText().strip() if k=='purpose' else ef[k].text().strip()
            profile[k]=value
        profile['gpu'] = self.editor_gpu_value()
        profile['id']=alias
        profile['preferred_client'] = str(ef['preferred_client'].currentData())
        if profile['preferred_client'] not in client_launcher.CLIENTS:
            raise ValueError(T('Неподдерживаемый агентный клиент'))
        for k in ('context','port','ngl','n_cpu_moe','parallel','batch','ubatch','image_min_tokens'):
            profile[k]=int(ef[k].value())
        for k in ('flash_attn','no_kv_offload','thinking_off','jinja','reasoning_off'):
            profile[k]=ef[k].isChecked()
        for k in ('cache_type_k','cache_type_v'): profile[k]=ef[k].currentText()
        profile['sampling']={k:ef[k].value() for k in ('temp','top_p','top_k','min_p','repeat_penalty')}
        # Validate, but don't require file existence during editing/import.
        multi.port_of(profile); multi.gpu_of(profile)
        if not profile['path'] and not profile['match']:
            raise ValueError(T('Укажи путь к GGUF или шаблон для поиска'))
        if profile['ubatch']>profile['batch']:
            raise ValueError(T('Micro batch не может быть больше batch'))
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
                raise ValueError(T('Нельзя менять alias работающей модели — сначала останови её'))
            if any(p['id']==updated['id'] and p['id']!=alias for p in self.cfg.get('models',[])):
                raise ValueError(T('Этот ID уже используется'))
            new_models=[updated if p['id']==alias else p for p in self.cfg.get('models',[])]
            if len(new_models)!=len(self.cfg.get('models',[])):
                raise ValueError(T('Исходный профиль не найден'))
            obj={**self.cfg,'models':new_models}
            self.cfg=obj
            self.persist_profiles()
            self.editor_dirty=False;self.editor_current_alias=updated['id']
            self.populate_settings_tree();self.populate_model_tree()
            self.select_alias_in_trees(updated['id'])
            self.editor_hint.setText(T('✓ Профиль сохранён в models.json'))
            if not silent: QMessageBox.information(self,T('Профиль'),T('Изменения сохранены. Для уже запущенной модели применятся после перезапуска.'))
            return True
        except Exception as exc:
            QMessageBox.warning(self,T('Ошибка профиля'),str(exc))
            return False

    def maintain_model_profiles(self):
        """Preview every edit and removal; never modify GGUF files."""
        if self.editor_dirty and not self.confirm_discard_or_save():
            return
        try:
            states = multi.all_states()
            active = [alias for alias, state in states.items()
                      if state.get('managed') and state.get('alive')]
            if active:
                QMessageBox.warning(
                    self, T('Обслуживание профилей'),
                    T('Для безопасного изменения каталога сначала останови '
                      'управляемые модели:\n') + '\n'.join(active))
                return
            # Re-read from disk instead of a possibly stale GUI cache.
            actual = core.config()
            plan = model_maintenance.plan_maintenance(actual)
        except Exception as exc:
            QMessageBox.warning(self, T('Анализ профилей'), str(exc))
            return
        changed = plan['changes']
        suggestions = plan['suggested']
        duplicate = [x for x in suggestions if x['type'] == 'duplicate']
        missing = [x for x in suggestions if x['type'] == 'missing']
        if not changed and not suggestions:
            QMessageBox.information(self, T('Анализ профилей'),
                                    T('Изменений не требуется.') + '\n' +
                                    '\n'.join(plan['warnings'][:10]))
            return
        report_lines = [
            f"GGUF: {plan['found_files']}",
            f"Изменить профилей: {len(changed)}",
            f"Убрать дублирующих профилей: {len(duplicate)}",
            f"Отсутствующих GGUF (только предложение): {len(missing)}",
            "",
        ]
        for item in changed:
            after = item['after']
            report_lines.append(
                f"✎ {item['id']}\n"
                f"    {after.get('name')} — {after.get('purpose')}\n"
                f"    context={after.get('context')} "
                f"ngl={after.get('ngl')} GPU={after.get('gpu') or 'auto'}"
            )
        for item in suggestions:
            report_lines.append(f"⚠ {item['id']}: {item['reason']}")
        for warning in plan['warnings']:
            report_lines.append(f"! {warning}")
        dialog = QDialog(self)
        dialog.setWindowTitle(T('Проверить изменения профилей'))
        dialog.resize(850, 620)
        layout = QVBoxLayout(dialog)
        label = QLabel(T(
            'Изменяются только настройки профилей (models.json). '
            'Файлы GGUF не удаляются, модели не запускаются. '
            'Отсутствующие модели по умолчанию сохраняются.'
        ))
        label.setWordWrap(True)
        layout.addWidget(label)
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText('\n'.join(report_lines))
        layout.addWidget(preview, 1)
        duplicate_box = QCheckBox(T(
            'Удалить повторные профили с одинаковым GGUF (файлы не затрагивать)'
        ))
        duplicate_box.setEnabled(bool(duplicate))
        duplicate_box.setChecked(False)
        layout.addWidget(duplicate_box)
        missing_box = QCheckBox(T(
            'Также удалить профили с отсутствующим GGUF (файлы моделей не затрагивать)'
        ))
        missing_box.setEnabled(bool(missing))
        missing_box.setChecked(False)
        layout.addWidget(missing_box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(T('Применить'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(T('Отмена'))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            # Protect against updates made by another process since preview.
            if core.config() != actual:
                raise RuntimeError(T('models.json изменён после анализа; запусти проверку снова.'))
            data = model_maintenance.apply_selection(
                plan, remove_missing=missing_box.isChecked(),
                remove_duplicates=duplicate_box.isChecked())
            if data == actual:
                return
            backup = model_catalog.save_config(core.MODELS, data)
            self.cfg = data
            self.editor_loading = False
            self.editor_dirty = False
            self.editor_current_alias = None
            self.populate_settings_tree()
            self.populate_model_tree()
            self.set_message(T('Профили обновлены, резервная копия: ') + str(backup))
            QMessageBox.information(
                self, T('Профили обновлены'),
                T('Настройки сохранены. Для новых профилей проверь фактическое '
                  'потребление памяти и успешность запуска CUDA.'))
        except Exception as exc:
            QMessageBox.warning(self, T('Обновление профилей'), str(exc))

    def import_local_models(self):
        """Preview and import both Censored/Uncensored folders without touching GGUF."""
        if self.editor_dirty and not self.confirm_discard_or_save():
            return
        try:
            plan = model_catalog.plan_import(self.cfg)
        except Exception as exc:
            QMessageBox.warning(self, T('Поиск GGUF'), str(exc))
            return
        if not plan['found']:
            QMessageBox.information(
                self, T('Поиск GGUF'),
                T('GGUF не обнаружены. Проверь, что диски смонтированы и каталоги доступны.') +
                ('\n' + '\n'.join(plan['missing_roots']) if plan['missing_roots'] else ''))
            return
        new = plan['added']
        if not new:
            QMessageBox.information(
                self, T('Поиск GGUF'),
                T(f"Найдено {plan['found']} GGUF. Новых профилей нет, ничего не изменено."))
            return
        preview = '\n'.join('• ' + p['name'] + f" (порт {p['port']})" for p in new[:14])
        if len(new) > 14:
            preview += f"\n… и ещё {len(new) - 14}"
        if plan['warnings']:
            preview += '\n\n' + T('Требует проверки:') + '\n' + '\n'.join(plan['warnings'][:5])
        if plan['missing_roots']:
            preview += '\n\n' + T('Каталоги не доступны:') + '\n' + '\n'.join(plan['missing_roots'])
        answer = QMessageBox.question(
            self, T('Импорт локальных GGUF'),
            T(f"Обнаружено GGUF: {plan['found']}\nУже учтено: {len(plan['existing'])}\n"
              f"Новых профилей: {len(new)}\n\n")
            + preview + '\n\n' +
            T('Существующие профили сохраняются. GGUF не изменяются.\n'
              'Новые модели не запускаются автоматически.\n\nДобавить профили?'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            backup = model_catalog.save_config(core.MODELS, plan['config'])
            self.cfg = plan['config']
            self.editor_dirty = False
            self.editor_current_alias = None
            self.populate_settings_tree()
            self.populate_model_tree()
            self.set_message(T(f'Добавлено {len(new)} профилей GGUF; резервная копия: {backup or "не нужна"}'))
            QMessageBox.information(
                self, T('Импорт GGUF'),
                T(f'Добавлено {len(new)} профилей. Для запуска проверь контекст, GPU и mmproj.'))
        except Exception as exc:
            QMessageBox.warning(self, T('Ошибка сохранения моделей'), str(exc))

    def next_port(self):
        used={int(p.get('port',8080)) for p in self.cfg.get('models',[])}
        for port in range(8081,8400):
            if port not in used and not core.port_open(port): return port
        raise RuntimeError(T('Нет свободного порта для нового профиля'))

    def unique_alias(self,base):
        ids={p['id'] for p in self.cfg.get('models',[])}
        name=base;idx=2
        while name in ids:
            name=f'{base}-{idx}';idx+=1
        return name

    def add_model(self):
        if self.editor_dirty and not self.confirm_discard_or_save(): return
        alias=self.unique_alias('new-model')
        profile={'id':alias,'name':T('Новая модель'),'purpose':T('Укажи назначение'),'context':32768,
                 'port':self.next_port(),'gpu':'','path':'','match':'*.gguf',
                 'preferred_client':'pi',
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
        clone['name']=original.get('name',original['id'])+T(' (копия)')
        clone['port']=self.next_port()
        self.cfg['models'].append(clone)
        self.persist_profiles()
        self.populate_settings_tree();self.populate_model_tree()
        self.select_alias_in_trees(clone['id'])
        self.tabs.setCurrentIndex(4)
        QMessageBox.information(self,T('Копия модели'),T(f"Создан {clone['id']} на порту {clone['port']}.\nПроверь GPU: сейчас он скопирован из исходного профиля."))

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
            answer=QMessageBox.question(self,T('Удаление работающей модели'),
                T(f'Модель {alias} работает. Сначала остановить её, затем удалить профиль?\nРаботающие другие модели не пострадают.'))
            if answer==QMessageBox.StandardButton.Yes:
                self.async_call(T('Остановка перед удалением ')+alias,
                                lambda:multi.stop(alias),
                                after=lambda ok,txt:actual_delete() if ok and not multi.inspect(alias).get('alive') else None)
            return
        if QMessageBox.question(self,T('Удаление'),T(f'Удалить профиль {alias}? GGUF-файл останется на диске.'))==QMessageBox.StandardButton.Yes:
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

    def browse_client_workspace(self):
        current = self.set_inputs['client_workspace'].text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, T('Рабочая папка клиентов OpenCode и Pi'), current)
        if chosen:
            self.set_inputs['client_workspace'].setText(chosen)

    def save_all_settings(self):
        data = core.settings()
        data.update({k: w.text().strip() for k, w in self.set_inputs.items()})
        if hasattr(self, 'logs_retention'):
            data['logs_retention_days'] = int(self.logs_retention.value())
        if hasattr(self, 'reports_retention'):
            data['reports_retention_days'] = int(self.reports_retention.value())
        core.atomic_json(core.SETTINGS, data)
        self.settings_data = data
        self.apply_retention_cleanup(startup=True)
        self.refresh_reports()
        QMessageBox.information(self, T('Настройки'), T('Настройки программы сохранены. Профили сохраняются отдельно.'))

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
        if not details: details = [T('Нет данных NVIDIA')]
        details.append(f"RAM {ram.get('ram',0):.1f}/{ram.get('ram_total',0):.1f} GiB · Swap {ram.get('swap',0):.1f} GiB")
        self.metrics_label.setText('\n'.join(details))
        state=core.get_status()
        self.update_builtin_services(state)
        self.refresh_custom_services()
        running=[k for k,v in multi.all_states().items() if v.get('state')=='running' and v.get('managed')]
        self.setWindowTitle(T(f'AI Model Lab — KDE · работающих моделей: {len(running)}'))
        self.status_label.setText(T('Работают: ')+(', '.join(running) if running else T('нет')))
        self.update_model_status_cells()
        self.update_instances_table()
        self.refresh_model_action_button()
        self.refresh_test_instances()

    def closeEvent(self,event):
        if self.shutdown_job and self.shutdown_job.isRunning():
            event.ignore()
            return
        if self.exit_requested:
            if any(job.isRunning() for job in self.jobs):
                QMessageBox.information(self,T('Идёт операция'),T('Дождись завершения загрузки или остановки серверов. Можно свернуть программу в трей.'))
                self.exit_requested=False; event.ignore(); return
            if self.editor_dirty and not self.confirm_discard_or_save():
                self.exit_requested=False; event.ignore(); return
            if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:
                QMessageBox.information(self,T('Активный тест'),T('Сначала останови активное испытание.'))
                self.exit_requested=False; event.ignore(); return
            if self.tray: self.tray.hide()
            event.accept()
            return
        dialog=QMessageBox(self)
        dialog.setWindowTitle(T('Закрыть AI Model Lab?'))
        dialog.setText(T('Выбери способ выхода. Управляемые серверы можно оставить или остановить.'))
        tray_btn=None
        if self.tray and self.tray.isVisible():
            tray_btn=dialog.addButton(T('Свернуть в трей'),QMessageBox.ButtonRole.AcceptRole)
        exit_btn=dialog.addButton(T('Закрыть приложение (серверы оставить)'),QMessageBox.ButtonRole.ActionRole)
        shutdown_btn=dialog.addButton(T('Закрыть и остановить все'),QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn=dialog.addButton(T('Отмена'),QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        clicked=dialog.clickedButton()
        if tray_btn and clicked==tray_btn:
            event.ignore(); self.hide()
            self.tray.showMessage('AI Model Lab',T('Приложение работает в трее; серверы продолжают работу.'),
                                  QSystemTrayIcon.MessageIcon.Information,3000)
        elif clicked==exit_btn:
            if any(job.isRunning() for job in self.jobs):
                QMessageBox.information(self,T('Идёт операция'),T('Пока идёт операция, приложение можно свернуть в трей.'))
                event.ignore(); return
            if self.editor_dirty and not self.confirm_discard_or_save():
                event.ignore(); return
            if self.proc and self.proc.state()!=QProcess.ProcessState.NotRunning:
                QMessageBox.information(self,T('Активный тест'),T('Сначала останови активное испытание.'))
                event.ignore(); return
            self.exit_requested=True
            if self.tray: self.tray.hide()
            event.accept()
        elif clicked==shutdown_btn:
            event.ignore()
            self.request_full_exit()
        else:
            event.ignore()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('AI Model Lab')
    app.setOrganizationName('AI Model Lab Local')
    window = Window()
    app._ai_lab_window = window
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
