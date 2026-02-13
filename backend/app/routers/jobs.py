from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel
import structlog
import uuid

from app import database, models
from app.auth import require_admin

logger = structlog.get_logger()

router = APIRouter()

# In-memory tracking of running jobs
# Format: {run_id: {"job_name": str, "status": str, "started_at": datetime, "completed_at": datetime, "error": str}}
_running_jobs: Dict[str, Dict[str, Any]] = {}


# Default job configurations
DEFAULT_JOBS = {
    "refresh_seed_data": {"interval_seconds": 24 * 60 * 60, "type": "PROCESS"},
    "check_processing_requests": {"interval_seconds": 5 * 60, "type": "PROCESS"},
    "sync_from_booklore": {"interval_seconds": 24 * 60 * 60, "type": "PROCESS"},
    "sync_from_audiobookshelf": {"interval_seconds": 24 * 60 * 60, "type": "PROCESS"},
    "sync_missing_metadata": {"interval_seconds": 6 * 60 * 60, "type": "PROCESS"},
}

# Available interval options (in seconds) for the dropdown
INTERVAL_OPTIONS = [
    {"value": 5 * 60, "label": "Every 5 minutes"},
    {"value": 15 * 60, "label": "Every 15 minutes"},
    {"value": 30 * 60, "label": "Every 30 minutes"},
    {"value": 60 * 60, "label": "Every 1 hour"},
    {"value": 3 * 60 * 60, "label": "Every 3 hours"},
    {"value": 6 * 60 * 60, "label": "Every 6 hours"},
    {"value": 12 * 60 * 60, "label": "Every 12 hours"},
    {"value": 24 * 60 * 60, "label": "Every 24 hours"},
    {"value": 48 * 60 * 60, "label": "Every 2 days"},
    {"value": 7 * 24 * 60 * 60, "label": "Every 7 days"},
]


class JobUpdateRequest(BaseModel):
    interval_seconds: int


class JobResponse(BaseModel):
    name: str
    type: str
    interval_seconds: int
    last_execution: Optional[str] = None
    next_execution: Optional[str] = None
    is_enabled: bool = True


def ensure_job_schedules_exist(db: Session):
    """Ensure all default jobs exist in the database"""
    for job_name, config in DEFAULT_JOBS.items():
        existing = db.query(models.JobSchedule).filter(
            models.JobSchedule.job_name == job_name
        ).first()
        
        if not existing:
            schedule = models.JobSchedule(
                job_name=job_name,
                interval_seconds=config["interval_seconds"],
                is_enabled=True,
            )
            db.add(schedule)
    
    try:
        db.commit()
    except Exception:
        db.rollback()


def get_job_schedule(job_name: str, db: Session) -> Optional[models.JobSchedule]:
    """Get job schedule from database"""
    return db.query(models.JobSchedule).filter(
        models.JobSchedule.job_name == job_name
    ).first()


def get_job_info(job_name: str, db: Session) -> Dict[str, Any]:
    """Get information about a job"""
    import json
    from app.scheduler import get_job_info as get_scheduler_job_info
    
    # First, try to get accurate info from the scheduler
    scheduler_info = get_scheduler_job_info(job_name)
    
    # Refresh the database session to get latest values
    db.expire_all()
    schedule = get_job_schedule(job_name, db)
    
    state = None
    if schedule:
        # Use scheduler's interval if available (most current)
        if scheduler_info and scheduler_info.get("interval_seconds"):
            interval_seconds = scheduler_info["interval_seconds"]
        else:
            interval_seconds = schedule.interval_seconds
        last_execution = schedule.last_execution
        is_enabled = schedule.is_enabled
        if schedule.state_json:
            try:
                state = json.loads(schedule.state_json)
            except:
                state = None
    else:
        config = DEFAULT_JOBS.get(job_name, {})
        interval_seconds = scheduler_info.get("interval_seconds") if scheduler_info else config.get("interval_seconds", 3600)
        last_execution = None
        is_enabled = True
    
    # Get next_execution from scheduler (most accurate) or fall back to calculation
    if scheduler_info and scheduler_info.get("next_run_time"):
        next_execution = datetime.fromisoformat(scheduler_info["next_run_time"])
    elif schedule and schedule.next_execution:
        next_execution = schedule.next_execution
    elif last_execution:
        next_execution = last_execution + timedelta(seconds=interval_seconds)
    elif interval_seconds > 0:
        next_execution = datetime.now()
    else:
        next_execution = None
    
    return {
        "name": job_name,
        "type": DEFAULT_JOBS.get(job_name, {}).get("type", "PROCESS"),
        "interval_seconds": interval_seconds,
        "last_execution": (last_execution.isoformat() + "Z") if last_execution else None,
        "next_execution": (next_execution.isoformat() + "Z") if next_execution else None,
        "is_enabled": is_enabled,
        "state": state,  # Job-specific state (e.g., offset for seed data)
    }


def update_job_execution_time(job_name: str, db: Session):
    """Update the last execution time for a job"""
    schedule = get_job_schedule(job_name, db)
    if schedule:
        schedule.last_execution = datetime.now()
        db.add(schedule)
        db.commit()


# Test endpoint
@router.get("/test")
async def test_jobs():
    """Test endpoint to verify jobs router is working"""
    return {"status": "ok", "message": "Jobs router is working"}


