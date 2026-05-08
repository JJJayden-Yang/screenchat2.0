## Purpose
定义用户通过偏好设置窗口查看和保存本地配置的行为。

## Requirements

### Requirement: 偏好设置窗口
用户点击「偏好设置...」菜单项时，系统 SHALL 弹出一个设置窗口，包含 API Key（遮盖）、截图间隔、记忆长度三个配置项。

#### Scenario: 打开设置窗口
- **WHEN** 用户点击「偏好设置...」菜单项
- **THEN** 弹出 customtkinter 窗口，字段已填写当前值

#### Scenario: 保存设置
- **WHEN** 用户点击「保存」按钮
- **THEN** 配置写入 `~/.screenchat/settings.json`，循环应用新值（无需重启）

#### Scenario: API Key 遮盖显示
- **WHEN** API Key 有值
- **THEN** 输入框中显示为 `sk-***...`，只展示前 5 位

### Requirement: 配置优先级
系统 SHALL 按 `settings.json > .env > 默认值` 的优先级加载配置。

#### Scenario: settings.json 有值时覆盖 .env
- **WHEN** `settings.json` 中有 `capture_interval: 30`
- **THEN** 系统使用 30，即使 `.env` 中设置了 20
