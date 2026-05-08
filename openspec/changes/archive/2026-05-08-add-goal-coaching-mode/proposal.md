## Why

当前 ScreenChat 的主动发言偏“看屏幕吐槽”，短期有新鲜感，但缺少明确任务价值。用户更需要的是围绕当前目标的陪跑：在偏离、卡住或完成节点时给出有行动价值的提醒，而不是随机评论。

本变更将小幕从“屏幕评论员”调整为“目标陪跑器”。默认保持安静，用户从菜单栏开始一段陪跑后，系统才围绕目标进行判断和提醒。

## What Changes

- 新增「开始陪跑...」菜单入口，打开陪跑设置窗口。
- 新增陪跑会话，包含目标文本、目标类型、时长、强度、开始时间、结束时间、状态统计。
- 将自动截图分析从“是否评论”升级为“判断陪跑状态 + 是否介入”。
- 新增结构化 AI 返回协议：`state`、`confidence`、`screen_summary`、`target_relevance`、`should_interrupt`、`message`、`suggested_action`。
- 新增三档陪跑强度：轻、标准、严格，控制偏离/卡住阈值和本轮最大主动提醒次数。
- 主动消息必须包含观察、与目标的关系、下一步动作；无明确帮助时必须沉默。
- 陪跑结束时生成本轮总结，记录主要推进、偏离/卡住片段和下一步建议。
- 非陪跑状态下默认不进行随机自动吐槽，保留用户主动「对话...」能力。

## Capabilities

### New Capabilities

- `goal-coaching`: 目标陪跑会话、陪跑强度、状态判断、提醒策略和结束总结。

### Modified Capabilities

- `tray-icon`: 菜单栏新增「开始陪跑...」、陪跑中状态展示和「结束陪跑」入口。
- `capture-loop`: 截图循环在陪跑中使用目标感知分析协议；非陪跑时默认不做随机评论。
- `bubble-notification`: 通知内容从普通 AI 评论变为陪跑提醒或陪跑总结，并受强度和提醒次数限制。
- `conversation-persistence`: 需要持久化陪跑提醒、状态快照和结束总结，方便聊天窗口和后续复盘读取。

## Impact

- 影响 `src/screenchat/loop.py` 的主循环、prompt、AI JSON 解析和沉默策略。
- 影响 `src/screenchat/tray/icon.py` 的菜单项、状态展示和 UI 队列事件。
- 新增或扩展 `src/screenchat/ui/` 下的陪跑设置窗口。
- 扩展 `src/screenchat/memory/database.py` 的数据模型，用于保存陪跑事件和总结。
- 可能需要从 `loop.py` 中抽出陪跑状态机和 AI 分析协议，以避免主循环继续膨胀。
- 不新增第三方依赖，继续使用 `customtkinter`、`mss`、`Pillow`、`openai`、`rumps`。
