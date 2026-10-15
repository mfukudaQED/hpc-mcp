# Development command workflows

HPC MCP provides a generic, **opt-in** command executor rather than one MCP
tool per executable. This keeps the same interface usable with site-specific
compilers, MPI implementations, and build systems.

## Capability overview

- `list_allowed_commands()`: report configured executable names, which ones
  are found on the MCP service's `PATH`, approved environment variables, and
  execution limits. This tool is advertised only when commands are enabled.
- `execute_command(argv, cwd, env_overrides=None)`: run a short task and return
  bounded combined output, an exit code, or a timeout indication.
- `start_background_process(argv, cwd, env_overrides=None)`: run a longer task
  and return a session ID immediately.
- `read_background_output(session_id, offset_bytes=0)`: return bounded output,
  the new byte offset, a running flag, and (once available) the process exit code.
- `terminate_background_process(session_id)`: terminate a server-managed user
  process group, **not** a Slurm/PBS job.

All execution is under the tunnel's unprivileged Linux user. Each command name
must appear in `commands.allowlist`; `cwd` must be inside
`filesystem.roots`. No shell is invoked, so use separate entries in `argv`;
do not pass strings such as `"make && ctest"`.

**Important security limitation:** the allowlist controls only the first
executable. `make`, `cmake`, `mpiexec`, compilers, test runners, and
interpreters can execute additional programs. CWD checks do not confine the
process's filesystem access; the runner is not an OS sandbox. Review source
trees, Makefiles, test definitions, commands, and target-site policy.

## Recommended command catalog

These are candidates to consider, **not** a default allowlist. Actual binary
names vary with installed software and environment modules.

| Group | Candidate commands | Typical use | Recommendation |
| --- | --- | --- | --- |
| CMake/Make | `cmake`, `make`, `ctest`, `ninja` | Configure, build, and test | Primary opt-in |
| Alternate build | `meson`, `autoreconf`, `autoconf`, `automake` | Build-system generation | Project-specific |
| GNU/LLVM | `gcc`, `g++`, `gfortran`, `clang`, `clang++`, `flang-new` | C, C++, and Fortran compilation | Primary opt-in |
| Intel oneAPI | `icx`, `icpx`, `ifx`, `ifort`, `icc`, `icpc` | Intel compiler stacks; names differ by version | Cluster-specific |
| MPI wrappers | `mpicc`, `mpicxx`, `mpifort`, `mpif90`, `mpiicx`, `mpiicpx`, `mpiifx`, `mpiifort` | MPI-linked compilation | Cluster-specific |
| MPI launch | `mpiexec`, `mpirun` | Launch parallel executables | **Explicit review / allocation** |
| Test runners | `pytest`, `tox`, `nox`, `ctest` | Regression/integration tests | Opt-in |
| Diagnostics | `gdb`, `lldb`, `valgrind`, `perf`, `gprof`, `gcov`, `llvm-cov` | Debugging, profiles, coverage | Review resource cost |
| Code quality | `clang-format`, `clang-tidy`, `cppcheck`, `ruff`, `mypy`, `shellcheck` | Style and static checks | Opt-in |
| Binary inspection | `file`, `ldd`, `nm`, `readelf`, `objdump`, `strings`, `size` | Libraries, linkage, and symbols | Mostly read-only |
| Dependencies | `pkg-config`, `spack`, `conda`, `pip`, `uv` | Inspect/manage toolchains and packages | Separate mutating review |
| Search/comparison | `rg`, `grep`, `find`, `diff`, `cmp`, `wc`, `stat` | Source investigation | Prefer native file tools first |
| Compute diagnostics | `lscpu`, `numactl`, `lstopo`, `nvidia-smi`, `rocm-smi` | Hardware/topology info | Cluster-specific |
| File operations | `rsync`, `tar`, `unzip`, `patch` | Data movement and patch application | Can mutate data |
| Version control | `git` | Commit, branch, remote operations | Prefer native `git_status_tool` / `git_diff_tool`; keep push manual |

The `module` command is often a shell function rather than an executable, so
`argv=["module", ...]` will usually **not work**. A site should initialize
its compiler/MPI environment in the user-level tunnel service (or an explicitly
reviewed wrapper), not grant unrestricted `bash -lc` access solely to run
`module load`. `command -v` and `type` are also commonly shell builtins;
`list_allowed_commands()` checks the service's actual executable search path.

