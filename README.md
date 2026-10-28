# VGR Financial Release Calendar

Expected results, revenue releases and trading updates for the companies FPR tracks.
The page shows the current month and the following two. Embedded on verygoodretail.ai at
`/intelligence/earnings-calendar`.

## Which companies are covered

`build.py` publishes an event from `_calendar.json` when either:

* the company is listed in FPR's `_roster.yaml` (one folder up, not in this repo), or
* the event has already been reported (`status` is `detected`), even if the company is
  off the roster.

An event for an off-roster company that has not reported is left out with a warning.

So coverage follows the FPR roster, not the VGR 40 constituent list. In the build of
26 Oct 2026 (47 events, 40 companies, 9 Sep 2026 to 28 Jan 2027):

* ABF / Primark is included. It is not a VGR 40 constituent.
* Shein is included. In the VGR 40 it is a staged addition, not yet a member.
* Christian Dior SE and Abercrombie & Fitch are VGR 40 constituents with no events.

> **To confirm (Pau):** should the FPR roster match the VGR 40? The page text written by
> `build.py` still says "the companies in the VGR 40".

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

`data.json` and `earnings-calendar.csv` hold every event in the source, past and future.
The three-month window is applied only on the page.

### `data.json` (`events` array, plus `updated`)

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

### `earnings-calendar.csv`

Header, in this order:

    date,company,label,period,time,confidence,reported,ticker,exchange,source,brief_url,id

Same meaning as in `data.json`. The CSV has no `name` or `detail` column. Empty cells mean
no value.

## Validation (`--check`)

The build stops, and writes nothing, on: a missing or duplicate id, a non-ISO date, a
confidence other than confirmed or estimated, a confirmed date with no source URL, or a period
that does not parse to a label. A company that is off the roster and has not reported is
left out with a warning.

## Files

`index.html` (page, data inlined) · `data.json` · `earnings-calendar.csv` · `calendar.ics`
(upcoming releases only; estimated dates carry "(est.)").

`?embed=1` hides the masthead for the iframe.
