#!/usr/bin/env python3
"""Verkennende analyse van brevo.db: categoriseren + aggregaten, om het dashboard-ontwerp op echte cijfers te baseren."""
import re, sqlite3, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
conn = sqlite3.connect(os.path.join(HERE, "brevo.db"))
rows = conn.execute("""
  SELECT c.name, c.sent_date, s.sent, s.delivered, s.unique_views, s.unique_clicks,
         s.unsubscriptions, s.soft_bounces, s.hard_bounces, s.opens_rate, s.complaints
  FROM campaigns c JOIN campaign_stats s ON s.campaign_id=c.id
  WHERE s.delivered>0 ORDER BY c.sent_date""").fetchall()

def classify(n):
    n = (n or "").lower()
    if "personeel" in n: return "Personeel"
    if re.search(r"beats|bites|steak|ribbekes|tapas|brunch|village|24-uur|santa|preparty|party|paaseieren|communie|themacafe|valentijn|fandag", n): return "Events & F&B"
    if re.search(r"shirt|fanshop|solden|tshirt|goodiebag|kalender|matchworn", n): return "Fanshop & merch"
    if re.search(r"\babo\b|abonnement|renewal|verleng|early ?bird|member|mini-abo", n): return "Abonnementen"
    if re.search(r"md-|ticket|presale|combiticket|kvcw-|kvc westerlo -|playoff|play-off", n): return "Ticketing"
    if re.search(r"kids|westel|stage|jobbeurs|academy|rbfa|u21|giveaway|prijsvraag", n): return "Jeugd & club"
    return "Overig"

cats = collections.defaultdict(lambda: {"n":0,"deliv":0,"views":0,"clicks":0,"unsub":0,"opensW":0})
months = collections.defaultdict(lambda: {"n":0,"deliv":0,"opensW":0,"clicks":0})
dow = collections.defaultdict(lambda: {"n":0,"opensW":0,"deliv":0})
DOWN = ["ma","di","wo","do","vr","za","zo"]
import datetime
overhundred=[]; allc=[]
for (name,sd,sent,deliv,views,clicks,unsub,sb,hb,orate,compl) in rows:
    cat = classify(name)
    c = cats[cat]; c["n"]+=1; c["deliv"]+=deliv; c["views"]+=views; c["clicks"]+=clicks; c["unsub"]+=unsub; c["opensW"]+=(orate or 0)*deliv
    mk = (sd or "")[:7]
    m = months[mk]; m["n"]+=1; m["deliv"]+=deliv; m["opensW"]+=(orate or 0)*deliv; m["clicks"]+=clicks
    try:
        dt = datetime.date.fromisoformat((sd or "")[:10]); d=dow[dt.weekday()]; d["n"]+=1; d["opensW"]+=(orate or 0)*deliv; d["deliv"]+=deliv
    except: pass
    if (orate or 0) > 100: overhundred.append((name, orate, deliv))
    allc.append((name,cat,deliv,orate or 0, round(clicks/deliv*100,2) if deliv else 0, unsub))

print("=== CATEGORIEËN ===")
print(f"{'categorie':<18}{'#':>4}{'afgeleverd':>12}{'gem.open%':>11}{'gem.klik%':>11}{'unsub':>8}")
for cat,c in sorted(cats.items(), key=lambda x:-x[1]["deliv"]):
    o = c["opensW"]/c["deliv"] if c["deliv"] else 0
    cl = c["clicks"]/c["deliv"]*100 if c["deliv"] else 0
    print(f"{cat:<18}{c['n']:>4}{c['deliv']:>12,}{o:>10.1f}%{cl:>10.2f}%{c['unsub']:>8,}")

print("\n=== PER WEEKDAG (verzenddag) ===")
for wd in range(7):
    if wd in dow and dow[wd]["deliv"]:
        d=dow[wd]; print(f"{DOWN[wd]}: {d['n']:>3} campagnes, gem.open {d['opensW']/d['deliv']:.1f}%")

print("\n=== TOP 8 open% (min 5000 afgeleverd) ===")
for name,cat,deliv,orate,cr,unsub in sorted([a for a in allc if a[2]>=5000], key=lambda x:-x[3])[:8]:
    print(f"  {orate:5.1f}%  {deliv:>7,}  [{cat}]  {name[:50]}")

print("\n=== LAAGSTE 5 open% (min 5000) ===")
for name,cat,deliv,orate,cr,unsub in sorted([a for a in allc if a[2]>=5000], key=lambda x:x[3])[:5]:
    print(f"  {orate:5.1f}%  {deliv:>7,}  [{cat}]  {name[:50]}")

print("\n=== TOP 5 klik% (min 5000) ===")
for name,cat,deliv,orate,cr,unsub in sorted([a for a in allc if a[2]>=5000], key=lambda x:-x[4])[:5]:
    print(f"  {cr:5.2f}%  {deliv:>7,}  [{cat}]  {name[:50]}")

print(f"\n=== DATAKWALITEIT ===\nCampagnes met open% > 100 (Apple MPP / mini-lijsten): {len(overhundred)}")
for n,o,d in overhundred[:6]: print(f"  {o:.1f}%  (afgeleverd {d})  {n[:45]}")
tot_d=sum(c['deliv'] for c in cats.values()); tot_o=sum(c['opensW'] for c in cats.values())
print(f"\nTotaal campagnes: {len(rows)} | totaal afgeleverd: {tot_d:,} | globaal gem. open%: {tot_o/tot_d:.1f}%")
print(f"Maanden met data: {len(months)} ({min(months)} → {max(months)})")
conn.close()
