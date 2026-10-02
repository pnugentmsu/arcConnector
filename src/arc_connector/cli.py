"""Command-line entry point for arc-connector."""
from __future__ import annotations

import argparse
import logging
import sys

from .auth import connect
from .config import Config
from .downloaders import download_attachments, download_feature_layer, download_image_service

logger = logging.getLogger(__name__)


def pull(config_path: str) -> int:
    config = Config.load(config_path)
    gis = connect(config.org_url, config.client_id, config.profile)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    failures = 0
    for item in config.items:
        try:
            if item.type == "feature":
                download_feature_layer(gis, item, config.output_dir)
                if item.include_attachments:
                    download_attachments(gis, item, config.output_dir)
            elif item.type == "image":
                download_image_service(gis, item, config.output_dir)
            else:
                raise ValueError(f"unknown item type '{item.type}' (expected 'feature' or 'image')")
        except Exception:
            failures += 1
            logger.exception("'%s': download failed", item.name)

    if failures:
        logger.error("%d of %d item(s) failed", failures, len(config.items))
    else:
        logger.info("All %d item(s) downloaded successfully", len(config.items))
    return 1 if failures else 0


def main(argv: list | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(prog="arc-connector")
    sub = parser.add_subparsers(dest="command", required=True)

    pull_parser = sub.add_parser("pull", help="Download configured layers/services")
    pull_parser.add_argument("--config", default="config.yaml", help="Path to config YAML file")

    args = parser.parse_args(argv)
    if args.command == "pull":
        return pull(args.config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
