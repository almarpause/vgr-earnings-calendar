#!/usr/bin/env python3
"""
VGR — Financial Release Calendar
Builds the public calendar page from FPR's _calendar.json, in the VGR house style
(Economist Word Style, Navy Edition) used by vgr-fashion50 and vgr-historic-share-prices.

    python build.py              # validate, then write data.json, index.html, calendar.ics, csv
    python build.py --check      # validate only, write nothing
    python build.py --offline    # do not fetch the site sitemap; keep the brief links already built

Reads   ../_calendar.json  (source of truth, written by _fpr.py)
        ../_roster.yaml    (company list; a row that is off-roster and not yet reported is left out)
        https://verygoodretail.ai/sitemap.xml  (a brief is linked only if its slug is live there)

Only whitelisted fields are published. notes, eventId, checked, detectedAt, folder and tier
never leave this folder.

Stdlib only.
"""
import csv, datetime, io, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CAL = os.path.join(ROOT, "_calendar.json")
ROSTER = os.path.join(ROOT, "_roster.yaml")
OUT_DATA = os.path.join(HERE, "data.json")
OUT_HTML = os.path.join(HERE, "index.html")
OUT_ICS = os.path.join(HERE, "calendar.ics")
OUT_CSV = os.path.join(HERE, "earnings-calendar.csv")

SITE = "https://verygoodretail.ai"
SITEMAP = SITE + "/sitemap.xml"
BRIEF_PREFIX = SITE + "/intelligence/archive/"
PAGE_URL = SITE + "/intelligence/earnings-calendar"

# Short display names, matching the names the site already uses for these companies.
# Anything not listed is shown as the roster name in capitals.
SHORT = {
    "ABF / Primark": "ABF / PRIMARK",
    "Next plc": "NEXT",
    "LPP SA": "LPP",
    "JD Sports Fashion": "JD SPORTS",
    "Titan Company": "TITAN",
    "Prada Group": "PRADA",
    "Swatch Group": "SWATCH",
    "Gildan Activewear": "GILDAN",
    "Abercrombie and Fitch": "ABERCROMBIE & FITCH",
}

PERIOD_RE = re.compile(r"^(Q[1-4]|H[12]|9M|FY)\s*(?:FY)?\s*(\d{4})(?:/(\d{2}))?\s*(.*)$")


# ---------------------------------------------------------------- helpers
def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def period_label(period):
    """'H1 FY2026' -> ('H1-26', ''), 'FY2026 annual results' -> ('FY26', 'annual results'),
    'H1 FY2026/27' -> ('H1-26/27', ''). Returns None when the period does not parse."""
    m = PERIOD_RE.match(period.strip())
    if not m:
        return None
    kind, year, year2, rest = m.groups()
    yy = year[2:] + ("/" + year2 if year2 else "")
    if kind == "FY":
        return "FY" + yy, rest.strip()
    # a period written as 'FY2026 ...' with no Q/H prefix is handled above; here kind is Q/H/9M
    return f"{kind}-{yy}", rest.strip()


