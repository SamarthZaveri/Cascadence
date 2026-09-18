"""python -m app.services.ingestion.seed --seed 42"""

import argparse
import json

from sqlalchemy import text

from app.db.neo4j_client import close_driver, get_driver
from app.db.postgres import engine
from app.services.gnn.infer import run_inference
from app.services.gnn.train import train_model
from app.services.ingestion.stores import read_network
from app.services.ingestion.synthetic_generator import generate_network, write_to_stores


def seed_demo(
    num_companies: int = 60,
    num_tiers: int = 4,
    avg_out_degree: int = 2,
    seed: int = 42,
    epochs: int = 120,
) -> dict:
    if seed < 0:
        raise ValueError("Demo seed must be nonnegative; negative seeds are reserved for training")
    graph = generate_network(num_companies, num_tiers, avg_out_degree, seed)
    # Serialize seed runs; fail quickly if another command is already running.
    with engine.connect() as connection:
        locked = connection.execute(text("SELECT pg_try_advisory_lock(18092026)")).scalar()
        connection.commit()
        if not locked:
            raise RuntimeError("Another seed run is active; retry after it completes")
        try:
            get_driver().verify_connectivity()
            write_to_stores(graph)
            persisted = read_network(list(graph.nodes))
            model, metrics = train_model(epochs=epochs, seed=seed)
            return run_inference(persisted, model, metrics, seed)
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(18092026)"))
            connection.commit()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate, train and score a synthetic demo network"
    )
    parser.add_argument("--num-companies", type=int, default=60)
    parser.add_argument("--num-tiers", type=int, default=4)
    parser.add_argument("--avg-out-degree", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--epochs", type=int, default=120)
    args = parser.parse_args()
    try:
        result = seed_demo(**vars(args))
        print(json.dumps(result, indent=2))
        print("Open http://localhost:3000/dashboard — synthetic companies and scores.")
    finally:
        close_driver()


if __name__ == "__main__":
    main()
