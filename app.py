"""Root entrypoint for Render and cloud deployments.

Launches the Research Dashboard web server and Live Search API.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure root directory is on sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from scripts.serve_dashboard import run

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    run(port=port, host=host)
