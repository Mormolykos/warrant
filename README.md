# warrant

**Does a contradiction detector know when it cannot tell?**

A measurement over ManConCorpus, the standard benchmark for contradictory claims
in biomedical literature. The result is negative in both directions, which is why
it is worth reporting.

---

## The problem

Automated contradiction detection is normally posed as a classification: given
two findings, do they conflict? But two published findings can differ because the
populations differ, the dose differs, the instrument differs, or the definition
differs — and none of those is a contradiction. Deciding conflict therefore
requires first establishing **comparability**: that the two findings were ever
about the same thing.

Benchmarks in this area supply comparability by construction. ManConCorpus groups
claims under an expert-written PICO question, and its annotators read the whole
abstracts. What the corpus *ships*, and what downstream systems consume, is the
single claim sentence.

So the question measured here is narrower than "is this a contradiction":

> Reading only the claim sentences, is there enough stated to establish that the
> two findings concern the same conditions at all?

## What was found

**1. For 77.1% of pairs, the text cannot support any verdict.**

Each claim sentence was annotated for six comparability axes, with a hard rule
that an axis the sentence does not state is recorded as NOT STATED rather than
inferred. Across 259 claims:

| axis | stated |
|---|---|
| outcome measure | 98.5% |
| intervention | 76.4% |
| population | 69.9% |
| conditions | 32.0% |
| methodology | 13.5% |
| measurement | 8.1% |

Of the 728 opposed pairs, **561 (77.1%) never state population, intervention or
outcome measure on at least one side.** Population is the biggest hole, missing
in 55.9% of pairs.

**2. A deterministic comparability check returns nothing at all.**

Requiring the axes to match before permitting a contradiction verdict yields
**0 contradictions out of 728** — 720 `different_condition`, 8
`insufficient_information`. Recall 0, precision undefined.

That 98.9% is not a discovery about the corpus. It is string equality failing,
and the sharpest example is unarguable:

```
[YS] population='patients with HCM'   outcome='adverse outcome'
[NO] population='HCM patients'        outcome='adverse prognosis'
      → "the claims differ on population, outcome_measure"
```

A softer matcher does not rescue it. Median token overlap between the stated axes
of an opposed pair is **0.000**, and accepting *any shared token whatsoever*
across all three axes recovers **4 pairs out of 728**. The vocabularies do not
overlap; the missing component is concept mapping, not normalisation.

**3. Language models do not become more cautious when the text says less.**

Two local models judged all 728 pairs with three allowed answers —
CONTRADICTION, NO_CONTRADICTION, NOT_ENOUGH_INFO — given exactly what the
deterministic layer was given. 1,456 judgements, zero unparsed.

| | qwen3:14b | qwen3:8b |
|---|---|---|
| CONTRADICTION | 40.1% | 24.2% |
| NO_CONTRADICTION | 31.3% | 56.2% |
| NOT_ENOUGH_INFO | 28.6% | 19.6% |

Splitting by whether the sentences state all three axes:

| model | measure | text states all 3 | text does not | diff | p |
|---|---|---|---|---|---|
| 14b | CONTRADICTION | 42.5% | 39.4% | +3.1 pp | 0.470 |
| 14b | NOT_ENOUGH_INFO | 26.3% | 29.2% | −2.9 pp | 0.469 |
| 8b | CONTRADICTION | 19.2% | 25.7% | −6.5 pp | 0.085 |
| 8b | NOT_ENOUGH_INFO | 20.4% | 19.4% | +0.9 pp | 0.791 |

**In both models the rate of "not enough information" does not rise when the
information is in fact absent.** The one nominally larger effect runs the wrong
way: the 8B model asserts contradiction *more* often when the text states less.

**4. The two models disagree on 39% of pairs**, at temperature 0 on identical
prompts. The single largest disagreement — 115 pairs — is the 14B answering
*"I cannot tell"* where the 8B answers *"they do not conflict"*: an absent value
reported as a negative finding.

## The shape of the result

Neither approach works, and they fail as mirror images. The deterministic layer
refuses everything. The models assert on 40% of pairs whose text cannot support
an assertion. **The bottleneck is not detecting contradiction. It is establishing
that two findings were ever about the same thing — and the sentences do not
contain what that requires.**

## Reproducing it

```bash
python fetch_corpus.py                                   # verifies SHA-256
python run_baseline.py --prompt prompts/p0_original.txt --model qwen3:14b
python audit_stats.py                                    # PASS/FAIL per number
```

Requires [Ollama](https://ollama.com) and `ollama pull qwen3:14b`. **No API key is
read unless you explicitly pass one**, and only `extract_axes.py --backend gemini`
accepts one — no key path is hardcoded anywhere in this repository.

`audit_stats.py` recomputes every headline number from the raw files and prints
PASS or FAIL against the value written in `RESULTS.md`. It re-derives the
checkable / not-checkable split independently rather than trusting the flag
stored in the result files.

**One honest caveat about reproduction.** The published axis annotations in
`data/axes.jsonl` were produced with `gemini-3.5-flash-lite`, and that is
recorded as it was actually run. Re-running `extract_axes.py --backend ollama`
uses a *different annotator* and will not reproduce those booleans exactly;
agreement between the two backends has not been measured. Everything downstream
of the axes — every baseline judgement, every rate in the tables above — is local
and reproduces exactly.

## Layout

```
fetch_corpus.py     download + SHA-256 verify ManConCorpus (not redistributed)
extract_axes.py     annotate each claim's six comparability axes
run_baseline.py     ask a local model, under a given prompt
measure.py          fill rates, verdicts, vocabulary distance, examples
audit_stats.py      independent recomputation, PASS/FAIL
prompts/            the pre-registered prompt variants
data/               PMIDs, axis booleans, verdicts — no corpus text
RESULTS.md          full write-up, failure cases, limitations
LICENSE-DATA        what is in data/ and why it is safe to publish
```

## Limitations

The full list is in [RESULTS.md](RESULTS.md). The ones that matter most:

- **There is no ground truth for true contradiction here.** Nothing says the
  models are *wrong* on any pair. The claim is about **warrant** — a verdict
  asserted where the supplied text does not state what would be needed to rule
  out a difference in setup. A model may be right from memorised knowledge of the
  underlying literature, and this design cannot tell that apart.
- **Axis annotation is by one model, checked against a re-run**, not by human
  annotators. Null-decision stability across an independent re-run of 40 claims
  was 97.5%.
- **Two models, one family, one quantisation.** Their 61% agreement is itself
  evidence a third would land elsewhere.
- **This is not a criticism of ManConCorpus.** Its annotators read whole
  abstracts and agreed with each other. This measures what survives into the
  sentence, which is the unit later systems consume.

## Attribution

ManConCorpus is by Abdulaziz Alamri and Mark Stevenson, University of Sheffield,
CC BY-NC-SA 2.0 UK, and is fetched from their page rather than redistributed
here. See [LICENSE-DATA](LICENSE-DATA).

> A. Alamri and M. Stevenson (2016). *A Corpus of Potentially Contradictory
> Research Claims from Cardiovascular Research Abstracts.* Journal of Biomedical
> Semantics 7:36. doi:10.1186/s13326-016-0083-z

The deterministic comparability layer under test is
[`slate.claims`](https://github.com/Mormolykos/slate).
