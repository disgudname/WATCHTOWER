"""
WATCHTOWER — one-time Spotify authorization.

Run this once on each machine before the trip:
    venv\Scripts\python auth_spotify.py

What it does:
  1. Opens a browser to Spotify's login page
  2. You log in and click Allow
  3. Spotify redirects to a page that won't load — that's fine
  4. You copy the full URL from the address bar and paste it here
  5. Token is saved to .spotify_cache and reused automatically from then on

Requires SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env.
Get them from https://developer.spotify.com/dashboard
"""

import os
import sys
import webbrowser
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

client_id     = os.getenv("SPOTIFY_CLIENT_ID", "")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "")
redirect_uri  = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback")
cache_path    = ".spotify_cache"

if not client_id or not client_secret:
    print("\n  ERROR: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set in .env")
    print("  Get them from https://developer.spotify.com/dashboard\n")
    sys.exit(1)

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    print("\n  ERROR: spotipy not installed. Run dev.ps1 first to set up the venv.\n")
    sys.exit(1)

auth_manager = SpotifyOAuth(
    client_id=client_id,
    client_secret=client_secret,
    redirect_uri=redirect_uri,
    scope="user-read-currently-playing user-read-playback-state",
    cache_path=cache_path,
    open_browser=False,
)

auth_url = auth_manager.get_authorize_url()

print()
print("  WATCHTOWER - Spotify Authorization")
print("  ------------------------------------")
print("  Opening Spotify in your browser...")
print("  Log in and click Allow.")
print("  You'll land on a page that won't load. That's fine.")
print("  Copy the full URL from the address bar and paste it below.")
print()

webbrowser.open(auth_url)

response_url = input("  Paste URL here: ").strip()

parsed = urlparse(response_url)
code   = parse_qs(parsed.query).get("code", [None])[0]

if not code:
    print("\n  ERROR: Couldn't find an auth code in that URL.")
    print("  Make sure you copied the full URL including '?code=...' at the end.\n")
    sys.exit(1)

try:
    auth_manager.get_access_token(code, as_dict=False)
    sp     = spotipy.Spotify(auth_manager=auth_manager)
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
    print("  You're all set. Restart WATCHTOWER and the now-playing widget will appear.")
    print()
except Exception as e:
    print(f"\n  Authorization failed: {e}\n")
    sys.exit(1)
