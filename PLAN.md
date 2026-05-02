# ScreenChat 2.0 — 桌面 AI 陪伴助手

## Context

从零构建跨平台（Win/Mac/Linux）桌面 AI 陪伴应用。后台静默运行，定期截图分析屏幕，AI 判断是否值得反馈，通过对话框主动互动。用户也可手动激活对话。

**人格定位**：朋友型 —— 像坐在旁边的老朋友，不喧宾夺主，关键时刻给建议，无聊时给鼓励。

**开发原则**：Karpathy 四原则驱动 —— Think Before Coding、Simplicity First、Surgical Changes、Goal-Driven Execution。代码一小块一小块加，每个模块独立可验证。

---

## 技术栈

| 组件 | 最终选型 | 理由 |
|------|---------|------|
| 语言 | Python 3.11+ | 用户指定 |
| **AI 模型** | **Kimi K2.5**（Moonshot AI） | 原生多模态视觉、中文顶级、OpenAI SDK 兼容、$0.60/M input、日均 ¥2-4 |
| AI SDK | **openai** + 自定义 base_url | 指向 `https://api.moonshot.ai/v1`，后期灵活切换模型 |
| 屏幕截图 | **mss** + Pillow | 跨平台、C 级性能 |
| 系统托盘 | **macOS: rumps / Win+Linux: pystray** | pystray 在 Apple Silicon 上有 GIL 崩溃 bug，macOS 换 rumps |
| 聊天窗口 | **customtkinter** | 现代外观、轻量 |
| 全局快捷键 | **pynput** | 跨平台、监听模式无需 root |
| 本地存储 | **sqlite3**（标准库） | 对话历史、配置 |
| 网页搜索 | function tool（可选） | AI 判断需要时触发，后端调搜索 API |
| 配置 | **python-dotenv** | `.env` 文件 |
| 系统通知 | 各平台原生 | macOS: osascript / Win: win10toast / Linux: notify-send |

### 模型对比

| 对比项 | Kimi K2.5 | GPT-4o-mini | DeepSeek-V3 |
|--------|-----------|-------------|-------------|
| 输入价格 | $0.60/M | $0.15/M | $0.27/M |
| 输出价格 | $3.00/M | $0.60/M | $1.10/M |
| 视觉能力 | ✅ 原生多模态（78.5% MMMU-Pro） | ✅ | ⚠️ 偏弱 |
| 中文能力 | ⭐ 顶级 | 良好 | ⭐ 顶级 |
| OpenAI SDK 兼容 | ✅ `/v1` | ✅ | ✅ |
| 日成本预估 | **¥2-4** | ¥1-3 | ¥1-2 |

---

## 项目结构

```
screenchat2.0/
├── pyproject.toml
├── .env.example
│
├── src/screenchat/
│   ├── __init__.py
│   ├── __main__.py
│   ├── main.py                  # 启动入口，线程/进程编排
│   ├── config.py                # .env → 类型化配置 dataclass
│   │
│   ├── capture/
│   │   ├── capturer.py          # mss 截图循环 + SHA-256 去重
│   │   └── image.py             # 缩放、压缩、base64 编码
│   │
│   ├── ai/
│   │   ├── client.py            # Kimi K2.5 客户端（OpenAI SDK + 自定义 base_url）
│   │   ├── analyzer.py          # MVP：单次调用，判断+评论一步完成
│   │   ├── chat.py              # 主动对话（含视觉上下文 + web_search tool）
│   │   └── prompts.py           # 所有 prompt 模板（按场景+人格分类）
│   │
│   ├── ui/
│   │   ├── chat_window.py       # customtkinter 聊天窗口
│   │   └── settings.py          # 设置对话框
│   │
│   ├── tray/
│   │   ├── controller.py        # 统一托盘接口（按平台选择后端）
│   │   ├── _darwin.py           # macOS: rumps 实现
│   │   └── _other.py            # Win/Linux: pystray 实现
│   │
│   ├── hotkey/
│   │   └── listener.py          # pynput 全局快捷键
│   │
│   ├── memory/
│   │   ├── database.py          # SQLite schema + 连接管理
│   │   └── models.py            # 数据模型 dataclass
│   │
│   ├── notification/
│   │   └── notifier.py          # 系统原生通知
│   │
│   └── utils/
│       ├── timing.py            # 定时器（带抖动）、冷却、限流
│       ├── platform.py          # 平台检测 + 各系统路径
│       └── logger.py            # 日志
│
└── tests/
```