def roster_companies():
    names = set()
    with open(ROSTER, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^  - company:\s*(.+?)\s*$", line)
            if m:
                names.add(m.group(1).strip().strip('"').strip("'"))
    return names


def live_brief_slugs():
    req = urllib.request.Request(SITEMAP, headers={"User-Agent": "vgr-earnings-calendar-build"})
    with urllib.request.urlopen(req, timeout=20) as r:
        xml = r.read().decode("utf-8", "replace")
    return set(re.findall(re.escape(BRIEF_PREFIX) + r"([a-z0-9\-]+)</loc>", xml))


def previous_briefs():
    if not os.path.exists(OUT_DATA):
        return {}
    try:
        with open(OUT_DATA, encoding="utf-8") as f:
            return {e["id"]: e["brief_url"] for e in json.load(f)["events"] if e.get("brief_url")}
    except Exception:
        return {}


# ---------------------------------------------------------------- build the public rows
def public_rows(offline=False):
    with open(CAL, encoding="utf-8") as f:
        cal = json.load(f)
    roster = roster_companies()
    errs, warns, rows, seen = [], [], [], set()
    if len(roster) < 30:
        errs.append(f"roster read only {len(roster)} companies from _roster.yaml")

    prev = previous_briefs()
    live = None
    if not offline:
        try:
            live = live_brief_slugs()
        except Exception as ex:
            warns.append(f"sitemap not reachable ({ex.__class__.__name__}); brief links kept from the last build")

    for e in cal.get("events", []):
        eid = e.get("id") or ""
        where = eid or e.get("company", "?")
        reported = e.get("status") == "detected"
        if not eid:
            errs.append(f"{where}: no id")
            continue
        if eid in seen:
            errs.append(f"{eid}: duplicate id")
        seen.add(eid)
        try:
            datetime.date.fromisoformat(e.get("date", ""))
        except ValueError:
            errs.append(f"{eid}: date {e.get('date')!r} is not ISO")
        conf = e.get("confidence")
        if conf not in ("confirmed", "estimated"):
            errs.append(f"{eid}: confidence {conf!r}")
        src = (e.get("source") or "").strip()
        if conf == "confirmed" and not re.match(r"^https?://", src):
            errs.append(f"{eid}: confirmed date without a source URL")
        lab = period_label(e.get("period", ""))
        if not lab:
            errs.append(f"{eid}: period {e.get('period')!r} does not parse to a label")
            continue
        if e.get("company") not in roster and not reported:
            warns.append(f"{eid}: {e.get('company')} is off-roster and not reported; left out")
            continue

        if live is not None:
            brief = BRIEF_PREFIX + eid if (reported and eid in live) else None
        else:
            brief = prev.get(eid)
        t = (e.get("time") or "").strip()
        rows.append({
            "id": eid,
            "company": e["company"],
            "name": SHORT.get(e["company"], e["company"].upper()),
            "ticker": e.get("ticker"),
            "exchange": e.get("exchange"),
            "period": e["period"],
            "label": lab[0],
            "detail": lab[1],
            "date": e["date"],
            "time": None if t in ("", "unknown") else t,
            "confidence": conf,
            "reported": reported,
            # the source is published only for a date the company has confirmed
            "source": src if conf == "confirmed" else None,
            "brief_url": brief,
        })
    rows.sort(key=lambda r: (r["date"], r["name"]))
    return {"updated": cal.get("updated"), "events": rows}, errs, warns


# ---------------------------------------------------------------- ics / csv
def ics_escape(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_ics(data):
    stamp = re.sub(r"[-:]", "", (data["updated"] or "1970-01-01T00:00:00")[:19]) + "Z"
    L = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Very Good Retail//Financial Release Calendar//EN",
         "CALSCALE:GREGORIAN", "X-WR-CALNAME:VGR Financial Release Calendar"]
    for r in data["events"]:
        if r["reported"]:
            continue
        d = datetime.date.fromisoformat(r["date"])
        est = " (est.)" if r["confidence"] == "estimated" else ""
        desc = r["company"] + ", " + r["period"] + ("" if not r["time"] else ", " + r["time"]) + \
            (". Estimated date, not yet confirmed by the company." if est else ". Date confirmed by the company.")
        L += ["BEGIN:VEVENT", f"UID:{r['id']}@vgr-earnings-calendar", f"DTSTAMP:{stamp}",
              f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
              f"DTEND;VALUE=DATE:{d + datetime.timedelta(days=1):%Y%m%d}",
              "SUMMARY:" + ics_escape(f"{r['name']} {r['label']}{est}"),
              "DESCRIPTION:" + ics_escape(desc),
              "URL:" + (r["source"] or PAGE_URL), "END:VEVENT"]
    L.append("END:VCALENDAR")
    return "\r\n".join(L) + "\r\n"


def build_csv(data):
    cols = ["date", "company", "label", "period", "time", "confidence", "reported", "ticker",
            "exchange", "source", "brief_url", "id"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for r in data["events"]:
        w.writerow(["" if r[c] is None else r[c] for c in cols])
    return buf.getvalue()


# ---------------------------------------------------------------- page
CSS = """
:root { --paper:#F1ECE3; --card:#fff; --panel:#E8E3D9; --ink:#141414;
  --muted:#8a8272; --sub:#6f6a5f; --line:#E0DACE; --rule:#1a1a1a;
  --red:#C0110A; --navy:#10294B;
  --serif:Georgia,"Times New Roman",serif; --sans:Arial,Helvetica,sans-serif; }
* { box-sizing:border-box; }
body { margin:0; background:var(--paper); color:var(--ink); font-family:var(--sans);
  font-size:14px; line-height:1.5; -webkit-font-smoothing:antialiased; }
.topbar { height:3px; background:var(--red); }
.wrap { max-width:1080px; margin:0 auto; padding:22px 22px 48px; }
.hd { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; }
.figbox { background:var(--red); color:#fff; font-weight:700; font-size:10px; letter-spacing:.09em;
  text-transform:uppercase; padding:5px 10px; display:inline-block; }
.vgr { font-weight:800; font-size:30px; letter-spacing:-.02em; }
h1 { font-family:var(--serif); font-weight:700; font-size:38px; line-height:1.05;
  letter-spacing:-.01em; margin:14px 0 8px; }
.lede { font-family:var(--serif); font-size:17px; color:var(--sub); max-width:74ch; margin:0; }
.meta { font-size:11.5px; color:var(--muted); margin-top:10px; padding-top:10px;
  border-top:1px solid var(--line); }
.lgnd { display:flex; flex-wrap:wrap; gap:8px 18px; align-items:center; margin-top:14px;
  font-size:11.5px; color:var(--sub); }
.lgnd span.k { display:inline-flex; align-items:center; gap:7px; }
.card { background:var(--card); border:1px solid var(--line); padding:20px 22px; margin-top:16px; }
.chead { font-family:var(--serif); font-weight:700; font-size:22px; letter-spacing:-.01em; }
.cdek { font-size:12.5px; color:var(--sub); margin-top:2px; }
table.grid { border-collapse:collapse; width:100%; table-layout:fixed; margin-top:14px; }
table.grid th { text-align:left; font-size:10px; font-weight:700; text-transform:uppercase;
  letter-spacing:.07em; color:var(--muted); border-bottom:1px solid var(--rule); padding:6px 7px; }
table.grid td { vertical-align:top; height:84px; padding:5px 6px 7px; border:1px solid var(--line); }
table.grid td.out { background:var(--paper); border-color:var(--line); }
table.grid td.past .dn { color:#c2baa9; }
table.grid td.today { box-shadow:inset 0 0 0 2px var(--red); }
.dn { font-family:var(--serif); font-weight:700; font-size:13px; color:var(--sub);
  font-variant-numeric:tabular-nums; }
.dn small { font-family:var(--sans); font-weight:700; font-size:9px; letter-spacing:.08em;
  color:var(--red); margin-left:5px; text-transform:uppercase; }
.chip { display:block; margin-top:5px; padding:4px 6px 4px 7px; border-left:3px solid var(--navy);
  background:#F5F2EC; color:var(--ink); text-decoration:none; font-size:11px; font-weight:700;
  line-height:1.25; letter-spacing:.01em; overflow-wrap:break-word; }
.chip b { white-space:nowrap; font-weight:700; }
.chip i { display:block; font-style:normal; font-weight:400; font-size:10px; color:var(--sub); }
.chip.est { border-left:3px dashed var(--muted); background:transparent; color:var(--sub);
  outline:1px dashed var(--line); outline-offset:-1px; }
.chip.rep { background:var(--navy); color:#fff; border-left-color:var(--navy); }
.chip.rep i { color:#c9d3e2; }
a.chip:hover { opacity:.75; }
.lgnd .chip { display:inline-block; margin:0; padding:2px 6px 2px 7px; font-size:10px; }
table.list { border-collapse:collapse; width:100%; font-size:12.5px; margin-top:16px; }
table.list th { text-align:left; font-size:10px; font-weight:700; text-transform:uppercase;
  letter-spacing:.07em; color:var(--muted); border-bottom:1px solid var(--rule);
  padding:6px 7px; white-space:nowrap; }
table.list td { padding:6px 7px; border-bottom:1px solid var(--line); vertical-align:top; }
table.list td.d { white-space:nowrap; font-variant-numeric:tabular-nums; }
table.list td.r { font-weight:700; white-space:nowrap; }
table.list tr.past td { color:var(--muted); }
table.list a { color:var(--navy); }
.tag { font-size:10px; font-weight:700; letter-spacing:.07em; text-transform:uppercase; white-space:nowrap; }
.tag.c { color:var(--navy); } .tag.e { color:var(--muted); } .tag.r { color:var(--red); }
.none { font-size:12.5px; color:var(--muted); margin-top:14px; }
.src { font-size:11px; color:var(--muted); margin-top:16px; padding-top:12px;
  border-top:1px solid var(--line); }
.src p { margin:0 0 6px; max-width:96ch; }
.src b { color:var(--ink); }
.src a { color:var(--navy); }
body.embed .hd, body.embed h1, body.embed .topbar { display:none; }
body.embed .wrap { padding-top:18px; }
@media (max-width:760px) {
  table.grid { display:none; }
  h1 { font-size:29px; }
  .card { padding:16px 14px; }
  table.list th.x, table.list td.x { display:none; }
}
"""

JS = r"""
(function(){
var D=JSON.parse(document.getElementById('data').textContent);
var MONTHS=['January','February','March','April','May','June','July','August','September',
  'October','November','December'];
var DOW=['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  .replace(/"/g,'&quot;');}
function el(id){return document.getElementById(id);}
function pad(n){return (n<10?'0':'')+n;}
function iso(y,m,d){return y+'-'+pad(m+1)+'-'+pad(d);}
if(/[?&]embed=1/.test(location.search)) document.body.className='embed';

// "today" on the Madrid clock, where the calendar is kept
var today;
try{ today=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Madrid',year:'numeric',
  month:'2-digit',day:'2-digit'}).format(new Date()); }
catch(e){ var n=new Date(); today=iso(n.getFullYear(),n.getMonth(),n.getDate()); }
var ty=+today.slice(0,4), tm=+today.slice(5,7)-1;

var byDate={};
D.events.forEach(function(e){(byDate[e.date]=byDate[e.date]||[]).push(e);});

function state(e){return e.reported?'rep':(e.confidence==='estimated'?'est':'');}
function tip(e){
  var s=e.company+', '+e.period;
  if(e.time) s+=', '+e.time;
  s+=e.reported?'. Reported.':(e.confidence==='estimated'
    ?'. Estimated date, not yet confirmed by the company.':'. Date confirmed by the company.');
  if(e.brief_url) s+=' Open the VGR analysis.';
  return s;
}
function chip(e){
  var inner=esc(e.name)+' <b>'+esc(e.label)+'</b>'+(e.detail?'<i>'+esc(e.detail)+'</i>':'')+
    (!e.reported&&e.confidence==='estimated'?'<i>est.</i>':'');
  var cls='chip '+state(e), t=' title="'+esc(tip(e))+'"';
  var href=e.brief_url||(!e.reported?e.source:null);
  return href?'<a class="'+cls+'" target="_blank" rel="noopener" href="'+esc(href)+'"'+t+'>'+inner+'</a>'
             :'<span class="'+cls+'"'+t+'>'+inner+'</span>';
}
function tag(e){
  if(e.reported) return '<span class="tag r">Reported</span>';
  return e.confidence==='estimated'?'<span class="tag e">Estimated</span>'
                                   :'<span class="tag c">Confirmed</span>';
}
function link(e){
  if(e.brief_url) return '<a target="_blank" rel="noopener" href="'+esc(e.brief_url)+'">VGR analysis</a>';
  if(e.source) return '<a target="_blank" rel="noopener" href="'+esc(e.source)+'">Company source</a>';
  return '';
}

function month(y,m){
  var last=new Date(y,m+1,0).getDate(), evs=[], wkend=false, d, k;
  for(d=1;d<=last;d++){ k=iso(y,m,d);
    if(byDate[k]){ evs=evs.concat(byDate[k]);
      if((new Date(y,m,d).getDay()+6)%7>4) wkend=true; } }
  var cols=wkend?7:5;
  var est=evs.filter(function(e){return !e.reported&&e.confidence==='estimated';}).length;
  var rep=evs.filter(function(e){return e.reported;}).length;
  var dek=evs.length+' release'+(evs.length===1?'':'s');
  if(evs.length){ var parts=[];
    if(rep) parts.push(rep+' reported');
    if(evs.length-rep-est) parts.push((evs.length-rep-est)+' confirmed');
    if(est) parts.push(est+' estimated');
    dek+=' · '+parts.join(' · '); }
  var h='<div class="card"><div class="chead">'+MONTHS[m]+' '+y+'</div><div class="cdek">'+dek+'</div>';
  if(!evs.length){
    return h+'<div class="none">No release date is in the calendar for this month yet.</div></div>';
  }

  // grid: weeks run Monday to Friday, with Saturday and Sunday only when a release falls on one
  h+='<table class="grid"><thead><tr>';
  for(var c=0;c<cols;c++) h+='<th>'+DOW[c]+'</th>';
  h+='</tr></thead><tbody>';
  var first=(new Date(y,m,1).getDay()+6)%7;      // 0 = Monday
  var start=1-first;                             // day-of-month in the first Monday cell
  for(var w=start; w<=last; w+=7){
    var row='', any=false;
    for(c=0;c<cols;c++){
      d=w+c;
      if(d<1||d>last){ row+='<td class="out"></td>'; continue; }
      any=true; k=iso(y,m,d);
      var cls=k<today?'past':(k===today?'today':'');
      row+='<td class="'+cls+'"><div class="dn">'+d+(k===today?'<small>Today</small>':'')+'</div>'+
        (byDate[k]||[]).map(chip).join('')+'</td>';
    }
    if(any) h+='<tr>'+row+'</tr>';
  }
  h+='</tbody></table>';

  // list: the same releases with the period as the company states it
  h+='<table class="list"><thead><tr><th>Date</th><th>Release</th><th>Period as stated</th>'+
     '<th class="x">Time</th><th>Date status</th><th class="x">Link</th></tr></thead><tbody>';
  evs.forEach(function(e){
    var dt=new Date(+e.date.slice(0,4),+e.date.slice(5,7)-1,+e.date.slice(8,10));
    h+='<tr'+(e.date<today&&!e.reported?' class="past"':'')+'><td class="d">'+
      DOW[(dt.getDay()+6)%7]+' '+(+e.date.slice(8,10))+' '+MONTHS[m].slice(0,3)+'</td>'+
      '<td class="r">'+esc(e.name)+' '+esc(e.label)+'</td>'+
      '<td>'+esc(e.company)+', '+esc(e.period)+'</td>'+
      '<td class="x">'+(e.time?esc(e.time):'')+'</td><td>'+tag(e)+'</td>'+
      '<td class="x">'+link(e)+'</td></tr>';
  });
  return h+'</tbody></table></div>';
}

var html='', span=[];
for(var i=0;i<3;i++){ var mm=tm+i, yy=ty+Math.floor(mm/12); mm=mm%12;
  html+=month(yy,mm); span.push(MONTHS[mm]+' '+yy); }
el('months').innerHTML=html;

var lo=iso(ty,tm,1), e3=tm+3, hi=iso(ty+Math.floor(e3/12),e3%12,1);
var win=D.events.filter(function(e){return e.date>=lo&&e.date<hi;});
var cos={}; win.forEach(function(e){cos[e.company]=1;});
var up=(D.updated||'').slice(0,10);
el('meta').textContent=span[0]+' to '+span[2]+' · '+win.length+' releases · '+
  Object.keys(cos).length+' companies · dates last checked '+up;

function post(){ try{ parent.postMessage({type:'vgr-embed-height',
  id:'earnings-calendar', height:document.documentElement.scrollHeight},'*'); }catch(e){} }
post(); window.addEventListener('load',post); window.addEventListener('resize',post);
})();
"""

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VGR Financial Release Calendar</title>
<meta name="description" content="Expected results and trading-update dates for the companies in the VGR 40: the current month and the following two.">
<link rel="canonical" href="__PAGE_URL__">
<script type="application/ld+json">__LD__</script>
<style>__CSS__</style></head>
<body>
<div class="topbar"></div>
<div class="wrap">
  <div class="hd"><span class="figbox">VGR Intelligence</span><span class="vgr">VGR</span></div>
  <h1>Financial release calendar</h1>
  <p class="lede">Expected results, revenue releases and trading updates for the companies in the VGR 40, for the current month and the following two. Each entry gives the company and the period reported.</p>
  <div class="meta" id="meta"></div>
  <div class="lgnd">
    <span class="k"><span class="chip">COMPANY Q3-26</span> Date confirmed by the company</span>
    <span class="k"><span class="chip est">COMPANY Q3-26</span> Estimated date</span>
    <span class="k"><span class="chip rep">COMPANY Q3-26</span> Reported</span>
  </div>
  <div id="months"><noscript>__FALLBACK__</noscript></div>
  <div class="src">
    <p><b>Confirmed</b> means the company, or its exchange filing, has published the specific day. <b>Estimated</b> means the company has not yet published the day; the date is taken from the company's prior-year date or from a third-party calendar and is replaced when the company confirms it.</p>
    <p><b>Labels.</b> Q, H and 9M are the quarter, half-year and nine-month period; FY is the full year. The two digits are the fiscal year as the company names it, so H1-26/27 is the first half of fiscal 2026/27. Times are as stated by the company.</p>
    <p>Companies can move a date without notice. The same data is available as <a href="./earnings-calendar.csv">CSV</a>, <a href="./data.json">JSON</a> and a calendar feed (<a href="./calendar.ics">ICS</a>). Not investment advice.</p>
  </div>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>__JS__</script>
</body></html>
"""


def fallback_table(data):
    rows = "".join(
        f"<tr><td>{esc(r['date'])}</td><td>{esc(r['name'])} {esc(r['label'])}</td>"
        f"<td>{esc(r['company'])}, {esc(r['period'])}</td>"
        f"<td>{'Reported' if r['reported'] else r['confidence'].capitalize()}</td></tr>"
        for r in data["events"])
    return ('<table class="list"><thead><tr><th>Date</th><th>Release</th><th>Period as stated</th>'
            '<th>Date status</th></tr></thead><tbody>' + rows + "</tbody></table>")


def build_html(data):
    ld = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "VGR Financial Release Calendar",
        "description": "Expected results and trading-update dates for the companies in the VGR 40.",
        "url": PAGE_URL,
        "creator": {"@type": "Organization", "name": "Very Good Retail", "url": SITE},
        "dateModified": data["updated"],
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (PAGE.replace("__CSS__", CSS).replace("__JS__", JS)
            .replace("__LD__", json.dumps(ld, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__PAGE_URL__", PAGE_URL)
            .replace("__FALLBACK__", fallback_table(data))
            .replace("__DATA__", blob))


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def main():
    check = "--check" in sys.argv
    data, errs, warns = public_rows(offline="--offline" in sys.argv)
    for w in warns:
        print("WARN  " + w)
    if errs:
        for e in errs:
            print("ERROR " + e)
        print(f"{len(errs)} error(s). Nothing written.")
        sys.exit(1)
    n = len(data["events"])
    est = sum(1 for r in data["events"] if r["confidence"] == "estimated" and not r["reported"])
    rep = sum(1 for r in data["events"] if r["reported"])
    briefs = sum(1 for r in data["events"] if r["brief_url"])
    print(f"OK    {n} events: {rep} reported ({briefs} linked to a brief), "
          f"{n - rep - est} confirmed, {est} estimated; calendar updated {data['updated']}")
    if check:
        return
    write(OUT_DATA, json.dumps(data, ensure_ascii=False, indent=1) + "\n")
    write(OUT_HTML, build_html(data))
    write(OUT_ICS, build_ics(data))
    write(OUT_CSV, build_csv(data))
    print("wrote data.json, index.html, calendar.ics, earnings-calendar.csv")


if __name__ == "__main__":
    main()
