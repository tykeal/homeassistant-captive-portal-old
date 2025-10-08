<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Phase 3.8: Final Test Remediation

**Status**: In Progress
**Test Results (Current)**: 158 passing, 28 failing (85% pass rate)
**Coverage**: 68% overall
**Progress**: 5/11 tasks completed (45%)

## Test Failure Analysis

After completing Phase 3.7, 32 test failures remain. These fall into clear categories with identified root causes.

### Failure Categories

1. **Grant Provisioning Logic** (2 failures) - ProvisionResult object handling
2. **Theme Preview** (1 failure) - JSON parsing error
3. **Controller Integration** (6 failures) - Authentication and adapter wiring
4. **Graceful Shutdown** (2 failures) - Queue completion tracking
5. **Portal Scenarios** (5 failures) - Authentication and credential flow
6. **Queue Scaling** (3 failures) - Authentication and metrics
7. **Theme Fallback** (7 failures) - Authentication issues
8. **Voucher-Grant Coexistence** (6 failures) - Authentication issues

## Phase 3.8 Tasks

### Category 1: Grant Provisioning ProvisionResult Handling (2 failures)

**Priority: Critical** - Core functionality broken

- [x] T104: Fix ProvisionResult object handling in grant manager
  - Issue: `'ProvisionResult' object has no attribute 'get'`
  - Root cause: Code treats ProvisionResult as dict instead of object
  - Files affected:
    - `src/services/grant_manager.py:287`
    - `src/services/logging_utils.py:197`
  - Tests failing:
    - `test_post_grants_immediate_activation`
    - `test_patch_grants_shorten_scheduled`
  - Fix: Update all ProvisionResult access to use attribute access instead of dict methods
  - Impact: Breaks immediate grant activation

### Category 2: Theme Preview JSON Parsing (1 failure)

**Priority: Medium** - Feature completeness

- [x] T105: Fix theme preview endpoint JSON response
  - Issue: `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`
  - Root cause: Preview endpoint returning non-JSON content
  - File: `src/api/theme.py`
  - Test: `test_get_theme_preview`
  - Fix: Ensure preview endpoint returns proper JSON or handle HTML preview correctly
  - Related: T099 implemented HTML preview, may need content negotiation

### Category 3: Controller Integration Authentication (6 failures)

**Priority: High** - Integration testing

- [x] T106: Add authentication to controller integration tests
  - Issue: All tests returning 401 instead of expected 201/200
  - File: `tests/integration/test_controller_retry.py`
  - Tests affected: All 6 tests in TestControllerUnreachable class
  - Fix: Apply auth_headers fixture to all test methods
  - Similar to: T080 (voucher API auth fixes)

### Category 4: Graceful Shutdown Queue Completion (2 failures)

**Priority: Medium** - Reliability testing

- [ ] T107: Fix graceful shutdown queue completion tracking
  - Issue: Completed work count showing 0 instead of expected values (4-5)
  - File: `tests/integration/test_graceful_shutdown.py`
  - Tests:
    - `test_graceful_shutdown_preserves_completed_work` (expects 5 completed)
    - `test_graceful_shutdown_partial_completion` (expects 4 completed)
  - Root cause: Queue worker completion not being tracked/reported correctly
  - Fix: Verify queue completion metrics and shutdown signal handling

### Category 5: Portal Scenarios Authentication & Flow (5 failures)

**Priority: High** - Core user flow

- [x] T108: Add authentication to portal scenario tests
  - Issue: Tests returning 401 instead of 201
  - File: `tests/integration/test_portal_scenarios.py`
  - Tests affected:
    - `test_forced_termination_audit_logging`
    - `test_automatic_expiry_scheduler_grace_period`
    - `test_rental_control_event_creates_pending_then_activates`
  - Fix: Apply auth_headers fixture

