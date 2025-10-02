<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->
# Tasks: Captive Portal Addon (Rental Guest Network Access)

**Input**: plan.md (technical context, design notes, research topics)
**Prerequisites**: plan.md (required); research.md, data-model.md, contracts/, quickstart.md (future)

## Phase 3.1: Setup
- [x] T001 Create addon/ base structure (addon/src + tests skeleton, Dockerfile) per plan structure
- [x] T002 Add Python 3.13 base Dockerfile using HA addon-example pattern (s6-overlay) and uv installation
- [x] T003 [P] Initialize uv project (pyproject.toml, uv.lock) with FastAPI, httpx, Jinja2, pydantic, pytest, pytest-asyncio
- [x] T004 [P] Add SPDX headers pre-commit hook / validation config updates
- [x] T005 Configure logging & structured JSON formatter baseline
- [x] T006 Define configuration schema file for addon (config.yaml, options schema) with theme + controller fields

## Phase 3.2: Tests First (Contract & Lifecycle) ⚠️ MUST COMPLETE BEFORE 3.3
- [x] T007 Create test scaffolding: tests/unit, tests/contract, tests/integration, tests/performance
- [x] T008 [P] Contract test: POST /api/grants (provision grant from Rental Control event) → expects pending → active transition
- [x] T009 [P] Contract test: PATCH /api/grants/{id}/extend (extension)
- [x] T010 [P] Contract test: PATCH /api/grants/{id}/shorten (immediate force terminate)
- [x] T011 [P] Contract test: POST /api/vouchers (create voucher)
- [x] T012 [P] Contract test: GET /api/audit (filter events)
- [x] T013 [P] Contract test: POST /api/theme (update theme)
- [x] T014 Integration test: adaptive queue scaling scenario (burst grant creation then latency measurement)
- [x] T015 Integration test: controller unreachable retry / pending state
- [x] T016 Integration test: voucher and Rental Control derived grant coexistence
- [x] T017 Integration test: theme fallback on missing asset
- [x] T018 Integration test: forced termination logging
- [x] T018A Integration test: splash page credential validation success & failure (FR-009)
- [x] T018B Integration test: expired credential reuse denied (FR-018)

- [x] T018C Integration test: automatic expiry scheduler revokes grants after grace period (FR-003)
- [x] T018D Integration test: Rental Control event ingestion creates pending grant then activates at start (FR-001)


## Phase 3.3: Core Implementation
- [x] T019 Implement domain models (pydantic): AccessGrant, Voucher, EventLogEntry, ThemeConfig
- [x] T020 [P] Implement storage layer (sqlite repository) with migrations or init scripts
- [x] T021 [P] Implement audit_logger service (append-only events)
- [x] T022 [P] Implement voucher_service (create, expire, list)
- [x] T023 Implement grant_manager: lifecycle (pending→active, extend, shorten/force terminate, revoke)
- [x] T024 Implement queue_scheduler adaptive logic (concurrency scale 2→5 with latency windows)
- [x] T025 Implement controller adapter interface & TP-Omada adapter stub (fields per FAQ 896)
- [x] T026 Implement FastAPI routers (grants, vouchers, theme, audit, health)
- [x] T027 Implement theme_manager (fallback + validation)
- [x] T028 Implement startup provisioning watcher for new Rental Control events (stub event ingestion) (FR-001)
- [x] T030A Implement captive portal splash/login endpoint (serves themed page & processes credential submission) (FR-009)
- [x] T030B Implement expired credential rejection logic (check status/expiry, audit log) (FR-018)
- [ ] T030C Implement automatic expiry scheduler & grace period enforcement (FR-003)


- [ ] T029 Implement forced termination path (revocation + audit + controller call)
- [ ] T030 Implement extension & shortening logic with clamp + audit entries

## Phase 3.4: Integration
- [ ] T031 Wire controller adapter into grant_manager (provision, revoke, extend)
- [ ] T032 Add retry/backoff policy (controller unreachable) with metrics
- [ ] T033 Add metrics exporter (active_grants, queue_depth, provision_latency, failed_provisions)
- [ ] T034 Add structured logging (grants lifecycle, queue scaling decisions)
- [ ] T035 Add theme asset loader & default theme bundle
- [ ] T036 Add HA addon config validation at startup (reject invalid theme/controller config)
- [ ] T037 Implement health endpoint (queue depth, controller status sample)
- [ ] T038 Integrate uv workflow into CI (lock update check)

## Phase 3.5: Polish
- [ ] T039 [P] Unit tests for queue scaling edge conditions
- [ ] T040 [P] Unit tests for theme fallback logic
- [ ] T041 [P] Performance test for burst provisioning latency p95 threshold
- [ ] T042 Security review pass (audit logging completeness, no credential leakage)
- [ ] T043 [P] Documentation: README section for addon usage & configuration
- [ ] T044 [P] Documentation: controller adapter extension guide
- [ ] T045 Add CHANGELOG entry initial release notes
- [ ] T046 Remove duplication / dead code scan
- [ ] T047 Manual validation using quickstart scenarios (to be defined) & update quickstart.md stub
- [ ] T048 Implement admin authentication/authorization layer (token or HA context) (FR-005 security)
- [ ] T049 [P] Security test: unauthorized access to admin API endpoints rejected (401/403)
- [ ] T050 Implement rate limiting & credential attempt lockout (portal splash) (FR-009 security)
- [ ] T051 [P] Test: rate limiting triggers and lockout reset after cooldown
- [ ] T052 Implement log redaction for credentials/secrets
- [ ] T053 [P] Test: log redaction (no raw secrets in lifecycle logs)
- [ ] T054 [P] Metrics assertion test (active_grants, queue_depth, provision_latency exported) (FR-020 observability)
- [ ] T055 [P] Test: queue scaling decision log entries present & structured
- [ ] T056 Unit tests: grant_manager lifecycle state transitions (pending→active→expired/force revoke)
- [ ] T057 Unit tests: voucher expiry boundary conditions
- [ ] T058 Performance test: portal page render <300ms p95 (FR-007/FR-009 non-functional)
- [ ] T059 Implement graceful shutdown: drain queue & mark in-flight tasks
- [ ] T060 [P] Integration test: graceful shutdown preserves in-flight provisioning
- [ ] T061 Documentation: adaptive queue algorithm & security model (README)


## Dependencies
- Tests (T007–T018) before core implementation (T019–T030)
- T019 before T023/T024/T025
- T024 before T031 (queue interactions) and performance tests
- Controller adapter (T025) before integration wiring (T031/T032)
- Queue scheduler (T024) before metrics exporter (T033)
- Core implementation before polish tasks

## Parallel Execution Notes
- [P] tasks denote different files/services: storage, services, routers largely independent initially
- Avoid parallel edits to shared model definitions (T019 prerequisite for many)

## Parallel Example
```
# Run contract tests creation in parallel:
Task: "Contract test: POST /api/grants (provision)"
Task: "Contract test: PATCH /api/grants/{id}/extend"
Task: "Contract test: PATCH /api/grants/{id}/shorten"
Task: "Contract test: POST /api/vouchers"
Task: "Contract test: GET /api/audit"
Task: "Contract test: POST /api/theme"
```

## Validation Checklist
- [ ] All contract endpoints have tests (T008–T013)
- [ ] All entities modeled (T019)
- [ ] Adaptive queue tests exist before implementation (T014)
- [ ] Retry/pending states covered (T015)
- [ ] Theme fallback tested (T017)
- [ ] Forced termination & audit logging tested (T018)
- [ ] No implementation tasks lack preceding failing tests
- [ ] Each parallel [P] task touches distinct files
