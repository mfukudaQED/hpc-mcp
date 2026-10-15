"""PBS/OpenPBS adapter: qstat, qsub and qdel.

The qstat -u format is common to OpenPBS/PBS Professional; installations with
nonstandard table layouts may require a site-specific adapter.
"""

from __future__ import annotations

import getpass
import re

from ..config import Settings
from .base import binary, checked_job_id, checked_script, execute


class PBSScheduler:
    name = "pbs"

    def list_jobs(self, settings: Settings) -> dict:
        user = getpass.getuser()
        result = execute(settings, [binary(settings, "qstat"), "-u", user], timeout=10)
        if result["exit_code"] != 0:
            return {"scheduler": self.name, "user": user, "jobs": [], "error": result["stderr"], "exit_code": result["exit_code"]}
        jobs = []
        lines = result["stdout"].splitlines()
        # Standard PBS alternate output has Job ID, Username, Queue,
        # Jobname, SessID, NDS, TSK, Memory, Time, S, Time.
        # Find state relative to the tail to accommodate unset columns.
        for line in lines:
            parts = line.split()
            if not parts or not re.match(r"^[0-9]+(?:\[.*?\])?(?:\.[A-Za-z0-9_.-]+)?$", parts[0]):
                continue
            if len(parts) < 5 or parts[1] != user:
                continue
            state = next((p for p in reversed(parts) if p in {"B", "E", "F", "H", "M", "Q", "R", "S", "T", "U", "W", "X"}), "?")
            jobs.append({
                "job_id": parts[0], "queue": parts[2], "name": parts[3],
                "state": state, "elapsed": "", "nodes": "", "reason": "",
                "scheduler": self.name,
            })
            if len(jobs) >= 200:
                break
        return {"scheduler": self.name, "user": user, "jobs": jobs}

    def submit(self, settings: Settings, script_path: str) -> dict:
        script = checked_script(settings, script_path)
        result = execute(settings, [binary(settings, "qsub"), str(script)], cwd=script.parent)
        if result["exit_code"] == 0:
            result["job_id"] = result["stdout"].splitlines()[0].strip()
        result["scheduler"] = self.name
        return result

    def job_detail(self, settings: Settings, job_id: str) -> dict:
        job_id = checked_job_id(job_id)
        result = execute(settings, [binary(settings, "qstat"), "-f", job_id], timeout=10)
        result.update({"scheduler": self.name, "job_id": job_id})
        return result

    def cancel(self, settings: Settings, job_id: str) -> dict:
        job_id = checked_job_id(job_id)
        result = execute(settings, [binary(settings, "qdel"), job_id])
        result.update({"scheduler": self.name, "job_id": job_id})
        return result
