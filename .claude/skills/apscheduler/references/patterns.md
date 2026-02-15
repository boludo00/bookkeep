# APScheduler Patterns Reference

## Contents
- Scheduler Configuration
- Job Registration Pattern
- Database Sync Pattern
- Event Listeners
- Anti-Patterns

## Scheduler Configuration

The global scheduler is configured with these critical settings:

```python
# backend/app/scheduler.py:49-62
scheduler = AsyncIOScheduler(
    jobstores={'default': MemoryJobStore()},
    job_defaults={
        'coalesce': True,       # Combine missed runs into one
        'max_instances': 1,     # Prevent concurrent job runs
        'misfire_grace_time': 60 * 60,  # 1 hour grace for missed jobs
    },
    timezone='UTC',
)
```

**Why these settings matter:**
- `coalesce=True`: If the server restarts and 5 job executions were missed, only ONE run happens
- `max_instances=1`: A slow job won't spawn duplicates on the next interval
- `misfire_grace_time`: Jobs missed by more than 1 hour are skipped entirely

## Job Registration Pattern

Jobs are registered at app startup with DB-backed intervals:

```python
# backend/app/scheduler.py:280-330
async def initialize_jobs():
    from app.tasks import refresh_seed_data, sync_from_booklore
    
    job_functions = {
        "refresh_seed_data": refresh_seed_data,
        "sync_from_booklore": sync_from_booklore,
    }
    
    db = SessionLocal()
    try:
        for job_name, definition in JOB_DEFINITIONS.items():
            schedule = db.query(JobSchedule).filter(
                JobSchedule.job_name == job_name
            ).first()
            
            interval = schedule.interval_seconds if schedule else definition["default_interval"]
            
            if not schedule:
                schedule = JobSchedule(
                    job_name=job_name,
                    interval_seconds=interval,
                    is_enabled=True,
                )
                db.add(schedule)
            
            func = job_functions.get(job_name)
            if func:
                add_job(job_name, func, interval)
        
        db.commit()
    finally:
        db.close()
```

## Database Sync Pattern

APScheduler and the database must stay synchronized. The `add_job` function handles this:

```python
# backend/app/scheduler.py:120-141
def add_job(job_name: str, func: Callable, interval_seconds: int):
    sched = get_scheduler()
    
    # Remove existing job first
    if sched.get_job(job_name):
        sched.remove_job(job_name)
    
    # Add with new interval
    trigger = IntervalTrigger(seconds=interval_seconds)
    sched.add_job(
        func,
        trigger=trigger,
        id=job_name,
        name=job_name,
        replace_existing=True,
    )
    
    # Sync next_execution to database
    update_next_execution_in_db(job_name)
```

## Event Listeners

Event listeners track job outcomes:

```python
# backend/app/scheduler.py:73-91
sched.add_listener(on_job_executed, EVENT_JOB_EXECUTED)
sched.add_listener(on_job_error, EVENT_JOB_ERROR)
sched.add_listener(on_job_missed, EVENT_JOB_MISSED)

def on_job_executed(event):
    logger.info("job_executed", job_id=event.job_id)
    update_job_in_db(event.job_id)  # Updates last_execution, next_execution

def on_job_error(event):
    logger.error("job_error", job_id=event.job_id, error=str(event.exception))

def on_job_missed(event):
    logger.warning("job_missed", job_id=event.job_id)
```

## Anti-Patterns

### WARNING: Sync DB Operations in Async Jobs

**The Problem:**

```python
# BAD - Creates new session inside async function without proper cleanup
async def my_job():
    db = SessionLocal()  # Sync session in async context
    results = db.query(Book).all()  # Blocking call
    # ... exception here leaves session unclosed
```

**Why This Breaks:**
1. Blocking `db.query()` blocks the event loop
2. Unclosed sessions cause connection pool exhaustion
3. No transaction rollback on exceptions

**The Fix:**

```python
# GOOD - Proper session management
async def my_job():
    db: Session = SessionLocal()
    try:
        results = db.query(Book).all()
        # Process results
        db.commit()
    except Exception as e:
        logger.error("my_job_error", error=str(e))
        db.rollback()
    finally:
        db.close()
```

### WARNING: Missing Job in job_functions Dict

**The Problem:**

```python
# Added to JOB_DEFINITIONS but forgot job_functions mapping
JOB_DEFINITIONS = {
    "my_new_job": {"default_interval": 3600, "type": "PROCESS"},
}

# In initialize_jobs():
job_functions = {
    # "my_new_job": my_new_job,  # Missing!
}
```

**Why This Breaks:**
- Job schedule is created in DB but never registered with scheduler
- `get_job_info()` returns None, causing UI errors
- No errors at startup - fails silently

**The Fix:**
Always update both `JOB_DEFINITIONS` and `job_functions` together.

### WARNING: Timezone Mismatch

**The Problem:**

```python
# BAD - Using local time
schedule.last_execution = datetime.now()  # Local timezone
schedule.next_execution = datetime.now() + timedelta(seconds=interval)
```

**Why This Breaks:**
- Scheduler uses UTC internally
- Job times display incorrectly in UI
- Rescheduling calculations are wrong after DST changes

**The Fix:**

```python
# GOOD - Always use UTC
from datetime import timezone
schedule.last_execution = datetime.now(timezone.utc)
schedule.next_execution = datetime.now(timezone.utc) + timedelta(seconds=interval)