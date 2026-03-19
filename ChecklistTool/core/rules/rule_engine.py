# -*- coding: utf-8 -*-
"""
校验规则引擎：树形关联规则（在 A 下限定 B 的取值）。
规则库持久化、规则匹配、返回违反规则的行及字段与规则名称。
"""

from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field as dc_field
import pandas as pd
import json
import os

# 项目配置
try:
    from config import RULES_DB_FILE, load_json_safe, save_json_safe, get_rules_fallback_path
except ImportError:
    RULES_DB_FILE = "user_data/rules/rules_db.json"
    def load_json_safe(path, default=None):
        return default or {}
    def save_json_safe(path, data):
        return False
    def get_rules_fallback_path():
        import os
        return os.path.join(os.path.expanduser("~"), "清单对比校审工具", "rules", "rules_db.json")


# -----------------------------------------------------------------------------
# 规则节点：树结构
# -----------------------------------------------------------------------------
@dataclass
class RuleNode:
    """
    单条条件节点：可递归包含子条件（与/或），构成树形校验规则。
    - field: 字段名（对应表头，支持复杂表头如 "系统|专业"）
    - operator: 运算符，如 "eq"(等于)、"in"(在列表中)、"not_empty"、"regex" 等
    - value: 与 operator 配合，如 "in" 时为列表，"regex" 时为正则字符串
        - logic: 子节点组合方式，"and" 表示全部满足，"or" 表示满足其一
            * 当节点本身也配置了 field 且存在 children 时，语义为“父条件命中后，子条件必须满足”
                即： (not 父条件) or 子条件组
    - children: 子节点列表；无子节点时本节点为叶子条件
    - rule_name: 规则名称，在校验结果中显示“违反的规则名称”
    """
    field: str = ""
    operator: str = "eq"
    value: Any = None
    logic: str = "and"
    children: List["RuleNode"] = dc_field(default_factory=list)
    rule_name: str = ""  # 规则名称，用于结果中提示违反的规则

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "operator": self.operator,
            "value": self.value,
            "logic": self.logic,
            "rule_name": self.rule_name,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RuleNode":
        if not d:
            return cls()
        children = [cls.from_dict(c) for c in d.get("children", [])]
        return cls(
            field=d.get("field", ""),
            operator=d.get("operator", "eq"),
            value=d.get("value"),
            logic=d.get("logic", "and"),
            children=children,
            rule_name=d.get("rule_name", ""),
        )