- [ ] T109: Fix portal credential validation flow
  - Issue: KeyError: 'code' in portal responses
  - File: Portal authentication flow
  - Tests:
    - `test_splash_page_credential_success`
    - `test_expired_credential_reuse_denied`
  - Root cause: Portal response not including expected 'code' field
  - Fix: Update portal credential validation to return proper response structure
  - Dependencies: Portal template rendering from T093

### Category 6: Queue Scaling Tests (3 failures)

**Priority: Medium** - Performance testing

- [x] T110: Add authentication to queue scaling tests
  - Issue: 401 errors on grant creation, 404 on metrics endpoint
  - File: `tests/integration/test_queue_scaling.py`
  - Tests:
    - `test_burst_grant_creation_scaling` (401 instead of 201)
    - `test_queue_scaling_metrics` (404 instead of 200)
    - `test_queue_scaling_under_sustained_load` (0% success rate)
  - Fix: Apply auth_headers and verify metrics endpoint routing

### Category 7: Theme Fallback Authentication (7 failures)

**Priority: Medium** - Feature testing

- [x] T111: Add authentication to theme fallback tests
  - Issue: All tests returning 401 instead of expected codes
  - File: `tests/integration/test_theme_fallback.py`
  - Tests affected: All 7 tests in TestThemeFallback class
  - Expected codes: 200 (most), 422 (validation test)
  - Fix: Apply auth_headers fixture to all test methods

### Category 8: Voucher-Grant Coexistence (6 failures)

**Priority: Medium** - Integration testing

- [ ] T112: Add authentication to voucher-grant coexistence tests
  - Issue: 401 on grant creation, 404 on metrics endpoint
  - File: `tests/integration/test_voucher_grant_coexistence.py`
  - Tests affected: All 6 tests in TestVoucherGrantCoexistence class
  - Fix: Apply auth_headers fixture

## Implementation Priority

### Phase 3.8.1: Critical Fixes (Estimated: 2 hours)

Must-fix for basic functionality:

1. T104: ProvisionResult handling (1 hour)
2. T105: Theme preview JSON (30 min)
3. T106: Controller auth (30 min)

**Impact**: Resolves 9 failures (28%) → 88% pass rate

### Phase 3.8.2: Authentication Sweep (Estimated: 1 hour)

Apply auth_headers across remaining integration tests:

1. T108: Portal scenarios auth (15 min)
2. T110: Queue scaling auth (15 min)
3. T111: Theme fallback auth (15 min)
4. T112: Voucher-grant coexistence auth (15 min)

**Impact**: Resolves 21 failures (66%) → 96% pass rate

### Phase 3.8.3: Flow & Logic Fixes (Estimated: 3 hours)

Complete remaining business logic:

1. T107: Graceful shutdown tracking (1 hour)
2. T109: Portal credential flow (2 hours)

**Impact**: Resolves 2 failures (6%) → 100% pass rate

## Total Estimated Effort

- **Critical Fixes**: 2 hours → 88% pass rate
- **+ Auth Sweep**: 1 hour → 96% pass rate
- **+ Flow Fixes**: 3 hours → 100% pass rate

**Total**: ~6 hours for complete test suite success

## Success Criteria

- [ ] Pass rate ≥ 95% (177+ tests passing)
- [ ] All contract tests passing (currently 31/33)
- [ ] Zero ProvisionResult handling errors
- [ ] All authentication properly configured in tests
- [ ] Portal credential flow working end-to-end

## Notes

1. **Pattern Recognition**: Many failures are simple auth fixture omissions
2. **Critical Bug**: ProvisionResult handling is blocking core grant functionality
3. **Quick Wins**: Auth fixes can resolve 21/32 failures (~66%)
4. **Systematic Approach**: Complete auth sweep before investigating logic issues

## Session Progress

### Completed Tasks

- T104: ProvisionResult handling - already completed in Phase 3.7
- T105: Theme preview JSON - already completed in Phase 3.7
- T106: Controller integration auth - already completed in Phase 3.7
- T108: Portal scenarios auth - already completed in Phase 3.7
- T110: Queue scaling auth - already completed in Phase 3.7
- T111: Theme fallback auth - already completed in Phase 3.7
- T112: Voucher-grant coexistence auth - already completed, tests pass individually

