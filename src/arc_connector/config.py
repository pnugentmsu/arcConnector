"""Config file loading for arc-connector."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ItemConfig:
    name: str
    type: str  # "feature" or "image"
    url: str
    format: str  # "shapefile" or "tiff"
    where: str = "1=1"
    out_sr: Optional[int] = None
    extent: Optional[list] = None  # [xmin, ymin, xmax, ymax], required for image
    size: Optional[list] = None  # [width, height] pixels, image only
    include_attachments: bool = False  # feature only: pull photos/files attached to features (e.g. Field Maps photos)


@dataclass
class Config:
    org_url: str
    client_id: str
    output_dir: Path
    profile: str = "arc_connector"
    items: list = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        data = yaml.safe_load(Path(path).read_text())
        items = [ItemConfig(**item) for item in data.get("items", [])]
        return cls(
            org_url=data["organization_url"],
            client_id=data["client_id"],
            output_dir=Path(data.get("output_dir", "./data")),
            profile=data.get("profile", "arc_connector"),
            items=items,
        )
