# Intel oneAPI and Intel MPI in the sham user-level MCP service

This guide describes the **sham-specific** deployment of the existing HPC MCP
Tunnel with the site's Intel oneAPI Environment Modules. The main HPC MCP
server, scheduler adapters, and tool permissions remain unchanged.

## Verified environment (2026-10-15)

- Compiler module: `compiler/latest` → Intel oneAPI 2023.1.0.
- MPI module: `mpi/latest` → Intel MPI 2021.9.0.
- MKL module: `mkl/latest` → Intel MKL 2023.1.0.
- Additional modules: `tbb/latest`, `compiler-rt/latest`,
  `oclfpga/latest`.
- Environment Modules: `/etc/profile.d/modules.sh`
- Site modulefiles: `/opt/intel/oneapi/modulefiles`

User-level `systemd` starts with a minimal PATH, without loading the
interactive shell's modules. A small startup script loads the six modulefiles,
sets the established sham-specific Intel MPI variables, and then execs the
existing Tunnel client. The service's private credentials continue to be
loaded by its existing systemd `EnvironmentFile`; the startup script neither
contains nor prints credentials.

## Install or update

Run all commands **as the ordinary Linux user; never use sudo**.

```bash
cd ~/work/hpc-mcp
install -m 0700 deploy/sham_oneapi_tunnel.sh ~/.local/bin/hpc-mcp-oneapi-launch

mkdir -p ~/.config/systemd/user/hpc-mcp-tunnel.service.d
cat > ~/.config/systemd/user/hpc-mcp-tunnel.service.d/oneapi.conf <<'EOF'
[Service]
ExecStart=
ExecStart=%h/.local/bin/hpc-mcp-oneapi-launch
EOF
chmod 0600 ~/.config/systemd/user/hpc-mcp-tunnel.service.d/oneapi.conf

env PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin \
  ~/.local/bin/hpc-mcp-oneapi-launch --check
systemctl --user daemon-reload
systemctl --user restart hpc-mcp-tunnel.service
systemctl --user is-active hpc-mcp-tunnel.service
```

The drop-in changes only `ExecStart`; the existing unit's `EnvironmentFile`,
limits and security restrictions remain in place. The user unit's current
`CPUQuota=10%`, `MemoryMax=512M`, and `TasksMax=64` are **not appropriate for
running substantial MPI workloads inside the Tunnel service cgroup**. Submit
actual parallel production calculations through the Slurm scheduler using a
reviewed batch script. `mpiexec -version` tests the launcher without starting
an MPI calculation.

## Verification from ChatGPT's HPC MCP integration

Use an approved working directory such as `~/work/hpc-mcp`:

```text
execute_command(argv=["ifx", "--version"], cwd="/home/fukuda/work/hpc-mcp")
execute_command(argv=["icx", "--version"], cwd="/home/fukuda/work/hpc-mcp")
execute_command(argv=["mpiexec", "-version"], cwd="/home/fukuda/work/hpc-mcp")
execute_command(argv=["mpiifort", "-show"], cwd="/home/fukuda/work/hpc-mcp")
```

All four commands succeeded on 2026-10-15 after restarting the user
service. The MCP command allowlist must independently permit each command.
This setup does **not** grant filesystem permissions, bypass the scheduler,
or start compute jobs.

The wrapper exports the two sham MPI defaults:

```bash
export I_MPI_COLL_EXTERNAL=no
export I_MPI_FABRICS=shm:ofi
```

Use per-job settings and allocations appropriate to each computation. Other
HPC systems should use their own module paths and launcher scripts, not this
sham-specific wrapper.

## Rollback

Restore the original Tunnel entrypoint by removing only this drop-in and
restarting the user-level service:

```bash
rm ~/.config/systemd/user/hpc-mcp-tunnel.service.d/oneapi.conf
systemctl --user daemon-reload
systemctl --user restart hpc-mcp-tunnel.service
```

The original unit file and private Tunnel credentials are not modified.
