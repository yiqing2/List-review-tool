# -*- coding: utf-8 -*-
"""
规则校验页：上传文件，选择要应用的规则，执行校验，结果中高亮违规行与规则名。
"""

import traceback
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QGroupBox,
    QListWidget,
    QMessageBox,
)
from PyQt6.QtCore import QThread, pyqtSignal

from ui.widgets import FilePathRow, ProgressWidget

try:
    from core.parsers import load_table_from_file, ParserError
    from core.rules import RuleEngine
except ImportError:
    load_table_from_file = None
    ParserError = Exception
    RuleEngine = None


class ValidateWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object, object)  # df, violations
    error = pyqtSignal(str)

    def __init__(self, path: str, rule_ids: list):
        super().__init__()
        self.path = path
        self.rule_ids = rule_ids

    def run(self):
        try:
            self.progress.emit(20, "加载文件...")
            df, _, _ = load_table_from_file(self.path)
            self.progress.emit(50, "加载规则并校验...")
            engine = RuleEngine()
            engine.load_rules()
            violations = engine.validate_dataframe(df, rule_ids=self.rule_ids or None)
            self.progress.emit(100, "校验完成")
            self.finished.emit(df, violations)
        except Exception as e:
            self.error.emit(str(e) + "\n" + traceback.format_exc())


class TabRuleValidate(QWidget):
    result_ready = pyqtSignal(object, object)  # df, violations

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._setup_ui()
        self._refresh_rules()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        g = QGroupBox("待校验文件")
        fl = QVBoxLayout(g)
        self.file_row = FilePathRow("文件：")
        self.file_row.path_changed.connect(self._on_file_selected)
        fl.addWidget(self.file_row)
        layout.addWidget(g)

        g2 = QGroupBox("选择校验规则（不选则应用全部）")
        fl2 = QVBoxLayout(g2)
        self.rule_list = QListWidget()
        self.rule_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        fl2.addWidget(self.rule_list)
        layout.addWidget(g2)

        self.progress = ProgressWidget()
        layout.addWidget(self.progress)
        btn = QPushButton("执行校验")
        btn.clicked.connect(self._run)
        layout.addWidget(btn)
        layout.addStretch()

    def _refresh_rules(self):
        self.rule_list.clear()
        if not RuleEngine:
            return
        engine = RuleEngine()
        engine.load_rules()
        for r in engine.get_rules():
            self.rule_list.addItem(f"{r.name} ({r.rule_id})")

    def _on_file_selected(self, path: str):
        pass

    def _run(self):
        path = self.file_row.path()
        if not path:
            QMessageBox.warning(self, "提示", "请先选择文件。")
            return
        ids = []
        for item in self.rule_list.selectedItems():
            text = item.text()
            if "(" in text and ")" in text:
                ids.append(text.split("(")[-1].rstrip(")"))
        self.progress.set_busy("校验中...")
        self._worker = ValidateWorker(path, ids)
        self._worker.progress.connect(self.progress.set_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, df, violations):
        self.progress.set_idle("校验完成")
        self.result_ready.emit(df, violations)

    def _on_error(self, err: str):
        self.progress.set_idle("出错")
        QMessageBox.critical(self, "错误", err)

    def refresh_rules_list(self):
        self._refresh_rules()
