<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->
# Feature Specification: Captive Portal Addon for Rental Guest Network Access

**Feature Branch**: `001-create-captive-portal`
**Created**: 2025-09-28
**Status**: Draft
**Input**: User description: "Create captive portal for rental guest access to the network. It must be pluggable for multiple backend network controllers with TP-Omada as the initial implementation target. It shall have an administration interface that allows for theming, viewing of current access grants, modification of access grants, creation of vouchers for additional flexibilty to provide access grants. Primary access grants will be obtained from the Rental Control integration of Home Assistant and will gain the username, password, and length of stay from Rental Control. There will be an API for modifying the access grant in cases where the length of a guest stay changes (either increases or decreases in length). The portal shall run as a Home Assistant addon (container) and the administration interface will be the webportal that is exposed to Home Assistant."

## Execution Flow (main)
```
1. Parse user description from Input
   → If empty: ERROR "No feature description provided"
2. Extract key concepts from description
   → Identify: actors, actions, data, constraints
3. For each unclear aspect:
   → Mark with [NEEDS CLARIFICATION: specific question]
4. Fill User Scenarios & Testing section
   → If no clear user flow: ERROR "Cannot determine user scenarios"
5. Generate Functional Requirements
   → Each requirement must be testable
   → Mark ambiguous requirements
6. Identify Key Entities (if data involved)
7. Run Review Checklist
   → If any [NEEDS CLARIFICATION]: WARN "Spec has uncertainties"
   → If implementation details found: ERROR "Remove tech details"
8. Return: SUCCESS (spec ready for planning)
```

---

## ⚡ Quick Guidelines
- ✅ Focus on WHAT users need and WHY
- ❌ Avoid HOW to implement (no tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

### Section Requirements
- **Mandatory sections**: Must be completed for every feature
- **Optional sections**: Include only when relevant to the feature
- When a section doesn't apply, remove it entirely (don't leave as "N/A")

### For AI Generation
When creating this spec from a user prompt:
1. **Mark all ambiguities**: Use [NEEDS CLARIFICATION: specific question] for any assumption you'd need to make
2. **Don't guess**: If the prompt doesn't specify something (e.g., "login system" without auth method), mark it
3. **Think like a tester**: Every vague requirement should fail the "testable and unambiguous" checklist item
4. **Common underspecified areas**:
   - User types and permissions
   - Data retention/deletion policies
   - Performance targets and scale
   - Error handling behaviors
   - Integration requirements
   - Security/compliance needs

---

## User Scenarios & Testing *(mandatory)*

### Primary User Story
A property host using Home Assistant with the Rental Control integration wants guests to receive temporary, policy-
bounded Wi-Fi access through a captive portal that automatically provisions and revokes credentials aligned with
their stay. The host can also manually create short-term vouchers (e.g., maintenance crew) outside Rental Control
but still manage them centrally.

### Acceptance Scenarios
1. **Given** a new rental booking exists in Rental Control with guest name, start/end dates, **When** the booking start
   time is reached, **Then** a corresponding network access grant becomes available in the captive portal.
2. **Given** an active guest access grant, **When** the stay end time passes, **Then** the captive portal revokes the
   associated credentials within a defined grace period.
3. **Given** a host accesses the admin interface, **When** they create a voucher with a custom duration, **Then** the
   voucher appears in the active grants list with an expiry timestamp.
4. **Given** an existing guest stay is extended in Rental Control, **When** the new end date is updated via the portal
   API, **Then** the access grant expiry adjusts accordingly and logs an audit event.
5. **Given** the host applies a new theme configuration, **When** a guest next loads the splash page, **Then** the
   updated branding and style are rendered.

### Edge Cases
- Stay shortened after credentials were already issued → access must end at revised time (with minimal propagation lag)
- Voucher overlap with a Rental Control derived grant for the same user/device → system must treat them independently
- Theme misconfiguration (missing assets) → portal should fall back to a default safe theme and log a warning
- Network controller temporarily unreachable during provisioning → retry with backoff; mark grant in pending state
- Guest attempts reuse of expired credentials → denied with user-friendly message
- Large bursts of new arrivals at same timestamp (scalability) → queue operations without blocking UI
- Conflict: attempt to reduce stay length below current time → clamp to now and warn host


