"""Scheduler backend selection and common operations."""

from __future__ import annotations

from ..config import Settings
from .base import Scheduler
from .pbs import PBSScheduler
from .slurm import SlurmScheduler


def get_scheduler(settings: Settings) -> Scheduler:
    """Select one configured scheduler; never probe the cluster implicitly."""
    if settings.scheduler_type == "slurm":
        return SlurmScheduler()
    if settings.scheduler_type == "pbs":
        return PBSScheduler()
    raise ValueError("No supported scheduler configured")
