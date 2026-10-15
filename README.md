# HPC MCP

**New user? Start here:** If you already have Remote Desktop Commander (RDC) connected to your Linux account, follow the **[RDC-assisted setup guide](docs/assisted_setup.md)**. ChatGPT can help inspect the cluster, install HPC MCP, and run tests through RDC. You must configure private Platform/Tunnel credentials yourself. Once HPC MCP works in a new ChatGPT conversation, RDC can be disabled.

**Without RDC:** follow the **[manual ChatGPT + Secure MCP Tunnel setup](docs/tunnel_setup.md)** and then the [user-level service guide](docs/service_backends.md).

A per-user [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for Linux HPC clusters, designed to work with an outbound OpenAI Secure MCP Tunnel. The server runs under an ordinary Linux account; it **does not require root privileges or inbound firewall ports**.

The code in this repository is independent of any particular cluster, user account, ChatGPT account, or Tunnel credentials. It is a research prototype, not a hardened command sandbox.

## Features

- Read-only by default: bounded file listing/reading/searching, Git status/diff, Slurm or PBS job inspection, and system information.
- Opt-in file creation, guarded file replacement, allowlisted command execution (including CMake/Make/MPI workflows), and managed background processes with approved environment overrides and exit-code tracking.
- Separately opt-in Slurm/PBS submission and cancellation, plus locally configured read-only site commands (e.g. point/quota).
- User-level persistence via `systemd --user` when Linger is enabled, or a `cron` watchdog when available.
- No root, setuid, shared daemon, or inbound MCP TCP server.

**Security:** Enabling commands grants the MCP integration capabilities of your Linux user. The executable allowlist is *not* a sandbox. For example, allowlisting Python permits arbitrary code execution. See [Security model](docs/security.md) before enabling any write or command tools.

## Requirements

- Linux and Python 3.11 or newer, with `python3 -m venv` available.
- Access to PyPI (or a suitably configured internal package index).
- `git` for Git tools, `squeue` for Slurm or PBS job inspection and optional scheduler submission.
- For a ChatGPT connection: the separately installed official [tunnel-client](https://github.com/openai/tunnel-client), a private Tunnel and credentials, and an eligible ChatGPT workspace. Availability and billing depend on the provider/account.
- For persistent operation: either a user systemd manager with `Linger=yes` or an active `crond` supporting user crontabs. Follow the cluster site's policies.

## Installation

```bash
git clone https://github.com/YOUR-ACCOUNT/hpc-mcp.git
cd hpc-mcp
./install.sh
```

The repository URL above is a placeholder until publication. Installation creates `.venv` and, if absent, `~/.config/hpc-mcp/config.toml` with mode 0600. It does **not** activate a Tunnel.

Copy and edit the local config to select your authorized filesystem roots (default `~/work`). Start with read-only permissions. To connect ChatGPT, follow [Tunnel setup](docs/tunnel_setup.md) and [Service backends](docs/service_backends.md). Keep `~/.config/hpc-mcp/tunnel.env` and the Tunnel profile outside the repository.

To inspect user-service availability and activate **after** provisioning your private credentials:

```bash
./install.sh --service-status
./install.sh --activate --backend=auto
```

Alternatively use `--backend=systemd`, `--backend=cron`, or `--backend=none`. The installer does not change logind Linger settings or start system daemons. A `Linger=no` environment may not preserve user processes across logout.

## Connect ChatGPT and manage the service

First, prepare a **private OpenAI Platform Tunnel**, a restricted **runtime API key** with `Tunnels Read + Use`, and a **custom MCP plugin** in your ChatGPT workspace. Creating/managing the Tunnel requires `Tunnels Read + Manage`. Platform API authorization and ChatGPT workspace access are separate; a ChatGPT subscription alone is not a substitute for a Platform key. See the detailed **[ChatGPT + Platform + Tunnel setup walkthrough](docs/tunnel_setup.md)**.

If you already use **Remote Desktop Commander (RDC)**, ChatGPT can assist with inspecting the Linux environment, installing HPC MCP, and testing it through RDC. You must handle private credentials and platform/plugin account authorization yourself. After verifying HPC MCP from a new chat, you can disable RDC. See **[RDC-assisted setup](docs/assisted_setup.md)**.

From the checkout directory (`cd ~/work/hpc-mcp`), manage the Tunnel with **one** backend:

| Action | systemd --user | cron watchdog |
| --- | --- | --- |
| Install and start | `./install.sh --activate --backend=systemd` | `./install.sh --activate --backend=cron` |
| Check status | `systemctl --user status hpc-mcp-tunnel.service` | `.venv/bin/python deploy/cron_watchdog.py status` |
| Stop temporarily | `systemctl --user stop hpc-mcp-tunnel.service` | *Not supported as persistent stop while scheduled* |
| Start again | `systemctl --user start hpc-mcp-tunnel.service` | `./install.sh --activate --backend=cron` |
| Restart after config edits | `systemctl --user restart hpc-mcp-tunnel.service` | `.venv/bin/python deploy/cron_watchdog.py stop` then `./install.sh --activate --backend=cron` |
| Stop and disable autostart | `systemctl --user disable --now hpc-mcp-tunnel.service` | `./install.sh --remove-cron` |
| Inspect logs | `journalctl --user -u hpc-mcp-tunnel.service -n 50 --no-pager` | `~/.local/state/hpc-mcp/cron/tunnel.log` (private file) |

```bash
./install.sh --service-status
./install.sh --activate --backend=auto
```

Automatic selection prefers usable `systemd --user` with `Linger=yes`, then cron if available. A cron `stop` alone is temporary because the scheduled watchdog can restart the Tunnel; use `./install.sh --remove-cron` to stop and remove the cron schedule. Use neither `sudo` nor system-wide `systemctl`. After changing enabled MCP tools, **restart your backend, select "Update tools" (or "Refresh tools") in ChatGPT Plugins, and test in a new chat**.

## Configuration

See [config/config.example.toml](config/config.example.toml). The default policy denies all writes, commands and Slurm submissions. Editing the private config requires restarting the Tunnel and refreshing tools in ChatGPT.

For testing with command execution enabled, you can restrict `[commands].allowlist` to `["whoami"]` and test `execute_command(argv=["whoami"], cwd="<an-allowed-root>")`. This is strictly opt-in. For compiler, build, and MPI tool setup, see [Development commands](docs/development_commands.md). The optional `list_allowed_commands` tool reports approved executables available on the service `PATH`.

## Slurm, PBS and site-specific commands

HPC MCP supports **Slurm** and **PBS/OpenPBS** through scheduler adapters.
Choose the backend independently on each cluster in its private configuration:

```toml
[scheduler]
type = "slurm"   # or "pbs", "none"
# bin_dir = "/path/to/scheduler/bin"

[permissions]
enable_scheduler_submit = false
enable_scheduler_cancel = false
enable_site_tools = false
```

The scheduler-neutral tools are `scheduler_list_jobs` and
`scheduler_job_detail`. Submitting an existing, reviewed script with
`scheduler_submit_script` requires `enable_commands = true` and
`enable_scheduler_submit = true`. Cancellation is separately opt-in.
Legacy Slurm-only `slurm_list_jobs` and `submit_slurm_script` tools remain
available on Slurm installations.

**Site commands:** each account can define trusted, fixed-argument
`[site_tools.NAME]` entries in its private TOML file. For example, a local
`point` enquiry can appear as `site_point_balance()`. No separate MCP
instance is required for simple status commands.

**No scheduler node-count cap is hard-coded in HPC MCP.** Job resources are
specified in each reviewed script and enforced by site policy. This project
is not an OS sandbox.

See **[Scheduler adapters and site-specific tools](docs/schedulers_and_site_tools.md)**
for examples, security constraints, and migration from Slurm-only settings.

## Development and tests

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

The tests use mocks for systemd, cron, and Slurm-related behavior; passing tests alone does not establish service persistence across logout or correct behavior on another cluster.

## Documentation

- [Tunnel setup](docs/tunnel_setup.md)
- [Scheduler adapters and site-specific tools](docs/schedulers_and_site_tools.md)
- [Development, build, and MPI command workflows](docs/development_commands.md)
- [systemd and cron](docs/service_backends.md)
- [Security and limitations](docs/security.md)
- [Architecture (Japanese)](docs/design_JA.md)
- [Contributing](CONTRIBUTING.md)

## Status

Version 0.2.0 is a research prototype. MCP tool discovery, direct stdio execution and a private Tunnel deployment have been tested on one HPC system; live PBS compatibility, broad portability, the cron backend on a real `Linger=no` host, and independent multi-user deployments are **not yet verified**.

This repository distributes source code; it does **not** publish a public ChatGPT plugin, nor does it contain or grant Tunnel access. HPC MCP is an independent community project and is not an official OpenAI product.

Licensed under the [MIT License](LICENSE).