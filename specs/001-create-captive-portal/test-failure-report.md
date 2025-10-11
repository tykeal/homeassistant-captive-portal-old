<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->
# Test Failure Report - Captive Portal Addon

**Generated**: 2025-10-06
**Test Run Summary**: 186 tests total - 126 passed, 55 failed, 16 errors

## Executive Summary

The test suite has **71 total issues** (55 failures + 16 errors) affecting ~38% of tests. Analysis shows 5 distinct root causes that can be systematically resolved:

1. **Authentication/Authorization Issues** (35+ failures): Admin API tests missing auth headers
2. **Queue Scheduler API Mismatch** (15+ failures): Tests using old method names
3. **Database Path Configuration** (5+ failures): Unit tests can't create temp DB
4. **Unimplemented CSV Export** (1 failure): Missing feature in audit API
5. **Constructor Signature Changes** (3 errors): Tests using outdated manager initialization

## Detailed Failure Analysis

### Category 1: Authentication Issues (401 Unauthorized)
**Severity**: HIGH
**Impact**: 35+ contract and integration tests
**Root Cause**: Admin API endpoints protected by `require_auth` dependency but tests not providing credentials

#### Affected Test Files:
- `tests/contract/test_grants_api.py`
  - `test_post_grants_provision_from_rental_control` - expects 201, gets 401
  - `test_patch_grants_extend` - expects 200, gets 401
  - `test_patch_grants_extend_nonexistent` - expects 404, gets 401
  - `test_patch_grants_shorten` - expects 200, gets 401
  - `test_patch_grants_shorten_scheduled` - expects 200, gets 401

- `tests/contract/test_theme_api.py`
  - `test_get_theme_current` - expects 200, gets 401
  - `test_get_theme_preview` - expects 200, gets 401

- `tests/integration/test_voucher_grant_coexistence.py`
  - `test_voucher_grant_creation_coexistence` - expects 201, gets 401
  - `test_audit_logging_different_sources` - expects 201, gets 401
  - `test_concurrent_access_different_sources` - expects 201, gets 401
  - `test_voucher_reuse_with_existing_rental_grants` - expects 201, gets 401
  - `test_expiry_handling_mixed_sources` - expects 201, gets 401
  - Plus 20+ more similar failures

#### Fix Strategy:
1. Update `tests/conftest.py` to provide auth fixtures
2. Add authentication headers to affected test requests
3. Consider environment variable `SUPERVISOR_TOKEN` or `API_KEY` for test mode

### Category 2: Queue Scheduler Method Name Mismatch
**Severity**: HIGH
**Impact**: 15+ unit and integration tests
**Root Cause**: Implementation uses `submit_task()` and module-level `shutdown_queue_scheduler()`, tests expect `submit()` and `scheduler.shutdown()`

#### Affected Test Files:
- `tests/unit/test_queue_scaling_logs.py` (7 tests)
  - `test_queue_scaling_up_logs_decision` - AttributeError: no attribute 'submit'
  - `test_queue_scaling_down_logs_decision` - AttributeError: no attribute 'submit'
  - `test_queue_scaling_logs_include_metrics` - AttributeError: no attribute 'get_queue_health'
  - `test_queue_health_endpoint_provides_scaling_info` - AttributeError: no attribute 'submit'
  - `test_queue_scaling_logs_are_searchable` - TypeError: BoundLogger.info() signature issue
  - `test_queue_scheduler_tracks_latency` - AttributeError: no attribute 'submit'
  - `test_queue_scaling_decision_logged_on_threshold_breach` - AttributeError: no attribute 'submit'

- `tests/integration/test_graceful_shutdown.py` (7 tests)
  - All tests fail with: AttributeError: no attribute 'shutdown'

- `tests/performance/test_burst_provisioning.py` (2 tests)
  - Related queue scheduler issues

#### Implementation Reality:
```python
# In src/services/queue_scheduler.py
class AdaptiveQueueScheduler:
    async def submit_task(...)  # NOT submit()

async def shutdown_queue_scheduler():  # Module-level, not method
```

