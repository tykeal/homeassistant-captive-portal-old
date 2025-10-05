<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->
# Quickstart Test Scenarios: Captive Portal Addon

**Feature**: Rental Guest Network Access
**Purpose**: Manual validation scenarios for end-to-end functionality testing
**Last Updated**: 2025-01-26
**Status**: Ready for validation (T047)

## Validation Status

These scenarios are designed for manual execution to validate the addon in a real Home Assistant environment with an actual TP-Omada controller. The automated test suite (Phases 3.2-3.5) provides comprehensive coverage of core functionality, but these scenarios validate:

- Real controller integration (not mocked)
- Home Assistant addon lifecycle (install, configure, restart)
- Actual network device authentication
- End-to-end user workflows

### Validation Checklist

Execute each scenario below and check off when validated:

- [ ] Scenario 1: Rental Control Grant Lifecycle
- [ ] Scenario 2: Manual Voucher Creation
- [ ] Scenario 3: Theme Customization
- [ ] Scenario 4: Network Controller Unreachable
- [ ] Scenario 5: Burst Provisioning (Adaptive Queue)
- [ ] Scenario 6: Expired Credential Reuse Prevention
- [ ] Scenario 7: Grant Stay Modification (Extension & Contraction)
- [ ] Scenario 8: Multi-Controller Compatibility (Future)
- [ ] Performance Benchmarks
- [ ] Security Checklist

**Instructions for Validation**:
1. Set up a test Home Assistant instance (VM or dedicated hardware)
2. Install TP-Omada controller (or use existing)
3. Install Rental Control integration (or use test data)
4. Install this addon from local build
5. Execute each scenario in order
6. Document results (pass/fail, observations, issues)
7. Update this checklist
8. File issues for any failures

**Expected Outcome**: All scenarios should pass before marking T047 complete.

## Prerequisites

- Home Assistant OS with Supervisor
- Rental Control integration installed and configured
- TP-Omada controller accessible (or mock/stub)
- Captive Portal addon installed from local build
- Test device(s) for portal access validation

## Scenario 1: Rental Control Grant Lifecycle

**Objective**: Verify automatic grant provisioning and revocation based on Rental Control booking

### Setup
1. Configure Rental Control with a test booking:
   - Guest name: "Test Guest Alpha"
   - Check-in: Current time + 5 minutes
   - Check-out: Current time + 2 hours
   - Generated credentials: username `guest_alpha`, password `test_pass_123`

### Execution Steps
1. **Pending State Observation**
   - Access addon admin panel in HA
   - Navigate to "Access Grants" view
   - Verify grant appears with status `pending`
   - Note: username, start time, end time displayed

2. **Activation at Start Time**
   - Wait for booking start time (or adjust system clock)
   - Refresh grants view
   - Verify grant status changes to `active`
   - Check audit log for `grant_activated` event

3. **Portal Access with Active Credentials**
   - Connect test device to guest network
   - Captive portal should redirect to splash page
   - Enter username: `guest_alpha`, password: `test_pass_123`
   - Verify successful authentication
   - Confirm device gains network access

4. **Extension Scenario** (optional)
   - Use admin API to extend grant by 1 hour
   - Verify updated end_at timestamp in grants view
   - Check audit log for `grant_extended` event

5. **Automatic Revocation at End**
   - Wait for original or extended end time + grace period
   - Verify grant status changes to `revoked` or `expired`
   - Check audit log for `grant_expired` event
   - Confirm device loses network access (portal re-prompts)

### Expected Outcomes
- ✅ Grant lifecycle: pending → active → expired/revoked
- ✅ Credentials work only during active period
- ✅ Audit log captures all state transitions
- ✅ Admin panel reflects current grant status

---

## Scenario 2: Manual Voucher Creation

**Objective**: Verify host can create ad-hoc vouchers independent of Rental Control

### Setup
No Rental Control booking required

### Execution Steps
1. **Create Voucher via Admin Panel**
   - Navigate to "Vouchers" section
   - Click "Create Voucher"
   - Fill form:
     - Code: `MAINT2025`
     - Duration: 4 hours
     - Note: "Maintenance crew access"
   - Submit

2. **Voucher Appears in Active Grants**
   - Navigate to "Access Grants" view
   - Verify voucher appears with:
     - Source: `Voucher`
     - Code: `MAINT2025`
     - Status: `active` (or `pending` if future start time supported)
     - End time: now + 4 hours

3. **Portal Access with Voucher**
   - Connect test device to guest network
   - Enter voucher code: `MAINT2025`
   - Verify authentication success
   - Confirm device network access

4. **Manual Revocation**
   - Return to admin panel
   - Select voucher in grants list
   - Click "Revoke" / "Force Terminate"
   - Confirm action

5. **Immediate Access Revocation**
   - Verify grant status changes to `revoked`
   - Check audit log for `grant_force_terminated` event with admin actor
   - Confirm device loses network access immediately

