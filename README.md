# WeCLI

A CLI for native WeChat on Linux: query local history, contacts, groups, sessions and favorites, export conversations, and send text through the desktop client.

Current version: **0.1.1**. See the [changelog](CHANGELOG.md) for scope and known limitations, including local Moments browsing.

[中文文档](README_CN.md)

## Installation

Only Linux with the native WeChat client is supported. Use the dedicated Conda environment:

```bash
git clone https://github.com/Staaaaaaaaar/wecli.git
cd wecli
conda env create -f environment.yml
conda activate wecli
wecli --help
```

The dedicated environment includes Python, AT-SPI, GTK and xdotool. No extra apt
installation is needed for these libraries. To update an existing environment,
run `conda env update -n wecli -f environment.yml` from the repository root.
After updating the source, run `python -m pip install --no-deps -e .` to refresh the CLI entry point.
Conda manages runtime dependencies; pip installs the project last. See
[desktop runtime](docs/desktop-runtime.md) for setup and verification.

## Quick start

### 1. Initialize

Run `wecli launch`, log in yourself in the WeChat window, then initialize from the activated environment:

```bash
wecli init
```

The command automatically requests sudo authorization when needed to read process memory. The password prompt does not echo characters; enter your system login password and press Enter. Scanning uses the current Python environment, while your normal user saves configuration and keys. No additional `chown` command is needed.

Initialization detects the data directory and extracts keys. Select the currently logged-in account when multiple accounts are found. To specify a data directory:

```bash
wecli init --db-dir /path/to/db_storage
```

### 2. Query data

After initialization, routine queries do not require sudo:

```bash
wecli sessions --limit 10
wecli history "Alice" --limit 20
wecli search "deadline" --chat "Team"
wecli contacts --query "Alice"
```

Commands return readable text by default; use `--format json` for machine-readable output. `export` supports Markdown and plain text. Run `wecli <command> --help` for options.

## Usage

### `send` — Send text (Linux X11)

```bash
wecli launch                         # Launch only; complete login yourself
wecli doctor
wecli send filehelper "Hello" --dry-run
wecli send filehelper "Hello"        # Confirm once, then send
wecli send "Unique remark" --file message.txt --yes
```

AT-SPI identifies the chat and verifies the draft before sending. One X11 monitor
with integer scaling is supported. Ambiguous names and existing drafts stop the
operation; uncertain sends are never retried automatically. `recorded` confirms
a local record, not delivery. See [sending details](docs/sending.md) and
[desktop runtime](docs/desktop-runtime.md) (Chinese).

Unlock the desktop and keep WeChat visible before sending. `doctor` currently
does not detect a locked screen and may report `ready` while sending cannot work.
Real sending has been verified only with File Transfer on WeChat 4.1.1.4;
ordinary friends, groups, and other client versions remain unverified.

### `sessions` — Recent Chats

```bash
wecli sessions                        # Last 20 sessions
wecli sessions --limit 10             # Last 10
wecli sessions --format text          # Human-readable
```

### `history` — Chat Messages

```bash
wecli history "Alice"                 # Last 50 messages
wecli history "Alice" --limit 100 --offset 50
wecli history "Team" --start-time "2026-04-01" --end-time "2026-04-03"
wecli history "Alice" --type link     # Only links
wecli history "Alice" --format text
```

**Options:** `--limit`, `--offset`, `--start-time`, `--end-time`, `--type`, `--format`

### `search` — Search Messages

```bash
wecli search "hello"                  # Global search
wecli search "hello" --chat "Alice"   # In specific chat
wecli search "meeting" --chat "TeamA" --chat "TeamB"  # Multiple chats
wecli search "report" --type file     # Only files
```

**Options:** `--chat` (repeatable), `--start-time`, `--end-time`, `--limit`, `--offset`, `--type`, `--format`

### `contacts` — Contact Search & Details

```bash
wecli contacts --query "Li"           # Search contacts
wecli contacts --detail "Alice"       # Contact details
wecli contacts --detail "wxid_xxx"    # By WeChat ID
```

Returns: nickname, remark, WeChat ID, bio, avatar URL, account type.

### `members` — Group Members

```bash
wecli members "Team Group"            # All members (readable text)
wecli members "Team Group" --format text
```

### `stats` — Chat Statistics

```bash
wecli stats "Team Group"
wecli stats "Alice" --start-time "2026-04-01" --end-time "2026-04-03"
wecli stats "Team Group" --format text
```

Returns: total messages, type breakdown, top 10 senders, 24-hour activity distribution.

### `export` — Export Conversations

```bash
wecli export "Alice" --format markdown              # To stdout
wecli export "Alice" --format txt --output chat.txt  # To file
wecli export "Team" --start-time "2026-04-01" --limit 1000
```

**Options:** `--format markdown|txt`, `--output`, `--start-time`, `--end-time`, `--limit`

### `moments` — Local Moments

