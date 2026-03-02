# Tex Security Audit — February 2026

This document describes every vulnerability found in the Tex codebase and the
exact fix applied for each one. It is intended for third-party review.

---

## Reporting a Vulnerability

If you find a security issue in Tex, please open a GitHub issue marked 
**[SECURITY]** or contact me directly before disclosing publicly.
Since Tex is a local-only tool with no network exposure or user data, 
most issues will be addressed quickly.

---



## Vulnerability 1 — Path Traversal in File Operations

**File:** `tex/tools/file_ops.py`
**Severity:** Critical
**Status:** Fixed

### What the vulnerability was

All file operation tools (`list_files`, `read_file`, `copy_file`, `move_file`,
`delete_file`) accepted path arguments directly from LLM JSON output with no
validation. Because Tex runs as the user, the LLM could output:

```json
{"tool": "read_file", "arguments": {"path": "/etc/shadow"}}
{"tool": "delete_file", "arguments": {"path": "/"}}
{"tool": "copy_file", "arguments": {"source": "/etc/sudoers", "destination": "~/exfil"}}
```

And those paths would be used directly. `Path.expanduser()` was called but no
boundary check existed.

### Fix applied

A `_safe_path()` function was added as a mandatory gate before every filesystem
operation. It enforces three rules:

1. The **resolved** (absolute, symlink-expanded) path must exist inside the
   user's home directory (`Path.home().resolve()`). Anything outside is
   rejected.
2. The path must not **be** the home directory itself — preventing operations
   on `~` directly.
3. A hardcoded blocklist of system prefixes (`/etc`, `/usr`, `/bin`, `/proc`,
   `/sys`, `/dev`, `/boot`, `/root`, `/var`, `/run`, `/snap`, `/opt`) provides
   a belt-and-suspenders second check.

Path traversal strings like `../../etc/passwd` are neutralised because
`Path.resolve()` is called before the containment check, producing the real
absolute path first.

### Additional fix: `delete_file` directory depth guard

`delete_file` previously used `shutil.rmtree()` on any directory, including
top-level home subdirectories like `~/Documents`. A depth check was added:
the path must be at least 2 levels deep within the home directory (e.g.
`~/Documents/old_project`) before `rmtree` is permitted. Top-level home
directories are rejected with a clear message telling the user to do it
manually.

### Additional fix: `read_file` line count cap

The `lines` argument is now capped at 500 regardless of what the LLM outputs.
This prevents memory exhaustion from reading a very large file with no limit.

---

## Vulnerability 2 — No PID Range Guard on `kill_process`

**File:** `tex/tools/processes.py`
**Severity:** High
**Status:** Fixed

### What the vulnerability was

`kill_process` accepted any integer PID and sent `SIGTERM` to it. PID 1 is
`systemd`. Killing systemd terminates the entire system immediately. Kernel
threads and other critical daemons occupy PIDs in the low range. A misbehaving
LLM could output:

```json
{"tool": "kill_process", "arguments": {"pid": 1}}
```

And Tex would forward the signal.

### Fix applied

Two separate guards were added:

1. **PID 0 and negative PIDs** — rejected first with a specific message explaining
   their OS semantics. Negative PIDs in `os.kill()` send signals to an entire
   process group; PID 0 signals all processes in the calling process group.
   Both are more dangerous than a simple invalid-PID and warrant a distinct message.

2. **PIDs 1–99** — rejected as the reserved kernel/system daemon range.
   `_MIN_SAFE_PID = 100` is the enforced lower bound. `systemd` is PID 1;
   kernel threads occupy the low range. User processes always have PIDs well above
   this threshold on a modern Linux system.

---

## Vulnerability 3 — No Fallthrough Case in Dispatcher

**File:** `tex/core/dispatcher.py`
**Severity:** Medium
**Status:** Fixed

### What the vulnerability was

The `match name:` block in `dispatch()` had no `case _:` default. If a tool
name somehow reached the dispatcher without matching any case (e.g. due to a
gap between the validator's registry and the dispatcher's handled cases), the
function would return `None` implicitly. The executor tries to unpack the return
value as `(bool, str)`, so this would crash with a `TypeError` that exposes an
internal traceback to the user.

More critically: a future code change could add a tool to the registry but
forget to add its case to the dispatcher. The silent `None` return made this
class of bug invisible.

### Fix applied

A `case _:` default was added that returns `(False, <security message>)`.
The message explicitly states this is a code bug, not a user error, making it
easy to identify during development if the registry and dispatcher ever diverge.

---

## Vulnerability 4 — No Argument Value Length Limit

**File:** `tex/core/validator.py`
**Severity:** Low–Medium
**Status:** Fixed

### What the vulnerability was

The validator checked argument names and types but not value lengths. A
compromised or confused model could output:

- An extremely long path string (millions of characters) that gets passed to
  `Path()` and causes memory pressure
- A long `message` value in `chat_response` that bloats terminal rendering
- Any string-typed argument with an embedded payload relying on length to
  bypass pattern-matching defences

### Fix applied

Step 4 of the validator was updated with three improvements:

**Configurable base limit.** The constant is now read from `config.max_arg_value_len`,
which is set by `TEX_MAX_ARG_LEN` in `.env` (default: 1024). Users who run models
that produce longer structured outputs can raise this without touching source code.

**Per-argument-type overrides.** A flat 1024-character cap would reject legitimate
chat responses — a detailed explanation of a Linux concept can easily exceed that.
Arguments in `_LONG_CONTENT_ARGS` (`message`, `explanation`) receive a 16x higher
limit (16 384 characters by default). These keys hold free-form natural language,
not structured data like paths or PIDs where strict limits make sense.

**Explicit string conversion.** `str(value)` is called explicitly before measuring
length so that non-string types (integers, booleans, lists) are consistently measured.
Previously this was implicit and could behave differently for non-string values.

**To override the limit:** Add `TEX_MAX_ARG_LEN=<value>` to your `.env` file.
The long-content multiplier (`_LONG_CONTENT_MULTIPLIER = 16`) can be adjusted
directly in `validator.py` if needed.


---

## Summary Table

| # | File | Vulnerability | Fix |
|---|---|---|---|
| 1a | `file_ops.py` | Path traversal, no boundary check | `_safe_path()` enforces home directory containment via `Path.is_relative_to()` |
| 1b | `file_ops.py` | `rmtree` on top-level home dirs | Depth-of-2 minimum before directory deletion |
| 1c | `file_ops.py` | Unbounded `read_file` line count | Capped at 500 lines |
| 1d | `file_ops.py` | `startswith()` string matching for blocked prefixes | Replaced with `Path.is_relative_to()`; non-standard homes skip the check |
| 2a | `processes.py` | No PID lower bound, could kill PID 1 | Reject PIDs in system range 1–99 |
| 2b | `processes.py` | PID 0 and negatives had misleading error message | Separate guard with OS-semantics explanation |
| 3 | `dispatcher.py` | No default case, returns `None` on miss | `case _:` returns safe error tuple |
| 4 | `validator.py` | Hardcoded flat 1024-char cap broke chat responses | Configurable via `TEX_MAX_ARG_LEN`; content args get 16x base limit |

---

## What was NOT changed

- The tool whitelist itself (`registry.py`) was not modified — it is already
  the primary line of defence and was correct.
- The LLM client (`client.py`) was not modified — it handles transport only.
- The executor (`executor.py`) was not modified — confirmation flow is correct.
- No tool implementations were removed or restricted beyond what is documented
  above.
