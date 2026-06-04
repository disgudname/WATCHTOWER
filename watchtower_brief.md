# WATCHTOWER — Claude Code Brief
*Home base relay and overlay server for the 2026 Reset Trip livestream*

## System Context
WATCHTOWER runs on a Windows 10 machine at home. It is unattended for the duration of the trip (June 16–23, 2026). It receives GPS data from the road via Traccar, serves two OBS browser source overlays, and keeps the YouTube stream alive when the field feed drops.

The operator may AnyDesk in remotely to check status or restart services. Everything should be robust enough to run a week without intervention.

## What WATCHTOWER is NOT responsible for
- Receiving RTMP video feed — that's node-media-server (separate, already handled)
- GPS collection — that's Traccar (already running on this machine)
- Scene switching — that's OBS + Advanced Scene Switcher
- Pushing to YouTube — that's OBS

## What WATCHTOWER Flask app IS responsible for
- Pulling current position, speed, heading, and route history from Traccar's local API
- Pulling current weather from OpenWeatherMap API (free tier, coordinates-based)
- Reverse geocoding coordinates to human-readable city/state (Nominatim, no API key required)
- Deriving local timezone from coordinates (timezonefinder library)
- Serving `/live` — LIVE overlay for OBS (sits over road footage)
- Serving `/dark` — DARK overlay for OBS (fills screen when field feed is absent)

---

## Traccar Integration

Traccar runs locally on the same machine. Default API is at `http://localhost:8082`.

Relevant endpoints:
- `GET /api/devices` — list devices, get device ID for the phone
- `GET /api/positions?deviceId={id}` — latest position for device
- `GET /api/positions?deviceId={id}&from={iso}&to={iso}` — route history

Auth: Traccar uses basic auth. Credentials should be stored in a config file (`config.py` or `.env`), not hardcoded.

Pull latest position every 5 seconds. Cache it in memory — don't hammer Traccar on every overlay page load.

Fields to extract from latest position:
- `latitude`, `longitude`
- `speed` (Traccar returns km/h — convert to mph)
- `course` (degrees, convert to cardinal: N, NE, E, SE, S, SW, W, NW)
- `fixTime` (ISO timestamp — store and display as "last seen X minutes ago")

---

## External API Integrations

### Weather — OpenWeatherMap
- Free tier, requires API key (store in config)
- `GET https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={key}&units=imperial`
- Pull every 10 minutes (weather doesn't change that fast, don't waste API calls)
- Extract: temperature (°F), conditions description, icon code
- Cache between pulls

### Reverse Geocoding — Nominatim
- Free, no API key, OpenStreetMap data
- `GET https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json`
- Returns city, state — format as "Albuquerque, NM"
- Pull every 60 seconds or when position changes significantly (>0.5 miles)
- Nominatim rate limit: 1 request/second max — respect this
- Set a descriptive User-Agent header (Nominatim requires it)
- Cache between pulls

### Timezone — timezonefinder
- Python library, no API needed, works offline
- `from timezonefinder import TimezoneFinder` → `tf.timezone_at(lat=lat, lng=lon)`
- Returns timezone string e.g. "America/Denver"
- Use `pytz` or `zoneinfo` to convert UTC to local time
- Re-derive when position changes significantly

---

## Route History

Store incoming Traccar positions to a local SQLite database (`route.db`). Simple table:
```
positions(id, timestamp, lat, lon, speed_mph, heading_deg, city_state)
```

Write a new row every time a fresh position comes in from Traccar (every 5 seconds while phone has signal). This builds the route line for the map overlay.

On startup, load existing route history from SQLite so the map shows the full trip so far even after a server restart.

---

## Overlay Pages

Both overlays are served as HTML pages with JavaScript that polls `/api/status` every 5 seconds for fresh data. They do not hit Traccar or external APIs directly — all data flows through the Flask backend.

