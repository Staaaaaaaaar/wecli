# WeCLI

面向 Linux 原生微信的命令行工具，支持本地聊天记录查询、联系人和群成员查询、统计、导出，以及通过桌面客户端发送文本。

当前版本：**0.1.1**。功能范围与已知限制见[版本记录](CHANGELOG.md)，也支持浏览本地朋友圈缓存。

[English](README.md)

## 安装

仅支持 Linux 原生微信客户端。推荐用独立 Conda 环境统一管理 Python、AT-SPI、GTK 和 xdotool，无需额外 apt 安装桌面库：

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

多数命令默认输出便于阅读的文本，`new-messages` 默认 JSON，可通过 `--format json` 获取机器可读结果；`export` 支持 Markdown 和纯文本。使用 `wecli <命令> --help` 查看选项。

## CLI 约定

工具生成的帮助、提示、状态标签和日志统一为英文；联系人和消息正文保留原文。
默认文本格式不会因管道或重定向自动切换，脚本应显式使用 `--format json`。
原有 JSON 字段结构保留，工具生成的类型名称和提示文案改为英文。
结果写入 stdout，进度、确认提示和诊断写入 stderr。
所有命令的 `-h` / `--help` 均无需初始化或读取微信数据。

退出码：`0` 成功（包含空结果）、`1` 运行失败、`2` 参数或用法错误、`3` 发送结果不确定。
非交互发送必须指定 `--yes`；`--dry-run` 只预览。
配置优先级为 `--config` > `WECLI_CONFIG` > `~/.wecli/config.json`，`init` 同样遵循。
非交互模式检测到多个账号时明确报错，要求指定目录或配置。

Bash 补全：`eval "$(_WECLI_COMPLETE=bash_source wecli)"`。
完整输出与兼容性约定见 [CLI conventions](docs/cli-conventions.md)。

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

发送前请手动解锁桌面并保持微信可见。当前 `doctor` 不检测锁屏，锁屏时仍可能报告
`ready`，但无法正常发送。真实发送仅在微信 4.1.1.4 的 File Transfer 上验证；
普通好友、群聊和其他客户端版本尚未完成实测。

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

### `moments` — 本地朋友圈

```bash
wecli moments list --limit 20
wecli moments list --user "张三" --since 2026-01-01 --until 2026-10-27
wecli moments search "旅行" --user "张三"
wecli moments show <id>
wecli moments list --before <next_cursor> --limit 20
```

`list` 和 `search` 按发布时间倒序，支持 `--user`、`--since`、`--until`、
`--limit`（1–1000）和 `--before`。作者精确匹配微信 ID、昵称或备注；重名时
请使用微信 ID。结束日期包含当天；时间按本机时区解释。分页时沿用原筛选条件，
将输出的 `next_cursor` 传给 `--before`，末页游标为 `null`。

`search` 仅对正文进行不区分大小写的字面搜索，不搜索评论。
`show` 显示正文、地点、媒体地址及参数、缓存中的点赞和评论；ID 使用列表输出的字符串。
三个指令默认输出便于阅读的文本，均支持 `--format json`。

仅查询本机缓存，不联网获取帖子或下载媒体，不保证历史、点赞评论及最新 WAL 增量完整。
JSON 包含 `source` 和 `notice`；列表通过 `parse_failures` 报告格式异常，
无法确定发布时间的帖子不会进入列表，可使用 `show` 按 ID 检查。

### `unread` — 未读会话

```bash
wecli unread                          # 所有未读会话
wecli unread --limit 10 --format text
```

### `new-messages` — 逐条增量读取

```bash
wecli new-messages --limit 100
wecli new-messages --cursor "$CURSOR" --limit 100
```

逐条返回消息和绑定账号的游标。处理成功后持久化 `next_cursor`，重放时按 `message_id` 去重。详见[服务集成契约](docs/service-integration.md)。

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

配置、密钥和会话快照保存在 `~/.wecli/`。可通过全局参数指定其他配置文件：

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
