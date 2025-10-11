# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

# Captive Portal Addon

Home Assistant addon for rental guest network captive portal with TP-Omada controller integration.

## Features

- Automated network access provisioning based on rental booking windows
- Manual voucher creation for immediate access grants
- Configurable captive portal themes
- Comprehensive audit logging
- Adaptive queue processing for high-demand scenarios
- TP-Omada controller integration (pluggable architecture)
- Rate limiting and security controls
- Metrics export for monitoring

## Installation

This addon is designed to be installed through the Home Assistant Add-on Store.

1. Navigate to **Supervisor** → **Add-on Store** in your Home Assistant instance
2. Add this repository URL (if not using official store)
3. Find **Captive Portal** in the add-on list
4. Click **Install**
5. Wait for the installation to complete

## Configuration

### Basic Configuration

Configure the addon through the **Configuration** tab in the Home Assistant UI:

```yaml
controller:
  type: omada                          # Controller type (currently: omada)
  url: https://192.168.1.10:8043      # Controller URL
  username: admin                      # Controller admin username
  password: !secret omada_password    # Controller admin password
  site_name: Default                   # Omada site name (optional, default: "Default")

theme:
  portal_title: "Guest Network Access" # Title shown on splash page
  background_color: "#f5f5f5"          # Background color (hex format)
  primary_color: "#007bff"             # Primary accent color (hex format)
  logo_url: ""                         # URL to custom logo (optional)

log_level: info                        # Logging level: debug|info|warning|error|critical
```

### Controller Configuration

#### TP-Omada Controller

The addon requires a TP-Omada controller (hardware or software) with API access:

- **URL**: Full HTTPS URL to your Omada controller (e.g., `https://192.168.1.10:8043`)
- **Credentials**: Admin credentials with voucher management permissions
- **Site Name**: The site name in your Omada controller (defaults to "Default")
- **API Version**: Compatible with Omada Controller v5.x API

**Security Note**: Use Home Assistant secrets for the controller password:
1. Edit your `secrets.yaml` file
2. Add entry: `omada_password: your_actual_password`
3. Reference in config: `password: !secret omada_password`

### Theme Configuration

Customize the captive portal appearance for your guests:

