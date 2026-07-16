#!/usr/bin/env python3
"""
Genereert het grafische campagne-dashboard 'E-mailcampagnes KVC Westerlo'.

Bron: brevo.db (standaard) of ruwe Brevo-JSON payloads (--from-payloads, cloud-modus).
Schrijft een self-contained HTML (SVG-grafieken, geen externe libs) + een
Artifact-versie (zonder html/head/body-wikkel).

Gebruik:
  python3 dashboard.py                         # uit brevo.db
  python3 dashboard.py --from-payloads --dir X # uit ruwe Brevo campaign-JSON
"""
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "brevo.db")
OUT = os.path.join(HERE, "nieuwsbrief-dashboard.html")
OUT_ARTIFACT = os.path.join(HERE, "dashboard-artifact.html")

MONTHS_NL = ["", "jan", "feb", "mrt", "apr", "mei", "jun",
             "jul", "aug", "sep", "okt", "nov", "dec"]

# Vaste categorie-volgorde (index 1..7 = kleur c1..c7 in de HTML)
CATS = ["Ticketing", "Events & F&B", "Abonnementen", "Fanshop & merch",
        "Jeugd & club", "Algemeen", "Personeel"]


def classify(name):
    n = (name or "").lower()
    if "personeel" in n:
        return "Personeel"
    if re.search(r"beats|bites|steak|ribbekes|tapas|brunch|village|24-uur|santa|preparty|party|paaseieren|communie|themacafe|valentijn|fandag", n):
        return "Events & F&B"
    if re.search(r"shirt|fanshop|solden|tshirt|goodiebag|kalender|matchworn", n):
        return "Fanshop & merch"
    if re.search(r"\babo\b|abonnement|renewal|verleng|early ?bird|member|mini-abo", n):
        return "Abonnementen"
    if re.search(r"md-|ticket|presale|combiticket|kvcw-|kvc westerlo -|playoff|play-off", n):
        return "Ticketing"
    if re.search(r"kids|westel|stage|jobbeurs|academy|rbfa|u21|giveaway|prijsvraag", n):
        return "Jeugd & club"
    return "Algemeen"


def _rec(cid, name, tag, sent_date, sent, delivered, soft_b, hard_b,
         views, clicks, unsub, complaints, opens_rate):
    d = None
    if sent_date:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", sent_date)
        if m:
            d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    if not d:
        return None
    delivered = delivered or 0
    if delivered <= 0:
        return None
    views = views or 0
    clicks = clicks or 0
    return {
        "id": cid, "name": name or "(zonder naam)", "date": d, "month": d[:7],
        "category": classify(name), "sent": sent or 0, "delivered": delivered,
        "bounces": (soft_b or 0) + (hard_b or 0), "views": views, "clicks": clicks,
        "unsub": unsub or 0, "complaints": complaints or 0,
        "openRate": round(opens_rate or 0, 2),
        "clickRate": round(clicks / delivered * 100, 2),
    }


