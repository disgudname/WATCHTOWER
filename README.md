# WATCHTOWER

Home base relay and overlay server for the **2026 Reset Trip** livestream.

Runs unattended on a Windows machine at home. Pulls GPS data from Traccar, fetches weather and reverse geocoding, and serves two OBS browser-source overlays for a YouTube road-trip stream.

---

## Overlays

| URL | Purpose |
|-----|---------|
| `http://localhost:5000/live` | **LIVE** — transparent HUD over road footage. Speed, heading, location, clock, weather, mini map. |
| `http://localhost:5000/dark` | **DARK** — full-screen broadcast card when the field feed drops. Last-known location, full route map, trip day. |
| `http://localhost:5000/api/status` | Raw JSON — everything the overlays consume. |

Both overlays are 1920×1080. Set OBS browser source size to match.

---

## Setup

Two paths depending on what you're doing:

| | `setup.ps1` | `dev.ps1` |
|---|---|---|
| **Use for** | Production home machine | Local testing / laptop |
| **Requires admin** | Yes (Task Scheduler) | No |
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

The two required fields:
```
TRACCAR_PASS=yourpassword
OPENWEATHERMAP_API_KEY=yourkey
```

Everything else has sensible defaults. See [Configuration](#configuration) for the full reference.

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

---

## Configuration

All settings live in `.env` (copy from `config.example.env`).

| Variable | Default | Description |
|----------|---------|-------------|
| `TRACCAR_URL` | `http://localhost:8082` | Traccar API base URL |
| `TRACCAR_USER` | `admin` | Traccar login username |
| `TRACCAR_PASS` | — | Traccar login password **[required]** |
| `TRACCAR_DEVICE_ID` | `1` | Device ID from Traccar (`/api/devices`) |
| `OPENWEATHERMAP_API_KEY` | — | OWM free-tier API key **[required]** |
| `FLASK_PORT` | `5000` | Port WATCHTOWER listens on |
| `DB_PATH` | `route.db` | SQLite database file path |
| `TRIP_NAME` | `2026 Reset Trip` | Shown on the dark overlay footer |
| `TRIP_START_DATE` | `2026-06-16` | Used to calculate current trip day |
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
            │   ◄── Nominatim geocoder (every ~60 s)
            │   ◄── timezonefinder (offline)
            │
            ├── route.db  (SQLite, persists full trip history)
            │
            └── /api/status  ◄── polled every 5 s by both overlays
                    ├── /live  (OBS browser source)
                    └── /dark  (OBS browser source)
```

WATCHTOWER does **not** handle:
- RTMP video ingest (that's node-media-server)
- GPS collection (that's Traccar)
- Scene switching (that's OBS + Advanced Scene Switcher)
- Pushing to YouTube (that's OBS)

---

## Staleness

If the GPS fix is more than 30 seconds old:
- `/api/status` sets `"stale": true`
- `/live` shows a pulsing **SIGNAL LOST** badge and blanks the speed readout
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
- **Leaflet.js** — maps via CDN, OpenStreetMap / CartoDB Dark tiles
- **OpenWeatherMap** — weather (free tier)
- **Nominatim** — reverse geocoding (free, no key)
