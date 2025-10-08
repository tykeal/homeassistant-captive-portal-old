<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Phase 3.8: Final Test Remediation

**Status**: In Progress
**Test Results (Current)**: 157 passing, 29 failing (84% pass rate)
**Coverage**: 68% overall
**Progress**: 2/11 tasks completed (18%)

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

- [ ] T106: Add authentication to controller integration tests
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

- [ ] T108: Add authentication to portal scenario tests
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

- [ ] T110: Add authentication to queue scaling tests
  - Issue: 401 errors on grant creation, 404 on metrics endpoint
  - File: `tests/integration/test_queue_scaling.py`
  - Tests:
    - `test_burst_grant_creation_scaling` (401 instead of 201)
    - `test_queue_scaling_metrics` (404 instead of 200)
    - `test_queue_scaling_under_sustained_load` (0% success rate)
  - Fix: Apply auth_headers and verify metrics endpoint routing

### Category 7: Theme Fallback Authentication (7 failures)

**Priority: Medium** - Feature testing

- [ ] T111: Add authentication to theme fallback tests
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

(None yet)

### In Progress

(None yet)

### Next Steps

1. Start with T104 (ProvisionResult fix) - critical blocker
2. Follow with T106 auth fix to validate controller tests
3. Complete auth sweep (T108, T110, T111, T112)
4. Address remaining logic issues (T105, T107, T109)
