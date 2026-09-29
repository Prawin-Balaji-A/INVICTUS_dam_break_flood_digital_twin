import threading
import time
from typing import Dict, Any, Callable, List
from enum import Enum
from pydantic import BaseModel

class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    PREPROCESSING = "PREPROCESSING"
    RUNNING = "RUNNING"
    POSTPROCESSING = "POSTPROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class JobInfo(BaseModel):
    id: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    message: str = "Job initialized"
    logs: List[str] = []
    error: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0
    result_metadata: Dict[str, Any] = {}

class JobManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(JobManager, cls).__new__(cls)
                cls._instance.jobs: Dict[str, JobInfo] = {}
        return cls._instance

    def create_job(self, job_id: str) -> JobInfo:
        with self._lock:
            job = JobInfo(id=job_id, started_at=time.time())
            self.jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> JobInfo | None:
        return self.jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        status: JobStatus | None = None,
        progress: float | None = None,
        message: str | None = None,
        log_entry: str | None = None,
        error: str | None = None,
        result_metadata: Dict[str, Any] | None = None
    ):
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = max(0.0, min(100.0, progress))
            if message is not None:
                job.message = message
            if log_entry is not None:
                timestamp = time.strftime("%H:%M:%S")
                job.logs.append(f"[{timestamp}] {log_entry}")
            if error is not None:
                job.error = error
                job.status = JobStatus.FAILED
            if result_metadata is not None:
                job.result_metadata.update(result_metadata)
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                job.completed_at = time.time()

    def run_in_background(self, job_id: str, target: Callable, *args, **kwargs):
        def worker():
            try:
                self.update_job(job_id, status=JobStatus.PREPROCESSING, progress=5.0, message="Starting preparation", log_entry="Job execution started in background")
                target(job_id, *args, **kwargs)
            except Exception as e:
                import traceback
                err_msg = f"{str(e)}\n{traceback.format_exc()}"
                self.update_job(job_id, error=err_msg, message=f"Failed: {str(e)}", log_entry=f"EXCEPTION: {str(e)}")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

job_manager = JobManager()
