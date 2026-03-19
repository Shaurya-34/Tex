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
   a belt-and-suspenders second check. **The blocklist is still active** — what
   changed in a subsequent fix (CodeRabbit review) was the *matching method*:
   the original `str.startswith()` string comparison was replaced with
   `Path.is_relative_to()` for correct path containment semantics. Additionally,
   the check is now skipped when `_HOME` itself lives inside a blocked prefix
   (e.g. Fedora Silverblue users with homes under `/var/home`) since Rule 1
   already handles containment in those environments.

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
 
 ## Vulnerability 5 — Potential Command Injection via Unvalidated Hostnames
 
 **File:** `tex/tools/network.py`
 **Severity:** High
 **Status:** Fixed
 
 ### What the vulnerability was
 
 The `ping_host` and `check_port` tools accepted a `host` argument from the LLM and 
 passed it to `subprocess.run(["ping", "-c", "1", host])` or `socket.gethostbyname(host)`. 
 Although a basic separator check (semicolons, pipes) was present in the validator, 
 it wasn't consistently applied to all network entry points, potentially allowing 
 shell meta-characters to be passed if the model bypasses the initial guard.
 
 ### Fix applied
 
 A centralized `_validate_host()` gate was added to all network tools. It enforces 
 a strict character whitelist (alphanumeric, dots, hyphens) and rejects any 
 hostname containing shell-sensitive characters like `;`, `&`, `|`, `` ` ``, `$`, 
 or spaces. Hostnames are also capped at 253 characters (DNS limit).
 
 ---
 
 ## Vulnerability 6 — Potential Command Injection via Unvalidated Service Names
 
 **File:** `tex/tools/services.py`
 **Severity:** High
 **Status:** Fixed
 
 ### What the vulnerability was
 
 All six mutating service tools (`start`, `stop`, `restart`, `enable`, `disable`, 
 `status`) passed the `name` argument directly to `systemctl`. While service 
 names are usually predictable strings, a malicious model could output a service 
 name containing a shell injection: `nginx; rm -rf /`.
 
 ### Fix applied
 
 A `_validate_service_name()` gate was added to all service management functions. 
 It restricts service names to common valid characters (`a-zA-Z0-0`, `-`, `.`, `@`) 
 and rejects any shell meta-characters. 
 
 ---
 
 ## Vulnerability 7 — Logic Bypass via Leading/Trailing Whitespace
 
 **File:** `tex/tools/network.py`, `tex/tools/services.py`
 **Severity:** Medium
 **Status:** Fixed
 
 ### What the vulnerability was
 
 Validators for hostnames and service names were checking the input string 
 but not returning the cleaned value. If a model provided `" nginx"`, 
 the validator might pass it (depending on regex strictness), but the 
 literal string `" nginx"` would then be passed to `subprocess.run()`. 
 In some shell environments or CLI tools, leading whitespace can be used 
 to bypass certain filters or logging.
 
 ### Fix applied
 
 `.strip()` was added to the beginning of all public functions in `network.py` 
 and `services.py`. The input is cleaned before being passed to both 
 the validator and the implementation.
 
 ---
 
 ## Vulnerability 8 — File Handle Leak in `resolv.conf`
 
 **File:** `tex/tools/network.py`
 **Severity:** Low (Resource exhaustion)
 **Status:** Fixed
 
 ### What the vulnerability was
 
 `show_network_info` was reading `/etc/resolv.conf` using `open(path).read()`. 
 If the read failed (e.g. Permission Error), the file handle could remain 
 open until the process terminated.
 
 ### Fix applied
 
 Replaced with a `with open(...) as f:` context manager to ensure the 
 handle is closed immediately regardless of errors.
 
 ---
 
 ## Vulnerability 9 — Information Disclosure via Incorrect Package Header Filtering
 
 **File:** `tex/tools/sysinfo.py`
 **Severity:** Low (Usability/Data loss)
 **Status:** Fixed
 
 ### What the vulnerability was
 
 `list_installed_packages` used broad string matching (`startswith("Installed")`) 
 to strip package manager headers. This would accidentally filter out 
 actual packages starting with those words (e.g. a Python package named "InstalledStuff").
 
 ### Fix applied
 
 The header detection was moved to token-based exact matches for the specific 
 header lines, ensuring that only metadata is stripped and actual package 
 information is preserved.
 
 ---
 
 ## Summary Table (Updated)
 
 | # | File | Vulnerability | Fix |
 |---|---|---|---|
 | 1a | `file_ops.py` | Path traversal, no boundary check | `_safe_path()` enforces home directory containment |
 | 1b | `file_ops.py` | `rmtree` on top-level home dirs | Depth-of-2 minimum before directory deletion |
 | 1c | `file_ops.py` | Unbounded `read_file` line count | Capped at 500 lines |
 | 1d | `file_ops.py` | `startswith()` string matching for paths | Replaced with `Path.is_relative_to()` |
 | 2a | `processes.py` | No PID lower bound, could kill PID 1 | Reject PIDs in system range 1–99 |
 | 3 | `dispatcher.py` | No default case, returns `None` on miss | `case _:` returns safe error tuple |
 | 4 | `validator.py` | Hardcoded flat 1024-char cap | Configurable via `TEX_MAX_ARG_LEN` |
 | 5 | `network.py` | Unvalidated hostname injection | `_validate_host()` whitelist gate |
 | 6 | `services.py` | Unvalidated service name injection | `_validate_service_name()` whitelist gate |
 | 7 | `various` | Whitespace-based filter bypass | Mandatory `.strip()` on user inputs |
 | 8 | `network.py` | File handle leak | Mandatory context managers (`with open`) |
 | 9 | `sysinfo.py` | Data loss in package filtering | Token-exact header matching |
 
 ---
 
 ## What was NOT changed
 
 - The tool whitelist itself (`registry.py`) was not modified — it remains correct.
 - The core execution confirmation flow is unchanged.
 - The logger is still active and logging all actions to `/logs/tex.log`.
