# -*- coding: utf-8 -*-
"""
交叉对比页：基准清单 + 多个待对比清单，配置键列与对比列后执行。
"""

import traceback
import os
from typing import Optional
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QGroupBox,
    QListWidget,
    QMessageBox,
    QLineEdit,
    QCheckBox,
    QSpinBox,
    QScrollArea,
    QFrame,
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt

from ui.widgets import FilePathRow, ColumnSelector, ProgressWidget

try:
    from core.parsers import load_table_from_file, ParserError
    from core.diff import DiffEngine, DiffResult
    from config import DIFF_DELETED
except ImportError:
    load_table_from_file = None
    ParserError = Exception
    DiffEngine = None
    DiffResult = None
    DIFF_DELETED = "deleted"


class CrossCompareWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(list)  # List[DiffResult]
    error = pyqtSignal(str)

    def __init__(
        self,
        base_path: str,
        other_paths: list,
        key_cols: list,
        compare_cols: list,
        max_rows: int = 0,
        compare_by_position: bool = False,
        compare_key_common_only: bool = False,
        missing_items_only: bool = False,
        header_rows: Optional[int] = None,
        skip_top_rows: int = 0,
    ):
        super().__init__()
        self.base_path = base_path
        self.other_paths = other_paths
        self.key_cols = key_cols
        self.compare_cols = compare_cols
        self.max_rows = max_rows
        self.compare_by_position = compare_by_position
        self.compare_key_common_only = compare_key_common_only
        self.missing_items_only = missing_items_only
        self.header_rows = header_rows
        self.skip_top_rows = skip_top_rows

    def run(self):
        try:
            kw = {}
            if self.max_rows and self.max_rows > 0:
                kw["max_rows"] = self.max_rows
            if self.header_rows is not None and self.header_rows > 0:
                kw["header_rows"] = self.header_rows
            if self.skip_top_rows and self.skip_top_rows > 0:
                kw["skip_top_rows"] = self.skip_top_rows
            self.progress.emit(10, "加载基准表...")
            base_df, _, _ = load_table_from_file(self.base_path, **kw)
            other_dfs = []
            n = len(self.other_paths)
            for i, p in enumerate(self.other_paths):
                self.progress.emit(20 + 60 * i // max(1, n), f"加载清单 {i+1}/{n}...")
                df, _, _ = load_table_from_file(p, **kw)
                other_dfs.append(df)
            self.progress.emit(80, "执行交叉对比...")
            # 默认参与对比的列：两表共有且排除内部列，避免只比行号导致“全未变”
            def _data_columns(base, other):
                return [c for c in base.columns if c in other.columns and c not in ("__row_index__", "__diff_type__", "__changed_fields__")]
            if self.missing_items_only:
                if not self.key_cols:
                    raise Exception("缺项检测需要先选择键列。")
                # 只输出“少了哪一项”：以两表中行数更多的为基准，找出另一表缺少的键，并标注基准行号
                engine = DiffEngine(key_columns=list(self.key_cols), compare_columns=[])
                results = []
                for idx, df in enumerate(other_dfs):
                    p_other = self.other_paths[idx] if idx < len(self.other_paths) else ""
                    # 以行数更多的文件为基准
                    if len(base_df) >= len(df):
                        more_df, more_path = base_df, self.base_path
                        less_df, less_path = df, p_other
                    else:
                        more_df, more_path = df, p_other
                        less_df, less_path = base_df, self.base_path

                    keys = list(self.key_cols)
                    key_to_more = {engine._row_key(more_df.iloc[i], keys): i for i in range(len(more_df))}
                    key_to_less = {engine._row_key(less_df.iloc[i], keys): i for i in range(len(less_df))}
                    missing_keys = [k for k in key_to_more.keys() if k not in key_to_less]

                    res = DiffResult()
                    base_name = os.path.basename(more_path) if more_path else "基准"
                    missing_in_name = os.path.basename(less_path) if less_path else "待对比"
                    extra_cols = ["__base_file__", "__missing_in__", "__base_row__"]
                    res.columns = list(more_df.columns) + [c for c in extra_cols if c not in more_df.columns]
                    res.key_columns = keys
                    res.compare_columns = []
                    res.count_deleted = len(missing_keys)
                    for k in missing_keys:
                        i_more = key_to_more[k]
                        row_dict = more_df.iloc[i_more].to_dict()
                        row_dict["__base_file__"] = base_name
                        row_dict["__missing_in__"] = missing_in_name
                        row_dict["__base_row__"] = int(i_more) + 1  # 1-based 行号
                        row_dict["__diff_type__"] = DIFF_DELETED
                        row_dict["__changed_fields__"] = []
                        row_dict["__changes_detail__"] = "缺少该项"
                        res.rows.append(row_dict)
                    results.append(res)
                self.progress.emit(100, "完成")
                self.finished.emit(results)
                return
            # 仅对比两表共有键的行：按键列对齐，不按行号，行数不同时只对共有键做差异化
            if self.compare_key_common_only and self.key_cols:
                keys_for_engine = list(self.key_cols)
            elif self.compare_by_position:
                keys_for_engine = []
            else:
                use_row_index = (
                    self.max_rows and self.max_rows > 0
                    and "__row_index__" in base_df.columns
                )
                keys_for_engine = list(self.key_cols) + ["__row_index__"] if use_row_index else self.key_cols
            engine = DiffEngine(key_columns=keys_for_engine, compare_columns=self.compare_cols or [])
            results = []
            for df in other_dfs:
                compare_cols_i = self.compare_cols or _data_columns(base_df, df)
                # 行数不同且只比共同项：先按键列取交集并对齐，避免产生新增/删除
                if self.compare_key_common_only and self.key_cols:
                    keys = list(self.key_cols)
                    key_to_base = {engine._row_key(base_df.iloc[i], keys): i for i in range(len(base_df))}
                    key_to_other = {engine._row_key(df.iloc[i], keys): i for i in range(len(df))}
                    common_keys = [k for k in key_to_base if k in key_to_other]
                    base_aligned = base_df.iloc[[key_to_base[k] for k in common_keys]].reset_index(drop=True)
                    other_aligned = df.iloc[[key_to_other[k] for k in common_keys]].reset_index(drop=True)
                    res = engine.compare_two_tables(base_aligned, other_aligned, keys=keys, compare_cols=compare_cols_i)
                else:
                    res = engine.compare_two_tables(base_df, df, keys=keys_for_engine, compare_cols=compare_cols_i)
                results.append(res)
            self.progress.emit(100, "完成")
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e) + "\n" + traceback.format_exc())


