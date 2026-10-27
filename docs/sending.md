# 发送文本消息

先完成 `wecli init`。日常启动和检查：

```bash
conda activate wecli
wecli launch        # 只启动微信，用户自行登录
wecli doctor        # 登录后检查环境，默认 JSON
```

`launch` 自动设置辅助功能参数；已有微信会复用。已有微信未启用辅助功能时，处理完未完成操作后，可显式运行 `wecli launch --restart`。wecli 不负责登录。`doctor` 无需密钥，不发送消息，报告当前 Python、工具和原生库路径。

```bash
wecli send filehelper "你好" --dry-run  # 解析和预览，不操作桌面
wecli send filehelper "你好"            # 确认一次后自动发送
wecli send "文件传输助手" "你好" --yes  # 跳过确认，供脚本使用
wecli send "唯一备注" --file message.txt --yes
printf '第一行\n第二行' | wecli send filehelper --file - --yes
```

自动选择聊天、核对标题和输入框、直接写入并回读文本，再点击发送按钮。
会短暂置前微信，完成后尽量恢复原窗口焦点和鼠标位置。点击发送按钮不依赖 Enter/Ctrl+Enter 设置，也不使用剪贴板。

收件人支持精确昵称、备注和 wxid，不使用模糊匹配。界面显示名称重名时，即使指定 wxid 也拒绝操作，请先设置唯一备注。普通联系人根据当前数据库中的唯一显示名称定位，仍依赖界面标题与联系人数据一致；这不是通过微信内部 ID 验证界面身份。File Transfer、文件传输助手和 `filehelper` 均对应内置对象。程序核对微信进程打开的数据目录与配置一致，拒绝跨账号操作。目标聊天已有草稿时停止，不覆盖内容；输入后取消或异常可能保留本次草稿，请自行检查。

默认输出 JSON，`--format text` 输出纯文本：

| status | 含义 | 退出码 |
|---|---|---|
| `dry_run` | 仅完成收件人和文本解析，未检查桌面 | 0 |
| `recorded` | 指定聊天新增了正文一致的本人本地记录 | 0 |
| `submitted` | 输入框清空且消息出现在界面，但本地记录未确认 | 0 |
| `unknown` | 操作可能已触发发送，结果无法确认 | 3 |

`ui_confirmed` 和 `local_record_confirmed` 分别表示界面及本地记录证据。以上均不代表服务器送达或对方已读。发送只尝试一次；结果不确定时先核对微信和 `history`，不要直接重跑。

**当前边界：** 单显示器 Linux X11、整数缩放；2 倍缩放已实测。拒绝多屏、缩放不一致、窗口焦点变化及屏幕外控件。保持微信窗口完整显示、桌面解锁，操作期间不要移动窗口或键鼠。不支持 Wayland、附件、@成员或锁屏后台发送。联系人会话未出现在列表时，会尝试精确搜索。

可用 `--window-id <十进制ID>` 指定主窗口，`--timeout 8` 设置每阶段等待时间（1–30 秒）。日常发送无需 sudo。worker 使用当前环境的 Python；Conda 下只使用本环境的 xdotool，缺包时明确报错。已移除旧的 `WECLI_ATSPI_PYTHON` 跨环境覆盖方式。

实测证据和限制见 [AT-SPI 验证记录](atspi-validation.md)。


依赖安装和启动配置见[桌面运行环境](desktop-runtime.md)。
