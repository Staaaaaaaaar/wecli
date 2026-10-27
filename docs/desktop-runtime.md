# 桌面运行环境

## 创建和更新

在仓库根目录运行：

```bash
conda env create -f environment.yml
conda activate wecli
wecli launch
# 用户在微信窗口自行登录。
wecli doctor
wecli init
wecli send filehelper "你好" --dry-run
```

已有同名环境时使用：

```bash
conda env update -n wecli -f environment.yml
conda activate wecli
```

环境文件通过 conda-forge 安装 Python 3.10、PyGObject、GTK3、AT-SPI、xdotool
及查询依赖，最后由 pip 安装当前项目。不要再通过 pip 覆盖这些已由 Conda 管理的
原生依赖。更新代码的入口检查可使用 `python -m pip install --no-deps -e .`。

GTK3 的 conda-forge 构建目前依赖 at-spi2-atk 2.38，而该包约束 AT-SPI core 2.40
系列，因此环境文件明确选用 `at-spi2-core=2.40.*`。盲目把 core 提升到最新版会
导致依赖无法求解。今后升级时先 dry-run，再做真实发送验证。

已对 `environment.yml` 执行空环境 dry-run，得到完整的 conda-forge 求解计划；
尚未另外安装一份全新环境。当前环境是从已有 wecli 环境增量更新并实测。
环境文件固定主要兼容范围，不是所有传递依赖的精确版本锁文件。

## 环境边界

- 查询与 AT-SPI worker 均使用当前环境的 Python，即 `sys.executable`。
- Conda 下只选择 `sys.prefix/bin/xdotool`，缺失时不回退系统命令。
- worker 优先使用环境内 typelibs 和 GIO 模块，并移除外部动态库注入变量。
- 普通非 Conda 环境仍可使用自己安装的 GI 绑定及 PATH 中的 xdotool，
  但不自动调用系统 Python。
- `WECLI_ATSPI_PYTHON` 已移除；不支持通过它混用另一个 Python。
- 官方微信仍由系统安装；X11、桌面 D-Bus 和辅助功能注册服务属于用户桌面。
  Conda 负责客户端库，不另起一个隔离总线，以便发现正在运行的微信。

## 启动与登录

`wecli launch` 为官方微信添加 `QT_ACCESSIBILITY=1` 和
`QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1`，并清理 Conda 的 PATH、动态库注入、
插件和 GI 搜索路径，保留显示、会话总线、输入法及显示缩放设置。
不会让官方微信继承 wecli 的 GTK/Qt 库路径。

默认复用已运行的微信。若已有微信只是在等待登录，返回 `awaiting_login`，
提示用户自行登录。若未暴露辅助功能，则提示先检查 doctor，必要时显式执行：

```bash
wecli launch --restart
```

`--restart` 会向已有微信发送 SIGTERM 并等待退出；超过 10 秒则停止，不强制终止。
执行前请处理未完成的传输与编辑。启动器不点击登录入口、不扫码、不确认手机登录，
也不会在 send 或 doctor 中自动重启微信。

非默认安装路径可用 `wecli launch --executable /path/to/wechat` 指定。
客户端日志追加到 `~/.wecli/wechat.log`（新建文件权限 0600），不输出到命令 JSON。

## 检查

```bash
wecli doctor
wecli doctor --format text
```

不需要数据库密钥，也不发送消息。JSON 包含：

- `python`、`prefix`、`gi_path`、`xdotool`：实际解释器及工具路径。
- `native_libraries`：从进程映射读取的已加载 AT-SPI、GDK、GI、GLib 等路径。
- `dependencies_in_prefix`：这些已检查的桌面依赖是否全部位于当前环境。
- `wechat_apps`、`database_roots`：辅助功能主进程与打开的微信数据目录。
- `monitors`、`ready`：显示配置及基本就绪状态。

未登录、无桌面连接、缺包或多个主进程时退出 1。Conda 下发现跨环境依赖也不报告就绪。
`ready` 仅表示基本运行条件满足，不证明特定联系人可定位、草稿为空或消息已送达；
send 仍执行账号、坐标、焦点、收件人和消息检查。

本机实测与系统依赖清理后的检查见[验证记录](atspi-validation.md)。
