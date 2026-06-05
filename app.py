import os
import time
import math
import logging
import threading
import sqlite3
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
from timezonefinder import TimezoneFinder
from dotenv import load_dotenv

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    _SPOTIPY_AVAILABLE = True
except ImportError:
    _SPOTIPY_AVAILABLE = False

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
TRACCAR_URL       = os.getenv("TRACCAR_URL", "http://localhost:8082")
TRACCAR_TOKEN     = os.getenv("TRACCAR_TOKEN", "")
TRACCAR_USER      = os.getenv("TRACCAR_USER", "admin")
TRACCAR_PASS      = os.getenv("TRACCAR_PASS", "")
TRACCAR_DEVICE_ID = int(os.getenv("TRACCAR_DEVICE_ID", "1"))
OWM_KEY           = os.getenv("OPENWEATHERMAP_API_KEY", "")
FLASK_PORT        = int(os.getenv("FLASK_PORT", "5000"))
DB_PATH           = os.getenv("DB_PATH", "route.db")
TRIP_START_DATE   = os.getenv("TRIP_START_DATE", "2026-06-16")
TRIP_END_DATE     = os.getenv("TRIP_END_DATE", "2026-06-23")
VEHICLE_NAME      = os.getenv("VEHICLE_NAME", "Serenity")
TRIP_NAME         = os.getenv("TRIP_NAME", "2026 Reset Trip")
SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
SPOTIFY_CACHE_PATH    = ".spotify_cache"

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("watchtower.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Shared state ──────────────────────────────────────────────────────────────
_lock = threading.Lock()
_state = {
    "lat": None, "lon": None,
    "speed_mph": None, "heading": "---",
    "city_state": "---",
    "last_seen_seconds": None,
    "local_time": "--:-- --", "local_timezone": "---",
    "weather_temp_f": None, "weather_desc": "---", "weather_icon": "01d",
    "route": [],
    "stale": True,
    "trip_day": None, "trip_total": None,
    "vehicle_name": VEHICLE_NAME,
    "trip_name": TRIP_NAME,
    "now_playing": {"active": False, "title": None, "artist": None, "art_url": None},
    "elevation_ft": None,
    "odometer_miles": 0.0,
    "state_crossing": None,
}

# odometer and state-crossing tracking (poll thread only — no lock needed)
_odo_last_lat  = None
_odo_last_lon  = None
_prev_state_abbr = None

tf = TimezoneFinder()
app = Flask(__name__)
CORS(app)

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                lat         REAL    NOT NULL,
                lon         REAL    NOT NULL,
                speed_mph   REAL,
                heading_deg REAL,
                city_state  TEXT
            )
        """)
        conn.commit()

def db_save(ts, lat, lon, speed_mph, heading_deg, city_state):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO positions (timestamp,lat,lon,speed_mph,heading_deg,city_state) "
                "VALUES (?,?,?,?,?,?)",
                (ts, lat, lon, speed_mph, heading_deg, city_state),
            )
    except Exception as e:
        log.error("DB write: %s", e)

def db_load_route():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT lat,lon FROM positions ORDER BY timestamp"
            ).fetchall()
        return [[round(r[0], 5), round(r[1], 5)] for r in rows]
    except Exception as e:
        log.error("DB read: %s", e)
        return []

def db_compute_odometer():
    """Recompute trip odometer from DB, filtering out GPS drift when stationary."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT lat, lon, speed_mph FROM positions ORDER BY timestamp"
            ).fetchall()
        total = 0.0
        prev_lat = prev_lon = None
        for lat, lon, speed in rows:
            if prev_lat is not None and speed is not None and speed >= MIN_MOVE_MPH:
                total += haversine_mi(prev_lat, prev_lon, lat, lon)
            prev_lat, prev_lon = lat, lon
        return round(total, 1)
    except Exception as e:
        log.error("Odometer DB compute: %s", e)
        return 0.0

