# APScheduler Workflows Reference

## Contents
- Adding a New Background Job
- Changing Job Intervals at Runtime
- Job State Persistence
- Debugging Job Issues

## Adding a New Background Job

Copy this checklist and track progress:
- [ ] Step 1: Add job definition to `JOB_DEFINITIONS` in `scheduler.py`
- [ ] Step 2: Implement async job function in `tasks.py`
- [ ] Step 3: Add function mapping in `initialize_jobs()` in `scheduler.py`
- [ ] Step 4: Add to `DEFAULT_JOBS` in `routers/jobs.py` for API exposure
- [ ] Step 5: Add to `job_functions` in `routers/jobs.py` run endpoint

### Step 1: Define the Job

```python
# backend/app/scheduler.py
JOB_DEFINITIONS = {
    "cleanup_old_downloads": {
        "default_interval": 24 * 60 * 60,  # 24 hours
        "description": "Remove completed downloads older than 30 days",
        "type": "PROCESS",
    },
}
```

### Step 2: Implement the Function

```python
# backend/app/tasks.py
async def cleanup_old_downloads():
    """Remove old completed download tasks"""
    from app.models import DownloadTask
    
    db: Session = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        deleted = db.query(DownloadTask).filter(
            DownloadTask.state == 'complete',
            DownloadTask.completed_at < cutoff
        ).delete()
        
        db.commit()
        logger.info("cleanup_old_downloads_complete", deleted=deleted)
    except Exception as e:
        logger.error("cleanup_old_downloads_error", error=str(e))
        db.rollback()
    finally:
        db.close()
```

### Step 3: Register in Scheduler

```python
# backend/app/scheduler.py - in initialize_jobs()
from app.tasks import cleanup_old_downloads

job_functions = {
    "cleanup_old_downloads": cleanup_old_downloads,
    # ... other jobs
}
```

### Step 4-5: Expose via API

```python
# backend/app/routers/jobs.py
DEFAULT_JOBS = {
    "cleanup_old_downloads": {"interval_seconds": 24 * 60 * 60, "type": "PROCESS"},
}

# In run_job endpoint, add to job_functions dict
job_functions = {
    "cleanup_old_downloads": cleanup_old_downloads,
}
```

## Changing Job Intervals at Runtime

The frontend calls `PUT /api/jobs/{job_name}` which triggers:

```python
# backend/app/routers/jobs.py:195-231
@router.put("/{job_name}")
async def update_job(job_name: str, update: JobUpdateRequest, db: Session):
    # Validate against allowed intervals
    valid_intervals = [opt["value"] for opt in INTERVAL_OPTIONS]
    if update.interval_seconds not in valid_intervals:
        raise HTTPException(status_code=400, detail="Invalid interval")
    
    # This updates both scheduler AND database
    from app.scheduler import reschedule_job
    reschedule_job(job_name, update.interval_seconds)
    
    return get_job_info(job_name, db)
```

The `reschedule_job` function handles the dual update:

```python
# backend/app/scheduler.py:168-206
def reschedule_job(job_name: str, interval_seconds: int):
    sched = get_scheduler()
    job = sched.get_job(job_name)
    
    if job:
        trigger = IntervalTrigger(seconds=interval_seconds)
        sched.reschedule_job(job_name, trigger=trigger)
        
        # Get new next_run_time
        updated_job = sched.get_job(job_name)
        next_run = updated_job.next_run_time.replace(tzinfo=None) if updated_job else None
        
        # Update database
        db = SessionLocal()
        try:
            schedule = db.query(JobSchedule).filter(
                JobSchedule.job_name == job_name
            ).first()
            if schedule:
                schedule.interval_seconds = interval_seconds
                schedule.next_execution = next_run
                db.commit()
        finally:
            db.close()
```

## Job State Persistence

Jobs can persist state between runs using `state_json`:

```python
# backend/app/tasks.py:68-159 - refresh_seed_data example
async def refresh_seed_data():
    import json
    
    db = SessionLocal()
    try:
        job = db.query(JobSchedule).filter(
            JobSchedule.job_name == "refresh_seed_data"
        ).first()
        
        # Load state
        state = {}
        if job and job.state_json:
            try:
                state = json.loads(job.state_json)
            except:
                state = {}
        
        current_offset = state.get("offset", 0)
        
        # Do work using offset...
        
        # Save updated state
        state["offset"] = current_offset + batch_size
        state["last_inserted"] = inserted
        
        if job:
            job.state_json = json.dumps(state)
        
        db.commit()
    finally:
        db.close()
```

## Debugging Job Issues

### Check Scheduler Status

```python
from app.scheduler import get_all_jobs
jobs = get_all_jobs()
# Returns: {"job_name": {"next_run_time": "...", "interval_seconds": ...}}
```

### Check Job in Database

```sql
SELECT job_name, interval_seconds, last_execution, next_execution, state_json 
FROM job_schedules;
```

### Common Issues

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Job never runs | Not in `job_functions` dict | Add mapping in `initialize_jobs()` |
| Job runs but no DB update | Missing `db.commit()` | Add commit before close |
| Job times wrong in UI | Timezone mismatch | Use `datetime.now(timezone.utc)` |
| Job runs multiple times | `max_instances > 1` | Keep `max_instances=1` |
| Stale data after restart | MemoryJobStore | Normal - DB intervals reload at startup |

### Iterate-Until-Pass Validation

When adding a new job:

1. Add the job definition and function
2. Restart the server: `uvicorn main:app --reload`
3. Check logs for: `job_initialized job_name=your_job_name`
4. If missing, check `job_functions` mapping and repeat step 1
5. Verify in API: `GET /api/jobs/` should list your job
6. Trigger manually: `POST /api/jobs/your_job_name/run`
7. Check logs for job completion or error