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

from src.main import parse_cli_args, main

if __name__ == "__main__":
    args = parse_cli_args()
    main(
        config_path=args.config,
        limit_override=args.limit,
        dry_run=args.dry_run,
        max_records=args.max_records,
        mode=args.mode,
        taxonomy_path=args.taxonomy,
        input_path=args.input,
        sample=args.sample,
        output_dir=getattr(args, "output_dir", None),
    )
