"""Authentication against ArcGIS Online via the organization's SSO."""
from __future__ import annotations

import logging
import os

# The oauthlib library underlying arcgis's token exchange flags the
# "urn:ietf:wg:oauth:2.0:oob" redirect URI as non-https and refuses to
# proceed ("insecure_transport" error), even though the actual token
# exchange with ArcGIS Online still happens over HTTPS - it's a false
# positive triggered by the oob URI's scheme, not an actual downgrade to
# plain HTTP. This is the documented workaround.
os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from arcgis.gis import GIS

logger = logging.getLogger(__name__)


def connect(org_url: str, client_id: str, profile: str = "arc_connector") -> GIS:
    """Connect to ArcGIS Online using OAuth2 user login through the org's SSO.

    On first run this opens a browser window for your organization's identity
    provider login page. No password is ever seen or stored by this script;
    only an encrypted refresh token is cached locally under the given
    ``profile`` name (in the user's home directory), so later runs reuse it
    without prompting again until it expires.
    """
    gis = GIS(org_url, client_id=client_id, profile=profile)
    me = gis.users.me
    org_name = gis.properties.get("name", org_url)
    logger.info("Connected to '%s' as %s", org_name, me.username if me else "unknown user")
    return gis
