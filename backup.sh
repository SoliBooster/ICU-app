#!/bin/bash
# ================= 数据库备份脚本 =================
# 用法：./backup.sh
# 建议配合 crontab 使用：0 3 * * * /root/ICU-app/backup.sh
# 备份保留最近 30 天

set -e

APP_DIR="/root/ICU-app"
BACKUP_DIR="/root/ICU-app/backups"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

# 检测是 MySQL 还是 SQLite
if [ -n "$MYSQL_HOST" ]; then
    # MySQL 备份
    BACKUP_FILE="$BACKUP_DIR/icu_mysql_$TIMESTAMP.sql.gz"
    echo "[$TIMESTAMP] 备份 MySQL..."
    mysqldump -h "$MYSQL_HOST" -P "${MYSQL_PORT:-3306}" -u "$MYSQL_USER" \
        -p"${MYSQL_PASSWORD}" "$MYSQL_DB" 2>/dev/null | gzip > "$BACKUP_FILE"
    echo "[$TIMESTAMP] ✅ MySQL 备份完成: $BACKUP_FILE"
else
    # SQLite 备份
    DB_FILE="$APP_DIR/icu.db"
    if [ -f "$DB_FILE" ]; then
        BACKUP_FILE="$BACKUP_DIR/icu_sqlite_$TIMESTAMP.db.gz"
        gzip -c "$DB_FILE" > "$BACKUP_FILE"
        echo "[$TIMESTAMP] ✅ SQLite 备份完成: $BACKUP_FILE"
    else
        echo "[$TIMESTAMP] ⚠️  数据库文件不存在: $DB_FILE"
    fi
fi

# 清理 30 天前的备份
find "$BACKUP_DIR" -name "icu_*.gz" -mtime +$RETENTION_DAYS -delete
echo "[$TIMESTAMP] 🧹 已清理 $RETENTION_DAYS 天前的备份"

# 可选：备份到远程（如 OSS 等），取消注释配置
# echo "[$TIMESTAMP] 上传到远程存储..."
# rclone copy "$BACKUP_DIR" remote:icu-backups/ 2>/dev/null && echo "✅ 远程备份完成"

echo "[$TIMESTAMP] ✅ 备份任务完成"
