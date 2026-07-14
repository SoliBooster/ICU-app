# ================= ICU 数据管理平台 =================
# 架构风格参考 farm-mall：一个 py 文件到底，清晰分段
# 功能：8 个分表 CRUD + 折线图 + 线性回归预测
import os
import re
import json
import math
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from sklearn.linear_model import LinearRegression

from config import DB_PATH, EXCEL_PATH, PORT, SECRET_KEY
from db import get_db, query_one, query_all, execute, dictify, dictify_all, placeholder, use_mysql

# SQL 占位符（SQLite用?, MySQL用%s）
P = placeholder()

# ================= 1. 初始化 Flask =================
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ================= 2. 分表元数据缓存 =================
# SHEETS[sheet_key] = {
#   'display': '血常规', 'key': 's_1', 'table_name': 't_xxx',
#   'columns': [{'key': 'col_1', 'display': 'WBC'}, ...],
#   'order': 0
# }
SHEETS = {}


def load_sheets():
    """从数据库加载分表元数据"""
    global SHEETS
    raw = query_all("SELECT DISTINCT sheet_key, sheet_display, sheet_order FROM _meta_columns ORDER BY sheet_order")
    sheets = {}
    for r in raw:
        key = r['sheet_key']
        cols = dictify_all(query_all(
            f"SELECT col_key, col_display, col_order FROM _meta_columns WHERE sheet_key={P} ORDER BY col_order",
            (key,)
        ))
        # 找出真实的 SQL 表名
        tname = None
        conn = get_db()
        cur = conn.cursor()
        if use_mysql():
            cur.execute("SELECT TABLE_NAME AS name FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME LIKE %s", (f'%{key.replace("s_", "_")}',))
        else:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?", (f'%{key.replace("s_", "_")}',))
        row = cur.fetchone()
        conn.close()
        if row:
            tname = row['name']

        if tname:
            sheets[key] = {
                'display': r['sheet_display'],
                'key': key,
                'table_name': tname,
                'columns': [{'key': c['col_key'], 'display': c['col_display']} for c in cols],
                'order': r['sheet_order'],
            }
    SHEETS = dict(sorted(sheets.items(), key=lambda kv: kv[1]['order']))


# ================= 3. 数据工具函数 =================

