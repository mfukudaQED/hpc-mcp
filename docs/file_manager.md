# Optional MCP File Manager integration

MCP File Manager is a separate,
optional MCP Apps file browser and text editor. HPC MCP hosts its tools and UI
resources inside the **existing per-user MCP server and Secure MCP Tunnel**.
It does not run another listener, reverse proxy, or server process.

The extension is disabled unless explicitly enabled by the user.

## Installation

1. Install and connect [HPC MCP](../README.md) first.
2. Obtain a checkout or release of MCP File Manager (the project can be
   installed from a local checkout even before it is publicly published).
3. Install the optional package into **HPC MCP's own Python environment**:

   ```sh
   cd /path/to/hpc-mcp
   .venv/bin/python -m pip install -e /path/to/mcp-file-manager
   ```

   Use `pip install /path/to/mcp-file-manager` for a non-editable install.
   The packaged UI is self-contained; Node.js/npm is only required for
   building the File Manager frontend from source.

4. Add the following setting to your private `~/.config/hpc-mcp/config.toml`:

   ```toml
   [extensions.file_manager]
   enabled = true
   enable_edit = false
   ```

   Do **not** append another `[extensions.file_manager]` table if one
   already exists. Existing filesystem roots in `[filesystem].roots` are
   passed to File Manager. Keep them limited to directories you authorize.

5. Restart the user-owned Tunnel service and select **Update tools** / **Refresh
   tools** in ChatGPT's connected plugin. See [updating an existing
   installation](upgrading.md) for exact commands for systemd and cron.

### Optional text editing

File Manager starts in read-only mode. To enable editing, **both** settings
must be true:

```toml
[permissions]
enable_writes = true

[extensions.file_manager]
enabled = true
enable_edit = true
```

Merge these keys into existing tables, without duplicating them.
**Important:** `permissions.enable_writes` is a global HPC MCP permission.
Setting it to true also enables the server's own authorized filesystem
write tools; it does not grant File Manager-only access. Review the
[security model](security.md) before opting in.

Editing is further restricted by File Manager to existing, owned,
owner-writable, small UTF-8 files (64 KiB maximum) and guarded by a
revision check. Writing is never implied just by enabling the UI.

### Older configuration compatibility

The older `[extensions.file_viewer]` / `enabled = true` setting is still
understood as a fallback. Prefer `[extensions.file_manager]` for all new
deployments. If both are present, the new table's `enabled` value takes
precedence. Editing requires the new `enable_edit` key and global
`enable_writes` regardless of the legacy key.

## User workflow in ChatGPT

Ask ChatGPT to open an **absolute file path** within an authorized root with
the HPC MCP `file_viewer_open` tool. This tool associates the UI with the
MCP App resource `ui://mcp-file-manager/v16/app.html`. The UI requests
`fullscreen` as its preferred display mode, which ChatGPT may honor by
opening it as a separate conversation tab; otherwise use **Open app in tab**
on the inline app. The host determines the final display position.

The File Explorer starts collapsed so the text viewer uses the whole panel.
Use **Explorer** to expand the folder tree and Markdown outline, and
**Hide Explorer** to collapse it. Selecting a file collapses the explorer.

`file_manager_panel` is a separate no-argument, optional thread-entrypoint
tool for hosts that expose it; its presence does **not** guarantee a
ChatGPT tab-add button in Chat mode. ChatGPT does not automatically turn
ordinary filenames in all assistant messages into a File Manager link.

Git history and restore are available for **already tracked and committed**
files when editing is enabled. Saves do not automatically create commits or
backups; manage version control yourself. The File Manager repository's `docs/USER_GUIDE.md` describes the editor,
Diff, history and safety limits.

## Confirm installed capabilities

Within an authorized testing directory, ask ChatGPT to open a small text
file; confirm the app loads and the Explorer can be expanded and collapsed.
If editing was enabled, use only a disposable file to test Save and restore.
If the `file_viewer_open` tool is missing, check:

- `[extensions.file_manager].enabled = true` in the private config.
- The optional package is installed in the Python interpreter **actually
  used** by HPC MCP (not an unrelated virtual environment).
- The Tunnel was restarted after any code/configuration change.
- ChatGPT's connected plugin tools were refreshed.

The extension does not introduce a separate HTTP endpoint. The same
per-user Tunnel, roots and ChatGPT trust settings apply.
