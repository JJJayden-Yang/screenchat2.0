# ScreenChat 2.0

桌面 AI 陪伴助手——像老朋友一样安静地待在菜单栏，定时看一眼你的屏幕，觉得值得说话时才轻轻弹个气泡。

**macOS 优先**，Windows / Linux 后续适配。

## 快速开始

```bash
# 0. 确保 Python >= 3.11
python3 --version

# 1. 克隆 + 进目录
git clone https://github.com/JJJayden-Yang/screenchat2.0.git
cd screenchat2.0

# 2. 创建虚拟环境（可选但推荐）
python3 -m venv .venv
source .venv/bin/activate

# 3. 一键装所有依赖（mss、Pillow、openai、rumps、customtkinter 等）
pip install -e .

# 4. 配 API Key → 去 https://platform.moonshot.ai 申请
#    方式 A：写环境变量
export SCREENCHAT_OPENAI_API_KEY=sk-你的key

#    方式 B：启动后在菜单栏「小幕」→ 偏好设置里填

# 5. 跑
python src/screenchat/loop.py
```

菜单栏出现「小幕」图标，看到 `启动了~` 就成功了。

## 做了什么

```
菜单栏「小幕」
  ├── 🔊/🔇 静音        ← 一键关掉 AI 自动评论
  ├── 最近记录...        ← 今天的对话历史
  ├── 偏好设置...        ← API Key、截图间隔、记忆长度
  └── 退出

后台每 20 秒：
  截图 → dHash 去重 → Kimi K2.5 看画面 → 值得说就弹通知
```

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

```
src/screenchat/
├── loop.py         # 核心 while-true 循环
├── config.py       # 配置管理
├── tray/
│   ├── icon.py     # 菜单栏图标 + 菜单
│   └── icon.png    # 占位图标
├── memory/
│   ├── database.py # SQLite 读写
│   └── models.py   # 数据模型
└── ui/
    ├── history_window.py   # 今日记录窗口
    └── settings_window.py  # 偏好设置窗口
```

## 配置项

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `api_key` | - | Moonshot API Key |
| `capture_interval` | 20 | 截图间隔（秒） |
| `memory_maxlen` | 20 | 消息记忆条数 |

## 记忆系统

三层递进，避免重复评论 + 省钱：

- **Layer 1** — 消息序列记忆：deque 存最近 N 轮对话，旧轮无图仅文本
- **Layer 2** — 场景摘要压缩：记忆快满时调 AI 压缩旧轮为一句话
- **Layer 3** — 感知哈希去重：dHash 汉明距离 <5 跳过 API

## 对话持久化

AI 每次说话写入 `~/.screenchat/history.db`，按天分表，启动时自动恢复今天的记忆。
