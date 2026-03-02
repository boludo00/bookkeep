"""
APScheduler-based job scheduler for Book Hound.
Handles all background tasks with proper scheduling, persistence, and dynamic updates.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED

logger = structlog.get_logger(__name__)

# Global scheduler instance
scheduler: Optional[AsyncIOScheduler] = None

# Job definitions with their default intervals (in seconds)
JOB_DEFINITIONS = {
    "refresh_seed_data": {
        "default_interval": 24 * 60 * 60,  # 24 hours
        "description": "Fetch new books from Hardcover API",
        "type": "PROCESS",
    },
    "check_processing_requests": {
        "default_interval": 5 * 60,  # 5 minutes
        "description": "Check download tasks for completed requests",
        "type": "PROCESS",
    },
    "sync_from_booklore": {
        "default_interval": 24 * 60 * 60,  # 24 hours
        "description": "Import books from Booklore library",
        "type": "PROCESS",
    },
    "sync_from_audiobookshelf": {
        "default_interval": 24 * 60 * 60,  # 24 hours
        "description": "Import audiobooks from Audiobookshelf library",
        "type": "PROCESS",
    },
    "sync_missing_metadata": {
        "default_interval": 6 * 60 * 60,  # 6 hours
        "description": "Fetch missing book metadata from Hardcover",
        "type": "PROCESS",
    },
    "sync_download_states": {
        "default_interval": 2 * 60,  # 2 minutes
        "description": "Sync download states from download clients",
        "type": "PROCESS",
    },
    "sync_hardcover_lists": {
        "default_interval": 6 * 60 * 60,  # 6 hours
        "description": "Sync Hardcover to-read/list books and auto-request them",
        "type": "PROCESS",
    },
}


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance"""
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler(
            jobstores={'default': MemoryJobStore()},
            job_defaults={
                'coalesce': True,  # Combine missed runs into one
                'max_instances': 1,  # Only one instance of each job at a time
                'misfire_grace_time': 60 * 60,  # 1 hour grace time
            },
            timezone='UTC',  # Explicitly use UTC for consistency
        )
    return scheduler


def start_scheduler():
    """Start the scheduler"""
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        logger.info("scheduler_started")
        
        # Add event listeners
        sched.add_listener(on_job_executed, EVENT_JOB_EXECUTED)
        sched.add_listener(on_job_error, EVENT_JOB_ERROR)
        sched.add_listener(on_job_missed, EVENT_JOB_MISSED)


def on_job_executed(event):
    """Called when a job is executed successfully"""
    logger.info("job_executed", job_id=event.job_id)
    update_job_in_db(event.job_id)


def on_job_error(event):
    """Called when a job raises an exception"""
    logger.error("job_error", job_id=event.job_id, error=str(event.exception))


def on_job_missed(event):
    """Called when a job's execution was missed"""
    logger.warning("job_missed", job_id=event.job_id)


def update_job_in_db(job_name: str):
    """Update job execution times in database after a run"""
    from app.database import SessionLocal
    from app.models import JobSchedule
    
    db = SessionLocal()
    try:
        schedule = db.query(JobSchedule).filter(JobSchedule.job_name == job_name).first()
        if schedule:
            schedule.last_execution = datetime.now()
            # Get next run time from scheduler
            sched = get_scheduler()
            job = sched.get_job(job_name)
            if job and job.next_run_time:
                schedule.next_execution = job.next_run_time.replace(tzinfo=None)
            else:
                interval = schedule.interval_seconds or JOB_DEFINITIONS.get(job_name, {}).get("default_interval", 3600)
                schedule.next_execution = datetime.now() + timedelta(seconds=interval)
            db.commit()
    except Exception as e:
        logger.warning("update_job_in_db_error", job_name=job_name, error=str(e))
        db.rollback()
    finally:
        db.close()


def add_job(job_name: str, func: Callable, interval_seconds: int):
    """Add or replace a job with the given interval"""
    sched = get_scheduler()
    
    # Remove existing job if it exists
    if sched.get_job(job_name):
        sched.remove_job(job_name)
    
    # Add the job with interval trigger
    trigger = IntervalTrigger(seconds=interval_seconds)
    sched.add_job(
        func,
        trigger=trigger,
        id=job_name,
        name=job_name,
        replace_existing=True,
    )
    
    logger.info("job_added", job_name=job_name, interval_seconds=interval_seconds)
    
    # Update next_execution in database
    update_next_execution_in_db(job_name)


def update_next_execution_in_db(job_name: str):
    """Update the next_execution in DB from scheduler"""
    from app.database import SessionLocal
    from app.models import JobSchedule
    
    sched = get_scheduler()
    job = sched.get_job(job_name)
    
    if not job:
        return
    
    db = SessionLocal()
    try:
        schedule = db.query(JobSchedule).filter(JobSchedule.job_name == job_name).first()
        if schedule and job.next_run_time:
            schedule.next_execution = job.next_run_time.replace(tzinfo=None)
            db.commit()
    except Exception as e:
        logger.warning("update_next_execution_error", job_name=job_name, error=str(e))
        db.rollback()
    finally:
        db.close()


