"""Ask a local model whether each opposed pair contradicts, under a given prompt.

    python run_baseline.py --prompt prompts/p0_original.txt --model qwen3:14b

The model is given exactly what the deterministic layer was given: the research
question and the two claim sentences. Nothing else. Allowing it the full abstract
would be a different and easier task than the one the corpus ships.

Local models only. Nothing here reads an API key, and that is deliberate: a
hosted endpoint changes underneath a result, and a result nobody can re-run is
not a result.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

HERE = Path(__file__).parent
OLLAMA = "http://localhost:11434/api/chat"
STATED = ("population", "intervention", "outcome_measure")


def load_pairs():
    """Opposed pairs, with `checkable` taken from the published axis booleans."""
    corpus = HERE / "mancon.xml"
    if not corpus.exists():
        sys.exit("mancon.xml missing — run `python fetch_corpus.py` first")

    # Keyed by (pmid, sentence hash), NOT by pmid. A PMID can appear with more
    # than one claim sentence, and keying on pmid alone silently overwrites one
    # with the other — which moves the checkable count from 167 to 169 and
    # quietly breaks comparability with every earlier run.
    stated = {}
    for line in (HERE / "data" / "axes.jsonl").open(encoding="utf-8"):
        r = json.loads(line)
        stated[(r["pmid"], r["sentence_sha256"])] = r["stated"]

    groups = collections.defaultdict(list)
    for rev in ET.parse(corpus).getroot().findall("REVIEW"):
        for c in rev.findall("CLAIM"):
            text = (c.text or "").strip()
            groups[c.get("QUESTION")].append({
                "pmid": c.get("PMID"), "assertion": c.get("ASSERTION"),
                "text": text,
                "key": (c.get("PMID"),
                        hashlib.sha256(text.encode()).hexdigest()[:16])})

    pairs, unmatched = [], 0
    for q, rs in groups.items():
        for a, b in itertools.combinations(rs, 2):
            if a["assertion"] == b["assertion"]:
                continue
            sa, sb = stated.get(a["key"]), stated.get(b["key"])
            if sa is None or sb is None:
                unmatched += 1
                continue
            pairs.append((q, a, b, all(sa[x] and sb[x] for x in STATED)))
    if unmatched:
        print(f"WARNING: {unmatched} pairs had no published axes and were skipped")
    return pairs


def ask(model: str, system: str, question: str, a: str, b: str) -> tuple[str, str]:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content":
                f"Research question:\n{question}\n\nClaim A:\n{a}\n\nClaim B:\n{b}"},
        ],
        "stream": False,
        "think": False,     # qwen3 reasons by default; the answer is one word
        "options": {"temperature": 0.0, "num_predict": 12},
    }
    r = requests.post(OLLAMA, json=body, timeout=180)
    r.raise_for_status()
    raw = (r.json().get("message", {}).get("content") or "").strip()
    up = raw.upper()
    # Longest first, so NO_CONTRADICTION is never matched as CONTRADICTION.
    for label in ("NO_CONTRADICTION", "NOT_ENOUGH_INFO", "CONTRADICTION"):
        if label in up:
            return label, raw
    m = re.search(r"[A-Z_]{5,}", up)
    return "UNPARSED", (m.group(0) if m else raw)[:80]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True, type=Path)
    ap.add_argument("--model", default="qwen3:14b")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    system = args.prompt.read_text(encoding="utf-8").strip()
    tag = args.prompt.stem
    out = args.out or HERE / "data" / f"baseline_{args.model.replace(':', '_')}_{tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    pairs = load_pairs()
    done = set()
    if out.exists():
        for line in out.open(encoding="utf-8"):
            try:
                d = json.loads(line)
                done.add((d["pmid_a"], d["pmid_b"], d["question_sha"]))
            except Exception:                            # noqa: BLE001, S112
                continue

    print(f"model={args.model}  prompt={tag}  pairs={len(pairs)}  already={len(done)}",
          flush=True)
    t0, n = time.time(), 0
    with out.open("a", encoding="utf-8") as fh:
        for q, a, b, checkable in pairs:
            qsha = hashlib.sha256(q.encode()).hexdigest()[:16]
            if (a["pmid"], b["pmid"], qsha) in done:
                continue
            try:
                verdict, raw = ask(args.model, system, q, a["text"], b["text"])
            except Exception as e:                       # noqa: BLE001
                print(f"  ERROR {type(e).__name__}: {str(e)[:100]}", flush=True)
                continue
            fh.write(json.dumps({
                "question_sha": qsha, "pmid_a": a["pmid"], "pmid_b": b["pmid"],
                "assertion_a": a["assertion"], "assertion_b": b["assertion"],
                "verdict": verdict, "raw": raw[:80], "checkable": checkable,
                "model": args.model, "prompt": tag,
            }, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            if n % 100 == 0:
                rate = n / (time.time() - t0)
                print(f"  {n} done  {rate:.2f}/s  ~{(len(pairs)-len(done)-n)/rate/60:.1f} min left",
                      flush=True)
    print(f"\nwrote {n} to {out.name} in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
