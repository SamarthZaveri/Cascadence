import re
from functools import lru_cache
from pathlib import Path

import spacy
from rapidfuzz import fuzz, process
from spacy.matcher import PhraseMatcher
from spacy.tokens import Doc

from app.config import get_settings


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", name.lower())).strip()


def short_name(name: str) -> str:
    return re.sub(
        r"(?i)(?:[, ]+(?:incorporated|inc|corporation|corp|limited|ltd|plc|co)\.?)+$", "", name
    ).strip()


@lru_cache
def language_model():
    path = Path(get_settings().NLP_CACHE_DIR) / "spacy"
    if not (path / "config.cfg").exists():
        raise RuntimeError("spaCy model missing. Run python -m app.services.nlp.setup first")
    return spacy.load(path)


class EntityResolver:
    def __init__(self, directory: list[dict]):
        self.aliases: dict[str, list[dict]] = {}
        self.matcher: PhraseMatcher | None = None
        for company in directory:
            for alias in {
                normalize_name(company["name"]),
                normalize_name(short_name(company["name"])),
            }:
                if len(alias) >= 3:
                    self.aliases.setdefault(alias, []).append(company)

    def resolve(self, name: str) -> tuple[dict | None, float]:
        key = normalize_name(name)
        unique = {row["cik"]: row for row in self.aliases.get(key, [])}
        if len(unique) == 1:
            return next(iter(unique.values())), 1.0
        if unique or len(key) < 6:
            return None, 0.0
        candidates = process.extract(key, self.aliases.keys(), scorer=fuzz.ratio, limit=2)
        if (
            candidates
            and candidates[0][1] >= 92
            and (len(candidates) == 1 or candidates[0][1] - candidates[1][1] >= 8)
        ):
            matches = {row["cik"]: row for row in self.aliases[candidates[0][0]]}
            if len(matches) == 1:
                return next(iter(matches.values())), candidates[0][1] / 100
        return None, 0.0

    def mentions(self, doc) -> list[tuple[str, dict, float]]:
        found = []
        for entity in doc.ents:
            if entity.label_ == "ORG":
                company, confidence = self.resolve(entity.text)
                if company:
                    found.append((entity.text, company, confidence))
        if self.matcher is None:
            self.matcher = PhraseMatcher(doc.vocab, attr="LOWER")
            self.matcher.add(
                "COMPANY", [Doc(doc.vocab, words=a.split()) for a in self.aliases if len(a) >= 5]
            )
        normalized = Doc(doc.vocab, words=normalize_name(doc.text).split())
        for _, start, end in self.matcher(normalized):
            alias = normalized[start:end].text
            company, confidence = self.resolve(alias)
            if company and all(company["cik"] != row[1]["cik"] for row in found):
                found.append((alias, company, confidence))
        return found