## Requirements *(mandatory)*

### Functional Requirements
- **FR-001**: System MUST obtain guest access grant inputs (username, password/credential, stay start, stay end) from Rental Control integration events.
- **FR-002**: System MUST provision network access on TP-Omada controller using the mapped credentials when a stay starts.
- **FR-003**: System MUST revoke or disable corresponding network access within a grace period after stay end.
- **FR-004**: System MUST support extension and contraction of an existing access grant via an authenticated admin/API request.
- **FR-005**: System MUST provide an administration web interface inside Home Assistant (iframe/webpanel) to view active, pending, expired, and voucher-based grants.
- **FR-006**: System MUST allow creation of manual vouchers with custom duration and optional note.
- **FR-007**: System MUST allow theming (logo, primary color, background, title text) for the guest splash/login page.
- **FR-008**: System MUST log all lifecycle events (create, extend, shorten, revoke, voucher create, voucher expire) with timestamp and actor/source.
- **FR-009**: System MUST present a captive portal splash page that validates credentials and transitions to authorized state.
- **FR-010**: System MUST mark provisioning attempts as pending and retry (with backoff) if the network controller is unreachable.
- **FR-011**: System MUST isolate plugin logic for different network controllers (pluggable backend) without code changes to core logic.
- **FR-012**: System MUST expose an API endpoint to adjust an existing grant end time.
- **FR-013**: System MUST allow administrators to force terminate (immediate revoke) an active grant at any time; otherwise normal shortening clamps to now with a warning.
- **FR-014**: System MUST fall back to a default theme if a configured theme asset is missing.
- **FR-015**: System MUST differentiate between Rental Control derived grants and voucher grants in UI and logs.
- **FR-016**: System MUST handle burst creation of multiple grants concurrently without UI timeouts.
- **FR-017**: System MUST provide a read-only audit view/filter for lifecycle events.
- **FR-018**: System MUST ensure expired credentials cannot be reused (deny & user-friendly message).
- **FR-019**: System MUST allow revocation of a grant prior to natural expiry via admin action.
- **FR-020**: System MUST queue provisioning tasks to avoid blocking HA main thread (NEEDS CLARIFICATION: specific queue or scheduling constraints?).

*Ambiguities flagged for clarification: FR-020 scheduling/queueing mechanics.*

### Key Entities *(include if feature involves data)*
- **AccessGrant**: Represents time-bounded network access derived from Rental Control (fields: id, source=RentalControl, username, secret/credential, start_at, end_at, status[pending|active|revoking|revoked|error], controller_type, controller_ref, created_at, updated_at).
- **Voucher**: Manually created discretionary access grant (fields: id, code/token, created_by, note, start_at, end_at, status, controller_ref(optional when provisioned), theme_snapshot(optional)).
- **ThemeConfig**: Current branding definitions (fields: id/version, logo_asset_ref, primary_color, background_style, title_text, updated_at, updated_by).
- **EventLogEntry**: Audit trail record (fields: id, event_type, subject_type, subject_id, actor, old_values, new_values, timestamp, source [system|admin|api]).


## Clarifications

### Outstanding Ambiguities
- FR-020: What scheduling/queue constraint (e.g., max parallel provisioning jobs) should be enforced for controller operations? [NEEDS CLARIFICATION]

### Session 2025-09-28
- Q: Should administrators be able to forcefully shorten (immediate terminate) an active grant at any time? → A: Allow force terminate anytime; revoke immediately and log reason


---

## Review & Acceptance Checklist
*GATE: Automated checks run during main() execution*

### Content Quality
- [ ] No implementation details (languages, frameworks, APIs)
- [ ] Focused on user value and business needs
- [ ] Written for non-technical stakeholders
- [ ] All mandatory sections completed

### Requirement Completeness
- [ ] No [NEEDS CLARIFICATION] markers remain
- [ ] Requirements are testable and unambiguous
- [ ] Success criteria are measurable
- [ ] Scope is clearly bounded
- [ ] Dependencies and assumptions identified

---

## Execution Status
*Updated by main() during processing*

- [ ] User description parsed
- [ ] Key concepts extracted
- [ ] Ambiguities marked
- [ ] User scenarios defined
- [ ] Requirements generated
- [ ] Entities identified
- [ ] Review checklist passed

---
