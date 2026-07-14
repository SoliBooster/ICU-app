# ================= 参考范围迁移脚本 =================
# 为现有数据库添加 indicator_refs 表
"""
用法：python3 migrate_refs.py
"""
from db import get_db, use_mysql, placeholder

def migrate():
    conn = get_db()
    cur = conn.cursor()
    p = placeholder()

    if use_mysql():
        cur.execute("""
            CREATE TABLE IF NOT EXISTS indicator_refs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sheet_key VARCHAR(50) NOT NULL,
                col_key VARCHAR(50) NOT NULL,
                ref_min DOUBLE,
                ref_max DOUBLE,
                UNIQUE KEY uq_ref (sheet_key, col_key)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS indicator_refs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sheet_key TEXT NOT NULL,
                col_key TEXT NOT NULL,
                ref_min REAL,
                ref_max REAL,
                UNIQUE(sheet_key, col_key)
            )
        """)

    conn.commit()
    conn.close()
    print("✅ indicator_refs 表已就绪")

if __name__ == '__main__':
    migrate()
