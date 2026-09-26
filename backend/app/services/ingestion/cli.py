import argparse
import json
from uuid import UUID

from app.services.ingestion.repository import augment, reconcile, review_relationship, writer_lock


def main():
    parser = argparse.ArgumentParser(description="Phase 2 source ingestion and review")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--tickers", nargs="+", required=True)
    ingest.add_argument("--days", type=int, default=7)
    ingest.add_argument("--queue", action="store_true")
    review = sub.add_parser("review")
    review.add_argument("--id", type=UUID, required=True)
    review.add_argument("--decision", choices=["approved", "rejected"], required=True)
    demo = sub.add_parser("augment")
    demo.add_argument("--company-id", type=UUID, required=True)
    demo.add_argument("--count", type=int, default=5)
    sub.add_parser("reconcile")
    sub.add_parser("score")
    cleanup = sub.add_parser("cleanup-synthetic")
    cleanup.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.command == "ingest":
        from app.services.ingestion.pipeline import run_ingestion_cycle, validate_tickers

        tickers = validate_tickers(args.tickers)
        if not 1 <= args.days <= 30:
            parser.error("days must be 1–30")
        if args.queue:
            from app.tasks.ingestion import ingest_sources

            result = {"task_id": ingest_sources.delay(tickers, args.days).id}
        else:
            result = run_ingestion_cycle(tickers, args.days)
    elif args.command == "review":
        result = review_relationship(args.id, args.decision)
    elif args.command == "augment":
        result = augment(args.company_id, args.count)
    elif args.command == "cleanup-synthetic":
        from app.services.ingestion.cleanup import cleanup_synthetic

        result = cleanup_synthetic(args.apply)
    elif args.command == "score":
        from app.services.gnn.registry import score_current as score_observed_network

        with writer_lock():
            result = score_observed_network()
    else:
        with writer_lock():
            result = reconcile()
    print(json.dumps(result, indent=2, default=str))
    if result.get("status") in {"partial", "failed"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
