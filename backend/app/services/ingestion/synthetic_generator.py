"""Reproducible fictional multi-tier supplier DAGs; edges point supplier -> customer."""

import random
from datetime import date
from uuid import NAMESPACE_URL, uuid5

import networkx as nx

INDUSTRIES = ("Electronics", "Manufacturing", "Logistics", "Materials", "Energy", "Other")
RELATIONSHIPS = ("raw_material", "component", "logistics", "manufacturing")
COUNTRIES = ("India", "Germany", "Japan", "United States", "Brazil", "South Korea")
PREFIXES = ("Aster", "Meridian", "Northstar", "Cobalt", "Juniper", "Atlas", "Helix", "Solstice")
SUFFIXES = ("Components", "Industries", "Materials", "Logistics", "Systems", "Works")


def generate_network(
    num_companies: int = 60, num_tiers: int = 4, avg_out_degree: int = 2, seed: int = 42
) -> nx.DiGraph:
    if not 1 <= num_tiers <= num_companies <= 1000:
        raise ValueError("Require 1 <= num_tiers <= num_companies <= 1000")
    if num_tiers == 1 and num_companies != 1:
        raise ValueError("One tier supports the isolated focal company only")
    if not 1 <= avg_out_degree <= 10:
        raise ValueError("avg_out_degree must be between 1 and 10")
    rng = random.Random(seed)
    graph = nx.DiGraph()
    identity = f"cascadence-v1:{seed}:{num_companies}:{num_tiers}:{avg_out_degree}"
    for index in range(num_companies):
        tier = 0 if index == 0 else 1 + (index - 1) % (num_tiers - 1)
        node_id = str(uuid5(NAMESPACE_URL, f"{identity}:{index}"))
        graph.add_node(
            node_id,
            uuid=node_id,
            name=f"{rng.choice(PREFIXES)} {rng.choice(SUFFIXES)} {index + 1:03d}",
            industry=rng.choice(INDUSTRIES[:-1]),
            hq_country=rng.choice(COUNTRIES),
            is_synthetic=True,
            tier=tier,
        )
    for supplier in graph.nodes:
        tier = graph.nodes[supplier]["tier"]
        candidates = [n for n in graph if graph.nodes[n]["tier"] == tier - 1]
        count = min(len(candidates), rng.randint(max(1, avg_out_degree - 1), avg_out_degree + 1))
        for _ in range(count):
            customer = rng.choices(
                candidates, weights=[1 + graph.in_degree(n) for n in candidates]
            )[0]
            candidates.remove(customer)
            graph.add_edge(
                supplier,
                customer,
                criticality=round(rng.uniform(0.15, 0.95), 4),
                relationship_type=rng.choice(RELATIONSHIPS),
                since=date(2024, 1, 1),
            )
    return graph


def write_to_stores(graph: nx.DiGraph) -> None:
    # Local import keeps generation usable without database configuration.
    from app.services.ingestion.stores import persist_network

    persist_network(graph)
