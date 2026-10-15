#!/usr/bin/env bash
# Start the per-user HPC MCP Tunnel with the sham Intel oneAPI toolchain.
# This uses the site's Environment Modules installation and never requires root.
set -euo pipefail

# The systemd user service does not start a login shell or load module paths.
source /etc/profile.d/modules.sh
module use /opt/intel/oneapi/modulefiles

# Match the default interactive Intel oneAPI compiler, MKL and MPI modules.
module load tbb/latest compiler-rt/latest mkl/latest oclfpga/latest compiler/latest mpi/latest

# This setting is needed for the existing Intel MPI workflow on sham.
export I_MPI_COLL_EXTERNAL=no
export I_MPI_FABRICS=shm:ofi

# Fail before starting the tunnel if the required compiler/MPI tools are absent.
for executable in ifort ifx icx icpx mpiifort mpiexec; do
    command -v "$executable" >/dev/null || {
        printf 'Missing required oneAPI executable: %s\n' "$executable" >&2
        exit 1
    }
done

# A read-only diagnostic; do not launch another Tunnel client.
if [[ "${1:-}" == "--check" ]]; then
    for executable in ifort ifx icx icpx mpiifort mpiexec; do
        command -v "$executable"
    done
    printf 'I_MPI_COLL_EXTERNAL=%s\n' "$I_MPI_COLL_EXTERNAL"
    printf 'I_MPI_FABRICS=%s\n' "$I_MPI_FABRICS"
    exit 0
fi

if [[ "$#" -ne 0 ]]; then
    printf 'Usage: %s [--check]\n' "$0" >&2
    exit 2
fi

exec "$HOME/.local/bin/tunnel-client" run --profile hpc-mcp --health.listen-addr=127.0.0.1:0
