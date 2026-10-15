"""Slurm adapter: squeue, sbatch, scontrol, and scancel."""

from __future__ import annotations

import getpass

from ..config import Settings
from .base import binary, checked_job_id, checked_script, execute


class SlurmScheduler:
    name = "slurm"

    def list_jobs(self, settings: Settings) -> dict:
        user = getpass.getuser()
        result = execute(settings, [
            binary(settings, "squeue"), "-h", "-u", user,
            "-o", "%i|%P|%j|%T|%M|%D|%R",
        ], timeout=10)
        if result["exit_code"] != 0:
            return {"scheduler": self.name, "user": user, "jobs": [], "error": result["stderr"], "exit_code": result["exit_code"]}
        jobs = []
        for line in result["stdout"].splitlines()[:200]:
            items = line.split("|", 6)
            if len(items) == 7:
                jobs.append({
                    "job_id": items[0], "queue": items[1], "name": items[2],
                    "state": items[3], "elapsed": items[4], "nodes": items[5],
                    "reason": items[6], "scheduler": self.name,
                })
        return {"scheduler": self.name, "user": user, "jobs": jobs}

    def submit(self, settings: Settings, script_path: str) -> dict:
        script = checked_script(settings, script_path)
        result = execute(settings, [
            binary(settings, "sbatch"), "--parsable", str(script),
        ], cwd=script.parent)
        if result["exit_code"] == 0:
            result["job_id"] = result["stdout"].split(";", 1)[0]
        result["scheduler"] = self.name
        return result

    def job_detail(self, settings: Settings, job_id: str) -> dict:
        job_id = checked_job_id(job_id)
        result = execute(settings, [
            binary(settings, "scontrol"), "show", "job", job_id,
        ], timeout=10)
        result.update({"scheduler": self.name, "job_id": job_id})
        return result

    def cancel(self, settings: Settings, job_id: str) -> dict:
        job_id = checked_job_id(job_id)
        # The scheduler is authoritative for Linux user ownership.
        result = execute(settings, [binary(settings, "scancel"), job_id])
        result.update({"scheduler": self.name, "job_id": job_id})
        return result
