"""
Neo4j driver wrapper. The driver object itself does not open a network connection on
creation — `neo4j.GraphDatabase.driver()` is lazy — so importing/booting the app never
requires a live Neo4j instance. Use `verify_connectivity()` explicitly (e.g. in a
startup health check or readiness probe) when you actually need to know it's reachable.
"""
from collections.abc import Generator
from contextlib import contextmanager

from neo4j import Driver, GraphDatabase, Session

from app.config import get_settings

settings = get_settings()

_driver: Driver | None = None


def get_driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
    return _driver


@contextmanager
def get_neo4j_session() -> Generator[Session, None, None]:
    driver = get_driver()
    session = driver.session()
    try:
        yield session
    finally:
        session.close()


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
