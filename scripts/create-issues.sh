#!/usr/bin/env bash
# Create zeClock evolution issues on GitHub
# Usage: ./scripts/create-issues.sh
# Requires: gh CLI authenticated (gh auth login)

set -euo pipefail

REPO="DMDTools/zeClock"

echo "Creating labels..."
gh label create "priority: critical" --color "b60205" --description "Highest priority - blocking users" --repo "$REPO" 2>/dev/null || true
gh label create "priority: high" --color "d93f0b" --description "High priority - significant value" --repo "$REPO" 2>/dev/null || true
gh label create "priority: medium" --color "fbca04" --description "Medium priority - nice to have" --repo "$REPO" 2>/dev/null || true
gh label create "priority: low" --color "0e8a16" --description "Low priority - future improvement" --repo "$REPO" 2>/dev/null || true
gh label create "type: bug" --color "d73a4a" --description "Something isn't working" --repo "$REPO" 2>/dev/null || true
gh label create "type: feature" --color "a2eeef" --description "New feature or request" --repo "$REPO" 2>/dev/null || true
gh label create "type: tech-debt" --color "d4c5f9" --description "Technical debt reduction" --repo "$REPO" 2>/dev/null || true
gh label create "type: dx" --color "bfdadc" --description "Developer experience improvement" --repo "$REPO" 2>/dev/null || true

echo ""
echo "Creating issues..."

# Issue 1
gh issue create --repo "$REPO" \
  --title "feat: Automatic update system (OTA) for headless deployments" \
  --label "priority: critical,type: feature" \
  --body '## Summary

zeClock often runs on Raspberry Pi in autonomous 24/7 mode. There is currently no mechanism to check for or apply updates without SSH access.

## Proposed Solution

1. **Version check**: Periodically query the GitHub Releases API to detect new versions
2. **User notification**: Display a brief message on the DMD (e.g. "Update available: v0.2.0") and/or show a banner in the Web UI
3. **Optional auto-update**: Offer a config flag (`auto_update = true`) that triggers `pip install --upgrade` / `pipx upgrade` automatically
4. **Rollback safety**: Before updating, save the current version so the user can rollback if something breaks

## Acceptance Criteria

- [ ] `GET /api/update/check` returns `{current_version, latest_version, update_available}`
- [ ] Web UI "Settings" tab shows update status
- [ ] DMD notification when update is available (once per day, non-intrusive)
- [ ] Config option to enable/disable auto-update
- [ ] Graceful handling of network errors (no crash if GitHub is unreachable)

## Context

Referenced in TODO.md under "Automatic updates".'

echo "  [1/10] Created: OTA updates"

# Issue 2
gh issue create --repo "$REPO" \
  --title "bug: Cannot type letters in weather plugin postal code field (Canadian codes)" \
  --label "priority: critical,type: bug" \
  --body '## Bug Description

Canadian postal codes contain letters (e.g. `H2X 1Y4`, `V6B 3K9`). The weather plugin configuration field in the Web UI only accepts numeric input, making it impossible for Canadian users to configure their location via postal code.

## Steps to Reproduce

1. Open Web UI → Settings → Weather plugin
2. Try to type a Canadian postal code like `H2X 1Y4`
3. Letters are rejected / not entered

## Expected Behavior

The postal code field should accept alphanumeric characters (letters + digits + spaces).

## Proposed Fix

The input validation in the Web UI JavaScript likely uses a pattern like `[0-9]` or `type="number"`. Change to `type="text"` with a permissive pattern or remove the restrictive validation entirely (server-side geocoding will handle invalid inputs gracefully).

## Context

Documented in TODO.md as a known bug. Low effort fix with high user impact.'

echo "  [2/10] Created: Canadian postal codes"

# Issue 3
gh issue create --repo "$REPO" \
  --title "refactor: Convert clock display into a configurable plugin" \
  --label "priority: high,type: tech-debt" \
  --body '## Summary

The clock/time rendering is currently hardcoded in `clock.py` (~100+ lines of rendering logic, caching, color management). Converting it into a proper `ClockPlugin` would:

- Reduce `clock.py` complexity significantly (single responsibility)
- Enable configurable alternation between time, date, day of week, and name day (saint of the day)
- Make the clock consistent with the plugin architecture (same config, same lifecycle)
- Allow users to configure clock behavior via `plugins.yaml`

## Proposed Design

```yaml
plugins:
  - name: clock
    frequency: 0  # special: always shown between other plugins
    settings:
      show_date: true
      show_day_of_week: true
      show_name_day: true
      alternation_seconds: 3
      date_format: "%d/%m"
```

