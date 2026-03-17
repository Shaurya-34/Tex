# Tex

> A transparent, local, explainable Linux task assistant.

Tex is a CLI tool that interprets your intent in plain English, maps it to safe predefined tools, shows you exactly what it plans to do, asks for confirmation, then executes — and logs everything.

**The LLM never executes commands directly. You are always in control.**

---

> **Status: Active Development**
> Core functionality is stable and usable, but the tool set and feature surface are still expanding.

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
tex ask "show me what's eating memory"
tex ask "is nginx running?"
tex ask "restart postgresql"
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

> **Tip:** Just run `tex` — it drops you into an interactive session where you can mix questions, tasks, and system commands freely without retyping `tex ask` each time.

---

## Architecture

```
User Input
    |
    v
LLM (Ollama, local) — intent classification + tool selection
    |
    v
Validator — schema check, whitelist enforcement, arg length guards
    |
    v
Tool Dispatcher — Python logic only, no raw shell from model
    |
    v
Plan Display — shown to user before anything runs
    |
    v
Confirmation Prompt — user explicitly approves
    |
    v
Execution Layer — subprocess, controlled environment
    |
    v
Logger — full audit trail in logs/tex.log
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
| `list_processes` | Show running processes, optionally filtered | — |
| `kill_process` | Kill a process by PID | destructive |
| `read_journal` | Read systemd journal logs | — |

### System Information
| Tool | Description | Flags |
|---|---|---|
| `get_system_info` | Show CPU, RAM, GPU, disk, and OS info | — |
| `list_installed_packages` | List installed packages (dnf, flatpak, snap, AppImage) | — |

### Service Management
| Tool | Description | Flags |
|---|---|---|
| `service_status` | Show the status of a systemd service | — |
| `start_service` | Start a systemd service | sudo |
| `stop_service` | Stop a running systemd service | sudo, destructive |
| `restart_service` | Restart a systemd service | sudo, destructive |
| `enable_service` | Enable a service to start on boot | sudo |
| `disable_service` | Disable a service from starting on boot | sudo, destructive |
| `list_services` | List services, filtered by name or state | — |

### Education & Conversation
| Tool | Description | Flags |
|---|---|---|
| `explain_command` | Explain a shell command without executing it | — |
| `chat_response` | Conversational reply for questions and general chat | no-confirm |

All tool calls are validated against this whitelist before dispatch. Any tool name not in this list is rejected outright before execution.

---

## Interactive Session

Run `tex` to enter the interactive session. You can mix tasks, questions, and system commands freely in one session without retyping `tex ask` every time.

```
$ tex

 ████████╗███████╗██╗  ██╗
 ╚══██╔══╝██╔════╝╚██╗██╔╝
    ██║   █████╗   ╚███╔╝
    ██║   ██╔══╝   ██╔██╗
    ██║   ███████╗██╔╝ ██╗
    ╚═╝   ╚══════╝╚═╝  ╚═╝

╭─ Interactive mode ────────────────────────────────╮
│ Ask anything or give me a task.                   │
│ Type exit or quit to end the session.             │
╰───────────────────────────────────────────────────╯

you › is nginx running?
you › restart it
you › show me all failed services
you › why would I use zsh over bash?
you › exit
```

- Task input goes through the full LLM → validate → plan → confirm → execute pipeline.
- Conversational input (questions, explanations) streams responses token-by-token immediately.
- Tex keeps up to 10 turns of context within a session.

---

## Safety Rules

1. No raw shell execution from model output. Ever.
2. Only whitelisted tools are allowed — any unknown tool name is rejected before dispatch.
3. Every action is shown to the user in a plan panel before execution.
4. Destructive actions require typing `yes` explicitly — no accidental confirms.
5. No automatic sudo escalation — the user decides if/when to escalate.
6. No background daemon. No always-on process.
7. File operations are constrained to your home directory. System paths are blocked.
8. Service names are validated against a character allowlist before being passed to `systemctl`.
9. Full action log at `logs/tex.log` (excluded from git).
10. Malformed or unexpected LLM output aborts immediately — Tex does not guess.

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

Tex is optimised to keep LLM round-trips as short as possible:

- **Compact tool schema** — tool definitions are serialised as one-liners in the system prompt rather than verbose JSON, saving ~700 prompt tokens per query.
- **Background warmup** — a 1-token ping is sent to Ollama in a daemon thread the moment Tex starts, so model weights are loading while the UI is rendering.
- **`num_ctx` tuned to 2048** — our prompts are short; a smaller context window means a faster KV-cache prefill (the main source of the initial "Thinking..." delay).

If responses are still slow, try a smaller model:
```bash
ollama pull llama3.2:1b
# then set TEX_MODEL=llama3.2:1b in .env
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
      executor.py    — Plan display, confirmation, execution flow
      logger.py      — Action and error logging
      validator.py   — LLM output schema validation and arg guards
    llm/
      client.py      — Ollama client, streaming, history, warmup
      prompts.py     — System prompts for task and chat modes
    tools/
      registry.py    — Tool whitelist, ToolDefinition schema, compact serialiser
      file_ops.py    — File operation implementations
      packages.py    — Package management implementations
      processes.py   — Process inspection and journal tools
      services.py    — Systemd service management tools
      sysinfo.py     — System information tools
  pyproject.toml
  .env.example
  .gitignore
  SECURITY.md
```

---

## Roadmap

- [ ] Two-pass LLM interpretation — tool output passed back to LLM for analysis and explanation
- [ ] Multi-tool chaining — one query can invoke multiple tools in sequence
- [ ] Network tools — `show_network_info`, `ping_host`, `check_port`
- [ ] Boot analysis — `systemd-analyze blame` integration
- [ ] Session persistence — save and restore conversation history across sessions
- [ ] apt / pacman support alongside dnf
- [ ] Plugin system — drop a `.py` in `~/.tex/plugins/` to register custom tools
- [ ] Test suite

---

## Security

See [SECURITY.md](SECURITY.md) for the full security audit, fixed vulnerabilities, and the disclosure policy.

---

## License

MIT
