# -*- coding: utf-8 -*-
"""
核心业务逻辑包（按功能块分子包）
- core.parsers: 表格解析
- core.diff: 对比引擎
- core.rules: 规则引擎
- core.export: 导出引擎
"""
from .parsers import load_table_from_file, get_columns_from_file, ParserError
from .diff import DiffEngine, DiffResult, cross_compare
from .rules import RuleEngine, RuleNode, ValidationRule, RuleViolation
from .export import (
    export_to_excel,
    export_to_csv,
    export_to_pdf,
    export_diff_result,
    ExportError,
)

__all__ = [
    "load_table_from_file",
    "get_columns_from_file",
    "ParserError",
    "DiffEngine",
    "DiffResult",
    "cross_compare",
    "RuleEngine",
    "RuleNode",
    "ValidationRule",
    "RuleViolation",
    "export_to_excel",
    "export_to_csv",
    "export_to_pdf",
    "export_diff_result",
    "ExportError",
]
