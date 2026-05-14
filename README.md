# ScreenChat 2.0

小幕是一个 macOS 菜单栏目标陪跑器。它平时不在后台持续分析屏幕；只有你主动开始一轮专注陪跑后，它才会按节奏看屏幕，在偏离目标、卡住、完成节点或屏幕长期不变时弹出提醒，并把本轮过程沉淀到专注星图。

当前定位：少说废话、少花钱、只在目标相关场景里介入。

## 快速开始

```bash
# 0. 确保 Python >= 3.11
python --version

# 1. 克隆 + 进入项目根目录
git clone https://github.com/JJJayden-Yang/screenchat2.0.git
cd screenchat2.0

# 2. 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
python -m pip install -e .

# 4. 配 API Key
export SCREENCHAT_OPENAI_API_KEY=sk-你的key

# 5. 启动
python -m screenchat
```

如果使用 conda：

```bash
conda activate ai-learning
cd /Users/yangjiangyi/develop/ai_repo/screenchat2.0
python -m pip install -e .
python -m screenchat
```

不要在 `src/screenchat/` 目录里直接运行 `python loop.py`，那样 Python 找不到顶层 `screenchat` 包，也不会自动安装依赖。

## 核心功能

### 目标陪跑

菜单栏点击「开始陪跑...」后填写：

- 本轮目标：例如「看 30 分钟学习视频」「修完启动报错」「写完 todo 再写代码」
- 目标类型：写代码/修 bug、学习/看文档、防走神、自定义
- 时长：25、45、60 分钟或自定义
- 强度：轻、标准、严格

陪跑中，小幕会把屏幕判断成：

- `on_track`：正在推进目标，保持安静，并逐渐拉长下一次 AI 检测间隔
- `distracted`：明显偏离目标，弹出带下一步动作的提醒
- `stuck`：和目标相关但像是卡住了，询问是否需要帮忙
- `milestone`：完成阶段节点，建议下一步
- `unclear`：看不懂或置信度低，保持安静
- `idle`：屏幕长时间不变，可能离开电脑或在看手机

主动提醒必须包含「观察 + 和目标的关系 + 下一步动作」。纯吐槽、泛泛鼓励会被拦掉。

### 动态检测节奏

小幕使用两套节奏，目标是省钱又不丢关键提醒：

1. AI 分析节奏：专注正常时指数退避，例如标准强度从 1 分钟开始，逐步到 2、4、8、15 分钟。
2. 屏幕未变化节奏：如果截图感知哈希几乎不变，不调用 AI，只每 60 秒做一次轻量变化检测。

当屏幕连续不变达到阈值时，小幕会认为进入 `idle`：

| 强度 | 第一次待机提醒 |
|------|----------------|
| 轻 | 8 分钟 |
| 标准 | 5 分钟 |
| 严格 | 3 分钟 |

进入待机后，每隔约 3 分钟可以继续提醒一次。屏幕一旦变化，会立刻回到 AI 分析流程。

### 暂停与结束

陪跑中菜单会显示：

- `Ⅱ 暂停专注`：每轮最多暂停 2 次
- `▶ 继续专注（MM:SS）`：暂停中显示剩余暂停时间
- `结束陪跑`：提前结束会弹出鼓励通知

每轮暂停最长 2 分钟。专注倒计时归零后会自动结束，并强制弹出结束通知，即使当前处于「暂停提醒」状态。

### 专注总结

每轮结束后会记录：

- 计划时长
- 有效专注时长
- 暂停次数
- 待机时间
- 是否提前结束
- 过程时间线：开始、屏幕观察、提醒、待机、结束

有效专注时长会扣掉暂停和待机时间。

### 专注星图

菜单栏点击「专注星图...」会生成并打开：

```text
~/.screenchat/focus_dashboard.html
```

星图规则：

- 一周一个星系
- 每轮完成的专注生成一个真实天体
- 专注越久，越容易解锁更稀有的天体
- 每颗星体有真实天体简介、贴图或程序化地貌
- 右侧面板展示本轮专注记录和待机时间
- 底部周度切换用于查看不同周的星系

### 主动聊天

点击「对话...」可以主动询问小幕：

- 帮我看这个报错
- 当前页面在讲什么
- 总结一下这页文档
- 我下一步该做什么

主动聊天默认不带截图，只有你勾选或选择带截图时才会上传当前屏幕，避免不必要的费用。

## 菜单说明

无活动陪跑时：

```text
开始陪跑...
暂停提醒 / 恢复提醒
专注星图...
对话...
偏好设置...
退出
```

