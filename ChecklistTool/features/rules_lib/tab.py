# -*- coding: utf-8 -*-
"""
规则库管理页：管理员可添加/编辑/删除规则（可视化条件树）；普通用户仅可查看与选择。
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
)
from PyQt6.QtCore import Qt, pyqtSignal

from features.rules_lib.rule_tree_editor import RuleTreeEditor
from core.rules import RuleEngine, ValidationRule, RuleNode
from ui.widgets import FilePathRow, ColumnSelector

try:
    from core.parsers import load_table_from_file
except ImportError:
    load_table_from_file = None

try:
    from config import ROLE_ADMIN
except ImportError:
    ROLE_ADMIN = "admin"


class TabRulesLib(QWidget):
    """规则库：列表 + 详情（条件树 + 说明）。管理员可编辑。"""
    rules_updated = pyqtSignal()

    def __init__(self, is_admin: bool, parent=None):
        super().__init__(parent)
        self.is_admin = is_admin
        self._engine = RuleEngine()
        self._current_rule_id = None
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
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("规则说明（仅管理员可编辑）")
        self.desc_edit.setMaximumHeight(80)
        right_layout.addWidget(self.desc_edit)
        right_layout.addWidget(QLabel("选择要校验/高亮的表头列（可多选；不确定第几列时用这里）："))
        self.target_cols_selector = ColumnSelector()
        self.target_cols_selector.set_columns([])
        right_layout.addWidget(self.target_cols_selector)
        right_layout.addWidget(QLabel("手动补充表头/列序号（逗号分隔；例如 TIME,CH2 或 2,4；空=仅使用上方选择）："))
        self.target_cols_edit = QLineEdit()
        self.target_cols_edit.setPlaceholderText("例如：TIME,CH2 或 2,4")
        right_layout.addWidget(self.target_cols_edit)
        self.tree_editor = RuleTreeEditor(columns=[])
        right_layout.addWidget(self.tree_editor)
        if self.is_admin:
            btn_add = QPushButton("新增规则")
            btn_add.clicked.connect(self._add_rule)
            btn_save = QPushButton("保存当前规则")
            btn_save.clicked.connect(self._save_rule)
            btn_del = QPushButton("删除当前规则")
            btn_del.clicked.connect(self._del_rule)
            h = QHBoxLayout()
            h.addWidget(btn_add)
            h.addWidget(btn_save)
            h.addWidget(btn_del)
            right_layout.addLayout(h)
        else:
            right_layout.addWidget(QLabel("（仅管理员可修改规则库）"))
        split.addWidget(right)
        layout.addWidget(split)

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
                # target_columns 优先填充选择器（命中列名），其余保留在手动输入框中
                saved = [x for x in (r.target_columns or []) if str(x).strip()]
                cols = list(getattr(self.tree_editor, "columns", []) or [])
                selected = [x for x in saved if x in cols]
                extra = [x for x in saved if x not in cols]
                self.target_cols_selector.set_columns(cols)
                for x in selected:
                    # 将已选列移入右侧“已选列”
                    for i in range(self.target_cols_selector.available.count()):
                        it = self.target_cols_selector.available.item(i)
                        if it and it.text() == x:
                            it.setSelected(True)
                    self.target_cols_selector._add()
                self.target_cols_edit.setText(",".join(extra))
                self.tree_editor.load_node(r.root)
                return
        self._current_rule_id = None

    def _add_rule(self):
        name, ok = QInputDialog.getText(self, "新增规则", "规则名称：")
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
        if not self._current_rule_id:
            QMessageBox.warning(self, "提示", "请先选择一条规则。")
            return
        for r in self._engine.get_rules():
            if r.rule_id == self._current_rule_id:
                r.description = self.desc_edit.toPlainText().strip()
                r.root = self.tree_editor.get_root_node()
                # 作用列（用于违规高亮），支持列名或列序号（1-based）
                selected = self.target_cols_selector.get_selected() if hasattr(self, "target_cols_selector") else []
                raw = self.target_cols_edit.text().strip()
                extras = [x.strip() for x in raw.split(",") if x.strip()] if raw else []
                merged = []
                for x in list(selected) + list(extras):
                    if x not in merged:
                        merged.append(x)
                r.target_columns = merged
                self._engine.save_rules()
                self.rules_updated.emit()
                self._path_label.setText("规则库保存位置：" + (self._engine.rules_file or "—"))
                QMessageBox.information(self, "提示", "已保存到：%s" % (self._engine.rules_file or ""))
                return
        QMessageBox.warning(self, "提示", "未找到当前规则。")

    def _del_rule(self):
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
        if hasattr(self, "target_cols_selector"):
            self.target_cols_selector.set_columns(columns or [])

    def _on_sample_file_selected(self, path: str):
        if not path or not load_table_from_file:
            return
        try:
            _, cols, _ = load_table_from_file(path)
            self.set_columns_for_editor(cols or [])
        except Exception as e:
            QMessageBox.warning(self, "提示", f"无法读取表头：{e}")