def parse_float(v):
    """把值转为 float，无法解析返回 None"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    s2 = re.sub(r'[<≥≤≈>~]', '', s)
    try:
        return float(s2)
    except ValueError:
        return None


def get_rows(sheet_key, patient_id=None):
    """获取某个分表的数据行，可选按患者筛选"""
    info = SHEETS.get(sheet_key)
    if not info:
        return []
    if patient_id:
        return dictify_all(query_all(f"SELECT * FROM {info['table_name']} WHERE patient_id={P} ORDER BY id", (patient_id,)))
    return dictify_all(query_all(f"SELECT * FROM {info['table_name']} ORDER BY id"))


def compute_predictions(rows, columns, n_future=3):
    """对每个数值列做线性回归预测"""
    n = len(rows)
    result = {}
    if n < 2:
        return result

    for col in columns:
        ck = col['key']
        ys = []
        xs = []
        for i, r in enumerate(rows):
            v = r.get(ck)
            if v is not None:
                ys.append(float(v))
                xs.append(i)
        if len(xs) >= 2:
            X = np.array(xs).reshape(-1, 1)
            y = np.array(ys)
            try:
                model = LinearRegression()
                model.fit(X, y)
                future_x = np.arange(n, n + n_future).reshape(-1, 1)
                future_y = model.predict(future_x)
                history = [r.get(ck) for r in rows]
                predicted = [round(float(v), 4) for v in future_y]
                result[ck] = {
                    'display': col['display'],
                    'history': history,
                    'predicted': predicted,
                    'slope': round(float(model.coef_[0]), 4),
                    'intercept': round(float(model.intercept_), 4),
                    'r2': round(float(model.score(X, y)), 4),
                }
            except Exception:
                continue
    return result


def future_labels(labels, n):
    """生成未来 N 个点的标签"""
    if not labels:
        return [f'预测+{i + 1}' for i in range(n)]
    # 尝试日期型 '7月10号'
    m = re.match(r'^(\d+)月(\d+)号?$', str(labels[-1]))
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        out = []
        d = day
        mon = month
        for i in range(n):
            d += 1
            maxd = 31 if mon in (1, 3, 5, 7, 8, 10, 12) else 30
            if d > maxd:
                d = 1
                mon += 1
                if mon > 12:
                    mon = 1
            out.append(f'{mon}月{d}号')
        return out
    # 纯数字 ID
    try:
        last = int(float(labels[-1]))
        return [str(last + i + 1) for i in range(n)]
    except (ValueError, TypeError):
        return [f'预测+{i + 1}' for i in range(n)]


# ================= 4. 用户认证工具 =================

def current_user():
    """获取当前登录用户"""
    uid = session.get('user_id')
    if not uid:
        return None
    return dictify(query_one(f"SELECT id, username, role, created_at FROM users WHERE id={P}", (uid,)))


def login_required(f):
    """登录验证装饰器"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            flash('请先登录。', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """管理员验证装饰器"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user['role'] != 'admin':
            flash('仅管理员可执行此操作。', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapper


def get_current_patient():
    """获取当前选中病人"""
    pid = session.get('patient_id')
    if not pid:
        return None
    row = query_one(f"SELECT id, name FROM patients WHERE id={P}", (pid,))
    return dictify(row)


def patient_selected_required(f):
    """病人选择验证装饰器（普通用户必须选病人）"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user and user['role'] != 'admin':
            if not session.get('patient_id'):
                flash('请先选择要查看的病人。', 'info')
                return redirect(url_for('select_patient'))
            patient = get_current_patient()
            if not patient:
                session.pop('patient_id', None)
                flash('请重新选择病人。', 'info')
                return redirect(url_for('select_patient'))
        return f(*args, **kwargs)
    return wrapper


# ================= 5. 上下文处理器 =================
@app.context_processor
def inject_globals():
    """全局注入变量到所有模板"""
    user = current_user()
    patient = get_current_patient()
    return {
        'sheets': SHEETS,
        'site_name': 'ICU 检验数据平台',
        'current_user': user,
        'is_admin': user and user['role'] == 'admin',
        'current_patient': patient,
    }


# ================= 6. 登录 / 注册 / 登出 / 病人选择 =================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    user = dictify(query_one(f"SELECT * FROM users WHERE username={P}", (username,)))
    if not user or not check_password_hash(user['password_hash'], password):
        flash('用户名或密码错误。', 'danger')
        return render_template('login.html')

    session['user_id'] = user['id']
    session.permanent = True
    session.pop('patient_id', None)
    flash(f'欢迎回来，{user["username"]}。', 'success')
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    confirm = request.form.get('confirm', '')

    # 校验
    if len(username) < 2 or len(username) > 20:
        flash('用户名长度2-20位。', 'danger')
        return render_template('register.html')
    if len(password) < 6:
        flash('密码至少6位。', 'danger')
        return render_template('register.html')
    if password != confirm:
        flash('两次密码输入不一致。', 'danger')
        return render_template('register.html')

    existing = query_one(f"SELECT id FROM users WHERE username={P}", (username,))
    if existing:
        flash('用户名已被注册。', 'danger')
        return render_template('register.html')

    execute(
        f"INSERT INTO users(username, password_hash, role) VALUES({P},{P},{P})",
        (username, generate_password_hash(password), 'user')
    )
    flash('注册成功，请登录。', 'success')
    return redirect(url_for('login'))


@app.route('/logout')
def logout():
    session.clear()
    flash('已退出登录。', 'info')
    return redirect(url_for('login'))


@app.route('/select_patient', methods=['GET', 'POST'])
@login_required
def select_patient():
    """普通用户选择病人并输入查看密码"""
    user = current_user()
    if user and user['role'] == 'admin':
        return redirect(url_for('index'))

    patients = dictify_all(query_all("SELECT id, name FROM patients ORDER BY id"))

    if request.method == 'POST':
        patient_id = request.form.get('patient_id', '').strip()
        view_password = request.form.get('view_password', '')

        if not patient_id:
            flash('请选择病人。', 'danger')
            return render_template('select_patient.html', patients=patients)

        patient = dictify(query_one(f"SELECT * FROM patients WHERE id={P}", (patient_id,)))
        if not patient:
            flash('病人不存在。', 'danger')
            return render_template('select_patient.html', patients=patients)

        if not check_password_hash(patient['view_password_hash'], view_password):
            flash('查看密码错误。', 'danger')
            return render_template('select_patient.html', patients=patients)

        session['patient_id'] = patient['id']
        flash(f'已进入 {patient["name"]} 的检查数据。', 'success')
        return redirect(url_for('index'))

    return render_template('select_patient.html', patients=patients)


@app.route('/switch_patient')
@login_required
def switch_patient():
    """切换病人（清除当前病人选择）"""
    session.pop('patient_id', None)
    return redirect(url_for('select_patient'))


# ================= 7. 首页 =================
@app.route('/')
@login_required
def index():
    user = current_user()
    # 普通用户必须选择病人
    if user and user['role'] != 'admin' and not session.get('patient_id'):
        return redirect(url_for('select_patient'))
    if not SHEETS:
        return render_template('error.html', message='数据库未初始化', code=500), 500
    first_key = list(SHEETS.keys())[0]
    return redirect(f'/sheet/{first_key}')


# ================= 8. 分表详情页 =================
@app.route('/sheet/<key>')
@login_required
@patient_selected_required
def sheet_view(key):
    info = SHEETS.get(key)
    if not info:
        abort(404)

    user = current_user()
    patient_id = session.get('patient_id') if (user and user['role'] != 'admin') else None
    rows = get_rows(key, patient_id)
    columns = info['columns']
    predictions = compute_predictions(rows, columns)
    flabels = future_labels([r['row_label'] for r in rows], 3)

    chart_data = {
        'labels': [r['row_label'] for r in rows],
        'future_labels': flabels,
        'columns': columns,
        'rows': rows,
        'predictions': predictions,
    }

    return render_template('sheet.html',
                           current_key=key,
                           sheet=info,
                           rows=rows,
                           columns=columns,
                           chart_data_json=json.dumps(chart_data, ensure_ascii=False, default=str),
                           is_admin=user and user['role'] == 'admin')


# ================= 9. API：获取数据 =================
@app.route('/api/data/<key>')
@login_required
@patient_selected_required
def api_get_data(key):
    info = SHEETS.get(key)
    if not info:
        return jsonify({'error': 'not found'}), 404
    user = current_user()
    patient_id = session.get('patient_id') if (user and user['role'] != 'admin') else None
    rows = get_rows(key, patient_id)
    return jsonify({'columns': info['columns'], 'rows': rows})


# ================= 10. API：新增记录（仅管理员） =================
@app.route('/api/data/<key>/row', methods=['POST'])
@admin_required
def api_add_row(key):
    info = SHEETS.get(key)
    if not info:
        return jsonify({'error': 'not found'}), 404

    payload = request.get_json(force=True) or {}
    row_label = str(payload.get('row_label', '')).strip()
    cols = info['columns']

    col_names = ['row_label']
    col_vals = [row_label]
    placeholders = [P]

    for c in cols:
        v = payload.get(c['key'], None)
        col_names.append(c['key'])
        col_vals.append(parse_float(v) if v not in (None, '') else None)
        placeholders.append(P)

    # 管理员添加记录时自动关联到当前病人（如果有选）
    patient_id = session.get('patient_id')
    if patient_id:
        col_names.append('patient_id')
        col_vals.append(patient_id)
        placeholders.append(P)

    sql = f"INSERT INTO {info['table_name']}({', '.join(col_names)}) VALUES({','.join(placeholders)})"
    new_id = execute(sql, col_vals)
    return jsonify({'ok': True, 'id': new_id})


# ================= 11. API：更新单元格（仅管理员） =================
@app.route('/api/data/<key>/cell', methods=['POST'])
@admin_required
def api_update_cell(key):
    info = SHEETS.get(key)
    if not info:
        return jsonify({'error': 'not found'}), 404

    payload = request.get_json(force=True) or {}
    row_id = payload.get('id')
    field = payload.get('field')
    value = payload.get('value')

    if row_id is None or not field:
        return jsonify({'error': 'missing id/field'}), 400

    if field == 'row_label':
        new_val = str(value).strip()
    elif field in [c['key'] for c in info['columns']]:
        new_val = parse_float(value) if value not in (None, '') else None
    else:
        return jsonify({'error': 'invalid field'}), 400

    execute(f"UPDATE {info['table_name']} SET {field}={P} WHERE id={P}", (new_val, row_id))
    return jsonify({'ok': True, 'value': new_val})


# ================= 12. API：删除记录（仅管理员） =================
@app.route('/api/data/<key>/row/<int:row_id>', methods=['DELETE'])
@admin_required
def api_delete_row(key, row_id):
    info = SHEETS.get(key)
    if not info:
        return jsonify({'error': 'not found'}), 404
    execute(f"DELETE FROM {info['table_name']} WHERE id={P}", (row_id,))
    return jsonify({'ok': True})


# ================= 13. API：预测 =================
@app.route('/api/predict/<key>')
@login_required
@patient_selected_required
def api_predict(key):
    info = SHEETS.get(key)
    if not info:
        return jsonify({'error': 'not found'}), 404

    user = current_user()
    patient_id = session.get('patient_id') if (user and user['role'] != 'admin') else None
    rows = get_rows(key, patient_id)
    predictions = compute_predictions(rows, info['columns'])
    flabels = future_labels([r['row_label'] for r in rows], 3)
    return jsonify({
        'labels': [r['row_label'] for r in rows],
        'future_labels': flabels,
        'predictions': predictions,
    })


# ================= 14. 管理员：病人管理 =================
@app.route('/admin/patients', methods=['GET', 'POST'])
@admin_required
def admin_patients():
    """管理员管理病人"""
    if request.method == 'POST':
        action = request.form.get('action', '')
        patient_id = request.form.get('patient_id', '')
        name = request.form.get('name', '').strip()
        view_password = request.form.get('view_password', '')

        if action == 'add':
            if not name:
                flash('请输入病人姓名。', 'danger')
            elif len(view_password) < 4:
                flash('查看密码至少4位。', 'danger')
            else:
                existing = query_one(f"SELECT id FROM patients WHERE name={P}", (name,))
                if existing:
                    flash(f'病人 "{name}" 已存在。', 'danger')
                else:
                    execute(
                        f"INSERT INTO patients(name, view_password_hash) VALUES({P},{P})",
                        (name, generate_password_hash(view_password))
                    )
                    flash(f'病人 "{name}" 已添加。', 'success')

        elif action == 'edit' and patient_id:
            if not name:
                flash('请输入病人姓名。', 'danger')
            else:
                if view_password:
                    execute(
                        f"UPDATE patients SET name={P}, view_password_hash={P} WHERE id={P}",
                        (name, generate_password_hash(view_password), patient_id)
                    )
                    flash('病人信息已更新。', 'success')
                else:
                    execute(
                        f"UPDATE patients SET name={P} WHERE id={P}",
                        (name, patient_id)
                    )
                    flash('病人姓名已更新。', 'success')

        elif action == 'delete' and patient_id:
            execute(f"DELETE FROM patients WHERE id={P}", (patient_id,))
            flash('病人已删除。', 'success')
            # 如果当前选中的是这个病人，清除选择
            if session.get('patient_id') == int(patient_id):
                session.pop('patient_id', None)

        return redirect(url_for('admin_patients'))

    patients = dictify_all(query_all("SELECT id, name, created_at FROM patients ORDER BY id"))
    return render_template('admin_patients.html', patients=patients)


# ================= 14. 错误处理 =================
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', message='页面不存在', code=404), 404


# ================= 15. 启动入口 =================
if __name__ == '__main__':
    # 先加载分表元数据
    load_sheets()
    # 如果没有数据表，重新初始化
    if not SHEETS:
        print("数据库未初始化，正在从 Excel 导入...")
        from init_db import init_db
        init_db(force=False)
        load_sheets()
    print(f"已加载 {len(SHEETS)} 个分表")
    app.run(host='0.0.0.0', port=PORT, debug=True)
