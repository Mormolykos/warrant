"""Recompute every headline number in RESULTS.md and print PASS or FAIL.

    python audit_stats.py

Deliberately shares no code with measure.py. It re-parses the corpus, re-joins
the published axis booleans, and RE-DERIVES the checkable / not-checkable split
rather than trusting the `checkable` flag stored in the baseline files. If the
stored flag and the fresh derivation ever disagree, every rate in the results is
wrong and this says so on the line marked `stored flag vs fresh derivation`.

Exit code 0 if every number reproduces, 1 otherwise.
"""
from __future__ import annotations

import collections
import hashlib
import itertools
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
STATED = ("population", "intervention", "outcome_measure")
ALL_AXES = STATED + ("conditions", "methodology", "measurement")

fails: list[str] = []


def check(label, got, want):
    ok = (abs(got - want) <= 0.05) if isinstance(want, float) else (got == want)
    print(f"  {'PASS' if ok else 'FAIL'}  {label:54s} got={got}  claimed={want}")
    if not ok:
        fails.append(f"{label}: got {got}, RESULTS.md claims {want}")


def ztest(x1, n1, x2, n2):
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se if se else 0.0
    ci = 1.96 * math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return p1, p2, math.erfc(abs(z) / math.sqrt(2)), (p1 - p2 - ci, p1 - p2 + ci)


corpus = HERE / "mancon.xml"
if not corpus.exists():
    sys.exit("mancon.xml missing — run `python fetch_corpus.py` first")

stated = {}
for line in (DATA / "axes.jsonl").open(encoding="utf-8"):
    r = json.loads(line)
    stated[(r["pmid"], r["sentence_sha256"])] = r["stated"]

rows = []
for rev in ET.parse(corpus).getroot().findall("REVIEW"):
    for c in rev.findall("CLAIM"):
        t = (c.text or "").strip()
        k = (c.get("PMID"), hashlib.sha256(t.encode()).hexdigest()[:16])
        if k in stated:
            rows.append({"pmid": c.get("PMID"), "question": c.get("QUESTION"),
                         "assertion": c.get("ASSERTION"), "stated": stated[k]})

print("=== DATASET ===")
check("distinct sentences annotated", len(stated), 255)
check("corpus rows with axes", len(rows), 259)

groups = collections.defaultdict(list)
for r in rows:
    groups[r["question"]].append(r)
check("question groups", len(groups), 24)

opp, agr = [], []
for q, rs in groups.items():
    for a, b in itertools.combinations(rs, 2):
        (opp if a["assertion"] != b["assertion"] else agr).append((q, a, b))
check("opposed pairs", len(opp), 728)
check("agreeing pairs", len(agr), 1047)

print("\n=== FILL AND CHECKABILITY ===")
fill = collections.Counter()
for r in rows:
    for a in ALL_AXES:
        if r["stated"][a]:
            fill[a] += 1
for a, want in [("population", 181), ("intervention", 198), ("outcome_measure", 255),
                ("conditions", 83), ("methodology", 35), ("measurement", 21)]:
    check(f"stated: {a}", fill[a], want)


def is_checkable(a, b):
    return all(a["stated"][x] and b["stated"][x] for x in STATED)


chk = sum(1 for _, a, b in opp if is_checkable(a, b))
check("opposed pairs checkable", chk, 167)
check("opposed pairs NOT checkable (%)", round(100 * (len(opp) - chk) / len(opp), 1), 77.1)

print("\n=== DETERMINISTIC LAYER: WHY IT RETURNS 0 CONTRADICTIONS ===")
# CONTRADICTS requires every one of the six axes recorded on BOTH sides. That is
# decidable from the booleans alone, with no axis strings and no dependency on
# the library under test: if no pair states all six, no pair can ever be ruled a
# contradiction, whatever the strings say.
all_six = sum(1 for _, a, b in opp
              if all(a["stated"][x] and b["stated"][x] for x in ALL_AXES))
check("opposed pairs stating all SIX axes on both sides", all_six, 0)
print("        -> 0 pairs are eligible for a CONTRADICTS verdict, independent of")
print("           string matching. The reported 0/728 follows from the booleans.")

print("\n=== BASELINES ===")
keyed = {}
for f in sorted(DATA.glob("baseline_*.jsonl")):
    rs = [json.loads(l) for l in f.open(encoding="utf-8")]
    name = f.stem
    c = collections.Counter(r["verdict"] for r in rs)
    print(f"\n  -- {name}  n={len(rs)}")
    check(f"{name}: unparsed replies", c["UNPARSED"], 0)

    fresh = {}
    for q, a, b in opp:
        fresh[(a["pmid"], b["pmid"], hashlib.sha256(q.encode()).hexdigest()[:16])] = \
            is_checkable(a, b)
    mism = sum(1 for r in rs
               if (k := (r["pmid_a"], r["pmid_b"], r.get("question_sha", ""))) in fresh
               and fresh[k] != r["checkable"])
    check(f"{name}: stored flag vs fresh derivation", mism, 0)

    ck = [r for r in rs if r["checkable"]]
    un = [r for r in rs if not r["checkable"]]
    for lab in ("CONTRADICTION", "NOT_ENOUGH_INFO"):
        x1 = sum(1 for r in ck if r["verdict"] == lab)
        x2 = sum(1 for r in un if r["verdict"] == lab)
        if not ck or not un:
            continue
        p1, p2, pv, ci = ztest(x1, len(ck), x2, len(un))
        print(f"        {lab:17s} stated={100*p1:5.1f}%  not={100*p2:5.1f}%  "
              f"diff={100*(p1-p2):+5.1f}pp  p={pv:.3f}  95%CI[{100*ci[0]:+.1f},{100*ci[1]:+.1f}]")
    keyed[name] = {(r["pmid_a"], r["pmid_b"], r.get("question_sha", "")): r["verdict"]
                   for r in rs}

print("\n" + "=" * 74)
if fails:
    print(f"AUDIT FAILED — {len(fails)} discrepancies:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("AUDIT PASSED — every checked number reproduces from ./data and the corpus.")
