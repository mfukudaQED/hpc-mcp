# Security model

HPC MCP is **not a multi-tenant root daemon**. Each researcher runs their own
process using their own unprivileged Linux account, with independently issued
Tunnel credentials. Never share a Tunnel ID or an API key with another user.

The default configuration only exposes bounded read-only tools. No TCP listener
is created by the Python server. File access is checked against canonicalized
roots and sensitive path names. Symlinks resolving outside a root are refused.
This is not a kernel sandbox; filesystem TOCTOU races and novel secret names
are not exhaustively prevented.

When `enable_commands = true`, the process can execute allowed binaries with the
full Linux account privileges. Even an allowlisted `python3`, `make`, `cmake`,
`mpiexec`, `git`, or `bash` may execute arbitrary programs or read secrets. A command allowlist is
**not a security boundary**. Do not enable this on shared identities or assume
that file roots restrict it. Model output and retrieved source code may carry
malicious prompt-injection instructions. `commands.env_allowlist` permits only
named variable overrides, but is not a sandbox; variables such as `LD_PRELOAD`,
`PATH`, or `PYTHONPATH` can alter executable selection and code loading. Prefer
reviewed OpenMP/MPI variables only. Build and MPI tools should run under the
appropriate scheduler allocation, never unreviewed on an HPC login node.

Use a dedicated Linux account with limited permissions, a container/namespace
sandbox, or a separately approved scheduler runner if hard command isolation
is required. No privilege escalation or `sudo` support is provided.

The optional `scheduler.bin_dir` setting selects trusted site-installed Slurm or PBS executables without relying on an interactive shell's `PATH`. The older `slurm.bin_dir` setting is still supported for Slurm. These settings are not sandboxes.

The Slurm and PBS submit tools do not enforce a custom node-count limit. Job resources
are requested by the script and enforced by the site's Slurm configuration.
Operators must review requested resources; a hard user quota requires
administrator-managed Slurm account/QoS configuration.

The background process manager creates detached child groups; session metadata
under `~/.local/state/hpc-mcp/sessions` is private and identifies PIDs by
creation time. It is an MVP, not an HPC job scheduler or comprehensive process
sandbox. Scheduler submission and cancellation run as the current UID and are
subject to site policies.

Custom site commands require an explicit `enable_site_tools = true`
opt-in and a fixed argument vector, absolute executable path, permitted
working directory, and short timeout. The `read_only = true` declaration
is not verified by the OS and does not prevent side effects. Review every
configured binary or script before enabling it. Scheduler cancellation has
its own opt-in and may terminate jobs; obtain explicit user review.

The Tunnel client needs its own runtime API key; create it with Read + Use only.
Do not place keys in a command line, source repository, chat message, or world-
readable file. For systemd, use a 0600 `EnvironmentFile` in the user's home.
Do not expose the local Tunnel admin UI externally.

Before enabling access, review institutional network policy, processing of
research data by third-party services, compute-node login restrictions, and
resource quota limits. Public plugin publication is not supported by private
Secure MCP Tunnel. Public repository distribution of the code is separate.