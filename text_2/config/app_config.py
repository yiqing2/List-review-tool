# -*- coding: utf-8 -*-
"""
应用全局配置模块
Application global configuration.
集中管理路径、常量、默认值，便于后续扩展与维护。
"""

import os
import json

# -----------------------------------------------------------------------------
# 路径配置
# -----------------------------------------------------------------------------
# 应用根目录（以 config 所在目录的上级为根）
APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 用户数据目录：规则库、导出结果、日志等
USER_DATA_DIR = os.path.join(APP_ROOT, "user_data")
RULES_DIR = os.path.join(USER_DATA_DIR, "rules")
EXPORT_DIR = os.path.join(USER_DATA_DIR, "exports")
LOG_DIR = os.path.join(USER_DATA_DIR, "logs")

for _dir in (USER_DATA_DIR, RULES_DIR, EXPORT_DIR, LOG_DIR):
    try:
        os.makedirs(_dir, exist_ok=True)
    except OSError:
        pass
# 若项目下 rules 不可写（如只读盘），改用用户目录，保证规则可长期保存
try:
    _t = os.path.join(RULES_DIR, ".w")
    with open(_t, "w") as _f:
        pass
    os.remove(_t)
except OSError:
    RULES_DIR = os.path.join(os.path.expanduser("~"), "清单对比校审工具", "rules")
    os.makedirs(RULES_DIR, exist_ok=True)

# -----------------------------------------------------------------------------
# 支持的文件格式
# -----------------------------------------------------------------------------
SUPPORTED_EXTENSIONS = (".xlsx", ".xls", ".csv", ".tsv", ".docx", ".et")
# 注：.et 若需支持，可后续接入转换或专用库

# -----------------------------------------------------------------------------
# 用户角色常量
# -----------------------------------------------------------------------------
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLES = (ROLE_ADMIN, ROLE_USER)

# -----------------------------------------------------------------------------
# 差异类型（用于导出高亮）
# -----------------------------------------------------------------------------
DIFF_ADDED = "added"
DIFF_DELETED = "deleted"
DIFF_MODIFIED = "modified"
DIFF_UNCHANGED = "unchanged"

# -----------------------------------------------------------------------------
# 规则库文件名
# -----------------------------------------------------------------------------
RULES_DB_FILE = os.path.join(RULES_DIR, "rules_db.json")


def get_rules_fallback_path() -> str:
    """规则库在项目目录不可写时使用的用户目录路径（便于长期保存）。"""
    return os.path.join(os.path.expanduser("~"), "清单对比校审工具", "rules", "rules_db.json")
# 当前登录用户信息（简单实现，可后续改为数据库）
CURRENT_USER_FILE = os.path.join(USER_DATA_DIR, "current_user.json")

# -----------------------------------------------------------------------------
# 默认导出与界面
# -----------------------------------------------------------------------------
DEFAULT_EXPORT_FORMAT = "xlsx"
DEFAULT_ENCODING = "utf-8"

def load_json_safe(path: str, default=None):
    """安全加载 JSON 文件，缺失或异常时返回 default。"""
    if default is None:
        default = {}
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError):
        pass
    return default

def save_json_safe(path: str, data: dict) -> bool:
    """安全保存 JSON 文件。"""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except (IOError, TypeError):
        return False