```bash
wecli moments list --limit 20
wecli moments list --user "Alice" --since 2026-01-01 --until 2026-10-27
wecli moments search "travel"
wecli moments show <id>
wecli moments list --before <next_cursor> --limit 20
```

`list` and `search` return newest posts first. Both accept `--user`, `--since`,
`--until`, `--limit` (1–1000), and `--before`. Authors match exact WeChat IDs,
nicknames, or remarks; use an ID to disambiguate duplicate names. Dates use the
local timezone; an end date includes the entire day. Keep filters unchanged
when passing `next_cursor` to `--before`; the final page returns `null`.

Search matches literal text in post bodies, ignoring case. `show` includes
location, media URLs and parameters, and cached likes/comments. Use the string
ID returned by the list. All three commands default to readable text and support
`--format json`.

Only local cached data is read. History, interactions, and the latest WAL changes
may be incomplete; no posts or media are downloaded. JSON includes `source` and
`notice`. Lists report malformed records through `parse_failures`; posts without
a usable timestamp are omitted and can be inspected by ID with `show`.

### `favorites` — WeChat Bookmarks

```bash
wecli favorites                       # Recent bookmarks
wecli favorites --type article        # Articles only
wecli favorites --query "machine learning"  # Search
```

**Types:** text, image, article, card, video

### `unread` — Unread Sessions

```bash
wecli unread                          # All unread sessions
wecli unread --limit 10 --format text
```

### `new-messages` — Individual incremental messages

```bash
wecli new-messages --limit 100
wecli new-messages --cursor "$CURSOR" --limit 100
```

Read individual rows with stable IDs and an account-bound cursor. Persist `next_cursor` after processing; replay deduplicates by `message_id`. See [service integration](docs/service-integration.md).

---

## CLI conventions

All tool-generated help, labels, prompts, and diagnostics are English. User names
and message content retain their original language. Most commands default to text;
`new-messages` defaults to JSON. Scripts should explicitly select their format.
The message API changes are documented in [service integration](docs/service-integration.md).

Results go to stdout; progress, prompts, and diagnostics go to stderr. `export`
keeps its `markdown|txt` formats and accepts `--output -` for stdout. Use `-h` or
`--help` at any command level without initializing WeChat data.

Exit codes: `0` success (including empty results), `1` operational failure,
`2` invalid usage, `3` an uncertain send outcome. Sending without a terminal
requires `--yes`; `--dry-run` never operates the desktop.

Configuration precedence is `--config` > `WECLI_CONFIG` > `~/.wecli/config.json`.
This also applies to `init`. Invalid configuration and ambiguous account detection
produce errors; noninteractive commands never silently select an account.

Shell completion (run with the environment active):

```bash
# Bash
eval "$(_WECLI_COMPLETE=bash_source wecli)"
# Zsh
eval "$(_WECLI_COMPLETE=zsh_source wecli)"
# Fish
_WECLI_COMPLETE=fish_source wecli | source
```

See [CLI contracts](docs/cli-conventions.md) for output and compatibility details.

## Message types

The `--type` option (on `history` and `search`):

| Value | Description |
|-------|-------------|
| `text` | Text messages |
| `image` | Images |
| `voice` | Voice messages |
| `video` | Videos |
| `sticker` | Stickers/emojis |
| `location` | Location shares |
| `link` | Links and app messages |
| `file` | File attachments |
| `call` | Voice/video calls |
| `system` | System messages |

---

## Configuration

Configuration, keys, and conversation snapshot state are stored in `~/.wecli/`. To use another configuration file:

```bash
wecli --config /path/to/config.json sessions
```

Alternatively, set `WECLI_CONFIG`. The internal Python module is named `wecli`.

## Linux notes

Initialization reads `/proc/<pid>/mem` and normally requires sudo. Keep the native Linux WeChat client running and logged in. Run installation, initialization, and routine queries as your normal user; initialization automatically requests sudo authorization only for key scanning.

Data directories are detected under `~/Documents/xwechat_files/*/db_storage` and `~/.local/share/weixin/data/db_storage`. Use `--db-dir` when your data is stored elsewhere.

If initialization reports no WeChat process, confirm that the client is running. If several accounts are detected, select the active account. An existing initialization returns immediately; use `wecli init --force` to scan again.

If an older sudo initialization left root-owned files, repair ownership once:

```bash
sudo chown -R "$(id -u):$(id -g)" "$HOME/.wecli"
```

## Development and releases

See [development and release instructions](docs/development.md) for the repository layout, local checks, and package builds.

## License and provenance

WeCLI is licensed under [Apache-2.0](LICENSE) and includes code derived from
[wechat-cli](https://github.com/huohuoer/wechat-cli). It is independently
maintained. See [NOTICE](NOTICE) for attribution and
[source provenance](docs/provenance.md) for inherited files, modifications,
and the limitations of the recorded upstream revision and bundled binary.