#### Fix Strategy:
1. Add `submit()` method as alias to `submit_task()` in AdaptiveQueueScheduler
2. Add `shutdown()` instance method that calls module-level shutdown
3. OR update all tests to use correct API (`submit_task()` and module-level shutdown)
4. Fix `get_queue_health()` -> `get_queue_status()` mismatch

### Category 3: Database Path Configuration
**Severity**: MEDIUM
**Impact**: 5+ metrics export tests
**Root Cause**: `sqlite3.OperationalError: unable to open database file`

#### Affected Test Files:
- `tests/unit/test_metrics_export.py`
  - `test_metrics_exports_active_grants` - DB init failure
  - `test_metrics_exports_queue_depth` - KeyError: 'metrics' (follows DB failure)
  - `test_metrics_exports_provision_latency_placeholder` - DB init failure
  - `test_metrics_exports_all_grant_states` - KeyError: 'metrics'
  - `test_metrics_exports_queue_workers` - KeyError: 'metrics'
  - `test_metrics_format_prometheus_compatible` - KeyError: 'metrics'
  - `test_health_endpoint_includes_metrics` - assertion failure
  - `test_metrics_real_time_updates` - KeyError: 'metrics'

#### Fix Strategy:
1. Update test fixtures to use in-memory SQLite (`:memory:`) or temp file
2. Ensure DB initialization in test setup
3. Mock database where appropriate for unit tests

### Category 4: Unimplemented CSV Export
**Severity**: LOW
**Impact**: 1 test
**Root Cause**: CSV export endpoint returns JSON instead of CSV

#### Affected Test:
- `tests/contract/test_audit_api.py::test_get_audit_export`
  - Expects: `content-type: text/csv`
  - Gets: `content-type: application/json`
  - Returns: `{"error": "CSV export not yet implemented"}`

#### Fix Strategy:
1. Implement CSV export in `src/api/audit.py::export_audit_events()`
2. Set proper response headers: `Response(content=csv_data, media_type="text/csv")`
3. Convert event list to CSV format using csv module

### Category 5: Constructor Signature Mismatches
**Severity**: MEDIUM
**Impact**: 3 performance tests
**Root Cause**: Test initialization uses outdated constructor arguments

#### Affected Test Files:
- `tests/performance/test_burst_provisioning.py` (2 tests)
  - TypeError: `GrantManager.__init__() got an unexpected keyword argument 'controller'`

- `tests/performance/test_portal_render.py` (3 tests)
  - TypeError: `ThemeManager.__init__() got an unexpected keyword argument 'theme_dir'`

#### Fix Strategy:
1. Review current GrantManager and ThemeManager constructors
2. Update test initialization to match current signatures
3. Use dependency injection patterns from conftest fixtures

## Fix Priority

### Priority 1 (High Impact - Complete First)
- **T062-T065**: Authentication fixes (resolves 35+ failures)
- **T066-T067**: Queue scheduler API compatibility (resolves 15+ failures)

### Priority 2 (Medium Impact)
- **T071-T072**: Database configuration (resolves 5+ failures)
- **T075-T076**: Constructor signature fixes (resolves 3 errors)

### Priority 3 (Low Impact - Nice to Have)
- **T073-T074**: CSV export implementation (resolves 1 failure)

### Priority 4 (Infrastructure)
- **T068-T070**: Update remaining tests to use correct APIs
- **T077-T079**: Documentation and validation

## Success Criteria

- [ ] All 186 tests pass
- [ ] No authentication errors (401s eliminated)
- [ ] Queue scheduler API consistent across codebase
- [ ] Database initialization robust in all test contexts
- [ ] CSV export feature complete
- [ ] Test coverage maintained above 80%
- [ ] CI/CD pipeline green

## Next Steps

1. Review and approve task additions (T062-T079) in tasks.md
2. Begin with Priority 1 fixes (auth and queue scheduler)
3. Run incremental test validation after each fix category
4. Update this report as fixes are applied
5. Document patterns in test README for future developers
