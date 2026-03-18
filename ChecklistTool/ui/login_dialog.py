# -*- coding: utf-8 -*-
"""
登录/角色选择对话框
选择以“业内人员”或“管理员”身份进入，用于控制规则库编辑权限。
"""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QLineEdit,
    QGroupBox,
)
from PyQt6.QtCore import Qt

try:
    from config import CURRENT_USER_FILE, save_json_safe
except ImportError:
    CURRENT_USER_FILE = "user_data/current_user.json"
    def save_json_safe(path, data):
        return False


class LoginDialog(QDialog):
    """
    兼容旧版本的登录对话框。
    旧逻辑使用“管理员/业内人员”角色控制规则库编辑权限；
    新版本已改为“秘钥解锁编辑”，不再需要角色。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("清单对比与校审工具 - 登录")
        self._user_name = "用户"
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        g = QGroupBox("用户信息")
        g_layout = QVBoxLayout(g)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("用户名（可选）")
        self.name_edit.setText("用户")
        g_layout.addWidget(QLabel("用户名："))
        g_layout.addWidget(self.name_edit)
        layout.addWidget(g)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("进入")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("退出")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _on_ok(self):
        self._user_name = (self.name_edit.text() or "用户").strip()
        save_json_safe(CURRENT_USER_FILE, {"user_name": self._user_name})
        self.accept()

    def user_name(self):
        return self._user_name
