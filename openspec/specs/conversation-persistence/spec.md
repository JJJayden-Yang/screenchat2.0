## Purpose
定义小幕将对话、屏幕概括和陪跑事件写入本地 SQLite 并按天读取的行为。
## Requirements
### Requirement: AI 输出增加截图概括
系统 SHALL 在 system prompt 中要求 AI 可选输出 `screen_summary` 字段（20 字内概括当前截图）。该字段非强制，缺失或解析失败不影核心逻辑。

#### Scenario: AI 正常输出 screen_summary
- **WHEN** AI 返回 `should_comment: true`
- **THEN** JSON 中可选包含 `screen_summary` 字段，概括当前画面内容

#### Scenario: screen_summary 缺失
- **WHEN** AI 返回的 JSON 中没有 `screen_summary` 字段
- **THEN** 系统默认 `screen_summary=""`，核心流程不受影响

### Requirement: SQLite 持久化
系统 SHALL 在 AI 说话时，将该条记录的日期、截图概括、评论、分类和时间戳写入 `~/.screenchat/history.db` 的 `conversations` 表。

#### Scenario: AI 说话时写入数据库
- **WHEN** AI 返回 `should_comment: true`
- **THEN** 一条记录写入 `conversations` 表，包含 date、screen_summary、comment、category、created_at

#### Scenario: AI 沉默时不写入
- **WHEN** AI 返回 `should_comment: false`
- **THEN** 不写入数据库

### Requirement: 按天查询
系统 SHALL 支持按日期查询对话记录。

#### Scenario: 查询当天记录
- **WHEN** 调用 `get_conversations(date=today)`
- **THEN** 返回该日期的所有记录，按时间升序

### Requirement: 陪跑事件持久化
系统 SHALL 将陪跑相关事件写入本地 SQLite，包括会话开始、主动提醒、状态快照、手动结束、自动结束和本轮总结。

#### Scenario: 记录会话开始
- **WHEN** 用户开始一段陪跑会话
- **THEN** 系统写入一条陪跑开始事件，包含目标文本、目标类型、时长和强度

#### Scenario: 记录主动提醒
- **WHEN** 系统弹出一条陪跑提醒
- **THEN** 系统写入一条提醒事件，包含状态、截图概括、目标关系、提醒内容和建议动作

#### Scenario: 记录结束总结
- **WHEN** 陪跑会话结束并生成总结
- **THEN** 系统写入一条总结事件，包含本轮目标、主要推进、偏离或卡住片段和下一步建议

### Requirement: 陪跑历史可供聊天窗口读取
系统 SHALL 支持聊天窗口读取当天陪跑事件，并以时间顺序展示关键提醒和总结。

#### Scenario: 聊天窗口展示陪跑提醒
- **WHEN** 用户打开「对话...」
- **THEN** 聊天窗口按时间顺序展示当天 AI 评论、用户消息、陪跑提醒和陪跑总结

#### Scenario: 陪跑总结进入上下文
- **WHEN** 用户在陪跑结束后继续聊天
- **THEN** AI 可读取本轮陪跑总结作为上下文，避免重复询问用户刚完成的目标

