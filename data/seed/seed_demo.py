"""
Fresh-clone demo seeding script (see README.md "Quick start").

Phase 0: stub only — confirms it can import the app package and connect nowhere.
Phase 1 onward, this will:
  1. Run services/ingestion/synthetic_generator.py to populate a demo workspace
  2. Ingest a small real SEC/GDELT dataset (Phase 2)
  3. Load the three curated backtest datasets (Phase 5)
  4. Run one full inference -> explanation -> recommendation cycle (Phase 4/5/6)

Run via: docker compose exec backend python data/seed/seed_demo.py
"""
import sys


def main() -> None:
    print("[seed_demo] Phase 0 stub — nothing to seed yet.")
    print("[seed_demo] Real seeding starts in Phase 1 (see PRD.md §10).")


if __name__ == "__main__":
    sys.exit(main())
