"""Small persistent background-job manager for the local dashboard."""
from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable

from core.db.office_sqlite import OfficeSQLite

logger = logging.getLogger(__name__)


class JobManager:
    """Runs expensive local-model work away from HTTP request threads.

    The executor defaults to one worker so local CPU/GPU inference is not
    thrashed by competing jobs. Job metadata is stored in SQLite and survives
    dashboard refreshes; interrupted work is reported honestly after restart.
    """

    def __init__(self, max_workers: int = 1):
        self.db = OfficeSQLite()
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="aimaos-job")
        self._lock = threading.Lock()
        self.db.interrupt_unfinished_jobs()
        try:
            from core.security import load_security_config
            retention_days = int(load_security_config().get("privacy", {}).get("log_retention_days", 30))
            self.db.prune_runtime_history(retention_days)
        except Exception:  # diagnostics must not prevent the job service from starting
            logger.exception("Could not prune expired dashboard job history")

    def submit(self, kind: str, title: str, function: Callable[[], object]) -> str:
        job_id = f"job_{uuid.uuid4().hex}"
        self.db.create_job(job_id, kind, title)

        def runner():
            self.db.update_job(job_id, status="running", started_at=datetime.now().isoformat())
            try:
                result = function()
                self.db.update_job(
                    job_id,
                    status="completed",
                    result=result,
                    completed_at=datetime.now().isoformat(),
                )
            except Exception as exc:  # noqa: BLE001 - boundary records errors for the UI
                logger.exception("Dashboard job %s failed", job_id)
                from core.privacy import redact_sensitive
                self.db.update_job(
                    job_id,
                    status="failed",
                    error=redact_sensitive(str(exc)),
                    completed_at=datetime.now().isoformat(),
                )

        self.executor.submit(runner)
        return job_id

    def get(self, job_id: str):
        return self.db.get_job(job_id)

    def list(self, limit: int = 50):
        return self.db.list_jobs(limit=limit)


_manager = None
_manager_lock = threading.Lock()


def get_job_manager() -> JobManager:
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = JobManager()
        return _manager