### Implementation Steps

1. Create `zeclock/plugins/clock_plugin.py` extending `PagedPlugin`
2. Move rendering logic from `clock.py._render_clock_frame()` into the plugin
3. Add date, day-of-week, and name-day rendering as additional pages
4. Update state machine in `clock.py` to use the plugin for clock display
5. Keep backward compatibility (clock still displays if no plugin config)

## Acceptance Criteria

- [ ] Clock rendering extracted into a plugin
- [ ] `clock.py` main loop simplified (no direct font/color rendering)
- [ ] Date and day-of-week display configurable
- [ ] Existing behavior unchanged when no explicit clock plugin config exists
- [ ] Tests pass with no regressions

## Context

Referenced in TODO.md under "Clock / Date Plugin".'

echo "  [3/10] Created: Clock as plugin"

# Issue 4
gh issue create --repo "$REPO" \
  --title "feat: Progressive Web App (PWA) for the Web UI" \
  --label "priority: high,type: feature" \
  --body '## Summary

The Web UI is currently a plain HTML/CSS/JS page served by aiohttp. Converting it to a PWA would significantly improve the mobile experience, especially for the speaker timer use case at conferences.

## Benefits

- **Installable** on phone/tablet home screen (full-screen, no browser chrome)
- **Offline capable** via Service Worker caching of static assets
- **Fast launch** for the speaker timer scenario (volunteer controls the timer from their phone)
- **Push notifications** possibility (timer finished, plugin forced, etc.)

## Implementation Steps

1. Add `manifest.json` with app name, icons, theme color, display mode
2. Create a Service Worker (`sw.js`) for static asset caching
3. Add appropriate `<link>` and `<meta>` tags to `index.html`
4. Create app icons (multiple sizes: 192x192, 512x512)
5. Ensure all API calls work when the app is installed (relative URLs)
6. Add install prompt handling in the UI

## Acceptance Criteria

- [ ] `manifest.json` present and valid
- [ ] Service Worker caches static assets (HTML, CSS, JS)
- [ ] App installable on Android (Chrome) and iOS (Safari)
- [ ] Speaker Timer functional when launched from home screen
- [ ] Lighthouse PWA audit passes

## Notes

The API endpoints remain server-dependent (requires network), but the UI shell and static assets should work offline.'

echo "  [4/10] Created: PWA"

# Issue 5
gh issue create --repo "$REPO" \
  --title "test: Add integration tests and code coverage reporting" \
  --label "priority: high,type: dx" \
  --body '## Summary

While the test suite is substantial (~37 test files, 500+ tests), the project lacks:
- Code coverage measurement and reporting
- Integration tests for the REST API
- End-to-end tests for the state machine lifecycle
- A minimum coverage threshold in CI

## Proposed Changes

### 1. Add coverage tooling

```toml
# pyproject.toml
[project.optional-dependencies]
dev = [
    ...
    "pytest-cov>=4.0",
]
```

### 2. REST API integration tests

Using `aiohttp.test_utils.TestClient` to test:
- All API endpoints (status, screen on/off, force plugin, text display)
- Speaker timer lifecycle (set → start → pause → reset)
- Configuration save/load cycle
- Error handling (invalid JSON, missing fields)

### 3. State machine integration tests

Test the full cycle: `CLOCK_ONLY → PLUGIN_SELECT → PLUGIN_ACTIVE → CLOCK_ONLY`
- Plugin activation and deactivation
- Forced plugin behavior
- Error recovery (5 consecutive errors → deactivation)

### 4. CI enforcement

```yaml
# .github/workflows/tests.yml
- name: Run tests with coverage
  run: pytest tests/ -v --tb=short --cov=zeclock --cov-report=xml --cov-fail-under=70
```

### 5. README badge

Add coverage badge via Codecov or similar service.

## Acceptance Criteria

- [ ] `pytest-cov` in dev dependencies
- [ ] Coverage report generated in CI
- [ ] Minimum 70% coverage threshold enforced
- [ ] At least 5 REST API integration tests
- [ ] At least 3 state machine lifecycle tests
- [ ] Coverage badge in README'

echo "  [5/10] Created: Test coverage"

# Issue 6
gh issue create --repo "$REPO" \
  --title "feat: Display rotation and flip support (--rotate, --flip)" \
  --label "priority: medium,type: feature" \
  --body '## Summary

Many physical ZeDMD setups have the display mounted upside down, sideways, or mirrored. Users need a software option to rotate/flip the output buffer before sending to hardware.

## Proposed Solution

