<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->
# Test Fix Quick Reference

## Quick Stats
- **Total Tests**: 186
- **Passing**: 126 (68%)
- **Failing**: 55 (30%)
- **Errors**: 16 (9%)
- **Pass Rate**: 68% → Target: 100%

## Fix Order (by impact)

### 1️⃣ Authentication Fixes → 35+ tests fixed
**Files to modify**:
- `addon/tests/conftest.py` - Add auth fixture
- `addon/tests/contract/test_grants_api.py` - Add headers
- `addon/tests/contract/test_theme_api.py` - Add headers
- `addon/tests/integration/test_voucher_grant_coexistence.py` - Add headers

**Implementation**:
```python
# In conftest.py
@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test_token"}

# In tests, change:
response = test_client.post("/api/grants", json=data)
# To:
response = test_client.post("/api/grants", json=data, headers=auth_headers)
```

**OR** configure test client globally:
```python
# In conftest.py
@pytest.fixture
def test_client():
    # Set environment variable to bypass auth in tests
    os.environ["SUPERVISOR_TOKEN"] = "test_token"
    # OR modify auth.py to check for TEST_MODE
```

### 2️⃣ Queue Scheduler API → 15+ tests fixed
**Files to modify**:
- `addon/src/services/queue_scheduler.py` - Add compatibility methods
- OR `addon/tests/unit/test_queue_scaling_logs.py` - Update test calls
- OR `addon/tests/integration/test_graceful_shutdown.py` - Update test calls

**Option A - Add compatibility layer** (recommended):
```python
# In AdaptiveQueueScheduler class
async def submit(self, *args, **kwargs):
    """Alias for submit_task for backward compatibility."""
    return await self.submit_task(*args, **kwargs)

async def shutdown(self, timeout: int = 30):
    """Instance method for graceful shutdown."""
    await shutdown_queue_scheduler()

def get_queue_health(self):
    """Alias for get_queue_status."""
    return self.get_queue_status()
```

**Option B - Update all tests**:
```python
# Change all occurrences:
scheduler.submit() → scheduler.submit_task()
scheduler.shutdown() → await shutdown_queue_scheduler()
scheduler.get_queue_health() → scheduler.get_queue_status()
```

### 3️⃣ Database Configuration → 5+ tests fixed
**Files to modify**:
- `addon/tests/conftest.py` - Add DB fixture
- `addon/tests/unit/test_metrics_export.py` - Use fixture

**Implementation**:
```python
# In conftest.py
@pytest.fixture
async def test_db():
    """Provide in-memory test database."""
    import tempfile
    db_path = tempfile.mktemp(suffix=".db")
    # Or use ":memory:" for pure in-memory

    # Initialize database
    from src.storage.database import init_database
    await init_database(db_path)

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)
```

### 4️⃣ Constructor Signature Fixes → 3 tests fixed
**Files to modify**:
- `addon/tests/performance/test_burst_provisioning.py`
- `addon/tests/performance/test_portal_render.py`

**Check current signatures**:
```bash
grep -A10 "def __init__" addon/src/services/grant_manager.py
grep -A10 "def __init__" addon/src/services/theme_manager.py
```

**Update test initialization to match**

### 5️⃣ CSV Export → 1 test fixed
**Files to modify**:
- `addon/src/api/audit.py` - Implement CSV export

**Implementation**:
```python
from fastapi.responses import Response
import csv
import io

@router.get("/export")
async def export_audit_events(...):
    events = await audit_logger.get_events(...)

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=['timestamp', 'event_type', ...])
        writer.writeheader()
        for event in events:
            writer.writerow(event.model_dump())

        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=audit.csv"}
        )
    # else json...
```

## Running Tests After Each Fix

```bash
# Run specific test file
cd addon
.venv/bin/pytest tests/contract/test_grants_api.py -v

# Run by category
.venv/bin/pytest tests/contract/ -v
.venv/bin/pytest tests/unit/test_queue_scaling_logs.py -v
.venv/bin/pytest tests/unit/test_metrics_export.py -v

# Full suite
.venv/bin/pytest -v

# With coverage
.venv/bin/pytest --cov=src --cov-report=term-missing
```

## Validation Checklist

After each fix category:
- [ ] Run affected tests - all pass
- [ ] Run full suite - no regressions
- [ ] Check coverage maintained
- [ ] Update tasks.md to mark completed
- [ ] Commit with clear message

## Estimated Time

- T062-T065 (Auth): 1-2 hours
- T066-T067 (Queue API): 30 min - 1 hour
- T068-T070 (Update tests): 1 hour
- T071-T072 (Database): 30 min
- T073-T074 (CSV export): 30 min
- T075-T076 (Constructors): 30 min
- T077-T079 (Docs/validation): 1 hour

**Total**: 5-7 hours
