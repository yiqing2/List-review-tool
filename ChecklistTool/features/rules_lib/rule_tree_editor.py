# -*- coding: utf-8 -*-
"""
规则条件树可视化编辑器（拖拽构建）。
将 RuleNode 树与 QTreeWidget 绑定，支持添加/删除/编辑节点，逻辑与/或。
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QComboBox,
    QLineEdit,
    QLabel,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt

from core.rules import RuleNode, RuleEngine


def _op_label(op: str) -> str:
    m = {
        "eq": "等于 (=)",
        "ne": "不等于 (≠)",
        "gt": "大于 (>)",
        "ge": "大于等于 (≥)",
        "lt": "小于 (<)",
        "le": "小于等于 (≤)",
        "in": "属于/在列表中",
        "not_in": "不属于/不在列表中",
        "not_empty": "非空",
        "empty": "为空",
        "regex": "正则匹配",
        "contains": "包含",
    }
    return m.get(op, op)


class RuleNodeEditDialog(QDialog):
    """编辑单个条件节点：字段、运算符、值、逻辑。"""

    def __init__(self, node: RuleNode, columns: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑条件节点")
        self.node = node
        self.columns = columns or []
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        self.field_combo = QComboBox()
        self.field_combo.setEditable(True)  # 可手动输入列名（如 系统|专业），无需先加载文件
        self.field_combo.addItem("（无/根节点）", "")
        for c in self.columns:
            self.field_combo.addItem(c, c)
        layout.addRow("字段（可下拉选择或直接输入列名）:", self.field_combo)
        self.op_combo = QComboBox()
        for op in RuleEngine.OPERATORS:
            self.op_combo.addItem(_op_label(op), op)
        layout.addRow("运算符:", self.op_combo)
        self.value_edit = QLineEdit()
        self.value_edit.setPlaceholderText("值（列表请用逗号分隔；大于/小于请填数字）")
        layout.addRow("值:", self.value_edit)
        self.logic_combo = QComboBox()
        self.logic_combo.addItem("且 (and)", "and")
        self.logic_combo.addItem("或 (or)", "or")
        layout.addRow("子节点逻辑:", self.logic_combo)
        self.rule_name_edit = QLineEdit()
        self.rule_name_edit.setPlaceholderText("规则名称（用于报告）")
        layout.addRow("规则名称:", self.rule_name_edit)

        # 回填：有预选项则选中，否则设为可编辑的当前值
        idx = self.field_combo.findData(self.node.field)
        if idx >= 0:
            self.field_combo.setCurrentIndex(idx)
        elif self.node.field:
            self.field_combo.setCurrentText(self.node.field)
        idx = self.op_combo.findData(self.node.operator)
        if idx >= 0:
            self.op_combo.setCurrentIndex(idx)
        if self.node.value is not None:
            if isinstance(self.node.value, list):
                self.value_edit.setText(",".join(str(x) for x in self.node.value))
            else:
                self.value_edit.setText(str(self.node.value))
        self.logic_combo.setCurrentIndex(0 if self.node.logic == "and" else 1)
        self.rule_name_edit.setText(self.node.rule_name or "")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_node(self) -> RuleNode:
        val = self.value_edit.text().strip()
        if "," in val:
            value = [x.strip() for x in val.split(",")]
        else:
            value = val if val else None
        # 优先用下拉选中项，否则用手动输入的文本（支持未在列表中的列名）
        field_val = self.field_combo.currentData()
        if field_val is None or (isinstance(field_val, str) and not field_val.strip()):
            field_val = self.field_combo.currentText().strip()
        self.node.field = field_val or ""
        self.node.operator = self.op_combo.currentData() or "eq"
        self.node.value = value
        self.node.logic = self.logic_combo.currentData() or "and"
        self.node.rule_name = self.rule_name_edit.text().strip()
        return self.node


def _node_to_item(node: RuleNode) -> QTreeWidgetItem:
    """将 RuleNode 转为 QTreeWidgetItem（仅当前节点，不递归）。"""
    if node.children:
        label = f"[{node.logic}] 条件组"
    else:
        label = f"{node.field} {_op_label(node.operator)} {node.value}" if node.field else "根"
    item = QTreeWidgetItem([label])
    item.setData(0, Qt.ItemDataRole.UserRole, node)
    return item


def _build_children(item: QTreeWidgetItem, node: RuleNode):
    for c in node.children:
        child_item = _node_to_item(c)
        item.addChild(child_item)
        _build_children(child_item, c)


def _item_to_node(item: QTreeWidgetItem) -> RuleNode:
    """从 QTreeWidgetItem 恢复 RuleNode（递归）。"""
    node = item.data(0, Qt.ItemDataRole.UserRole)
    if not isinstance(node, RuleNode):
        node = RuleNode()
    node.children = []
    for i in range(item.childCount()):
        node.children.append(_item_to_node(item.child(i)))
    return node


class RuleTreeEditor(QWidget):
    """规则条件树编辑器：树形展示，支持添加子节点、编辑、删除。"""

    def __init__(self, columns: list = None, parent=None):
        super().__init__(parent)
        self.columns = columns or []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["条件"])
        layout.addWidget(self.tree)
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加根/子条件")
        add_btn.clicked.connect(self._add_node)
        edit_btn = QPushButton("编辑")
        edit_btn.clicked.connect(self._edit_node)
        del_btn = QPushButton("删除")
        del_btn.clicked.connect(self._del_node)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(edit_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def set_columns(self, columns: list):
        self.columns = list(columns)

    def load_node(self, root: RuleNode):
        """从 RuleNode 加载树。"""
        self.tree.clear()
        if not root:
            return
        item = _node_to_item(root)
        _build_children(item, root)
        self.tree.addTopLevelItem(item)

    def get_root_node(self) -> RuleNode:
        """导出当前树为 RuleNode。"""
        if self.tree.topLevelItemCount() == 0:
            return RuleNode()
        item = self.tree.topLevelItem(0)
        return _item_to_node(item)

    def _current_item(self) -> QTreeWidgetItem:
        return self.tree.currentItem()

    def _add_node(self):
        """添加子节点：若已选中某节点则在其下添加子条件，否则添加为顶层节点。"""
        item = self._current_item()
        node = RuleNode(field="", operator="eq", value=None, logic="and")
        new_item = _node_to_item(node)
        if item:
            item.addChild(new_item)
            item.setExpanded(True)
        else:
            self.tree.addTopLevelItem(new_item)
        self.tree.setCurrentItem(new_item)
        self._edit_node()

    def _edit_node(self):
        item = self._current_item()
        if not item:
            return
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(node, RuleNode):
            node = RuleNode()
        dlg = RuleNodeEditDialog(node, self.columns, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.get_node()
            label = f"[{node.logic}] 条件组" if node.children else (f"{node.field} {_op_label(node.operator)} {node.value}" if node.field else "根")
            item.setText(0, label)
            item.setData(0, Qt.ItemDataRole.UserRole, node)

    def _del_node(self):
        item = self._current_item()
        if not item:
            return
        parent = item.parent()
        if parent:
            parent.removeChild(item)
        else:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
