// 分表页：图表渲染 + 数据增删改查
(function () {
    var sheetKey = document.getElementById('sheetKey').value;
    var raw = document.getElementById('chartData').value;
    var DATA = {};
    try { DATA = JSON.parse(raw); } catch (e) { console.error('chart data parse error', e); }

    var PALETTE = [
        '#0d9488', '#ea580c', '#7c3aed', '#db2777', '#2563eb',
        '#65a30d', '#0891b2', '#c026d3', '#f59e0b', '#059669',
        '#e11d48', '#4f46e5', '#0284c7', '#ca8a04', '#16a34a',
        '#9333ea', '#dc2626', '#0d9488', '#92400e', '#1d4ed8'
    ];

    // ---------- 工具 ----------
    function $(s, p) { return (p || document).querySelector(s); }
    function $all(s, p) { return Array.prototype.slice.call((p || document).querySelectorAll(s)); }
    function showToast(msg, type) {
        var t = document.getElementById('toast');
        if (!t) return;
        t.textContent = msg;
        t.className = 'toast show ' + (type || '');
        clearTimeout(t._timer);
        t._timer = setTimeout(function () { t.className = 'toast'; }, 2200);
    }
    function num(v) {
        if (v === null || v === undefined || v === '') return null;
        var n = parseFloat(v);
        return isNaN(n) ? null : n;
    }
    function colorFor(i) { return PALETTE[i % PALETTE.length]; }

    // ---------- 状态 ----------
    var selectedCols = [];    // 折线图选中的指标
    var predictCol = null;    // 预测图指标
    var lineCharts = [];      // 存储所有折线图实例
    var predictChart = null;

    // ---------- 初始化指标选择 ----------
    function initColChips() {
        var box = $('#colChips');
        box.innerHTML = '';
        (DATA.columns || []).forEach(function (c, i) {
            var chip = document.createElement('span');
            chip.className = 'chip';
            chip.dataset.key = c.key;
            chip.title = c.display;
            var dot = document.createElement('span');
            dot.className = 'chip-dot';
            dot.style.background = colorFor(i);
            chip.appendChild(dot);
            var txt = document.createElement('span');
            txt.textContent = c.display;
            chip.appendChild(txt);
            chip.addEventListener('click', function () { toggleCol(c.key); });
            box.appendChild(chip);
        });
        // 默认选中前 3 个
        selectedCols = (DATA.columns || []).slice(0, 3).map(function (c) { return c.key; });
        syncChips();
    }
    function syncChips() {
        $all('.chip', $('#colChips')).forEach(function (chip) {
            var on = selectedCols.indexOf(chip.dataset.key) >= 0;
            chip.classList.toggle('active', on);
        });
    }
    function toggleCol(key) {
        var i = selectedCols.indexOf(key);
        if (i >= 0) selectedCols.splice(i, 1);
        else selectedCols.push(key);
        if (selectedCols.length > 6) selectedCols.shift(); // 最多6个
        syncChips();
        renderLineChart();
    }

    // ---------- 折线图（每个指标独立一块，各用各自y轴） ----------
    function renderLineChart() {
        var container = $('#lineChartContainer');
        if (!container) return;

        // 销毁旧图
        lineCharts.forEach(function (c) { if (c) c.destroy(); });
        lineCharts = [];
        container.innerHTML = '';

        if (selectedCols.length === 0) {
            container.innerHTML = '<div class="empty-chart-hint">请选择指标</div>';
            return;
        }

        var labels = DATA.labels || [];

        selectedCols.forEach(function (key, idx) {
            var colIdx = (DATA.columns || []).findIndex(function (c) { return c.key === key; });
            var colName = (DATA.columns[colIdx] || {}).display || key;
            var chartColor = colorFor(colIdx);

            // ---- 图表卡片 ----
            var card = document.createElement('div');
            card.className = 'mini-chart-card';

            var header = document.createElement('div');
            header.className = 'mini-chart-header';
            header.innerHTML = '<span class="mini-chart-dot" style="background:' + chartColor + '"></span>'
                + '<span class="mini-chart-title">' + colName + '</span>';
            card.appendChild(header);

            var canvasWrap = document.createElement('div');
            canvasWrap.className = 'mini-chart-canvas';
            var canvas = document.createElement('canvas');
            canvasWrap.appendChild(canvas);
            card.appendChild(canvasWrap);

            container.appendChild(card);

            // ---- 渲染 Chart ----
            var data = (DATA.rows || []).map(function (r) { return num(r[key]); });

            // 过滤出有效值算 y 轴范围
            var valid = data.filter(function (v) { return v !== null; });
            var dataMin = valid.length ? Math.min.apply(null, valid) : 0;
            var dataMax = valid.length ? Math.max.apply(null, valid) : 1;
            var range = dataMax - dataMin || 1;
            var pad = range * 0.15; // 上下留 15% 空白，避免线贴边
            var yMin = Math.max(0, dataMin - pad);  // 不超过0
            var yMax = dataMax + pad;

            var chart = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: colName,
                        data: data,
                        borderColor: chartColor,
                        backgroundColor: chartColor + '22',
                        tension: 0.32,
                        borderWidth: 2.5,
                        pointRadius: 4.5,
                        pointHoverRadius: 7,
                        pointBackgroundColor: chartColor,
                        spanGaps: true,
                        fill: true,
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: function (c) {
                                    return c.parsed.y === null ? colName + '：—' : colName + '：' + c.parsed.y;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { display: false },
                            ticks: { font: { size: 11 }, maxRotation: 45 }
                        },
                        y: {
                            min: yMin,
                            max: yMax,
                            grid: { color: '#eef1f4' },
                            ticks: { font: { size: 11 } }
                        }
                    }
                }
            });
            lineCharts.push(chart);
        });
    }

    // ---------- 预测图 ----------
    function initPredictSelect() {
        var sel = $('#predictSelect');
        sel.innerHTML = '';
        var preds = DATA.predictions || {};
        var keys = Object.keys(preds);
        if (keys.length === 0) {
            var opt = document.createElement('option');
            opt.textContent = '暂无可预测指标（需 ≥2 个有效数据点）';
            opt.value = '';
            sel.appendChild(opt);
            sel.disabled = true;
            return;
        }
        sel.disabled = false;
        keys.forEach(function (k) {
            var opt = document.createElement('option');
            opt.value = k;
            opt.textContent = preds[k].display;
            sel.appendChild(opt);
        });
        predictCol = keys[0];
        sel.value = predictCol;
        sel.addEventListener('change', function () { predictCol = sel.value; renderPredictChart(); });
        renderPredictChart();
    }
    function renderPredictChart() {
        var ctx = $('#predictChart');
        if (!ctx) return;
        var preds = DATA.predictions || {};
        var p = preds[predictCol];
        var info = $('#predictInfo');
        if (!p) {
            info.innerHTML = '';
            if (predictChart) { predictChart.destroy(); predictChart = null; }
            return;
        }
        info.innerHTML = '斜率 <b>' + p.slope + '</b> · 截距 <b>' + p.intercept + '</b> · 拟合度 R² <b>' + p.r2 + '</b>';
        var histLabels = DATA.labels || [];
        var futureLabels = DATA.future_labels || [];
        var allLabels = histLabels.concat(futureLabels);
        var histData = p.history.concat(futureLabels.map(function () { return null; }));
        var predData = histLabels.map(function () { return null; }).concat(p.predicted);
        // 连接点：在历史最后一点也画上预测起点
        if (histLabels.length > 0) {
            predData[histLabels.length - 1] = p.history[histLabels.length - 1];
        }
        var idx = (DATA.columns || []).findIndex(function (c) { return c.key === predictCol; });
        var col = colorFor(idx);
        if (predictChart) predictChart.destroy();
        predictChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: allLabels,
                datasets: [
                    {
                        label: '历史数据',
                        data: histData,
                        borderColor: col,
                        backgroundColor: col + '22',
                        tension: 0.3,
                        borderWidth: 2.5,
                        pointRadius: 5,
                        spanGaps: true,
                        fill: true,
                    },
                    {
                        label: '预测趋势',
                        data: predData,
                        borderColor: '#ea580c',
                        backgroundColor: 'transparent',
                        borderDash: [6, 5],
                        tension: 0.3,
                        borderWidth: 2.5,
                        pointRadius: 5,
                        pointStyle: 'rectRot',
                        spanGaps: true,
                        fill: false,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { position: 'top', align: 'start', labels: { boxWidth: 12, usePointStyle: true, font: { size: 12 } } },
                    tooltip: { callbacks: { label: function (c) { return c.dataset.label + ': ' + (c.parsed.y === null ? '—' : c.parsed.y); } } }
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { grid: { color: '#eef1f4' }, ticks: { font: { size: 11 } } }
                }
            }
        });
    }

    // ---------- 数据增删改查 ----------
    function saveCell(input) {
        var id = input.dataset.id;
        var field = input.dataset.field;
        var value = input.value;
        fetch(apiUrl('/api/data/' + sheetKey + '/cell'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: parseInt(id, 10), field: field, value: value })
        }).then(function (r) { return r.json(); }).then(function (res) {
            if (res.ok) {
                input.classList.add('saved');
                setTimeout(function () { input.classList.remove('saved'); }, 600);
                if (field !== 'row_label') {
                    input.value = (res.value === null || res.value === undefined) ? '' : res.value;
                    var row = (DATA.rows || []).find(function (r2) { return String(r2.id) === String(id); });
                    if (row) row[field] = res.value;
                    softRefreshCharts();
                }
            } else {
                showToast('保存失败', 'error');
            }
        }).catch(function () { showToast('网络错误', 'error'); });
    }

    function softRefreshCharts() {
        renderLineChart();
    }

    function bindInlineEdit() {
        $all('.cell-input').forEach(function (input) {
            input.addEventListener('change', function () { saveCell(input); });
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') { input.blur(); }
            });
        });
        $all('.del-row').forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (!confirm('确认删除该行数据？')) return;
                var id = btn.dataset.id;
                fetch(apiUrl('/api/data/' + sheetKey + '/row/' + id), { method: 'DELETE' })
                    .then(function (r) { return r.json(); })
                    .then(function (res) {
                        if (res.ok) {
                            var tr = btn.closest('tr');
                            if (tr) tr.remove();
                            DATA.rows = (DATA.rows || []).filter(function (r2) { return String(r2.id) !== String(id); });
                            DATA.labels = (DATA.rows || []).map(function (r2) { return r2.row_label; });
                            softRefreshCharts();
                            refreshPredictions();
                            showToast('已删除', 'success');
                        } else {
                            showToast('删除失败', 'error');
                        }
                    }).catch(function () { showToast('网络错误', 'error'); });
            });
        });
    }

    function refreshPredictions() {
        fetch(apiUrl('/api/predict/' + sheetKey)).then(function (r) { return r.json(); }).then(function (d) {
            DATA.predictions = d.predictions || {};
            DATA.future_labels = d.future_labels || [];
            initPredictSelect();
        }).catch(function () {});
    }

    // ---------- 新增记录 ----------
    function bindAddRow() {
        var modal = $('#addModal');
        var openBtn = $('#addRowBtn');
        var closeBtn = $('#modalCloseBtn');
        var cancelBtn = $('#modalCancelBtn');
        var saveBtn = $('#modalSaveBtn');
        if (!openBtn) return;
        function open() {
            $('#newRowLabel').value = '';
            $all('.new-col-input').forEach(function (i) { i.value = ''; });
            modal.classList.add('show');
            setTimeout(function () { $('#newRowLabel').focus(); }, 50);
        }
        function close() { modal.classList.remove('show'); }
        openBtn.addEventListener('click', open);
        closeBtn.addEventListener('click', close);
        cancelBtn.addEventListener('click', close);
        modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
        saveBtn.addEventListener('click', function () {
            var payload = { row_label: $('#newRowLabel').value };
            $all('.new-col-input').forEach(function (i) {
                payload[i.dataset.field] = i.value;
            });
            fetch(apiUrl('/api/data/' + sheetKey + '/row'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(function (r) { return r.json(); }).then(function (res) {
                if (res.ok) {
                    showToast('已新增记录', 'success');
                    location.reload();
                } else {
                    showToast('保存失败', 'error');
                }
            }).catch(function () { showToast('网络错误', 'error'); });
        });
    }

    function bindRefreshChart() {
        var btn = $('#refreshChartBtn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            fetch(apiUrl('/api/data/' + sheetKey)).then(function (r) { return r.json(); }).then(function (d) {
                DATA.rows = d.rows;
                DATA.labels = (d.rows || []).map(function (r2) { return r2.row_label; });
                renderLineChart();
                refreshPredictions();
                showToast('图表已刷新', 'success');
            });
        });
    }

    // ---------- 启动 ----------
    document.addEventListener('DOMContentLoaded', function () {
        initColChips();
        renderLineChart();
        initPredictSelect();
        bindInlineEdit();
        bindAddRow();
        bindRefreshChart();
    });
})();
