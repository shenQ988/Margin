"""Hallucination eval: known-injection testing against real WeRead highlights.

Salts a book's REAL highlighted content (pulled from your actual WeRead
shelf) with a few deliberately false claims, then measures whether the
agent's answers repeat the planted falsehoods as fact (``repeated_injection``)
or invent something traceable to neither the real nor injected content at
all (``free_invention``). These are tracked as separate metrics throughout
— see eval/hallucination/scorer.py.

Two-stage workflow, run as separate commands:

    python -m eval.hallucination.build_fixtures --list
    python -m eval.hallucination.build_fixtures --book-ids <id1> <id2> ...
        (then manually review fixtures_draft.json and copy/edit it into
        fixtures_reviewed.json yourself — never automated)

    python -m eval.hallucination.run_hallucination_eval
"""
