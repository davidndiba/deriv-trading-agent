"""Adds the repo root to sys.path.

Running `python scripts/run_phaseN.py` directly puts only `scripts/` on
sys.path, not the repo root, so the top-level packages (agents/, config/,
schemas/, storage/, tools/) aren't importable without this. Importing this
module first (it's a plain sibling file, already reachable via the same
default sys.path entry) fixes that for every script without requiring
`PYTHONPATH=.` or a package install.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
