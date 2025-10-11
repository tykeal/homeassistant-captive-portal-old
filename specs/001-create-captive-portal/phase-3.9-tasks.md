<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Phase 3.9: Test Isolation and Remaining Fixes

**Status**: In Progress
**Test Results (Target)**: 186 passing, 0 failing (100% pass rate)
**Current Results**: 178 passing, 2 failing (metrics), 6 blocked (controller tests)
**Progress**: 2/8 tasks completed (25%)

## Problem Summary

Phase 3.8 revealed a critical test isolation issue: **all integration tests pass when run individually or in small groups, but 28 tests fail when run as part of the full test suite**. This indicates state leakage between tests rather than actual code failures.

## Root Cause Analysis

### Evidence

Tests with 100% pass rate individually, 0% in full suite:
- `test_voucher_grant_coexistence.py`: 6/6 pass alone, 0/6 in suite (401 auth errors)
- `test_portal_scenarios.py`: 5/5 pass alone, 0/5 in suite (401 or KeyError)
- `test_queue_scaling.py`: 3/3 pass alone, 0/3 in suite (401 errors)
- `test_theme_fallback.py`: 7/7 pass alone, 0/7 in suite (401 errors)

### Suspected Issues

1. **API Key Environment Variable Leakage**
   - Symptom: 401 Unauthorized errors in full suite
   - Hypothesis: `CAPTIVE_PORTAL_API_KEY` not properly set/reset between tests
   - Location: `conftest.py` lines 144, 172

2. **Database State Pollution**
   - Symptom: Grants/vouchers from previous tests affecting later tests
   - Hypothesis: temp_database fixture not creating fresh DB per test
   - Location: `conftest.py` lines 82-86, 141-155

3. **Global Config Module State**
   - Symptom: Config from one test affecting next test
   - Hypothesis: `config_module.config` not properly reset
   - Location: `conftest.py` lines 135-138, 167-168

4. **Database Manager Singleton**
   - Symptom: Database connections not reset between tests
   - Hypothesis: `db_module._db_manager` global state persists
   - Location: `conftest.py` lines 147, 168

5. **Test Client Async Context**
   - Symptom: FastAPI app state persisting across tests
   - Hypothesis: TestClient context not fully cleaned up
   - Location: `conftest.py` lines 163-164

## Phase 3.9 Tasks

### Category 1: Critical Test Infrastructure Fixes

**Priority: CRITICAL** - Blocks all other work

- [ ] T113: Fix environment variable cleanup in test_client fixture
  - Issue: `CAPTIVE_PORTAL_API_KEY` may not be properly set for each test
  - Root cause: Environment variable cleanup in finally block might fail
  - Files affected: `tests/conftest.py`
  - Fix approach:
    1. Move env var setup earlier in fixture
    2. Add explicit assertion that key is set
    3. Use try/finally to guarantee cleanup
    4. Add autouse fixture to verify env state between tests
  - Impact: Should fix 21/28 failures (all 401 errors)
  - Estimated time: 1 hour

- [ ] T114: Ensure database isolation between tests
  - Issue: Database state may persist across tests
  - Root cause: temp_database creates file but may not reset connection pool
  - Files affected: `tests/conftest.py`, `src/storage/database.py`
  - Fix approach:
    1. Force database close after each test
    2. Delete database file in finally block
    3. Reset connection pool state
    4. Add autouse fixture to verify DB is clean
  - Impact: Ensures no data pollution
  - Estimated time: 2 hours

- [ ] T115: Add explicit fixture teardown and cleanup
  - Issue: test_client fixture cleanup may not be thorough
  - Root cause: Relying on context manager cleanup may not be sufficient
  - Files affected: `tests/conftest.py`
  - Fix approach:
    1. Add explicit teardown steps
    2. Shutdown FastAPI app properly
    3. Close all database connections
    4. Reset all mocks
    5. Clear async event loop
  - Impact: Ensures complete cleanup between tests
  - Estimated time: 2 hours

- [ ] T116: Add test isolation validation
  - Issue: No automated check that tests are properly isolated
  - Root cause: Missing test infrastructure
  - Files affected: `tests/conftest.py`
  - Fix approach:
    1. Add autouse fixture that runs before/after each test
    2. Check environment variable state
    3. Verify database is empty
    4. Check no global state exists
    5. Log isolation violations
  - Impact: Catches future isolation issues immediately
  - Estimated time: 2 hours

### Category 2: Controller Retry Test Fixes

