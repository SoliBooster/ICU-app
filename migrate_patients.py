# ================= 病人系统迁移脚本 =================
# 为现有数据库添加病人支持：
# 1. 创建 patients 表
# 2. 添加默认病人 杜桂琴（查看密码：123456）
# 3. 为所有数据表添加 patient_id 列
"""
用法：python migrate_patients.py
（兼容 SQLite 本地开发 & MySQL 生产环境）
"""
import os
import sys
from werkzeug.security import generate_password_hash
from db import get_db, use_mysql, placeholder


def migrate():
    conn = get_db()
    cur = conn.cursor()
    p = placeholder()

    # ===== 1. 创建 patients 表 =====
    if use_mysql():
        cur.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                view_password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                view_password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    print("✅ patients 表已就绪")

    # ===== 2. 种子数据：杜桂琴 =====
    if use_mysql():
        cur.execute(f"SELECT id FROM patients WHERE name={p}", ("杜桂琴",))
        row = cur.fetchone()
    else:
        cur.execute(f"SELECT id FROM patients WHERE name={p}", ("杜桂琴",))
        row = cur.fetchone()

    if not row:
        cur.execute(
            f"INSERT INTO patients(name, view_password_hash) VALUES({p},{p})",
            ("杜桂琴", generate_password_hash("123456"))
        )
        print("✅ 已创建默认患者：杜桂琴（查看密码：123456）")
    else:
        print("ℹ️  杜桂琴已存在，跳过")

    # ===== 3. 为数据表添加 patient_id 列 =====
    if use_mysql():
        cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME LIKE 't\\_%'")
        tables = [row['TABLE_NAME'] for row in cur.fetchall()]
    else:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 't\\_' ESCAPE '\\'")
        tables = [row['name'] for row in cur.fetchall()]

    if not tables:
        # MySQL 的 LIKE 转义方式不同
        if use_mysql():
            cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME LIKE 't_%'")
            tables = [row['TABLE_NAME'] for row in cur.fetchall()]
        else:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 't_%'")
            tables = [row['name'] for row in cur.fetchall()]

    added = 0
    for tname in tables:
        # 检查是否已有 patient_id 列
        if use_mysql():
            cur.execute(f"SHOW COLUMNS FROM `{tname}` LIKE 'patient_id'")
            exists = cur.fetchone()
        else:
            cur.execute(f"PRAGMA table_info({tname})")
            cols = [r['name'] for r in cur.fetchall()]
            exists = 'patient_id' in cols

        if not exists:
            if use_mysql():
                cur.execute(f"ALTER TABLE `{tname}` ADD COLUMN patient_id INT DEFAULT 1")
            else:
                cur.execute(f"ALTER TABLE {tname} ADD COLUMN patient_id INTEGER DEFAULT 1")
            added += 1
            print(f"  → 已添加 patient_id 到 {tname}")

    conn.commit()
    conn.close()
    print(f"\n✅ 迁移完成！共为 {added} 个表添加 patient_id 列")


if __name__ == '__main__':
    migrate()
