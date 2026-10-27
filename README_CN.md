# WeCLI

面向 Linux 原生微信的命令行工具，支持本地聊天记录查询、联系人和群成员查询、统计、导出，以及通过桌面客户端发送文本。

[English](README.md)

## 安装

当前开发和使用面向 Linux 原生微信客户端。推荐用独立 Conda 环境统一管理 Python、AT-SPI、GTK 和 xdotool，无需额外 apt 安装桌面库：

```bash
git clone https://github.com/Staaaaaaaaar/wecli.git
cd wecli
conda env create -f environment.yml
conda activate wecli
wecli --help
```

已有 `wecli` 环境时，在仓库根目录执行 `conda env update -n wecli -f environment.yml`。
更新源码后可执行 `python -m pip install --no-deps -e .` 刷新入口。运行依赖由 Conda 管理，pip 最后安装项目本身。详细环境说明见[桌面运行环境](docs/desktop-runtime.md)。

## 快速开始

### 1. 初始化

先运行 `wecli launch`，由用户在微信窗口自行登录，再在已激活的环境中执行：

```bash
wecli init
```

需要读取进程内存时，程序会自动请求 sudo 授权。密码输入时不会显示字符，输入系统登录密码后回车即可。扫描使用当前 Python 环境，配置和密钥由普通用户保存，无需额外执行 `chown`。

初始化会检测微信数据目录并提取密钥。检测到多个账号时，选择当前登录的账号。也可以指定数据目录：

```bash
wecli init --db-dir /path/to/db_storage
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

### `send` — 发送文本（Linux X11）

```bash
wecli launch                         # 只启动微信，用户自行登录
wecli doctor                         # 登录后检查环境
wecli send filehelper "你好" --dry-run
wecli send filehelper "你好"          # 确认一次后发送
wecli send "唯一备注" --file message.txt --yes
```

通过 AT-SPI 自动定位聊天、核对草稿并发送，支持单屏整数缩放 X11。
界面重名或已有草稿时停止；结果不确定时不自动重发。`recorded` 表示本地记录已确认，不代表送达。
输入方式、状态和限制见[发送说明](docs/sending.md)，依赖和启动配置见[桌面运行环境](docs/desktop-runtime.md)。

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

初始化通过 `/proc/<pid>/mem` 读取微信进程内存，通常需要 sudo。请保持 Linux 原生微信客户端运行并登录。安装、初始化和日常查询均以普通用户执行；初始化仅为密钥扫描自动请求 sudo 授权。

默认检测 `~/Documents/xwechat_files/*/db_storage` 和 `~/.local/share/weixin/data/db_storage`。数据保存在其他位置时，使用 `--db-dir` 指定。

如果提示未检测到微信进程，先确认客户端正在运行。检测到多个账号时，选择当前登录的账号。已完成初始化时会直接返回，使用 `wecli init --force` 重新扫描。

如果曾使用旧版 sudo 初始化且尚未恢复目录所有权，需要执行一次修复：

```bash
sudo chown -R "$(id -u):$(id -g)" "$HOME/.wecli"
```

## 开发与发布

仓库结构、本地验证和打包步骤见[开发与发布说明](docs/development.md)。

## 许可与来源

WeCLI 采用 [Apache-2.0](LICENSE) 许可，包含基于
[wechat-cli](https://github.com/huohuoer/wechat-cli) 修改的代码，由本项目独立维护。
归属说明见 [NOTICE](NOTICE)，沿用文件、修改范围及上游版本和附带二进制的
来源确认限制见[源码来源说明](docs/provenance.md)。
