# 清单对比与校审工具

离线桌面版：同一清单不同版本对比、基于自定义规则的校验、多清单交叉对比；支持 Excel、CSV、TSV、Word 等格式；结果可导出 PDF/Excel/CSV，带差异高亮与规则违规标记。

## 功能概览

- **版本对比**：两版清单按键列匹配，识别新增/删除/修改行，可配置对比列。
- **规则校验**：按规则库中的条件树校验数据，高亮违规字段并提示规则名称。
- **交叉对比**：基准清单与多个待对比清单逐表对比。
- **规则库**：管理员可维护规则（可视化条件树）；业内人员仅可查看与选择。
- **结果报告**：表格预览，导出 PDF（带格式）、Excel（含标记与高亮）、CSV（纯数据）。

## 环境与运行

```bash
# Python 3.8+
pip install -r requirements.txt
python main.py
```

首次运行会提示选择角色（业内人员 / 管理员），规则库保存在 `user_data/rules/`，导出与日志在 `user_data/exports/`、`user_data/logs/`。

## 项目结构（便于后续扩展）

```
ChecklistTool/
├── main.py              # 入口，异常捕获与日志
├── config/              # 配置与路径
│   └── app_config.py
├── core/                # 核心逻辑
│   ├── parsers.py       # 多格式解析、复杂表头
│   ├── diff_engine.py   # 差异对比
│   ├── rule_engine.py   # 规则树与校验
│   └── export_engine.py # 导出 PDF/Excel/CSV
├── ui/                  # 界面
│   ├── main_window.py   # 主窗口与选项卡
│   ├── login_dialog.py  # 角色选择
│   ├── widgets.py       # 通用控件
│   ├── rule_tree_editor.py  # 规则条件树编辑
│   ├── tab_version_diff.py
│   ├── tab_rule_validate.py
│   ├── tab_cross_compare.py
│   ├── tab_rules_lib.py
│   └── tab_results.py
└── user_data/           # 运行时生成
    ├── rules/
    ├── exports/
    └── logs/
```

## 表头说明

支持多级表头（如 Excel 中多行表头）：解析器会自动检测或按配置表头行数，将多行合并为层级列名（如 `系统|专业`），便于在键列与对比列中选择。

## 扩展建议

- 支持 `.et` 格式：可接入 WPS 转换或专用库。
- 规则库可改为 SQLite，支持更多元数据。
- 导出样式（颜色、字体）可通过配置或主题扩展。
