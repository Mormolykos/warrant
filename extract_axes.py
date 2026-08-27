"""Annotate each claim sentence with the six comparability axes.

    python extract_axes.py --backend ollama --model qwen3:14b
    python extract_axes.py --backend gemini --model gemini-3.5-flash-lite \
                           --env-file /path/to/.env

WHICH BACKEND PRODUCED THE PUBLISHED DATA
-----------------------------------------
`data/axes.jsonl` in this repository was produced with **gemini-3.5-flash-lite**
at temperature 0 on 2026-08-26. It is recorded that way because the result should
be reproducible as it was actually run, not as it would be nicer to have run it.

A local re-run with `--backend ollama` will NOT reproduce those axes exactly. It
is a different annotator. Cross-annotator agreement between the two backends has
NOT been measured, and until it is, a local re-run is a replication attempt
rather than a reproduction. Everything downstream of the axes — every baseline,
every rate in RESULTS.md — is local and reproduces exactly.

The rule the annotator is given is the whole design: an axis the sentence does
not state is NOT STATED, never inferred. Nulls are the measurement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
AXES = ["population", "intervention", "outcome_measure",
        "conditions", "methodology", "measurement"]

SYSTEM = """You extract the stated conditions of a single scientific claim sentence.

You will be given ONE sentence from a biomedical abstract. Return ONLY a JSON object with exactly these six keys:

  population         who or what was studied (e.g. "elderly men with type 2 diabetes")
  intervention       what was done or given, INCLUDING dose or amount if stated (e.g. "4 g/day omega-3")
  outcome_measure    what was measured as the result (e.g. "incidence of heart failure")
  conditions         setting, duration, comparator or study context (e.g. "12 weeks, vs placebo")
  methodology        study design if stated (e.g. "randomised double-blind trial", "meta-analysis")
  measurement        the instrument, scale or units of the outcome (e.g. "ambulatory systolic BP in mmHg")

ABSOLUTE RULE: if the sentence does not state something, the value is null.

Do NOT infer, complete, or supply anything from your own knowledge of the topic. If the sentence says "in patients" with no further detail, population is "patients" — not the disease you assume from context. If no dose is given, do not add one. A null is always better than a guess; nulls are the measurement being made here.

Copy the wording from the sentence where you can. Return strictly JSON, no prose, no code fence."""

EMPTY = {"null", "none", "n/a", "not stated", "not specified", "unknown", ""}


def clean(data: dict) -> dict:
    out = {}
    for a in AXES:
        v = data.get(a)
        out[a] = v.strip() if (isinstance(v, str) and v.strip()
                               and v.strip().lower() not in EMPTY) else None
    return out


def ollama_extract(model: str, sentence: str) -> dict:
    import requests
    r = requests.post("http://localhost:11434/api/chat", json={
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": f"Sentence:\n{sentence}"}],
        "stream": False, "think": False, "format": "json",
        "options": {"temperature": 0.0, "num_predict": 700},
    }, timeout=300)
    r.raise_for_status()
    return clean(json.loads(r.json()["message"]["content"]))


def gemini_extract(client, model: str, sentence: str) -> dict:
    from google.genai import types
    resp = client.models.generate_content(
        model=model, contents=f"Sentence:\n{sentence}",
        # No thinking_config: gemini-3.5-flash-lite rejects the parameter itself
        # with a 400, not merely the value. Probed 2026-08-26.
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM, temperature=0.0,
            max_output_tokens=700, response_mime_type="application/json"))
    return clean(json.loads((resp.text or "").strip()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=("ollama", "gemini"), default="ollama")
    ap.add_argument("--model", default="qwen3:14b")
    ap.add_argument("--env-file", type=Path, default=None,
                    help="for --backend gemini: a .env holding GEMINI_API_KEY. "
                         "No path is hardcoded; nothing is read unless you pass this.")
    ap.add_argument("--out", type=Path, default=HERE / "data" / "axes_local.jsonl")
    ap.add_argument("--interval", type=float, default=0.0,
                    help="seconds between calls; use ~4.5 for a free API tier")
    args = ap.parse_args()

    corpus = HERE / "mancon.xml"
    if not corpus.exists():
        sys.exit("mancon.xml missing — run `python fetch_corpus.py` first")

    seen, claims = set(), []
    qids: dict[str, str] = {}
    for rev in ET.parse(corpus).getroot().findall("REVIEW"):
        for c in rev.findall("CLAIM"):
            text = (c.text or "").strip()
            qids.setdefault(c.get("QUESTION"), "Q%02d" % (len(qids) + 1))
            k = (c.get("PMID"), hashlib.sha256(text.encode()).hexdigest()[:16])
            if k in seen:
                continue                      # annotate each SENTENCE once
            seen.add(k)
            claims.append({"pmid": c.get("PMID"), "sha": k[1], "text": text,
                           "question_id": qids[c.get("QUESTION")],
                           "assertion": c.get("ASSERTION"), "type": c.get("TYPE")})

    gclient = None
    if args.backend == "gemini":
        if not args.env_file:
            sys.exit("--backend gemini requires --env-file; no key path is assumed")
        from dotenv import load_dotenv
        from google import genai
        load_dotenv(args.env_file)
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            sys.exit(f"no GEMINI_API_KEY in {args.env_file}")
        gclient = genai.Client(api_key=key)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if args.out.exists():
        for line in args.out.open(encoding="utf-8"):
            try:
                d = json.loads(line)
                done.add((d["pmid"], d["sentence_sha256"]))
            except Exception:                              # noqa: BLE001, S112
                continue

    print(f"backend={args.backend} model={args.model} sentences={len(claims)} "
          f"already={len(done)}", flush=True)
    t0, n, failed = time.time(), 0, 0
    last = 0.0
    with args.out.open("a", encoding="utf-8") as fh:
        for c in claims:
            if (c["pmid"], c["sha"]) in done:
                continue
            if args.interval:
                gap = args.interval - (time.monotonic() - last)
                if gap > 0:
                    time.sleep(gap)
                last = time.monotonic()
            try:
                axes = (ollama_extract(args.model, c["text"]) if args.backend == "ollama"
                        else gemini_extract(gclient, args.model, c["text"]))
            except Exception as e:                         # noqa: BLE001
                failed += 1
                print(f"  FAILED {c['pmid']}: {type(e).__name__}: {str(e)[:110]}",
                      flush=True)
                continue
            fh.write(json.dumps({
                "pmid": c["pmid"], "question_id": c["question_id"],
                "assertion": c["assertion"], "type": c["type"],
                "sentence_sha256": c["sha"],
                "stated": {a: axes[a] is not None for a in AXES},
                "axis_word_count": {a: (len(axes[a].split()) if axes[a] else 0)
                                    for a in AXES},
                # The extracted strings reproduce a median 59% of their source
                # sentence, so they are kept locally and never published.
                # See LICENSE-DATA.
                "axes_local_only": axes,
            }, ensure_ascii=False) + "\n")
            fh.flush()
            n += 1
            if n % 25 == 0:
                print(f"  {n} done  {n/(time.time()-t0):.2f}/s", flush=True)
    print(f"\nwrote {n}, failed {failed}, in {(time.time()-t0)/60:.1f} min -> {args.out.name}")


if __name__ == "__main__":
    main()