**Priority: High** - Design issue, not isolation issue

- [ ] T117: Refactor controller retry tests to use fixture mocking
  - Issue: Tests try to patch controller after fixture sets up mock
  - Root cause: Tests written before fixture-based mocking was implemented
  - Files affected: `tests/integration/test_controller_retry.py`, `tests/conftest.py`
  - Fix approach:
    1. Add `configure_controller_failure` helper to conftest
    2. Allow mock_controller to be reconfigured per test
    3. Update all 5 controller retry tests to use fixture configuration
    4. Remove in-test patching attempts
  - Tests affected:
    - `test_controller_unreachable_grant_remains_pending`
    - `test_controller_retry_with_backoff`
    - `test_controller_recovery_pending_to_active` (already passes)
    - `test_controller_permanent_failure_handling`
    - `test_metrics_include_controller_failures`
  - Impact: Fixes 4-5 test failures
  - Estimated time: 2 hours

### Category 3: Graceful Shutdown Completion

**Priority: Medium** - Partially complete from Phase 3.8

- [x] T118: Fix queue drain race condition (T107 completion)
  - Issue: drain() returns before tasks actually complete
  - Root cause: drain() was calling get_queue_status() which returns 'queue_size' but looking for 'queue_depth', causing it to always get 0
  - Files affected: `src/services/queue_integration.py`
  - Fix applied:
    1. Changed drain() to use get_metrics() instead of get_queue_status()
    2. Reduced polling interval from 0.5s to 0.1s for faster responsiveness
  - Tests affected:
    - `test_graceful_shutdown_preserves_completed_work` ✅
    - `test_graceful_shutdown_partial_completion` ✅
  - Impact: Fixes 2 test failures - all graceful shutdown tests now pass (7/7)
  - Status: COMPLETED
  - Commit: Fix(queue): fix queue drain race condition in graceful shutdown

### Category 4: Portal Credential Flow

**Priority: Low** - May be fixed by isolation fixes

- [x] T119: Investigate portal credential validation (T109 investigation)
  - Issue: KeyError: 'code' in portal responses
  - Root cause: Already fixed in Phase 3.8 (likely through test isolation and auth fixes)
  - Files affected: None - issue was already resolved
  - Tests affected:
    - `test_splash_page_credential_success` ✅
    - `test_expired_credential_reuse_denied` ✅
  - Impact: No changes needed - tests already passing
  - Status: COMPLETED (no action required)
  - Note: This was likely fixed by earlier authentication and isolation fixes

## Implementation Strategy

### Phase 3.9.1: Test Infrastructure (4-6 hours)

**Must complete first - everything else depends on this**

1. T113: Environment variable cleanup (1 hour)
2. T114: Database isolation (2 hours)
3. T115: Explicit teardown (2 hours)
4. T116: Isolation validation (2 hours)

**Expected outcome**: All or most integration tests pass in full suite

### Phase 3.9.2: Remaining Fixes (4-6 hours)

Once tests are reliable:

1. T117: Controller retry refactor (2 hours)
2. T118: Queue drain race condition (2 hours)
3. T119: Portal credential investigation (2 hours, if needed)

**Expected outcome**: 100% test pass rate

## Success Criteria

- [ ] All 186 tests pass in full suite (not just individually)
- [ ] No 401 authentication errors in integrated tests
- [ ] No database state pollution between tests
- [ ] All controller retry scenarios work correctly
- [ ] Graceful shutdown completes all queued work
- [ ] Test suite is reliable and repeatable
- [ ] Test isolation validation catches future issues

## Total Estimated Effort

- Test Infrastructure: 6-8 hours (CRITICAL PATH)
- Controller Tests: 2 hours
- Shutdown Tests: 2 hours
- Portal Tests: 2 hours (conditional)

**Total**: 12-14 hours for 100% reliable test suite

## Notes

1. **Do not attempt fixes before infrastructure** - Without test isolation, we cannot validate fixes
2. **Tests are not broken** - The code works, test infrastructure has issues
3. **Quick wins possible** - Environment variable fix (T113) may resolve 75% of failures
4. **Infrastructure is one-time cost** - Once fixed, benefits all future test work

## Migration Note

Tasks from Phase 3.8 that are superseded or incorporated here:

- T107: Now T118 (graceful shutdown completion)
- T109: Now T119 (portal credential investigation)
- T112: Already complete, just needed isolation fix
- T104-T111: Already complete in Phase 3.7
