"""Extract reviewable evidence, never auto-approve a commercial relationship."""

import re

from app.services.nlp.entity_extraction import EntityResolver, language_model, normalize_name

NEGATED = re.compile(
    r"\b(no longer|not|never|may|might|could|would|if|previously|potential)\b", re.I
)


def extract_supplier_mentions(
    text: str, filer: dict, directory: list[dict], nlp=None
) -> list[dict]:
    nlp = nlp or language_model()
    resolver = EntityResolver(directory)
    blocks = re.split(r"(?<=[.!?])\s+", text)
    relevant = [
        b
        for b in blocks
        if re.search(
            r"\b(suppl\w*|sourc\w*|manufactur\w*|customer\w*|purchas\w*|sell\w*|provid\w*|buy)\b",
            b,
            re.I,
        )
    ]
    results = {}
    for doc in nlp.pipe([b[:12000] for b in relevant[:3000]], batch_size=32):
        sentence = doc.text
        if NEGATED.search(sentence):
            continue
        normalized = normalize_name(sentence)
        for mention, company, confidence in resolver.mentions(doc):
            if company["cik"] == filer["cik"]:
                continue
            alias = re.escape(normalize_name(mention))
            supplier = bool(
                re.search(
                    r"\b(?:we|our company)\b.{0,90}\b(?:source|purchase|buy)\w*.{0,60}\bfrom\s+"
                    + alias,
                    normalized,
                )
                or re.search(
                    alias + r".{0,60}\b(?:supplies|provides)\b.{0,60}\b(?:us|our)\b", normalized
                )
                or re.search(
                    r"\bour suppliers?\b.{0,40}\b(?:include|is|are)\b.{0,40}" + alias, normalized
                )
            )
            customer = bool(
                re.search(r"\bwe\s+(?:supply|sell|provide)\b.{0,80}\bto\s+" + alias, normalized)
            )
            if supplier == customer:
                continue
            source, target = (company, filer) if supplier else (filer, company)
            relation = (
                "logistics"
                if re.search(r"\b(ship|transport|logistics)", normalized)
                else ("raw_material" if "raw material" in normalized else "component")
            )
            match = re.search(r"\W+".join(re.escape(p) for p in mention.split()), sentence, re.I)
            start = max(0, match.start() - 500) if match else 0
            results[(source["cik"], target["cik"])] = {
                "supplier": source,
                "customer": target,
                "relationship_type": relation,
                "confidence": round(confidence * 0.95, 4),
                "evidence": sentence[start : start + 1200],
                "status": "pending",
            }
    return list(results.values())
