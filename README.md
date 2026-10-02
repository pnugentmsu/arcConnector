# arc-connector

Pulls feature layers and imagery from ArcGIS Online down to local files
(shapefile for vector data, GeoTIFF for imagery), authenticating through
your organization's SSO.

## Setup

1. Install (from the repo root, ideally in a virtualenv):

   ```bash
   pip install -e .
   ```

2. Get a `client_id` for scripted access. In your ArcGIS Online org:
   - Content -> New item -> Developer credentials (or "Application")
   - Register a new application; note its Client ID
   - Under the app's Authentication settings, add a redirect URI:
     `urn:ietf:wg:oauth:2.0:oob` (works for the interactive login flow used
     here)

   If you don't have privileges to create one, ask your ArcGIS Online
   administrator for a client_id, or check whether the org already has one
   set up for scripted/notebook access.

3. Copy the example config and fill in your org URL, client_id, and the
   layers/services you want:

   ```bash
   cp config.example.yaml config.yaml
   ```

## Authentication (SSO)

This connects via OAuth2 user login against your organization's named URL
(`https://yourorg.maps.arcgis.com`), which redirects through whatever
identity provider your org uses (Azure AD, Okta, etc.) — the same login
screen you'd see signing into ArcGIS Online in a browser. No password is
entered into or stored by this tool.

On first run, a browser window opens for you to sign in and approve the
app. After that, an encrypted refresh token is cached locally under the
`profile` name from your config, so future runs won't prompt again until it
expires.

## Usage

```bash
arc-connector pull --config config.yaml
```

Each item in `config.yaml` is one of:

- `type: feature` — a Feature Layer URL, exported to a shapefile (`.shp` +
  `.dbf` + `.shx` + `.prj`) in `output_dir`. Point, line, and polygon
  geometry are all supported (auto-detected from the layer) - a Field Maps
  survey typically publishes one sublayer per geometry type
  (`FeatureServer/0`, `/1`, `/2`, ...), so add one item per sublayer.
  Supports an optional `where` SQL filter and `out_sr`.
  - `include_attachments: true` additionally downloads any files attached
    to features - e.g. photos taken in Field Maps at a point/line/polygon.
    These come from the layer's attachment table, not from an image
    service, since they're files tied to individual features rather than a
    continuous raster. Saved to `<output_dir>/<name>_attachments/`, with an
    index CSV (`<output_dir>/<name>_attachments_index.csv`) mapping each
    file back to its parent feature's `OBJECTID` so you can join photos to
    the shapefile.
- `type: image` — a true raster Image Service (e.g. orthoimagery/basemap
  imagery), exported to a `.tif` in `output_dir`. This is for continuous
  raster data, not photos attached to features (use `include_attachments`
  for those). Requires `extent` (`[xmin, ymin, xmax, ymax]`) and accepts an
  optional `size` in pixels.

## Notes / limitations

- Shapefile field names are truncated to 10 characters (a DBF format
  limit) — if you have long or similar field names that collide after
  truncation, rename them in the source layer or switch to a different
  output format.
- Large imagery exports are bound by the image service's max export size
  and your org's usage limits; keep `extent`/`size` reasonable, or split
  large areas into multiple items.
- Requires permission in your ArcGIS Online org to view/export each layer
  or service you configure.
