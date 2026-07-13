# ================= 配置 =================
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ===== 数据库配置 =====
# 本地开发用 SQLite，线上用 MySQL
# 当 MYSQL_HOST 为空时使用 SQLite

# MySQL 连接参数（部署时填写）
MYSQL_HOST = os.getenv("MYSQL_HOST", "")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "icu_data")

# SQLite 路径（本地开发用）
DB_PATH = os.path.join(BASE_DIR, 'icu.db')

# Excel 数据文件
EXCEL_PATH = os.path.join(BASE_DIR, 'upload', 'ICU数据.xlsx')

# 服务端口
PORT = 5000

# Flask 密钥
SECRET_KEY = 'icu_data_secret_key_change_in_production'
