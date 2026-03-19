# Tex

> A transparent, local, explainable Linux task assistant.

Tex is a CLI tool that interprets your intent in plain English, maps it to safe predefined tools, shows you exactly what it plans to do, asks for confirmation, then executes — and logs everything.

**The LLM never executes commands directly. You are always in control.**

---

> **Status: Active Development**
> Core functionality is stable and usable. The tool set and feature surface are still expanding.

---

## Screenshots

![Tex help screen](assets/tex-help.png)
![Chat mode](assets/tex-chat.png)
![Task execution](assets/tex-ask.png)

---

## Philosophy

- **Local-first.** No cloud. Runs entirely on your machine via [Ollama](https://ollama.com).
- **Explicit over automatic.** Tex always shows what it is going to do before doing it.
- **Explain before execute.** You understand what is happening, always.
- **Education is a feature.** Tex teaches while it works.
- **User stays in control.** No background daemons. No silent actions. No raw shell from model output.

---

## Quickstart

### 1. Install Ollama and pull a model

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2
```

### 2. Install Tex

```bash
git clone https://github.com/Shaurya-34/Tex.git
cd Tex
pip install -e .
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env to set your preferred Ollama model and options
```

### 4. Use it

```bash
tex                              # launch interactive session (recommended)
tex ask "install zsh"            # one-shot task
tex ask "is nginx running?"
tex ask "why is my boot slow?"
tex ask "show my network info"
tex explain "journalctl -xe"
tex tools                        # list all available tools
tex history                      # view the action log
```

---

## CLI Commands

| Command | Description |
|---|---|
| `tex` | Launch the interactive session (main daily-driver interface) |
| `tex ask "<task>"` | One-shot: ask Tex to perform a task and exit |
| `tex ask "<task>" --dry-run` | Show the plan without executing anything |
| `tex ask "<task>" --yes` | Skip the confirmation prompt |
| `tex explain "<command>"` | Explain what a shell command does (no execution) |
| `tex tools` | List all available tools with flags and descriptions |
| `tex history` | View the action log |
| `tex version` | Show the current Tex version |
| `tex --help` | Show all subcommands |

> **Tip:** Just run `tex` — it drops you into an interactive session where you can mix questions, tasks, and system commands freely across multiple turns.

---

## Architecture

```
User Input
    │
    ▼
LLM (Ollama, local) — intent classification + tool selection  [Pass 1]
    │
    ▼
Validator — schema check, whitelist enforcement, arg length guards
    │
    ▼
Tool Dispatcher — Python logic only, no raw shell from model
    │
    ▼
Plan Display — shown to user before anything runs
    │
    ▼
Confirmation Prompt — user explicitly approves
    │
    ▼
Execution Layer — subprocess, controlled environment
    │
    ▼
LLM (same model) — interprets output, answers the question  [Pass 2]
    │
    ▼
Logger — full audit trail in logs/tex.log
```

### Two-pass interpretation

Diagnostic tools (service status, process list, journal logs, system info, boot analysis,
network info) automatically trigger a second LLM call after the raw output is shown.
The second call interprets the data in the context of what the user actually asked:

```
you › why is my boot slow?

╭─ Output ─────────────────────────────────────────────────╮
│ Startup finished in 3.012s (kernel) + 28.431s (userspace) │
│ NetworkManager-wait-online.service  14.203s               │
│ udisks2.service                      3.891s               │
│ ...                                                       │
╰───────────────────────────────────────────────────────────╯

╭─ Tex says ────────────────────────────────────────────────╮
│ The main bottleneck is NetworkManager-wait-online at      │
│ 14.2s — it waits for a full internet connection before    │
│ boot can continue. You can safely disable it:             │
│   systemctl disable NetworkManager-wait-online            │
╰───────────────────────────────────────────────────────────╯
```

### Multi-turn context

Tex keeps up to 10 turns of conversation history within a session.
Tool results are injected into history so follow-up references resolve correctly:

```
you › is nginx running?          → service_status nginx
you › restart it                 → resolves "it" = nginx automatically
you › show me its logs           → resolves "its" = nginx.service
```

---

## Available Tools

### Package Management
| Tool | Description | Flags |
|---|---|---|
| `install_package` | Install a package via dnf | sudo |
| `remove_package` | Remove a package via dnf | sudo, destructive |
| `search_package` | Search for packages matching a keyword | — |

### File Operations
| Tool | Description | Flags |
|---|---|---|
| `list_files` | List files in a directory | — |
| `read_file` | Read a file's contents | — |
| `copy_file` | Copy a file from source to destination | — |
| `move_file` | Move or rename a file | destructive |
| `delete_file` | Delete a file permanently | destructive |

### Process Management
| Tool | Description | Flags |
|---|---|---|
| `list_processes` | Show running processes, optionally filtered | interpretable |
| `kill_process` | Kill a process by PID | destructive |
| `read_journal` | Read systemd journal logs | interpretable |

### System Information
| Tool | Description | Flags |
|---|---|---|
| `get_system_info` | Show CPU, RAM, GPU, disk, and OS info | interpretable |
| `list_installed_packages` | List installed packages (dnf + flatpak + snap + AppImage) | interpretable |

### Service Management
| Tool | Description | Flags |
|---|---|---|
| `service_status` | Show the status of a systemd service | interpretable |
| `start_service` | Start a systemd service | sudo |
| `stop_service` | Stop a running systemd service | sudo, destructive |
| `restart_service` | Restart a systemd service | sudo, destructive |
| `enable_service` | Enable a service to start on boot | sudo |
| `disable_service` | Disable a service from starting on boot | sudo, destructive |
| `list_services` | List services, filtered by name or state | interpretable |
| `analyze_boot` | Show boot time breakdown and slowest services (systemd-analyze) | interpretable |

### Network
| Tool | Description | Flags |
|---|---|---|
| `show_network_info` | Show interfaces, IPs, routes, DNS, listening ports | interpretable |
| `ping_host` | Ping a hostname or IP address | — |
| `check_port` | Check if a TCP port is open on a host | — |

### Education & Conversation
| Tool | Description | Flags |
|---|---|---|
| `explain_command` | Explain a shell command without executing it | — |
| `chat_response` | Conversational reply for questions and general chat | no-confirm |

**Interpretable** tools trigger a second LLM pass that analyses the raw output and directly answers the user's question.

All tool calls are validated against this whitelist before dispatch. Any tool name not in this list is rejected outright.

---

## Interactive Session

Run `tex` to enter the interactive session. Mix tasks, questions, and diagnostics freely.

```
$ tex

╭─ Interactive mode ─────────────────────────────────────────╮
│ Ask anything or give me a task.                            │
│ Type exit or quit to end the session.                      │
╰────────────────────────────────────────────────────────────╯

you › something is eating my memory, what is it?
you › can I run a local LLM alongside this?
you › kill the biggest offender
you › is port 11434 open on localhost?
you › why was my boot slow this morning?
you › exit
```

---

## Test Suite

*   **Security Guards**: Validates all paths, PIDs, and hostnames before execution.
*   **Comprehensive Test Suite**: 120+ unit tests covering security, validation, and tool logic.

## Getting Started

## Safety Rules

1. No raw shell execution from model output. Ever.
2. Only whitelisted tools are allowed — any unknown tool name is rejected before dispatch.
3. Every action is shown to the user in a plan panel before execution.
4. Destructive actions require typing `yes` explicitly — no accidental confirms.
5. No automatic sudo escalation — the user decides if/when to escalate.
6. No background daemon. No always-on process.
7. File operations are constrained to your home directory. System paths are blocked.
8. Service names are validated against a character allowlist before being passed to `systemctl`.
9. Network hostnames are validated against a character allowlist before any subprocess call.
10. PIDs below 100 (system/kernel range) are blocked from kill signals.
11. Full action log at `logs/tex.log` (excluded from git).
12. Malformed or unexpected LLM output aborts immediately — Tex does not guess.

---

## Configuration

Copy `.env.example` to `.env` and adjust as needed:

```bash
# Ollama model to use
TEX_MODEL=llama3.2

# LLM sampling temperature — keep low for structured tool output
TEX_TEMPERATURE=0.1

# Max tokens to generate per response (JSON tool calls are ~80 tokens)
TEX_MAX_TOKENS=256

# Context window size — smaller is faster
TEX_NUM_CTX=2048

# Require confirmation before execution (set false to skip for all actions)
TEX_CONFIRM=true

# Max character length for a single argument value
TEX_MAX_ARG_LEN=1024
```

---

## Performance Notes

Tex is optimised to keep LLM round-trips fast:

- **Compact tool schema** — tool definitions are serialised as one-liners in the system prompt, saving ~700 prompt tokens per query vs verbose JSON.
- **Background warmup** — a 1-token ping is sent to Ollama in a daemon thread the moment Tex starts, so model weights are loading while the banner renders.
- **`num_ctx` tuned to 2048** — our prompts are short; a smaller context window means faster KV-cache prefill (the main source of the initial "Thinking..." delay).
- **Transient streaming** — the live streaming panel uses `transient=True` so intermediate renders are cleared before printing the final response, eliminating ghost-panel duplicates when scrolling.

If responses are still slow, try a smaller model:
```bash
ollama pull llama3.2:1b
# TEX_MODEL=llama3.2:1b in .env
```

---

## Stack

- **Python 3.10+**
- **Typer** — CLI framework
- **Rich** — terminal UI, panels, tables, live streaming
- **Pydantic** — tool call schema validation
- **Ollama** — local LLM inference
- **Loguru** — structured action logging
- **python-dotenv** — local configuration

---

## Project Structure

```
tex/
  tex/
    main.py          — CLI entry point, all command definitions
    config.py        — Configuration loaded from .env
    core/
      dispatcher.py  — Routes validated tool calls to implementations
      executor.py    — Plan display, confirmation, execution, interpretation trigger
      logger.py      — Action and error logging
      validator.py   — LLM output schema validation and arg guards
    llm/
      client.py      — Ollama client, streaming, history, warmup, inject_tool_result
      prompts.py     — System prompts for task, chat, and interpretation passes
    tools/
      registry.py    — Tool whitelist, ToolDefinition schema, compact serialiser
      file_ops.py    — File operation implementations
      packages.py    — Package management implementations
      processes.py   — Process inspection and journal tools
      services.py    — Systemd service management + analyze_boot
      sysinfo.py     — System information tools
      network.py     — Network diagnostic tools
  pyproject.toml
  .env.example
  .gitignore
  SECURITY.md
```

---

## Roadmap

- [x] Two-pass LLM interpretation — raw output + LLM analysis in every diagnostic query
- [x] Multi-turn context — tool results injected into history for follow-up references
- [x] Network tools — `show_network_info`, `ping_host`, `check_port`
- [x] Boot analysis — `analyze_boot` via systemd-analyze
- [x] Replaced keyword routing heuristic — LLM now decides all routing
- [ ] **Test suite** — unit tests for validator, dispatcher, and tool implementations
- [ ] **Multi-tool chaining** — one query invoking multiple tools in sequence
- [ ] **Session persistence** — save and restore conversation history across sessions
- [ ] apt / pacman support alongside dnf
- [ ] Plugin system — drop a `.py` in `~/.tex/plugins/` to register custom tools

---

## Security

See [SECURITY.md](SECURITY.md) for the full security audit, fixed vulnerabilities, and the disclosure policy.

---

## License

MIT