陪跑中：

```text
陪跑中：目标 24:59
Ⅱ 暂停专注
结束陪跑
暂停提醒 / 恢复提醒
专注星图...
对话...
偏好设置...
退出
```

## 运行日志说明

```text
· (on_track: 当前无需介入)
```

屏幕和目标相关，本轮保持安静。

```text
· (distracted: 偏离时间未达阈值)
```

AI 判断偏离，但还没达到当前强度要求的持续时间。

```text
· (idle: 屏幕未变化 5 分钟)
```

截图几乎没变化，本轮进入待机统计。这个阶段不调用 AI，只做轻量变化检测。

```text
💬 ...
```

提醒通过判定，并推送到 macOS 通知。

```text
⚠ Request timed out.
```

模型接口超时，本轮会继续循环，不会退出应用。

## 配置项

配置读取顺序：`~/.screenchat/settings.json` > `.env` > 默认值。

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `SCREENCHAT_OPENAI_API_KEY` | - | Moonshot 或兼容 OpenAI API 的 Key |
| `SCREENCHAT_AGENT_MODEL` | `kimi-k2.5` | 模型名，可按服务商实际模型调整 |
| `SCREENCHAT_OPENAI_BASE_URL` | `https://api.moonshot.ai/v1` | OpenAI 兼容接口地址 |
| `SCREENCHAT_CAPTURE_INTERVAL` | `20` | 无陪跑时基础睡眠间隔；陪跑中主要由动态检测节奏控制 |
| `SCREENCHAT_MEMORY_MAXLEN` | `20` | 主动聊天和提醒的短期上下文条数 |

## 数据位置

```text
~/.screenchat/history.db
~/.screenchat/settings.json
~/.screenchat/focus_dashboard.html
~/.screenchat/focus_dashboard_assets/
```

`history.db` 是 SQLite 数据库，保存普通对话、陪跑事件、总结、待机时间和星图所需数据。

## 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.11+ |
| AI | Kimi / Moonshot OpenAI 兼容接口 |
| 截图 | mss + Pillow |
| 屏幕变化检测 | imagehash dHash |
| 菜单栏 | rumps（macOS 原生） |
| 窗口 | customtkinter |
| 存储 | SQLite |
| 星图 | HTML + Three.js |

## 项目结构

```text
src/screenchat/
├── loop.py                  # 主循环、陪跑编排、AI 调用、通知队列
├── coaching.py              # 陪跑会话、强度规则、提醒判定、总结
├── config.py                # 配置管理
├── tray/
│   ├── icon.py              # 菜单栏图标、菜单、macOS 通知
│   └── icon.png
├── memory/
│   ├── database.py          # SQLite 读写和兼容迁移
│   └── models.py            # 数据模型
└── ui/
    ├── coaching_window.py   # 开始陪跑窗口
    ├── chat_window.py       # 对话和历史窗口
    ├── focus_dashboard.py   # 3D 专注星图生成器
    └── settings_window.py   # 偏好设置窗口
```

## 常见问题

### 找不到 `screenchat` 包

请回到项目根目录运行：

```bash
cd /Users/yangjiangyi/develop/ai_repo/screenchat2.0
python -m pip install -e .
python -m screenchat
```

### 缺少 `imagehash` 或其它依赖

当前环境没有安装项目依赖：

```bash
python -m pip install -e .
```

### 没有收到通知气泡

检查三件事：

- 菜单栏不是「恢复提醒」状态
- macOS 系统设置里允许 Python/终端发送通知
- 当前确实处于活动陪跑中；无陪跑时小幕不会持续监控屏幕

### 为什么后台不一直输出 `idle`

无活动陪跑时小幕会安静睡眠，不做屏幕分析。`idle` 只表示活动陪跑中屏幕长时间没有变化，并会计入本轮待机时间。

### 怎么控制费用

费用主要来自 AI 看图。当前策略已经尽量降低调用次数：

- 无陪跑时不看屏幕
- 屏幕不变时只做本地 dHash，不调用 AI
- 专注正常时检测间隔会逐步拉长到上限
- 主动聊天默认不带截图

想进一步省钱，可以把陪跑强度设为「轻」，或把本轮目标拆成更短、更明确的小段。

## 验证

```bash
PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/screenchat-pycache python -m unittest discover -s tests
PYTHONPATH=src PYTHONPYCACHEPREFIX=/private/tmp/screenchat-pycache python -m compileall -q src tests
```
