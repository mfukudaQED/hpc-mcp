# Updating an existing HPC MCP installation

These procedures apply to an already installed, **per-user** HPC MCP
deployment. They do not require root privileges or new Tunnel credentials.

The installer updates code and the Python environment but **does not
overwrite** an existing `~/.config/hpc-mcp/config.toml`, replace private
Tunnel credentials, or automatically restart an already active service.

## 1. Review and update the HPC MCP checkout

From the directory where you originally cloned HPC MCP:

```sh
cd /path/to/hpc-mcp
git status --short
git pull --ff-only
./install.sh
```

Before `git pull`, resolve any local edits or untracked files that would
conflict with the update. Do not discard local work using `git reset --hard`.
If installing from an archive, replace the checkout using the method you
used for that archive instead of running `git pull`.

`./install.sh` reuses the checkout's `.venv` when present, executes
`.venv/bin/python -m pip install -e .`, and creates the user config only
if it does not already exist. Its default install mode does **not**
start or stop the existing Tunnel.

If the existing environment is broken, inspect the Python interpreter
and environment before changing it. The current HPC MCP release expects
Python 3.11+; `install.sh` uses `python3` when creating a new `.venv`.

**Note:** New changes are only available to other users after their
maintainer publishes/pushes the corresponding commits. An existing
installation is not updated automatically by a local, unpushed commit.

## 2. Optional: install/upgrade MCP File Manager

File Manager is a **separate project** and is not installed automatically
by `./install.sh`. To opt in:

```sh
cd /path/to/mcp-file-manager
git pull --ff-only
/path/to/hpc-mcp/.venv/bin/python -m pip install -e .
```

Skip `git pull` if using a published archive or a checkout not yet
associated with a remote. The first installation may use a locally
available package checkout. If upgrading an existing editable install,
updating the source plus restarting HPC MCP is often sufficient; rerunning
pip ensures package metadata and dependencies stay in sync.

In your private `~/.config/hpc-mcp/config.toml` add or merge:

```toml
[extensions.file_manager]
enabled = true
enable_edit = false
```

No change is needed to `[permissions].enable_writes` for read-only use.
For editing, deliberately set `[permissions].enable_writes = true`
**and** `[extensions.file_manager].enable_edit = true`. This grants
HPC MCP's other explicitly authorized file-write tools too. See
[File Manager integration](file_manager.md) and
[security](security.md).

Use only filesystem roots you intend to expose; they are shared across
HPC MCP's core file tools and this extension.

## 3. Restart only your active backend

Check your currently selected backend:

```sh
cd /path/to/hpc-mcp
./install.sh --service-status
```

If **systemd --user** is the active backend:

```sh
systemctl --user restart hpc-mcp-tunnel.service
systemctl --user status hpc-mcp-tunnel.service
```

If **cron watchdog** is the active backend:

```sh
cd /path/to/hpc-mcp
.venv/bin/python deploy/cron_watchdog.py stop
.venv/bin/python deploy/cron_watchdog.py start
.venv/bin/python deploy/cron_watchdog.py status
```

These commands manage the current user's service only. Do not run them
with `sudo`, and do not activate both backends simultaneously.
The cron watchdog's scheduled invocation may start the Tunnel again
even after a temporary `stop`; to remove its schedule altogether use
`./install.sh --remove-cron` intentionally.

If using neither backend, restart your own manually launched Tunnel
by the method used to launch it.

## 4. Refresh the ChatGPT connection

In ChatGPT, open the connected HPC MCP plugin and select **Update tools**
or **Refresh tools**. Start a new conversation if stale tool schemas
persist. Verify `ping` and (if enabled) `file_viewer_open`.

The File Manager v16 resource URI is
`ui://mcp-file-manager/v16/app.html`, which helps avoid reopening an
older cached UI. The UI asks ChatGPT to prefer fullscreen; actual rendering
remains host-controlled.

## 5. Troubleshooting and rollback

- **Existing config missing new options:** `install.sh` does not merge
  new configuration keys into an existing file. Add the extension section
  manually; do not overwrite your private settings with an example.
- **File Manager fails to import:** install the optional package using
  `/path/to/hpc-mcp/.venv/bin/python -m pip install -e /path/to/mcp-file-manager`.
- **Tools missing after restart:** confirm `enabled = true`, that the
  active service uses the updated checkout/environment, and refresh ChatGPT.
- **UI still appears inline:** use **Open app in tab** if offered; the
  fullscreen preference is not mandatory.
- **Editing unavailable:** both opt-in settings are needed, plus ownership,
  file-size and other File Manager editing restrictions.
- **Need to revert:** disable `[extensions.file_manager].enabled` and
  restart/refresh. The other HPC MCP tools continue to work. For an HPC
  MCP code rollback, deliberately check out a reviewed earlier revision;
  first preserve any uncommitted work. Do not delete credentials/config.

See [service backends](service_backends.md) for full lifecycle details.