@router.get("/intervals")
async def list_interval_options(
    current_user = Depends(require_admin)
):
    """List available interval options for job scheduling"""
    return INTERVAL_OPTIONS


@router.get("/", response_model=List[Dict[str, Any]])
async def list_jobs(
    db: Session = Depends(database.get_db),
    current_user = Depends(require_admin)
):
    """List all scheduled jobs"""
    ensure_job_schedules_exist(db)
    
    jobs = []
    for job_name in DEFAULT_JOBS.keys():
        job_info = get_job_info(job_name, db)
        jobs.append(job_info)
    return jobs


@router.get("/{job_name}")
async def get_job(
    job_name: str,
    db: Session = Depends(database.get_db),
    current_user = Depends(require_admin)
):
    """Get details of a specific job"""
    if job_name not in DEFAULT_JOBS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_name}' not found"
        )
    
    return get_job_info(job_name, db)


@router.put("/{job_name}")
async def update_job(
    job_name: str,
    update: JobUpdateRequest,
    db: Session = Depends(database.get_db),
    current_user = Depends(require_admin)
):
    """Update job schedule (interval)"""
    if job_name not in DEFAULT_JOBS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_name}' not found"
        )
    
    # Validate interval
    valid_intervals = [opt["value"] for opt in INTERVAL_OPTIONS]
    if update.interval_seconds not in valid_intervals:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid interval. Must be one of: {valid_intervals}"
        )
    
    ensure_job_schedules_exist(db)
    
    # Reschedule the job in APScheduler (also updates database)
    from app.scheduler import reschedule_job
    reschedule_job(job_name, update.interval_seconds)
    
    # Refresh session to get updated values
    db.expire_all()
    
    logger.info("job_schedule_updated",
               job_name=job_name,
               interval_seconds=update.interval_seconds,
               user_id=current_user.id)
    
    return get_job_info(job_name, db)


@router.post("/{job_name}/run")
async def run_job(
    job_name: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user = Depends(require_admin)
):
    """Manually trigger a job"""
    if job_name not in DEFAULT_JOBS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job '{job_name}' not found"
        )
    
    # Trigger the job via APScheduler
    from app.scheduler import run_job_now
    run_job_now(job_name)
    
    # Import job functions for the background task wrapper
    from app.tasks import refresh_seed_data, check_processing_requests, sync_from_booklore, sync_from_audiobookshelf, sync_missing_metadata

    job_functions = {
        "refresh_seed_data": refresh_seed_data,
        "check_processing_requests": check_processing_requests,
        "sync_from_booklore": sync_from_booklore,
        "sync_from_audiobookshelf": sync_from_audiobookshelf,
        "sync_missing_metadata": sync_missing_metadata,
    }
    
    job_func = job_functions.get(job_name)
    if not job_func:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job function for '{job_name}' not found"
        )
    
    # Generate a unique run ID
    run_id = str(uuid.uuid4())
    started_at = datetime.now()
    
    # Track this job run
    _running_jobs[run_id] = {
        "job_name": job_name,
        "status": "running",
        "started_at": started_at,
        "completed_at": None,
        "error": None,
    }
    
    # Create wrapper to track execution time and status
    async def tracked_job():
        try:
            await job_func()
            _running_jobs[run_id]["status"] = "completed"
            _running_jobs[run_id]["completed_at"] = datetime.now()
            logger.info("job_completed", job_name=job_name, run_id=run_id)
        except Exception as e:
            _running_jobs[run_id]["status"] = "failed"
            _running_jobs[run_id]["completed_at"] = datetime.now()
            _running_jobs[run_id]["error"] = str(e)
            logger.error("job_failed", job_name=job_name, run_id=run_id, error=str(e))
        finally:
            # Update execution time after job completes
            new_db = database.SessionLocal()
            try:
                update_job_execution_time(job_name, new_db)
            finally:
                new_db.close()
            
            # Clean up old job runs (keep last 100)
            if len(_running_jobs) > 100:
                oldest_keys = sorted(_running_jobs.keys(), 
                                    key=lambda k: _running_jobs[k]["started_at"])[:50]
                for k in oldest_keys:
                    del _running_jobs[k]
    
    # Update execution time when starting
    update_job_execution_time(job_name, db)
    
    # Run job in background
    background_tasks.add_task(tracked_job)
    
    logger.info("job_triggered_manually", job_name=job_name, run_id=run_id, user_id=current_user.id)
    
    return {
        "message": f"Job '{job_name}' has been triggered",
        "job_name": job_name,
        "run_id": run_id,
        "triggered_at": started_at.isoformat()
    }


@router.get("/status/{run_id}")
async def get_job_status(
    run_id: str,
    current_user = Depends(require_admin)
):
    """Check the status of a job run"""
    if run_id not in _running_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job run '{run_id}' not found"
        )
    
    job_run = _running_jobs[run_id]
    
    # Calculate duration
    duration_seconds = None
    if job_run["started_at"]:
        end_time = job_run["completed_at"] or datetime.now()
        duration_seconds = (end_time - job_run["started_at"]).total_seconds()
    
    return {
        "run_id": run_id,
        "job_name": job_run["job_name"],
        "status": job_run["status"],
        "started_at": job_run["started_at"].isoformat() if job_run["started_at"] else None,
        "completed_at": job_run["completed_at"].isoformat() if job_run["completed_at"] else None,
        "duration_seconds": duration_seconds,
        "error": job_run["error"],
    }