- **portal_title**: Text displayed at the top of the login page
- **background_color**: Page background color (hex format: #RRGGBB)
- **primary_color**: Button and accent color (hex format: #RRGGBB)
- **logo_url**: Optional URL to a logo image (PNG/JPG, recommended size: 200x80px)

**Theme Fallback**: If custom assets (logo) fail to load, the addon automatically falls back to default styling and logs a warning.

### Advanced Configuration

Additional settings can be configured via the addon options (optional):

- **Grace Period**: Time (in seconds) after booking end before revoking access (default: 300)
- **Queue Concurrency**: Adaptive queue scaling range (default: 2-5 concurrent operations)
- **Retry Policy**: Controller connection retry attempts and backoff (default: exponential backoff, max 5 retries)

## Usage

### Integration with Rental Control

The addon automatically provisions guest access when:

1. A booking is created in the Rental Control integration
2. The booking start time is reached
3. The addon receives the booking event with guest credentials

**Required Rental Control Fields**:
- Guest username
- Guest password/credential
- Check-in date/time
- Check-out date/time

The addon will:
- Create a pending access grant when the booking is created
- Activate the grant at check-in time
- Automatically revoke access after check-out + grace period

### Manual Voucher Creation

For ad-hoc access (maintenance, contractors, etc.), create vouchers via the admin panel:

1. Navigate to **Supervisor** → **Captive Portal** → **Open Web UI**
2. Authenticate with Home Assistant credentials
3. Click **Vouchers** → **Create Voucher**
4. Fill in:
   - **Code/Token**: Unique voucher identifier (auto-generated or custom)
   - **Duration**: How long the voucher is valid (hours)
   - **Note**: Optional description (e.g., "HVAC technician visit")
5. Click **Create**

The voucher is immediately active and can be used on the captive portal splash page.

### Modifying Access Grants

Extend or shorten existing grants via the admin panel or API:

**Via Admin Panel**:
1. Navigate to **Access Grants**
2. Select the grant to modify
3. Choose action:
   - **Extend**: Add additional time
   - **Shorten**: Reduce end time (clamped to current time minimum)
   - **Force Terminate**: Immediately revoke access

**Via API**:
```bash
# Extend grant by 2 hours
curl -X PATCH http://homeassistant.local:8000/api/grants/{grant_id}/extend \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"additional_hours": 2}'

# Shorten grant to specific end time
curl -X PATCH http://homeassistant.local:8000/api/grants/{grant_id}/shorten \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"new_end_at": "2025-01-27T15:00:00Z"}'

# Force terminate
curl -X POST http://homeassistant.local:8000/api/grants/{grant_id}/terminate \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Audit Logging

All lifecycle events are logged to the audit trail:

- Grant created/activated/expired/revoked
- Voucher created/used/expired
- Theme updates
- Extension/shortening operations
- Force terminations
- Failed authentication attempts

Access the audit log via:
1. **Admin Panel**: **Audit** → **Event Log**
2. **API**: `GET /api/audit?event_type=grant_activated&since=2025-01-01`

### Metrics and Monitoring

The addon exports Prometheus-compatible metrics at `/metrics`:

- `active_grants_total`: Current number of active access grants
- `queue_depth`: Pending provisioning operations
- `provision_latency_seconds`: Time to provision grants (p50, p95, p99)
- `failed_provisions_total`: Count of failed controller operations
- `portal_requests_total`: Splash page request count
- `credential_attempts_total`: Authentication attempts (success/failure)

Configure Prometheus or Home Assistant's built-in metrics scraper to collect these.

## Adaptive Queue Processing

The addon uses an adaptive concurrency model to handle burst provisioning efficiently while preventing controller overload.

### Algorithm Design

The adaptive queue scheduler dynamically adjusts the number of concurrent provisioning operations based on real-time performance metrics:

**Initial State**:
- Concurrency: 2 parallel operations
- Latency window: Last 20 completed operations
- Measurement: Rolling average of provisioning latency

**Scaling Rules**:

1. **Scale Up** (increase concurrency):
   - **Condition**: Average latency < 200ms over last 20 operations
   - **Action**: Increment concurrency by 1 (max: 5)
   - **Rationale**: Controller is responding quickly, can handle more load
   - **Rate**: Check every 10 operations to avoid thrashing

2. **Scale Down** (decrease concurrency):
   - **Condition**: Average latency > 400ms over last 20 operations
   - **Action**: Decrement concurrency by 1 (min: 2)
   - **Rationale**: Controller is under stress, reduce load
   - **Rate**: Check every 5 operations (faster response to overload)

**Bounds**:
- Minimum concurrency: 2 (ensures reasonable throughput)
- Maximum concurrency: 5 (prevents overwhelming small controllers)
- Configurable via `QUEUE_MIN_CONCURRENCY` and `QUEUE_MAX_CONCURRENCY` environment variables (future)

### Use Cases

**High-Demand Scenario** (property turnover):
- Multiple guests check in simultaneously
- Initial concurrency: 2
- If controller responds quickly (< 200ms), scale to 3, then 4, then 5
- All grants provisioned rapidly without timeout

**Controller Stress** (slow network, high load):
- Provisioning latency increases to 450ms
- Queue scales down to prevent overwhelming controller
- Maintains stability at reduced throughput

**Mixed Workload**:
- Queue continuously adapts to changing conditions
- Automatic recovery from temporary slowdowns

### Observability

Queue scaling decisions are fully observable:

**Structured Logs**:
```json
{
  "event": "queue_scaled_up",
  "old_concurrency": 2,
  "new_concurrency": 3,
  "avg_latency_ms": 180.5,
  "window_size": 20,
  "timestamp": "2025-01-26T10:30:00Z"
}
```

**Metrics**:
- `queue_concurrency_current`: Current concurrency level (gauge)
- `queue_scaling_events_total`: Count of scale up/down events (counter)
- `provision_latency_seconds`: Latency histogram (p50, p95, p99)
- `queue_depth`: Pending operations (gauge)

**Dashboard Integration**:
Monitor queue performance in Home Assistant or Prometheus/Grafana:
- Track scaling events over time
- Correlate latency with concurrency changes
- Alert on sustained high latency or queue depth

### Performance Targets

- **Provisioning Latency**: < 2s p95 (per constitution)
- **Portal Render**: < 300ms p95 server-side
- **Queue Adaptation**: Scale decision within 10-20 operations

### Configuration (Advanced)

Override default thresholds via environment variables (addon options):

```yaml
options:
  queue:
    min_concurrency: 2          # Minimum parallel operations
    max_concurrency: 5          # Maximum parallel operations
    scale_up_threshold_ms: 200  # Avg latency to trigger scale up
    scale_down_threshold_ms: 400 # Avg latency to trigger scale down
    latency_window_size: 20     # Rolling average window
```

## Security Model

The addon implements defense-in-depth security with multiple layers of protection.

### Authentication and Authorization

**Admin API** (Grant management, vouchers, theme, audit):
- **Requirement**: Valid Home Assistant long-lived access token
- **Validation**: Token verified against HA authentication system
- **Scope**: Full administrative access to all addon functions
- **Token Format**: `Authorization: Bearer <token>` header
- **Expiration**: Follows HA token policy (typically 10 years, but revocable)

**Portal Endpoints** (Splash page, credential submission):
- **Access**: Public (no authentication required)
- **Protection**: Rate limiting, credential validation only
- **Purpose**: Allow guest devices to authenticate for network access

**Internal APIs** (Health, metrics):
- **Exposure**: Container-local only (not exposed to external network)
- **Use Case**: HA supervisor monitoring, Prometheus scraping via internal network

### Rate Limiting

Portal credential submission is rate-limited to prevent brute-force attacks:

**Limits**:
- **Per IP Address**: 5 authentication attempts per 5 minutes
- **Lockout Duration**: 15 minutes after exceeding limit
- **Scope**: Applies to `/portal/authenticate` endpoint only
- **Bypass**: Admin API not rate-limited (already token-protected)

**Implementation**:
- In-memory sliding window counter per IP
- Automatic cleanup of expired entries
- Logged at `WARNING` level when triggered

**User Experience**:
- Friendly error message: "Too many attempts. Please try again in 15 minutes."
- Legitimate users rarely hit limit (5 attempts is generous for typos)

### Credential Security

**Storage**:
- Guest credentials stored hashed (bcrypt) in SQLite database
- Controller passwords encrypted by Home Assistant secrets system
- Access tokens (if used) stored with expiration timestamps

**Logging**:
- Credentials **never logged** in plaintext
- Automatic redaction of sensitive fields in structured logs
- Log examples:
  ```json
  {
    "event": "grant_created",
    "username": "guest123",
    "password": "[REDACTED]",
    "grant_id": "abc-123"
  }
  ```

**Transmission**:
- Controller communication over HTTPS with certificate validation
- Portal credential submission over HTTPS (when configured)
- No credentials in URL query parameters (POST body only)

### Network Isolation

**Container Security**:
- Addon runs in isolated Home Assistant supervisor container
- Minimal attack surface (no SSH, no unnecessary services)
- Read-only filesystem except `/data` volume

**Port Exposure**:
- **8000/tcp**: Web UI and portal (configurable in HA addon options)
- **No other ports exposed** by default
- Controller communication outbound-only (no incoming from controller)

**Firewall Recommendations**:
- Restrict 8000/tcp to local network (guest network + admin LAN)
- Block internet access to admin API endpoints (optional reverse proxy)
- Allow outbound HTTPS to controller IP/hostname

### Audit Logging

All security-relevant events are logged to the audit trail:

**Logged Events**:
- Grant provisioning (success/failure)
- Credential authentication attempts (success/failure)
- Rate limit triggers
- Admin API access (with actor)
- Force terminations
- Theme updates
- Configuration changes

**Audit Log Fields**:
```json
{
  "event_id": "uuid",
  "timestamp": "ISO 8601",
  "event_type": "grant_created",
  "actor": "admin_user_id or system",
  "subject_type": "grant",
  "subject_id": "grant_uuid",
  "old_values": {},
  "new_values": {},
  "source": "api|system|portal"
}
```

**Retention**:
- Audit logs retained indefinitely (or per configured policy)
- Immutable append-only storage
- Queryable via admin API with filters

### Threat Mitigation

**Credential Brute Force**:
- **Mitigation**: Rate limiting (5 attempts / 5 minutes)
- **Detection**: Audit log + metrics (`credential_attempts_total{result="failure"}`)
- **Response**: Automatic lockout, alerting via HA notifications (future)

**Expired Credential Reuse**:
- **Mitigation**: Explicit expiry checks before authentication
- **Detection**: Logged as `expired_credential_rejected` event
- **Response**: User-friendly error, audit log entry

**Session Hijacking**:
- **Mitigation**: Short-lived access tokens (if applicable)
- **Detection**: Monitor for unusual access patterns (IP changes)
- **Response**: Token revocation, force re-authentication

**Controller Credential Leak**:
- **Mitigation**: Encrypted storage via HA secrets, HTTPS-only transmission
- **Detection**: Monitor for unauthorized controller access (controller-side)
- **Response**: Rotate credentials via addon config update

**Rogue Device Reuse**:
- **Mitigation**: MAC address + credential binding (controller-dependent)
- **Detection**: Audit log of device authorizations
- **Response**: Manual revocation via admin panel

**Timing Attacks**:
- **Mitigation**: Constant-time comparison for credential validation
- **Detection**: Statistical analysis of authentication latency (advanced)
- **Response**: N/A (prevented by design)

### Compliance Considerations

**GDPR / Privacy**:
- Minimal PII storage (username, booking dates only)
- No tracking of browsing activity post-authentication
- Audit logs contain operational data, not personal browsing data
- Right to erasure: Revoke grant + purge audit logs (manual process)

**PCI-DSS** (if applicable):
- No payment card data stored
- Network segmentation recommended (guest network isolated)

**SPDX Licensing**:
- All source files include SPDX headers (compliance requirement)
- License violations detected by pre-commit hooks

### Security Testing

**Automated Tests**:
- `T049`: Unauthorized access to admin API rejected (401/403)
- `T051`: Rate limiting triggers and lockout reset after cooldown
- `T053`: Log redaction (no raw secrets in logs)

**Manual Security Review**:
- See `addon/docs/SECURITY_REVIEW.md` for detailed checklist
- Conducted pre-release and quarterly (per constitution)

### Reporting Security Issues

If you discover a security vulnerability:

1. **Do NOT** open a public GitHub issue
2. Email security contact: `tykeal@bardicgrove.org`
3. Include:
   - Description of vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
4. Allow 90 days for patch before public disclosure

**Response SLA**:
- Acknowledgment: 48 hours
- Initial assessment: 7 days
- Patch (if confirmed): 30 days (critical), 90 days (non-critical)

## Troubleshooting

### Grant Stuck in "Pending" Status

**Symptoms**: Grant created but never activates

**Possible Causes**:
1. Controller unreachable
2. Invalid controller credentials
3. Network firewall blocking addon → controller communication

**Resolution**:
1. Check addon logs: **Supervisor** → **Captive Portal** → **Logs**
2. Look for connection errors or retry attempts
3. Verify controller URL and credentials in config
4. Test controller API access manually:
   ```bash
   curl -k https://your-controller-url:8043/api/info
   ```
5. Check firewall rules between Home Assistant and controller

### Portal Page Not Loading

**Symptoms**: Guests cannot access splash page

**Possible Causes**:
1. Addon not started
2. Port 8000 not accessible
3. Theme rendering error

**Resolution**:
1. Verify addon status: **Supervisor** → **Captive Portal** (should show "Started")
2. Check port mapping: Ensure 8000/tcp is exposed
3. Review logs for template rendering errors
4. Try reverting to default theme (remove custom logo_url)

### Credentials Not Working on Portal

**Symptoms**: Valid credentials rejected

**Possible Causes**:
1. Grant expired
2. Credential not yet provisioned to controller
3. Controller provisioning failed

**Resolution**:
1. Check grant status in admin panel (should be "active")
2. Verify controller shows the voucher/client in its UI
3. Check audit log for provisioning errors
4. Manually retry provisioning via admin panel

### High Provisioning Latency

**Symptoms**: Slow grant activation, queue backlog

**Possible Causes**:
1. Controller performance issues
2. Network latency to controller
3. Adaptive queue scaled down due to errors

**Resolution**:
1. Check metrics: `/metrics` → `provision_latency_seconds`
2. Review queue scaling logs for scale-down events
3. Verify controller performance (CPU, memory)
4. Consider reducing concurrent bookings or pre-provisioning

### Missing Metrics

**Symptoms**: `/metrics` endpoint returns no data

**Possible Causes**:
1. Metrics exporter not initialized
2. Addon restart cleared in-memory metrics

**Resolution**:
1. Restart addon: **Supervisor** → **Captive Portal** → **Restart**
2. Verify metrics endpoint: `curl http://homeassistant.local:8000/metrics`
3. Check logs for metrics_exporter service errors

## API Reference

### Grants

- `GET /api/grants` - List all access grants (with filters)
- `GET /api/grants/{id}` - Get specific grant details
- `POST /api/grants` - Create grant (from Rental Control event)
- `PATCH /api/grants/{id}/extend` - Extend grant duration
- `PATCH /api/grants/{id}/shorten` - Shorten grant duration
- `POST /api/grants/{id}/terminate` - Force terminate grant

### Vouchers

- `GET /api/vouchers` - List vouchers
- `POST /api/vouchers` - Create new voucher
- `DELETE /api/vouchers/{id}` - Revoke voucher

### Audit

- `GET /api/audit` - Query audit events (filterable by type, date, subject)

### Theme

- `GET /api/theme` - Get current theme config
- `POST /api/theme` - Update theme settings

### Health

- `GET /api/health` - Health check (queue depth, controller status)

### Portal

- `GET /portal` - Captive portal splash page
- `POST /portal/authenticate` - Submit credentials for authentication

Full OpenAPI specification available at: `/docs` (Swagger UI)

## Development

### Adding a New Controller Adapter

See [docs/CONTROLLER_ADAPTER.md](docs/CONTROLLER_ADAPTER.md) for detailed guide.

### Running Tests

```bash
cd addon
uv sync
uv run pytest
```

### Code Quality

```bash
# Format
uv run ruff format

# Lint
uv run ruff check --fix

# Type check
uv run mypy src/

# Coverage
uv run pytest --cov=src --cov-report=html
```

## Support

- **Issues**: [GitHub Issues](https://github.com/tykeal/homeassistant-captive-portal/issues)
- **Documentation**: [Full Documentation](https://github.com/tykeal/homeassistant-captive-portal/tree/main/docs)
- **Home Assistant Community**: [Forum Thread](https://community.home-assistant.io/)

## License

Apache-2.0 - See [LICENSE](../LICENSE) for details