### CLI Arguments

```bash
zeclock --rotate 180          # Rotate 180 degrees
zeclock --rotate 90           # Rotate 90 degrees clockwise
zeclock --flip horizontal     # Mirror horizontally
zeclock --flip vertical       # Mirror vertically
```

### Config File

```ini
[display]
rotate = 180
flip = horizontal
```

### Implementation

Apply transformation in `clock.py` main loop, just before `send_frame()`:

```python
# After brightness/dimming, before send
if self._rotate:
    frame = frame.rotate(self._rotate, expand=False)
if self._flip == "horizontal":
    frame = frame.transpose(Image.FLIP_LEFT_RIGHT)
elif self._flip == "vertical":
    frame = frame.transpose(Image.FLIP_TOP_BOTTOM)
```

## Acceptance Criteria

- [ ] `--rotate` CLI arg accepts 0, 90, 180, 270
- [ ] `--flip` CLI arg accepts `horizontal`, `vertical`
- [ ] Config file support in `[display]` section
- [ ] Works correctly in both SD (128x32) and HD (256x64) modes
- [ ] 90/270 rotation correctly swaps width/height for the display buffer
- [ ] No measurable performance impact (PIL transpose is fast)

## Context

Referenced in TODO.md under "Rotation / Flip".'

echo "  [6/10] Created: Rotation/Flip"

# Issue 7
gh issue create --repo "$REPO" \
  --title "feat: Health monitoring dashboard (uptime, plugin errors, diagnostics)" \
  --label "priority: medium,type: feature" \
  --body '## Summary

For headless Raspberry Pi deployments, it is difficult to know if zeClock is running correctly. A diagnostics API endpoint and Web UI page would provide visibility into the system health.

## Proposed Features

### API Endpoint: `GET /api/diagnostics`

```json
{
  "uptime_seconds": 86412,
  "version": "0.1.0",
  "latest_version": "0.2.0",
  "backend": {
    "type": "zedmd",
    "connected": true,
    "resolution": "256x64",
    "reconnections": 2
  },
  "plugins": {
    "total": 8,
    "active": 6,
    "failed": 1,
    "unconfigured": 1,
    "errors_last_hour": {"weather": 3, "stock": 0}
  },
  "brightness": {
    "mode": "auto",
    "current_hw": 7,
    "sw_dimming": 0,
    "time_only": false
  },
  "network": {
    "wifi_connected": true,
    "api_latency_ms": {"open-meteo": 234, "yahoo-finance": 512}
  },
  "system": {
    "cpu_temp": 52.3,
    "memory_used_mb": 128,
    "disk_free_mb": 4096
  }
}
```

### Web UI: "Health" Tab

- Visual indicators (green/yellow/red) for each subsystem
- Plugin error history (last 10 errors with timestamp)
- Uptime counter
- Network connectivity status
- Backend connection history

## Implementation Notes

- Track error counts per plugin (already partially done via `consecutive_errors`)
- Store reconnection events in a circular buffer
- Raspberry Pi system info via `/sys/class/thermal/` and `/proc/meminfo`
- Keep diagnostics lightweight (no database, in-memory only)

## Acceptance Criteria

- [ ] `GET /api/diagnostics` returns structured health data
- [ ] Web UI has a "Health" or "Status" tab
- [ ] Plugin error history tracked (last N errors)
- [ ] Backend reconnection count tracked
- [ ] Works on both RPi and desktop (graceful fallback for RPi-specific metrics)'

echo "  [7/10] Created: Health monitoring"

# Issue 8
gh issue create --repo "$REPO" \
  --title "feat: Custom RGB colors and per-plugin color themes" \
  --label "priority: medium,type: feature" \
  --body '## Summary

Currently, the color system is limited to a fixed palette of 8 named colors (`orange`, `blue`, `red`, etc.) applied globally. Users want:
- Custom RGB hex colors (`#FF6600`)
- Different colors per plugin
- Preview of color/font in the Web UI

## Proposed Changes

### 1. Custom RGB in CLI and Config

```bash
zeclock --color "#FF6600"
zeclock --color "rgb(255, 102, 0)"
```

```ini
[display]
color = #FF6600
```

### 2. Per-Plugin Color Override

```yaml
plugins:
  - name: weather
    settings:
      color: "#4A90D9"  # Weather in blue
  - name: stock
    settings:
      color: "#2ECC71"  # Stocks in green
  - name: pong
    settings:
      color: orange     # Named colors still work
```

### 3. Color Preview in Web UI

In the Settings tab, show a live preview of the selected color on a small DMD mockup.

