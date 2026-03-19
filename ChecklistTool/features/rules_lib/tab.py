# -*- coding: utf-8 -*-
"""
规则库管理页：默认只读；需要输入秘钥解锁编辑（添加/编辑/删除规则）。
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QInputDialog,
    QLineEdit,
    QTextEdit,
    QSplitter,
    QSpinBox,
    QFileDialog,
    QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal

from features.rules_lib.rule_tree_editor import RuleTreeEditor
from core.rules import RuleEngine, ValidationRule, RuleNode
from ui.widgets import FilePathRow

try:
    from core.parsers import load_table_from_file
except ImportError:
    load_table_from_file = None

try:
    from config.app_config import get_rules_edit_key, DEFAULT_RULES_EDIT_KEY
except Exception:
    def get_rules_edit_key() -> str:
        return "admin"
    DEFAULT_RULES_EDIT_KEY = "admin"


class TabRulesLib(QWidget):
    """规则库：列表 + 详情（条件树 + 说明）。默认只读，秘钥解锁编辑。"""
    rules_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._engine = RuleEngine()
        self._current_rule_id = None
        self._edit_unlocked = False
        self._setup_ui()
        self._load_rules()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        # 使用说明（规则库建立步骤）
        help_text = QLabel(
            "【使用说明】\n"
            "1. 点击「新增规则」输入规则名称，新规则会出现在左侧列表并自动选中。\n"
            "2. 右侧条件树默认有一个「根」节点；点击「添加根/子条件」可添加子条件，选中某节点后点「编辑」设置：字段（可手动输入列名，如 系统|专业）、运算符、值。\n"
            "3. 根节点可作为条件组，子节点为具体条件；编辑时「字段」选（无/根节点）表示该节点不参与单条判断。\n"
            "   若父节点既配置了字段又有子节点：语义为“父条件命中后，子节点必须满足”（即 A -> B）。\n"
            "4. 编辑完成后务必点击「保存当前规则」才会写入规则库；若列表为空可点「刷新列表」从文件重新加载。"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #444; background: #f5f5f5; padding: 6px; border-radius: 4px;")
        help_text.setMaximumHeight(90)
        layout.addWidget(help_text)
        self._path_label = QLabel("规则库保存位置：加载中…")
        self._path_label.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(self._path_label)
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("规则列表"))
        self.rule_list = QListWidget()
        self.rule_list.currentItemChanged.connect(self._on_rule_selected)
        left_layout.addWidget(self.rule_list)
        btn_refresh = QPushButton("刷新列表")
        btn_refresh.clicked.connect(self._load_rules)
        left_layout.addWidget(btn_refresh)
        split.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("规则详情与条件树"))
        right_layout.addWidget(QLabel("用于表头下拉的示例文件（可选）："))
        self.sample_file = FilePathRow("文件：")
        self.sample_file.path_changed.connect(self._on_sample_file_selected)
        right_layout.addWidget(self.sample_file)
        sample_opts = QHBoxLayout()
        sample_opts.addWidget(QLabel("表头占用行数："))
        self.sample_header_rows_spin = QSpinBox()
        self.sample_header_rows_spin.setRange(0, 10)
        self.sample_header_rows_spin.setValue(0)
        self.sample_header_rows_spin.setToolTip(
            "0=Excel 自动检测表头行数。\n"
            "1=仅第1行为表头；2=第1～2行合并为表头。"
        )
        sample_opts.addWidget(self.sample_header_rows_spin)
        sample_opts.addWidget(QLabel("跳过顶部行数："))
        self.sample_skip_top_rows_spin = QSpinBox()
        self.sample_skip_top_rows_spin.setRange(0, 50)
        self.sample_skip_top_rows_spin.setValue(0)
        self.sample_skip_top_rows_spin.setToolTip("例如第1行为大标题、第2行才是列名：跳过=1，表头=1")
        sample_opts.addWidget(self.sample_skip_top_rows_spin)
        self.btn_reload_sample_cols = QPushButton("按设置重读表头")
        self.btn_reload_sample_cols.clicked.connect(self._reload_sample_columns)
        sample_opts.addWidget(self.btn_reload_sample_cols)
        sample_opts.addStretch()
        right_layout.addLayout(sample_opts)
        self.sample_header_rows_spin.valueChanged.connect(lambda _=None: self._reload_sample_columns())
        self.sample_skip_top_rows_spin.valueChanged.connect(lambda _=None: self._reload_sample_columns())
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("规则说明（解锁编辑后可修改）")
        self.desc_edit.setMaximumHeight(80)
        right_layout.addWidget(self.desc_edit)
        self.tree_editor = RuleTreeEditor(columns=[])
        right_layout.addWidget(self.tree_editor)

        self.btn_unlock = QPushButton("解锁编辑（需秘钥）")
        self.btn_unlock.clicked.connect(self._toggle_unlock)
        right_layout.addWidget(self.btn_unlock)

        self.btn_add = QPushButton("新增规则")
        self.btn_add.clicked.connect(self._add_rule)
        self.import_template_combo = QComboBox()
        self.import_template_combo.addItem("模板1：基准列+case列（每行一条规则）", "template1")
        self.import_template_combo.addItem("模板2：多条件=>结果（每行一条规则）", "template2")
        self.btn_import_rules = QPushButton("导入规则表")
        self.btn_import_rules.clicked.connect(self._import_rules_by_template)
        self.btn_save = QPushButton("保存当前规则")
        self.btn_save.clicked.connect(self._save_rule)
        self.btn_del = QPushButton("删除当前规则")
        self.btn_del.clicked.connect(self._del_rule)
        h = QHBoxLayout()
        h.addWidget(self.btn_add)
        h.addWidget(self.import_template_combo)
        h.addWidget(self.btn_import_rules)
        h.addWidget(self.btn_save)
        h.addWidget(self.btn_del)
        right_layout.addLayout(h)

        self._apply_edit_lock()
        split.addWidget(right)
        layout.addWidget(split)

    def _apply_edit_lock(self):
        """根据解锁状态启用/禁用编辑控件。"""
        unlocked = bool(self._edit_unlocked)
        self.desc_edit.setReadOnly(not unlocked)
        # 条件树始终可查看/展开；仅在未解锁时禁用“添加/编辑/删除”等修改入口
        self.tree_editor.setEnabled(True)
        if hasattr(self.tree_editor, "set_editable"):
            self.tree_editor.set_editable(unlocked)
        self.btn_add.setEnabled(unlocked)
        self.import_template_combo.setEnabled(unlocked)
        self.btn_import_rules.setEnabled(unlocked)
        self.btn_save.setEnabled(unlocked)
        self.btn_del.setEnabled(unlocked)
        self.btn_unlock.setText("锁定编辑" if unlocked else "解锁编辑（需秘钥）")

    def _import_rules_by_template(self):
        tpl = self.import_template_combo.currentData() or "template1"
        if tpl == "template2":
            self._import_rules_template2()
            return
        self._import_rules_template1()

    def _toggle_unlock(self):
        if self._edit_unlocked:
            self._edit_unlocked = False
            self._apply_edit_lock()
            return
        key, ok = self._ask_text(
            title="解锁规则库编辑",
            label="请输入秘钥：",
            echo_mode=QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        expected = get_rules_edit_key()
        if not expected or expected.strip() == "":
            QMessageBox.warning(self, "提示", "未配置规则库编辑秘钥。请设置环境变量后重启程序。")
            return
        if key.strip() != expected:
            QMessageBox.warning(self, "提示", "秘钥错误，无法解锁编辑。")
            return
        self._edit_unlocked = True
        self._apply_edit_lock()
        if expected == DEFAULT_RULES_EDIT_KEY:
            QMessageBox.information(
                self,
                "提示",
                "你正在使用默认秘钥 admin。\n建议通过环境变量 CHECKLISTTOOL_RULES_EDIT_KEY 设置为你自己的秘钥。",
            )

    def _load_rules(self):
        """从文件重新加载规则并刷新列表。"""
        self._engine.load_rules()
        self._refresh_list_from_engine()
        self._path_label.setText("规则库保存位置：" + (self._engine.rules_file or "—"))

    def _refresh_list_from_engine(self):
        """仅根据当前内存中的规则刷新列表（不读文件），用于新增后立即显示。"""
        self.rule_list.clear()
        for r in self._engine.get_rules():
            item = QListWidgetItem(f"{r.name} ({r.rule_id})")
            item.setData(Qt.ItemDataRole.UserRole, r.rule_id)
            self.rule_list.addItem(item)

    def _on_rule_selected(self, current: QListWidgetItem, previous):
        if not current:
            self._current_rule_id = None
            return
        rule_id = current.data(Qt.ItemDataRole.UserRole) or ""
        for r in self._engine.get_rules():
            if r.rule_id == rule_id:
                self._current_rule_id = rule_id
                self.desc_edit.setPlainText(r.description or "")
                self.tree_editor.load_node(r.root)
                return
        self._current_rule_id = None

    def _add_rule(self):
        if not self._edit_unlocked:
            QMessageBox.warning(self, "提示", "规则库处于只读状态，请先点击“解锁编辑（需秘钥）”。")
            return
        name, ok = self._ask_text(title="新增规则", label="规则名称：")
        if not ok or not name.strip():
            return
        rule = ValidationRule(rule_id="", name=name.strip(), description="", root=RuleNode())
        self._engine.add_rule(rule)
        if not self._engine.save_rules():
            QMessageBox.warning(
                self, "提示",
                "规则保存失败。请检查程序目录或用户目录「清单对比校审工具/rules」是否可写。",
            )
            return
        self._path_label.setText("规则库保存位置：" + (self._engine.rules_file or "—"))
        # 从内存刷新列表，确保新规则立即显示
        self._refresh_list_from_engine()
        new_id = rule.rule_id
        for i in range(self.rule_list.count()):
            item = self.rule_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == new_id:
                self.rule_list.setCurrentRow(i)
                self._current_rule_id = new_id
                self.desc_edit.setPlainText(rule.description or "")
                self.tree_editor.load_node(rule.root)
                break
        self.rules_updated.emit()
        QMessageBox.information(self, "提示", "已添加规则，请编辑条件树后点击“保存当前规则”。")

    def _save_rule(self):
        if not self._edit_unlocked:
            QMessageBox.warning(self, "提示", "规则库处于只读状态，请先点击“解锁编辑（需秘钥）”。")
            return
        if not self._current_rule_id:
            QMessageBox.warning(self, "提示", "请先选择一条规则。")
            return
        for r in self._engine.get_rules():
            if r.rule_id == self._current_rule_id:
                r.description = self.desc_edit.toPlainText().strip()
                r.root = self.tree_editor.get_root_node()
                self._engine.save_rules()
                self.rules_updated.emit()
                self._path_label.setText("规则库保存位置：" + (self._engine.rules_file or "—"))
                QMessageBox.information(self, "提示", "已保存到：%s" % (self._engine.rules_file or ""))
                return
        QMessageBox.warning(self, "提示", "未找到当前规则。")

    def _import_rules_template1(self):
        """
        模板1导入：
        - 一列基准列（如 base_name）
        - 若干 case 列（如 case1, case2, case3）
        每行生成一条独立规则：base_col=base_val -> case_col1=v1 且 case_col2=v2 ...
        """
        if not self._edit_unlocked:
            QMessageBox.warning(self, "提示", "规则库处于只读状态，请先点击“解锁编辑（需秘钥）”。")
            return
        if not load_table_from_file:
            QMessageBox.warning(self, "提示", "缺少表格解析模块，无法导入。")
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择规则表（模板1）",
            "",
            "Excel 文件 (*.xlsx *.xls);;所有文件 (*.*)",
        )
        if not path:
            return

        try:
            kwargs = {}
            hr = self.sample_header_rows_spin.value()
            st = self.sample_skip_top_rows_spin.value()
            if hr > 0:
                kwargs["header_rows"] = hr
            if st > 0:
                kwargs["skip_top_rows"] = st
            df, cols, _ = load_table_from_file(path, **kwargs)
        except Exception as e:
            QMessageBox.warning(self, "提示", f"读取规则表失败：{e}")
            return

        usable_cols = [c for c in (cols or []) if c != "__source_row__"]
        if len(usable_cols) < 2:
            QMessageBox.warning(self, "提示", "规则表至少需要 2 列：1 列基准列 + 至少 1 列 case 列。")
            return

        default_base_col = "base_name" if "base_name" in usable_cols else usable_cols[0]
        base_col, ok = QInputDialog.getItem(
            self,
            "选择基准列",
            "请选择基准列（例如 base_name）：",
            usable_cols,
            max(0, usable_cols.index(default_base_col)),
            False,
        )
        if not ok or not base_col:
            return

        case_cols = [c for c in usable_cols if c != base_col]
        if not case_cols:
            QMessageBox.warning(self, "提示", "未找到 case 列，请检查模板内容。")
            return

        created_count = 0
        skipped_rows = 0
        last_rule_id = None

        import os
        file_base_name = os.path.splitext(os.path.basename(path))[0]

        for i, row in df.iterrows():
            base_raw = row.get(base_col, None)
            base_val = "" if base_raw is None else str(base_raw).strip()
            if base_val == "":
                skipped_rows += 1
                continue

            leaves = []
            for case_col in case_cols:
                v_raw = row.get(case_col, None)
                v = "" if v_raw is None else str(v_raw).strip()
                if v == "":
                    continue
                leaves.append(RuleNode(field=case_col, operator="eq", value=v, logic="and", children=[]))

            if not leaves:
                skipped_rows += 1
                continue

            source_row = row.get("__source_row__", None)
            row_mark = str(source_row).strip() if source_row is not None and str(source_row).strip() else str(int(i) + 2)
            rule_name = f"导入模板1_{file_base_name}_{base_val}_R{row_mark}"
            row_case_cols = [n.field for n in leaves]

            rule = ValidationRule(
                rule_id="",
                name=rule_name,
                description=f"模板1导入：基准列={base_col}, 基准值={base_val}",
                root=RuleNode(field=base_col, operator="eq", value=base_val, logic="and", children=leaves),
                target_columns=row_case_cols,
            )
            self._engine.add_rule(rule)
            created_count += 1
            last_rule_id = rule.rule_id

        if created_count == 0:
            QMessageBox.warning(self, "提示", "未导入任何规则：请检查基准列和 case 列是否有有效值。")
            return

        if not self._engine.save_rules():
            QMessageBox.warning(self, "提示", "导入后保存失败，请检查规则库路径是否可写。")
            return

        self._path_label.setText("规则库保存位置：" + (self._engine.rules_file or "—"))
        self._refresh_list_from_engine()
        self.set_columns_for_editor(usable_cols)

        if last_rule_id:
            for i in range(self.rule_list.count()):
                item = self.rule_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == last_rule_id:
                    self.rule_list.setCurrentRow(i)
                    break

        self.rules_updated.emit()
        QMessageBox.information(
            self,
            "提示",
            f"导入完成：新增规则 {created_count} 条。\n"
            f"跳过无效行: {skipped_rows} 条。",
        )

    def _import_rules_template2(self):
        """
        模板2导入：
        - 多个条件列（如 condition1/2/3）
        - 1个结果列（如 result）
        每行生成一条独立规则：当所有条件列同时满足该行值时，结果列必须等于该行值。
        """
        if not self._edit_unlocked:
            QMessageBox.warning(self, "提示", "规则库处于只读状态，请先点击“解锁编辑（需秘钥）”。")
            return
        if not load_table_from_file:
            QMessageBox.warning(self, "提示", "缺少表格解析模块，无法导入。")
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择规则表（模板2）",
            "",
            "Excel 文件 (*.xlsx *.xls);;所有文件 (*.*)",
        )
        if not path:
            return

        try:
            kwargs = {}
            hr = self.sample_header_rows_spin.value()
            st = self.sample_skip_top_rows_spin.value()
            if hr > 0:
                kwargs["header_rows"] = hr
            if st > 0:
                kwargs["skip_top_rows"] = st
            df, cols, _ = load_table_from_file(path, **kwargs)
        except Exception as e:
            QMessageBox.warning(self, "提示", f"读取规则表失败：{e}")
            return

        usable_cols = [c for c in (cols or []) if c != "__source_row__"]
        if len(usable_cols) < 2:
            QMessageBox.warning(self, "提示", "规则表至少需要 2 列：条件列 + 结果列。")
            return

        default_result_col = "result" if "result" in usable_cols else usable_cols[-1]
        result_col, ok = QInputDialog.getItem(
            self,
            "选择结果列",
            "请选择结果列（例如 result）：",
            usable_cols,
            max(0, usable_cols.index(default_result_col)),
            False,
        )
        if not ok or not result_col:
            return

        condition_cols = [c for c in usable_cols if c != result_col]
        if not condition_cols:
            QMessageBox.warning(self, "提示", "未找到条件列，请检查模板内容。")
            return

        created_count = 0
        skipped_rows = 0
        last_rule_id = None

        import os
        file_base_name = os.path.splitext(os.path.basename(path))[0]

        for i, row in df.iterrows():
            cond_pairs = []
            for c in condition_cols:
                raw = row.get(c, None)
                val = "" if raw is None else str(raw).strip()
                if val == "":
                    continue
                cond_pairs.append((c, val))

            result_raw = row.get(result_col, None)
            result_val = "" if result_raw is None else str(result_raw).strip()

            if not cond_pairs or result_val == "":
                skipped_rows += 1
                continue

            # 用“链式蕴含”表达多条件同时满足时约束结果：
            # c1=v1 -> (c2=v2 -> (... -> result=rv))
            node = RuleNode(field=result_col, operator="eq", value=result_val, logic="and", children=[])
            for cond_col, cond_val in reversed(cond_pairs):
                node = RuleNode(field=cond_col, operator="eq", value=cond_val, logic="and", children=[node])

            source_row = row.get("__source_row__", None)
            row_mark = str(source_row).strip() if source_row is not None and str(source_row).strip() else str(int(i) + 2)
            cond_mark = "_".join(f"{k}={v}" for k, v in cond_pairs)
            if len(cond_mark) > 48:
                cond_mark = cond_mark[:48]
            rule_name = f"导入模板2_{file_base_name}_R{row_mark}_{cond_mark}"

            rule = ValidationRule(
                rule_id="",
                name=rule_name,
                description=(
                    f"模板2导入：当 {' 且 '.join(f'{k}={v}' for k, v in cond_pairs)} 时，"
                    f"{result_col} 必须等于 {result_val}"
                ),
                root=node,
                target_columns=[result_col],
            )
            self._engine.add_rule(rule)
            created_count += 1
            last_rule_id = rule.rule_id

        if created_count == 0:
            QMessageBox.warning(self, "提示", "未导入任何规则：请检查条件列与结果列是否有有效值。")
            return

        if not self._engine.save_rules():
            QMessageBox.warning(self, "提示", "导入后保存失败，请检查规则库路径是否可写。")
            return

        self._path_label.setText("规则库保存位置：" + (self._engine.rules_file or "—"))
        self._refresh_list_from_engine()
        self.set_columns_for_editor(usable_cols)

        if last_rule_id:
            for i in range(self.rule_list.count()):
                item = self.rule_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == last_rule_id:
                    self.rule_list.setCurrentRow(i)
                    break

        self.rules_updated.emit()
        QMessageBox.information(
            self,
            "提示",
            f"导入完成：新增规则 {created_count} 条。\n"
            f"跳过无效行: {skipped_rows} 条。",
        )

    def _del_rule(self):
        if not self._edit_unlocked:
            QMessageBox.warning(self, "提示", "规则库处于只读状态，请先点击“解锁编辑（需秘钥）”。")
            return
        if not self._current_rule_id:
            QMessageBox.warning(self, "提示", "请先选择一条规则。")
            return
        if QMessageBox.question(self, "确认", "确定删除该规则？") != QMessageBox.StandardButton.Yes:
            return
        self._engine.remove_rule(self._current_rule_id)
        self._engine.save_rules()
        self._current_rule_id = None
        self._load_rules()
        self.rules_updated.emit()
        QMessageBox.information(self, "提示", "已删除。")

    def set_columns_for_editor(self, columns: list):
        """从外部传入当前文件的列名，供条件树选择字段。"""
        self.tree_editor.set_columns(columns or [])

    def _on_sample_file_selected(self, path: str):
        if not path or not load_table_from_file:
            return
        self._reload_sample_columns()

    def _reload_sample_columns(self):
        path = self.sample_file.path()
        if not path or not load_table_from_file:
            return
        try:
            kwargs = {}
            hr = self.sample_header_rows_spin.value()
            st = self.sample_skip_top_rows_spin.value()
            if hr > 0:
                kwargs["header_rows"] = hr
            if st > 0:
                kwargs["skip_top_rows"] = st
            _, cols, _ = load_table_from_file(path, **kwargs)
            self.set_columns_for_editor(cols or [])
        except Exception as e:
            QMessageBox.warning(self, "提示", f"无法读取表头：{e}")

    def _ask_text(self, title: str, label: str, echo_mode=QLineEdit.EchoMode.Normal):
        """统一文本输入弹窗：限制宽度，避免被长文本撑开。"""
        dlg = QInputDialog(self)
        dlg.setWindowTitle(title)
        dlg.setLabelText(label)
        dlg.setTextEchoMode(echo_mode)
        dlg.setMinimumWidth(360)
        dlg.setMaximumWidth(560)
        dlg.resize(420, 120)
        ok = dlg.exec() == QInputDialog.DialogCode.Accepted
        return dlg.textValue(), ok


