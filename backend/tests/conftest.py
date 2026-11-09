import os
from pathlib import Path

os.environ.setdefault("MATCHBOOK_DB", str(Path(__file__).resolve().parents[2] / "evals" / "results" / "test.db"))
os.environ["MATCHBOOK_PACE"] = "0"
