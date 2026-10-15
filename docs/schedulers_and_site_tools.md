# Schedulers and site-specific tools

HPC MCP supports two job schedulers through a common MCP interface: **Slurm** and **PBS/OpenPBS**. It also supports optional, fixed-argument site-specific commands such as a `point` balance enquiry. All features run under the authenticated, unprivileged Linux account; they do not require root.

## Scheduler selection

Edit your private `~/.config/hpc-mcp/config.toml` on each cluster.

**Slurm (default, backward compatible):**

```toml
[scheduler]
type = "slurm"
# Set if Slurm commands are unavailable on the Tunnel service PATH:
bin_dir = "/path/to/slurm/bin"

[permissions]
enable_scheduler_submit = false
enable_scheduler_cancel = false
```

**PBS/OpenPBS:**

```toml
[scheduler]
type = "pbs"
# Set this only if PBS commands are unavailable on PATH.
bin_dir = "/path/to/pbs/bin"

[permissions]
enable_scheduler_submit = false
enable_scheduler_cancel = false
```

For machines without a batch scheduler, set `[scheduler] type = "none"`.

If the commands are available on PATH, omit `bin_dir` or set it to `""`. Both `[slurm] bin_dir` and `[permissions] enable_slurm_submit` are supported as **legacy Slurm-only** configuration keys. New configurations should use `[scheduler]` and `enable_scheduler_submit`. A Slurm configuration still registers `slurm_list_jobs` and `submit_slurm_script` for existing ChatGPT clients.

| MCP tool | Slurm command | PBS command | Default |
| --- | --- | --- | --- |
| `scheduler_list_jobs` | `squeue -h -u USER` | `qstat -u USER` | Enabled |
| `scheduler_job_detail(job_id)` | `scontrol show job` | `qstat -f` | Enabled |
| `scheduler_submit_script(script_path)` | `sbatch --parsable` | `qsub` | Disabled |
| `scheduler_cancel_job(job_id)` | `scancel` | `qdel` | Disabled |

Submission requires `enable_commands = true` and `enable_scheduler_submit = true`. Cancellation additionally requires **its own** `enable_scheduler_cancel = true`, and must be reviewed before each request. The submission tool accepts only an existing script under the configured `filesystem.roots`; it does not synthesize or edit scripts. These settings do not impose scheduler resource quotas; job resources are governed by the script and local scheduler policy.

**PBS format coverage:** the adapter handles the standard OpenPBS/PBS Professional `qstat -u` alternate table with a `Job ID`, `Username`, `Queue`, `Jobname`, and state field. PBS variants, including Torque and customized site formats, may differ. The adapter reports the current user's jobs only. Verify compatibility against the cluster's real `qstat` output before production use.

## Site-specific commands

Do **not** create a separate MCP server for every simple local command. Put a command definition in the machine's **private** TOML file and enable this optional feature. For example, if `point` is installed at `/usr/local/bin/point`:

```toml
[permissions]
enable_site_tools = true

[site_tools.point_balance]
description = "Read remaining compute points on this cluster"
argv = ["/usr/local/bin/point"]
read_only = true
cwd = "~/work"
timeout_seconds = 10
```

**Important:** the binary path is only an example; use `command -v point` on the actual cluster to locate it. The executable must exist and be executable. The `cwd` must be inside one of the configured `filesystem.roots`. Command arguments are **fixed** by the local config and cannot be supplied by ChatGPT. No shell is invoked.

After restarting the Tunnel and selecting **Update tools** in ChatGPT Plugins, the tool is advertised as `site_point_balance()`. More than one command can be defined, e.g. `[site_tools.quota_summary]` or `[site_tools.allocation]`, each with a different absolute `argv[0]`.

Only configure commands that genuinely perform non-mutating queries. The required `read_only = true` line is a **human assertion**, not an OS-enforced check; a malicious or misconfigured command could write files or submit jobs with the full privileges of the Linux user. Do not put tokens or passwords in `argv`; do not expose shell interpreters or unreviewed scripts as site tools.

For complex or site-specific APIs requiring authentication, substantial parsing, or permissions more complicated than fixed arguments, prefer a separately maintained Python extension or adapter rather than arbitrary shell command templates. External package loading is not part of this implementation.

## Testing without submitting jobs

```bash
cd ~/work/hpc-mcp
.venv/bin/python -m pytest -q
```

Scheduler adapters are tested with mocked `sbatch`, `qsub`, `squeue`, `qstat`, and related command outputs. The tests **do not submit or cancel real HPC jobs**. Test real scheduler output first with the read-only `scheduler_list_jobs` and `scheduler_job_detail` tools. Live PBS interoperability depends on the target cluster and has not been verified in the initial development environment.

## Refreshing ChatGPT tools

1. Edit only the private TOML policy on the **target** HPC cluster.
2. Restart the active `systemd --user` Tunnel or its cron watchdog.
3. Open ChatGPT Plugins and select **Update tools** on that cluster's custom MCP integration.
4. Use a new chat to verify `get_system_info` (hostname/user), then read-only scheduler and site tools.

A separate private Tunnel can be configured for each HPC system, with its own scheduler and site command declarations.
