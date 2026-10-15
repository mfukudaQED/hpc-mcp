# Secure MCP Tunnel deployment (per researcher)

This guide connects **a private HPC MCP server** running under an ordinary Linux account to **your own ChatGPT custom MCP plugin**. It requires separate OpenAI Platform and ChatGPT setup. No root privilege, incoming firewall rule, or public MCP endpoint is required.

For a quicker overview, see the [README](../README.md). For an optional ChatGPT-assisted installation using Remote Desktop Commander (RDC), see [Assisted setup](assisted_setup.md).

## 1. Prepare OpenAI Platform and ChatGPT

These are **different resources**:

| Resource | Purpose | Where to prepare it |
| --- | --- | --- |
| Platform organization and Tunnel | Host the private relay endpoint and authorize a workspace | [Platform Tunnels](https://platform.openai.com/settings/organization/tunnels) |
| Tunnel management permission | Create/edit a tunnel: **Tunnels Read + Manage** | Platform organization permissions |
| Runtime API key | Run `tunnel-client`: **Tunnels Read + Use** | [Platform API keys](https://platform.openai.com/settings/organization/api-keys) |
| ChatGPT workspace and private plugin | Select the tunnel and expose MCP tools to ChatGPT | [ChatGPT Plugins](https://chatgpt.com/plugins) |

1. Sign in to the [OpenAI Platform](https://platform.openai.com/) using the intended account/organization. A ChatGPT subscription is **not** the same as Platform API billing or authorization; confirm service availability, usage limits, and any applicable charges separately.
2. In **Platform > Organization > Tunnels**, create a Tunnel (or reuse an appropriate existing one) with **Tunnels Read + Manage**. Copy its `tunnel_id` to your private setup notes. Associate the tunnel with the **specific ChatGPT workspace** where you will use the plugin, not just its Platform organization.
3. Create a **restricted runtime API key** with **Tunnels Read + Use**, for the Linux host running `tunnel-client`. Do **not** use a Platform admin key in the long-running service. The operator who selects the tunnel in ChatGPT also needs the required Tunnel use permission.
4. Confirm that the ChatGPT workspace allows adding and using custom MCP servers; on managed workspaces, ask the workspace administrator. ChatGPT-side permissions and Platform Tunnel permissions are independent.
5. Keep the runtime key private. Never paste it into ChatGPT, a Git repository, a terminal command argument, screenshots, or a support ticket.

The latest requirements may differ by workspace or plan. Follow the [official Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) if the UI has changed.

## 2. Install HPC MCP as your normal Linux user

The example assumes the checkout is at `~/work/hpc-mcp`; adjust subsequent paths if you use a different location.

```bash
mkdir -p ~/work
cd ~/work
git clone https://github.com/YOUR-ACCOUNT/hpc-mcp.git
cd hpc-mcp
./install.sh
vi ~/.config/hpc-mcp/config.toml
```

The repository address is a placeholder until the project is published. By default, the per-user configuration permits read-only access under `~/work`. Keep it read-only for the first connection. The MCP executable is `~/work/hpc-mcp/.venv/bin/hpc-mcp`, using stdio, not an inbound TCP port.

## 3. Install the official tunnel-client

Download the appropriate verified binary from [Platform Tunnels](https://platform.openai.com/settings/organization/tunnels) or the [official releases](https://github.com/openai/tunnel-client/releases/latest). Verify the publisher and release integrity according to your site's policy. Install the executable at `~/.local/bin/tunnel-client` with permission 0700, without root.

```bash
~/.local/bin/tunnel-client help quickstart
```

The host needs outbound HTTPS access to `api.openai.com:443` (or the documented mTLS endpoint when configured). Do not open inbound ports.

## 4. Configure a private runtime key and Tunnel profile

Create a private user-only environment file:

```bash
install -d -m 700 ~/.config/hpc-mcp
umask 077
vi ~/.config/hpc-mcp/tunnel.env
chmod 600 ~/.config/hpc-mcp/tunnel.env
```

Enter the following **locally in the editor**, replacing the placeholder with the runtime key:

```text
CONTROL_PLANE_API_KEY=YOUR_PRIVATE_RUNTIME_API_KEY
```

Do not commit, upload, copy into ChatGPT, or print this file. The `systemd --user` service reads this file as its `EnvironmentFile`; the cron watchdog reads it directly.

Initialize the local tunnel profile (replace the Tunnel ID; use your actual checkout path):

```bash
set -a
. ~/.config/hpc-mcp/tunnel.env
set +a

~/.local/bin/tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile hpc-mcp \
  --tunnel-id 'YOUR_TUNNEL_ID' \
  --mcp-command "$HOME/work/hpc-mcp/.venv/bin/hpc-mcp"

~/.local/bin/tunnel-client doctor --profile hpc-mcp --explain
unset CONTROL_PLANE_API_KEY
```

Do not use a privileged/admin API key here. Confirm the profile exists at `~/.config/tunnel-client/hpc-mcp.yaml` and that the sensitive profile is owned by the current user and permission 0600:

```bash
chmod 600 ~/.config/tunnel-client/hpc-mcp.yaml
```

The `doctor` check should report readiness; resolve any error before proceeding.

## 5. Start the Tunnel: manual, systemd or cron

For an interactive one-off test, use the same private file in your own shell and run the client in the foreground:

```bash
set -a
. ~/.config/hpc-mcp/tunnel.env
set +a
~/.local/bin/tunnel-client run --profile hpc-mcp
```

Press Ctrl-C to stop. Then run `unset CONTROL_PLANE_API_KEY` in that shell.

For a persistent service, **stop the foreground client first**, and choose exactly one backend:

```bash
cd ~/work/hpc-mcp
./install.sh --service-status
./install.sh --activate --backend=auto
```

`auto` chooses `systemd --user` if the user manager is usable with `Linger=yes`; otherwise it chooses a usable per-user `cron`; otherwise it reports an error. Explicit choices:

```bash
./install.sh --activate --backend=systemd
# Or, on a supported host where systemd user persistence is unavailable:
./install.sh --activate --backend=cron
```

This does not alter Linger or start system-wide services. Never run it with sudo. Check site policy before installing persistent user processes.

### systemd: start, stop and logs

```bash
systemctl --user status hpc-mcp-tunnel.service
systemctl --user start hpc-mcp-tunnel.service
systemctl --user stop hpc-mcp-tunnel.service
systemctl --user restart hpc-mcp-tunnel.service
systemctl --user enable --now hpc-mcp-tunnel.service
systemctl --user disable --now hpc-mcp-tunnel.service
journalctl --user -u hpc-mcp-tunnel.service -n 50 --no-pager
```

`stop` stops the running service; `disable --now` stops it **and** prevents automatic startup. Use the user service only: **never** use `sudo systemctl` here.

### cron: start, stop and logs

```bash
cd ~/work/hpc-mcp
./install.sh --activate --backend=cron
.venv/bin/python deploy/cron_watchdog.py status
.venv/bin/python deploy/cron_watchdog.py start
./install.sh --remove-cron
```

`--activate --backend=cron` installs a managed `@reboot` and five-minute watchdog schedule in **your own** crontab and starts the Tunnel. `--remove-cron` removes only the managed entries **and stops** the watchdog-owned Tunnel. Do **not** rely on `cron_watchdog.py stop` alone for a lasting stop: the next scheduled watchdog run may restart the Tunnel. To resume, run `./install.sh --activate --backend=cron` again.

Inspect `crontab -l` and the private log at `~/.local/state/hpc-mcp/cron/tunnel.log` if needed; do not share logs containing secrets. Cron persistence after logout or reboot is site-dependent and has not been validated on all HPC systems. See [Service backends](service_backends.md) for switching backends and restrictions.

## 6. Connect the Tunnel to ChatGPT

1. Keep the Tunnel running and healthy.
2. Open [ChatGPT Plugins](https://chatgpt.com/plugins) in your browser.
3. Select **+** > **Add custom MCP server**. Set a recognizable name (for example, `HPC MCP (my cluster)`) and optional description.
4. Under **Connection**, select **Tunnel**, then select your available tunnel or enter its `tunnel_id`. Configure authentication if requested by the UI, review the security warning, and confirm creation. The `tunnel_id` is an identifier, **not** the runtime API key. Never paste the runtime API key here.
5. In an ordinary ChatGPT chat, call `ping`, then `get_system_info`. Confirm that the reported Linux user is **your own** account. Only after that should you test file listing or Slurm status.
6. After enabling additional local tools in `~/.config/hpc-mcp/config.toml`, **restart** the Tunnel and use the plugin's **Update tools / Refresh tools** action in ChatGPT. Open a new chat and check the updated list. A browser page reload alone may not refresh tool definitions.
7. If supported by your account/client, repeat a read-only test from the ChatGPT mobile app.

The exact plugin labels can change. Follow the [official plugin connection guide](https://developers.openai.com/plugins/deploy/connect-chatgpt) if your interface differs.

## 7. Optional write and command access

Opt in by editing only your **local** `~/.config/hpc-mcp/config.toml`, after reading [Security model](security.md). For example:

```toml
[permissions]
enable_writes = true
enable_commands = false
enable_slurm_submit = false
```

For command access, change `enable_commands` explicitly and define a narrow `[commands].allowlist`. An allowlisted interpreter such as `python3` can execute arbitrary code **with the Linux user's privileges**, regardless of filesystem roots. Always review the requested operation. Restart the active backend and update the ChatGPT plugin tool list afterward.

## Scheduler and site-specific tools

HPC MCP supports either Slurm or PBS/OpenPBS and can expose fixed-argument
status commands such as a site-specific `point` command. Select the scheduler
on the Linux host with `[scheduler] type = "slurm"` or
`[scheduler] type = "pbs"`. By default, scheduler inspection is enabled and
submission/cancellation are disabled.

To submit reviewed batch scripts, explicitly enable
`enable_commands = true` and `enable_scheduler_submit = true` in the
private user config. Job cancellation requires a separate
`enable_scheduler_cancel = true` setting. For local status commands, set
`enable_site_tools = true` and define one or more `[site_tools.NAME]`
tables with a trusted absolute executable path and fixed arguments.

Restart your user-level Tunnel and select **Update tools** in ChatGPT Plugins
after configuration changes. Existing Slurm-only installations remain
compatible. See the full [scheduler and site-tools guide](schedulers_and_site_tools.md).

## Troubleshooting checklist

- Check `./install.sh --service-status` and the selected backend's **status** command.
- Run `tunnel-client doctor --profile hpc-mcp --explain` with your locally loaded runtime key. Do not print it.
- Verify outbound HTTPS, the **correct Tunnel ID**, the Platform organization/ChatGPT workspace association, and **Tunnels Read + Use**.
- Confirm that only one backend/client instance owns the Tunnel.
- For missing tools, restart the Tunnel, then **Update tools** from ChatGPT Plugins; start a new conversation.
- On `Linger=no`, systemd-user persistence is not guaranteed. The cron fallback also depends on the site's policies.
- Never paste credential files or raw secrets into diagnostic reports.

## Official references

- [OpenAI Secure MCP Tunnel guide](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [OpenAI tunnel-client repository and onboarding](https://github.com/openai/tunnel-client/blob/master/docs/onboarding.md)
- [Connect a custom MCP server in ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt)
