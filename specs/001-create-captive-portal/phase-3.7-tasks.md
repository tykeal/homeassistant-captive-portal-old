<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Phase 3.7: Remaining Test Failures Remediation

**Status**: Planning
**Test Results**: 122 passing, 64 failing (66% pass rate)
**Coverage**: 59% overall

## Test Failure Analysis Summary

After completing Phase 3.6 infrastructure fixes, 64 test failures remain. These are categorized into distinct root causes that can be addressed systematically.

### Failure Categories

1. **Voucher API Missing Auth** (6 failures) - Quick fix
2. **Business Logic Issues** (23 failures) - Implementation gaps
3. **Test Mock/Patch Issues** (12 failures) - Test infrastructure
4. **Portal Template/Routing** (8 failures) - Template rendering
5. **Model Validation** (3 failures) - Schema updates needed
6. **Theme Manager Integration** (7 failures) - Asset loading
7. **Controller Integration** (6 failures) - Adapter wiring
8. **Date/Time Issues** (3 failures) - Test data dates

## Phase 3.7 Tasks

### Category 1: Authentication Fixes (6 failures)

**Priority: High** - Quick wins, similar to Phase 3.6 fixes

- [x] T080: Add auth_headers to test_vouchers_api.py
  - File: `tests/contract/test_vouchers_api.py`
  - Fix: Apply auth_headers fixture to all 6 test methods
  - Similar to: T063-T065

### Category 2: Grant API Business Logic (5 failures)

**Priority: High** - Core functionality

- [x] T081: Fix grant status determination logic
  - Issue: Grants becoming 'active' when should be 'pending'
  - Root cause: Start time comparison using past test dates
  - Fix: Update test dates to future OR fix status logic in grant_manager.py
  - Files: `tests/contract/test_grants_api.py`, `src/services/grant_manager.py`

- [x] T082: Implement grant extension endpoint
  - Issue: Endpoint exists but returns errors
  - Files: `src/api/grants.py`, `src/services/grant_manager.py`
  - Methods needed: Grant extension logic

- [x] T083: Implement grant shortening/termination endpoint
  - Issue: Endpoint exists but returns errors
  - Files: `src/api/grants.py`, `src/services/grant_manager.py`
  - Methods needed: Grant termination logic

### Category 3: Theme API Implementation (3 failures)

**Priority: Medium** - Feature completion

- [ ] T084: Implement theme GET endpoint
  - Issue: Returns empty/default data
  - File: `src/api/theme.py`
  - Fix: Wire theme_manager.get_current_theme()

- [ ] T085: Implement theme reset endpoint
  - Issue: Not implemented
  - File: `src/api/theme.py`
  - Fix: Add reset_to_default functionality

- [ ] T086: Implement theme preview endpoint
  - Issue: Not implemented
  - File: `src/api/theme.py`
  - Fix: Add preview generation logic

### Category 4: Audit API Enhancement (1 failure)

**Priority: Low** - Edge case

- [ ] T087: Fix audit date range filtering
  - Issue: Date range query not filtering correctly
  - File: `src/services/audit_logger.py`
  - Fix: Verify datetime parsing and comparison logic

### Category 5: Metrics Export Mock Issues (8 failures)

**Priority: Medium** - Test quality

- [ ] T088: Fix metrics export test mocking strategy
  - Issue: Patches not applying to test client requests
  - File: `tests/unit/test_metrics_export.py`
  - Fix: Refactor to use dependency injection or proper fixture scope
  - Root cause: Patches applied at wrong scope

### Category 6: Queue Scaling Log Tests (4 failures)

**Priority: Low** - Test infrastructure

- [ ] T089: Fix log capture in queue scaling tests
  - Issue: Logs not being captured in test buffer
  - File: `tests/unit/test_queue_scaling_logs.py`
  - Fix: Update logging configuration for test mode
  - Note: API works correctly, only test capture broken

### Category 7: Graceful Shutdown Tests (3 failures)

**Priority: Medium** - Model validation

- [ ] T090: Add guest_name to AccessGrant test fixtures
  - Issue: ValidationError - guest_name field required
  - File: `tests/integration/test_graceful_shutdown.py`
  - Fix: Update AccessGrant creation to include guest_name
  - Root cause: Model schema changed, tests not updated

### Category 8: Portal Scenarios (5 failures)

**Priority: Medium** - Integration testing

- [ ] T091: Implement forced termination audit logging
  - File: `tests/integration/test_portal_scenarios.py`
  - Dependencies: Grant termination endpoint (T083)

- [ ] T092: Implement splash page credential validation
  - Issue: Portal authentication flow incomplete
  - Files: `src/portal/router.py`, portal templates
  - Dependencies: Portal rendering (T093)

- [ ] T093: Fix portal template rendering
  - Issue: 404 errors on portal routes
  - File: `src/portal/router.py`
  - Fix: Verify template paths and Jinja2 configuration

- [ ] T094: Implement expired credential reuse prevention
  - File: Integration test logic
  - Dependencies: Portal auth flow

