#!/usr/bin/env python3
"""
Genereert een grafisch campagne-dashboard uit brevo.db.

Leest campaigns + campaign_stats, berekent de cijfers, en schrijft een
self-contained HTML-bestand met grafieken (SVG, geen externe libs) en filters.

Gebruik:
  python3 dashboard.py            # schrijft nieuwsbrief-dashboard.html
Herbruikbaar: draai opnieuw na een sync om te verversen.
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


def _rec(cid, name, tag, sent_date, sent, delivered, soft_b, hard_b,
         views, clicks, unsub, complaints, opens_rate):
    """Bouw één genormaliseerd campagne-record (gedeeld door db- en payload-bron)."""
    d = None
    if sent_date:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", sent_date)
        if m:
            d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    if not d:
        return None
    delivered = delivered or 0
    views = views or 0
    clicks = clicks or 0
    click_rate = round(clicks / delivered * 100, 2) if delivered else 0
    return {
        "id": cid, "name": name or "(zonder naam)", "date": d, "month": d[:7],
        "tag": tag or "", "sent": sent or 0, "delivered": delivered,
        "bounces": (soft_b or 0) + (hard_b or 0), "views": views, "clicks": clicks,
        "unsub": unsub or 0, "complaints": complaints or 0,
        "openRate": round(opens_rate or 0, 2), "clickRate": click_rate,
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
    last_sync = (cur.execute("SELECT MAX(ran_at) FROM sync_runs").fetchone() or [None])[0]
    conn.close()
    return data, last_sync


def records_from_payloads(pdir):
    """Bouw records rechtstreeks uit ruwe Brevo-campagne-JSON (cloud-modus, geen db)."""
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
            cid = c.get("id")
            if cid in seen:
                continue
            seen.add(cid)
            sender = c.get("sender") or {}
            rec = _rec(cid, c.get("name"), c.get("tag"),
                       c.get("sentDate") or c.get("scheduledAt"),
                       g.get("sent"), g.get("delivered"), g.get("softBounces"),
                       g.get("hardBounces"), g.get("uniqueViews"), g.get("uniqueClicks"),
                       g.get("unsubscriptions"), g.get("complaints"), g.get("opensRate"))
            if rec:
                data.append(rec)
    data.sort(key=lambda x: x["date"])
    return data


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-payloads", action="store_true",
                    help="bouw uit ruwe Brevo-JSON in --dir i.p.v. uit brevo.db (cloud-modus)")
    ap.add_argument("--dir", default=os.path.join(HERE, "payloads"),
                    help="map met campaigns*.json (alleen met --from-payloads)")
    args = ap.parse_args()

    if args.from_payloads:
        data = records_from_payloads(args.dir)
        last_sync = datetime.now(timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M")
    else:
        if not os.path.exists(DB):
            raise SystemExit("brevo.db bestaat niet. Draai eerst een sync of gebruik --from-payloads.")
        data, last_sync = records_from_db()

    gen = datetime.now(timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M")
    payload = {
        "generated": gen,
        "lastSync": last_sync or "onbekend",
        "campaigns": data,
        "monthsNl": MONTHS_NL,
    }

    html = HTML_TEMPLATE.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"Dashboard geschreven: {OUT}  ({len(data)} campagnes)")

    # Artifact-versie: inhoud zonder <html>/<head>/<body>-wikkel (Artifact levert die zelf).
    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    style = re.search(r"<style>.*?</style>", html, re.S).group(0)
    body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
    artifact = f"<title>{title}</title>\n{style}\n{body}"
    with open(OUT_ARTIFACT, "w", encoding="utf-8") as fh:
        fh.write(artifact)
    print(f"Artifact-versie geschreven: {OUT_ARTIFACT}")


HTML_TEMPLATE = r"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Nieuwsbrief dashboard - KVC Westerlo</title>
<style>
  :root{
    --plane:#f9f9f7; --surface:#fcfcfb; --line:#e1e0d9; --baseline:#c3c2b7;
    --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
    --s1:#2a78d6; --s2:#1baf7a; --seq:#256abf; --seqLite:#cde2fb;
    --accent:#eda100; --good:#0ca30c; --crit:#d03b3b;
    --card:#fcfcfb; --ring:rgba(11,11,11,.10);
  }
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      --plane:#0d0d0d; --surface:#1a1a19; --line:#2c2c2a; --baseline:#383835;
      --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
      --s1:#3987e5; --s2:#199e70; --seq:#3987e5; --seqLite:#184f95;
      --accent:#c98500; --good:#0ca30c; --crit:#d03b3b;
      --card:#1a1a19; --ring:rgba(255,255,255,.10);
    }
  }
  :root[data-theme="dark"]{
    --plane:#0d0d0d; --surface:#1a1a19; --line:#2c2c2a; --baseline:#383835;
    --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
    --s1:#3987e5; --s2:#199e70; --seq:#3987e5; --seqLite:#184f95;
    --accent:#c98500; --good:#0ca30c; --crit:#d03b3b;
    --card:#1a1a19; --ring:rgba(255,255,255,.10);
  }
  :root[data-theme="light"]{
    --plane:#f9f9f7; --surface:#fcfcfb; --line:#e1e0d9; --baseline:#c3c2b7;
    --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
    --s1:#2a78d6; --s2:#1baf7a; --seq:#256abf; --seqLite:#cde2fb;
    --accent:#eda100; --good:#0ca30c; --crit:#d03b3b;
    --card:#fcfcfb; --ring:rgba(11,11,11,.10);
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--plane);color:var(--ink);
    font:14px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
  header{padding:26px 30px 6px}
  h1{margin:0;font-size:21px;letter-spacing:-.02em;font-weight:650}
  h1 b{color:var(--accent);font-weight:650}
  .sub{color:var(--muted);font-size:12.5px;margin-top:3px}
  .bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;padding:16px 30px}
  .bar .grp{display:flex;gap:6px;background:var(--surface);border:1px solid var(--line);
    border-radius:10px;padding:4px}
  .bar button{border:0;background:transparent;color:var(--ink2);font:inherit;font-size:12.5px;
    padding:6px 11px;border-radius:7px;cursor:pointer}
  .bar button.on{background:var(--s1);color:#fff}
  .bar input{background:var(--surface);border:1px solid var(--line);border-radius:10px;
    color:var(--ink);font:inherit;font-size:13px;padding:8px 12px;min-width:200px}
  .bar .count{color:var(--muted);font-size:12.5px;margin-left:auto}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;padding:6px 30px 4px}
  .kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
  .kpi .n{font-size:30px;font-weight:680;letter-spacing:-.02em;line-height:1.1}
  .kpi .l{color:var(--muted);font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;margin-top:4px}
  .kpi .d{font-size:12px;margin-top:6px;color:var(--ink2)}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:16px 30px 30px}
  @media (max-width:900px){.grid{grid-template-columns:1fr}}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 18px 12px}
  .card.full{grid-column:1/-1}
  .card h2{margin:0 0 2px;font-size:14px;font-weight:640}
  .card .cap{color:var(--muted);font-size:12px;margin:0 0 12px}
  .legend{display:flex;gap:16px;flex-wrap:wrap;margin:0 0 8px;font-size:12.5px;color:var(--ink2)}
  .legend span{display:inline-flex;align-items:center;gap:6px}
  .legend i{width:14px;height:3px;border-radius:2px;display:inline-block}
  svg{display:block;width:100%;overflow:visible}
  .axis text{fill:var(--muted);font-size:11px}
  .axis line{stroke:var(--line);stroke-width:1}
  .baseline{stroke:var(--baseline);stroke-width:1}
  .lbl{fill:var(--ink);font-size:11px;font-weight:600}
  .lbl2{fill:var(--ink2);font-size:11px}
  table{width:100%;border-collapse:collapse;font-size:12.5px}
  th,td{padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap;text-align:right;
    font-variant-numeric:tabular-nums}
  th:first-child,td:first-child{text-align:left;font-variant-numeric:normal;max-width:340px;
    overflow:hidden;text-overflow:ellipsis}
  th{position:sticky;top:0;background:var(--card);cursor:pointer;user-select:none;color:var(--ink2);font-weight:600}
  th:hover{color:var(--accent)}
  tbody tr:hover{background:color-mix(in srgb,var(--s1) 8%,transparent)}
  .tblwrap{max-height:420px;overflow:auto;border:1px solid var(--line);border-radius:12px}
  .tip{position:fixed;pointer-events:none;background:var(--surface);border:1px solid var(--ring);
    border-radius:10px;padding:8px 10px;font-size:12px;box-shadow:0 6px 24px rgba(0,0,0,.18);
    opacity:0;transition:opacity .08s;z-index:50;min-width:150px}
  .tip .tv{font-weight:680;font-size:13px}
  .tip .tr{display:flex;align-items:center;gap:7px;margin-top:3px;color:var(--ink2)}
  .tip .tr i{width:12px;height:3px;border-radius:2px}
  .tip .tr b{margin-left:auto;color:var(--ink);font-variant-numeric:tabular-nums}
  .foot{color:var(--muted);font-size:11.5px;padding:0 30px 30px}
</style></head>
<body>
<header>
  <h1>Nieuwsbrief dashboard <b>KVC Westerlo</b></h1>
  <div class="sub" id="subtitle"></div>
</header>

<div class="bar">
  <div class="grp" id="ranges"></div>
  <input id="search" type="search" placeholder="Zoek campagne (bv. abo, MD-1, personeel)…" autocomplete="off">
  <span class="count" id="scopecount"></span>
</div>

<div class="kpis" id="kpis"></div>

<div class="grid">
  <div class="card full">
    <h2>Open- en klikpercentage per maand</h2>
    <p class="cap">Gewogen naar aantal afgeleverde e-mails. Open% is de Brevo-maatstaf (incl. Apple-privacy).</p>
    <div class="legend">
      <span><i style="background:var(--s1)"></i>Open %</span>
      <span><i style="background:var(--s2)"></i>Klik %</span>
    </div>
    <svg id="trend" viewBox="0 0 800 300" role="img" aria-label="Open- en klikpercentage per maand"></svg>
  </div>

  <div class="card">
    <h2>Verzonden e-mails per maand</h2>
    <p class="cap">Totaal afgeleverde e-mails.</p>
    <svg id="volume" viewBox="0 0 400 300" role="img" aria-label="Verzonden e-mails per maand"></svg>
  </div>

  <div class="card">
    <h2>Engagement-trechter</h2>
    <p class="cap">Van verzonden tot geklikt, alle campagnes in beeld samen.</p>
    <svg id="funnel" viewBox="0 0 400 300" role="img" aria-label="Engagement trechter"></svg>
  </div>

  <div class="card full">
    <h2>Top campagnes op open%</h2>
    <p class="cap">Hoogst scorende campagnes binnen de selectie (min. 500 afgeleverd).</p>
    <svg id="top" viewBox="0 0 800 360" role="img" aria-label="Top campagnes op open percentage"></svg>
  </div>

  <div class="card full">
    <h2>Alle campagnes</h2>
    <p class="cap">Klik op een kolomkop om te sorteren. Dit is de volledige tabel achter de grafieken.</p>
    <div class="tblwrap"><table id="tbl"></table></div>
  </div>
</div>

<div class="foot" id="foot"></div>
<div class="tip" id="tip"></div>

<script>
const PAYLOAD = /*__DATA__*/null;
const M = PAYLOAD.monthsNl;
const ALL = PAYLOAD.campaigns;
const tip = document.getElementById('tip');
const fmt = n => n.toLocaleString('nl-BE');
const pct = n => n.toFixed(1).replace('.', ',') + '%';
function monthLabel(key){ const [y,m]=key.split('-'); return M[+m]+" '"+y.slice(2); }

let state = { range:'all', q:'' };

function inRange(c){
  if(state.range==='all') return true;
  const now = new Date(PAYLOAD.campaigns[PAYLOAD.campaigns.length-1].date);
  const d = new Date(c.date);
  if(state.range==='y2026') return c.date >= '2026-01-01';
  const days = {d90:90,d30:30}[state.range];
  const cutoff = new Date(now); cutoff.setDate(cutoff.getDate()-days);
  return d >= cutoff;
}
function scope(){
  const q = state.q.trim().toLowerCase();
  return ALL.filter(c => inRange(c) && (!q || c.name.toLowerCase().includes(q)));
}

function showTip(html, x, y){
  tip.innerHTML = html;
  tip.style.opacity = 1;
  const r = tip.getBoundingClientRect();
  let px = x + 14, py = y + 14;
  if(px + r.width > innerWidth-8) px = x - r.width - 14;
  if(py + r.height > innerHeight-8) py = y - r.height - 14;
  tip.style.left = px+'px'; tip.style.top = py+'px';
}
function hideTip(){ tip.style.opacity = 0; }

// ---------- KPI ----------
function renderKpis(cs){
  const sent = cs.reduce((a,c)=>a+c.delivered,0);
  const wOpen = sent ? cs.reduce((a,c)=>a+c.openRate*c.delivered,0)/sent : 0;
  const clicks = cs.reduce((a,c)=>a+c.clicks,0);
  const wClick = sent ? clicks/sent*100 : 0;
  const unsub = cs.reduce((a,c)=>a+c.unsub,0);
  const K = [
    ['Campagnes', fmt(cs.length), ''],
    ['Afgeleverd', fmt(sent), 'e-mails in beeld'],
    ['Gem. open %', pct(wOpen), 'gewogen'],
    ['Gem. klik %', pct(wClick), fmt(clicks)+' unieke clicks'],
    ['Uitschrijvingen', fmt(unsub), sent? (unsub/sent*100).toFixed(2).replace('.',',')+'% van verzonden':''],
  ];
  document.getElementById('kpis').innerHTML = K.map(k=>
    `<div class="kpi"><div class="n">${k[1]}</div><div class="l">${k[0]}</div><div class="d">${k[2]}</div></div>`
  ).join('');
}

// ---------- monthly aggregate ----------
function byMonth(cs){
  const m = {};
  cs.forEach(c=>{
    (m[c.month] ??= {month:c.month, delivered:0, opensW:0, clicks:0, n:0});
    const o=m[c.month]; o.delivered+=c.delivered; o.opensW+=c.openRate*c.delivered;
    o.clicks+=c.clicks; o.n++;
  });
  return Object.values(m).sort((a,b)=>a.month<b.month?-1:1).map(o=>({
    month:o.month, n:o.n, delivered:o.delivered,
    open:o.delivered? o.opensW/o.delivered:0,
    click:o.delivered? o.clicks/o.delivered*100:0
  }));
}

// ---------- TREND (2-series line, shared % axis) ----------
function renderTrend(cs){
  const svg=document.getElementById('trend'); const W=800,H=300;
  const mx={l:44,r:16,t:12,b:34}; const iw=W-mx.l-mx.r, ih=H-mx.t-mx.b;
  const d=byMonth(cs);
  if(d.length===0){ svg.innerHTML=empty(W,H); return; }
  const maxY=Math.max(10, Math.ceil(Math.max(...d.map(x=>Math.max(x.open,x.click)))/10)*10);
  const X=i=> mx.l + (d.length===1? iw/2 : i/(d.length-1)*iw);
  const Y=v=> mx.t + ih - v/maxY*ih;
  let s='';
  // grid + y ticks
  for(let t=0;t<=maxY;t+=maxY/5){
    const y=Y(t); s+=`<line class="axis" x1="${mx.l}" y1="${y}" x2="${W-mx.r}" y2="${y}"/>`;
    s+=`<text class="axis" x="${mx.l-8}" y="${y+4}" text-anchor="end">${t}%</text>`;
  }
  // x labels (thin)
  const step=Math.ceil(d.length/8);
  d.forEach((p,i)=>{ if(i%step===0||i===d.length-1)
    s+=`<text class="axis" x="${X(i)}" y="${H-mx.b+18}" text-anchor="middle">${monthLabel(p.month)}</text>`; });
  const path=(key,col)=>{
    let p='';
    d.forEach((x,i)=> p+=(i?'L':'M')+X(i)+' '+Y(x[key]));
    s+=`<path d="${p}" fill="none" stroke="${col}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
    d.forEach((x,i)=> s+=`<circle cx="${X(i)}" cy="${Y(x[key])}" r="4" fill="${col}" stroke="var(--surface)" stroke-width="2"/>`);
  };
  path('open','var(--s1)'); path('click','var(--s2)');
  // end labels (direct)
  const last=d[d.length-1];
  s+=`<text class="lbl" x="${X(d.length-1)+8}" y="${Y(last.open)+4}">${pct(last.open)}</text>`;
  s+=`<text class="lbl" x="${X(d.length-1)+8}" y="${Y(last.click)+4}">${pct(last.click)}</text>`;
  // crosshair hit layer
  s+=`<line id="cross" x1="0" y1="${mx.t}" x2="0" y2="${mx.t+ih}" stroke="var(--baseline)" stroke-width="1" opacity="0"/>`;
  s+=`<rect x="${mx.l}" y="${mx.t}" width="${iw}" height="${ih}" fill="transparent" id="trendhit"/>`;
  svg.innerHTML=s;
  const hit=svg.querySelector('#trendhit'), cross=svg.querySelector('#cross');
  hit.addEventListener('pointermove',e=>{
    const pt=localX(svg,e,W); let i=Math.round((pt-mx.l)/(iw||1)*(d.length-1));
    i=Math.max(0,Math.min(d.length-1,i)); const p=d[i];
    cross.setAttribute('x1',X(i)); cross.setAttribute('x2',X(i)); cross.setAttribute('opacity',1);
    showTip(`<div class="tv">${monthLabel(p.month)}</div>
      <div class="tr"><i style="background:var(--s1)"></i>Open <b>${pct(p.open)}</b></div>
      <div class="tr"><i style="background:var(--s2)"></i>Klik <b>${pct(p.click)}</b></div>
      <div class="tr">Campagnes <b>${p.n}</b></div>
      <div class="tr">Afgeleverd <b>${fmt(p.delivered)}</b></div>`, e.clientX, e.clientY);
  });
  hit.addEventListener('pointerleave',()=>{cross.setAttribute('opacity',0);hideTip();});
}

// ---------- VOLUME (columns, sequential) ----------
function renderVolume(cs){
  const svg=document.getElementById('volume'); const W=400,H=300;
  const mx={l:46,r:10,t:12,b:34}; const iw=W-mx.l-mx.r, ih=H-mx.t-mx.b;
  const d=byMonth(cs);
  if(!d.length){svg.innerHTML=empty(W,H);return;}
  const maxY=Math.max(...d.map(x=>x.delivered))||1;
  const bw=Math.min(24, iw/d.length*0.7);
  const X=i=> mx.l + (i+0.5)/d.length*iw;
  const Y=v=> mx.t + ih - v/maxY*ih;
  let s='';
  for(let t=0;t<=4;t++){ const val=maxY*t/4, y=Y(val);
    s+=`<line class="axis" x1="${mx.l}" y1="${y}" x2="${W-mx.r}" y2="${y}"/>`;
    s+=`<text class="axis" x="${mx.l-8}" y="${y+4}" text-anchor="end">${short(val)}</text>`; }
  const step=Math.ceil(d.length/6);
  d.forEach((p,i)=>{
    const x=X(i)-bw/2, y=Y(p.delivered), h=mx.t+ih-y;
    s+=`<rect x="${x}" y="${y}" width="${bw}" height="${h}" rx="4" fill="var(--seq)" class="vbar" data-i="${i}"/>`;
    if(i%step===0||i===d.length-1)
      s+=`<text class="axis" x="${X(i)}" y="${H-mx.b+18}" text-anchor="middle">${monthLabel(p.month)}</text>`;
  });
  s+=`<line class="baseline" x1="${mx.l}" y1="${mx.t+ih}" x2="${W-mx.r}" y2="${mx.t+ih}"/>`;
  svg.innerHTML=s;
  svg.querySelectorAll('.vbar').forEach(b=>{
    const p=d[+b.dataset.i];
    b.addEventListener('pointermove',e=>{ b.style.opacity=.8;
      showTip(`<div class="tv">${monthLabel(p.month)}</div>
        <div class="tr">Afgeleverd <b>${fmt(p.delivered)}</b></div>
        <div class="tr">Campagnes <b>${p.n}</b></div>`, e.clientX,e.clientY);});
    b.addEventListener('pointerleave',()=>{b.style.opacity=1;hideTip();});
  });
}

// ---------- FUNNEL (ordinal horizontal) ----------
function renderFunnel(cs){
  const svg=document.getElementById('funnel'); const W=400,H=300;
  const sent=cs.reduce((a,c)=>a+c.sent,0);
  const deliv=cs.reduce((a,c)=>a+c.delivered,0);
  const views=cs.reduce((a,c)=>a+c.views,0);
  const clicks=cs.reduce((a,c)=>a+c.clicks,0);
  const steps=[['Verzonden',sent,'#9ec5f4'],['Afgeleverd',deliv,'#5598e7'],
               ['Geopend',views,'#2a78d6'],['Geklikt',clicks,'#184f95']];
  const base=steps[0][1]||1;
  if(!deliv){svg.innerHTML=empty(W,H);return;}
  const mx={l:86,r:64,t:14,b:10}; const iw=W-mx.l-mx.r;
  const bh=44, gap=(H-mx.t-mx.b-bh*4)/3;
  let s='';
  steps.forEach((st,i)=>{
    const y=mx.t+i*(bh+gap), w=Math.max(2, st[1]/base*iw);
    s+=`<rect x="${mx.l}" y="${y}" width="${w}" height="${bh-6}" rx="4" fill="${st[2]}" class="fbar" data-i="${i}"/>`;
    s+=`<text class="lbl2" x="${mx.l-10}" y="${y+bh/2}" text-anchor="end">${st[0]}</text>`;
    s+=`<text class="lbl" x="${mx.l+w+8}" y="${y+bh/2}">${fmt(st[1])}</text>`;
    const p=(st[1]/base*100); const pv=(st[1]/deliv*100);
    s+=`<text class="lbl2" x="${mx.l+w+8}" y="${y+bh/2+13}">${i===0?'100%':pct(p)}${i>=2?' · '+pct(pv)+' v. afgel.':''}</text>`;
  });
  svg.innerHTML=s;
  svg.querySelectorAll('.fbar').forEach(b=>{ const st=steps[+b.dataset.i];
    b.addEventListener('pointermove',e=>{b.style.opacity=.8;
      showTip(`<div class="tv">${st[0]}</div><div class="tr">Aantal <b>${fmt(st[1])}</b></div>
        <div class="tr">Van verzonden <b>${pct(st[1]/base*100)}</b></div>`,e.clientX,e.clientY);});
    b.addEventListener('pointerleave',()=>{b.style.opacity=1;hideTip();});
  });
}

// ---------- TOP campaigns (horizontal bars, emphasis) ----------
function renderTop(cs){
  const svg=document.getElementById('top'); const W=800;
  const list=cs.filter(c=>c.delivered>=500).slice().sort((a,b)=>b.openRate-a.openRate).slice(0,12);
  const H=Math.max(120, list.length*28+30);
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  if(!list.length){svg.innerHTML=empty(W,H);return;}
  const mx={l:300,r:60,t:8,b:20}; const iw=W-mx.l-mx.r;
  const maxY=Math.max(...list.map(c=>c.openRate));
  const bh=20, gap=8;
  let s='';
  list.forEach((c,i)=>{
    const y=mx.t+i*(bh+gap), w=Math.max(2,c.openRate/maxY*iw);
    const col=i===0?'var(--accent)':'var(--seq)';
    const short=c.name.length>44?c.name.slice(0,43)+'…':c.name;
    s+=`<text class="lbl2" x="${mx.l-10}" y="${y+bh/2+4}" text-anchor="end">${escapeXml(short)}</text>`;
    s+=`<rect x="${mx.l}" y="${y}" width="${w}" height="${bh}" rx="4" fill="${col}" class="tbar" data-i="${i}"/>`;
    s+=`<text class="lbl" x="${mx.l+w+8}" y="${y+bh/2+4}">${pct(c.openRate)}</text>`;
  });
  svg.innerHTML=s;
  svg.querySelectorAll('.tbar').forEach(b=>{ const c=list[+b.dataset.i];
    b.addEventListener('pointermove',e=>{b.style.opacity=.8;
      showTip(`<div class="tv">${escapeHtml(c.name)}</div>
        <div class="tr">Open <b>${pct(c.openRate)}</b></div>
        <div class="tr">Klik <b>${pct(c.clickRate)}</b></div>
        <div class="tr">Afgeleverd <b>${fmt(c.delivered)}</b></div>
        <div class="tr">Datum <b>${c.date}</b></div>`,e.clientX,e.clientY);});
    b.addEventListener('pointerleave',()=>{b.style.opacity=1;hideTip();});
  });
}

// ---------- TABLE (twin) ----------
let sortKey='date', sortAsc=false;
function renderTable(cs){
  const cols=[['name','Campagne'],['date','Datum'],['delivered','Afgeleverd'],
    ['openRate','Open %'],['clickRate','Klik %'],['clicks','Clicks'],
    ['unsub','Uitschr.'],['bounces','Bounces']];
  const rows=cs.slice().sort((a,b)=>{
    let x=a[sortKey],y=b[sortKey];
    if(typeof x==='string'){return sortAsc?x.localeCompare(y):y.localeCompare(x);}
    return sortAsc?x-y:y-x;
  });
  let s='<thead><tr>'+cols.map(c=>`<th data-k="${c[0]}">${c[1]}</th>`).join('')+'</tr></thead><tbody>';
  rows.forEach(c=>{
    s+=`<tr><td title="${escapeHtml(c.name)}">${escapeHtml(c.name)}</td><td>${c.date}</td>
      <td>${fmt(c.delivered)}</td><td>${pct(c.openRate)}</td><td>${pct(c.clickRate)}</td>
      <td>${fmt(c.clicks)}</td><td>${fmt(c.unsub)}</td><td>${fmt(c.bounces)}</td></tr>`;
  });
  s+='</tbody>';
  const tbl=document.getElementById('tbl'); tbl.innerHTML=s;
  tbl.querySelectorAll('th').forEach(th=>th.addEventListener('click',()=>{
    const k=th.dataset.k; if(k===sortKey)sortAsc=!sortAsc; else{sortKey=k;sortAsc=false;}
    renderTable(scope());
  }));
}

// ---------- helpers ----------
function short(v){ return v>=1000? (v/1000).toFixed(v>=10000?0:1).replace('.',',')+'k' : Math.round(v); }
function empty(W,H){ return `<text x="${W/2}" y="${H/2}" text-anchor="middle" fill="var(--muted)" font-size="13">Geen campagnes in deze selectie</text>`; }
function localX(svg,e,W){ const r=svg.getBoundingClientRect(); return (e.clientX-r.left)/r.width*W; }
function escapeXml(s){return String(s).replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));}
function escapeHtml(s){return String(s).replace(/[<>&"]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]));}

// ---------- orchestration ----------
function renderAll(){
  const cs=scope();
  document.getElementById('scopecount').textContent = cs.length+' van '+ALL.length+' campagnes';
  renderKpis(cs); renderTrend(cs); renderVolume(cs); renderFunnel(cs); renderTop(cs); renderTable(cs);
}
function buildBar(){
  const ranges=[['all','Alles'],['y2026','2026'],['d90','90 dagen'],['d30','30 dagen']];
  const box=document.getElementById('ranges');
  box.innerHTML=ranges.map(r=>`<button data-r="${r[0]}" class="${r[0]===state.range?'on':''}">${r[1]}</button>`).join('');
  box.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{
    state.range=b.dataset.r;
    box.querySelectorAll('button').forEach(x=>x.classList.toggle('on',x===b));
    renderAll();
  }));
  let t; document.getElementById('search').addEventListener('input',e=>{
    clearTimeout(t); t=setTimeout(()=>{state.q=e.target.value;renderAll();},150);
  });
}
document.getElementById('subtitle').textContent =
  'Laatste sync: '+PAYLOAD.lastSync+'  ·  rapport: '+PAYLOAD.generated+'  ·  '+ALL.length+' campagnes met statistieken';
document.getElementById('foot').textContent =
  'Bron: brevo.db (lokaal). Open% = Brevo-maatstaf incl. Apple Mail Privacy. Klik% = unieke clicks / afgeleverd. Ververs met: python3 dashboard.py';
buildBar();
addEventListener('resize',()=>renderAll());
renderAll();
</script>
</body></html>"""


if __name__ == "__main__":
    main()