def reschedule_job(job_name: str, interval_seconds: int):
    """Reschedule an existing job with a new interval"""
    from app.database import SessionLocal
    from app.models import JobSchedule
    
    sched = get_scheduler()
    job = sched.get_job(job_name)
    
    if job:
        trigger = IntervalTrigger(seconds=interval_seconds)
        sched.reschedule_job(job_name, trigger=trigger)
        
        # Get the new next_run_time from scheduler
        updated_job = sched.get_job(job_name)
        next_run = None
        if updated_job and updated_job.next_run_time:
            next_run = updated_job.next_run_time.replace(tzinfo=None)
        
        logger.info("job_rescheduled", 
                   job_name=job_name, 
                   interval_seconds=interval_seconds,
                   next_run_time=next_run.isoformat() if next_run else None)
        
        # Update database directly
        db = SessionLocal()
        try:
            schedule = db.query(JobSchedule).filter(JobSchedule.job_name == job_name).first()
            if schedule:
                schedule.interval_seconds = interval_seconds
                schedule.next_execution = next_run
                db.commit()
                logger.info("job_db_updated", job_name=job_name, next_execution=next_run)
        except Exception as e:
            logger.error("job_db_update_failed", job_name=job_name, error=str(e))
            db.rollback()
        finally:
            db.close()
    else:
        logger.warning("job_not_found_for_reschedule", job_name=job_name)


def get_job_info(job_name: str) -> Optional[Dict[str, Any]]:
    """Get information about a scheduled job"""
    sched = get_scheduler()
    
    if not sched.running:
        logger.debug("scheduler_not_running")
        return None
    
    job = sched.get_job(job_name)
    
    if not job:
        logger.debug("job_not_in_scheduler", job_name=job_name)
        return None
    
    next_run = job.next_run_time
    if next_run:
        # Convert to naive datetime
        next_run = next_run.replace(tzinfo=None)
    
    # Get interval from trigger
    interval = None
    if hasattr(job.trigger, 'interval'):
        interval = int(job.trigger.interval.total_seconds())
    
    return {
        "name": job_name,
        "next_run_time": next_run.isoformat() if next_run else None,
        "interval_seconds": interval,
    }


def get_all_jobs() -> Dict[str, Dict[str, Any]]:
    """Get information about all scheduled jobs"""
    sched = get_scheduler()
    jobs = {}
    
    for job in sched.get_jobs():
        info = get_job_info(job.id)
        if info:
            jobs[job.id] = info
    
    return jobs


def run_job_now(job_name: str):
    """Trigger a job to run immediately"""
    sched = get_scheduler()
    job = sched.get_job(job_name)
    
    if job:
        # Modify the job to run now
        sched.modify_job(job_name, next_run_time=datetime.now())
        logger.info("job_triggered_now", job_name=job_name)
    else:
        logger.warning("job_not_found_for_run", job_name=job_name)


def pause_job(job_name: str):
    """Pause a job"""
    sched = get_scheduler()
    sched.pause_job(job_name)
    logger.info("job_paused", job_name=job_name)


def resume_job(job_name: str):
    """Resume a paused job"""
    sched = get_scheduler()
    sched.resume_job(job_name)
    logger.info("job_resumed", job_name=job_name)


async def initialize_jobs():
    """Initialize all jobs from database or defaults"""
    from app.database import SessionLocal
    from app.models import JobSchedule
    from app.tasks import (
        refresh_seed_data,
        check_processing_requests,
        sync_from_booklore,
        sync_from_audiobookshelf,
        sync_missing_metadata,
        sync_download_states,
        sync_hardcover_lists,
    )

    # Map job names to their async functions
    job_functions = {
        "refresh_seed_data": refresh_seed_data,
        "check_processing_requests": check_processing_requests,
        "sync_from_booklore": sync_from_booklore,
        "sync_from_audiobookshelf": sync_from_audiobookshelf,
        "sync_missing_metadata": sync_missing_metadata,
        "sync_download_states": sync_download_states,
        "sync_hardcover_lists": sync_hardcover_lists,
    }
    
    db = SessionLocal()
    try:
        for job_name, definition in JOB_DEFINITIONS.items():
            # Get interval from database or use default
            schedule = db.query(JobSchedule).filter(JobSchedule.job_name == job_name).first()
            
            if schedule:
                interval = schedule.interval_seconds
            else:
                interval = definition["default_interval"]
                # Create schedule entry
                schedule = JobSchedule(
                    job_name=job_name,
                    interval_seconds=interval,
                    is_enabled=True,
                )
                db.add(schedule)
            
            # Add job to scheduler
            func = job_functions.get(job_name)
            if func:
                add_job(job_name, func, interval)
                logger.info("job_initialized", job_name=job_name, interval_seconds=interval)
        
        db.commit()
    except Exception as e:
        logger.error("initialize_jobs_error", error=str(e))
        db.rollback()
    finally:
        db.close()