def db_last_position():
    """Return (lat, lon) of the most recent stored position, or (None, None)."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT lat, lon FROM positions ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        return (row[0], row[1]) if row else (None, None)
    except Exception:
        return (None, None)

# ── Helpers ───────────────────────────────────────────────────────────────────
_CARDINALS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

MIN_MOVE_MPH = 3.0

_STATE_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY", "District of Columbia": "DC",
}
_ABBR_TO_STATE = {v: k for k, v in _STATE_ABBR.items()}

def to_cardinal(deg):
    if deg is None:
        return "---"
    return _CARDINALS[round(float(deg) / 45) % 8]

def haversine_mi(lat1, lon1, lat2, lon2):
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def trip_day_of():
    try:
        start = date.fromisoformat(TRIP_START_DATE)
        end   = date.fromisoformat(TRIP_END_DATE)
        today = date.today()
        total = (end - start).days + 1
        if today < start:
            return (today - start).days, total   # negative: days until departure
        if start <= today <= end:
            return (today - start).days + 1, total
    except Exception:
        pass
    return None, None

# ── Reverse geocoder ──────────────────────────────────────────────────────────
_geo_lat = _geo_lon = None
_geo_result   = "---"
_geo_last_req = 0.0

def geocode(lat, lon):
    global _geo_lat, _geo_lon, _geo_result, _geo_last_req
    if _geo_lat is not None and haversine_mi(lat, lon, _geo_lat, _geo_lon) < 0.5:
        return _geo_result
    if time.time() - _geo_last_req < 1.0:
        return _geo_result
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lon, "format": "json"},
            headers={"User-Agent": "WATCHTOWER/1.0 2026-reset-trip-overlay"},
            timeout=6,
        )
        addr = r.json().get("address", {})
        city  = (addr.get("city") or addr.get("town")
                 or addr.get("village") or addr.get("county", ""))
        state_full = addr.get("state", "")
        state = _STATE_ABBR.get(state_full, state_full[:2].upper() if state_full else "")
        _geo_result = f"{city}, {state}".strip(", ") or "Unknown"
        _geo_lat, _geo_lon = lat, lon
    except Exception as e:
        log.error("Geocode: %s", e)
    finally:
        _geo_last_req = time.time()
    return _geo_result

# ── Weather ───────────────────────────────────────────────────────────────────
_wx_temp = None
_wx_desc = None
_wx_icon = None
_wx_last = 0.0

def get_weather(lat, lon):
    global _wx_temp, _wx_desc, _wx_icon, _wx_last
    if time.time() - _wx_last < 600:
        return _wx_temp, _wx_desc or "---", _wx_icon or "01d"
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"lat": lat, "lon": lon, "appid": OWM_KEY, "units": "imperial"},
            timeout=6,
        )
        d = r.json()
        if "main" not in d:
            log.error("Weather API error: %s", d.get("message", d))
        else:
            _wx_temp = round(d["main"]["temp"])
            _wx_desc = d["weather"][0]["description"].title()
            _wx_icon = d["weather"][0]["icon"]
            _wx_last = time.time()
    except Exception as e:
        log.error("Weather: %s", e)
    return _wx_temp, _wx_desc or "---", _wx_icon or "01d"

# ── Timezone / local time ─────────────────────────────────────────────────────
_tz_zone = None
_tz_lat  = _tz_lon = None

def local_time_at(lat, lon):
    global _tz_zone, _tz_lat, _tz_lon
    try:
        if _tz_zone is None or (
            _tz_lat is not None and haversine_mi(lat, lon, _tz_lat, _tz_lon) > 50
        ):
            tz_str = tf.timezone_at(lat=lat, lng=lon)
            if tz_str:
                _tz_zone = ZoneInfo(tz_str)
                _tz_lat, _tz_lon = lat, lon
        if _tz_zone:
            now = datetime.now(tz=_tz_zone)
            # lstrip("0") strips leading zero on hour; safe for all 12-hr values
            hm      = now.strftime("%I:%M %p").lstrip("0")
            tz_abbr = now.strftime("%Z")
            return hm, tz_abbr
    except Exception as e:
        log.error("Timezone: %s", e)
    return "--:-- --", "---"

# ── Spotify ───────────────────────────────────────────────────────────────────
_sp_client = None

def _get_spotify():
    global _sp_client
    if not _SPOTIPY_AVAILABLE:
        return None
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return None
    if not os.path.exists(SPOTIFY_CACHE_PATH):
        return None
    if _sp_client is None:
        try:
            auth = SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope="user-read-currently-playing user-read-playback-state",
                cache_path=SPOTIFY_CACHE_PATH,
                open_browser=False,
            )
            _sp_client = spotipy.Spotify(auth_manager=auth)
        except Exception as e:
            log.error("Spotify init: %s", e)
    return _sp_client

def _spotify_poll():
    while True:
        sp = _get_spotify()
        if sp:
            try:
                result = sp.current_playback()
                if result and result.get("is_playing") and result.get("item"):
                    track  = result["item"]
                    images = track["album"]["images"]
                    now_playing = {
                        "active":   True,
                        "title":    track["name"],
                        "artist":   ", ".join(a["name"] for a in track["artists"]),
                        "art_url":  images[0]["url"] if images else None,
                    }
                else:
                    now_playing = {"active": False}
                with _lock:
                    _state["now_playing"] = now_playing
            except Exception as e:
                log.error("Spotify poll: %s", e)
        time.sleep(15)

# ── Traccar poll thread ───────────────────────────────────────────────────────
def _traccar_poll():
    while True:
        try:
            headers = {"Authorization": f"Bearer {TRACCAR_TOKEN}"} if TRACCAR_TOKEN else {}
            r = requests.get(
                f"{TRACCAR_URL}/api/positions",
                params={"deviceId": TRACCAR_DEVICE_ID},
                headers=headers,
                auth=None if TRACCAR_TOKEN else (TRACCAR_USER, TRACCAR_PASS),
                timeout=5,
            )
            if r.status_code != 200:
                log.error("Traccar returned HTTP %d: %s", r.status_code, r.text[:200])
                with _lock:
                    _state["stale"] = True
                time.sleep(5)
                continue
            positions = r.json()

            # Device online/offline status
            stale = True
            try:
                dr = requests.get(
                    f"{TRACCAR_URL}/api/devices",
                    params={"id": TRACCAR_DEVICE_ID},
                    headers=headers,
                    auth=None if TRACCAR_TOKEN else (TRACCAR_USER, TRACCAR_PASS),
                    timeout=5,
                )
                if dr.status_code == 200:
                    devices = dr.json()
                    if devices:
                        stale = devices[0].get("status", "offline") != "online"
            except Exception as e:
                log.error("Traccar device status: %s", e)

            if positions:
                global _odo_last_lat, _odo_last_lon, _prev_state_abbr

                pos       = positions[0]
                lat       = pos["latitude"]
                lon       = pos["longitude"]
                speed_mph = pos.get("speed", 0) * 0.621371
                heading   = to_cardinal(pos.get("course"))
                fix_time  = pos.get("fixTime", "")
                elevation_ft = round(pos.get("altitude", 0) * 3.28084)

                local_time, local_tz = local_time_at(lat, lon)
                wx_temp, wx_desc, wx_icon = get_weather(lat, lon)
                city_state = geocode(lat, lon)
                trip_day, trip_total = trip_day_of()

                try:
                    fix_dt  = datetime.fromisoformat(fix_time.replace("Z", "+00:00"))
                    age_sec = int((datetime.now(timezone.utc) - fix_dt).total_seconds())
                except Exception:
                    age_sec = 9999

                # Odometer — only accumulate when actually moving (Doppler speed filter
                # prevents GPS drift while parked from adding phantom miles)
                odo_delta = 0.0
                if _odo_last_lat is not None and speed_mph >= MIN_MOVE_MPH:
                    odo_delta = haversine_mi(_odo_last_lat, _odo_last_lon, lat, lon)
                _odo_last_lat, _odo_last_lon = lat, lon

                # State crossing detection
                state_abbr = city_state.split(", ")[-1] if ", " in city_state else ""
                crossing = None
                if state_abbr and _prev_state_abbr is not None and state_abbr != _prev_state_abbr:
                    crossing = {
                        "abbr": state_abbr,
                        "name": _ABBR_TO_STATE.get(state_abbr, state_abbr),
                        "at": time.time(),
                    }
                    log.info("State crossing: %s → %s", _prev_state_abbr, state_abbr)
                if state_abbr:
                    _prev_state_abbr = state_abbr

                point = [round(lat, 5), round(lon, 5)]

                with _lock:
                    if not _state["route"] or _state["route"][-1] != point:
                        _state["route"].append(point)
                    updates = {
                        "lat": lat, "lon": lon,
                        "speed_mph": round(speed_mph, 1),
                        "heading": heading,
                        "city_state": city_state,
                        "last_seen_seconds": age_sec,
                        "local_time": local_time,
                        "local_timezone": local_tz,
                        "weather_temp_f": wx_temp,
                        "weather_desc": wx_desc,
                        "weather_icon": wx_icon,
                        "stale": stale,
                        "trip_day": trip_day,
                        "trip_total": trip_total,
                        "elevation_ft": elevation_ft,
                        "odometer_miles": round(_state["odometer_miles"] + odo_delta, 1),
                    }
                    if crossing:
                        updates["state_crossing"] = crossing
                    _state.update(updates)

                db_save(fix_time, lat, lon, speed_mph, pos.get("course"), city_state)

        except Exception as e:
            log.error("Traccar poll: %s", e)
            with _lock:
                _state["stale"] = True

        time.sleep(5)

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/pdm.png")
def pdm_art():
    return send_from_directory(".", "pdm.png")

@app.route("/api/status")
def api_status():
    with _lock:
        return jsonify(dict(_state))

@app.route("/api/tips")
def api_tips():
    tips_path = os.path.join(os.path.dirname(__file__), "tips.txt")
    tips = []
    try:
        with open(tips_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("TIP|"):
                    tips.append(line[4:])
    except FileNotFoundError:
        pass
    return jsonify(tips)

@app.route("/live")
def live():
    return render_template("live.html")

@app.route("/dark")
def dark():
    return render_template("dark.html")

@app.route("/mobile")
def mobile():
    return render_template("mobile.html")

@app.route("/")
def index():
    return (
        "<h2>WATCHTOWER</h2>"
        "<a href='/live'>/live</a> &nbsp; <a href='/dark'>/dark</a> &nbsp; "
        "<a href='/mobile'>/mobile</a> &nbsp; <a href='/api/status'>/api/status</a>"
    )

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    init_db()

    history = db_load_route()
    odo = db_compute_odometer()
    last_lat, last_lon = db_last_position()
    with _lock:
        _state["route"] = history
        _state["odometer_miles"] = odo
    if last_lat is not None:
        _odo_last_lat, _odo_last_lon = last_lat, last_lon
    log.info("Loaded %d route points from DB, odometer %.1f mi", len(history), odo)

    threading.Thread(target=_traccar_poll, daemon=True).start()
    log.info("Traccar poll thread started")

    if _SPOTIPY_AVAILABLE and SPOTIFY_CLIENT_ID and os.path.exists(SPOTIFY_CACHE_PATH):
        threading.Thread(target=_spotify_poll, daemon=True).start()
        log.info("Spotify poll thread started")
    else:
        log.info("Spotify not configured — skipping (run auth_spotify.py to enable)")

    try:
        from waitress import serve
        log.info("WATCHTOWER starting on port %d (waitress)", FLASK_PORT)
        serve(app, host="0.0.0.0", port=FLASK_PORT)
    except ImportError:
        log.warning("waitress not installed — using Flask dev server")
        app.run(host="0.0.0.0", port=FLASK_PORT, debug=False)