- [ ] T095: Implement automatic expiry scheduler integration
  - File: `src/services/expiry_scheduler.py`
  - Fix: Wire scheduler into test harness

### Category 9: Rental Control Event Ingestion (1 failure)

**Priority: Medium** - Feature integration

- [ ] T096: Complete rental control event ingestion flow
  - Issue: Event processing incomplete
  - File: `src/services/event_ingestion.py`
  - Fix: Implement full pending→active state transition

### Category 10: Queue Scaling Integration (3 failures)

**Priority: Medium** - Performance testing

- [ ] T097: Fix queue scaling integration tests
  - Issue: Integration with grant manager incomplete
  - File: `tests/integration/test_queue_scaling.py`
  - Fix: Wire queue scheduler into grant provisioning tests

### Category 11: Rate Limiting Tests (1 failure)

**Priority: Low** - Feature testing

- [ ] T098: Fix rate limiting stats endpoint
  - Issue: Stats aggregation incomplete
  - File: `src/services/rate_limiter.py`
  - Fix: Implement stats collection and endpoint

### Category 12: Theme Fallback Tests (7 failures)

**Priority: Low** - Error handling

- [ ] T099: Implement theme asset loader error handling
  - Issue: ThemeAssetLoader not integrated
  - File: `src/services/theme_asset_loader.py`
  - Tests: All theme fallback scenarios
  - Fix: Complete asset loading, validation, and fallback logic

### Category 13: Voucher-Grant Coexistence (6 failures)

**Priority: Low** - Integration scenarios

- [ ] T100: Fix voucher-grant coexistence test data
  - Issue: Mixed source grant scenarios failing
  - File: `tests/integration/test_voucher_grant_coexistence.py`
  - Fix: Update test data and verify dual-source logic

### Category 14: Controller Retry Tests (6 failures)

**Priority: Low** - Resilience testing

- [ ] T101: Complete controller retry/backoff integration
  - Issue: Controller adapter not fully wired into tests
  - File: `tests/integration/test_controller_retry.py`
  - Fix: Mock controller properly in integration tests

### Category 15: Performance Tests (5 failures)

**Priority: Low** - Performance validation

- [ ] T102: Fix burst provisioning performance tests
  - Issue: Grant manager mock setup incomplete
  - File: `tests/performance/test_burst_provisioning.py`
  - Fix: Update mocks after constructor changes

- [ ] T103: Fix portal render performance tests
  - Issue: Portal routes returning 404
  - File: `tests/performance/test_portal_render.py`
  - Dependencies: Portal template rendering (T093)

## Implementation Priority

### Phase 3.7.1: Quick Wins (Estimated: 2 hours)

High-impact, low-effort fixes:

1. T080: Voucher API auth (30 min)
2. T081: Grant status logic (1 hour)
3. T087: Audit date filtering (30 min)

**Impact**: Resolves 12 failures (19%)

### Phase 3.7.2: Core Business Logic (Estimated: 8 hours)

Essential feature completion:

1. T082: Grant extension (2 hours)
2. T083: Grant termination (2 hours)
3. T084-T086: Theme API endpoints (2 hours)
4. T090: Model validation fixes (30 min)
5. T093: Portal template rendering (2 hours)

**Impact**: Resolves 14 additional failures (22%)

### Phase 3.7.3: Test Infrastructure (Estimated: 4 hours)

Improve test quality:

1. T088: Metrics mock refactoring (2 hours)
2. T089: Log capture fix (1 hour)
3. T100: Test data cleanup (1 hour)

**Impact**: Resolves 18 additional failures (28%)

### Phase 3.7.4: Advanced Features (Estimated: 12 hours)

Lower priority enhancements:

1. T091-T095: Portal scenarios (4 hours)
2. T096-T097: Event ingestion and scaling (3 hours)
3. T098-T099: Rate limiting and theme fallback (3 hours)
4. T101-T103: Controller and performance (2 hours)

**Impact**: Resolves 20 remaining failures (31%)

## Total Estimated Effort

- **Quick Wins**: 2 hours → 87% pass rate
- **+ Core Logic**: 8 hours → 94% pass rate
- **+ Test Infrastructure**: 4 hours → 99% pass rate
- **+ Advanced Features**: 12 hours → 100% pass rate

**Total**: ~26 hours for complete test suite success

## Success Criteria

- [ ] Pass rate > 95% (177+ tests passing)
- [ ] Zero authentication failures
- [ ] All contract tests passing
- [ ] Core grant lifecycle working end-to-end
- [ ] Portal rendering functional
- [ ] Theme API complete

## Notes

1. **Not Blocking MVP**: The remaining failures don't block basic functionality
2. **Infrastructure Solid**: All Phase 3.6 fixes holding strong
3. **Clear Path Forward**: Each failure has identified root cause and fix
4. **Incremental**: Can implement in phases based on priority

## Task Assignment Strategy

- **Solo Developer**: Focus on Phase 3.7.1 and 3.7.2 first
- **Team**: Parallelize by category (auth, business logic, test infra)
- **MVP Rush**: Only implement Phase 3.7.1 and core of 3.7.2
