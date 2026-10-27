# Linux 开发与发布

## 环境与安装

当前开发和本地验证面向 Linux，使用 Python 3.10 或更高版本。微信数据查询需要同一台机器上的原生微信客户端及本地数据库。

```bash
conda env create -f environment.yml
conda activate wecli
wecli --help
wecli --version
```

已有环境使用 `conda env update -n wecli -f environment.yml` 更新。
更新代码后可执行 `python -m pip install --no-deps -e .` 刷新命令入口。不要使用 sudo 安装依赖。
环境来源、自检和启动边界见[桌面运行环境](desktop-runtime.md)。

## 仓库结构

- `wecli/commands/`：命令实现。
- `wecli/core/`：配置、解密、缓存与数据库查询。
- `wecli/keys/scanner_linux.py`：Linux 进程检测与密钥提取。
- `wecli/keys/common.py`：密钥扫描和验证的共享逻辑。
- `wecli/output/`：输出格式化。
- `pyproject.toml`：包元数据、Python 依赖、命令入口与资源配置。
- `environment.yml`：Conda 运行环境与桌面原生依赖。
- `docs/sending.md`：发送参数、状态和限制。
- `docs/desktop-runtime.md`：依赖管理、启动和诊断。
- `docs/atspi-validation.md`：历史试验及当前环境验收证据。

## 本地检查

```bash
python -m compileall -q wecli
python -m unittest discover -s tests -v
wecli --help
wecli --version
wecli init --help
wecli doctor --help
wecli launch --help
wecli send --help
git diff --check
```

除 `init`、`send`、`doctor` 和 `launch` 外，当前子命令会在显示帮助前加载配置，未初始化时可能提示缺少数据目录或密钥文件。

真实数据验证请按 [中文使用说明](../README_CN.md) 以普通用户运行 `wecli init`，然后运行会话查询、历史查询和导出。Linux 初始化只为密钥扫描启动 sudo 子进程，沿用当前环境的 Python 绝对路径；子进程经管道返回密钥，父进程保存配置与密钥，无需恢复目录所有权。自动化测试覆盖授权调用、失败保护和子进程输出协议，不代替真实 sudo 与微信数据验证。

配置和密钥保存在 `~/.wecli/`，可用 `WECLI_CONFIG` 或全局 `--config` 参数指定查询配置。密钥、数据库和聊天导出内容不应提交到仓库。

## 构建与安装验证

版本号当前为 `0.1.0`。更新版本时同步修改 `pyproject.toml` 和 `wecli/main.py`。

```bash
python -m pip install build
python -m build
python3 -m venv /tmp/wecli-release-check
/tmp/wecli-release-check/bin/python -m pip install dist/wecli-*.whl
/tmp/wecli-release-check/bin/wecli --help
/tmp/wecli-release-check/bin/wecli --version
```

`dist/` 保存源码包与 wheel；`build/`、`dist/`、`*.egg-info/` 和 Python 缓存均为生成文件，不应提交。构建与启动检查通过后，仍需使用真实微信数据验证核心命令，再进行发布。

## 发送命令

- `commands/send.py`：文本输入、一次确认、JSON 输出和退出码。
- `core/sending.py`：实时联系人读取、精确目标解析、本地新增本人记录核对。
- `core/desktop.py`：以 JSON stdin/stdout 启动当前 Python 的 AT-SPI worker。
- `core/atspi_worker.py`：AT-SPI 控件定位、单屏缩放检查、账号目录核对、
  输入回读、发送按钮点击、界面核对及焦点恢复。

查询、联系人解析与 worker 使用同一 Python 环境。`environment.yml` 统一声明
PyGObject、GTK3、AT-SPI 和 xdotool；worker 使用环境内的原生库和工具。
`core/runtime.py` 负责工具解析和环境清理，`doctor` 读取实际加载路径及桌面状态，
`launch` 仅启动微信，不负责用户登录。
worker 是普通 Python 包模块，wheel 必须包含该文件。

发送操作以用户级文件锁互斥；使用显示名称定位，不保证同名账号或过期数据库下的
稳定 ID 映射。拒绝当前联系人数据中的显示名称歧义，核对进程打开的数据目录和目标标题。
不写微信数据库，不使用剪贴板，不覆盖已有草稿，不自动重试。
读取数据库的确认依据为目标表、正文、本人 sender、时间和基线中不存在的 local_id，
不会把历史同文或对方发来的消息当成本次回执。

自动化测试使用替身和临时 SQLite，覆盖取消、焦点/收件人变化、已有草稿、
坐标缩放、显示名称歧义、超时/异常一次尝试、界面与本地记录状态。
真实命令已在 File Transfer 上完成中文多行发送验证，见
[验证记录](atspi-validation.md)。普通好友和群聊、其他客户端版本尚未实测。

接口参考：[AT-SPI](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/)、
[GDK monitor](https://docs.gtk.org/gdk3/class.Monitor.html)、
[xdotool](https://github.com/jordansissel/xdotool/blob/main/xdotool.pod)。
