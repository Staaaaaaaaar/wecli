# Linux 微信 AT-SPI 可行性验证

验证日期：2026-10-25，Asia/Shanghai。

以下保留早期试验和接入记录。当前已统一到 Conda，worker 不再调用系统 Python；
最新依赖和启动边界见[桌面运行环境](desktop-runtime.md)，Conda 验收见本文末尾。

## 结论

本机 Linux 微信 `4.1.1.4` 在启用 Qt 辅助功能后，可以通过 AT-SPI
定位 File Transfer（`filehelper`）会话、识别输入框、直接写入和回读中文多行文本，
并通过控件实时位置驱动 X11 点击完成发送。

此次验证是 AT-SPI + X11 混合方式：输入使用 `EditableText`，点击使用
`xdotool`。尚未验证完全依靠 AT-SPI Action、后台窗口或无桌面发送。

## 启动条件

本机为 X11、单显示器、2 倍缩放，系统 Python 可导入 `gi.repository.Atspi`。
此次在用户授权后重启微信，设置：

```bash
QT_ACCESSIBILITY=1 QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1 /usr/bin/wechat
```

启动前仅设置 `QT_ACCESSIBILITY=1` 时，主进程没有注册到 AT-SPI；
树中只有 `WeChatAppEx` 辅助进程。启用当前会话的 `org.a11y.Status.IsEnabled`
并带上两个环境变量重启后，出现 `application: wechat` 主窗口。
本次未修改系统启动项或桌面快捷方式。

## 实际验证

1. 从 `Chats` 列表识别 `File Transfer` 聊天项。
2. 按实时控件位置点击后，核对聊天标题和可编辑输入框名称均为 `File Transfer`。
3. 确认输入框为空，通过 `EditableText.set_text_contents` 写入测试消息，
   用 `Text.get_text` 完整回读匹配。未使用剪贴板。
4. 确认 `Send(S)` 按钮启用，重新核对收件人和草稿后，只点击一次发送。
5. 发送后输入框清空，`Messages` 列表出现测试正文。
6. 用现有 CLI 查询 `history filehelper --limit 10`，返回同一条本人消息，查询无失败。

测试正文：

```text
WeCLI AT-SPI 可行性测试 2026-10-25T21:07:12+08:00
中文与多行输入验证；对象：File Transfer。
```

本地历史返回：

```text
[2026-10-25 21:07] me: WeCLI AT-SPI 可行性测试 2026-10-25T21:07:12+08:00
中文与多行输入验证；对象：File Transfer。
```

以上证据确认了客户端操作和本地消息落库，未单独验证服务器回执或手机端接收。

## 实现时必须处理的问题

- **缩放转换**：本机 AT-SPI 返回逻辑坐标，X11 使用物理坐标；单屏 scale=2。
  未转换的点击未能切换到目标会话，标题检查及时阻止后续输入。
  正式实现需要动态检测缩放和显示器布局，不能固定乘 2。
- **动作缺失**：聊天列表项未暴露可用的点击动作；输入框和发送按钮主要暴露
  `SetFocus`。此次采用语义定位后点击实时位置，窗口必须可见且未被遮挡。
- **搜索事件**：搜索框直接写入文本后，没有立即产生搜索结果；
  触发实际键盘编辑事件后才出现结果。此次最终发送使用聊天列表定位，
  未完成搜索路径的端到端验证。
- **收件人身份**：File Transfer 是明确的内置目标；普通联系人重名、群聊重名、
  昵称改变和 wxid 到界面对象的映射仍需独立验证。
- **结果确认**：可结合本项目数据库读取，按目标 `filehelper`、唯一正文及时间
  核对新增记录；未知结果不能直接重发。

2026-10-25 的验证尚未接入 `send`。此后的项目集成见下节。

## 2026-10-27 项目接入验收

正式 `send` 已改用 AT-SPI 适配器。命令所在 Conda 环境为
`/home/sam/miniconda3/envs/wecli/bin/python`，worker 使用 `/usr/bin/python3`。
本次未重启微信或修改系统设置；当前微信已提供 AT-SPI。

通过 CLI（`send filehelper <中文多行文本> --yes`）发送一次，输出：

```json
{
  "status": "recorded",
  "recipient": "filehelper",
  "backend": "atspi",
  "ui_confirmed": true,
  "local_record_confirmed": true,
  "scale": 2,
  "local_record": {"local_id": 75, "create_time": 1793079838}
}
```

正文：

```text
WeCLI AT-SPI 集成验证 2026-10-27T13:43:57+08:00
通过正式 send 命令发送：中文、多行、输入回读和本地记录校验。
```

另通过正式 worker 的搜索路径搜索并打开 File Transfer，标题及输入框校验通过；
此检查未额外输入或发送消息。记录核对使用结构化数据库字段，排除基线已有同文记录和
非本人的 sender，不解析 history 的显示字符串。

当前仅 File Transfer 完成真实发送验收；普通好友、群聊和其他版本未实测。
仅支持单屏整数缩放 X11，拒绝多屏或无法确定缩放的布局。仍需可见且未遮挡的窗口。
本地落库和界面证据不证明手机端收到或服务器送达。

## 2026-10-27 Conda 统一环境验收

- 更新 wecli 环境下载约 42.3 MiB（Conda 安装计划中的 FETCH 合计）。
- 环境目录 `du -sk` 从 236480 KiB 增至 433284 KiB，新增约 192.2 MiB；
  不包含 Conda 下载缓存，硬链接也会影响真实磁盘增量。
- Python 3.10.22、PyGObject 3.58.0、GTK3 3.24.52、AT-SPI 2.40.3、
  xdotool 4.20260303.1。
- doctor 确认 GI、xdotool 和所检查的已加载原生库均在
  `/home/sam/miniconda3/envs/wecli` 内，`dependencies_in_prefix: true`。
- launch 已验证复用已有进程，以及按显式 restart 启动并保留辅助功能参数；
  已确认启动进程不含 Conda 的 LD_LIBRARY_PATH、GI_TYPELIB_PATH、CONDA_PREFIX。
- 通过当前环境向 File Transfer 发送中文多行文本，返回 `recorded`，
  `ui_confirmed: true`、`local_record_confirmed: true`，本地记录 ID 为 76。


系统 `xdotool`、`xclip`、`libxdo3` 清理后已重新核对：三个包均不再安装；
Conda 环境运行 `wecli doctor --format text` 仍返回 `ready`，
`dependencies_in_prefix: True`。此复核未发送新消息，也未执行登录操作。