### Expected Outcomes
- ✅ Voucher creation succeeds
- ✅ Voucher credentials grant access
- ✅ Manual revocation works immediately
- ✅ Voucher differentiated from Rental Control grants in UI

---

## Scenario 3: Theme Customization

**Objective**: Verify splash page theming updates

### Setup
Prepare custom theme assets:
- Logo: `custom_logo.png` (200x80px)
- Primary color: `#3498db` (blue)
- Background: Light gradient
- Title text: "Welcome to Sunset Rentals Guest Wi-Fi"

### Execution Steps
1. **Apply Theme via Admin Panel**
   - Navigate to "Theme Settings"
   - Upload logo asset
   - Set primary color to `#3498db`
   - Set title text
   - Submit changes

2. **Verify Theme Applied**
   - Open splash page in incognito browser
   - Confirm:
     - Logo displays correctly
     - Primary color applied to buttons/headers
     - Title text matches custom value

3. **Theme Fallback Test**
   - Manually corrupt/remove logo asset file (via SSH/console)
   - Reload splash page
   - Verify default logo appears (fallback behavior)
   - Check logs for theme asset warning

### Expected Outcomes
- ✅ Theme changes apply to splash page
- ✅ Missing assets fall back gracefully
- ✅ Theme config persists across addon restarts

---

## Scenario 4: Network Controller Unreachable

**Objective**: Verify retry/backoff behavior when TP-Omada controller is unavailable

### Setup
1. Configure addon with TP-Omada controller endpoint
2. Temporarily block network access to controller (firewall rule or stop service)

### Execution Steps
1. **Create Grant with Controller Offline**
   - Trigger new Rental Control booking or create voucher
   - Observe grant created in admin panel

2. **Pending State Due to Provisioning Failure**
   - Verify grant status remains `pending`
   - Check logs for controller connection errors
   - Verify retry attempts with backoff (e.g., 1s, 2s, 4s, 8s)

3. **Restore Controller Access**
   - Remove firewall rule / restart controller service
   - Wait for next retry attempt

4. **Automatic Recovery**
   - Verify grant transitions to `active` once controller responds
   - Check audit log for delayed activation event
   - Confirm metrics show failed_provisions count (before recovery)

### Expected Outcomes
- ✅ Grants remain pending when controller unavailable
- ✅ Retry logic with exponential backoff executes
- ✅ Automatic recovery when controller restored
- ✅ Metrics reflect provisioning failures

---

## Scenario 5: Burst Provisioning (Adaptive Queue)

**Objective**: Verify adaptive queue handles burst grant creation

### Setup
Configure Rental Control with 10 simultaneous bookings starting at same time

### Execution Steps
1. **Trigger Burst Creation**
   - Import 10 bookings with identical start time (now + 1 minute)
   - Wait for start time

2. **Observe Queue Behavior**
   - Monitor addon logs for queue scaling messages
   - Expected pattern:
     - Initial concurrency: 2
     - If avg latency < 200ms over last 20 jobs: scale to 3, then 4, then 5
     - If avg latency > 400ms: scale back down

3. **Verify Provisioning Latency**
   - Check metrics for `provision_latency` p95
   - Confirm < 2s per grant (non-functional requirement)

4. **Confirm All Grants Active**
   - Navigate to grants view
   - Verify all 10 grants transitioned to `active`
   - Audit log shows all provisions successful

### Expected Outcomes
- ✅ Adaptive queue scales concurrency (2→5) based on latency
- ✅ All grants provisioned without UI timeout
- ✅ Metrics exported for queue_depth, provision_latency
- ✅ Logs show queue scaling decisions

---

## Scenario 6: Expired Credential Reuse Prevention

**Objective**: Verify expired credentials are rejected

### Setup
1. Create voucher with 10-minute duration
2. Use voucher to authenticate device
3. Wait for expiry (or manually expire via DB or API)

### Execution Steps
1. **Access with Active Credential**
   - Connect device, submit voucher code
   - Verify access granted

2. **Wait for Expiry**
   - Allow voucher to expire naturally or force expire
   - Verify grant status changes to `expired`

3. **Attempt Reuse of Expired Credential**
   - Disconnect and reconnect device (or clear auth state)
   - Submit same voucher code on splash page

4. **Verify Rejection**
   - Portal displays user-friendly error: "This credential has expired"
   - Device remains unauthorized (no network access)
   - Audit log records `expired_credential_rejected` event

### Expected Outcomes
- ✅ Expired credentials denied access
- ✅ User-friendly error message displayed
- ✅ Audit log captures rejection event
- ✅ No security bypass via credential reuse

---

## Scenario 7: Grant Stay Modification (Extension & Contraction)

**Objective**: Verify API for adjusting grant duration

### Setup
Active grant (from Rental Control or voucher) with end_at = now + 2 hours

