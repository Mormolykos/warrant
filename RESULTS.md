# Comparability, not contradiction: what a claim sentence fails to say

Measurement run 2026-08-26. Nothing here is tuned for a favourable number.
Where the instrument failed, the failure is reported as the result.

## What was run

- **Corpus:** ManConCorpus (Alamri & Stevenson 2016, *J Biomed Semantics* 7:36),
  fetched from the authors' Sheffield page, CC BY-NC-SA 2.0 UK.
  SHA-256 `c6925524b0117e877e64782af048d18a851bf0127361abe29587858238a180f4`.
  Not redistributed; a fetch script is shipped instead.
- **Size:** 24 systematic reviews, 24 expert-authored PICO questions,
  259 claim rows over 255 distinct sentences.
  Within-question pairs: **728 opposed** (the corpus's potentially-contradictory
  pairs), **1,047 agreeing**.
- **Given by the corpus, not inferred:** the claim triple (the shared question)
  and the polarity (the corpus's own YS/NO). Only the six comparability axes were
  extracted, one claim at a time, `gemini-3.5-flash-lite`, temperature 0,
  instructed to return null rather than infer.
- **Comparison:** `slate.claims.compare`, deterministic, no model in the path.

## 1. What a claim sentence actually states

| axis | stated | of 259 |
|---|---|---|
| outcome_measure | 255 | 98.5% |
| intervention | 198 | 76.4% |
| population | 181 | 69.9% |
| conditions | 83 | 32.0% |
| methodology | 35 | 13.5% |
| measurement | 21 | 8.1% |

## 2. The finding

**77.1% of opposed pairs (561 of 728) have at least one of population,
intervention or outcome_measure never stated on at least one side.**

Only 167 pairs (22.9%) state all three on both sides. Missing axis, opposed
pairs: population 407 (55.9%), intervention 298 (40.9%), outcome_measure 36 (4.9%).

Agreeing pairs fare better but not well: 350 of 1,047 (33.4%) state all three.

**This is not a criticism of the corpus.** Its annotators read whole abstracts
and agreed with each other. It is a measurement of what survives into the unit of
text the corpus ships and downstream systems consume — the claim sentence.

## 3. The artifact, reported as an artifact

Under deterministic axis matching, opposed pairs come back:

| verdict | n | % |
|---|---|---|
| different_condition | 720 | 98.9% |
| insufficient_information | 8 | 1.1% |
| **contradicts** | **0** | **0.0%** |

**The layer reports zero contradictions on 728 pairs. Recall is 0. Precision is
undefined.** That is the honest headline for the instrument.

The 98.9% is *not* a discovery about the corpus. It is string equality failing:
two different studies word their population differently, so the axes differ and
the pair is declared incomparable. It measures vocabulary.

## 4. Why a better matcher does not rescue it

Jaccard over content tokens, pairs where both sides state the axis:

| axis | n | median | mean | zero overlap | exact string match |
|---|---|---|---|---|---|
| population | 263 | 0.000 | 0.081 | 198 (75.3%) | 3 |
| intervention | 426 | 0.000 | 0.102 | 275 (64.6%) | 11 |
| outcome_measure | 647 | 0.000 | 0.071 | 469 (72.5%) | 6 |

Ablation, replacing equality with token overlap (all three axes must pass):

| threshold | comparable opposed pairs | of 728 |
|---|---|---|
| 1.000 | 0 | 0.0% |
| 0.500 | 0 | 0.0% |
| 0.300 | 0 | 0.0% |
| 0.100 | 4 | 0.5% |
| any shared token | 4 | 0.5% |

Ceiling is 167 (22.9%) — the pairs that state all three axes at all.
**Accepting any shared token whatsoever recovers 4 pairs.** The vocabularies do
not overlap. Normalisation is not the missing piece; a mapping between concepts is.

## 5. Failure cases

**The sharpest one.** Same population, word order reversed; synonymous outcome:

```
[YS] pop='patients with HCM'   out='adverse outcome'
[NO] pop='HCM patients'        out='adverse prognosis'
VERDICT: different_condition — "the claims differ on population, outcome_measure"
```

**A genuine candidate the layer refuses.** Identical stated population, same
outcome, opposite polarity — blocked because one side never named its intervention:

```
[YS] pop='Korean women' int=None out='preeclampsia'
[NO] pop='Korean women' int='AGT M235T and ACE intron 16 polymorphism' out='preeclampsia'
VERDICT: insufficient_information
```

**Plausibly the same intervention, different words:**

```
[YS] int='Cardiac rehabilitation'
[NO] int='exercise intervention'
VERDICT: different_condition
```

**Extraction junk.** `methodology='study'` recovered from "this study …",
4 instances found. Thin but not wrong; it inflates the methodology fill rate.

Only 4 of 728 opposed pairs have identical stated populations. **0 pairs have
nothing at all to compare on** — every claim states at least one axis.

## 6. Is the extraction stable?

Independent re-run, 40 claims, temperature 0:

| | agreement |
|---|---|
| null-decision (drives every verdict) | **234/240 = 97.5%** |
| exact string | 221/240 = 92.1% |

Per axis, null-decision: methodology and measurement 100%, population /
outcome_measure / conditions 97.5%, intervention 92.5%. Six disagreements, all
recorded. The headline in §2 is stable to roughly ±2.5% from extraction noise.

## 6b. The LLM baseline — does a model notice when the text cannot support a verdict?

Same 728 opposed pairs. The model is given exactly what the claim layer was
given: the research question and the two claim sentences. Three allowed answers:
CONTRADICTION, NO_CONTRADICTION, NOT_ENOUGH_INFO. Local models, temperature 0,
reasoning disabled, `num_predict=12`. **No API key was used.** Zero unparsed
replies in 1,456 judgements.

| | qwen3:14b | qwen3:8b |
|---|---|---|
| CONTRADICTION | 40.1% | 24.2% |
| NO_CONTRADICTION | 31.3% | 56.2% |
| NOT_ENOUGH_INFO | 28.6% | 19.6% |

**The test.** Split each model's verdicts by whether the sentences state all
three of population / intervention / outcome_measure on both sides — that is,
by whether the text contains what a verdict would need.

| model | measure | text states all 3 | text does not | diff | p |
|---|---|---|---|---|---|
| 14b | CONTRADICTION | 42.5% | 39.4% | +3.1 pp | 0.470 |
| 14b | NOT_ENOUGH_INFO | 26.3% | 29.2% | −2.9 pp | 0.469 |
| 8b | CONTRADICTION | 19.2% | 25.7% | −6.5 pp | 0.085 |
| 8b | NOT_ENOUGH_INFO | 20.4% | 19.4% | +0.9 pp | 0.791 |

**In both models, the rate of "not enough information" does not rise when the
information is in fact absent** (p = 0.469 and p = 0.791). The one nominally
larger effect runs the wrong way: the 8B model asserts contradiction *more often*
when the text states less (p = 0.085, not significant).

For comparison, on the identical 728 pairs the deterministic claim layer returns
**0 contradictions** — the opposite failure, and equally unusable.

**Two models of the same family disagree on 39% of pairs.** Agreement is
444/728 = 61.0% at temperature 0 on identical prompts. The dominant transitions
from 14b to 8b:

| 14b | 8b | n |
|---|---|---|
| NOT_ENOUGH_INFO | NO_CONTRADICTION | 115 |
| CONTRADICTION | NO_CONTRADICTION | 101 |
| CONTRADICTION | NOT_ENOUGH_INFO | 31 |

The largest single flip converts *"I cannot tell"* into *"they do not conflict"*.
That is an absent value being reported as a negative finding, which is the exact
failure the layer was built to prevent, appearing in the baseline rather than in
the instrument.

## 6c. Prompt sensitivity — the attack on §6b, and what it did to it

The obvious rebuttal to §6b is *"the model would distinguish missing information
perfectly if you simply told it to be conservative."* Four prompts were written
and fixed before the run, and all four are reported. Two models, 728 pairs each,
**5,824 judgements, zero unparsed**, all local, no API key.

- **p0** the original prompt, run again as an exact replication
- **p1** lists the conditions that must be present and requires NOT_ENOUGH_INFO otherwise
- **p2** forbids using any knowledge outside the supplied sentences
- **p3** instructs conservative adjudication, preferring NOT_ENOUGH_INFO

### Overall distribution

| run | CONTRADICTION | NO_CONTRADICTION | NOT_ENOUGH_INFO |
|---|---|---|---|
| 14b p0 | 39.6% | 32.0% | 28.4% |
| 14b p1 | 19.0% | 10.7% | 70.3% |
| 14b p2 | 23.5% | 25.3% | 51.2% |
| 14b p3 | 28.8% | 37.9% | 33.2% |
| 8b p0 | 24.2% | 56.2% | 19.6% |
| 8b p1 | 1.2% | 12.5% | 86.3% |
| 8b p2 | 16.3% | 16.5% | 67.2% |
| 8b p3 | 14.8% | 7.1% | 78.0% |

**Caution works on the rate.** Refusal rises from 28.4% to 70.3% (14B) and from
19.6% to 86.3% (8B). The rebuttal is right that far.

### Direction — and this is where it fails

| run | CONTRADICTION stated | missing | difference | p |
|---|---|---|---|---|
| 14b p0 | 40.1% | 39.4% | −0.7 pp | 0.866 |
| 14b p1 | 11.4% | 21.2% | **+9.8 pp** | 0.004 |
| 14b p2 | 17.4% | 25.3% | **+7.9 pp** | 0.033 |
| 14b p3 | 24.0% | 30.3% | +6.4 pp | 0.112 |
| 8b p0 | 19.2% | 25.7% | +6.5 pp | 0.085 |
| 8b p1 | 0.0% | 1.6% | +1.6 pp | 0.100 |
| 8b p2 | 12.0% | 17.6% | +5.7 pp | 0.082 |
| 8b p3 | 9.0% | 16.6% | **+7.6 pp** | 0.015 |

Correct behaviour is a *negative* difference. **Seven of eight runs are positive**
— contradiction asserted more often where the conditions are missing. Sign test,
one-sided, **p = 0.035**. The inversion is largest under p1, the most cautious
prompt.

So the answer to the rebuttal is: telling the model to be conservative raises
refusal by forty points and does not correct the direction at all.

### Where the added refusal landed

A reader asked the right follow-up: did the forty-point refusal jump improve
discrimination between eligible and ineligible pairs, or did it only move the
operating point? The same split applied to NOT_ENOUGH_INFO answers it. Here
correct behaviour is a *positive* difference — refuse **more** where the
conditions are missing.

| run | NOT_ENOUGH_INFO stated | missing | difference | p |
|---|---|---|---|---|
| 14b p0 | 24.6% | 29.6% | +5.0 pp | 0.205 |
| 14b p1 | 80.8% | 67.2% | **−13.6 pp** | 0.001 |
| 14b p2 | 58.7% | 49.0% | **−9.7 pp** | 0.028 |
| 14b p3 | 31.7% | 33.7% | +2.0 pp | 0.638 |
| 8b p0 | 20.4% | 19.4% | −0.9 pp | 0.791 |
| 8b p1 | 85.0% | 86.6% | +1.6 pp | 0.598 |
| 8b p2 | 69.5% | 66.5% | −3.0 pp | 0.473 |
| 8b p3 | 82.6% | 76.6% | −6.0 pp | 0.101 |

**On the 14B it is neither a uniform shift nor an improvement.** Under p1 the
well-specified pairs gain 56 points of refusal (24.6% → 80.8%) and the
underspecified pairs gain 38 (29.6% → 67.2%). The two prompts that raise refusal
most, p1 and p2, are the two that refuse **significantly more often on the pairs
that state their conditions** — the pairs with the least need of it. A threshold
shift is monotone and preserves the ranking between the two groups; this
reverses it, so the change is not one a threshold could have bought.

**What this is not.** Five of eight runs carry the wrong sign, and that is not
offered as a result — no sign test is claimed here, and it would not pass one.
Only the two 14B runs are individually significant. Above 80% refusal the rates
compress against a ceiling, which is where 8b p1 sits. The stated group is 167
pairs against 561. And *discrimination* here means separating pairs that state
their conditions from pairs that do not — **not** separating true contradictions
from false ones, for which this corpus supplies no ground truth.

### Replication and prompt fragility

The 8B model's p0 re-run is **identical** to the original §6b run on all 728
pairs; the 14B's is within 0.5 pp. The pipeline reproduces.

Agreement between runs is low. Same model, temperature 0, p0 against p1: **54.8%**
— prompt wording alone changes nearly half the verdicts. Same prompt, different
model: 61.5%.

### A mechanism, offered as hypothesis and NOT tested

When conditions are stated, a model can see that they differ, and refuses. When
they are absent there is nothing visible to differ, so two bare opposing claims
read as a clean conflict. On that account, absence of stated conditions is being
treated as absence of confounds. Testing it needs pairs whose conditions are
stated *and identical*; this corpus contains four.

## 7. Limitations

- **Single extractor, single model, single annotator.** No inter-annotator
  agreement. The null decisions are checkable against the sentences by any
  reader, which is the only external check offered here.
- **Rate limiting corrupted the first attempt.** 119 of 259 calls failed and the
  survivors were not a random sample — they were whichever landed between
  throttles, correlated with file position and therefore topic. Re-run paced at
  4.5 s/call: 0 errors. The first run's numbers were discarded, not patched.
- **`gemini-3.5-flash-lite` rejects `thinking_budget=0` outright** (400 on every
  call). Diagnosed by probe, not guessed.
- **The triple and polarity are the corpus's**, so this measures only the
  conditions layer. A system re-deriving the triple would face additional error.
- **Stopword choice affects the Jaccard numbers.** "patients" is a stopword here;
  including it would raise overlap without changing the conclusion.
- **"Potentially contradictory" is the corpus's own framing.** An opposed pair is
  not asserted by its authors to be a true contradiction.
- **No ground truth for true contradiction.** Nothing here says the models are
  *wrong* on any pair. The claim is about warrant — a verdict asserted where the
  supplied text does not state what would be needed to rule out a difference in
  setup. A model may be right by accident, or right from memorised knowledge of
  the underlying literature, and this design cannot tell those apart.
- **Two models, one family, one quantisation.** qwen3 14B and 8B at Q4_K_M. The
  61% agreement between them is itself evidence that a third model would land
  somewhere else again.
- **Prompt sensitivity IS now measured, and it overturned the original wording.**
  Four pre-registered prompts × two models × 728 pairs = 5,824 judgements, run
  2026-08-27. The original write-up of §6b said the models were *insensitive* to
  whether the text stated its conditions (p = 0.469, p = 0.791). That was a
  property of one prompt. Under cautious prompting the effect is not absent, it
  is **inverted and significant**: contradiction is asserted more often when the
  conditions are missing, in seven of eight runs (sign test p = 0.035), largest
  under the most cautious prompt (+9.8 pp, p = 0.004). Caution moves the overall
  refusal rate from 28.4% to 70.3% (14B) and 19.6% to 86.3% (8B) without changing
  the direction. **The §6b tables below are left exactly as first written and are
  correct for the prompt they describe; the conclusion drawn from them was too
  weak and is superseded by §6c.**
- **Sixteen significance tests were run across the matrix.** Three reach p < 0.05
  individually; at that count some would be expected by chance. The direction
  claim rests on the sign test across runs, not on any single run.
- **The pooled estimate is deliberately not quoted as a result.** Pooling all
  eight runs gives +5.6 pp at z = 4.4, but the runs share the same 728 pairs and
  are not independent, so that interval is too narrow to mean what it appears to.
- **"Checkable" is defined by my extractor**, so §6b inherits every limitation of
  §1–§2, including the 97.5% null-decision stability rather than 100%.
- **The 95% CI on the 14B contradiction difference is [−5.4, +11.6] pp.** This
  rules out a large effect, not a small one. A real difference of a few points
  would not have been detected at this sample size.

## 8. What this licenses, and what it does not

**Licensed:** on the field's own benchmark, a contradiction detector reading the
claim sentence cannot verify comparability for 77.1% of the pairs it is asked to
judge, and surface matching recovers 0.5% of the rest. Conditions-aware
comparison, implemented conservatively, returns nothing at all.

**Not licensed:** that the corpus is mislabelled. That LLM contradiction
detectors are wrong on these pairs — that was not measured here, and it needs a
baseline run. That refusal-by-default is a good design; on this evidence it is
unusable without concept mapping.

**The open question this hands to whoever reads it:** the bottleneck is not
detecting contradiction. It is establishing that two findings were ever about the
same thing — and the text does not contain what that requires.
