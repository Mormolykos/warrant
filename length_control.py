"""Does input length explain the refusal-vs-stated-axes correlation? No.

RESULTS.md reports a rank correlation between refusal rate and the number of
stated PICO axes, under the cautious and strict-evidence prompts. The obvious
confound is length: a pair that states more axes is a longer pair, and a small
model may simply refuse longer input. This script tests that directly and by
both of the methods it can be tested by — a partial correlation controlling for
length, and a length-matched stratification that never compares pairs of
different length to each other.

The answer is that length does correlate with axis count (+0.362), does NOT
drive refusal on the 8B model at all, and was SUPPRESSING the reported effect
rather than producing it: every positive correlation gets larger once length is
held, not smaller.

One difference from the figures published in the discussion thread. Those used a
pmid-level join between judgements and axis annotations. This script keys on
(pmid, sentence sha256) — the same key run_baseline.py itself uses — because a
PMID can carry more than one claim sentence. The reproduction block below shows
the correction is bounded at 0.005 of rho and changes no sign and no verdict.

    python length_control.py

No network, no model, no API key. Reads ./data and ./mancon.xml only.
"""
from __future__ import annotations

import collections
import hashlib
import itertools
import json
import math
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
AXES = ("population", "intervention", "outcome_measure",
        "conditions", "methodology", "measurement")
N_PERM = 20_000

# Seeded so the permutation p-values below reproduce exactly. Monte-Carlo
# standard error is printed alongside them; it is the honest width of a p
# estimated by sampling rather than enumerated.
random.seed(20260909)

# rho(refusal, n_axes) as published in the discussion thread, computed there
# with a pmid-level join. Reproduced here to within PUBLISHED_TOL.
PUBLISHED = {
    "qwen3_14b_p0_original": -0.029, "qwen3_14b_p1_caution": +0.131,
    "qwen3_14b_p2_strict_evidence": +0.087, "qwen3_14b_p3_conservative": -0.031,
    "qwen3_8b_p0_original": -0.013, "qwen3_8b_p1_caution": -0.012,
    "qwen3_8b_p2_strict_evidence": +0.081, "qwen3_8b_p3_conservative": +0.111,
}
PUBLISHED_TOL = 0.006


