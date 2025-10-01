<!--
Sync Impact Report
Version change: v1.0.0 → v1.1.0
Modified sections: Development Workflow & Quality Gates
Added sections: (none)
Removed sections: (none)
Templates requiring updates:
  .specify/templates/plan-template.md ✅ (version reference updated to v1.1.0)
  .specify/templates/spec-template.md ✅ (no direct version reference; no change needed)
  .specify/templates/tasks-template.md ✅ (no direct reference; no change needed)
Follow-up TODOs: None
-->

# Captive Portal Addon Constitution

## Core Principles

### 1. Modular Addon Architecture
The captive portal MUST be composed of clearly separated, minimal modules (authentication flow, session management,
UI/splash delivery, device authorization, metrics, configuration). Each module MUST have a single responsibility and
MUST NOT introduce hidden coupling. Cross-module communication MUST use explicit, documented interfaces.
Rationale: Ensures extensibility for future Rental Control integration changes and feature evolution.

### 2. Security & Privacy by Design (NON-NEGOTIABLE)
All network entry points MUST enforce the strictest feasible access controls. Sensitive data (device identifiers,
lease information, personal info) MUST never be logged in plaintext. Encryption in transit is REQUIRED when supported
by the host environment. Default posture: deny-by-default, explicit allow. Threat modeling for session hijack,
rogue device reuse, and timing abuse MUST precede release. Any relaxation requires documented justification.

### 3. Observability & Accountability
All state transitions (authorize device, renew session, revoke, expire) MUST be logged with structured fields
(timestamp, action, subject, correlation/session id). Metrics MUST include active sessions, authentication latency,
failed authorization attempts, and expiry churn. Logs MUST NOT contain PII. Traces or correlation IDs MUST propagate
across async boundaries where applicable.

### 4. Test-First Quality Gates
Behavioral (user / device flow) tests, configuration parsing tests, and security boundary tests MUST be written and
failing before implementing corresponding logic (TDD). No code may merge without: (a) all tests green, (b) new logic
covered by at least one assertion, (c) security-impacting paths explicitly exercised.

### 5. Licensing & Compliance (SPDX Discipline)
Every file supporting comments MUST begin with an SPDX copyright and license identifier. Missing headers are a build
or CI failure. License changes MUST be reviewed and version-impact assessed. Third‑party attributions MUST be
aggregated in a single NOTICE or LICENSE metadata location.

## Additional Constraints & Standards

1. Home Assistant Addon Alignment: Must follow HA addon directory + configuration conventions (config.yaml, options,
   schema, service exposure). No undocumented overrides.
2. Rental Control Integration Compatibility: Public interaction surfaces (API endpoints, MQTT topics, events, or file
   drop points) MUST remain backward compatible within a MAJOR version.
3. Resource Efficiency: Idle memory footprint SHOULD remain minimal; long‑lived processes MUST release stale session
   state promptly on expiry.
4. Performance Targets: Authorization round trip SHOULD complete in <250ms p95 under nominal load on supported hardware.
5. Session Policy: Expired sessions MUST be purged deterministically; renewal MUST extend only remaining duration rules
   (never unbounded extension without policy alignment).
6. Configuration: All tunable values (timeouts, grace periods, UI content, network rules) MUST be declaratively defined
   (no hard-coded magic constants) and validated at startup.
7. Error Handling: Graceful degradation preferred—UI must surface user-friendly messages, while logs capture technical
   diagnostics.
8. No Silent Failures: Any security or authorization bypass attempt MUST emit structured warning level logs.
9. Dependency Discipline: Introduce new runtime dependencies only with documented rationale and security review.
10. Backward Compatibility: MINOR versions may add optional fields; removing or altering semantics requires MAJOR bump.

## Development Workflow & Quality Gates

1. Branch Flow: feature/<slug> → PR → review → main. No direct commits to main.
2. Required PR Checklist (auto or manual):
   - All SPDX headers present
   - New/updated modules have tests
   - No TODO without linked issue
   - Security-sensitive changes reviewed by a second maintainer
3. Test Tiers:
   - Unit: Logic & validation rules
   - Functional: Session lifecycle, authorization decisions
   - Integration: Home Assistant addon startup & interaction with Rental Control integration
   - Security: Unauthorized / replay / expired session attempts
4. Coverage: Critical path (session creation, renewal, expiry, revocation) MUST have explicit test coverage.
5. Observability Tests: At least one test MUST assert presence & structure of emitted log/metric for a key flow.
6. CI Gates (blocking): formatting, SPDX scan, tests pass, license compliance, static analysis (if configured).
7. Documentation: New externally visible behavior MUST update README/addon usage docs before merge.
8. Release Artifacts: Versioned changelog entries summarizing feature, security, and compatibility notes.
9. Pre-commit Enforcement: Local git hooks (e.g., pre-commit) MUST NOT be bypassed (no use of --no-verify) except via a
   time-bound documented exception referencing an issue; disabling hooks without approval is a policy violation.

## Governance

1. Authority: This constitution supersedes ad-hoc preferences. Conflicts MUST be resolved by aligning code/specs to
   these principles unless an amendment is ratified.
2. Amendment Process:
   - Proposal PR referencing current version
   - Rationale + impact statement (backward compatibility & risk)
   - Semantic version bump justification (MAJOR/MINOR/PATCH)
   - Review & approval by at least one additional maintainer
3. Versioning Rules:
   - MAJOR: Breaking module interfaces, removal or redefinition of a Core Principle
   - MINOR: New principle, new mandatory workflow gate, additive observable field
   - PATCH: Wording clarifications, non-normative editorial fixes
4. Compliance Review: Quarterly (or pre-release) audit of SPDX headers, security tests, logging coverage, and dependency
   integrity.
5. Exception Handling: Temporary deviations MUST include an issue link + expiration condition; unresolved exceptions
   block release.
6. Archival: Superseded versions retained in VCS history; no in-place edits to historical versions.

**Version**: v1.1.0 | **Ratified**: 2025-09-28 | **Last Amended**: 2025-10-01