def records_from_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT c.id, c.name, c.sent_date, c.tag,
               s.sent, s.delivered, s.soft_bounces, s.hard_bounces,
               s.unique_views, s.unique_clicks, s.unsubscriptions,
               s.complaints, s.opens_rate
        FROM campaigns c JOIN campaign_stats s ON s.campaign_id = c.id
        WHERE s.delivered IS NOT NULL AND s.delivered > 0
        ORDER BY c.sent_date ASC
    """)
    data = []
    for r in cur.fetchall():
        rec = _rec(r[0], r[1], r[3], r[2], r[4], r[5], r[6], r[7],
                   r[8], r[9], r[10], r[11], r[12])
        if rec:
            data.append(rec)
    last = (cur.execute("SELECT MAX(ran_at) FROM sync_runs").fetchone() or [None])[0]
    conn.close()
    return data, last


def records_from_payloads(pdir):
    import glob
    data, seen = [], set()
    for f in sorted(glob.glob(os.path.join(pdir, "campaigns*.json"))):
        try:
            doc = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        camps = doc.get("campaigns") if isinstance(doc, dict) else (doc if isinstance(doc, list) else [])
        for c in (camps or []):
            g = ((c.get("statistics") or {}).get("globalStats")) or {}
            if not g or not g.get("delivered"):
                continue
            if c.get("id") in seen:
                continue
            seen.add(c.get("id"))
            rec = _rec(c.get("id"), c.get("name"), c.get("tag"),
                       c.get("sentDate") or c.get("scheduledAt"),
                       g.get("sent"), g.get("delivered"), g.get("softBounces"),
                       g.get("hardBounces"), g.get("uniqueViews"), g.get("uniqueClicks"),
                       g.get("unsubscriptions"), g.get("complaints"), g.get("opensRate"))
            if rec:
                data.append(rec)
    data.sort(key=lambda x: x["date"])
    return data


def nl_date(iso):
    """2026-07-16... -> '16 juli 2026'."""
    maanden = ["", "januari", "februari", "maart", "april", "mei", "juni",
               "juli", "augustus", "september", "oktober", "november", "december"]
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not m:
        return "onbekend"
    return f"{int(m.group(3))} {maanden[int(m.group(2))]} {m.group(1)}"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-payloads", action="store_true")
    ap.add_argument("--dir", default=os.path.join(HERE, "payloads"))
    args = ap.parse_args()

    if args.from_payloads:
        data = records_from_payloads(args.dir)
        last_sync = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    else:
        if not os.path.exists(DB):
            raise SystemExit("brevo.db bestaat niet. Draai eerst een sync of gebruik --from-payloads.")
        data, last_sync = records_from_db()

    dates = sorted(r["date"] for r in data)
    span = ""
    if dates:
        span = f"{nl_date(dates[0])} t/m {nl_date(dates[-1])}"
    updated = nl_date((last_sync or "")[:10]) if last_sync else "onbekend"

    payload = {
        "updated": updated, "span": span, "count": len(data),
        "campaigns": data, "monthsNl": MONTHS_NL, "cats": CATS,
    }
    html = HTML_TEMPLATE.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Dashboard geschreven: {OUT}  ({len(data)} campagnes)")

    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    style = re.search(r"<style>.*?</style>", html, re.S).group(0)
    body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
    with open(OUT_ARTIFACT, "w", encoding="utf-8") as fh:
        fh.write(f"<title>{title}</title>\n{style}\n{body}")
    print(f"Artifact-versie geschreven: {OUT_ARTIFACT}")


HTML_TEMPLATE = r"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E-mailcampagnes - KVC Westerlo</title>
<style>
  :root{
    --plane:#f4f3ef; --surface:#fcfcfb; --line:#e5e4dd; --baseline:#c3c2b7;
    --ink:#12100c; --ink2:#57544d; --muted:#8a877f;
    --accent:#2a78d6; --accent2:#1baf7a; --seq:#256abf; --grid:#eae9e2;
    --good:#0ca30c; --goodink:#006300; --warn:#b7791f; --crit:#c0392b;
    --card:#ffffff; --ring:rgba(18,16,12,.08); --chipbg:#efeee8;
    --c1:#2a78d6; --c2:#1baf7a; --c3:#eda100; --c4:#0a8a3f; --c5:#5a49c4; --c6:#d8639a; --c7:#8a877f;
  }
  @media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
    --plane:#0c0c0b; --surface:#171716; --line:#2a2a27; --baseline:#3a3a36;
    --ink:#f4f3ee; --ink2:#bdbcb2; --muted:#8a877f;
    --accent:#3987e5; --accent2:#22c58a; --seq:#3987e5; --grid:#242422;
    --good:#12b312; --goodink:#3ccb3c; --warn:#e0a83a; --crit:#e05a4c;
    --card:#171716; --ring:rgba(255,255,255,.08); --chipbg:#22221f;
    --c1:#3987e5; --c2:#22c58a; --c3:#e0a83a; --c4:#2fb45f; --c5:#9085e9; --c6:#e07bb0; --c7:#9a978d;
  }}
  :root[data-theme="dark"]{
    --plane:#0c0c0b; --surface:#171716; --line:#2a2a27; --baseline:#3a3a36;
    --ink:#f4f3ee; --ink2:#bdbcb2; --muted:#8a877f;
    --accent:#3987e5; --accent2:#22c58a; --seq:#3987e5; --grid:#242422;
    --good:#12b312; --goodink:#3ccb3c; --warn:#e0a83a; --crit:#e05a4c;
    --card:#171716; --ring:rgba(255,255,255,.08); --chipbg:#22221f;
    --c1:#3987e5; --c2:#22c58a; --c3:#e0a83a; --c4:#2fb45f; --c5:#9085e9; --c6:#e07bb0; --c7:#9a978d;
  }
  :root[data-theme="light"]{
    --plane:#f4f3ef; --surface:#fcfcfb; --line:#e5e4dd; --baseline:#c3c2b7;
    --ink:#12100c; --ink2:#57544d; --muted:#8a877f;
    --accent:#2a78d6; --accent2:#1baf7a; --seq:#256abf; --grid:#eae9e2;
    --good:#0ca30c; --goodink:#006300; --warn:#b7791f; --crit:#c0392b;
    --card:#ffffff; --ring:rgba(18,16,12,.08); --chipbg:#efeee8;
    --c1:#2a78d6; --c2:#1baf7a; --c3:#eda100; --c4:#0a8a3f; --c5:#5a49c4; --c6:#d8639a; --c7:#8a877f;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--plane);color:var(--ink);
    font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1180px;margin:0 auto;padding:0 22px 40px}
  header{padding:26px 0 4px}
  h1{margin:0;font-size:23px;letter-spacing:-.02em;font-weight:680}
  h1 b{color:var(--accent);font-weight:680}
  .sub{color:var(--ink2);font-size:13px;margin-top:4px}
  /* filterbalk */
  .bar{position:sticky;top:0;z-index:30;background:color-mix(in srgb,var(--plane) 92%,transparent);
    backdrop-filter:blur(8px);padding:12px 0;margin:10px 0 4px;border-bottom:1px solid var(--line);
    display:flex;gap:10px 14px;flex-wrap:wrap;align-items:center}
  .grp{display:flex;gap:4px;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:3px}
  .grp button{border:0;background:transparent;color:var(--ink2);font:inherit;font-size:12.5px;
    padding:6px 11px;border-radius:7px;cursor:pointer;white-space:nowrap}
  .grp button.on{background:var(--accent);color:#fff}
  .chips{display:flex;gap:6px;flex-wrap:wrap}
  .chip{border:1px solid var(--line);background:var(--surface);color:var(--ink2);border-radius:20px;
    padding:5px 11px 5px 9px;font-size:12.5px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;user-select:none}
  .chip .dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto}
  .chip.off{opacity:.38}
  .chip.sel{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 13%,var(--surface));color:var(--ink);font-weight:600}
  .pop{position:fixed;display:none;background:var(--surface);border:1px solid var(--ring);border-radius:14px;
    padding:16px;box-shadow:0 14px 44px rgba(0,0,0,.28);z-index:70;min-width:236px}
  .pop-h{font-weight:650;font-size:13.5px;margin-bottom:12px}
  .pop-l{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--ink2);margin-bottom:11px}
  .pop input[type=date]{background:var(--plane);border:1px solid var(--line);border-radius:9px;color:var(--ink);font:inherit;font-size:13px;padding:8px 10px}
  .pop-a{display:flex;justify-content:space-between;align-items:center;margin-top:4px}
  .pop-a .clr{background:transparent;border:0;color:var(--muted);font:inherit;font-size:12px;cursor:pointer;padding:6px}
  .pop-a .app{background:var(--accent);color:#fff;border:0;border-radius:9px;padding:8px 16px;cursor:pointer;font:inherit;font-size:13px;font-weight:600}
  input[type=search]{background:var(--surface);border:1px solid var(--line);border-radius:10px;
    color:var(--ink);font:inherit;font-size:13px;padding:8px 12px;min-width:190px}
  .toggle{display:inline-flex;align-items:center;gap:7px;font-size:12.5px;color:var(--ink2);cursor:pointer;user-select:none}
  .toggle .sw{width:34px;height:19px;border-radius:19px;background:var(--line);position:relative;transition:background .15s;flex:0 0 auto}
  .toggle .sw::after{content:"";position:absolute;top:2px;left:2px;width:15px;height:15px;border-radius:50%;background:#fff;transition:left .15s;box-shadow:0 1px 2px rgba(0,0,0,.3)}
  .toggle.on .sw{background:var(--accent)}
  .toggle.on .sw::after{left:17px}
  .scope{color:var(--muted);font-size:12.5px;margin-left:auto}
  /* datakwaliteit-noot */
  .note{background:color-mix(in srgb,var(--warn) 12%,var(--surface));border:1px solid color-mix(in srgb,var(--warn) 35%,var(--line));
    border-radius:12px;padding:10px 14px;font-size:12.5px;color:var(--ink2);margin:12px 0 0;display:flex;gap:9px;align-items:flex-start}
  .note b{color:var(--ink)}
  /* KPI's */
  .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:16px 0 8px}
  @media (max-width:1000px){.kpis{grid-template-columns:repeat(3,1fr)}}
  @media (max-width:620px){.kpis{grid-template-columns:repeat(2,1fr)}}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 16px}
  .kpi.lead{background:linear-gradient(160deg,color-mix(in srgb,var(--accent) 12%,var(--card)),var(--card))}
  .kpi .l{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.05em;display:flex;align-items:center;gap:5px;flex-wrap:wrap}
  .kpi .l .lt{white-space:nowrap}
  .kpi .n{font-size:27px;font-weight:700;letter-spacing:-.02em;line-height:1.15;margin-top:3px}
  .kpi .d{font-size:12px;margin-top:4px;color:var(--ink2)}
  .badge{font-size:9.5px;font-weight:600;letter-spacing:.03em;padding:2px 6px;border-radius:20px;text-transform:none;
    background:var(--chipbg);color:var(--muted)}
  .st-good{color:var(--goodink)} .st-warn{color:var(--warn)} .st-crit{color:var(--crit)}
  /* kaarten */
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:17px 18px 13px;margin-top:14px}
  .row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
  @media (max-width:820px){.row{grid-template-columns:1fr}}
  .card h2{margin:0;font-size:15px;font-weight:650;letter-spacing:-.01em}
  .card .cap{color:var(--ink2);font-size:12.5px;margin:3px 0 10px}
  .legend{display:flex;gap:14px;flex-wrap:wrap;margin:2px 0 8px;font-size:12px;color:var(--ink2)}
  .legend span{display:inline-flex;align-items:center;gap:6px}
  .legend i{width:13px;height:3px;border-radius:2px;display:inline-block}
  .legend i.dot{width:9px;height:9px;border-radius:50%}
  svg{display:block;width:100%;overflow:visible}
  .axis text{fill:var(--muted);font-size:11px}
  .gl{stroke:var(--grid);stroke-width:1}
  .bl{stroke:var(--baseline);stroke-width:1}
  .bm{stroke:var(--ink2);stroke-width:1;stroke-dasharray:4 3;opacity:.7}
  .lbl{fill:var(--ink);font-size:11px;font-weight:600}
  .lbl.sm{font-weight:500;fill:var(--ink2)}
  .qlab{fill:var(--muted);font-size:10.5px}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  th,td{padding:9px 12px;border-bottom:1px solid var(--line);white-space:nowrap;text-align:right;font-variant-numeric:tabular-nums}
  th:first-child,td:first-child,th.l,td.l{text-align:left;font-variant-numeric:normal}
  td:first-child{max-width:290px;overflow:hidden;text-overflow:ellipsis}
  th{position:sticky;top:0;background:var(--card);cursor:pointer;user-select:none;color:var(--ink2);font-weight:600;z-index:1}
  th:hover{color:var(--accent)}
  tbody tr:nth-child(even){background:color-mix(in srgb,var(--ink) 3.5%,transparent)}
  tbody tr:hover{background:color-mix(in srgb,var(--accent) 9%,transparent)}
  td.kc{position:relative;font-weight:600}
  td.kc::before{content:"";position:absolute;right:0;top:4px;bottom:4px;width:var(--kw,0%);
    background:color-mix(in srgb,var(--accent2) 30%,transparent);border-radius:3px 0 0 3px;z-index:0}
  td.kc span{position:relative;z-index:1}
  .tblwrap{max-height:460px;overflow:auto;border:1px solid var(--line);border-radius:12px;margin-top:4px}
  .tchip{font-size:11px;padding:2px 8px;border-radius:20px;background:var(--chipbg);color:var(--ink2);display:inline-flex;align-items:center;gap:5px}
  .tchip .dot{width:8px;height:8px;border-radius:50%}
  .flag{color:var(--warn);font-weight:700;cursor:help}
  .up{color:var(--goodink)} .down{color:var(--crit)}
  .foot{color:var(--muted);font-size:11.5px;margin-top:22px}
  .tip{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);border-radius:10px;
    padding:8px 11px;font-size:12px;box-shadow:0 8px 30px rgba(0,0,0,.22);opacity:0;transition:opacity .08s;z-index:60;max-width:280px}
  .tip .tv{font-weight:700;font-size:13px;margin-bottom:2px}
  .tip .tr{display:flex;align-items:center;gap:7px;color:var(--ink2)}
  .tip .tr b{margin-left:auto;color:var(--ink);font-variant-numeric:tabular-nums;padding-left:12px}
  .tip .tr i{width:10px;height:10px;border-radius:50%;flex:0 0 auto}
  .empty{fill:var(--muted);font-size:13px}
</style></head>
<body>
<div class="wrap">
<header>
  <h1>E-mailcampagnes <b>KVC Westerlo</b></h1>
  <div class="sub" id="sub"></div>
</header>

<div class="bar">
  <div class="grp" id="ranges"></div>
  <div class="chips" id="chips"></div>
  <input id="search" type="search" placeholder="Zoek campagne..." autocomplete="off">
  <label class="toggle" id="perstog"><span class="sw"></span><span>Personeel meetellen</span></label>
  <span class="scope" id="scope"></span>
</div>

<div class="note" id="qnote" style="display:none"></div>

<div class="kpis" id="kpis"></div>

<div class="card">
  <h2>Van verstuurd naar geklikt</h2>
  <p class="cap">Van elke verstuurde mail: hoeveel komen aan, worden geopend en aangeklikt? De stap Geopend ligt hoog door Apple Mail Privacy.</p>
  <svg id="funnel" viewBox="0 0 820 250" role="img" aria-label="Trechter van verstuurd naar geklikt"></svg>
</div>

<div class="row">
  <div class="card">
    <h2>Welk contenttype opent het best?</h2>
    <p class="cap">Open% per categorie, gewogen naar bezorgde mails. Stippellijn = clubgemiddelde.</p>
    <svg id="catopen" viewBox="0 0 400 300" role="img" aria-label="Open percentage per categorie"></svg>
  </div>
  <div class="card">
    <h2>...en welk type klikt het best?</h2>
    <p class="cap">Klik% per categorie. De eerlijkste maat: klikken wordt niet vervalst door privacyfilters.</p>
    <svg id="catclick" viewBox="0 0 400 300" role="img" aria-label="Klik percentage per categorie"></svg>
  </div>
</div>

<div class="card">
  <h2>Waar gaat je zendvolume naartoe?</h2>
  <p class="cap">Aantal bezorgde mails per categorie. Toont welk type het zwaarst weegt in het gemiddelde.</p>
  <svg id="volume" viewBox="0 0 820 250" role="img" aria-label="Zendvolume per categorie"></svg>
</div>

<div class="card">
  <h2>Open% en klik% per maand</h2>
  <p class="cap">Eigen schaal per paneel, zodat de kliktrend leesbaar blijft. Stippellijn = clubgemiddelde over de selectie.</p>
  <svg id="trend" viewBox="0 0 820 360" role="img" aria-label="Open en klik percentage per maand"></svg>
</div>

<div class="card">
  <h2>Geopend versus geklikt per campagne</h2>
  <p class="cap">Rechtsboven = onderwerp en inhoud werken. Rechtsonder = goed onderwerp, zwak aanbod. Linksonder = herbekijken. Bolgrootte = bereik. Min. 5.000 bezorgd.</p>
  <div class="legend" id="scatleg"></div>
  <svg id="scatter" viewBox="0 0 820 420" role="img" aria-label="Open versus klik per campagne"></svg>
</div>

<div class="row">
  <div class="card">
    <h2>Uitschrijvingen per categorie</h2>
    <p class="cap">Per 1.000 bezorgde mails. Welk contenttype verbrandt je lijst het snelst? Stippellijn = clubgemiddelde.</p>
    <svg id="unsub" viewBox="0 0 400 300" role="img" aria-label="Uitschrijvingen per categorie"></svg>
  </div>
  <div class="card">
    <h2>Sterkste en zwakste op klik%</h2>
    <p class="cap">Enkel campagnes met min. 5.000 bezorgd, zodat mini-lijsten de lijst niet kapen.</p>
    <svg id="ranks" viewBox="0 0 400 300" role="img" aria-label="Sterkste en zwakste campagnes"></svg>
  </div>
</div>

<div class="card">
  <h2>Alle campagnes</h2>
  <p class="cap">Klik op een kolomkop om te sorteren. "vs norm" = klik% t.o.v. het gemiddelde van dezelfde categorie.</p>
  <div class="tblwrap"><table id="tbl"></table></div>
</div>

<div class="foot" id="foot"></div>
</div>
<div class="pop" id="custompop">
  <div class="pop-h">Aangepaste periode</div>
  <label class="pop-l">Van<input type="date" id="dfrom"></label>
  <label class="pop-l">Tot<input type="date" id="dto"></label>
  <div class="pop-a"><button class="clr" id="popclear">Terug naar alles</button><button class="app" id="popapply">Toepassen</button></div>
</div>
<div class="tip" id="tip"></div>

<script>
const PAYLOAD = /*__DATA__*/null;
const M = PAYLOAD.monthsNl, CATS = PAYLOAD.cats, ALL = PAYLOAD.campaigns;
const MKT = CATS.filter(c=>c!=="Personeel");
const tip = document.getElementById('tip');
const fmt = n => Math.round(n).toLocaleString('nl-BE');
const p1 = n => (Math.round(n*10)/10).toLocaleString('nl-BE',{minimumFractionDigits:1,maximumFractionDigits:1})+'%';
const p2 = n => (Math.round(n*100)/100).toLocaleString('nl-BE',{minimumFractionDigits:2,maximumFractionDigits:2})+'%';
const axn = v => (Math.round(v*10)/10).toLocaleString('nl-BE',{maximumFractionDigits:1});
const catIdx = c => Math.max(1, CATS.indexOf(c)+1);
const catCol = c => `var(--c${catIdx(c)})`;
function monLab(k){const [y,m]=k.split('-');return M[+m]+" '"+y.slice(2);}

let state = { range:'d30', cat:null, q:'', pers:false, from:null, to:null };

// ---- initiele filterstaat uit URL (voor verificatie/screenshots) ----
(function(){const u=new URLSearchParams(location.search);
  if(u.get('p'))state.range=u.get('p');
  if(u.get('q'))state.q=u.get('q');
  if(u.get('pers')==='1')state.pers=true;
  if(u.get('c')&&MKT.includes(u.get('c')))state.cat=u.get('c');
  if(u.get('from'))state.from=u.get('from');
  if(u.get('to'))state.to=u.get('to');
})();

function inRange(c){
  if(state.range==='all')return true;
  if(state.range==='custom')return (!state.from||c.date>=state.from)&&(!state.to||c.date<=state.to);
  const last=ALL[ALL.length-1].date;
  if(state.range==='y2026')return c.date>='2026-01-01';
  const days={d90:90,d30:30}[state.range]; if(!days)return true;
  const cut=new Date(last); cut.setDate(cut.getDate()-days);
  return new Date(c.date)>=cut;
}
function scope(){
  const q=state.q.trim().toLowerCase();
  return ALL.filter(c=>{
    if(c.category==='Personeel' && !state.pers)return false;
    if(state.cat && c.category!==state.cat && c.category!=='Personeel')return false;
    if(!inRange(c))return false;
    if(q && !c.name.toLowerCase().includes(q))return false;
    return true;
  });
}
// gewogen statistieken
function stats(list){
  let d=0,se=0,vw=0,cl=0,un=0,co=0;
  for(const c of list){d+=c.delivered;se+=c.sent;vw+=c.views;cl+=c.clicks;un+=c.unsub;co+=c.complaints;}
  return {n:list.length, delivered:d, sent:se, views:vw, clicks:cl, unsub:un, complaints:co,
    open:d?vw/d*100:0, click:d?cl/d*100:0, unsubPM:d?un/d*1000:0,
    deliv:se?d/se*100:0, complPM:d?co/d*1000:0};
}
function byCat(list){ // gewogen per categorie, vaste volgorde, enkel cats met data
  const m={};
  for(const c of list){(m[c.category]??=[]).push(c);}
  return CATS.filter(c=>m[c]).map(c=>({cat:c, ...stats(m[c])}));
}

// ---- SVG helpers ----
function niceTicks(max, target){
  target=target||5;
  if(max<=0)return {ticks:[0,1], max:1};
  const raw=max/target, mag=Math.pow(10,Math.floor(Math.log10(raw))), nrm=raw/mag;
  let step= nrm<1.5?1: nrm<3?2: nrm<7?5:10; step*=mag;
  const nm=Math.ceil(max/step)*step, t=[];
  for(let v=0;v<=nm+step*0.001;v+=step)t.push(Math.round(v*1e6)/1e6);
  return {ticks:t, max:nm};
}
function esc(s){return String(s).replace(/[<>&"]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));}
function empty(svg,W,H){svg.setAttribute('viewBox',`0 0 ${W} ${H}`);svg.innerHTML=`<text class="empty" x="${W/2}" y="${H/2}" text-anchor="middle">Geen campagnes in deze selectie</text>`;}
function showTip(html,x,y){tip.innerHTML=html;tip.style.opacity=1;const r=tip.getBoundingClientRect();
  let px=x+14,py=y+14; if(px+r.width>innerWidth-8)px=x-r.width-14; if(py+r.height>innerHeight-8)py=y-r.height-14;
  tip.style.left=Math.max(6,px)+'px';tip.style.top=Math.max(6,py)+'px';}
function hideTip(){tip.style.opacity=0;}
function localX(svg,e,W){const r=svg.getBoundingClientRect();return (e.clientX-r.left)/r.width*W;}

// ---- KPI's ----
function renderKpis(cs){
  const s=stats(cs);
  const cats=byCat(cs.filter(c=>c.category!=='Personeel'));
  let best={cat:'-',click:0}; cats.forEach(c=>{if(c.click>best.click)best={cat:c.cat,click:c.click};});
  const unsubCls=s.unsubPM<=5?'st-good':s.unsubPM<=8?'st-warn':'st-crit';
  const delivCls=s.deliv>=98?'st-good':s.deliv>=95?'st-warn':'st-crit';
  const K=[
    {l:'Bereik (bezorgd)', n:fmt(s.delivered), d:`${s.n} campagnes`},
    {l:'Gem. klik %', n:p2(s.click), d:`${fmt(s.clicks)} unieke klikken`, lead:1,
      badge:'eerlijkste maat'},
    {l:'Gem. open %', n:p1(s.open), d:'gewogen', badge:'incl. Apple-privacy'},
    {l:'Uitschrijf %', n:p2(s.unsubPM/10), d:`${fmt(s.unsub)} totaal`, cls:unsubCls, hint:'gezond onder 0,50%'},
    {l:'Afgeleverd', n:p1(s.deliv), d:`spamklachten ${p2(s.complPM/10)}`, cls:delivCls, hint:'gezond boven 98%'},
    {l:'Sterkste categorie', n:best.cat, d:`klik% ${p2(best.click)}`, small:1},
  ];
  document.getElementById('kpis').innerHTML=K.map(k=>
    `<div class="kpi${k.lead?' lead':''}">
       <div class="l"><span class="lt">${k.l}</span>${k.badge?`<span class="badge">${k.badge}</span>`:''}</div>
       <div class="n${k.cls?' '+k.cls:''}"${k.small?' style="font-size:20px"':''}>${k.n}</div>
       <div class="d">${k.hint?`<span class="${k.cls||''}">${k.hint}</span> · `:''}${k.d}</div>
     </div>`).join('');
}

// ---- Trechter ----
function renderFunnel(cs){
  const svg=document.getElementById('funnel'),W=820,H=250; const s=stats(cs);
  if(!s.delivered)return empty(svg,W,H);
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const steps=[
    {l:'Verstuurd', v:s.sent, sub:'100%', col:'var(--c1)', o:.45},
    {l:'Afgeleverd', v:s.delivered, sub:p1(s.deliv)+' van verstuurd', col:'var(--c1)', o:.7},
    {l:'Geopend', v:s.views, sub:p1(s.delivered?s.views/s.delivered*100:0)+' van bezorgd', col:'var(--c1)', o:.9, note:'incl. Apple-privacy'},
    {l:'Geklikt', v:s.clicks, sub:p1(s.views?s.clicks/s.views*100:0)+' van geopend', col:'var(--accent2)', o:1},
  ];
  const mx={l:96,r:150,t:10,b:8}, iw=W-mx.l-mx.r, base=s.sent||1;
  const bh=42, gap=(H-mx.t-mx.b-bh*4)/3; let out='';
  steps.forEach((st,i)=>{
    const y=mx.t+i*(bh+gap), w=Math.max(3, st.v/base*iw);
    out+=`<rect x="${mx.l}" y="${y}" width="${w}" height="${bh-8}" rx="4" fill="${st.col}" fill-opacity="${st.o}" class="fb" data-i="${i}"/>`;
    out+=`<text class="lbl sm" x="${mx.l-10}" y="${y+bh/2-4}" text-anchor="end">${st.l}</text>`;
    out+=`<text class="lbl" x="${mx.l+w+10}" y="${y+bh/2-6}">${fmt(st.v)}</text>`;
    out+=`<text class="qlab" x="${mx.l+w+10}" y="${y+bh/2+8}">${st.sub}${st.note?' · '+st.note:''}</text>`;
  });
  svg.innerHTML=out;
  svg.querySelectorAll('.fb').forEach(b=>{const st=steps[+b.dataset.i];
    b.addEventListener('pointermove',e=>{b.style.opacity=.82;
      showTip(`<div class="tv">${st.l}</div><div class="tr">Aantal<b>${fmt(st.v)}</b></div><div class="tr">Van verstuurd<b>${p1(st.v/base*100)}</b></div>`,e.clientX,e.clientY);});
    b.addEventListener('pointerleave',()=>{b.style.opacity=1;hideTip();});});
}

// ---- horizontale categorie-balken (open/klik/unsub) ----
function hCatBars(svgId,W,_H,cats,valFn,fmtFn,bench,benchLabel){
  const svg=document.getElementById(svgId);
  if(!cats.length)return empty(svg,W,150);
  const bh=26, gap=15, top=18, axisb=26;                 // hoogte groeit mee met #categorieen
  const ih=cats.length*bh+(cats.length-1)*gap, H=top+ih+axisb;
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const mx={l:118,r:58}, iw=W-mx.l-mx.r;
  const vals=cats.map(valFn), maxV=Math.max(bench||0,...vals);
  const nt=niceTicks(maxV,4), X=v=>mx.l+v/nt.max*iw;
  let out='';
  nt.ticks.forEach(t=>{out+=`<line class="gl" x1="${X(t)}" y1="${top}" x2="${X(t)}" y2="${top+ih}"/>`;
    out+=`<text class="axis" x="${X(t)}" y="${H-8}" text-anchor="middle">${fmtFn(t,true)}</text>`;});
  cats.forEach((c,i)=>{const y=top+i*(bh+gap), v=valFn(c), w=Math.max(2,v/nt.max*iw);
    out+=`<rect x="${mx.l}" y="${y}" width="${w}" height="${bh}" rx="4" fill="${catCol(c.cat)}" class="cb" data-i="${i}"/>`;
    out+=`<text class="lbl sm" x="${mx.l-9}" y="${y+bh/2+4}" text-anchor="end">${c.cat}</text>`;
    out+=`<text class="lbl" x="${mx.l+w+7}" y="${y+bh/2+4}">${fmtFn(v)}</text>`;});
  if(bench){out+=`<line class="bm" x1="${X(bench)}" y1="${top-2}" x2="${X(bench)}" y2="${top+ih+2}"/>`;
    out+=`<text class="qlab" x="${X(bench)}" y="${top-5}" text-anchor="middle">${benchLabel}</text>`;}
  svg.innerHTML=out;
  svg.querySelectorAll('.cb').forEach(b=>{const c=cats[+b.dataset.i];
    b.addEventListener('pointermove',e=>{b.style.opacity=.82;
      showTip(`<div class="tv"><span class="tchip"><span class="dot" style="background:${catCol(c.cat)}"></span>${c.cat}</span></div>
        <div class="tr">Waarde<b>${fmtFn(valFn(c))}</b></div><div class="tr">Campagnes<b>${c.n}</b></div><div class="tr">Bezorgd<b>${fmt(c.delivered)}</b></div>`,e.clientX,e.clientY);});
    b.addEventListener('pointerleave',()=>{b.style.opacity=1;hideTip();});});
}

// ---- Volume per categorie (gesorteerd, categorie-kleur) ----
function renderVolume(cs){
  const cats=byCat(cs).slice().sort((a,b)=>b.delivered-a.delivered);
  const svg=document.getElementById('volume'),W=820,H=Math.max(120,cats.length*40+30);
  if(!cats.length)return empty(svg,W,H);
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const tot=cats.reduce((a,c)=>a+c.delivered,0), mx={l:118,r:150,t:6,b:6}, iw=W-mx.l-mx.r;
  const maxV=Math.max(...cats.map(c=>c.delivered)), bh=24, gap=(H-mx.t-mx.b-cats.length*bh)/Math.max(1,cats.length-1);
  let out='';
  cats.forEach((c,i)=>{const y=mx.t+i*(bh+gap), w=Math.max(2,c.delivered/maxV*iw);
    out+=`<rect x="${mx.l}" y="${y}" width="${w}" height="${bh}" rx="4" fill="${catCol(c.cat)}" class="vb" data-i="${i}"/>`;
    out+=`<text class="lbl sm" x="${mx.l-9}" y="${y+bh/2+4}" text-anchor="end">${c.cat}</text>`;
    out+=`<text class="lbl" x="${mx.l+w+8}" y="${y+bh/2+4}">${fmt(c.delivered)} <tspan class="qlab">· ${p1(c.delivered/tot*100)}</tspan></text>`;});
  svg.innerHTML=out;
  svg.querySelectorAll('.vb').forEach(b=>{const c=cats[+b.dataset.i];
    b.addEventListener('pointermove',e=>{b.style.opacity=.82;
      showTip(`<div class="tv"><span class="tchip"><span class="dot" style="background:${catCol(c.cat)}"></span>${c.cat}</span></div>
      <div class="tr">Bezorgd<b>${fmt(c.delivered)}</b></div><div class="tr">Aandeel<b>${p1(c.delivered/tot*100)}</b></div><div class="tr">Campagnes<b>${c.n}</b></div>`,e.clientX,e.clientY);});
    b.addEventListener('pointerleave',()=>{b.style.opacity=1;hideTip();});});
}

// ---- maandtrend (2 panelen) ----
function months(cs){
  const m={};
  for(const c of cs){(m[c.month]??=[]).push(c);}
  return Object.keys(m).sort().map(k=>({month:k, ...stats(m[k])}));
}
function renderTrend(cs){
  const svg=document.getElementById('trend'),W=820,H=360; const d=months(cs), s=stats(cs);
  if(d.length<1)return empty(svg,W,H);
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const mx={l:44,r:56,t:14,b:26}, iw=W-mx.l-mx.r, ph=150, gapP=26;
  const X=i=> d.length===1? mx.l+iw/2 : mx.l+i/(d.length-1)*iw;
  // x-labels zonder overlap: label als er minstens minGap px sinds de vorige is
  const minGap=64; let lastLabX=-1e9;
  d.forEach(p=>{p._lab=0;});
  d.forEach((p,i)=>{const x=X(i); if(x-lastLabX>=minGap){p._lab=1;lastLabX=x;}});
  // forceer laatste maand; verwijder de voorlaatste als die te dichtbij staat
  if(d.length>1){const li=d.length-1;
    if(!d[li]._lab){ if(X(li)-lastLabX<minGap){for(let j=li-1;j>=0;j--){if(d[j]._lab){d[j]._lab=0;break;}}} d[li]._lab=1; }}
  function panel(y0,key,col,label,benchV){
    const vals=d.map(p=>p[key]), nt=niceTicks(Math.max(benchV,...vals),4), Y=v=>y0+ph-v/nt.max*ph;
    let o='';
    nt.ticks.forEach(t=>{o+=`<line class="gl" x1="${mx.l}" y1="${Y(t)}" x2="${W-mx.r}" y2="${Y(t)}"/>`;
      o+=`<text class="axis" x="${mx.l-8}" y="${Y(t)+3}" text-anchor="end">${axn(t)}%</text>`;});
    if(benchV){o+=`<line class="bm" x1="${mx.l}" y1="${Y(benchV)}" x2="${W-mx.r}" y2="${Y(benchV)}"/>`;
      o+=`<text class="qlab" x="${W-mx.r+4}" y="${Y(benchV)+3}">${p1(benchV)}</text>`;}
    let path=''; d.forEach((p,i)=>path+=(i?'L':'M')+X(i).toFixed(1)+' '+Y(p[key]).toFixed(1));
    o+=`<path d="${path}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    d.forEach((p,i)=>{o+=`<circle cx="${X(i)}" cy="${Y(p[key])}" r="3.2" fill="${col}" stroke="var(--card)" stroke-width="1.6"/>`;});
    o+=`<text class="lbl sm" x="${mx.l}" y="${y0-4}">${label}</text>`;
    return o;
  }
  let out=panel(mx.t,'open','var(--accent)','Open %',s.open);
  out+=panel(mx.t+ph+gapP,'click','var(--accent2)','Klik %',s.click);
  // x-as onderaan
  d.forEach((p,i)=>{if(p._lab)out+=`<text class="axis" x="${X(i)}" y="${H-8}" text-anchor="middle">${monLab(p.month)}</text>`;});
  // crosshair over beide panelen
  out+=`<line id="tc" x1="0" y1="${mx.t}" x2="0" y2="${mx.t+ph*2+gapP}" class="bl" opacity="0"/>`;
  out+=`<rect x="${mx.l}" y="${mx.t}" width="${iw}" height="${ph*2+gapP}" fill="transparent" id="thit"/>`;
  svg.innerHTML=out;
  const hit=svg.querySelector('#thit'),cx=svg.querySelector('#tc');
  hit.addEventListener('pointermove',e=>{const px=localX(svg,e,W);let i=d.length===1?0:Math.round((px-mx.l)/iw*(d.length-1));
    i=Math.max(0,Math.min(d.length-1,i));const p=d[i];cx.setAttribute('x1',X(i));cx.setAttribute('x2',X(i));cx.setAttribute('opacity',1);
    showTip(`<div class="tv">${monLab(p.month)}</div>
      <div class="tr"><i style="background:var(--accent)"></i>Open<b>${p1(p.open)}</b></div>
      <div class="tr"><i style="background:var(--accent2)"></i>Klik<b>${p2(p.click)}</b></div>
      <div class="tr">Campagnes<b>${p.n}</b></div><div class="tr">Bezorgd<b>${fmt(p.delivered)}</b></div>`,e.clientX,e.clientY);});
  hit.addEventListener('pointerleave',()=>{cx.setAttribute('opacity',0);hideTip();});
}

// ---- Scatter ----
function renderScatter(cs){
  const svg=document.getElementById('scatter'),W=820,H=420;
  const pts=cs.filter(c=>c.category!=='Personeel'&&c.delivered>=5000&&c.openRate<=100);
  if(!pts.length)return empty(svg,W,H);
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const s=stats(pts), mx={l:44,r:16,t:12,b:34}, iw=W-mx.l-mx.r, ih=H-mx.t-mx.b;
  const xs=pts.map(p=>p.openRate), ys=pts.map(p=>p.clickRate);
  const xmin=Math.max(0,Math.floor((Math.min(...xs)-3)/5)*5), xmax=Math.ceil((Math.max(...xs)+3)/5)*5;
  const ntY=niceTicks(Math.max(...ys)*1.05,5);
  const X=v=>mx.l+(v-xmin)/(xmax-xmin)*iw, Y=v=>mx.t+ih-v/ntY.max*ih;
  const rMax=Math.max(...pts.map(p=>p.delivered)), R=v=>4+Math.sqrt(v/rMax)*13;
  let out='';
  for(let t=xmin;t<=xmax;t+=5){out+=`<line class="gl" x1="${X(t)}" y1="${mx.t}" x2="${X(t)}" y2="${mx.t+ih}"/>`;out+=`<text class="axis" x="${X(t)}" y="${H-14}" text-anchor="middle">${t}%</text>`;}
  ntY.ticks.forEach(t=>{out+=`<line class="gl" x1="${mx.l}" y1="${Y(t)}" x2="${W-mx.r}" y2="${Y(t)}"/>`;out+=`<text class="axis" x="${mx.l-8}" y="${Y(t)+3}" text-anchor="end">${axn(t)}%</text>`;});
  out+=`<text class="axis" x="${mx.l+iw/2}" y="${H}" text-anchor="middle">open %  →</text>`;
  out+=`<text class="axis" transform="rotate(-90 13 ${mx.t+ih/2})" x="13" y="${mx.t+ih/2}" text-anchor="middle">↑  klik %</text>`;
  // benchmark kwadranten
  out+=`<line class="bm" x1="${X(s.open)}" y1="${mx.t}" x2="${X(s.open)}" y2="${mx.t+ih}"/>`;
  out+=`<line class="bm" x1="${mx.l}" y1="${Y(s.click)}" x2="${W-mx.r}" y2="${Y(s.click)}"/>`;
  out+=`<text class="qlab" x="${W-mx.r-4}" y="${mx.t+12}" text-anchor="end">toppers</text>`;
  out+=`<text class="qlab" x="${W-mx.r-4}" y="${mx.t+ih-6}" text-anchor="end">goed onderwerp, zwak aanbod</text>`;
  // punten (grootste onderaan zodat kleine bovenop)
  pts.slice().sort((a,b)=>b.delivered-a.delivered).forEach(p=>{
    out+=`<circle cx="${X(p.openRate).toFixed(1)}" cy="${Y(p.clickRate).toFixed(1)}" r="${R(p.delivered).toFixed(1)}" fill="${catCol(p.category)}" fill-opacity="0.72" stroke="var(--card)" stroke-width="1.2" class="pt"
      data-n="${esc(p.name)}" data-c="${esc(p.category)}" data-o="${p.openRate}" data-k="${p.clickRate}" data-d="${p.delivered}"/>`;});
  svg.innerHTML=out;
  svg.querySelectorAll('.pt').forEach(el=>{
    el.addEventListener('pointermove',e=>{el.setAttribute('stroke','var(--ink)');
      showTip(`<div class="tv">${el.dataset.n}</div>
        <div class="tr"><i style="background:${catCol(el.dataset.c)}"></i>${el.dataset.c}</div>
        <div class="tr">Open<b>${p1(+el.dataset.o)}</b></div><div class="tr">Klik<b>${p2(+el.dataset.k)}</b></div>
        <div class="tr">Bezorgd<b>${fmt(+el.dataset.d)}</b></div>`,e.clientX,e.clientY);});
    el.addEventListener('pointerleave',()=>{el.setAttribute('stroke','var(--card)');hideTip();});});
  // legende
  document.getElementById('scatleg').innerHTML=byCat(pts).map(c=>`<span><i class="dot" style="background:${catCol(c.cat)}"></i>${c.cat}</span>`).join('');
}

// ---- Ranglijsten ----
function renderRanks(cs){
  const svg=document.getElementById('ranks'),W=400;
  const elig=cs.filter(c=>c.delivered>=5000).slice().sort((a,b)=>b.clickRate-a.clickRate);
  if(elig.length<2){empty(svg,W,300);document.getElementById('ranks').closest('.card').style.display=elig.length?'':'';return;}
  const top=elig.slice(0,8), low=elig.slice(-5).reverse();
  const list=[{h:'Sterkste',rows:top},{h:'Zwakste',rows:low}];
  const rowH=22, gap=7, headH=20;
  const H=headH+8+top.length*(rowH+gap)+ 22 + headH+8+low.length*(rowH+gap);
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  const maxV=Math.max(...top.map(c=>c.clickRate)); const mx={l:6,r:118}, bx=170, bw=W-mx.r-bx;
  let out='', y=0;
  list.forEach(grp=>{
    out+=`<text class="lbl sm" x="${mx.l}" y="${y+14}">${grp.h} op klik%</text>`; y+=headH+6;
    grp.rows.forEach(c=>{
      const w=Math.max(2,c.clickRate/maxV*bw), nm=c.name.length>26?c.name.slice(0,25)+'…':c.name;
      out+=`<text class="lbl sm" x="${mx.l}" y="${y+rowH/2+4}" style="font-size:10.5px">${esc(nm)}</text>`;
      out+=`<rect x="${bx}" y="${y+2}" width="${w}" height="${rowH-4}" rx="3" fill="${catCol(c.category)}"/>`;
      out+=`<text class="lbl" x="${bx+w+6}" y="${y+rowH/2+4}">${p2(c.clickRate)}</text>`;
      out+=`<text class="qlab" x="${W-4}" y="${y+rowH/2+4}" text-anchor="end">${fmt(c.delivered)}</text>`;
      y+=rowH+gap;
    });
    y+=22;
  });
  svg.innerHTML=out;
}

// ---- Tabel ----
const MND3=["","jan","feb","mrt","apr","mei","jun","jul","aug","sep","okt","nov","dec"];
function dispDate(d){const [y,m,dd]=d.split('-');return `${+dd} ${MND3[+m]} '${y.slice(2)}`;}
let sortKey='date', sortAsc=false;
function renderTable(cs){
  const norms={}; byCat(cs.filter(c=>c.category!=='Personeel')).forEach(c=>norms[c.cat]=c.click);
  const maxClick=Math.max(0.5,...cs.map(c=>c.clickRate));
  const cols=[['name','Campagne','l'],['category','Categorie','l'],['date','Datum','l'],
    ['delivered','Bezorgd'],['openRate','Open %'],['clickRate','Klik %'],['deltaN','vs norm'],
    ['unsubR','Uitschrijf %'],['ndR','Niet bezorgd %']];
  const rows=cs.map(c=>({...c, unsubR:c.delivered?c.unsub/c.delivered*100:0,
    ndR:c.sent?(c.sent-c.delivered)/c.sent*100:0,
    deltaN:(norms[c.category]!=null)? c.clickRate-norms[c.category] : null}));
  rows.sort((a,b)=>{let x=a[sortKey],y=b[sortKey];
    if(x==null)x=-1e9; if(y==null)y=-1e9;
    if(typeof x==='string')return sortAsc?x.localeCompare(y):y.localeCompare(x);
    return sortAsc?x-y:y-x;});
  let h='<thead><tr>'+cols.map(c=>`<th class="${c[2]||''}" data-k="${c[0]}">${c[1]}</th>`).join('')+'</tr></thead><tbody>';
  rows.forEach(c=>{
    const flag=c.openRate>100?` <span class="flag" title="Boven 100% door Apple Mail Privacy bij een mini-lijst, geen fout.">⚠</span>`:'';
    const dn=c.deltaN==null?'<span class="qlab">-</span>':`<span class="${c.deltaN>=0?'up':'down'}">${c.deltaN>=0?'+':''}${p2(c.deltaN).replace('%','')}</span>`;
    const kw=(Math.max(0,c.clickRate)/maxClick*100).toFixed(1);
    h+=`<tr><td class="l" title="${esc(c.name)}">${esc(c.name)}</td>
      <td class="l"><span class="tchip"><span class="dot" style="background:${catCol(c.category)}"></span>${c.category}</span></td>
      <td class="l">${dispDate(c.date)}</td><td>${fmt(c.delivered)}</td><td>${p1(c.openRate)}${flag}</td>
      <td class="kc" style="--kw:${kw}%"><span>${p2(c.clickRate)}</span></td><td>${dn}</td><td>${p2(c.unsubR)}</td><td>${p1(c.ndR)}</td></tr>`;
  });
  const tbl=document.getElementById('tbl'); tbl.innerHTML=h+'</tbody>';
  tbl.querySelectorAll('th').forEach(th=>th.addEventListener('click',()=>{
    const k=th.dataset.k; if(k===sortKey)sortAsc=!sortAsc; else{sortKey=k;sortAsc=(k==='name'||k==='category');}
    renderTable(scope());}));
}

// ---- orchestratie ----
function renderAll(){
  const cs=scope();
  document.getElementById('scope').textContent=`toont ${cs.length} van ${ALL.length} campagnes`;
  renderKpis(cs); renderFunnel(cs);
  // categorie-balken volgen de selectie (Personeel verschijnt grijs als de toggle aan staat);
  // de benchmark blijft zuiver marketing (Personeel telt nooit mee in het clubgemiddelde).
  const bc=byCat(cs), bs=stats(cs.filter(c=>c.category!=='Personeel'));
  hCatBars('catopen',400,300, bc, c=>c.open, (v,ax)=>ax?axn(v)+'%':p1(v), bs.open, 'clubgem.');
  hCatBars('catclick',400,300, bc, c=>c.click, (v,ax)=>ax?axn(v)+'%':p2(v), bs.click, 'clubgem.');
  renderVolume(cs); renderTrend(cs); renderScatter(cs);
  hCatBars('unsub',400,300, bc, c=>c.unsubPM, (v,ax)=>ax?axn(v):(Math.round(v*10)/10).toLocaleString('nl-BE',{minimumFractionDigits:1,maximumFractionDigits:1})+' ‰', bs.unsubPM, 'clubgem.');
  renderRanks(cs); renderTable(cs);
}

// ---- filterbalk opbouwen ----
function buildBar(){
  const ranges=[['d30','30 dagen'],['d90','90 dagen'],['y2026','2026'],['all','Alles'],['custom','Aangepast']];
  const rb=document.getElementById('ranges');
  rb.innerHTML=ranges.map(r=>`<button data-r="${r[0]}" class="${r[0]===state.range?'on':''}">${r[1]}</button>`).join('');
  const pop=document.getElementById('custompop'), df=document.getElementById('dfrom'), dt=document.getElementById('dto');
  const minD=ALL[0].date, maxD=ALL[ALL.length-1].date;
  df.min=dt.min=minD; df.max=dt.max=maxD;
  df.value=state.from||minD; dt.value=state.to||maxD;
  const setRangeBtn=r=>rb.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x.dataset.r===r));
  function openPop(btn){const r=btn.getBoundingClientRect(); pop.style.display='block';
    const w=pop.offsetWidth||236; pop.style.left=Math.max(8,Math.min(r.left,innerWidth-w-8))+'px'; pop.style.top=(r.bottom+8)+'px';}
  function closePop(){pop.style.display='none';}
  rb.querySelectorAll('button').forEach(b=>b.onclick=()=>{
    if(b.dataset.r==='custom'){openPop(b); return;}       // popup i.p.v. direct filteren
    state.range=b.dataset.r; setRangeBtn(state.range); closePop(); renderAll();});
  document.getElementById('popapply').onclick=()=>{state.from=df.value||null; state.to=dt.value||null;
    state.range='custom'; setRangeBtn('custom'); closePop(); renderAll();};
  document.getElementById('popclear').onclick=()=>{state.range='all'; setRangeBtn('all'); closePop(); renderAll();};
  document.addEventListener('click',e=>{if(pop.style.display==='block'&&!pop.contains(e.target)&&!e.target.closest('[data-r="custom"]'))closePop();});
  if(new URLSearchParams(location.search).get('pop')==='1'){setRangeBtn('custom');openPop(rb.querySelector('[data-r="custom"]'));}
  // categorie-chips: één klik = enkel die categorie, opnieuw klikken = alles terug
  const ch=document.getElementById('chips');
  ch.innerHTML=MKT.map(c=>`<span class="chip" data-c="${c}"><span class="dot" style="background:${catCol(c)}"></span>${c}</span>`).join('');
  const paint=()=>ch.querySelectorAll('.chip').forEach(x=>{const c=x.dataset.c;
    x.classList.toggle('sel',state.cat===c); x.classList.toggle('off',state.cat!==null&&state.cat!==c);});
  ch.querySelectorAll('.chip').forEach(el=>el.onclick=()=>{const c=el.dataset.c;
    state.cat=(state.cat===c)?null:c; paint(); renderAll();});
  paint();
  const pt=document.getElementById('perstog'); pt.classList.toggle('on',state.pers);
  pt.onclick=()=>{state.pers=!state.pers;pt.classList.toggle('on',state.pers);renderAll();};
  const se=document.getElementById('search'); se.value=state.q;
  let t; se.oninput=e=>{clearTimeout(t);t=setTimeout(()=>{state.q=e.target.value;renderAll();},150);};
}

// datakwaliteit-noot als er >100% campagnes zijn
(function(){const bad=ALL.filter(c=>c.openRate>100);
  if(bad.length){const n=document.getElementById('qnote');n.style.display='';
    n.innerHTML=`<span>ℹ️</span><span><b>Let op:</b> ${bad.length} interne personeelsmail toont een open% boven 100%. Dat komt door Apple Mail Privacy bij hele kleine lijsten en is geen fout. Interne lijsten (Personeel) staan standaard buiten de cijfers, zet ze aan met de schakelaar hierboven.</span>`;}
})();

document.getElementById('sub').textContent=`${PAYLOAD.count} campagnes · ${PAYLOAD.span} · laatste update ${PAYLOAD.updated}`;
document.getElementById('foot').textContent='Bron: e-mailstatistieken uit Brevo. Open% = Brevo-maatstaf incl. Apple Mail Privacy (licht overschat). Klik% = unieke klikken gedeeld door bezorgde mails.';
buildBar();
let rt; addEventListener('resize',()=>{clearTimeout(rt);rt=setTimeout(renderAll,120);});
renderAll();
</script>
</body></html>"""


if __name__ == "__main__":
    main()
