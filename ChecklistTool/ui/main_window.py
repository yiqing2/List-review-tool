# -*- coding: utf-8 -*-
"""
主窗口：集成规则校验、交叉对比、规则库、结果报告等选项卡。
（已移除“版本对比”界面：两文件对比可通过“交叉对比”添加 1 个待对比文件实现。）
"""

import sys
import os

# 将项目根目录加入路径，便于各模块导入 config、core
if getattr(sys, "frozen", False):
    _root = os.path.dirname(sys.executable)
else:
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTabWidget,
    QLabel,
    QStatusBar,
    QMessageBox,
)
from PyQt6.QtCore import Qt

from features.rule_validate import TabRuleValidate
from features.cross_compare import TabCrossCompare
from features.rules_lib import TabRulesLib
from features.results import TabResults


class MainWindow(QMainWindow):
    """清单对比与校审工具主窗口。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("清单对比与校审工具")
        self.setMinimumSize(900, 650)
        self.resize(1000, 700)
        self._tab_results = None
        self._tab_rules = None
        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.addWidget(QLabel("清单对比与校审工具"))

        tabs = QTabWidget()
        tab_validate = TabRuleValidate()
        tab_validate.result_ready.connect(self._on_validate_result)
        tabs.addTab(tab_validate, "规则校验")

        tab_cross = TabCrossCompare()
        tab_cross.result_ready.connect(self._on_cross_result)
        tabs.addTab(tab_cross, "交叉对比")

        self._tab_rules = TabRulesLib()
        self._tab_rules.rules_updated.connect(tab_validate.refresh_rules_list)
        tabs.addTab(self._tab_rules, "规则库")

        self._tab_results = TabResults()
        tabs.addTab(self._tab_results, "结果报告")

        layout.addWidget(tabs)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("就绪")

    def _on_validate_result(self, df, violations):
        self._tab_results.set_validation_result(df, violations)
        self.statusBar().showMessage(f"校验完成，共 {len(violations)} 条违规")

    def _on_cross_result(self, results):
        if not results:
            return
        self._tab_results.set_diff_result(results[0])
        if len(results) > 1:
            self.statusBar().showMessage(f"交叉对比完成，共 {len(results)} 组结果，已展示第一组")
        else:
            self.statusBar().showMessage("交叉对比完成，请查看结果报告页")
