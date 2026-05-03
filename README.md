# ScreenChat 2.0

桌面 AI 陪伴助手——像老朋友一样安静地待在菜单栏，定时看一眼你的屏幕，觉得值得说话时才轻轻弹个气泡。

**macOS 优先**，Windows / Linux 后续适配。

## 怎么跑

```bash
# 1. 安装依赖
pip install -e .

# 2. 配置 API Key（二选一）

## 方式 A：环境变量
export SCREENCHAT_OPENAI_API_KEY=sk-你的key

## 方式 B：在应用里填（启动后点菜单栏图标 → 偏好设置）

# 3. 启动
python src/screenchat/loop.py
```

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
