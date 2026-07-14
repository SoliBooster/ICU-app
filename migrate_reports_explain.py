# ================= 报告 + 指标解释 迁移脚本 =================
# 为现有数据库新增：
# 1. reports 表 — 图片报告
# 2. indicator_explanations 表 — 指标名词解释
"""
用法：python migrate_reports_explain.py
"""
from db import get_db, use_mysql, placeholder


def migrate():
    conn = get_db()
    cur = conn.cursor()
    p = placeholder()

    # ===== 1. 创建 reports 表 =====
    if use_mysql():
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INT AUTO_INCREMENT PRIMARY KEY,
                patient_id INT NOT NULL DEFAULT 1,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                image_path VARCHAR(500) NOT NULL,
                report_date DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL DEFAULT 1,
                title TEXT NOT NULL,
                description TEXT,
                image_path TEXT NOT NULL,
                report_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    print("✅ reports 表已就绪")

    # ===== 2. 创建 indicator_explanations 表 =====
    if use_mysql():
        cur.execute("""
            CREATE TABLE IF NOT EXISTS indicator_explanations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                sheet_key VARCHAR(50) NOT NULL,
                col_key VARCHAR(50) NOT NULL,
                content TEXT,
                images TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_explain (sheet_key, col_key)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS indicator_explanations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sheet_key TEXT NOT NULL,
                col_key TEXT NOT NULL,
                content TEXT,
                images TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sheet_key, col_key)
            )
        """)
    print("✅ indicator_explanations 表已就绪")

    conn.commit()
    conn.close()
    print("✅ 迁移完成")


if __name__ == '__main__':
    migrate()
