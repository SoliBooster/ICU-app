# ================= 数据库操作工具 =================
# 支持 SQLite（本地开发）和 MySQL（生产部署）
# 当 config.MYSQL_HOST 设置了值，自动使用 MySQL；否则使用 SQLite

import sqlite3
import pymysql
import pymysql.cursors
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB, DB_PATH


def use_mysql():
    """判断是否使用 MySQL"""
    return bool(MYSQL_HOST)


def get_db():
    """获取数据库连接"""
    if use_mysql():
        return pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DB,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def query_one(sql, args=None):
    """执行查询，只取一条结果"""
    conn = get_db()
    try:
        if use_mysql():
            with conn.cursor() as cur:
                cur.execute(sql, args or ())
                return cur.fetchone()
        else:
            cur = conn.cursor()
            cur.execute(sql, args or ())
            return cur.fetchone()
    finally:
        conn.close()


def query_all(sql, args=None):
    """执行查询，取出所有结果"""
    conn = get_db()
    try:
        if use_mysql():
            with conn.cursor() as cur:
                cur.execute(sql, args or ())
                return cur.fetchall()
        else:
            cur = conn.cursor()
            cur.execute(sql, args or ())
            return cur.fetchall()
    finally:
        conn.close()


def execute(sql, args=None):
    """执行增、删、改操作"""
    conn = get_db()
    try:
        if use_mysql():
            with conn.cursor() as cur:
                cur.execute(sql, args or ())
                conn.commit()
                return cur.lastrowid
        else:
            cur = conn.cursor()
            cur.execute(sql, args or ())
            conn.commit()
            return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def dictify(row):
    """将数据库行转为普通字典"""
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return dict(row)


def dictify_all(rows):
    """将一批行转为字典列表"""
    return [dictify(r) for r in rows]


def placeholder():
    """返回 SQL 占位符：MySQL 用 %s，SQLite 用 ?"""
    return '%s' if use_mysql() else '?'


def placeholder_list(n):
    """返回 n 个占位符的列表"""
    p = placeholder()
    return [p] * n
