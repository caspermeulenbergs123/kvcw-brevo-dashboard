#!/usr/bin/env python3
"""
Brevo -> SQLite ingest.

Leest JSON-payloads uit ./payloads/ (aangeleverd door Claude via de Brevo-
connectie) en schrijft ze weg naar brevo.db. Volledig deterministisch en
idempotent: opnieuw draaien werkt bestaande rijen bij op basis van id.

Payload-bestandsnamen (glob):
  payloads/contacts*.json   -> {"contacts": [...]}
  payloads/lists*.json      -> {"lists": [...]}
  payloads/segments*.json   -> {"segments": [...]}
  payloads/campaigns*.json  -> {"campaigns": [...]}

Meerdere bestanden per soort mag (bv. paginering: contacts_00.json,
contacts_01.json ...).

Gebruik:
  python3 ingest.py               # ingest alle payloads/*.json
  python3 ingest.py --keep        # payloads niet verplaatsen na afloop
"""
import argparse
import glob
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "brevo.db")
SCHEMA = os.path.join(HERE, "schema.sql")
PAYLOADS = os.path.join(HERE, "payloads")
ARCHIVE = os.path.join(HERE, "payloads", "_done")


def now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load(pattern):
    """Alle records uit alle matchende payload-bestanden onder één key."""
    rows = []
    files = sorted(glob.glob(os.path.join(PAYLOADS, pattern)))
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        # accepteer zowel {"key":[...]} als een kale lijst
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    rows.extend(v)
                    break
        elif isinstance(data, list):
            rows.extend(data)
    return rows, files


def upsert_contacts(cur, rows, ts):
    n = 0
    for c in rows:
        attrs = c.get("attributes") or {}
        cur.execute(
            """INSERT OR REPLACE INTO contacts
               (id,email,firstname,lastname,email_blacklisted,sms_blacklisted,
                whatsapp_blacklisted,created_at,modified_at,list_ids,attributes,synced_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                c.get("id"),
                c.get("email"),
                attrs.get("FIRSTNAME"),
                attrs.get("LASTNAME"),
                1 if c.get("emailBlacklisted") else 0,
                1 if c.get("smsBlacklisted") else 0,
                1 if c.get("whatsappBlacklisted") else 0,
                c.get("createdAt"),
                c.get("modifiedAt"),
                json.dumps(c.get("listIds") or []),
                json.dumps(attrs, ensure_ascii=False),
                ts,
            ),
        )
        n += 1
    return n


def upsert_lists(cur, rows, ts):
    n = 0
    for l in rows:
        cur.execute(
            """INSERT OR REPLACE INTO lists
               (id,name,folder_id,unique_subscribers,synced_at)
               VALUES (?,?,?,?,?)""",
            (l.get("id"), l.get("name"), l.get("folderId"),
             l.get("uniqueSubscribers", 0), ts),
        )
        n += 1
    return n


def upsert_segments(cur, rows, ts):
    n = 0
    for s in rows:
        cur.execute(
            """INSERT OR REPLACE INTO segments
               (id,name,category_name,updated_at,synced_at)
               VALUES (?,?,?,?,?)""",
            (s.get("id"), s.get("segmentName"), s.get("categoryName"),
             s.get("updatedAt"), ts),
        )
        n += 1
    return n


def upsert_campaigns(cur, rows, ts):
    n = 0
    for c in rows:
        sender = c.get("sender") or {}
        cur.execute(
            """INSERT OR REPLACE INTO campaigns
               (id,name,subject,type,status,sender_email,sender_name,tag,
                scheduled_at,sent_date,recipients,synced_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                c.get("id"), c.get("name"), c.get("subject"), c.get("type"),
                c.get("status"), sender.get("email"), sender.get("name"),
                c.get("tag"), c.get("scheduledAt"), c.get("sentDate"),
                json.dumps(c.get("recipients") or {}, ensure_ascii=False), ts,
            ),
        )
        g = (((c.get("statistics") or {}).get("globalStats")) or {})
        if g:
            cur.execute(
                """INSERT OR REPLACE INTO campaign_stats
                   (campaign_id,sent,delivered,soft_bounces,hard_bounces,
                    unique_views,viewed,unique_clicks,clickers,unsubscriptions,
                    complaints,opens_rate,synced_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    c.get("id"), g.get("sent"), g.get("delivered"),
                    g.get("softBounces"), g.get("hardBounces"),
                    g.get("uniqueViews"), g.get("viewed"), g.get("uniqueClicks"),
                    g.get("clickers"), g.get("unsubscriptions"),
                    g.get("complaints"), g.get("opensRate"), ts,
                ),
            )
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true",
                    help="payloads niet archiveren na ingest")
    args = ap.parse_args()

    ts = now()
    conn = sqlite3.connect(DB)
    with open(SCHEMA, "r", encoding="utf-8") as fh:
        conn.executescript(fh.read())
    cur = conn.cursor()

    counts = {"contacts": 0, "lists": 0, "segments": 0, "campaigns": 0}
    used_files = []

    contacts, f = load("contacts*.json"); used_files += f
    counts["contacts"] = upsert_contacts(cur, contacts, ts)

    lists, f = load("lists*.json"); used_files += f
    counts["lists"] = upsert_lists(cur, lists, ts)

    segments, f = load("segments*.json"); used_files += f
    counts["segments"] = upsert_segments(cur, segments, ts)

    campaigns, f = load("campaigns*.json"); used_files += f
    counts["campaigns"] = upsert_campaigns(cur, campaigns, ts)

    scope = ",".join(k for k, v in counts.items() if v) or "leeg"
    cur.execute(
        """INSERT INTO sync_runs (ran_at,scope,contacts,lists,segments,campaigns,note)
           VALUES (?,?,?,?,?,?,?)""",
        (ts, scope, counts["contacts"], counts["lists"],
         counts["segments"], counts["campaigns"],
         f"{len(used_files)} payload-bestand(en)"),
    )
    conn.commit()

    # totalen tonen
    for t in ("contacts", "lists", "segments", "campaigns", "campaign_stats"):
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<16} {n:>7} rijen in db")
    conn.close()

    print("\nIngest van deze run:")
    for k, v in counts.items():
        print(f"  +{v} {k}")

    if used_files and not args.keep:
        os.makedirs(ARCHIVE, exist_ok=True)
        for f in used_files:
            os.replace(f, os.path.join(ARCHIVE, os.path.basename(f)))
        print(f"\n{len(used_files)} payload(s) verplaatst naar payloads/_done/")
    elif not used_files:
        print("\nGeen payloads gevonden in payloads/ — niets te doen.")


if __name__ == "__main__":
    main()
