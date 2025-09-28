
<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Implementation Plan: Captive Portal Addon (Rental Guest Network Access)

**Branch**: `001-create-captive-portal` | **Date**: 2025-09-28 | **Spec**: specs/001-create-captive-portal/spec.md
**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

## Execution Flow (/plan command scope)
```
1. Load feature spec from Input path
   → If not found: ERROR "No feature spec at {path}"
2. Fill Technical Context (scan for NEEDS CLARIFICATION)
   → Detect Project Type from file system structure or context (web=frontend+backend, mobile=app+api)
   → Set Structure Decision based on project type
3. Fill the Constitution Check section based on the content of the constitution document.
4. Evaluate Constitution Check section below
   → If violations exist: Document in Complexity Tracking
   → If no justification possible: ERROR "Simplify approach first"
   → Update Progress Tracking: Initial Constitution Check
5. Execute Phase 0 → research.md
   → If NEEDS CLARIFICATION remain: ERROR "Resolve unknowns"
6. Execute Phase 1 → contracts, data-model.md, quickstart.md, agent-specific template file (e.g., `CLAUDE.md` for Claude Code, `.github/copilot-instructions.md` for GitHub Copilot, `GEMINI.md` for Gemini CLI, `QWEN.md` for Qwen Code or `AGENTS.md` for opencode).
7. Re-evaluate Constitution Check section
   → If new violations: Refactor design, return to Phase 1
   → Update Progress Tracking: Post-Design Constitution Check
8. Plan Phase 2 → Describe task generation approach (DO NOT create tasks.md)
9. STOP - Ready for /tasks command
```

**IMPORTANT**: The /plan command STOPS at step 7. Phases 2-4 are executed by other commands:
- Phase 2: /tasks command creates tasks.md
- Phase 3-4: Implementation execution (manual or via tools)

## Summary
Provide a Home Assistant addon that offers a configurable captive portal for rental guests. It provisions and revokes
network access based on Rental Control integration booking windows, supports manual voucher grants, provides an admin
panel (HA webpanel), logs all lifecycle events, and uses a pluggable backend architecture starting with TP-Omada.
Technical approach: modular service layers (grant lifecycle manager, controller adapters, theme manager, audit logger,
queue scheduler with adaptive concurrency 2→5) aligned with constitution principles (modularity, observability,
security/privacy, test-first).

## Technical Context
**Language/Version**: Python 3.13 (target) – ensure addon base image variant supports 3.13; if not, introduce build stage to supply 3.13 runtime
**Primary Dependencies**: FastAPI (admin + portal HTTP), httpx (controller API calls), Jinja2 (theme templating), pydantic (config & models), uv (package/env management)
**Storage**: Lightweight embedded DB (SQLite) for grants, vouchers, events (future pluggable) – small scale persistence
**Testing**: pytest (unit + integration), pytest-asyncio, coverage
**Target Platform**: Home Assistant OS / Supervisor managed addon container (Linux, amd64/arm64)
**Project Type**: single (addon service + internal modules)
**Performance Goals**: Provision latency < 2s p95, portal page render < 300ms server-side, adaptive queue latency <400ms threshold
**Constraints**: Memory <150MB RSS typical; do not block HA supervisor; structured logging JSON-capable; hardened against concurrent modification
**Scale/Scope**: Expected concurrent active grants: <500; burst grant creations: up to 50 in 1 minute at property turnover
**Packaging Note**: Use uv for dependency resolution, lockfile generation, and isolated execution; block merges without updated uv lock on dependency changes.


## Constitution Check
*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- Modularity: Planned modules (grant_manager, controller_adapters, theme_manager, audit_logger, queue_scheduler) uphold single responsibility.
- Security & Privacy: No PII stored beyond credentials & booking identifiers; credentials not logged; deny-by-default for admin API.
- Observability: Structured logs for lifecycle events; metrics: active_grants, pending_provisions, queue_depth, provision_latency.
- Test-First Quality Gates: Commit to write contract + lifecycle tests before implementation.
- SPDX Discipline: All new source files will start with headers.
Status: PASS (no violations).

## Project Structure

### Documentation (this feature)
```
specs/001-create-captive-portal/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->
```
```
addon/
├── src/
│   ├── core/
│   ├── controllers/
│   ├── api/
│   ├── portal/
│   ├── themes/
│   ├── models/
│   ├── services/
│   └── storage/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   └── performance/
└── Dockerfile
```

# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: Adopt single addon modular layout under addon/src with clear domain folders; test segregation by type; supports pluggable controllers.

## Phase 0: Outline & Research
1. **Extract unknowns from Technical Context** above:
   - For each NEEDS CLARIFICATION → research task
   - For each dependency → best practices task
   - For each integration → patterns task

2. **Generate and dispatch research agents**:
   ```
   For each unknown in Technical Context:
     Task: "Research {unknown} for {feature context}"
   For each technology choice:
     Task: "Find best practices for {tech} in {domain}"
   ```

3. **Consolidate findings** in `research.md` using format:
   - Decision: [what was chosen]
   - Rationale: [why chosen]
   - Alternatives considered: [what else evaluated]

**Output**: research.md with all NEEDS CLARIFICATION resolved

## Phase 1: Design & Contracts
*Prerequisites: research.md complete*

1. **Extract entities from feature spec** → `data-model.md`:
   - Entity name, fields, relationships
   - Validation rules from requirements
   - State transitions if applicable

2. **Generate API contracts** from functional requirements:
   - For each user action → endpoint
   - Use standard REST/GraphQL patterns
   - Output OpenAPI/GraphQL schema to `/contracts/`

3. **Generate contract tests** from contracts:
   - One test file per endpoint
   - Assert request/response schemas
   - Tests must fail (no implementation yet)

4. **Extract test scenarios** from user stories:
   - Each story → integration test scenario
   - Quickstart test = story validation steps

5. **Update agent file incrementally** (O(1) operation):
   - Run `.specify/scripts/bash/update-agent-context.sh copilot`
     **IMPORTANT**: Execute it exactly as specified above. Do not add or remove any arguments.
   - If exists: Add only NEW tech from current plan
   - Preserve manual additions between markers
   - Update recent changes (keep last 3)
   - Keep under 150 lines for token efficiency
   - Output to repository root

**Output**: data-model.md, /contracts/*, failing tests, quickstart.md, agent-specific file

## Phase 2: Task Planning Approach
*This section describes what the /tasks command will do - DO NOT execute during /plan*

**Task Generation Strategy**:
- Load `.specify/templates/tasks-template.md` as base
- Generate tasks from Phase 1 design docs (contracts, data model, quickstart)
- Each contract → contract test task [P]
- Each entity → model creation task [P]

### Phase 0 Research Topics
- Evaluate TP-Omada API rate limits & auth scheme.
- Confirm Home Assistant addon best practice for embedding FastAPI.
- Assess SQLite write contention under adaptive queue concurrency.
- Determine theming asset size guidelines.

- Reference: TP-Omada voucher & portal workflow (https://www.tp-link.com/us/support/faq/896/) to inform controller adapter contract design (voucher creation fields, expiration handling, portal redirection parameters).

### Phase 1 Design Notes
- Entities map: AccessGrant, Voucher, Event (audit), Theme.
- Contracts: provisioning endpoint(s), extension/shorten, voucher create, theme update, audit log fetch, health.
- Integration tests derive from Acceptance Scenarios 1–5.

- Each user story → integration test task
- Implementation tasks to make tests pass

**Ordering Strategy**:
- TDD order: Tests before implementation
- Dependency order: Models before services before UI
- Mark [P] for parallel execution (independent files)

**Estimated Output**: 25-30 numbered, ordered tasks in tasks.md

**IMPORTANT**: This phase is executed by the /tasks command, NOT by /plan

## Phase 3+: Future Implementation
*These phases are beyond the scope of the /plan command*

**Phase 3**: Task execution (/tasks command creates tasks.md)
**Phase 4**: Implementation (execute tasks.md following constitutional principles)
**Phase 5**: Validation (run tests, execute quickstart.md, performance validation)

## Complexity Tracking
*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |


## Progress Tracking
*This checklist is updated during execution flow*

**Phase Status**:
- [ ] Phase 0: Research complete (/plan command)
- [ ] Phase 1: Design complete (/plan command)
- [ ] Phase 2: Task planning complete (/plan command - describe approach only)
- [ ] Phase 3: Tasks generated (/tasks command)
- [ ] Phase 4: Implementation complete
- [ ] Phase 5: Validation passed

**Gate Status**:
- [ ] Initial Constitution Check: PASS
- [ ] Post-Design Constitution Check: PASS
- [ ] All NEEDS CLARIFICATION resolved
- [ ] Complexity deviations documented

---
*Based on Constitution v1.0.0 - See `/memory/constitution.md`*
