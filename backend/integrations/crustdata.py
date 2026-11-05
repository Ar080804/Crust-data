"""Owner: Sunil. Cache every raw response in data/crustdata_cache/<key>.json and commit it."""


def verify(expert: dict) -> list[dict]:
    """Return a list of Claim dicts (see contract/CONTRACT.md):
    {text, status: verified|contradicted|unverifiable, evidence, source: "crustdata:person_enrich", fetched_at}"""
    raise NotImplementedError
