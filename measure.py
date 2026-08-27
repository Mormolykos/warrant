"""Every number reported in RESULTS.md, computed from ./data.

    python measure.py

Reads whatever `data/baseline_*.jsonl` files exist, so it reports the completed
baseline and any prompt-sensitivity runs together, in one table. Nothing is
cherry-picked: every baseline file present is reported.

The vocabulary-distance section needs the extracted axis STRINGS, which are not
published (see LICENSE-DATA). It runs only if `data/axes_local.jsonl` exists from
a local `extract_axes.py` run, and says so plainly when it does not.
"""
from __future__ import annotations

import collections
import hashlib
import itertools
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE / "data"
STATED = ("population", "intervention", "outcome_measure")
ALL_AXES = STATED + ("conditions", "methodology", "measurement")

STOP = set("""a an the of in on for with without to and or is are was were be been
being at by from as that this these those it its their his her not no than then
does do did which who whom whose we our us they them he she compared comparison
versus vs group groups patients subjects study studies trial trials effect
effects associated association increase increased decrease decreased risk""".split())


def toks(s):
    return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower())
            if w not in STOP and len(w) > 2}


def jaccard(a, b):
    ta, tb = toks(a), toks(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else None


def ztest(x1, n1, x2, n2):
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se if se else 0.0
    ci = 1.96 * math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return p1, p2, math.erfc(abs(z) / math.sqrt(2)), (p1 - p2 - ci, p1 - p2 + ci)


def load_rows():
    """Corpus rows joined to published axis booleans, keyed by (pmid, sentence)."""
    corpus = HERE / "mancon.xml"
    if not corpus.exists():
        sys.exit("mancon.xml missing — run `python fetch_corpus.py` first")
    stated, wc = {}, {}
    for line in (DATA / "axes.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        stated[(r["pmid"], r["sentence_sha256"])] = r["stated"]
        wc[(r["pmid"], r["sentence_sha256"])] = r["axis_word_count"]
    rows = []
    for rev in ET.parse(corpus).getroot().findall("REVIEW"):
        for c in rev.findall("CLAIM"):
            t = (c.text or "").strip()
            k = (c.get("PMID"), hashlib.sha256(t.encode()).hexdigest()[:16])
            if k in stated:
                rows.append({"pmid": c.get("PMID"), "question": c.get("QUESTION"),
                             "assertion": c.get("ASSERTION"), "text": t,
                             "stated": stated[k], "wc": wc[k], "key": k})
    return rows


def main() -> None:
    rows = load_rows()
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r["question"]].append(r)

    print("=" * 74)
    print("ManConCorpus (Alamri & Stevenson 2016), CC BY-NC-SA 2.0 UK — not redistributed")
    print(f"claim rows {len(rows)}   question groups {len(groups)}")
    print("=" * 74)

    print("\n[1] WHAT A CLAIM SENTENCE STATES")
    fill = collections.Counter()
    for r in rows:
        for a in ALL_AXES:
            if r["stated"][a]:
                fill[a] += 1
    for a in ALL_AXES:
        print(f"    {a:17s} {fill[a]:3d}/{len(rows)}  {100*fill[a]/len(rows):5.1f}%")

    opp, agr = [], []
    for q, rs in groups.items():
        for a, b in itertools.combinations(rs, 2):
            (opp if a["assertion"] != b["assertion"] else agr).append((q, a, b))
    print(f"\n    opposed pairs {len(opp)}   agreeing pairs {len(agr)}")

    print("\n[2] CAN COMPARABILITY BE VERIFIED FROM THE SENTENCES?")
    for name, pairs in (("OPPOSED", opp), ("AGREEING", agr)):
        full = sum(1 for _, a, b in pairs
                   if all(a["stated"][x] and b["stated"][x] for x in STATED))
        print(f"    {name:9s} n={len(pairs):5d}   all three stated both sides "
              f"{full:5d} ({100*full/len(pairs):5.1f}%)   "
              f"unverifiable {len(pairs)-full:5d} ({100*(len(pairs)-full)/len(pairs):5.1f}%)")
    miss = collections.Counter()
    for _, a, b in opp:
        for x in STATED:
            if not (a["stated"][x] and b["stated"][x]):
                miss[x] += 1
    print("    missing axis, opposed pairs:")
    for x, n in miss.most_common():
        print(f"      {x:17s} {n:5d}  {100*n/len(opp):5.1f}%")

    # ---- baselines, every file present -----------------------------------
    files = sorted(DATA.glob("baseline_*.jsonl"))
    if files:
        print(f"\n[3] MODEL BASELINES — {len(files)} run(s) found, all reported")
        print(f"    {'run':38s} {'n':>5s} {'CONTRA':>7s} {'NO':>7s} {'NEI':>7s} {'UNP':>4s}")
        table = {}
        for f in files:
            rs = [json.loads(l) for l in f.open(encoding="utf-8")]
            c = collections.Counter(r["verdict"] for r in rs)
            table[f.stem] = rs
            print(f"    {f.stem[:38]:38s} {len(rs):5d} "
                  f"{100*c['CONTRADICTION']/len(rs):6.1f}% {100*c['NO_CONTRADICTION']/len(rs):6.1f}% "
                  f"{100*c['NOT_ENOUGH_INFO']/len(rs):6.1f}% {c['UNPARSED']:4d}")

        print("\n[4] THE TEST: does the verdict depend on whether the text states the conditions?")
        print(f"    {'run':38s} {'measure':16s} {'stated':>7s} {'not':>7s} {'diff':>8s} {'p':>7s}")
        for name, rs in table.items():
            ck = [r for r in rs if r["checkable"]]
            un = [r for r in rs if not r["checkable"]]
            if not ck or not un:
                continue
            for lab in ("CONTRADICTION", "NOT_ENOUGH_INFO"):
                x1 = sum(1 for r in ck if r["verdict"] == lab)
                x2 = sum(1 for r in un if r["verdict"] == lab)
                p1, p2, pv, ci = ztest(x1, len(ck), x2, len(un))
                print(f"    {name[:38]:38s} {lab:16s} {100*p1:6.1f}% {100*p2:6.1f}% "
                      f"{100*(p1-p2):+7.1f}pp {pv:7.3f}   95%CI[{100*ci[0]:+.1f},{100*ci[1]:+.1f}]")

        print("\n[5] PAIRWISE AGREEMENT BETWEEN RUNS")
        keyed = {n: {(r["pmid_a"], r["pmid_b"], r.get("question_sha", "")): r["verdict"]
                     for r in rs} for n, rs in table.items()}
        names = sorted(keyed)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                common = set(keyed[a]) & set(keyed[b])
                if not common:
                    continue
                ag = sum(1 for k in common if keyed[a][k] == keyed[b][k])
                print(f"    {a[:34]:34s} vs {b[:34]:34s} {ag:4d}/{len(common):4d} = {100*ag/len(common):5.1f}%")

    # ---- vocabulary distance, local strings only -------------------------
    local = DATA / "axes_local.jsonl"
    print("\n[6] VOCABULARY DISTANCE BETWEEN STATED AXES")
    if not local.exists():
        print("    SKIPPED — needs the extracted axis strings, which are not published.")
        print("    Run:  python extract_axes.py --backend ollama --model qwen3:14b")
        print("    (see LICENSE-DATA for why the strings are not in this repository)")
    else:
        ax = {}
        for line in local.open(encoding="utf-8"):
            r = json.loads(line)
            ax[(r["pmid"], r["sentence_sha256"])] = r["axes_local_only"]
        for x in STATED:
            vals = [j for _, a, b in opp
                    if (j := jaccard(ax.get(a["key"], {}).get(x),
                                     ax.get(b["key"], {}).get(x))) is not None]
            if not vals:
                continue
            vals.sort()
            zero = sum(1 for v in vals if v == 0.0)
            print(f"    {x:17s} n={len(vals):4d} median={vals[len(vals)//2]:.3f} "
                  f"mean={sum(vals)/len(vals):.3f} zero-overlap={zero} ({100*zero/len(vals):.1f}%)")


if __name__ == "__main__":
    main()