### `/api/status` endpoint
Returns JSON:
```json
{
  "lat": 35.084,
  "lon": -106.651,
  "speed_mph": 72.4,
  "heading": "SW",
  "city_state": "Albuquerque, NM",
  "last_seen_seconds": 8,
  "local_time": "2:34 PM",
  "local_timezone": "MDT",
  "weather_temp_f": 91,
  "weather_desc": "Sunny",
  "weather_icon": "01d",
  "route": [[35.084, -106.651], [35.071, -106.489], ...],
  "stale": false
}
```

`stale: true` when last Traccar fix is >30 seconds old. Overlays should visually indicate staleness.

### `/live` — LIVE Overlay
Sits over road footage in OBS. HUD aesthetic, dark semi-transparent elements, arranged at edges of frame so road is visible.

Elements:
- **Speed** — large, top left or bottom left. "72 MPH". Show "---" if stale.
- **Heading** — smaller, next to speed. "SW"
- **Location** — bottom of frame. "Albuquerque, NM"
- **Clock** — top right. Local time to traveler. "2:34 PM MDT"
- **Weather** — top right or bottom right. Temp + icon. "91°F ☀️"
- **Mini map** — small corner map (OpenStreetMap tile) with current position pin and route line. Maybe 200x200px. Should not dominate the overlay.

Design notes:
- Dark background panels behind text, semi-transparent (~70% opacity)
- Light text — white or light grey
- OBS browser source background should be transparent (`body { background: transparent }`)
- Stormchaser HUD aesthetic — functional, not decorative
- Recommended OBS browser source size: 1920x1080 (full frame, elements positioned absolutely)

### `/dark` — DARK Overlay
Fills the screen when OBS switches to the placeholder scene. Designed to look intentional — not a dead stream.

Elements:
- **Header** — "SERENITY IS OFF-GRID" or similar. Large, centered.
- **Last seen** — "Last seen near Albuquerque, NM — 14 minutes ago". Prominent.
- **Map** — larger than LIVE version, showing full route line of the trip so far with last known position pin
- **Weather** — current conditions at last known location
- **Clock** — local time at last known location
- **Trip context** — subtle footer. "2026 Reset Trip — Day 3"

Design notes:
- Full dark background — not transparent, this fills the whole scene
- More visual breathing room than LIVE overlay
- Route line on map should show the whole trip so far — satisfying to look at
- Should not look like an error screen. It should look like a deliberate broadcast card.
- Recommended OBS browser source size: 1920x1080

---

## Map Implementation

Use Leaflet.js (CDN, no install) for both overlays. OpenStreetMap tiles, no API key needed.

For LIVE overlay: small map, fixed zoom around current position, updates as position changes.
For DARK overlay: map auto-fits bounds to show full route line so far.

Route line: draw as a Leaflet polyline from the `route` array in `/api/status`.
Current position: Leaflet circle marker or custom pin.

---

## Tech Stack
- Python 3, Flask, flask-cors
- `timezonefinder`, `pytz`
- `requests` (for OpenWeatherMap and Nominatim)
- `sqlite3` (stdlib, no extra install)
- Leaflet.js via CDN (no install)
- Plain HTML/CSS/JS for overlay pages

### requirements.txt
```
flask
flask-cors
timezonefinder
pytz
requests
```

---

## Configuration
All credentials and settings in a `config.py` or `.env` file:
```
TRACCAR_URL=http://localhost:8082
TRACCAR_USER=admin
TRACCAR_PASS=yourpassword
TRACCAR_DEVICE_ID=1
OPENWEATHERMAP_API_KEY=yourkey
FLASK_PORT=5000
```

---

## Startup & Reliability
- Flask app should run as a Windows service or via a startup script so it survives reboots
- Suggest `waitress` as the WSGI server instead of Flask dev server for unattended use (`pip install waitress`)
- All external API calls wrapped in try/except — if OpenWeatherMap or Nominatim fails, overlay shows last cached value, not an error
- If Traccar is unreachable, show last known position with stale indicator
- Log errors to a local file (`watchtower.log`) for post-trip debugging

---

## Out of Scope
- Authentication on the Flask app (LAN only)
- RTMP handling (node-media-server)
- OBS configuration
- Traccar setup
- YouTube stream key management
