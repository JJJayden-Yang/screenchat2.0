## Purpose
定义小幕后台截图、视觉分析和循环运行的核心行为。
## Requirements
### Requirement: 定时截图循环
系统 SHALL 以可配置的时间间隔（默认 20 秒）循环执行截图操作。循环在用户手动终止（Ctrl+C）前持续运行。

#### Scenario: 正常截图循环
- **WHEN** 循环启动且间隔配置为 20 秒
- **THEN** 系统每约 20 秒触发一次截图，在终端打印时间戳和截图状态

#### Scenario: 用户手动终止
- **WHEN** 用户按下 Ctrl+C
- **THEN** 系统优雅退出，打印 goodbye 消息

### Requirement: 截图发送到 Kimi K2.5
系统 SHALL 将每次截图缩放至 1280px、JPEG q=85 压缩后，以 base64 格式发送至 Kimi K2.5 视觉模型。

#### Scenario: 成功截图并分析
- **WHEN** 截图成功获取
- **THEN** 系统将截图发至 Kimi K2.5，等待 JSON 响应

#### Scenario: API 调用失败
- **WHEN** API 返回错误（如网络问题、鉴权失败）
- **THEN** 系统打印错误信息，等待下一个周期重试，不退出循环

### Requirement: AI 返回 JSON 判断是否评论
系统 SHALL 根据当前是否存在活动陪跑会话选择 AI 分析协议。没有活动陪跑会话时，系统 SHALL 默认沉默，不生成随机主动评论。有活动陪跑会话时，系统 SHALL 解析目标感知 JSON，包含 `state`、`confidence`、`screen_summary`、`target_relevance`、`should_interrupt`、`message` 和 `suggested_action` 字段。

#### Scenario: 非陪跑状态默认沉默
- **WHEN** 应用运行且没有活动陪跑会话
- **THEN** 截图循环不调用随机评论协议，不弹出吐槽通知

#### Scenario: 陪跑状态下判断推进
- **WHEN** 陪跑分析返回 `{"state": "on_track", "should_interrupt": false}`
- **THEN** 系统记录状态为正在推进，不弹出通知

#### Scenario: 陪跑状态下判断偏离
- **WHEN** 陪跑分析返回 `{"state": "distracted", "should_interrupt": true, "message": "这个视频页和目标不相关，要不要切回去？"}`
- **THEN** 系统结合强度阈值和提醒次数决定是否弹出该提醒

#### Scenario: 陪跑状态下判断卡住
- **WHEN** 陪跑分析返回 `{"state": "stuck", "should_interrupt": true, "message": "这个报错停了挺久，要不要我帮你看？"}`
- **THEN** 系统结合强度阈值和提醒次数决定是否弹出该提醒

#### Scenario: 低置信度沉默
- **WHEN** 陪跑分析返回的 `confidence` 低于系统阈值
- **THEN** 系统不弹出通知，并将状态视为 `unclear`

