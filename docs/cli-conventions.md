# CLI conventions

## Language and presentation

Tool-generated help, prompts, errors, type labels, and notices use English.
Contact names, message bodies, and content read from WeChat retain their language.
Chinese accessibility names remain supported for locating the official client's UI.

Commands default to `--format text`. Sessions, unread conversations, and contacts
use compact tables with Unicode-aware widths and truncated cells. History and
search retain message lines; Moments details use indented fields. Empty queries
succeed with a readable explanation. Text is a display format, not a parsing API.
No colors or animation are emitted, so redirected output needs no cleanup.

Use `--format json` explicitly in scripts, including when redirecting or piping.
The selected format never changes based on whether stdout is a terminal.
JSON output is one UTF-8 JSON document followed by a newline, without progress or
log prefixes. Existing object keys and list/object shapes are retained. Synthesized
message types, summaries, and notices now use English; those display strings are
not stable identifiers. Use the documented `--type` values for filtering.
Raw message content is not translated. Internal scanner and AT-SPI worker JSON
protocols remain independent of the public command's presentation format.

`export` uses `--format markdown|txt` and writes the document to stdout unless
`--output PATH` is supplied. `--output -` explicitly selects stdout. File export
confirmation goes to stderr. Failed subqueries produce a warning; if all queried
records fail, export fails rather than reporting an empty successful export.

## Streams and exit codes

Results belong on stdout. Progress, interactive prompts, warnings, and errors
belong on stderr. Diagnostics returned as data by `doctor --format json` or
`send --format json` stay inside their structured result. Query JSON retains its
existing `failures` field for partial failures; text mode warns on stderr.

| Code | Meaning |
| --- | --- |
| 0 | Success, including an empty query or a successful dry run |
| 1 | Operational failure, missing data, or invalid configuration |
| 2 | Invalid arguments, invalid date/cursor syntax, or missing noninteractive consent |
| 3 | Send outcome unknown; inspect chat history before sending again |

A local `recorded` send result does not prove server delivery or recipient receipt.
Sending never retries automatically. Interactive confirmation defaults to no.
Without a terminal, send requires explicit `--yes`; `--dry-run` is exempt.
Multiple auto-detected accounts require an explicit choice; without a terminal,
provide `init --db-dir PATH` or select a configuration.

## Configuration and state

The configuration path is selected by `--config`, then `WECLI_CONFIG`, then
`~/.wecli/config.json`. Global options precede the subcommand. An explicitly
selected missing configuration is an error for data queries. `init` may create it.
Relative paths in configuration are resolved against its directory, and `~` is
expanded. Malformed JSON or invalid field types are reported, never discarded.
`init --db-dir` overrides the saved directory; otherwise init uses the saved value
before auto-detection. Other configuration fields are preserved. Config writes
are atomic and use mode `0600`; new state directories use `0700`.

`new-messages` compares the last timestamp for each conversation in `SessionTable`.
It cannot reconstruct intermediate messages or reliably detect changes sharing a
timestamp. It is not an ingestion API or complete event stream. Its first call
returns unread summaries and saves a snapshot. Per-account snapshots are stored
next to the selected keys file as `last_check_<account-hash>.json`; the account
hash is derived from the canonical database directory. Output is written before
advancing the snapshot; this does not provide transactional downstream delivery
or concurrent polling guarantees. Corrupt snapshots produce an actionable error.
Remove a snapshot to reset. The old shared `last_check.json` is not imported;
upgrading starts a fresh snapshot for each account.

## Help, completion, and maintenance

Every command accepts `-h` and `--help` without loading configuration, keys, or
databases. Numeric ranges and date syntax are validated before data access.
`wecli --version` and `python -m wecli --version` share the package version source.

Click's shell completion is available without additional packages:

```bash
# Bash
eval "$(_WECLI_COMPLETE=bash_source wecli)"
# Zsh
eval "$(_WECLI_COMPLETE=zsh_source wecli)"
# Fish
_WECLI_COMPLETE=fish_source wecli | source
```

The `dev` extra installs Ruff and build tooling. `bash scripts/check.sh` runs lint,
format verification, compilation, and isolated CLI/unit tests. The Linux CI matrix
also builds distributions. Automated checks do not prove live WeChat access,
sudo authorization, AT-SPI behavior, or message delivery.
