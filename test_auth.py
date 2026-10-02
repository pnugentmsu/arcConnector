"""Check that the cached login profile works, without any real data pull.

Run bootstrap_auth.py first if you haven't yet - this script relies on a
cached profile already being seeded (see that file for why).
"""
from arc_connector.auth import connect
from arc_connector.config import Config

config = Config.load("config.yaml")
gis = connect(config.org_url, config.client_id, config.profile)
print(f"Success - signed in as {gis.users.me.username}")
