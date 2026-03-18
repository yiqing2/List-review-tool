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
    from config import ROLE_ADMIN, ROLE_USER, CURRENT_USER_FILE, save_json_safe
except ImportError:
    ROLE_ADMIN = "admin"
    ROLE_USER = "user"
    CURRENT_USER_FILE = "user_data/current_user.json"
    def save_json_safe(path, data):
        return False


class LoginDialog(QDialog):
    """简单角色选择：业内人员 / 管理员。可扩展为真实账号密码。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("清单对比与校审工具 - 登录")
        self._role = ROLE_USER
        self._user_name = "用户"
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        g = QGroupBox("选择身份")
        g_layout = QVBoxLayout(g)
        self.role_combo = QComboBox()
        self.role_combo.addItem("业内人员（上传文件、配置任务、执行校验、查看报告）", ROLE_USER)
        self.role_combo.addItem("管理员（可设计、维护校验规则与规则库）", ROLE_ADMIN)
        self.role_combo.currentIndexChanged.connect(self._on_role_changed)
        g_layout.addWidget(QLabel("角色："))
        g_layout.addWidget(self.role_combo)
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

    def _on_role_changed(self):
        idx = self.role_combo.currentIndex()
        if idx >= 0:
            self._role = self.role_combo.currentData()

    def _on_ok(self):
        self._role = self.role_combo.currentData() or ROLE_USER
        self._user_name = (self.name_edit.text() or "用户").strip()
        save_json_safe(CURRENT_USER_FILE, {"role": self._role, "user_name": self._user_name})
        self.accept()

    def role(self):
        return self._role

    def user_name(self):
        return self._user_name