# -----------------------------------------------------------------------------
# 单条规则：在“父字段 A”下，对“子字段 B”的约束
# -----------------------------------------------------------------------------
@dataclass
class ValidationRule:
    """校验规则：id、名称、条件树、可选的作用列（不填则整行）。"""
    rule_id: str = ""
    name: str = ""
    description: str = ""
    root: RuleNode = dc_field(default_factory=RuleNode)
    # 若指定，则仅对这些列做“出错字段”高亮
    target_columns: List[str] = dc_field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "root": self.root.to_dict(),
            "target_columns": self.target_columns,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValidationRule":
        if not d:
            return cls()
        root = RuleNode.from_dict(d.get("root", {}))
        return cls(
            rule_id=d.get("rule_id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
            root=root,
            target_columns=d.get("target_columns", []),
        )


# -----------------------------------------------------------------------------
# 规则匹配结果
# -----------------------------------------------------------------------------
@dataclass
class RuleViolation:
    """单行违反的规则记录。"""
    row_index: int
    rule_name: str
    rule_id: str
    error_fields: List[str]
    message: str = ""


# -----------------------------------------------------------------------------
# 规则引擎
# -----------------------------------------------------------------------------
class RuleEngine:
    """执行规则匹配，返回违反规则的行及出错字段、规则名称。"""

    OPERATORS = ("eq", "in")

    def __init__(self, rules_file: Optional[str] = None):
        self.rules_file = rules_file or RULES_DB_FILE
        self._rules: List[ValidationRule] = []

    def _eval_cell(self, cell_value: Any, operator: str, expected: Any) -> bool:
        """单单元格与条件的判断。"""
        s = "" if cell_value is None or (isinstance(cell_value, float) and pd.isna(cell_value)) else str(cell_value).strip()
        def _to_float(v: Any) -> Optional[float]:
            if v is None:
                return None
            try:
                t = str(v).strip()
                if t == "":
                    return None
                return float(t)
            except Exception:
                return None
        if operator == "eq":
            return s == ("" if expected is None else str(expected).strip())
        if operator == "ne":
            return s != ("" if expected is None else str(expected).strip())
        if operator in ("gt", "ge", "lt", "le"):
            a = _to_float(s)
            b = _to_float(expected)
            if a is not None and b is not None:
                if operator == "gt":
                    return a > b
                if operator == "ge":
                    return a >= b
                if operator == "lt":
                    return a < b
                return a <= b
            # 非数值：退化为字符串比较
            es = "" if expected is None else str(expected).strip()
            if operator == "gt":
                return s > es
            if operator == "ge":
                return s >= es
            if operator == "lt":
                return s < es
            return s <= es
        if operator == "in":
            if not isinstance(expected, list):
                expected = [expected]
            return s in [str(x).strip() for x in expected]
        if operator == "not_in":
            if not isinstance(expected, list):
                expected = [expected]
            return s not in [str(x).strip() for x in expected]
        if operator == "not_empty":
            return bool(s)
        if operator == "empty":
            return not bool(s)
        if operator == "regex":
            import re
            return bool(re.search(str(expected or ""), s))
        if operator == "contains":
            return str(expected or "") in s
        return False

    def _eval_node(self, node: RuleNode, row: pd.Series) -> bool:
        """递归求值条件树。"""
        has_self_cond = bool(node.field)
        self_ok = True
        if has_self_cond:
            cell = row.get(node.field, None)
            self_ok = self._eval_cell(cell, node.operator, node.value)

        if node.children:
            results = [self._eval_node(c, row) for c in node.children]
            if node.logic == "and":
                children_ok = all(results)
            else:
                children_ok = any(results)

            # 父节点同时有“自身条件 + 子节点”时，采用蕴含语义：
            # 父条件不命中 -> 该分支直接通过；父条件命中 -> 子条件组必须通过。
            if has_self_cond:
                return (not self_ok) or children_ok
            return children_ok

        return self_ok

    def validate_row(self, row: pd.Series, rule: ValidationRule) -> Optional[RuleViolation]:
        """判断一行是否违反该规则；违反则返回 RuleViolation。"""
        if self._eval_node(rule.root, row):
            return None  # 条件满足，不违反
        # target_columns 支持列名或列序号（1-based），便于配置“第2列满足A规则、第4列满足B规则”
        if rule.target_columns:
            mapped = []
            cols = list(row.index)
            for t in rule.target_columns:
                ts = str(t).strip()
                if ts.isdigit():
                    idx = int(ts) - 1
                    if 0 <= idx < len(cols):
                        mapped.append(cols[idx])
                elif ts:
                    mapped.append(ts)
            error_fields = mapped if mapped else list(row.index)
        else:
            error_fields = list(row.index)
        return RuleViolation(
            row_index=int(row.name) if hasattr(row, "name") else -1,
            rule_name=rule.name,
            rule_id=rule.rule_id,
            error_fields=error_fields,
            message=f"违反规则: {rule.name}",
        )

    def validate_dataframe(self, df: pd.DataFrame, rule_ids: Optional[List[str]] = None) -> List[RuleViolation]:
        """对 DataFrame 应用规则库中规则（或指定 rule_ids），返回所有违反记录。"""
        violations = []
        rules = [r for r in self._rules if not rule_ids or r.rule_id in rule_ids]
        for rule in rules:
            for idx, row in df.iterrows():
                v = self.validate_row(row, rule)
                if v is not None:
                    v.row_index = int(idx)
                    violations.append(v)
        return violations

    def _rule_row_activated(self, rule: ValidationRule, row: pd.Series) -> bool:
        """
        判断一行是否“进入该规则的验证范围”。
        规则：若存在任一叶子条件，其祖先链（不含叶子自身）上的字段条件全部命中，则视为已进入。
        """
        root = rule.root
        if root is None:
            return False

        def _is_true(node: RuleNode) -> bool:
            if not getattr(node, "field", ""):
                return True
            cell = row.get(node.field, None)
            return self._eval_cell(cell, node.operator, node.value)

        def _walk(node: RuleNode, ancestors: List[RuleNode]) -> bool:
            current_ancestors = list(ancestors)
            if getattr(node, "field", ""):
                current_ancestors.append(node)

            children = list(getattr(node, "children", []) or [])
            if not children:
                # 叶子本身是“要校验的约束”，进入范围仅看其祖先链命中情况。
                if not getattr(node, "field", ""):
                    return False
                trigger_anc = current_ancestors[:-1]
                return all(_is_true(a) for a in trigger_anc)

            for c in children:
                if _walk(c, current_ancestors):
                    return True
            return False

        return _walk(root, [])

    def validate_dataframe_with_coverage(
        self,
        df: pd.DataFrame,
        rule_ids: Optional[List[str]] = None,
    ) -> tuple[List[RuleViolation], List[int]]:
        """
        返回 (违规列表, 未进入验证范围的行索引列表)。
        未进入验证范围：对所选规则集合，均未命中任何规则前置条件。
        """
        violations = self.validate_dataframe(df, rule_ids=rule_ids)
        rules = [r for r in self._rules if not rule_ids or r.rule_id in rule_ids]
        if not rules:
            return violations, []

        unvalidated_rows: List[int] = []
        for idx, row in df.iterrows():
            activated = False
            for rule in rules:
                if self._rule_row_activated(rule, row):
                    activated = True
                    break
            if not activated:
                unvalidated_rows.append(int(idx))
        return violations, unvalidated_rows

    def load_rules(self) -> bool:
        """从规则库文件加载；若默认路径无文件则尝试用户目录（与长期保存一致）。"""
        data = load_json_safe(self.rules_file, default={"rules": []})
        if (not data.get("rules")) or not os.path.isfile(self.rules_file):
            try:
                fallback = get_rules_fallback_path()
                if os.path.isfile(fallback):
                    fb_data = load_json_safe(fallback, default={"rules": []})
                    if fb_data.get("rules"):
                        data = fb_data
                        self.rules_file = fallback
            except Exception:
                pass
        self._rules = [ValidationRule.from_dict(r) for r in data.get("rules", [])]
        return True

    def save_rules(self) -> bool:
        """保存规则库到文件；若默认路径不可写则自动保存到用户目录以实现长期保存。"""
        data = {"rules": [r.to_dict() for r in self._rules]}
        if save_json_safe(self.rules_file, data):
            return True
        try:
            fallback = get_rules_fallback_path()
            if save_json_safe(fallback, data):
                self.rules_file = fallback
                return True
        except Exception:
            pass
        return False

    def add_rule(self, rule: ValidationRule) -> None:
        """添加一条规则（管理员）。"""
        if not rule.rule_id:
            rule.rule_id = f"rule_{len(self._rules)}_{id(rule)}"
        self._rules.append(rule)

    def update_rule(self, rule_id: str, rule: ValidationRule) -> bool:
        """更新规则（管理员）。"""
        for i, r in enumerate(self._rules):
            if r.rule_id == rule_id:
                rule.rule_id = rule_id
                self._rules[i] = rule
                return True
        return False

    def remove_rule(self, rule_id: str) -> bool:
        """删除规则（管理员）。"""
        for i, r in enumerate(self._rules):
            if r.rule_id == rule_id:
                self._rules.pop(i)
                return True
        return False

    def get_rules(self) -> List[ValidationRule]:
        """返回当前规则列表（只读给普通用户）。"""
        return list(self._rules)
