"""Root CLI Entrypoint for the V0 Reddit Evidence Collection System.

Allows running the collector directly from the repository root:
    python main.py --dry-run
    python main.py --limit 10
    python main.py --config config/queries.yaml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure root is in sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.main import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="V0 Reddit Research Evidence-Collection Pipeline"
    )
    parser.add_argument(
        "--config",
        default="config/queries.yaml",
        help="Path to YAML configuration file (default: config/queries.yaml)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Override max results per query for sample runs (e.g. --limit 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and show what would run without collecting data",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Stop collection early after reaching target raw record count (e.g. --max-records 500)",
    )
    args = parser.parse_args()

    main(
        config_path=args.config,
        limit_override=args.limit,
        dry_run=args.dry_run,
        max_records=args.max_records,
    )
