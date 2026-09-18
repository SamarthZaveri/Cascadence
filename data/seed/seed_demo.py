"""Phase 1 demo entry point; supports repo-root and Compose execution."""
import sys
from pathlib import Path

repo_backend = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(repo_backend if repo_backend.exists() else Path("/app")))

from app.services.ingestion.seed import main  # noqa: E402

if __name__ == "__main__":
    main()
