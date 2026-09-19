import re

from app.services.nlp.embeddings import embed_text
from app.services.nlp.entity_extraction import normalize_name, short_name

EVENTS = {
    "strike": (
        "labor strike workers stop production",
        r"\b(strike|walkout|industrial action)\b",
        0.7,
    ),
    "natural_disaster": (
        "earthquake flood hurricane damages factory",
        r"\b(earthquake|flood|hurricane|wildfire)\b",
        0.8,
    ),
    "geopolitical": (
        "war sanctions export restrictions disrupt supply",
        r"\b(war|sanctions|export ban)\b",
        0.75,
    ),
    "financial_distress": (
        "company bankruptcy insolvency financial distress",
        r"\b(bankruptcy|insolvency|default)\b",
        0.8,
    ),
    "regulatory": (
        "regulator recalls products shuts plant",
        r"\b(recall|antitrust|regulator|investigation)\b",
        0.5,
    ),
}


def classify_relevance(title: str, company: dict, embed=embed_text) -> float:
    aliases = {normalize_name(company["name"]), normalize_name(short_name(company["name"]))}
    if not any(
        re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", normalize_name(title))
        for a in aliases
        if len(a) >= 3
    ):
        return 0.0
    vectors = embed(
        [title, f"{short_name(company['name'])} company business operations supply chain"]
    )
    return max(0.0, min(1.0, float(vectors[0] @ vectors[1])))


def classify_event(title: str, embed=embed_text) -> dict:
    negated = bool(
        re.search(
            r"\b(no|not|avoids?|averts?|ends?|ended|resolved|may|might|could|risk of)\b",
            title,
            re.I,
        )
    )
    candidates = [(name, data) for name, data in EVENTS.items() if re.search(data[1], title, re.I)]
    if not candidates or negated:
        return {
            "event_type": "other",
            "severity_score": None,
            "classification_method": "headline_heuristic",
            "classification_note": "No unambiguous current disruption in headline",
        }
    vectors = embed([title] + [c[1][0] for c in candidates])
    similarities = vectors[1:] @ vectors[0]
    index = int(similarities.argmax())
    name, (_, _, severity) = candidates[index]
    return {
        "event_type": name,
        "severity_score": severity,
        "classification_method": "keyword_plus_minilm",
        "event_similarity": float(similarities[index]),
        "classification_note": "Unverified headline-level heuristic; not confirmed company impact",
    }
