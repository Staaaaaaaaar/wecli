# WeCLI

面向 Linux 本地微信数据的命令行工具，用于查询本地聊天记录、联系人、群成员、会话和收藏，支持聊天统计与导出。

[English](README.md)

## 安装

当前开发和使用面向 Linux 原生微信客户端，需要 Python 3.10 或更高版本。使用虚拟环境从源码安装：

```bash
git clone https://github.com/Staaaaaaaaar/wecli.git
cd wecli
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
wecli --help
```

使用 Conda 时，激活已有环境即可，无需再创建 `.venv`。更新源码后可重新执行 `python -m pip install -e .` 刷新命令入口。

## 快速开始

### 1. 初始化

先启动微信并登录。在 Linux 的已激活 Python 环境中执行：

```bash
sudo env HOME="$HOME" "$(python -c 'import sys; print(sys.executable)')" -m wecli.main init
sudo chown -R "$(id -u):$(id -g)" "$HOME/.wecli"
```

sudo 密码输入时不会显示字符，输入系统登录密码后回车即可。使用当前环境的 Python 绝对路径可以避免 sudo 找不到 Conda 或虚拟环境中的命令。

初始化会检测微信数据目录并提取密钥。检测到多个账号时，选择当前登录的账号。也可以指定数据目录：

```bash
sudo env HOME="$HOME" "$(python -c 'import sys; print(sys.executable)')" -m wecli.main init --db-dir /path/to/db_storage
sudo chown -R "$(id -u):$(id -g)" "$HOME/.wecli"
```

### 2. 查询数据

初始化后，日常查询无需 sudo：

```bash
wecli sessions --limit 10
wecli history "张三" --limit 20
wecli search "截止日期" --chat "项目组"
wecli contacts --query "李"
```

查询命令默认输出 JSON，可通过 `--format text` 查看纯文本；`export` 支持 Markdown 和纯文本。使用 `wecli <命令> --help` 查看选项。

## 使用说明

### `sessions` — 最近会话

```bash
wecli sessions                        # 最近 20 个会话
wecli sessions --limit 10             # 最近 10 个
wecli sessions --format text          # 纯文本输出
```

### `history` — 聊天记录

```bash
wecli history "张三"                  # 最近 50 条消息
wecli history "张三" --limit 100 --offset 50
wecli history "交流群" --start-time "2026-04-01" --end-time "2026-04-03"
wecli history "张三" --type link      # 只看链接
wecli history "张三" --format text
```

**选项：** `--limit`、`--offset`、`--start-time`、`--end-time`、`--type`、`--format`

### `search` — 搜索消息

```bash
wecli search "项目"                 # 全局搜索
wecli search "项目" --chat "交流群"  # 指定聊天搜索
wecli search "开会" --chat "群A" --chat "群B"  # 多个聊天
wecli search "报告" --type file        # 只搜文件
```

**选项：** `--chat`（可多次指定）、`--start-time`、`--end-time`、`--limit`、`--offset`、`--type`、`--format`

### `contacts` — 联系人搜索与详情

```bash
wecli contacts --query "李"           # 搜索联系人
wecli contacts --detail "张三"        # 查看详情
wecli contacts --detail "wxid_xxx"    # 通过 wxid 查看
```

详情包括：昵称、备注、微信号、个性签名、头像 URL、账号类型。

### `members` — 群成员列表

```bash
wecli members "项目组"              # 成员列表
wecli members "项目组" --format text
```

### `stats` — 聊天统计

```bash
wecli stats "项目组"
wecli stats "张三" --start-time "2026-04-01" --end-time "2026-04-03"
wecli stats "项目组" --format text
```

返回：消息总数、类型分布、发言 Top 10、24 小时活跃分布。

### `export` — 导出聊天记录

```bash
wecli export "张三" --format markdown              # 输出到 stdout
wecli export "张三" --format txt --output chat.txt  # 输出到文件
wecli export "群聊" --start-time "2026-04-01" --limit 1000
```

**选项：** `--format markdown|txt`、`--output`、`--start-time`、`--end-time`、`--limit`

### `favorites` — 微信收藏

```bash
wecli favorites                       # 最近收藏
wecli favorites --type article        # 只看文章
wecli favorites --query "计算机网络"    # 搜索收藏
```

**类型：** text、image、article、card、video

### `unread` — 未读会话

```bash
wecli unread                          # 所有未读会话
wecli unread --limit 10 --format text
```

### `new-messages` — 增量新消息

```bash
wecli new-messages                    # 首次: 返回未读消息 + 保存状态
wecli new-messages                    # 后续: 仅返回上次以来的新消息
```

状态保存在 `~/.wecli/last_check.json`，删除此文件可重置。

---

## 消息类型过滤

`--type` 选项（适用于 `history` 和 `search`）：

| 值 | 说明 |
|---|------|
| `text` | 文本消息 |
| `image` | 图片 |
| `voice` | 语音 |
| `video` | 视频 |
| `sticker` | 表情 |
| `location` | 位置 |
| `link` | 链接/应用消息 |
| `file` | 文件 |
| `call` | 音视频通话 |
| `system` | 系统消息 |

---

## 配置

配置、密钥和增量查询状态保存在 `~/.wecli/`。可通过全局参数指定其他配置文件：

```bash
wecli --config /path/to/config.json sessions
```

也可设置 `WECLI_CONFIG` 环境变量。内部 Python 模块名为 `wecli`。

## Linux 使用说明

初始化通过 `/proc/<pid>/mem` 读取微信进程内存，通常需要 sudo。请保持 Linux 原生微信客户端运行并登录。安装和日常查询使用普通用户执行。

默认检测 `~/Documents/xwechat_files/*/db_storage` 和 `~/.local/share/weixin/data/db_storage`。数据保存在其他位置时，使用 `--db-dir` 指定。

如果提示未检测到微信进程，先确认客户端正在运行。检测到多个账号时，选择当前登录的账号。初始化后执行上方的目录所有权恢复命令，确保普通用户可以更新 `~/.wecli/` 中的状态。

## 开发与发布

仓库结构、本地验证和打包步骤见[开发与发布说明](docs/development.md)。
