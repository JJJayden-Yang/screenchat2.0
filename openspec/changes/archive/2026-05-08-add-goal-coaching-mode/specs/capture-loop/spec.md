## MODIFIED Requirements

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
