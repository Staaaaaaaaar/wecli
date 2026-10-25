# Linux 开发与发布

## 环境与安装

当前开发和本地验证面向 Linux，使用 Python 3.10 或更高版本。微信数据查询需要同一台机器上的原生微信客户端及本地数据库。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
wecli --help
wecli --version
```

使用已有 Conda 环境时，先激活环境，再执行安装与检查命令，无需创建 `.venv`。更新代码后可重新执行 `python -m pip install -e .` 刷新命令入口。不要使用 sudo 安装依赖。

## 仓库结构

- `wecli/commands/`：命令实现。
- `wecli/core/`：配置、解密、缓存与数据库查询。
- `wecli/keys/scanner_linux.py`：Linux 进程检测与密钥提取。
- `wecli/keys/common.py`：密钥扫描和验证的共享逻辑。
- `wecli/output/`：输出格式化。
- `pyproject.toml`：包元数据、依赖、命令入口与资源配置。

## 本地检查

```bash
python -m compileall -q wecli
python -m unittest discover -s tests -v
wecli --help
wecli --version
wecli init --help
git diff --check
```

除 `init` 外，当前子命令会在显示帮助前加载配置，未初始化时可能提示缺少数据目录或密钥文件。

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
