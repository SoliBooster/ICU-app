# Quick search debug
import sys
sys.path.insert(0, '/home/jarryyansir/workspace-c707c28a-9d95-41c3-995c-741268b278d8')
from db import get_db, dictify_all, dictify

conn = get_db()
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 't_%'")
tables = [r['name'] for r in cur.fetchall()]
print("Tables:", tables)

for t in tables[:1]:
    cur.execute(f"SELECT * FROM {t} LIMIT 3")
    rows = [dict(r) for r in cur.fetchall()]
    print(f"\n{t} rows:")
    for r in rows:
        print(f"  id={r['id']} label='{r['row_label']}'")

    # Test search
    q = "7"
    cur.execute(f"SELECT id, row_label FROM {t} WHERE row_label LIKE ?", (f"%{q}%",))
    hits = [dict(r) for r in cur.fetchall()]
    print(f"\nSearch '{q}' in {t}: {len(hits)} hits")
    for h in hits:
        print(f"  -> id={h['id']} label='{h['row_label']}'")

conn.close()