class TabCrossCompare(QWidget):
    result_ready = pyqtSignal(list)  # List[DiffResult]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._columns = []
        self._setup_ui()

    def _setup_ui(self):
        # 使用滚动区域，避免内容过高时基准清单等被遮挡
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(400)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(0, 0, 8, 0)

        g_files = QGroupBox("文件")
        fl = QVBoxLayout(g_files)
        self.base_file = FilePathRow("基准清单（旧）：")
        self.base_file.path_changed.connect(self._on_base_selected)
        fl.addWidget(self.base_file)
        fl.addWidget(QLabel("待对比清单（可多选文件）："))
        self.others_list = QListWidget()
        self.others_list.setMinimumHeight(100)
        self.others_list.setAlternatingRowColors(True)
        fl.addWidget(self.others_list)
        h_btn = QHBoxLayout()
        add_btn = QPushButton("添加文件…")
        add_btn.clicked.connect(self._add_other)
        remove_btn = QPushButton("移除选中")
        remove_btn.clicked.connect(self._remove_other)
        h_btn.addWidget(add_btn)
        h_btn.addWidget(remove_btn)
        h_btn.addStretch()
        fl.addLayout(h_btn)
        hdr_row = QHBoxLayout()
        hdr_row.addWidget(QLabel("表头占用行数："))
        self.header_rows_spin = QSpinBox()
        self.header_rows_spin.setRange(0, 10)
        self.header_rows_spin.setValue(0)
        self.header_rows_spin.setToolTip(
            "从文件当前起点起，连续几行合并为列名（不是「第几行是表头」）。\n"
            "1=仅第1行为表头，数据从第2行起；2=第1～2行合并为表头，数据从第3行起。\n"
            "0=Excel 自动检测表头行数。"
        )
        hdr_row.addWidget(self.header_rows_spin)
        hdr_row.addWidget(QLabel("跳过顶部行数："))
        self.skip_top_spin = QSpinBox()
        self.skip_top_spin.setRange(0, 50)
        self.skip_top_spin.setValue(0)
        self.skip_top_spin.setToolTip(
            "先丢弃文件最上面若干行再识别表头。例如第1行为大标题、第2行才是列名时填 1，"
            "且「表头占用行数」填 1。"
        )
        hdr_row.addWidget(self.skip_top_spin)
        btn_refresh_hdr = QPushButton("刷新表头列")
        btn_refresh_hdr.setToolTip("按当前「表头占用行数」「跳过顶部行数」重新读取基准文件表头，无需重新选文件")
        btn_refresh_hdr.clicked.connect(lambda: self._refresh_base_columns(True))
        hdr_row.addWidget(btn_refresh_hdr)
        hdr_row.addStretch()
        fl.addLayout(hdr_row)
        fl.addWidget(
            QLabel(
                "说明：填「2」表示用第1、2行合并成列名，数据从第3行开始——若您本意是「只有第2行是表头」，"
                "请把「跳过顶部行数」设为 1，「表头占用行数」设为 1。"
            )
        )
        self.header_rows_spin.valueChanged.connect(lambda _=None: self._refresh_base_columns(False))
        self.skip_top_spin.valueChanged.connect(lambda _=None: self._refresh_base_columns(False))
        fl.addWidget(QLabel("最大读取行数（仅 Excel，留空自动；若只读到 2 千多行可填如 120000）："))
        self.max_rows_edit = QLineEdit()
        self.max_rows_edit.setPlaceholderText("例如 120000，留空不限制")
        fl.addWidget(self.max_rows_edit)
        layout.addWidget(g_files)

        g_cols = QGroupBox("键列与对比列")
        fl2 = QVBoxLayout(g_cols)
        self.missing_items_only_cb = QCheckBox("缺项检测（以行数更多的文件为基准，找出另一份缺少的项并标注基准行号）")
        self.missing_items_only_cb.setToolTip("勾选后将只输出“少了哪一项”，不做逐列差异对比；需要先选择键列。")
        fl2.addWidget(self.missing_items_only_cb)
        self.compare_key_common_only_cb = QCheckBox("仅对比两表共有键的行（行数不同时勾选，按键列对齐后只对共有键做差异化）")
        self.compare_key_common_only_cb.setToolTip("勾选后：按所选键列匹配行，只对「基准与待对比文件中键列值相同的行」做差异化比对；仅存在于基准的行标为删除，仅存在于待对比的标为新增。行数不同时推荐勾选。")
        fl2.addWidget(self.compare_key_common_only_cb)
        self.compare_by_position_cb = QCheckBox("按行号逐行对比（不按键列合并；键列相同但后续列不同时勾选）")
        self.compare_by_position_cb.setToolTip("勾选后：第1行对第1行、第2行对第2行…不按键列合并，适合键列重复但每行数据不同的表")
        fl2.addWidget(self.compare_by_position_cb)
        fl2.addWidget(QLabel("键列（用于匹配同一行；「仅对比共有键」或未勾选按行号时生效）："))
        self.key_selector = ColumnSelector()
        fl2.addWidget(self.key_selector)
        fl2.addWidget(QLabel("参与对比的列（空则除键列外全部）："))
        self.compare_selector = ColumnSelector()
        fl2.addWidget(self.compare_selector)
        layout.addWidget(g_cols)

        self.progress = ProgressWidget()
        layout.addWidget(self.progress)
        btn = QPushButton("执行交叉对比")
        btn.clicked.connect(self._run)
        layout.addWidget(btn)
        layout.addStretch()

        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _on_base_selected(self, path: str):
        self._refresh_base_columns(False)

    def _refresh_base_columns(self, show_ok: bool):
        path = self.base_file.path()
        if not path or not load_table_from_file:
            return
        try:
            hr = self.header_rows_spin.value() if self.header_rows_spin.value() > 0 else None
            sk = int(self.skip_top_spin.value())
            kw = {}
            if hr is not None:
                kw["header_rows"] = hr
            if sk > 0:
                kw["skip_top_rows"] = sk
            old_k = self.key_selector.get_selected()
            old_c = self.compare_selector.get_selected()
            _, cols, _ = load_table_from_file(path, **kw)
            self._columns = cols
            self.key_selector.set_columns(cols)
            self.compare_selector.set_columns(cols)
            for name in old_k:
                for i in range(self.key_selector.available.count()):
                    it = self.key_selector.available.item(i)
                    if it and it.text() == name:
                        it.setSelected(True)
                        break
                self.key_selector._add()
            for name in old_c:
                for i in range(self.compare_selector.available.count()):
                    it = self.compare_selector.available.item(i)
                    if it and it.text() == name:
                        it.setSelected(True)
                        break
                self.compare_selector._add()
            if show_ok:
                QMessageBox.information(self, "提示", f"已刷新，共 {len(cols)} 列。")
        except Exception as e:
            QMessageBox.warning(self, "提示", f"无法读取表头：{e}")

    def _add_other(self):
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", "", "支持格式 (*.xlsx *.xls *.csv *.tsv *.docx);;所有 (*.*)")
        if path:
            self.others_list.addItem(path)

    def _remove_other(self):
        for item in list(self.others_list.selectedItems()):
            self.others_list.takeItem(self.others_list.row(item))

    def _run(self):
        base_path = self.base_file.path()
        if not base_path:
            QMessageBox.warning(self, "提示", "请选择基准清单。")
            return
        other_paths = [self.others_list.item(i).text() for i in range(self.others_list.count())]
        if not other_paths:
            QMessageBox.warning(self, "提示", "请至少添加一个待对比清单。")
            return
        key_cols = self.key_selector.get_selected()
        compare_cols = self.compare_selector.get_selected()
        compare_by_position = self.compare_by_position_cb.isChecked()
        compare_key_common_only = self.compare_key_common_only_cb.isChecked()
        missing_items_only = self.missing_items_only_cb.isChecked()
        if missing_items_only and not key_cols:
            QMessageBox.warning(self, "提示", "勾选「缺项检测」时请先选择键列。")
            return
        if missing_items_only:
            # 缺项检测优先：不再按行号/共同项差异对比
            compare_by_position = False
            compare_key_common_only = False
        if compare_key_common_only and not key_cols:
            QMessageBox.warning(self, "提示", "勾选「仅对比两表共有键的行」时请先选择键列。")
            return
        if compare_key_common_only and compare_by_position:
            compare_by_position = False
        header_rows = self.header_rows_spin.value() if self.header_rows_spin.value() > 0 else None
        skip_top_rows = int(self.skip_top_spin.value())
        max_rows = 0
        try:
            t = self.max_rows_edit.text().strip()
            if t:
                max_rows = int(t)
        except ValueError:
            pass
        self.progress.set_busy("交叉对比中...")
        self._worker = CrossCompareWorker(
            base_path,
            other_paths,
            key_cols,
            compare_cols,
            max_rows=max_rows,
            compare_by_position=compare_by_position,
            compare_key_common_only=compare_key_common_only,
            missing_items_only=missing_items_only,
            header_rows=header_rows,
            skip_top_rows=skip_top_rows,
        )
        self._worker.progress.connect(self.progress.set_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, results: list):
        self.progress.set_idle("完成")
        self.result_ready.emit(results)

    def _on_error(self, err: str):
        self.progress.set_idle("出错")
        QMessageBox.critical(self, "错误", err)
