# -*- coding: utf-8 -*-
"""Naive term-by-term accumulation (ssum): every float sum that reaches data/processed/*.json
or the rendered page goes through it.

Why not the builtin sum(): since Python 3.12 the builtin sum() uses Neumaier compensated
summation for floats (gh-100425), so the same data differs in the last bit between 3.10 and
3.12.  Real case: the four per-horizon rank AUCs of lambda=6400 in lambda_audit.json are
0.753 / 0.644 / 0.617 / 0.62, and
  3.10.11: sum(...) = 2.6340000000000003 -> /4 = 0.6585000000000001 -> page prints 0.659
  3.12.14: sum(...) = 2.634              -> /4 = 0.6585            -> page prints 0.658
so the cloud build (3.12) and the local build (3.10) differed by exactly one character and the
documented 0.659 no longer matched.  An explicit += is plain IEEE-754 double addition: bit-for-bit
reproducible on every interpreter version.  Integer counts (sum(1 for ...)) and numpy .sum() are
exact and unaffected - keep using those.
"""


def ssum(xs):
    """Naive term-by-term sum (float() first, so ints/strings cannot silently concatenate)."""
    t = 0.0
    for x in xs:
        t += float(x)
    return t