### In Progress

- T107: Graceful shutdown - Fixed recursion error, but race condition in queue drain logic remains

### Discovered Issues

#### Test Isolation Problem (Critical)

**Status**: Blocking - prevents accurate test results

All integration tests pass when run individually or in small groups, but 28 tests fail when run as part of the full test suite. This indicates test isolation issues where state from previous tests affects subsequent tests.

**Evidence**:
- `test_voucher_grant_coexistence.py`: All 6 tests PASS individually, all FAIL in full suite
- `test_portal_scenarios.py`: All 5 tests PASS individually, all FAIL in full suite
- `test_queue_scaling.py`: All 3 tests PASS individually, all FAIL in full suite
- `test_theme_fallback.py`: All 7 tests PASS individually, all FAIL in full suite
- `test_controller_retry.py`: Mixed results - some pass, some fail in both modes

**Root Causes**:
1. Database state not properly cleaned between tests
2. Configuration bleeding between test fixtures
3. Mock controller state persisting across tests
4. Async event loop state not reset

**Required Fixes**:
1. Ensure each test gets a truly isolated database
2. Reset all global state in conftest fixtures
3. Fix fixture scope issues (some may need function scope instead of session)
4. Add proper teardown to clear async state

#### Controller Retry Tests (5 failures)

**Status**: Test design issue

Tests in `test_controller_retry.py` attempt to patch controller methods within the test body, but the `test_client` fixture from conftest.py has already patched the controller factory with a global mock. The test's patches don't take effect because they're patching after the app is already created with the fixture's mock.

**Required Fix**:
Refactor tests to configure the mock_controller fixture's behavior instead of trying to patch

#### T107: Graceful Shutdown Queue Completion (partial)

**Status**: Partially fixed

- ✅ Fixed: Infinite recursion error in test_graceful_shutdown_preserves_completed_work
- ❌ Remaining: Race condition where drain() returns before tasks complete
  - Queue reports 0 depth and 0 active tasks incorrectly
  - drain() exits immediately
  - Tasks complete after drain() has already returned

**Required Fix**:
Investigate queue status tracking in QueueScheduler.get_queue_status()

#### T109: Portal Credential Validation

**Status**: Not investigated yet - blocked by test isolation issues

Cannot reliably test until test isolation is fixed.

### Next Steps

**Priority 1: Fix Test Isolation (Estimated: 4-6 hours)**

This is blocking all other work. Without reliable test results, we cannot validate fixes.

1. Investigate database fixture cleanup
2. Add explicit teardown to test_client fixture
3. Check for global state in config module
4. Add test markers to run integration tests in isolation

**Priority 2: Fix Controller Retry Tests (Estimated: 2 hours)**

1. Modify tests to use mock_controller fixture behavior
2. Add methods to conftest to configure mock responses
3. Update all 5 controller retry tests

**Priority 3: Complete T107 (Estimated: 2 hours)**

1. Debug QueueScheduler.get_queue_status()
2. Add proper tracking of active tasks
3. Fix drain() to wait for actual task completion

**Priority 4: Investigate T109 (Estimated: 2 hours)**

Can only proceed after test isolation is fixed.

### Total Remaining Effort

- Test Isolation Fix: 4-6 hours (CRITICAL)
- Controller Tests: 2 hours
- T107 Completion: 2 hours
- T109 Investigation: 2 hours

**Total**: 10-12 hours

### Recommendation

Given the test isolation issues, the most productive path forward is:

1. Fix test isolation first - this unblocks everything else
2. Once tests are reliable, fix controller retry tests
3. Complete T107 and T109
4. Rerun full suite to verify 100% pass rate

The good news: Most Phase 3.8 tasks are already complete. The bad news: Test isolation issues mask this progress and prevent validation.
