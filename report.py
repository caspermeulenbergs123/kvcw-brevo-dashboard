#!/usr/bin/env python3
"""
Genereert een leesbaar HTML-dashboard uit brevo.db.

Gebruik:
  python3 report.py        # schrijft report.html

Herbruikbaar: draai opnieuw na een sync om het dashboard te verversen.
"""
import html
import json
import os
import sqlite3
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "brevo.db")
OUT = os.path.join(HERE, "report.html")


def q(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def esc(v):
    return html.escape("" if v is None else str(v))


def table(cols, rows, numeric_from=1):
    """Bouw een sorteerbare tabel. Kolommen vanaf numeric_from worden als getal gesorteerd."""
    thead = "".join(
        f'<th data-num="{1 if i >= numeric_from else 0}">{esc(c)}</th>'
        for i, c in enumerate(cols)
    )
    body = []
    for r in rows:
        tds = "".join(f"<td>{esc(v)}</td>" for v in r)
        body.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{thead}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def main():
    if not os.path.exists(DB):
        raise SystemExit("brevo.db bestaat nog niet. Draai eerst een sync.")
    conn = sqlite3.connect(DB)

    # KPI's
    def scalar(sql):
        return q(conn, sql)[1][0][0]

    kpi = {
        "Contacten": scalar("SELECT COUNT(*) FROM contacts"),
        "Lijsten": scalar("SELECT COUNT(*) FROM lists"),
        "Segmenten": scalar("SELECT COUNT(*) FROM segments"),
        "Campagnes": scalar("SELECT COUNT(*) FROM campaigns"),
    }
    last_sync = scalar("SELECT MAX(ran_at) FROM sync_runs") or "nog niet"

    # Campagnes met stats
    c_cols, c_rows = q(conn, """
        SELECT c.name AS campagne, c.sent_date AS verzonden,
               s.sent AS verzonden_aan, s.delivered AS afgeleverd,
               ROUND(s.opens_rate,1) AS open_pct,
               s.unique_clicks AS unieke_clicks,
               s.unsubscriptions AS uitschr, s.hard_bounces AS hard_bounces
        FROM campaigns c LEFT JOIN campaign_stats s ON s.campaign_id = c.id
        ORDER BY c.sent_date DESC
    """)

    l_cols, l_rows = q(conn, """
        SELECT name AS lijst, unique_subscribers AS contacten, folder_id AS map
        FROM lists ORDER BY unique_subscribers DESC
    """)

    s_cols, s_rows = q(conn, """
        SELECT name AS segment, category_name AS categorie, updated_at AS bijgewerkt
        FROM segments ORDER BY updated_at DESC
    """)

    run_cols, run_rows = q(conn, """
        SELECT ran_at AS wanneer, scope, contacts, lists AS lijsten,
               segments AS segmenten, campaigns AS campagnes
        FROM sync_runs ORDER BY id DESC LIMIT 15
    """)
    conn.close()

    gen = datetime.now(timezone.utc).astimezone().strftime("%d-%m-%Y %H:%M")

    kpi_html = "".join(
        f'<div class="kpi"><span class="n">{v:,}</span><span class="l">{k}</span></div>'.replace(",", ".")
        for k, v in kpi.items()
    )

    doc = f"""<!doctype html>
<html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brevo dashboard - KVC Westerlo</title>
<style>
  :root {{ --bg:#0f1115; --card:#171a21; --line:#262b36; --txt:#e6e9ef; --mut:#8b93a3; --acc:#ffd200; --acc2:#4f8cff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:var(--bg); color:var(--txt); }}
  header {{ padding:28px 32px 8px; }}
  h1 {{ margin:0; font-size:22px; letter-spacing:-.02em; }}
  .sub {{ color:var(--mut); font-size:13px; margin-top:4px; }}
  .kpis {{ display:flex; gap:14px; flex-wrap:wrap; padding:20px 32px; }}
  .kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 20px; min-width:140px; }}
  .kpi .n {{ display:block; font-size:28px; font-weight:700; letter-spacing:-.02em; }}
  .kpi .l {{ display:block; color:var(--mut); font-size:12px; text-transform:uppercase; letter-spacing:.05em; margin-top:2px; }}
  section {{ padding:8px 32px 32px; }}
  h2 {{ font-size:14px; text-transform:uppercase; letter-spacing:.06em; color:var(--mut); margin:24px 0 10px; }}
  .wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:12px; }}
  table {{ width:100%; border-collapse:collapse; font-size:13.5px; }}
  th,td {{ text-align:left; padding:9px 14px; border-bottom:1px solid var(--line); white-space:nowrap; }}
  th {{ position:sticky; top:0; background:var(--card); cursor:pointer; user-select:none; font-weight:600; }}
  th:hover {{ color:var(--acc); }}
  td:not(:first-child), th:not(:first-child) {{ text-align:right; font-variant-numeric:tabular-nums; }}
  tbody tr:hover {{ background:#1d222c; }}
  tbody tr:nth-child(even) {{ background:#141821; }}
  .hint {{ color:var(--mut); font-size:12px; margin:6px 0 0; }}
</style></head>
<body>
<header>
  <h1>Brevo dashboard <span style="color:var(--acc)">KVC Westerlo</span></h1>
  <div class="sub">Laatste sync: {esc(last_sync)} &nbsp;·&nbsp; rapport gegenereerd: {gen}</div>
</header>
<div class="kpis">{kpi_html}</div>
<section>
  <h2>Campagnes ({len(c_rows)})</h2>
  <div class="wrap">{table(c_cols, c_rows)}</div>
  <p class="hint">Klik op een kolomkop om te sorteren.</p>

  <h2>Lijsten ({len(l_rows)})</h2>
  <div class="wrap">{table(l_cols, l_rows)}</div>

  <h2>Segmenten ({len(s_rows)})</h2>
  <div class="wrap">{table(s_cols, s_rows)}</div>

  <h2>Sync-historiek</h2>
  <div class="wrap">{table(run_cols, run_rows)}</div>
</section>
<script>
document.querySelectorAll('table').forEach(function(t){{
  t.querySelectorAll('th').forEach(function(th, idx){{
    let asc = true;
    th.addEventListener('click', function(){{
      const num = th.dataset.num === '1';
      const rows = Array.from(t.tBodies[0].rows);
      rows.sort(function(a,b){{
        let x=a.cells[idx].innerText, y=b.cells[idx].innerText;
        if(num){{ x=parseFloat(x.replace(',','.'))||-Infinity; y=parseFloat(y.replace(',','.'))||-Infinity; return asc?x-y:y-x; }}
        return asc? x.localeCompare(y): y.localeCompare(x);
      }});
      rows.forEach(r=>t.tBodies[0].appendChild(r));
      asc=!asc;
    }});
  }});
}});
</script>
</body></html>"""

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"Dashboard geschreven: {OUT}")


if __name__ == "__main__":
    main()
