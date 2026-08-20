"""Reusable entry point for the standalone YouTube creator collector."""
from __future__ import annotations

import argparse
import os
import runpy
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
COLLECTOR = Path(__file__).resolve().with_name("collector.py")
DEFAULT_CREATORS = Path(__file__).resolve().with_name("creator_channels.json")


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--creator-config", type=Path, default=DEFAULT_CREATORS)
    args, remaining = parser.parse_known_args()
    if not COLLECTOR.is_file():
        raise SystemExit(f"Collector source was not found: {COLLECTOR}")
    if not args.creator_config.is_file():
        raise SystemExit(f"Creator configuration was not found: {args.creator_config}")

    os.environ["FEEDIT_YOUTUBE_OUTPUT_DIR"] = str(PIPELINE_DIR / "data" / "youtube")
    os.environ["FEEDIT_CREATOR_CONFIG_PATH"] = str(args.creator_config.resolve())
    os.chdir(PIPELINE_DIR)  # makes youtube_pipeline/.env discoverable
    sys.argv = [str(COLLECTOR), *remaining]
    runpy.run_path(str(COLLECTOR), run_name="__main__")


if __name__ == "__main__":
    main()
