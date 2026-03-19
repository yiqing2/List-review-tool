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
    QSpinBox,
    QLineEdit,
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

    def __init__(
        self,
        path: str,
        rule_ids: list,
        header_rows=None,
        skip_top_rows: int = 0,
        max_rows: int = 0,
    ):
        super().__init__()
        self.path = path
        self.rule_ids = rule_ids
        self.header_rows = header_rows
        self.skip_top_rows = skip_top_rows
        self.max_rows = max_rows

    def run(self):
        try:
            self.progress.emit(20, "加载文件...")
            kwargs = {}
            if self.header_rows is not None and self.header_rows > 0:
                kwargs["header_rows"] = self.header_rows
            if self.skip_top_rows and self.skip_top_rows > 0:
                kwargs["skip_top_rows"] = self.skip_top_rows
            if self.max_rows and self.max_rows > 0:
                kwargs["max_rows"] = self.max_rows
            df, _, _ = load_table_from_file(self.path, **kwargs)
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
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("表头占用行数："))
        self.header_rows_spin = QSpinBox()
        self.header_rows_spin.setRange(0, 10)
        self.header_rows_spin.setValue(0)
        self.header_rows_spin.setToolTip(
            "0=Excel 自动检测表头行数。\n"
            "1=仅第1行为表头，数据从第2行起；2=第1～2行合并为表头，数据从第3行起。"
        )
        header_row.addWidget(self.header_rows_spin)
        header_row.addWidget(QLabel("跳过顶部行数："))
        self.skip_top_spin = QSpinBox()
        self.skip_top_spin.setRange(0, 50)
        self.skip_top_spin.setValue(0)
        self.skip_top_spin.setToolTip("例如第1行为大标题、第2行才是列名：跳过=1，表头=1")
        header_row.addWidget(self.skip_top_spin)
        header_row.addStretch()
        fl.addLayout(header_row)

        max_row = QHBoxLayout()
        max_row.addWidget(QLabel("最大读取行数（仅 Excel，留空自动）："))
        self.max_rows_edit = QLineEdit()
        self.max_rows_edit.setPlaceholderText("例如 120000，留空不限制")
        max_row.addWidget(self.max_rows_edit)
        fl.addLayout(max_row)
        fl.addWidget(
            QLabel(
                "说明：填 2 表示用第1、2行合并成列名，数据从第3行开始。若仅第2行是表头，请设 跳过顶部行数=1、表头占用行数=1。"
            )
        )
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
        max_rows_text = self.max_rows_edit.text().strip()
        max_rows = 0
        if max_rows_text:
            if not max_rows_text.isdigit() or int(max_rows_text) <= 0:
                QMessageBox.warning(self, "提示", "最大读取行数需为正整数，或留空。")
                return
            max_rows = int(max_rows_text)

        header_rows = self.header_rows_spin.value()
        skip_top_rows = self.skip_top_spin.value()
        ids = []
        for item in self.rule_list.selectedItems():
            text = item.text()
            if "(" in text and ")" in text:
                ids.append(text.split("(")[-1].rstrip(")"))
        self.progress.set_busy("校验中...")
        self._worker = ValidateWorker(
            path,
            ids,
            header_rows=header_rows if header_rows > 0 else None,
            skip_top_rows=skip_top_rows,
            max_rows=max_rows,
        )
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
