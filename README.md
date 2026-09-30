# VGR Financial Release Calendar

Expected results, revenue releases and trading updates for the companies in the VGR 40:
the current month and the following two. Embedded on verygoodretail.ai at
`/intelligence/earnings-calendar`.

## How it updates

`_calendar.json` (one folder up, written by `_fpr.py`) is the only source. After every
calendar write (`cal-upsert`, `cal-push`, `detect`) and after a distribution leg is marked,
`_fpr.py` runs `publish.py`, which rebuilds the page and pushes it only if the output changed.
GitHub Pages serves the new page; the site embeds it in an iframe, so no site publish is needed.

The three-month window is computed in the browser from today's date, so the page rolls to
the next month on the 1st without a rebuild.

    python build.py            # validate and build
    python build.py --check    # validate only
    python build.py --offline  # do not fetch the sitemap; keep existing brief links
    python publish.py          # build, commit if changed, push

## What is published

| field | meaning |
|---|---|
| `id` | `<company>-<period>` slug, equal to the brief slug on the site |
| `company`, `name` | roster name and the short display name |
| `ticker`, `exchange` | as in the roster |
| `period` | the period as the company states it |
| `label`, `detail` | short label derived from `period` (`H1-26`, `FY26`, `9M-26`) and the rest of the period text |
| `date` | ISO date |
| `time` | as stated by the company; absent when not stated |
| `confidence` | `confirmed` (the company published the day) or `estimated` |
| `reported` | true once FPR has detected the release |
| `source` | company or exchange URL, for confirmed dates only |
| `brief_url` | the VGR analysis, only once its slug is in the live sitemap |

Internal fields (`notes`, `eventId`, `checked`, `detectedAt`, `folder`, `tier`, `status`)
are not published.

## Validation (`--check`)

The build stops, and writes nothing, on: a missing or duplicate id, a non-ISO date, a
confidence other than confirmed or estimated, a confirmed date with no source URL, or a period
that does not parse to a label. A company that is off the roster and has not reported is
left out with a warning.

## Files

`index.html` (page, data inlined) · `data.json` · `earnings-calendar.csv` · `calendar.ics`
(upcoming releases only; estimated dates carry "(est.)").

`?embed=1` hides the masthead for the iframe.
