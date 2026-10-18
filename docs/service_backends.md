# Unprivileged service installation (systemd / cron)

This deployment never calls sudo, su, pkexec, or any system-wide service
management command. Each researcher runs it under their own Linux UID and
their own ChatGPT Tunnel credentials.

## Initial setup

1. Install using `./install.sh`. This updates the Python package and preserves
   existing private configuration. **It does not start a Tunnel.**
2. Follow `docs/tunnel_setup.md` to create private files
   (`~/.config/tunnel-client/hpc-mcp.yaml` and
   `~/.config/hpc-mcp/tunnel.env`), chmod 0600 and owned by the user.
3. Run `./install.sh --service-status` to inspect the available backends.
4. Run `./install.sh --activate --backend=auto` to select:

   - `Linger=yes` and a responsive user manager: `systemd --user`.
   - Otherwise, if the user's crond is available: `cron`.
   - Otherwise, fail visibly; do not falsely promise background persistence.

Select explicitly with `--backend=systemd` or `--backend=cron`, or use
`--backend=none` for install-only mode.

## Updating a running installation

After fetching new HPC MCP code, run `./install.sh` to update the package
without replacing your private `config.toml`. Manually merge any newly
introduced settings, restart your **existing** user-owned backend, and
refresh tools in ChatGPT. See the complete [upgrade guide](upgrading.md),
including how to install or upgrade the optional [MCP File Manager](file_manager.md).

## systemd backend

Copies `deploy/hpc-mcp-tunnel.service` to
`~/.config/systemd/user/hpc-mcp-tunnel.service`, then calls user-only
`systemctl --user daemon-reload`, `enable` and `start`. It intentionally never
restarts an already active instance.

```sh
systemctl --user status hpc-mcp-tunnel.service
systemctl --user restart hpc-mcp-tunnel.service
systemctl --user stop hpc-mcp-tunnel.service
```

No attempt is made to change Linger or other system-wide policies.

## cron backend

Adds a bounded managed block to the existing user's crontab, preserving
unrelated jobs, with `@reboot` and every-five-minute watchdog entries.
The watchdog is run with the project's Python interpreter and manages only
the current user's Tunnel client. It uses a file lock, PID start ticks,
an exact executable check, and a private state directory to limit duplicate
processes and mistaken signals. It reads the private API key without a shell.

```sh
./install.sh --service-status
.venv/bin/python deploy/cron_watchdog.py status
./install.sh --remove-cron
```

Watchdog logs live in `~/.local/state/hpc-mcp/cron/tunnel.log` (mode 0600).
Cron requires an active crond daemon and a usable per-user crontab.
The installer does not start crond or change system-level settings.

**HPC caveat:** Some sites kill cron job descendants or all user processes
upon logout. Neither `setsid` nor `@reboot` overrides cluster policies.
Always test actual persistence after logout and reboot; do not install
background services where site policies prohibit them.

## Day-to-day lifecycle: enable, stop, restart, disable

Run all commands from the repository root as your own Linux user. Do **not** start both backends at the same time.

| Operation | systemd backend | cron backend |
| --- | --- | --- |
| Enable / install | `./install.sh --activate --backend=systemd` | `./install.sh --activate --backend=cron` |
| Start | `systemctl --user start hpc-mcp-tunnel.service` | `./install.sh --activate --backend=cron` |
| Status | `systemctl --user status hpc-mcp-tunnel.service` | `.venv/bin/python deploy/cron_watchdog.py status` |
| Restart | `systemctl --user restart hpc-mcp-tunnel.service` | `.venv/bin/python deploy/cron_watchdog.py stop` then `./install.sh --activate --backend=cron` |
| Disable and stop | `systemctl --user disable --now hpc-mcp-tunnel.service` | `./install.sh --remove-cron` |

For cron, manually calling the watchdog's `stop` action does **not** remove its recurring schedule: the next watchdog invocation may start it again. Use `--remove-cron` to stop it persistently. The cron installer modifies only its own delimited block in the user's crontab.

For systemd, `stop` does not disable autostart, but `disable --now` does. After modifying local MCP permissions, restart the active backend, select **Update tools / Refresh tools** in ChatGPT Plugins and test in a new conversation.

To switch between backends, first disable and stop the old backend, then activate the new one. Cron is only a fallback when the site's scheduler and persistence policy support it.

## Enabling editing and process execution

The default is deliberately read-only. Individual users may explicitly
enable capabilities in `~/.config/hpc-mcp/config.toml`:

```toml
[permissions]
enable_writes = true
enable_commands = true
enable_slurm_submit = false

[commands]
allowlist = ["hostname", "whoami", "pwd", "date", "uptime", "git", "python3"]
```

Then restart the user's Tunnel so tools are rediscovered:

```sh
systemctl --user restart hpc-mcp-tunnel.service
```

For Slurm or PBS submission, enable `enable_scheduler_submit = true`
alongside `enable_commands = true` in the private configuration.
To select a scheduler, set `[scheduler] type = "slurm"` or
`[scheduler] type = "pbs"`. Site command enquiries can be configured
under `[site_tools.NAME]` and enabled with `enable_site_tools = true`.
All changes require a restart of the active user-level backend and a ChatGPT
**Update tools** action. See [scheduler configuration](schedulers_and_site_tools.md).

File changes use approved roots and SHA-256 guarded overwrite. **The command
allowlist is not an OS sandbox:** interpreters and build tools may run arbitrary
user-privileged code and read outside the file roots. Use only with a trusted,
private per-user Tunnel; review all modifications and untrusted source content.
Never use administrator privileges on sham.
