# ================= 数据管理平台 =================
# 架构风格参考 farm-mall：一个 py 文件到底，清晰分段
# 功能：8 个分表 CRUD + 折线图 + 线性回归预测
import os
import re
import json
import math
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sklearn.linear_model import LinearRegression

from config import DB_PATH, EXCEL_PATH, PORT, SECRET_KEY
from db import get_db, query_one, query_all, execute, dictify, dictify_all, placeholder, use_mysql

# SQL 占位符（SQLite用?, MySQL用%s）
P = placeholder()

# ================= 1. 初始化 Flask =================
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ================= 1-2. 文件上传配置 =================
UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
REPORT_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, 'reports')
EXPLAIN_UPLOAD_FOLDER = os.path.join(UPLOAD_FOLDER, 'explain')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

os.makedirs(REPORT_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EXPLAIN_UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ================= 2. 分表元数据缓存 =================
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
    info = SHEETS.get(sheet_key)
    if not info:
        return []
    if patient_id:
        return dictify_all(query_all(f"SELECT * FROM {info['table_name']} WHERE patient_id={P} ORDER BY id", (patient_id,)))
    return dictify_all(query_all(f"SELECT * FROM {info['table_name']} ORDER BY id"))


def compute_predictions(rows, columns, n_future=3):
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
    if not labels:
        return [f'预测+{i + 1}' for i in range(n)]
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
    try:
        last = int(float(labels[-1]))
        return [str(last + i + 1) for i in range(n)]
    except (ValueError, TypeError):
        return [f'预测+{i + 1}' for i in range(n)]


# ================= 4. 用户认证工具 =================

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return dictify(query_one(f"SELECT id, username, role, created_at FROM users WHERE id={P}", (uid,)))


def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            flash('请先登录。', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
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
    pid = session.get('patient_id')
    if not pid:
        return None
    row = query_one(f"SELECT id, name FROM patients WHERE id={P}", (pid,))
    return dictify(row)


def patient_selected_required(f):
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
    user = current_user()
    patient = get_current_patient()
    return {
        'sheets': SHEETS,
        'site_name': '安康·检验守护',
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
    session.pop('patient_id', None)
    return redirect(url_for('select_patient'))


# ================= 7. 首页 =================
@app.route('/')
@login_required
def index():
    user = current_user()
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

    ref_ranges = get_ref_ranges(key)

    return render_template('sheet.html',
                           current_key=key,
                           sheet=info,
                           rows=rows,
                           columns=columns,
                           chart_data_json=json.dumps(chart_data, ensure_ascii=False, default=str),
                           is_admin=user and user['role'] == 'admin',
                           ref_ranges=ref_ranges)


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
            if session.get('patient_id') == int(patient_id):
                session.pop('patient_id', None)

        return redirect(url_for('admin_patients'))

    patients = dictify_all(query_all("SELECT id, name, created_at FROM patients ORDER BY id"))
    return render_template('admin_patients.html', patients=patients)


# ================= 15. 搜索 =================
@app.route('/search')
@login_required
@patient_selected_required
def search():
    """搜索检验数据"""
    q = request.args.get('q', '').strip()
    if not q:
        return render_template('search.html', q=q, results=[])

    user = current_user()
    patient_id = session.get('patient_id') if (user and user['role'] != 'admin') else None
    results = []

    # 1. 搜索指标名称（列名）
    col_matches = query_all(
        f"SELECT sheet_key, sheet_display, col_key, col_display, sheet_order FROM _meta_columns WHERE col_display LIKE {P} ORDER BY sheet_order, col_order",
        (f'%{q}%',)
    )

    # 2. 搜索日期/编号
    row_matches = []  # (sheet_key, sheet_display, row) 元组
    for sk, info in SHEETS.items():
        tname = info['table_name']
        try:
            if patient_id:
                rows = dictify_all(query_all(
                    f"SELECT * FROM {tname} WHERE patient_id={P} AND row_label LIKE {P} ORDER BY id",
                    (patient_id, f'%{q}%')
                ))
            else:
                rows = dictify_all(query_all(
                    f"SELECT * FROM {tname} WHERE row_label LIKE {P} ORDER BY id",
                    (f'%{q}%',)
                ))
            for r in rows:
                row_matches.append((sk, info['display'], info['table_name'], r))
        except Exception:
            pass

    # 整理指标搜索结果：按分表分组，每组包含匹配的列 + 数据
    for sk in sorted(set(m['sheet_key'] for m in col_matches)):
        matched = [m for m in col_matches if m['sheet_key'] == sk]
        info = SHEETS.get(sk)
        if not info:
            continue
        tname = info['table_name']
        # 获取该分表的所有行
        try:
            if patient_id:
                all_rows = dictify_all(query_all(f"SELECT * FROM {tname} WHERE patient_id={P} ORDER BY id", (patient_id,)))
            else:
                all_rows = dictify_all(query_all(f"SELECT * FROM {tname} ORDER BY id"))
        except Exception:
            all_rows = []
        # 只保留 matched 列
        matched_keys = [m['col_key'] for m in matched]
        filtered_rows = []
        for r in all_rows:
            fr = {'id': r['id'], 'row_label': r['row_label']}
            for mk in matched_keys:
                fr[mk] = r.get(mk)
            filtered_rows.append(fr)
        results.append({
            'type': 'indicator',
            'key': sk,
            'sheet_display': info['display'],
            'matched_cols': [{'key': m['col_key'], 'display': m['col_display']} for m in matched],
            'rows': filtered_rows,
        })

    # 整理日期搜索结果：按分表分组
    row_groups = {}
    for sk, sdisp, tname, r in row_matches:
        if sk not in row_groups:
            info = SHEETS.get(sk)
            row_groups[sk] = {
                'sheet_display': sdisp,
                'columns': info['columns'] if info else [],
                'rows': [],
            }
        row_groups[sk]['rows'].append(r)

    for sk, rg in row_groups.items():
        results.append({
            'type': 'label',
            'key': sk,
            'sheet_display': rg['sheet_display'],
            'columns': rg['columns'],
            'rows': rg['rows'],
        })

    return render_template('search.html', q=q, results=results)


# ================= 16. API：添加指标列（仅管理员） =================
@app.route('/api/columns/<key>/add', methods=['POST'])
@admin_required
def api_add_column(key):
    info = SHEETS.get(key)
    if not info:
        return jsonify({'error': 'not found'}), 404

    payload = request.get_json(force=True) or {}
    col_name = str(payload.get('name', '')).strip()
    col_type = payload.get('type', 'numeric')
    position = payload.get('position')  # 可选，插入位置（col_order 索引）

    if not col_name:
        return jsonify({'error': '请输入指标名称'}), 400

    for c in info['columns']:
        if c['display'] == col_name:
            return jsonify({'error': f'指标 "{col_name}" 已存在'}), 400

    tname = info['table_name']
    existing_cols = info['columns']
    new_col_key = f'col_{len(existing_cols) + 1}'

    # 计算插入位置
    total = len(existing_cols)
    if position is not None and 0 <= position < total:
        new_order = position
        # 后面列的 col_order 全部 +1
        for c in existing_cols:
            if c.get('col_order', 0) >= position:
                execute(
                    f"UPDATE _meta_columns SET col_order = col_order + 1 WHERE sheet_key={P} AND col_key={P}",
                    (key, c['key'])
                )
    else:
        max_order = max((c.get('col_order', 0) for c in existing_cols), default=0)
        new_order = max_order + 1

    if use_mysql():
        sql_type = 'DOUBLE' if col_type == 'numeric' else 'VARCHAR(255)'
        execute(f"ALTER TABLE `{tname}` ADD COLUMN `{new_col_key}` {sql_type} DEFAULT NULL")
    else:
        sql_type = 'REAL' if col_type == 'numeric' else 'TEXT'
        execute(f"ALTER TABLE {tname} ADD COLUMN {new_col_key} {sql_type} DEFAULT NULL")

    sheet_order = info.get('order', 0)
    execute(
        f"INSERT INTO _meta_columns(sheet_key, sheet_display, col_key, col_display, col_order, sheet_order) VALUES({P},{P},{P},{P},{P},{P})",
        (key, info['display'], new_col_key, col_name, new_order, sheet_order)
    )

    load_sheets()

    return jsonify({'ok': True, 'col_key': new_col_key, 'display': col_name, 'position': new_order})


# ================= 16-2. API：重新排序列（仅管理员） =================
@app.route('/api/columns/<key>/reorder', methods=['POST'])
@admin_required
def api_reorder_columns(key):
    """以整列为单位重新排序，拖拽后调用此接口"""
    info = SHEETS.get(key)
    if not info:
        return jsonify({'error': 'not found'}), 404

    payload = request.get_json(force=True) or {}
    new_order = payload.get('order', [])  # 例如 ["col_3", "col_1", "col_2"]

    if not new_order:
        return jsonify({'error': '缺少 order 参数'}), 400

    existing = query_all(f"SELECT col_key FROM _meta_columns WHERE sheet_key={P}", (key,))
    existing_keys = {e['col_key'] for e in existing}

    if set(new_order) != existing_keys:
        return jsonify({'error': '列集合不匹配'}), 400

    conn = get_db()
    cur = conn.cursor()
    for idx, col_key in enumerate(new_order):
        cur.execute(
            f"UPDATE _meta_columns SET col_order={P} WHERE sheet_key={P} AND col_key={P}",
            (idx, key, col_key)
        )
    conn.commit()
    conn.close()

    load_sheets()

    return jsonify({'ok': True, 'order': new_order})


# ================= 17. API：参考范围（仅管理员） =================
@app.route('/api/refs/<key>', methods=['GET', 'POST'])
@login_required
def api_refs(key):
    """获取/设置指标的参考范围"""
    info = SHEETS.get(key)
    if not info:
        return jsonify({'error': 'not found'}), 404

    if request.method == 'GET':
        refs = query_all(f"SELECT col_key, ref_min, ref_max FROM indicator_refs WHERE sheet_key={P}", (key,))
        result = {}
        for r in refs:
            result[r['col_key']] = {
                'ref_min': r['ref_min'],
                'ref_max': r['ref_max'],
            }
        return jsonify(result)

    # POST: 仅管理员可设置
    user = current_user()
    if not user or user['role'] != 'admin':
        return jsonify({'error': '仅管理员可操作'}), 403

    payload = request.get_json(force=True) or {}
    col_key = payload.get('col_key', '')
    ref_min = payload.get('ref_min')
    ref_max = payload.get('ref_max')

    if not col_key:
        return jsonify({'error': '缺少 col_key'}), 400

    # 验证列存在
    valid = any(c['key'] == col_key for c in info['columns'])
    if not valid:
        return jsonify({'error': '列不存在'}), 400

    # 转为 float 或 None
    try:
        ref_min = float(ref_min) if ref_min not in (None, '') else None
    except (ValueError, TypeError):
        ref_min = None
    try:
        ref_max = float(ref_max) if ref_max not in (None, '') else None
    except (ValueError, TypeError):
        ref_max = None

    # UPSERT
    existing = query_one(f"SELECT id FROM indicator_refs WHERE sheet_key={P} AND col_key={P}", (key, col_key))
    if existing:
        execute(f"UPDATE indicator_refs SET ref_min={P}, ref_max={P} WHERE id={P}", (ref_min, ref_max, existing['id']))
    else:
        execute(f"INSERT INTO indicator_refs(sheet_key, col_key, ref_min, ref_max) VALUES({P},{P},{P},{P})", (key, col_key, ref_min, ref_max))

    return jsonify({'ok': True, 'ref_min': ref_min, 'ref_max': ref_max})


# ================= 18. API：导出 CSV =================
@app.route('/api/export/<key>')
@login_required
@patient_selected_required
def api_export(key):
    """导出分表数据为 CSV"""
    info = SHEETS.get(key)
    if not info:
        abort(404)

    user = current_user()
    patient_id = session.get('patient_id') if (user and user['role'] != 'admin') else None
    rows = get_rows(key, patient_id)
    columns = info['columns']

    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    # 表头
    headers = ['日期/编号'] + [c['display'] for c in columns]
    writer.writerow(headers)

    # 数据行
    for r in rows:
        writer.writerow([r.get('row_label', '')] + [r.get(c['key'], '') for c in columns])

    csv_data = output.getvalue()
    output.close()

    # 文件名
    filename = f'{info["display"]}.csv'
    # URL 编码文件名
    from urllib.parse import quote
    encoded = quote(filename)

    return (csv_data, 200, {
        'Content-Type': 'text/csv; charset=utf-8-sig',
        'Content-Disposition': f'attachment; filename*=UTF-8\'\'{encoded}',
    })


# ================= 19. 获取参考范围（辅助函数，用于模板） =================
def get_ref_ranges(sheet_key):
    """获取分表所有列的参考范围"""
    refs = query_all(f"SELECT col_key, ref_min, ref_max FROM indicator_refs WHERE sheet_key={P}", (sheet_key,))
    result = {}
    for r in refs:
        result[r['col_key']] = {
            'ref_min': r['ref_min'],
            'ref_max': r['ref_max'],
        }
    return result


# ================= 20. 错误处理 =================
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', message='页面不存在', code=404), 404


# ================= 21. 图片报告 =================
@app.route('/reports')
@login_required
def reports_list():
    """报告列表页"""
    user = current_user()
    is_admin_user = user and user['role'] == 'admin'

    patient_id = session.get('patient_id') if (user and user['role'] != 'admin') else None

    if patient_id:
        rows = dictify_all(query_all(f"SELECT * FROM reports WHERE patient_id={P} ORDER BY created_at DESC", (patient_id,)))
    else:
        rows = dictify_all(query_all("SELECT * FROM reports ORDER BY created_at DESC"))

    patients = dictify_all(query_all("SELECT id, name FROM patients ORDER BY id"))

    return render_template('reports.html',
                           reports=rows,
                           patients=patients,
                           is_admin=is_admin_user)


@app.route('/reports/upload', methods=['GET', 'POST'])
@login_required
@admin_required
def report_upload():
    """提交图片报告"""
    patients = dictify_all(query_all("SELECT id, name FROM patients ORDER BY id"))

    if request.method == 'GET':
        return render_template('report_form.html', patients=patients, report=None, edit_mode=False)

    # POST
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    patient_id = request.form.get('patient_id', 1)
    file = request.files.get('image')

    if not title:
        flash('请填写报告标题。', 'danger')
        return render_template('report_form.html', patients=patients, report=None, edit_mode=False)

    if not file or file.filename == '':
        flash('请选择要上传的图片。', 'danger')
        return render_template('report_form.html', patients=patients, report=None, edit_mode=False)

    if not allowed_file(file.filename):
        flash('只支持图片格式（png/jpg/jpeg/gif/webp/bmp）。', 'danger')
        return render_template('report_form.html', patients=patients, report=None, edit_mode=False)

    filename = secure_filename(file.filename)
    import time
    unique_name = f"{int(time.time())}_{filename}"
    file.save(os.path.join(REPORT_UPLOAD_FOLDER, unique_name))

    image_rel = f'uploads/reports/{unique_name}'

    execute(
        f"INSERT INTO reports(patient_id, title, description, image_path) VALUES({P},{P},{P},{P})",
        (int(patient_id), title, description, image_rel)
    )

    flash('图片报告已提交 ✓', 'success')
    return redirect(url_for('reports_list'))


@app.route('/reports/<int:report_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def report_edit(report_id):
    """编辑图片报告"""
    report = dictify(query_one(f"SELECT * FROM reports WHERE id={P}", (report_id,)))
    if not report:
        abort(404)

    patients = dictify_all(query_all("SELECT id, name FROM patients ORDER BY id"))

    if request.method == 'GET':
        return render_template('report_form.html', patients=patients, report=report, edit_mode=True)

    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    patient_id = request.form.get('patient_id', 1)
    file = request.files.get('image')

    if not title:
        flash('请填写报告标题。', 'danger')
        return render_template('report_form.html', patients=patients, report=report, edit_mode=True)

    if file and file.filename != '':
        if not allowed_file(file.filename):
            flash('只支持图片格式。', 'danger')
            return render_template('report_form.html', patients=patients, report=report, edit_mode=True)
        filename = secure_filename(file.filename)
        import time
        unique_name = f"{int(time.time())}_{filename}"
        file.save(os.path.join(REPORT_UPLOAD_FOLDER, unique_name))
        image_rel = f'uploads/reports/{unique_name}'
        execute(f"UPDATE reports SET image_path={P} WHERE id={P}", (image_rel, report_id))

    execute(
        f"UPDATE reports SET title={P}, description={P}, patient_id={P} WHERE id={P}",
        (title, description, int(patient_id), report_id)
    )

    flash('报告已更新 ✓', 'success')
    return redirect(url_for('reports_list'))


@app.route('/reports/<int:report_id>/delete', methods=['POST'])
@login_required
@admin_required
def report_delete(report_id):
    """删除图片报告"""
    report = dictify(query_one(f"SELECT * FROM reports WHERE id={P}", (report_id,)))
    if not report:
        abort(404)

    # 删除物理文件
    file_path = os.path.join(app.static_folder, report['image_path'])
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass

    execute(f"DELETE FROM reports WHERE id={P}", (report_id,))
    flash('报告已删除。', 'info')
    return redirect(url_for('reports_list'))


# ================= 22. 指标名词解释 =================
@app.route('/explain/<sheet_key>/<col_key>')
@login_required
def explain_view(sheet_key, col_key):
    """查看指标解释"""
    info = SHEETS.get(sheet_key)
    if not info:
        abort(404)

    col_info = next((c for c in info['columns'] if c['key'] == col_key), None)
    if not col_info:
        abort(404)

    explain = dictify(query_one(
        f"SELECT * FROM indicator_explanations WHERE sheet_key={P} AND col_key={P}",
        (sheet_key, col_key)
    ))

    user = current_user()
    is_admin_user = user and user['role'] == 'admin'

    # 解析图片列表
    explain_images = []
    if explain and explain.get('images'):
        try:
            explain_images = json.loads(explain['images'])
        except (json.JSONDecodeError, TypeError):
            explain_images = []

    return render_template('explain.html',
                           sheet_key=sheet_key,
                           col_key=col_key,
                           col_display=col_info['display'],
                           sheet_display=info['display'],
                           explain=explain,
                           explain_images=explain_images,
                           is_admin=is_admin_user)


@app.route('/explain/<sheet_key>/<col_key>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def explain_edit(sheet_key, col_key):
    """编辑指标解释"""
    info = SHEETS.get(sheet_key)
    if not info:
        abort(404)

    col_info = next((c for c in info['columns'] if c['key'] == col_key), None)
    if not col_info:
        abort(404)

    explain = dictify(query_one(
        f"SELECT * FROM indicator_explanations WHERE sheet_key={P} AND col_key={P}",
        (sheet_key, col_key)
    ))

    # 解析已有图片列表
    explain_images = []
    if explain and explain.get('images'):
        try:
            explain_images = json.loads(explain['images'])
        except (json.JSONDecodeError, TypeError):
            explain_images = []

    if request.method == 'GET':
        return render_template('explain_edit.html',
                               sheet_key=sheet_key,
                               col_key=col_key,
                               col_display=col_info['display'],
                               sheet_display=info['display'],
                               explain=explain,
                               explain_images=explain_images)

    # POST
    content = request.form.get('content', '').strip()
    images = request.files.getlist('images')

    existing_images = []
    if explain and explain.get('images'):
        try:
            existing_images = json.loads(explain['images'])
        except (json.JSONDecodeError, TypeError):
            existing_images = []

    # 处理新上传的图片
    new_images = []
    for file in images:
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            import time
            unique_name = f"{int(time.time())}_{filename}"
            file.save(os.path.join(EXPLAIN_UPLOAD_FOLDER, unique_name))
            new_images.append(f'uploads/explain/{unique_name}')

    all_images = existing_images + new_images

    # 删除标记的图片
    keep_images_str = request.form.get('keep_images', '')
    if keep_images_str:
        keep_set = set()
        for k in keep_images_str.split(','):
            k = k.strip()
            if k:
                keep_set.add(k)
        # 不在 keep_set 中的图片被删除
        deleted = [img for img in all_images if img not in keep_set]
        for img_path in deleted:
            full_path = os.path.join(app.static_folder, img_path)
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
            except Exception:
                pass
        all_images = [img for img in all_images if img in keep_set]

    images_json = json.dumps(all_images, ensure_ascii=False)

    if explain:
        execute(
            f"UPDATE indicator_explanations SET content={P}, images={P} WHERE id={P}",
            (content, images_json, explain['id'])
        )
    else:
        execute(
            f"INSERT INTO indicator_explanations(sheet_key, col_key, content, images) VALUES({P},{P},{P},{P})",
            (sheet_key, col_key, content, images_json)
        )

    flash('解释已保存 ✓', 'success')
    return redirect(url_for('explain_view', sheet_key=sheet_key, col_key=col_key))


# ================= 18. 启动入口 =================
if __name__ == '__main__':
    load_sheets()
    if not SHEETS:
        print("数据库未初始化，正在从 Excel 导入...")
        from init_db import init_db
        init_db(force=False)
        load_sheets()

    # 自动检测并创建缺失的新表（安全迁移，不影响已有数据）
    try:
        missing_tables = []
        conn = get_db()
        cur = conn.cursor()
        if use_mysql():
            cur.execute("SHOW TABLES LIKE 'reports'")
            if not cur.fetchone():
                missing_tables.append('reports')
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS reports (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        patient_id INT NOT NULL DEFAULT 1,
                        title VARCHAR(200) NOT NULL,
                        description TEXT,
                        image_path VARCHAR(500) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
            cur.execute("SHOW TABLES LIKE 'indicator_explanations'")
            if not cur.fetchone():
                missing_tables.append('indicator_explanations')
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
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reports'")
            if not cur.fetchone():
                missing_tables.append('reports')
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        patient_id INTEGER NOT NULL DEFAULT 1,
                        title TEXT NOT NULL,
                        description TEXT,
                        image_path TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='indicator_explanations'")
            if not cur.fetchone():
                missing_tables.append('indicator_explanations')
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
        conn.commit()
        conn.close()
        if missing_tables:
            print(f"已自动创建缺失的表：{', '.join(missing_tables)}")
    except Exception as e:
        print(f"自动建表检查跳过（非关键）：{e}")

    print(f"已加载 {len(SHEETS)} 个分表")
    app.run(host='0.0.0.0', port=PORT, debug=True)