---

## 核心数据流

### MVP：单模型一步完成（Simplicity First）

```
定时触发 → 截图(mss) → JPEG压缩(1280px, q=85) → SHA-256去重
                                                      │
                              ┌── 跳过 ←── 重复/空闲/冷却中？
                              │
                              ▼
               Kimi K2.5（单次调用，一次性判断+生成评论）
               返回 JSON: {should_comment, comment, category}
                                                      │
                              ┌── 丢弃 ←── should_comment=false
                              │
                              ▼ should_comment=true
                    推入 UI 队列 → 更新聊天窗口 + 系统通知
```

> 为什么不用两级判官？Karpathy #2：Simplicity First。先跑通流程，后期成本敏感了再拆 judge+commentator。

### 主动对话

```
用户激活 → 聊天窗口置前 → 用户输入消息
                              │
           收集：当前截图 + 对话历史（最近20条）
                              │
           Kimi K2.5（含 web_search function tool）
                              │
           生成回复 → 更新聊天窗口
```

---

## 线程模型

**macOS:**
```
主线程: customtkinter mainloop
子进程: rumps 菜单栏图标
守护线程: 截图循环
守护线程: AI 工作线程
守护线程: 快捷键监听
```

**Windows / Linux:**
```
主线程: customtkinter mainloop
守护线程: pystray（线程内创建 Icon 对象）
守护线程: 截图循环
守护线程: AI 工作线程
守护线程: 快捷键监听
```

跨线程通信全部通过 `queue.Queue`，无共享可变状态。

---

## AI Prompt 设计（朋友型人格）

### 核心文件：`analyzer.py` 使用的 Prompt

```
你是「小幕」，一个桌面 AI 陪伴伙伴。

你的个性：像大学室友，会吐槽、会夸你、会提醒你别上头。
不假装是专家，不端着，不假装一直在盯着看。
说话自然口语化，像微信聊天不是工作报告。

规则：
- 大部分时候闭嘴。只有真的注意到有趣/有用/不对劲的事才说话
- 如果画面很日常（桌面、浏览器首页）→ 不用说
- 如果刚才已经评论过类似内容 → 跳过

当前场景类别：{category}

你最近说过的话（别说重复的）：
{recent_comments}

现在用户屏幕上显示的是：
[图片]

用 JSON 回复，不要有额外内容：
{
  "should_comment": true/false,
  "comment": "如果说话，1-2句自然的口语。如果不说，空字符串",
  "category": "gaming|coding|trading|studying|writing|social|shopping|language|interview|design|health|general",
  "vibe": "用户当前的状态：focused(专注中，别打扰)|chill(放松，可以聊)|frustrated(遇到困难需要鼓励)|celebrating(值得一起高兴)"
}
```

### 聊天 Prompt（`chat.py` 使用）

```
你是「小幕」，一个朋友型桌面 AI 陪伴伙伴。

系统信息：现在 {time}，用户在用 {platform}

你的个性：
- 像大学室友，轻松、会吐槽、会鼓励
- 说话口语化，不端着
- 用户问你屏幕上什么东西时，认真看然后回答
- 如果不懂就说「这块我不太确定，要不要帮你搜一下？」然后等用户确认
- 用中文聊天

对话历史（最近 20 条）：
{chat_history}

当前屏幕截图已附带。

如果需要搜索最新信息（如游戏版本攻略），使用 web_search 工具。
```

### 场景化行为矩阵（朋友型）

