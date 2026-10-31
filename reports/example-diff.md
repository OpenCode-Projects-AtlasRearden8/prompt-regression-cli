# Prompt regression diff

- Old: example run 2026-10-31T22:28:27Z
- New: example run 2026-10-31T22:28:27Z
- Versions: release-notes@v2, support-reply@v2 -> release-notes@v2, support-reply@v2
- Cases: 3/3 -> 2/3 passing
- Rubric/exact changes: 0 fixed, 2 regressed

## **REGRESSED** angry-broken-clip / rubric:apology

pass -> FAIL

Apologizes directly using the lowercase word "sorry"

- old detail: all substrings found
- new detail: missing: 'sorry'

## **REGRESSED** angry-broken-clip / rubric:one-next-step

pass -> FAIL

Promises a replacement within 3 business days

- old detail: all substrings found
- new detail: missing: '3 business days'
