# TODO - zeClock

## Future ideas and planned improvements

---

### 🐛 Bugs

- [ ] **Weather plugin**: cannot type letters in the postal code field — Canadian postal codes contain letters (e.g. H2X 1Y4). Fix input validation.

---

### 🧩 Plugins

#### 🕐 Clock / Date Plugin

- [ ] **Turn the clock display into a plugin** (currently core code, not a plugin)
- [ ] Display time
- [ ] Display date
- [ ] Display day of the week
- [ ] Display the name day (saint of the day)
- [ ] Configurable alternation between time, date, day, and name day

#### 🌤️ Weather Plugin

- [ ] Display weather service connection status

#### 📡 Social Media Plugin

- [ ] Display Twitch subscriber count
- [ ] Display YouTube subscriber count

#### 📶 WiFi Status Plugin

- [ ] Display WiFi status (connected or not)

#### 🔮 Horoscope Plugin

- [ ] Display the daily horoscope based on the configured astrological sign

#### 📅 Calendar / Agenda Plugin

- [ ] Display upcoming events from Google Calendar, iCal (iCloud, Outlook, etc.)
- [ ] Configurable lookahead (next event, next 24h, etc.)
- [ ] Show event title and time remaining / start time

#### 📊 Custom Counter Plugin

- [ ] Display any numeric value with a label (e.g. "Sales: 42", "CPU: 78%")
- [ ] Feed value via MQTT or HTTP webhook (push from any external system)
- [ ] Configurable label, unit, and icon

#### 🔔 Push Notification Plugin

- [X] Receive and display a short text message from any system via webhook or MQTT
- [X] Configurable display duration before returning to normal rotation
- [X] Priority levels (normal, urgent — urgent interrupts current display immediately)

#### 📰 RSS / News Ticker Plugin

- [ ] Fetch and scroll headlines from one or more RSS feeds
- [ ] Configurable refresh interval and number of items to display
- [ ] Filter by keyword

#### 🪂 Paragliding Plugin (Paraglidable / Spotair)

- [ ] Integration with [Paraglidable](https://paraglidable.com/) API (AI-based paragliding forecast)
  - API endpoint: `https://api.paraglidable.com/?key=YOUR_KEY&format=json`
  - Requires a free API key (email registration, limited to 10 spots per key)
- [ ] Display **flyability percentage** for today (probability a flight will be reported)
- [ ] Display **cross-country (XC) percentage** for today (probability of a 60+ point flight, PWC scoring)
- [ ] Display forecast for tomorrow and the upcoming week (day-by-day)
- [ ] Configurable spot(s) selection (latitude/longitude based)
- [ ] Color-coded display (e.g. green = good flyability, yellow = marginal, red = no-go)
- [ ] Optional: show wind and humidity safety indicators (API provides separate wind/humidity probabilities)

#### 🕹️ Recalbox Plugin

- [ ] Integration with Recalbox RGBJAMMA or dual (game data display, scores, etc.)

#### 🎤 Speaker Timer Plugin (conference)

Timer for conferences and presentations, visible from the stage on the ZeDMD.

**Essential features**

- [x] Large countdown display — big, readable digits from stage distance
- [x] Automatic color change based on configurable thresholds (green → yellow → red)
- [x] Configurable presets per session — pre-saved durations (5, 20, 45 min) quickly recalled
- [x] Countdown to zero then count-up — switches to red once time is exceeded
- [x] Remote control — start/pause/reset from phone, tablet, or laptop (Web UI)
- [x] Discreet messages to the speaker — short text sent to the speaker screen only ("Speak louder", "Wrap up", "Q&A 5 min")
- [x] Simple operator interface — large Start/Pause/Reset buttons, usable under pressure by volunteers
- [x] Visual signals only (colors, countdown), no distracting beeps or flashes

**Nice-to-have**

- [x] Cross-platform web interface (control from any device)
- [ ] Configurable layouts: time only, time + session name, time + next session
- [ ] Program profiles (keynote, panel, lightning talk) with pre-configured timers
- [x] Robust offline mode (no WiFi dependency for the local timer)
- [ ] Integration with production systems (cues, slides)

---

### 🖥️ Display

#### 🔤 Fonts and styles

- [ ] Show a preview of available fonts/styles before selection

#### 🔄 Rotation / Flip

- [ ] Option to rotate the screen (90°, 180°, 270°) — software rotation of the buffer before sending to ZeDMD (`--rotate 180`)
- [ ] Option to flip the display horizontally or vertically (`--flip horizontal`, `--flip vertical`)

---

### 💡 Brightness and scheduling

- [x] Schedule by day of the week with time ranges and brightness percentage
  - Example: Monday 8am–4pm → 50%, Saturday 8pm–10pm → 50%, rest → 0%
  - Configured in `[brightness_schedule]` section of `zeclock.ini`
- [x] Allow brightness below 5 — very low brightness option (1 to 5)
  - Software dimming (pixel-level) combined with HW brightness 1 for ultra-low levels
- [x] Automatically turn off the screen at night via sunrise/sunset API (based on geographic location)
  - Uses sunrise-sunset.org API with `[location]` config (latitude/longitude)
- [x] Automatically adjust brightness based on time of day / sunrise / sunset
  - `sunrise_brightness` and `sunset_brightness` config options
- [x] "Time only" mode from a given hour: no date change, weather, or animation - brightness set to minimum
  - `time_only` in `[brightness_schedule]` (format: `22:00-08:00`)

---

### 🎛️ Remote control

- [x] Turn the screen on / off (all black) remotely
- [x] Force display of a specific plugin
- [x] Display free text + emoji on demand
- [x] **Primary protocol: MQTT**
  - Bidirectional pub/sub, native Home Assistant (MQTT Discovery)
  - zeClock publishes: state, active plugin, brightness...
  - zeClock subscribes: commands (on/off, force plugin, display text...)
- [x] REST API (HTTP) as a complement for simple integrations and Recalbox (Web Manager)
- [x] Web UI for controlling all clock capabilities (plugins, screen, messages, speaker timer)
- [ ] OSC (optional, for live/show integrations)
- [x] Home Assistant integration via MQTT Discovery (auto-created entities)
- [ ] Recalbox bridge: small script that translates Recalbox events ↔ MQTT

---

### 🔄 Automatic updates

- [ ] Check for new versions of zeClock on GitHub (releases API)
- [ ] Notify the user that an update is available (display on the DMD or via log)
- [ ] Option for automatic update (self-update via pip/pipx/uvx)