### Execution Steps
1. **Extend Grant**
   - API request: `PATCH /api/grants/{id}/extend` with `additional_hours: 2`
   - Response: 200 OK with updated grant
   - Verify end_at extended by 2 hours
   - Audit log: `grant_extended` event

2. **Shorten Grant (Future End Time)**
   - API request: `PATCH /api/grants/{id}/shorten` with `new_end_at: now + 1 hour`
   - Response: 200 OK
   - Verify end_at updated to now + 1 hour
   - Audit log: `grant_shortened` event

3. **Attempt Shorten to Past (Clamp Behavior)**
   - API request: `PATCH /api/grants/{id}/shorten` with `new_end_at: now - 1 hour`
   - Response: 200 OK with warning
   - Verify end_at clamped to `now` (immediate expiry)
   - Audit log: `grant_shortened` with warning flag

4. **Force Terminate**
   - API request: `POST /api/grants/{id}/terminate`
   - Response: 200 OK
   - Verify status immediately changes to `revoked`
   - Device loses access instantly
   - Audit log: `grant_force_terminated`

### Expected Outcomes
- ✅ Extension API works correctly
- ✅ Shortening updates end time
- ✅ Past timestamps clamp to now with warning
- ✅ Force terminate revokes immediately
- ✅ All modifications logged in audit trail

---

## Scenario 8: Multi-Controller Compatibility (Future)

**Objective**: Verify pluggable controller architecture

### Setup
Addon configured with TP-Omada controller (current implementation)

### Execution Steps
1. **Verify Current Controller Works**
   - Create grant, verify TP-Omada provisioning succeeds

2. **Future: Add UniFi Controller Adapter**
   - Implement `UniFiAdapter` class extending `BaseController`
   - Configure addon with `controller_type: unifi`
   - Restart addon

3. **Verify Adapter Switch**
   - Create new grant
   - Verify provisioning uses UniFi API calls
   - Core logic (grant_manager, queue_scheduler) unchanged

### Expected Outcomes
- ✅ Controller adapters implement common interface
- ✅ Switching controllers requires config change only (no code edits)
- ✅ TP-Omada adapter functional as baseline

---

## Performance Benchmarks

### Provisioning Latency
- **Target**: < 2s p95
- **Measurement**: Create 50 grants, measure time from create to active
- **Pass Criteria**: 95th percentile < 2000ms

### Portal Render Time
- **Target**: < 300ms p95 server-side
- **Measurement**: 100 requests to splash page endpoint
- **Pass Criteria**: 95th percentile response time < 300ms

### Queue Adaptive Scaling
- **Target**: Latency threshold triggers scale: <200ms → scale up, >400ms → scale down
- **Measurement**: Monitor queue logs during burst provisioning
- **Pass Criteria**: Log entries show concurrency changes matching latency conditions

---

## Security Checklist

- [ ] Admin API endpoints reject unauthenticated requests (401/403)
- [ ] Rate limiting prevents credential brute force (e.g., 5 attempts / minute)
- [ ] Logs do not contain plaintext passwords or secrets
- [ ] Expired credentials cannot be reused
- [ ] Session tokens (if applicable) expire appropriately
- [ ] HTTPS enforced for admin panel (if configured)
- [ ] SPDX headers present in all source files

---

## Troubleshooting Common Issues

### Grant Stuck in Pending
- **Check**: Controller reachability (network, credentials)
- **Check**: Logs for retry attempts and error messages
- **Fix**: Verify controller config in addon options

### Portal Page Not Rendering
- **Check**: Theme asset paths in config
- **Check**: Logs for template rendering errors
- **Fix**: Revert to default theme or fix asset references

### Device Not Gaining Access After Auth
- **Check**: Controller provisioning success in logs
- **Check**: Grant status is `active` in admin panel
- **Check**: Device MAC/IP matches provisioned entry

### Metrics Not Exporting
- **Check**: Metrics endpoint `/metrics` returns data
- **Check**: Prometheus/HA scraper configured correctly
- **Fix**: Restart addon, verify metrics_exporter service initialized

---

## Post-Validation Checklist

After completing all scenarios:

- [ ] All grants lifecycle transitions work (pending → active → expired/revoked)
- [ ] Vouchers function independently of Rental Control
- [ ] Theme customization applies and falls back gracefully
- [ ] Controller retry/backoff handles unreachable scenarios
- [ ] Adaptive queue scales based on provisioning latency
- [ ] Expired credentials rejected with audit logging
- [ ] Extension/shortening/termination APIs functional
- [ ] Performance targets met (provision < 2s, render < 300ms)
- [ ] Security: auth required, rate limiting works, no credential leakage in logs
- [ ] Metrics exported and accurate

---

## Notes for Implementers

- Scenarios can be automated with pytest integration tests
- Mock controller adapter useful for CI/CD pipelines
- Theme assets should have fallback defaults in addon bundle
- Audit log filtering API critical for troubleshooting
- HA addon supervisor integration requires proper manifest (config.yaml)

**Status**: Ready for T047 manual validation
