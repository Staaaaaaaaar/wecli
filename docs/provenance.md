# 源码来源与许可说明

本文件记录 WeCLI 的来源、沿用范围及已知限制；不修改根目录 LICENSE 的条款。

## 上游与版本确认情况

- 上游项目：<https://github.com/huohuoer/wechat-cli>。
- 已检查的参考版本：`a3789232d4f79bf0b30634d9dadbce71e4acd601`（上游版本号 0.2.4）。
- 该参考版本的 [LICENSE](https://github.com/huohuoer/wechat-cli/blob/a3789232d4f79bf0b30634d9dadbce71e4acd601/LICENSE) 为 Apache-2.0；其根目录没有列出 NOTICE。
- 上游 README 同时引用了 `freestylefly/wechat-cli`；这里保留这一线索，不将托管账号直接认定为全部代码的版权人。
- 本仓库历史从 `59d5d88f1fcf57f6ef4ca10c14291252dcd16a83` 的导入开始，没有保留上游 Git 历史。因此，上述参考提交不是已确认的原始复制基线，也没有完成全部文件与该版本的逐字比对。

## 初始导入范围

下表根据本地初始提交列出导入路径。上游 Python 包名为 `wechat_cli`，本地改为 `wecli`；对应关系用于追踪来源，不表示文件与参考版本逐字相同。
空的 `__init__.py` 仅为包标记，不声称其具有独立的版权内容。

| 本地路径 | 上游对应路径 |
| --- | --- |
| `wecli/__init__.py` | `wechat_cli/__init__.py` |
| `wecli/bin/find_all_keys_macos.arm64` | `wechat_cli/bin/find_all_keys_macos.arm64` |
| `wecli/bin/find_all_keys_macos.c` | `wechat_cli/bin/find_all_keys_macos.c` |
| `wecli/commands/__init__.py` | `wechat_cli/commands/__init__.py` |
| `wecli/commands/contacts.py` | `wechat_cli/commands/contacts.py` |
| `wecli/commands/export.py` | `wechat_cli/commands/export.py` |
| `wecli/commands/favorites.py` | `wechat_cli/commands/favorites.py` |
| `wecli/commands/history.py` | `wechat_cli/commands/history.py` |
| `wecli/commands/init.py` | `wechat_cli/commands/init.py` |
| `wecli/commands/members.py` | `wechat_cli/commands/members.py` |
| `wecli/commands/new_messages.py` | `wechat_cli/commands/new_messages.py` |
| `wecli/commands/search.py` | `wechat_cli/commands/search.py` |
| `wecli/commands/sessions.py` | `wechat_cli/commands/sessions.py` |
| `wecli/commands/stats.py` | `wechat_cli/commands/stats.py` |
| `wecli/commands/unread.py` | `wechat_cli/commands/unread.py` |
| `wecli/core/__init__.py` | `wechat_cli/core/__init__.py` |
| `wecli/core/config.py` | `wechat_cli/core/config.py` |
| `wecli/core/contacts.py` | `wechat_cli/core/contacts.py` |
| `wecli/core/context.py` | `wechat_cli/core/context.py` |
| `wecli/core/crypto.py` | `wechat_cli/core/crypto.py` |
| `wecli/core/db_cache.py` | `wechat_cli/core/db_cache.py` |
| `wecli/core/key_utils.py` | `wechat_cli/core/key_utils.py` |
| `wecli/core/messages.py` | `wechat_cli/core/messages.py` |
| `wecli/keys/__init__.py` | `wechat_cli/keys/__init__.py` |
| `wecli/keys/common.py` | `wechat_cli/keys/common.py` |
| `wecli/keys/scanner_linux.py` | `wechat_cli/keys/scanner_linux.py` |
| `wecli/keys/scanner_macos.py` | `wechat_cli/keys/scanner_macos.py` |
| `wecli/keys/scanner_windows.py` | `wechat_cli/keys/scanner_windows.py` |
| `wecli/main.py` | `wechat_cli/main.py` |
| `wecli/output/__init__.py` | `wechat_cli/output/__init__.py` |
| `wecli/output/formatter.py` | `wechat_cli/output/formatter.py` |

## 本项目的修改与新增

- 初始代码适配了 `wecli` 包名、命令入口、配置环境变量和用户目录，并有源码格式调整；各文件不一定都涉及这些修改。
- 后续 Linux 初始化修改包括微信进程识别、权限处理，以及通过独立提权进程扫描密钥。`wecli/keys/elevation.py` 为后续新增文件。
- 桌面启动、环境诊断和 AT-SPI 发送相关的 `commands/launch.py`、`commands/doctor.py`、`commands/send.py` 以及 `core/desktop.py`、`core/runtime.py`、`core/atspi_worker.py`、`core/sending.py` 为本地后续新增文件，不标记成从上述上游文件修改。
- `tests/` 下现有测试为本地后续新增；README、开发和运行文档由本项目维护，当前 README 已重新编写。
- 初始导入的非空 Python/C 源文件在文件头记录 Apache-2.0、上游来源及本项目修改事实；这些声明不取代或转移上游权利。细节以本地 Git 差异和后续确认的上游基线为准。
- `pyproject.toml` 沿用上游打包结构并作修改，在本文件集中记录；本项目的 `environment.yml` 使用同样的最低构建后端版本。

## 附带 macOS 二进制

`wecli/bin/find_all_keys_macos.arm64` 与 C 源码一起进入初始提交，目前仍由 `bin/*` 打包规则包含。
此次许可整理不修改或重新构建该二进制。其精确上游版本、构建工具链及与附带 C 源码的一致性尚未独立验证；不能将源码旁存在该文件当作可复现构建证明。
本地文件未发生变化也不代表其构建来源已经核实。后续若继续发布它，应记录可核验的获取来源或在 macOS 上从已知源码重新构建并记录摘要。

## 维护和分发约定

1. 保留相关原始版权、归属及许可声明；新增自己的声明时不得覆盖原始声明。
2. 修改沿用文件时保留文件内的修改提示；新引入其他来源时更新本文件及必要的第三方许可。
3. LICENSE 保存完整 Apache-2.0 正文。NOTICE 是本项目补充的来源说明，不是声称上游提供了同名文件。
4. `pyproject.toml` 使用 SPDX 标识 `Apache-2.0`，并显式将 LICENSE、NOTICE 和本文件列入 `license-files`，使 wheel 和 sdist 都携带这些说明。该配置需要 setuptools >= 77.0.3。
5. 普通 Python/Conda 依赖没有被复制进本仓库；若以后打包成包含依赖的独立可执行文件，需要另行核查并附带所分发依赖的许可。
6. WeCLI 独立维护；来源署名不表示上游或腾讯/微信认可、维护或担保本项目。

## 核验入口

- [Apache License 2.0，第 4 条再分发要求](https://www.apache.org/licenses/LICENSE-2.0#section-4)
- [上游参考版本文件树](https://github.com/huohuoer/wechat-cli/tree/a3789232d4f79bf0b30634d9dadbce71e4acd601)
- [setuptools 的许可证元数据配置](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)
