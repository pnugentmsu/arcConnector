"""One-time interactive sign-in to seed the cached login profile.

Works around a bug in this version of the `arcgis` package: its built-in
interactive (oob) sign-in path passes a bogus `authorization_response`
value into oauthlib's token exchange, which then tries to parse that
literal string as a callback URL and crashes with
"MismatchingStateError: CSRF Warning! State not equal in request and
response" - regardless of what code you actually enter.

This script performs the OAuth2 authorization-code exchange directly
instead (the same request ArcGIS Online expects, just without the stray
argument), then hands the resulting refresh token to GIS() via its
`password=` argument - which is arc_connector's normal, un-buggy code path
for reusing a login (see auth.py). That call also seeds the cached
profile, so after this succeeds once, `arc-connector pull` and
test_auth.py will reuse the cached profile without ever hitting the buggy
interactive path again (until the refresh token expires or is revoked -
if that happens, just rerun this script).
"""
import os
import webbrowser
from pathlib import Path

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from arcgis.gis import GIS
from requests_oauthlib import OAuth2Session

from arc_connector.config import Config

CODE_FILE = Path("auth_code.txt")


def get_code_from_user(prompt: str) -> str:
    print(prompt)
    if CODE_FILE.exists():
        CODE_FILE.unlink()
    print("If pasting into this terminal doesn't work:")
    print("  1. Open Notepad, paste the code there")
    print(f"  2. Save it as: {CODE_FILE.resolve()}")
    print("  3. Come back here and press Enter (just Enter - no paste needed)")
    typed = input().strip()
    if CODE_FILE.exists():
        code = CODE_FILE.read_text().strip()
        CODE_FILE.unlink()
        return code
    return typed


def main() -> None:
    config = Config.load("config.yaml")
    org_url = config.org_url.rstrip("/")
    client_id = config.client_id

    oauth = OAuth2Session(client_id, redirect_uri="urn:ietf:wg:oauth:2.0:oob")
    authorization_url, _state = oauth.authorization_url(
        f"{org_url}/sharing/rest/oauth2/authorize", allow_verification="false"
    )

    print("Opening your browser to sign in via your organization's SSO...")
    webbrowser.open_new(authorization_url)
    print(f"If it didn't open, go to this URL yourself:\n{authorization_url}\n")

    code = get_code_from_user("Enter the code ArcGIS shows after you sign in:")

    token = oauth.fetch_token(
        f"{org_url}/sharing/rest/oauth2/token",
        code=code,
        include_client_id=True,
    )
    refresh_token = token["refresh_token"]

    gis = GIS(org_url, client_id=client_id, password=refresh_token, profile=config.profile)
    print(f"Success - signed in as {gis.users.me.username}")
    print(f"Cached under profile '{config.profile}' - future runs won't need this step again.")


if __name__ == "__main__":
    main()