## Implementation Notes

- Extend `COLOR_MAP` in `colors.py` to accept hex strings
- Parse `#RRGGBB` format in addition to named colors
- Pass color through `PluginContext` so plugins can access their configured color
- Fallback: if plugin has no color config, use the global color

## Acceptance Criteria

- [ ] `--color "#RRGGBB"` accepted in CLI
- [ ] Config file accepts hex color strings
- [ ] Per-plugin color override in `plugins.yaml`
- [ ] Web UI color picker (native `<input type="color">`)
- [ ] Backward compatible (named colors still work)
- [ ] Invalid color strings fall back to default orange'

echo "  [8/10] Created: Custom colors"

# Issue 9
gh issue create --repo "$REPO" \
  --title "docs: Plugin SDK documentation and scaffolding tool" \
  --label "priority: medium,type: dx" \
  --body '## Summary

The plugin architecture is well-designed (`ClockPlugin` ABC, `PagedPlugin`, `PluginHelpers`, `config_schema`), but the developer documentation is incomplete:
- `docs/plugin_authoring.md` is referenced in code comments but does not exist
- No template or example plugin for new contributors
- No CLI tool to scaffold a new plugin

## Proposed Deliverables

### 1. Plugin Authoring Guide (`docs/plugin_authoring.md`)

- How to create a plugin (step by step)
- Plugin lifecycle (discover → load → validate → initialize → render → cleanup)
- Available APIs (`PluginHelpers`, `PluginContext`, bitmap fonts, colors)
- Configuration schema system (`ConfigField` types, Web UI auto-generation)
- Testing your plugin (fixtures from `conftest.py`)
- Publishing and sharing (user plugin directory `~/.zeclock/plugins/`)

### 2. Example Plugin Template

```
examples/
  my_custom_plugin.py    # Minimal working example with comments
  my_paged_plugin.py     # PagedPlugin example with multiple pages
```

### 3. CLI Scaffolding Tool

```bash
zeclock create-plugin my-awesome-plugin
# Creates ~/.zeclock/plugins/my_awesome_plugin.py with boilerplate
```

### 4. API Version Documentation

Document `PLUGIN_API_VERSION` (currently "1.0") and the compatibility guarantee.

## Acceptance Criteria

- [ ] `docs/plugin_authoring.md` exists and is comprehensive
- [ ] At least 2 example plugin files in `examples/`
- [ ] `zeclock create-plugin <name>` CLI command works
- [ ] README links to the authoring guide
- [ ] `PLUGIN_API_VERSION` documented with SemVer policy'

echo "  [9/10] Created: Plugin SDK docs"

# Issue 10
gh issue create --repo "$REPO" \
  --title "feat: Docker support with docker-compose for easy deployment" \
  --label "priority: low,type: dx" \
  --body '## Summary

Add containerization support to simplify deployment, testing, and onboarding. Especially useful for:
- Trying zeClock without installing dependencies
- CI/CD testing in isolated environments
- Running in virtual mode on any machine
- Avoiding native library conflicts (`libzedmd`)

## Proposed Files

### `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install -e ".[dev]" && \
    python -m zeclock.installer --no-prompt

EXPOSE 8080 3000
CMD ["zeclock", "--backend", "dmdserver"]
```

### `docker-compose.yml`

```yaml
services:
  zeclock:
    build: .
    ports:
      - "8080:8080"   # Web UI / REST API
    environment:
      - ZECLOCK_BACKEND=dmdserver
      - ZECLOCK_COLOR=auto
    volumes:
      - zeclock-data:/root/.zeclock
    depends_on:
      - virtual-dmd

  virtual-dmd:
    build:
      context: .
      dockerfile: Dockerfile.virtual
    ports:
      - "3000:3000"   # Browser DMD renderer
      - "6789:6789"   # dmdserver port

  mosquitto:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
    profiles: ["mqtt"]

volumes:
  zeclock-data:
```

## Acceptance Criteria

- [ ] `docker build .` succeeds and produces a working image
- [ ] `docker compose up` starts zeClock + virtual DMD
- [ ] Browser at localhost:3000 shows the virtual DMD
- [ ] Web UI accessible at localhost:8080
- [ ] Optional MQTT broker via `docker compose --profile mqtt up`
- [ ] Documentation in README (quick start with Docker)

## Notes

- ARM builds (for RPi) can be added later via multi-arch build
- The native `libzedmd` is not needed in Docker (dmdserver backend)'

echo "  [10/10] Created: Docker support"

echo ""
echo "Done! All 10 issues created."
