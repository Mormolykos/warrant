"""Fetch ManConCorpus from the authors' page and verify it byte-for-byte.

The corpus is NOT redistributed in this repository. It is CC BY-NC-SA 2.0 UK and
belongs to its authors:

    A. Alamri and M. Stevenson (2016). A Corpus of Potentially Contradictory
    Research Claims from Cardiovascular Research Abstracts.
    Journal of Biomedical Semantics 7:36. doi:10.1186/s13326-016-0083-z

Run this once before anything else:

    python fetch_corpus.py

It writes ./mancon.xml and refuses to proceed if the hash does not match the
version these results were computed against.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from urllib.request import urlopen

URL = ("https://staffwww.dcs.shef.ac.uk/people/M.Stevenson/resources/"
       "bio_contradictions/corpus.xml")
SHA256 = "c6925524b0117e877e64782af048d18a851bf0127361abe29587858238a180f4"
OUT = Path(__file__).parent / "mancon.xml"


def main() -> int:
    if OUT.exists():
        got = hashlib.sha256(OUT.read_bytes()).hexdigest()
        if got == SHA256:
            print(f"{OUT.name} already present and verified.")
            return 0
        print(f"{OUT.name} exists but hashes {got[:16]}…, expected {SHA256[:16]}…")
        print("Refusing to overwrite. Move it aside and re-run.")
        return 2

    print(f"fetching {URL}")
    try:
        data = urlopen(URL, timeout=60).read()          # noqa: S310
    except Exception as e:                               # noqa: BLE001
        print(f"fetch failed: {type(e).__name__}: {e}")
        print("\nThe corpus is hosted on a university staff page. If it has moved,")
        print("the paper's DOI above is the authoritative reference.")
        return 1

    got = hashlib.sha256(data).hexdigest()
    if got != SHA256:
        print(f"HASH MISMATCH\n  expected {SHA256}\n  got      {got}")
        print("\nThe corpus has changed since these results were computed.")
        print("Nothing written. Results in RESULTS.md describe the expected hash.")
        return 3

    OUT.write_bytes(data)
    print(f"wrote {OUT.name}  ({len(data)} bytes)  sha256 verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
