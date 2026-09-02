import re
import json
import os

"""
validate_narrative_numbers.py -- safety net for any narrative text (LLM- or
human-written) that claims to connect real facts with prose.

The rule this enforces: narrative is allowed to connect real facts with
prose, but is NEVER allowed to introduce a number that isn't already
sitting in the verified facts JSON the templated layer already produced.
This is a concrete guardrail, not a promise -- a script that actually
checks. In production, this exact check caught a real rounding slip in the
first hand-written sample it was tested against ($59,417 written where the
source fact was $59,417.61) before it was ever wired to a live API call.

How it works: pulls every numeric value out of the source facts (any dict
already loaded in memory, or JSON files on disk -- see the two entry
points below) into one "allowed" set, covering every metric, description,
and worth_considering string. Then pulls every numeric value out of the
candidate narrative text the same way, and flags anything that doesn't
match an allowed number within a small rounding tolerance. This does NOT
judge whether the interpretation is reasonable -- only whether every
number quoted is real. Judgment about the prose itself is still a human's
job.
"""

NUMBER_RE = re.compile(r'-?\$?\d[\d,]*\.?\d*%?x?\b')


def extract_numbers(text):
    """Returns a set of floats found in text, money/percent/multiplier signs stripped."""
    out = set()
    for raw in NUMBER_RE.findall(text):
        cleaned = raw.replace('$', '').replace(',', '').replace('%', '').replace('x', '')
        try:
            out.add(round(float(cleaned), 2))
        except ValueError:
            continue
    return out


def _walk_collect(node, allowed):
    if isinstance(node, dict):
        for v in node.values():
            _walk_collect(v, allowed)
    elif isinstance(node, list):
        for v in node:
            _walk_collect(v, allowed)
    elif isinstance(node, str):
        allowed.update(extract_numbers(node))
    elif isinstance(node, (int, float)):
        allowed.add(round(float(node), 2))


def collect_allowed_numbers_from_data(*data_objects):
    """Same extraction as collect_allowed_numbers, but for dicts/lists
    already loaded in memory -- what ceo_weekly_memo.py uses, since it has
    the Senior Managers' output already parsed and doesn't need a second
    disk read."""
    allowed = set()
    for data in data_objects:
        _walk_collect(data, allowed)
    return allowed


def collect_allowed_numbers(*json_paths):
    allowed = set()
    for path in json_paths:
        if not os.path.exists(path):
            print(f"[WARN] Missing source file: {path}")
            continue
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _walk_collect(data, allowed)
    return allowed


def numbers_match(n, allowed, tol=0.5):
    """A narrative number is OK if it matches an allowed number exactly,
    matches when rounded to the nearest whole unit (covers $71,695 in
    prose vs $71,695.37 in the source fact), or is within a small absolute
    tolerance (covers minor rounding in percentages/ratios)."""
    if n in allowed:
        return True
    if round(n) in {round(a) for a in allowed}:
        return True
    return any(abs(n - a) <= tol for a in allowed)


def check_narrative(narrative_text, allowed_numbers):
    """Core check, usable directly on in-memory text + an already-built
    allowed set. Returns (is_valid, unmatched_list) -- what
    ceo_weekly_memo.py calls on each API-generated narrative before
    deciding whether to use it or fall back to the templated version."""
    narrative_numbers = extract_numbers(narrative_text)
    unmatched = sorted(n for n in narrative_numbers if not numbers_match(n, allowed_numbers))
    return len(unmatched) == 0, unmatched


def validate(narrative_path, *fact_json_paths):
    with open(narrative_path, 'r', encoding='utf-8') as f:
        narrative = f.read()

    allowed = collect_allowed_numbers(*fact_json_paths)
    narrative_numbers = extract_numbers(narrative)

    matched, unmatched = [], []
    for n in sorted(narrative_numbers):
        (matched if numbers_match(n, allowed) else unmatched).append(n)

    read_not_fact_count = narrative.count('[READ, NOT FACT:')

    print(f"Numbers found in narrative: {len(narrative_numbers)}")
    print(f"Matched against verified facts: {len(matched)}")
    print(f"UNMATCHED (would be flagged for review): {len(unmatched)}")
    if unmatched:
        for n in unmatched:
            print(f"  [FLAG] {n} -- not found in any source fact")
    print(f"\nInterpretation segments explicitly labeled [READ, NOT FACT: ...]: {read_not_fact_count}")
    print(f"\n[{'PASS' if not unmatched else 'FAIL -- needs review'}]")
    return len(unmatched) == 0
