"""
WATCHTOWER — one-time Spotify authorization.

Run this once on each machine before the trip:
    python auth_spotify.py   (inside the venv, or via dev.ps1 first to set it up)

What it does:
  1. Opens a browser to Spotify's login page
  2. You log in and click Allow
  3. Spotify redirects to localhost:8888/callback — the page won't load, that's fine
  4. Copy the full URL from the address bar and paste it when prompted
  5. Token is saved to .spotify_cache and reused automatically from then on

Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env.
Get them from https://developer.spotify.com/dashboard — create a free app,
then add http://localhost:8888/callback as a Redirect URI in the app settings.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

client_id     = os.getenv("SPOTIFY_CLIENT_ID", "")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
redirect_uri  = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
cache_path    = ".spotify_cache"

if not client_id or not client_secret:
    print("\n  ERROR: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in .env")
    print("  Get them from https://developer.spotify.com/dashboard\n")
    sys.exit(1)

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    print("\n  ERROR: spotipy not installed. Run:  pip install spotipy\n")
    sys.exit(1)

print()
print("  WATCHTOWER - Spotify Authorization")
print("  ------------------------------------")
print("  1. A browser window will open — log in to Spotify and click Allow.")
print("  2. You'll be sent to a page that won't load. That's expected.")
print("  3. Copy the full URL from the address bar and paste it below.")
print()

auth_manager = SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    scope="user-read-currently-playing user-read-playback-state",
    cache_path=cache_path,
    open_browser=True,
)

sp = spotipy.Spotify(auth_manager=auth_manager)

try:
    result = sp.current_playback()
    print()
    print("  Authorization successful. Token saved to .spotify_cache")
    if result and result.get("is_playing") and result.get("item"):
        track  = result["item"]
        artist = ", ".join(a["name"] for a in track["artists"])
        print(f"  Now playing: {track['name']} - {artist}")
    else:
        print("  (Nothing playing right now - that's fine.)")
    print()
    print("  WATCHTOWER will use this token automatically from now on.")
    print("  You do not need to run this script again unless you revoke access.")
    print()
except Exception as e:
    print(f"\n  Authorization failed: {e}\n")
    sys.exit(1)
