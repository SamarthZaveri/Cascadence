"""Default demo installs real catalog data. Synthetic training is explicit opt-in."""
import sys
from pathlib import Path

repo_backend = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(repo_backend if repo_backend.exists() else Path("/app")))

if __name__ == "__main__":
    if "--synthetic" in sys.argv:
        sys.argv.remove("--synthetic")
        from app.services.ingestion.seed import main

        main()
    else:
        from app.services.extra_signals.cli import main

        if len(sys.argv) > 1:
            raise SystemExit("For legacy synthetic training, pass --synthetic explicitly")
        sys.argv = [sys.argv[0], "bootstrap"]
        main()
