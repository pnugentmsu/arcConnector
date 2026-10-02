"""Download feature layers (with attachments) to shapefile and image services to GeoTIFF.

Output layout under output_dir:
  shapefiles/<name>.shp (+ .dbf/.shx/.prj)   - one layer's features
  photos/<name>/                             - that layer's attachments
  photos/<name>/index.csv                    - each photo joined to its point's
                                                name/attributes and lat/lon
  imagery/<name>.tif                         - raster image service exports
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path

import shapefile  # pyshp
from arcgis.features import FeatureLayer
from arcgis.raster import ImageryLayer

from .config import ItemConfig

logger = logging.getLogger(__name__)

_SHAPE_TYPE_MAP = {
    "esriGeometryPoint": shapefile.POINT,
    "esriGeometryMultipoint": shapefile.MULTIPOINT,
    "esriGeometryPolyline": shapefile.POLYLINE,
    "esriGeometryPolygon": shapefile.POLYGON,
}

_DBF_TYPE_MAP = {
    "esriFieldTypeString": "C",
    "esriFieldTypeDate": "D",
    "esriFieldTypeInteger": "N",
    "esriFieldTypeSmallInteger": "N",
    "esriFieldTypeOID": "N",
    "esriFieldTypeDouble": "F",
    "esriFieldTypeSingle": "F",
}


def _dbf_field(field_def: dict) -> tuple:
    name = field_def["name"][:10]  # DBF field names are limited to 10 chars
    dbf_type = _DBF_TYPE_MAP.get(field_def["type"], "C")
    if dbf_type == "F":
        return (name, "F", 19, 11)
    if dbf_type == "N":
        return (name, "N", 18, 0)
    return (name, "C", 254)


def _write_geometry(writer: "shapefile.Writer", shape_type: int, geometry: dict | None) -> None:
    if not geometry:
        writer.null()
        return
    if shape_type == shapefile.POINT:
        writer.point(geometry["x"], geometry["y"])
    elif shape_type == shapefile.MULTIPOINT:
        writer.multipoint(geometry["points"])
    elif shape_type == shapefile.POLYLINE:
        writer.line(geometry["paths"])
    elif shape_type == shapefile.POLYGON:
        writer.poly(geometry["rings"])
    else:
        writer.null()


def _write_prj(out_path: Path, spatial_reference: dict | None) -> None:
    if not spatial_reference:
        return
    wkid = spatial_reference.get("latestWkid") or spatial_reference.get("wkid")
    if not wkid:
        return
    try:
        from pyproj import CRS

        wkt = CRS.from_epsg(wkid).to_wkt()
        out_path.with_suffix(".prj").write_text(wkt)
    except Exception:
        logger.warning(
            "Could not write .prj for %s (WKID %s) - set the projection manually in your GIS software.",
            out_path.name,
            wkid,
        )


def download_feature_layer(gis, item: ItemConfig, output_dir: Path) -> Path:
    layer = FeatureLayer(item.url, gis=gis)
    feature_set = layer.query(where=item.where, out_sr=item.out_sr, out_fields="*")
    features = feature_set.features
    if not features:
        raise ValueError(f"'{item.name}': query returned no features")

    shape_type = _SHAPE_TYPE_MAP.get(feature_set.geometry_type)
    if shape_type is None:
        raise ValueError(f"'{item.name}': unsupported geometry type {feature_set.geometry_type}")

    shapefiles_dir = output_dir / "shapefiles"
    shapefiles_dir.mkdir(parents=True, exist_ok=True)
    out_path = shapefiles_dir / item.name

    fields = feature_set.fields
    with shapefile.Writer(str(out_path), shapeType=shape_type) as writer:
        for f in fields:
            writer.field(*_dbf_field(f))
        for feat in features:
            _write_geometry(writer, shape_type, feat.geometry)
            writer.record(*[feat.attributes.get(f["name"]) for f in fields])

    _write_prj(out_path, feature_set.spatial_reference)
    logger.info("'%s': wrote %d features to %s", item.name, len(features), out_path.with_suffix(".shp"))
    return out_path.with_suffix(".shp")


def _attachment_field(info: dict, *names: str):
    for name in names:
        if name in info:
            return info[name]
    return None


def download_attachments(gis, item: ItemConfig, output_dir: Path) -> list:
    """Download photos/files attached to features (e.g. Field Maps photos).

    These live in the layer's attachment table, not as a raster/image
    service, so they're pulled via the attachments REST resource rather than
    export_image. Each layer's photos go in their own folder, with an index
    CSV joining every photo back to its parent feature's own attributes
    (e.g. a point name field) and its lat/lon (reprojected to WGS84), so
    photos can be mapped or matched to a point independently of the
    shapefile.
    """
    layer = FeatureLayer(item.url, gis=gis)

    # Pull parent feature attributes + lat/lon so each attachment can carry
    # its point's identifying info without needing the shapefile alongside it.
    feature_set = layer.query(where=item.where or "1=1", out_fields="*", out_sr=4326)
    oid_field = feature_set.object_id_field_name or "OBJECTID"
    attribute_fields = [f["name"] for f in feature_set.fields if f["name"] != oid_field]
    features_by_oid = {}
    for feat in feature_set.features:
        oid = feat.attributes.get(oid_field)
        geometry = feat.geometry or {}
        features_by_oid[oid] = {
            "latitude": geometry.get("y"),
            "longitude": geometry.get("x"),
            "attributes": {k: v for k, v in feat.attributes.items() if k != oid_field},
        }

    try:
        infos = layer.attachments.search(where=item.where or "1=1")
    except TypeError:
        infos = layer.attachments.search()

    if not infos:
        logger.info("'%s': no attachments found", item.name)
        return []

    photos_dir = output_dir / "photos" / item.name
    photos_dir.mkdir(parents=True, exist_ok=True)

    base_columns = ["attachment_file", "parent_objectid", "latitude", "longitude", "attachment_id", "attachment_name", "content_type"]
    index_rows = []
    saved_paths = []
    for info in infos:
        parent_oid = _attachment_field(info, "PARENTOBJECTID", "parentObjectId")
        attachment_id = _attachment_field(info, "ID", "id")
        name = _attachment_field(info, "NAME", "name") or f"attachment_{attachment_id}"
        content_type = _attachment_field(info, "CONTENTTYPE", "contentType")
        feature_info = features_by_oid.get(parent_oid, {})

        # Field Maps often names photos generically per point ("Photo 1.jpg"),
        # so a shared flat folder would silently overwrite attachments from
        # different points that happen to share a name. One subfolder per
        # parent feature keeps every photo, and also groups a point's own
        # photos together.
        dest_dir = photos_dir / str(parent_oid)
        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = layer.attachments.download(
                oid=parent_oid,
                attachment_id=attachment_id,
                save_path=str(dest_dir),
            )
            paths = result if isinstance(result, list) else [result]
            for p in paths:
                saved_paths.append(Path(p))
                row = {
                    "attachment_file": f"{parent_oid}/{Path(p).name}",
                    "parent_objectid": parent_oid,
                    "latitude": feature_info.get("latitude"),
                    "longitude": feature_info.get("longitude"),
                    "attachment_id": attachment_id,
                    "attachment_name": name,
                    "content_type": content_type,
                }
                row.update(feature_info.get("attributes", {}))
                index_rows.append(row)
        except Exception:
            logger.exception(
                "'%s': failed to download attachment %s (%s) for feature %s",
                item.name,
                attachment_id,
                name,
                parent_oid,
            )

    fieldnames = base_columns + [f for f in attribute_fields if f not in base_columns]
    index_path = photos_dir / "index.csv"
    with open(index_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(index_rows)

    logger.info(
        "'%s': downloaded %d attachment(s) to %s (index: %s)",
        item.name,
        len(saved_paths),
        photos_dir,
        index_path,
    )
    return saved_paths


def download_image_service(gis, item: ItemConfig, output_dir: Path) -> Path:
    if not item.extent or len(item.extent) != 4:
        raise ValueError(f"'{item.name}': image downloads require an 'extent' [xmin, ymin, xmax, ymax] in the config")

    layer = ImageryLayer(item.url, gis=gis)
    xmin, ymin, xmax, ymax = item.extent
    width, height = item.size or [2048, 2048]

    imagery_dir = output_dir / "imagery"
    imagery_dir.mkdir(parents=True, exist_ok=True)

    result = layer.export_image(
        bbox=f"{xmin},{ymin},{xmax},{ymax}",
        size=[width, height],
        export_format="tiff",
        f="image",
        save_folder=str(imagery_dir),
        save_file=f"{item.name}.tif",
    )
    out_path = Path(result) if result else imagery_dir / f"{item.name}.tif"
    logger.info("'%s': wrote imagery to %s", item.name, out_path)
    return out_path