def load_pairs() -> list[dict]:
    """The 728 judged pairs, in the order run_baseline.py emitted them.

    Deliberately mirrors run_baseline.load_pairs() rather than importing it:
    that module imports `requests`, and this analysis must run in an
    environment that has never spoken to a model. The join key is the same.
    """
    stated = {}
    for line in (HERE / "data" / "axes.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        stated[(r["pmid"], r["sentence_sha256"])] = r["stated"]

    groups = collections.defaultdict(list)
    for rev in ET.parse(HERE / "mancon.xml").getroot().findall("REVIEW"):
        for c in rev.findall("CLAIM"):
            text = (c.text or "").strip()
            groups[c.get("QUESTION")].append({
                "pmid": c.get("PMID"), "assertion": c.get("ASSERTION"),
                "text": text,
                "key": (c.get("PMID"),
                        hashlib.sha256(text.encode()).hexdigest()[:16])})

    pairs = []
    for q, rs in groups.items():
        for a, b in itertools.combinations(rs, 2):
            if a["assertion"] == b["assertion"]:
                continue
            sa, sb = stated.get(a["key"]), stated.get(b["key"])
            if sa is None or sb is None:
                continue
            # The exact user message run_baseline.ask() sends. Length has to be
            # measured on what the model actually read, not on the claims alone
            # — the question text is in there too and it varies by review.
            msg = (f"Research question:\n{q}\n\nClaim A:\n{a['text']}"
                   f"\n\nClaim B:\n{b['text']}")
            pairs.append({
                "pmid_a": a["pmid"], "pmid_b": b["pmid"],
                "assertion_a": a["assertion"], "assertion_b": b["assertion"],
                "n_axes": sum(bool(sa[x]) for x in AXES)
                          + sum(bool(sb[x]) for x in AXES),
                "words": len(msg.split()),
                "chars": len(msg),
            })
    return pairs


def ranks(xs: list[float]) -> list[float]:
    """Midranks. Ties matter here — n_axes takes eight distinct values over 728
    pairs, so tie handling is most of the statistic."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    out = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[order[k]] = avg
        i = j + 1
    return out


def pearson(x: list[float], y: list[float]) -> float:
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return 0.0 if sxx <= 0 or syy <= 0 else sxy / math.sqrt(sxx * syy)


def spearman(x: list[float], y: list[float]) -> float:
    return pearson(ranks(x), ranks(y))


def residualise(y: list[float], z: list[float]) -> list[float]:
    """OLS residuals of y on z, both already rank vectors. Partial Spearman is
    the Pearson correlation of two such residual vectors."""
    n = len(y)
    mz, my = sum(z) / n, sum(y) / n
    szz = sum((c - mz) ** 2 for c in z)
    b = 0.0 if szz <= 0 else sum((c - mz) * (d - my)
                                 for c, d in zip(z, y)) / szz
    return [d - (my + b * (c - mz)) for c, d in zip(z, y)]


def perm_p(stat_fn, y: list[float]) -> tuple[float, float, float]:
    """Two-sided permutation p by shuffling y, with Monte-Carlo SE."""
    obs = stat_fn(y)
    shuffled = list(y)
    hits = 0
    for _ in range(N_PERM):
        random.shuffle(shuffled)
        if abs(stat_fn(shuffled)) >= abs(obs) - 1e-12:
            hits += 1
    p = (hits + 1) / (N_PERM + 1)
    return obs, p, math.sqrt(p * (1 - p) / N_PERM)


def strat_rho(refusal, axes, bins) -> float:
    """n-weighted mean of within-bin Spearman. A bin holds pairs of comparable
    length, so no comparison inside it can be explained by length."""
    num = den = 0.0
    for idx in bins:
        r = [refusal[i] for i in idx]
        a = [axes[i] for i in idx]
        if len(idx) < 8 or len(set(r)) < 2 or len(set(a)) < 2:
            continue
        num += len(idx) * spearman(r, a)
        den += len(idx)
    return num / den if den else 0.0


def main() -> int:
    pairs = load_pairs()
    runs = sorted((HERE / "data").glob("baseline_qwen3_*_p*.jsonl"))
    if not runs:
        sys.exit("no baseline_*_p*.jsonl in ./data — run run_baseline.py first")

    axes = [float(p["n_axes"]) for p in pairs]
    length = [float(p["words"]) for p in pairs]
    rank_axes, rank_len = ranks(axes), ranks(length)
    resid_axes = residualise(rank_axes, rank_len)

    order = sorted(range(len(pairs)), key=lambda i: length[i])
    cut = len(order) // 10
    bins = [order[k * cut:(k + 1) * cut if k < 9 else len(order)]
            for k in range(10)]

    print(f"pairs rebuilt from ./mancon.xml and ./data/axes.jsonl: {len(pairs)}")
    print("\nThe confound is real:")
    print(f"  spearman(n_axes, words) = {spearman(axes, length):+.3f}")
    print(f"  spearman(n_axes, chars) = "
          f"{spearman(axes, [float(p['chars']) for p in pairs]):+.3f}")
    print(f"  spearman(words,  chars) = "
          f"{spearman(length, [float(p['chars']) for p in pairs]):+.3f}")
    buckets = collections.defaultdict(list)
    for a, w in zip(axes, length):
        buckets[int(a)].append(w)
    print("\n  n_axes  n_pairs  median words")
    for k in sorted(buckets):
        v = sorted(buckets[k])
        print(f"  {k:6d} {len(v):8d} {v[len(v) // 2]:13.0f}")

    print("\nReproduction of the published rho(refusal, n_axes).")
    print("Published figures used a pmid-level join; this uses "
          "(pmid, sentence sha256).")
    print(f"PASS means the two agree to within {PUBLISHED_TOL} of rho.\n")

    rows, fails = [], []
    for f in runs:
        tag = f.stem.replace("baseline_", "")
        recs = [json.loads(l) for l in f.open(encoding="utf-8")]
        if len(recs) != len(pairs):
            sys.exit(f"{f.name}: {len(recs)} judgements for {len(pairs)} pairs")
        for r, p in zip(recs, pairs):
            if (r["pmid_a"], r["pmid_b"], r["assertion_a"], r["assertion_b"]) \
                    != (p["pmid_a"], p["pmid_b"],
                        p["assertion_a"], p["assertion_b"]):
                sys.exit(f"{f.name}: positional join disagrees with the pair "
                         f"list — the corpus or the run file has moved")

        refusal = [1.0 if r["verdict"] == "NOT_ENOUGH_INFO" else 0.0
                   for r in recs]
        rho, p_rho, se_rho = perm_p(lambda y: pearson(ranks(y), rank_axes),
                                    refusal)
        want = PUBLISHED.get(tag)
        ok = want is not None and abs(rho - want) <= PUBLISHED_TOL
        if not ok:
            fails.append(tag)
        print(f"  {'PASS' if ok else 'FAIL'}  {tag:30s} "
              f"got={rho:+.3f}  published={want:+.3f}  "
              f"delta={abs(rho - want):.3f}")
        rows.append((tag, refusal, rho, p_rho, se_rho))

    if fails:
        print(f"\nREPRODUCTION FAILED for {len(fails)}: {', '.join(fails)}")
        return 1
    print("\nREPRODUCTION PASSED — the pmid-level join cost at most "
          f"{max(abs(r[2] - PUBLISHED[r[0]]) for r in rows):.3f} of rho.")

    print(f"\nControlling for length. {N_PERM:,} permutations, MC SE in "
          "brackets.\n")
    print(f"  {'run':30} {'rho(ref,len)':>12} {'p':>8} | "
          f"{'partial':>8} {'p':>8} | {'matched':>8} {'p':>8}")
    print("  " + "-" * 92)

    for tag, refusal, rho, p_rho, se_rho in rows:
        # A. does length by itself predict refusal?
        rho_l, p_l, _ = perm_p(lambda y: pearson(ranks(y), rank_len), refusal)
        # B. partial correlation, length held
        pr, p_pr, se_pr = perm_p(
            lambda y: pearson(residualise(ranks(y), rank_len), resid_axes),
            refusal)
        # C. length-matched: shuffle refusal only WITHIN a length decile
        obs_s = strat_rho(refusal, axes, bins)
        work, hits = list(refusal), 0
        for _ in range(N_PERM):
            for b in bins:
                vals = [work[i] for i in b]
                random.shuffle(vals)
                for i, v in zip(b, vals):
                    work[i] = v
            if abs(strat_rho(work, axes, bins)) >= abs(obs_s) - 1e-12:
                hits += 1
        p_s = (hits + 1) / (N_PERM + 1)

        print(f"  {tag:30} {rho_l:+12.3f} {p_l:8.4f} | "
              f"{pr:+8.3f} {p_pr:8.4f} | {obs_s:+8.3f} {p_s:8.4f}")

    print("\n  zero-order rho(refusal, n_axes) for comparison:")
    for tag, _, rho, p_rho, se_rho in rows:
        print(f"  {tag:30} {rho:+12.3f} {p_rho:8.4f}  [SE {se_rho:.4f}]")

    print("\nlength deciles, median words: " +
          ", ".join(str(int(length[b[len(b) // 2]])) for b in bins))
    print("bin sizes: " + ", ".join(str(len(b)) for b in bins))
    print("\nWhat this does not show. Word count is whitespace tokens, not "
          "qwen's BPE;\ncharacter count gives the same picture but both are "
          "proxies. Ruling out length\nis not identifying a mechanism — that "
          "needs the manipulation, not another\ncorrelation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
