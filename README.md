# ScreenChat 2.0

菜单栏目标陪跑器。小幕默认安静待着；你开始一段目标陪跑后，它才定时看屏幕，在你偏离目标、卡住太久或完成阶段时弹出有行动价值的提醒。

**macOS 优先**，Windows / Linux 后续适配。

## 快速开始

```bash
# 0. 确保 Python >= 3.11
python --version

# 1. 克隆 + 进目录
git clone https://github.com/JJJayden-Yang/screenchat2.0.git
cd screenchat2.0

# 2. 创建虚拟环境（可选但推荐）
python -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
python -m pip install -e .

# 4. 配 API Key → 去 https://platform.moonshot.ai 申请
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

不要在 `src/screenchat/` 目录里直接运行 `python loop.py`，那样 Python 找不到顶层 `screenchat` 包。

## 核心用法

菜单栏「小幕」：

```text
开始陪跑...
暂停提醒 / 恢复提醒
对话...
偏好设置...
退出
```

点「开始陪跑...」后填写：

- 本轮目标：例如「15 分钟看学习视频」「45 分钟修完启动报错」
- 目标类型：写代码/修 bug、学习/看文档、防走神、自定义
- 时长：25、45、60 分钟或自定义
- 强度：轻、标准、严格

陪跑中，小幕会把屏幕判断成：

- `on_track`：正在推进目标，保持安静
- `distracted`：明显偏离目标，弹气泡提醒
- `stuck`：和目标相关但像是卡住了，询问是否帮忙
- `milestone`：完成阶段，给下一步建议
- `unclear`：看不懂或不确定，保持安静

主动提醒必须包含「观察 + 和目标的关系 + 下一步动作」。纯吐槽、泛泛鼓励会被拦掉。

## 主动聊天

点「对话...」可以打开聊天窗口。你可以主动问：

- 帮我看这个报错
- 当前页面在讲什么
- 总结一下这页文档
- 我下一步该做什么

聊天窗口会展示当天普通对话、陪跑提醒和陪跑总结。

## 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.11+ |
| AI | Kimi K2.5（OpenAI SDK + Moonshot） |
| 截图 | mss + Pillow |
| 菜单栏 | rumps（macOS 原生） |
| 窗口 | customtkinter |
| 存储 | SQLite（`~/.screenchat/history.db`） |
| 配置 | settings.json > .env > 默认值 |

## 项目结构

```text
src/screenchat/
├── loop.py              # 主循环、进程/线程编排、AI 调用
├── coaching.py          # 陪跑会话、强度规则、状态判断、提醒判定
├── config.py            # 配置管理
├── tray/
│   ├── icon.py          # 菜单栏图标 + 菜单 + 通知
│   └── icon.png
├── memory/
│   ├── database.py      # SQLite 读写
│   └── models.py        # 数据模型
└── ui/
    ├── coaching_window.py   # 开始陪跑窗口
    ├── chat_window.py       # 对话和历史窗口
    └── settings_window.py   # 偏好设置窗口
```

## 配置项

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `SCREENCHAT_OPENAI_API_KEY` | - | Moonshot API Key |
| `SCREENCHAT_AGENT_MODEL` | `kimi-k2.5` | 模型名 |
| `SCREENCHAT_OPENAI_BASE_URL` | `https://api.moonshot.ai/v1` | OpenAI 兼容接口地址 |
| `SCREENCHAT_CAPTURE_INTERVAL` | `20` | 截图间隔（秒） |
| `SCREENCHAT_MEMORY_MAXLEN` | `20` | 消息记忆条数 |

## 运行日志说明

```text
· (idle)
```

当前没有活动陪跑任务，小幕保持安静。

```text
· (dup)
```

当前截图和上一张几乎一样，dHash 去重后跳过 AI 调用。

```text
· (distracted: 提醒缺少行动价值)
```

AI 判断偏离目标，但返回的提醒不包含清晰下一步动作，所以没有弹气泡。

```text
💬 ...
```

已经通过提醒判定，并推送到 macOS 通知。

## 常见问题

### 找不到 `screenchat` 包

不要在 `src/screenchat/` 目录里跑 `python loop.py`。请回到项目根目录：

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
- 当前陪跑还没结束；日志显示 `· (idle)` 代表没有活动陪跑

## 验证

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPYCACHEPREFIX=/private/tmp/screenchat-pycache python -m compileall -q src tests
```
