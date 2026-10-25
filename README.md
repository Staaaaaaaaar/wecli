# WeCLI

A command-line tool for local WeChat data on Linux. Query local chat history, contacts, group members, sessions, and favorites, with conversation statistics and export.

[中文文档](README_CN.md)

## Installation

Development and usage currently target Linux with the native WeChat client and Python 3.10 or later. Install from source in a virtual environment:

```bash
git clone https://github.com/Staaaaaaaaar/wecli.git
cd wecli
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
wecli --help
```

If using Conda, activate your existing environment instead of creating `.venv`. After updating the source, rerun `python -m pip install -e .` to refresh the command entry point.

## Quick start

### 1. Initialize

Start WeChat and log in. With your Python environment activated on Linux:

```bash
sudo env HOME="$HOME" "$(python -c 'import sys; print(sys.executable)')" -m wecli.main init
sudo chown -R "$(id -u):$(id -g)" "$HOME/.wecli"
```

The sudo password prompt does not echo characters. Enter your system login password and press Enter. Using the active environment's absolute Python path avoids command lookup issues with Conda and virtual environments.

Initialization detects the data directory and extracts keys. Select the currently logged-in account when multiple accounts are found. To specify a data directory:

```bash
sudo env HOME="$HOME" "$(python -c 'import sys; print(sys.executable)')" -m wecli.main init --db-dir /path/to/db_storage
sudo chown -R "$(id -u):$(id -g)" "$HOME/.wecli"
```

### 2. Query data

After initialization, routine queries do not require sudo:

```bash
wecli sessions --limit 10
wecli history "Alice" --limit 20
wecli search "deadline" --chat "Team"
wecli contacts --query "Alice"
```

Query commands return JSON by default; use `--format text` for plain text. `export` supports Markdown and plain text. Run `wecli <command> --help` for options.

## Usage

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
wecli members "Team Group"            # All members (JSON)
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

### `new-messages` — Incremental New Messages

```bash
wecli new-messages                    # First: return unread + save state
wecli new-messages                    # Subsequent: only new since last call
```

State saved at `~/.wecli/last_check.json`. Delete to reset.

---

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

Configuration, keys, and incremental query state are stored in `~/.wecli/`. To use another configuration file:

```bash
wecli --config /path/to/config.json sessions
```

Alternatively, set `WECLI_CONFIG`. The internal Python module is named `wecli`.

## Linux notes

Initialization reads `/proc/<pid>/mem` and normally requires sudo. Keep the native Linux WeChat client running and logged in. Run installation and routine queries as your normal user.

Data directories are detected under `~/Documents/xwechat_files/*/db_storage` and `~/.local/share/weixin/data/db_storage`. Use `--db-dir` when your data is stored elsewhere.

If initialization reports no WeChat process, confirm that the client is running. If several accounts are detected, select the active account. After initialization, restore ownership of `~/.wecli/` using the command above so normal queries can update their state.

## Development and releases

See [development and release instructions](docs/development.md) for the repository layout, local checks, and package builds.