| 场景 | 用户 vibe | 小幕的行为 |
|------|-----------|-----------|
| 打游戏，刚输了 | frustrated | "这队友确实离谱……要不先喝口水缓缓？下把再来" |
| 打游戏，正在团战 | focused | 不说（画面变化快，不打扰） |
| 打游戏，结算画面 | chill | "这装备出得可以啊，就是那个闪现有点抽象了哈哈" |
| 写代码，正常工作中 | focused | 不说 |
| 写代码，报错看了 3 分钟 | frustrated | "这报错看着像拼写问题？右上角那个变量名好像不太对" |
| 写代码，提交成功 | celebrating | "👏 功能通了！今天进度不错" |
| 看视频/刷社交媒体 | chill | 偶尔一起聊内容（"这视频讲的确实有道理"） |
| 凌晨 1 点了还在屏幕前 | tired | "快一点了，明天再搞吧？身体要紧" |
| 桌面发呆/切换窗口频繁 | unfocused | "感觉你在纠结什么？需要帮忙理一下吗" |
| 购物页面 | chill | "这个看着不错。不过我之前看到过类似的，要不要帮你比个价？" |

---

## 成本模型（Kimi K2.5）

每天 6 小时活跃，20 秒间隔 = 1080 次截图。去重跳过 70% → 324 张进入 AI。

| 环节 | 次数 | 每次 tokens | 日 cost | 日 ¥ |
|------|------|-----------|---------|------|
| 截图分析（high） | 324 | 1105 in + 100 out | $0.24 + $0.10 | ¥1.75 + ¥0.73 |
| 主动聊天 | ~20 轮 | 2000/轮 | ~$0.05 | ~¥0.36 |
| **合计** | | | **~$0.39** | **~¥2.8** |

> ¥5/天预算绰绰有余。测试阶段无需额外优化。

---

## 增量开发计划

原则：每完成一个模块，立即可以运行和验证。不攒一堆代码一起测。

### 里程碑 1：骨架能跑
- `pyproject.toml`、`.env.example`
- `config.py`（读 `.env`、类型化）
- `memory/database.py` + `models.py`（建表、连接）
- `utils/logger.py`、`utils/platform.py`、`utils/timing.py`
- `main.py`（启动→读配置→初始化 DB→打印就绪→退出）
- **验证**: `python -m screenchat` 启动，`~/.screenchat/` 目录出现、DB 文件存在

### 里程碑 2：截图能存
- `capture/image.py`（缩放、压缩、base64、hash）
- `capture/capturer.py`（定时线程、去重逻辑）
- **验证**: 每 5 秒截图，终端日志输出 "changed" / "duplicate"

### 里程碑 3：托盘能点
- `tray/_darwin.py`（rumps 菜单栏）
- `tray/_other.py`（pystray 托盘）
- `tray/controller.py`（统一接口）
- **验证**: 托盘图标出现，菜单有「打开」「退出」，点击退出正常关闭

### 里程碑 4：AI 能说话
- `ai/client.py`（Kimi K2.5 客户端，base_url 指向 Moonshot）
- `ai/prompts.py`（朋友型 prompt 模板）
- `ai/analyzer.py`（定时截图→调 AI→判断是否评论）
- `notification/notifier.py`（系统通知）
- **验证**: AI 在合适时机主动评论，终端打印或系统通知提示

### 里程碑 5：能聊天
- `ui/chat_window.py`（customtkinter 聊天窗口）
- `ai/chat.py`（主动对话逻辑）
- `hotkey/listener.py`（全局快捷键）
- **验证**: 点击托盘→弹出聊天窗口→发消息→AI 回复（含屏幕上下文）

### 里程碑 6：能设置
- `ui/settings.py`（设置对话框：间隔、冷却、场景开关、API key）
- **验证**: GUI 里改截图间隔，实时生效

### 里程碑 7：打磨打包（可选）
- 错误处理、日志轮转、PyInstaller

---

## 关键风险

| 风险 | 缓解 |
|------|------|
| pystray macOS GIL 崩溃 | macOS 用 rumps，建托盘抽象层 |
| macOS 截图权限未授予 | 启动时检测，弹引导 |
| AI 评论烦人 | 静音按钮、场景开关、反馈机制 |
| 快捷键冲突 | 可配置热键 |

---

## 验证方式

1. 每阶段独立验证（见增量开发计划）
2. `python -m screenchat` 开发模式运行
3. 单元测试：memory CRUD、config 解析、image hash
4. Mock 测试：mock Kimi 响应测 analyzer 逻辑