Scheduler commands (Slurm/PBS submission and cancellation) are intentionally
handled by dedicated scheduler tools, not by adding unrestricted `sbatch`,
`qsub`, `scancel`, or `qdel` to the command allowlist.

## Machine-local configuration

For sham, the reviewed starting list is in
[`config/command_allowlist.sham.example.toml`](../config/command_allowlist.sham.example.toml).
It is an example rather than a live policy; merge its `[commands]` section into
the private per-user configuration after checking the installed compiler/MPI
modules. Adding `mpiexec` to a name allowlist does not make it visible on the
service `PATH`, nor does it allocate compute nodes.

Edit the private `~/.config/hpc-mcp/config.toml` **on each machine**, not
the committed template, to grant exactly the commands required:

```toml
[filesystem]
roots = ["~/work"]

[permissions]
enable_commands = true

[commands]
allowlist = [
  "hostname", "whoami", "pwd", "date", "uptime",
  "cmake", "make", "ninja", "ctest",
  "gcc", "g++", "gfortran", "icx", "icpx", "ifx",
  "mpicc", "mpicxx", "mpifort"
]
env_allowlist = [
  "OMP_NUM_THREADS", "OMP_PROC_BIND", "OMP_PLACES",
  "MKL_NUM_THREADS", "I_MPI_COLL_EXTERNAL", "I_MPI_FABRICS"
]

[limits]
command_timeout_seconds = 120
max_background_sessions = 4
```

This is an **illustrative opt-in configuration**, not a safe default. If direct
MPI launching has been approved for this user's session and site, add
`"mpiexec"` deliberately; its presence in the command allowlist is itself
a broad execution privilege. Never run a parallel compute workload on a login
node unless the site's policy explicitly allows it.

Keep short commands in `execute_command`; use a managed background session for
large builds/tests. The synchronous timeout is at most 300 seconds. Background
sessions survive the initial MCP request but their status tracking is
best-effort; if the tunnel process restarts while a job is running, an exit
code may be unknown. For production HPC workloads, submit through Slurm/PBS.

## MCP call examples

The following calls are examples of tool arguments, **not** shell snippets.
The working directory must already exist and be allowed.

### Configure an out-of-source CMake build

```text
start_background_process(
  argv=["cmake", "-S", ".", "-B", "build", "-DCMAKE_BUILD_TYPE=Release"],
  cwd="/home/USER/work/PROJECT"
)
```

### Build (bounded parallelism)

```text
start_background_process(
  argv=["cmake", "--build", "build", "--parallel", "16"],
  cwd="/home/USER/work/PROJECT"
)

start_background_process(
  argv=["make", "-j", "16"],
  cwd="/home/USER/work/PROJECT"
)
```

### Run CTest

```text
start_background_process(
  argv=["ctest", "--test-dir", "build", "--output-on-failure", "-j", "4"],
  cwd="/home/USER/work/PROJECT"
)
```

### MPI (only inside a valid allocation or where permitted by site policy)

```text
start_background_process(
  argv=["mpiexec", "-n", "8", "./my_program"],
  cwd="/home/USER/work/PROJECT",
  env_overrides={
    "I_MPI_COLL_EXTERNAL": "no",
    "I_MPI_FABRICS": "shm:ofi",
    "OMP_NUM_THREADS": "16"
  }
)
```

For sham's existing Intel MPI workflow, `mpiexec` together with
`I_MPI_COLL_EXTERNAL=no` and `I_MPI_FABRICS=shm:ofi` is the tested
starting point; `srun` has previously shown problems with that stack.
The preferred execution location is still a **reviewed Slurm batch script**
submitted with `scheduler_submit_script`, which places the MPI command
inside an allocated job. The MCP tunnel process on a login node is **not**
automatically inside that allocation. The example above is not permission to
launch on a login node.

## Deployment / verification

1. Review each new executable and every `env_allowlist` entry against local
   policies and the requested directories.
2. Edit the private TOML on that particular cluster.
3. Restart the selected `systemd --user` or cron Tunnel backend.
4. Refresh the plugin tools in ChatGPT and open a new conversation.
5. Call `list_allowed_commands` before requesting a build.
6. Test `cmake --version`, `make --version`, and `mpiexec --version`
   individually; they do not run a project build or an MPI job.
7. Review an actual source tree and batch allocation before compiling/running.

No GitHub push, scheduler submission, or cluster-wide permission change is
needed to introduce the command support in source code.
