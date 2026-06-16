# WATCHTOWER

Home base relay and overlay server for the **2026 Reset Trip** livestream.

Runs unattended on a Windows machine at home. Pulls GPS data from Traccar, fetches weather and reverse geocoding, and serves OBS browser-source overlays for a YouTube road-trip stream. Maps show live weather radar, NWS alerts, FAA TFRs, and ADS-B aircraft pulled from [Pandemonium EOC](https://eoc.pandemoniumair.com/).

---

## Overlays

| URL | Purpose |
|-----|---------|
| `/live` | **LIVE** — transparent HUD over road footage. Location, highway badge, weather, mini map with overlays, tips, state-crossing banner. |
| `/dark` | **DARK** — full-screen broadcast card when the field feed drops. Last-known location, full route map with overlays, trip day counter, cycling tips. |
| `/mobile` | **MOBILE** — side-panel layout for a 1920×1080 canvas with a 608×1080 vertical phone feed in the centre. |
| `/api/status` | Raw JSON — everything the overlays consume. |
| `/api/route` | Full trip route as `[[lat,lon],…]` from the database. |
| `/api/tips` | JSON array of tips loaded from `tips.txt`. |

All overlays are 1920×1080. Set OBS browser source size to match.

---

## Map overlays

Both `/live` and `/dark` run MapLibre GL JS maps with four live data layers stacked in this order (bottom to top):

| Layer | Source | Refresh |
|-------|--------|---------|
| **NOAA MRMS radar** | `/proxy/weather-radar` → EOC | 5-minute frame fetch; 15-frame animation loops continuously at ~300 ms/frame |
| **NWS weather alerts** | `/proxy/weather-alerts` → EOC | Every 2 min. Polygons colored by severity. Tornado/severe thunderstorm warnings flash white. |
| **FAA TFRs** | `/proxy/aviation` → EOC | Every 5 min. Filled polygons with colored outline + white halo. |
| **ADS-B aircraft** | `/proxy/adsb` → EOC | Every 15 s. tar1090-style silhouettes rotated to heading, colored by altitude. |
| **Route line** | `/api/status` | Every 5 s |
| **Position marker** | `/api/status` | Every 5 s |

All EOC data is fetched server-side through Flask proxy routes — the browser never crosses origins.

The `/dark` map fits its zoom to the full route on load. The `/live` map stays at zoom 11 and follows the vehicle.

---

## Setup

Two paths depending on what you're doing:

**Windows (PowerShell):**

| | `setup.ps1` | `dev.ps1` |
|---|---|---|
| **Use for** | Production home machine | Local testing / laptop |
| **Requires admin** | Yes (Task Scheduler) | No |
| **Auto-starts on boot** | Yes | No — foreground process, Ctrl+C to stop |

**Linux (bash):**

| | `setup.sh` | `dev.sh` |
|---|---|---|
| **Use for** | Production Linux machine | Local testing |
| **Requires sudo** | No (systemd user service) | No |
| **Auto-starts on boot** | Yes | No — foreground process, Ctrl+C to stop |

### Prerequisites

- Python 3.9+ in PATH ([python.org](https://www.python.org/downloads/))
- Traccar running locally on the same machine (or set `TRACCAR_URL` in `.env` to point elsewhere)
- A free [OpenWeatherMap](https://openweathermap.org/api) API key

### Steps

**1. Clone the repo**
```
git clone <repo-url>
cd WATCHTOWER
```

**2. Configure credentials**

Copy the example config and fill in your values:
```
copy config.example.env .env
notepad .env
```

The required field:
```
OPENWEATHERMAP_API_KEY=yourkey
```

For Traccar auth, set either `TRACCAR_TOKEN` (preferred) or `TRACCAR_PASS`. See [Configuration](#configuration) for the full reference.

**3. Run setup (as Administrator)**
```
.\setup.ps1
```

This will:
- Create a Python virtual environment
- Install all dependencies
- Initialise the SQLite route database
- Register a Windows Task Scheduler task that starts WATCHTOWER at boot (runs as SYSTEM, restarts automatically on crash)

**4. Start WATCHTOWER**
```
.\start.ps1
```

That's it. WATCHTOWER will start automatically on every reboot from here on.

---

## Starting and stopping

| Action | Command |
|--------|---------|
| Start / restart | `.\start.ps1` |
| Stop | `Stop-ScheduledTask -TaskName WATCHTOWER` |
| Check status | `Get-ScheduledTask -TaskName WATCHTOWER` |
| View live logs | `Get-Content watchtower.log -Wait` |

`start.ps1` is safe to run at any time, including remotely over AnyDesk — it stops any running instance before starting a fresh one.

---

## OBS configuration

Add two browser sources to your OBS scene collection:

**LIVE overlay** (place over your road footage scene):
- URL: `http://localhost:5000/live`
- Width: `1920`, Height: `1080`
- Background colour: `#00000000` (transparent)
- Refresh browser when scene becomes active: enabled

**DARK card** (use as a full-screen placeholder scene):
- URL: `http://localhost:5000/dark`
- Width: `1920`, Height: `1080`
- Background colour: `#00000000` (transparent — the page itself is fully dark)

**MOBILE overlay** (place over a scene where a vertical phone feed occupies the centre 608px):
- URL: `http://localhost:5000/mobile`
- Width: `1920`, Height: `1080`
- Background colour: `#00000000` (transparent)

---

## Configuration

All settings live in `.env` (copy from `config.example.env`).

| Variable | Default | Description |
|----------|---------|-------------|
| `TRACCAR_URL` | `http://localhost:8082` | Traccar API base URL |
| `TRACCAR_TOKEN` | — | Traccar API token (preferred auth — find it in Traccar: Settings → Account → Token) |
| `TRACCAR_USER` | `admin` | Traccar username (fallback if `TRACCAR_TOKEN` is blank) |
| `TRACCAR_PASS` | — | Traccar password (fallback if `TRACCAR_TOKEN` is blank) |
| `TRACCAR_DEVICE_ID` | `1` | Device ID from Traccar (`/api/devices`) |
| `TRACCAR_SSL_VERIFY` | `true` | Set to `false` to skip SSL cert verification (use if Traccar is on a self-signed cert) |
| `OPENWEATHERMAP_API_KEY` | — | OWM free-tier API key **[required]** |
| `FLASK_PORT` | `5000` | Port WATCHTOWER listens on |
| `DB_PATH` | `route.db` | SQLite database file path |
| `TRIP_NAME` | `2026 Reset Trip` | Shown on the dark overlay footer |
| `TRIP_START_DATE` | `2026-06-16` | Used to calculate current trip day. Before departure, overlays show a T−N countdown. |
| `TRIP_END_DATE` | `2026-06-23` | Used to calculate trip length |
| `VEHICLE_NAME` | `Serenity` | Shown in the dark overlay headline |

---

## Architecture

```
Traccar (localhost:8082)
    └── GPS position every 5 s
            │
            ▼
        app.py  ◄── OpenWeatherMap (every 10 min)
            │   ◄── Nominatim geocoder (every ~0.5 mi)
            │   ◄── timezonefinder (offline)
            │
            ├── route.db  (SQLite, persists full trip history)
            ├── tips.txt  (loaded on each /api/tips request)
            │
            ├── /api/status     ◄── polled every 5 s by all overlays
            │     fields: lat/lon, speed_mph, heading, city_state,
            │             highway, elevation_ft, odometer_miles,
            │             local_time, weather_*, stale,
            │             trip_day/total, state_crossing, route[]
            ├── /api/route      ◄── full DB route, fetched once on /dark load
            ├── /api/tips       ◄── fetched on page load by /live and /dark
            │
            ├── /proxy/adsb            ─┐
            ├── /proxy/aviation         ├── Flask pass-through to
            ├── /proxy/weather-alerts   │   eoc.pandemoniumair.com
            ├── /proxy/weather-radar   ─┘   (avoids CORS, keeps browser
            │                               on same origin)
            ├── /live    (OBS browser source — MapLibre GL JS)
            ├── /dark    (OBS browser source — MapLibre GL JS)
            └── /mobile  (OBS browser source)
```

### External data sources

| Source | What it provides | Key |
|--------|-----------------|-----|
| Traccar | GPS position, speed, heading, altitude | Token / password |
| OpenWeatherMap | Temperature, conditions, icon | API key (free tier) |
| Nominatim | City/state reverse geocoding, road name | None |
| timezonefinder | Local timezone (offline lookup) | None |
| Pandemonium EOC | ADS-B aircraft, NOAA MRMS radar, NWS alerts, FAA TFRs | None (proxied) |

WATCHTOWER does **not** handle:
- RTMP video ingest (that's node-media-server)
- GPS collection (that's Traccar)
- Scene switching (that's OBS + Advanced Scene Switcher)
- Pushing to YouTube (that's OBS)

---

## Tips

`tips.txt` in the project root supplies the rotating tip bar shown at the bottom of `/live` and `/dark`. Tips cycle every 30 seconds in a shuffled random order.

Format — one tip per line:
```
TIP|Your tip text here.
```

Add as many lines as you like. Changes take effect after a server restart.

---

## Staleness

Staleness is determined by Traccar's device status (`online` vs `offline`), checked every ~15 seconds. When the device goes offline:
- `/api/status` sets `"stale": true`
- `/live` shows a pulsing **GPS SIGNAL LOST** badge
- `/dark` continues showing last-known position with a live-counting age timer ("14 min ago")

---

## Logs

Errors are written to `watchtower.log` in the project root. Tail it live:

```powershell
Get-Content watchtower.log -Wait
```

---

## Tech stack

- **Python 3.9+** — Flask, flask-cors, waitress, requests, timezonefinder, python-dotenv
- **SQLite** — route history (stdlib, no install)
- **MapLibre GL JS 4.7.1** — GPU-rendered maps via CDN, CartoDB Light raster tiles
- **adsb-markers.js** — vendored tar1090 aircraft shape/color library (from Pandemonium EOC)
- **OpenWeatherMap** — weather (free tier)
- **Nominatim** — reverse geocoding (free, no key)
- **Pandemonium EOC** — ADS-B, radar, NWS alerts, FAA TFRs (proxied through Flask)
