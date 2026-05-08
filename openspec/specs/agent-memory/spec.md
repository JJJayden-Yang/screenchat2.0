## Purpose
定义小幕在自动观察和对话中的短期记忆、去重和摘要压缩能力。

## Requirements

### Requirement: 消息序列记忆
系统 SHALL 以标准 OpenAI messages 格式保存最近 5 轮对话历史。旧轮次 user 内容为纯文本占位符 `(约N秒前)`，不放截图。仅当前轮 user 内容包含实际图片。AI 说话后将 `role: assistant` 追加到序列。

#### Scenario: AI 说话后追加消息
- **WHEN** AI 返回 `should_comment: true`
- **THEN** 系统将 `{role: user, content: "(约N秒前)"}` 和 `{role: assistant, content: 评论}` 追加到 messages 序列

#### Scenario: 构建 AI 请求的 messages
- **WHEN** 下一次调用 `analyze()`
- **THEN** messages 数组包含 system prompt + 旧轮文本 + 当前截图，旧轮不含图片

#### Scenario: 超过 5 轮时自动淘汰
- **WHEN** messages 序列已有 10 条（5 轮 × 2 条/轮）
- **THEN** 新消息追加时，最早一轮的 2 条自动丢弃

### Requirement: 感知哈希去重
系统 SHALL 在每次截图后计算 dHash，与上一张截图的哈希比较汉明距离。距离小于阈值 5 时跳过 API 调用，视为 silent。

#### Scenario: 相同画面跳过 API
- **WHEN** 当前截图 dHash 与上一张汉明距离 < 5
- **THEN** 系统不调用 AI，直接打印 `· (dup)` 表示跳过去重

#### Scenario: 画面变化后正常调用
- **WHEN** 当前截图 dHash 与上一张汉明距离 ≥ 5
- **THEN** 系统正常调用 AI 分析

#### Scenario: 首张截图无历史
- **WHEN** 应用刚启动，尚无上一张截图
- **THEN** 系统正常调用 AI 分析，不进行去重判断
