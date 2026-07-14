// 分表页：图表渲染 + 数据增删改查 + 参考范围
(function () {
    var sheetKey = document.getElementById('sheetKey').value;
    var raw = document.getElementById('chartData').value;
    var refRaw = document.getElementById('refRanges').value;
    var DATA = {};
    var REFS = {};
    try { DATA = JSON.parse(raw); } catch (e) { console.error('chart data parse error', e); }
    try { REFS = JSON.parse(refRaw); } catch (e) { /* no refs */ }

    var PALETTE = [
        '#0d9488', '#ea580c', '#7c3aed', '#db2777', '#2563eb',
        '#65a30d', '#0891b2', '#c026d3', '#f59e0b', '#059669',
        '#e11d48', '#4f46e5', '#0284c7', '#ca8a04', '#16a34a',
        '#9333ea', '#dc2626', '#0d9488', '#92400e', '#1d4ed8'
    ];

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

    var selectedCols = [];
    var predictCol = null;
    var lineCharts = [];
    var predictChart = null;

    // ---------- 参考范围辅助 ----------
    function getRef(key) { return REFS[key] || {}; }
    function getRefMin(key) { var r = getRef(key); return r.ref_min !== undefined && r.ref_min !== null ? r.ref_min : null; }
    function getRefMax(key) { var r = getRef(key); return r.ref_max !== undefined && r.ref_max !== null ? r.ref_max : null; }
    function hasRef(key) { return getRefMin(key) !== null || getRefMax(key) !== null; }

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
        if (selectedCols.length > 6) selectedCols.shift();
        syncChips();
        renderLineChart();
    }

    // ---------- 合并参考范围区域到 Chart.js 配置 ----------
    function makeRefZonePlugin(refMin, refMax, chartColor) {
        if (refMin === null && refMax === null) return null;
        var yMin = refMin !== null ? refMin : -Infinity;
        var yMax = refMax !== null ? refMax : Infinity;
        return {
            id: 'refZone_' + Math.random(),
            beforeDraw: function (chart) {
                var yScale = chart.scales.y;
                var xScale = chart.scales.x;
                var ctx = chart.ctx;
                if (!yScale || !xScale) return;

                var pixelMin = (refMin !== null) ? yScale.getPixelForValue(refMin) : xScale.top;
                var pixelMax = (refMax !== null) ? yScale.getPixelForValue(refMax) : yScale.bottom;
                if (refMin === null) pixelMin = xScale.top;
                if (refMax === null) pixelMax = yScale.bottom;

                var top = Math.min(pixelMin, pixelMax);
                var height = Math.abs(pixelMax - pixelMin);
                if (height < 1) return;

                ctx.save();
                ctx.fillStyle = 'rgba(13, 148, 136, 0.08)';
                ctx.fillRect(xScale.left, top, xScale.right - xScale.left, height);
                ctx.restore();
            }
        };
    }

    // ---------- 折线图 ----------
    function renderLineChart() {
        var container = $('#lineChartContainer');
        if (!container) return;

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

            var data = (DATA.rows || []).map(function (r) { return num(r[key]); });
            var valid = data.filter(function (v) { return v !== null; });
            var dataMin = valid.length ? Math.min.apply(null, valid) : 0;
            var dataMax = valid.length ? Math.max.apply(null, valid) : 1;
            var range = dataMax - dataMin || 1;
            var pad = range * 0.15;
            var yMin = Math.max(0, dataMin - pad);
            var yMax = dataMax + pad;

            // 参考范围影响 y 轴范围
            var rr = REFS[key] || {};
            if (rr.ref_min !== null && rr.ref_min !== undefined && rr.ref_min < yMin) yMin = rr.ref_min - pad;
            if (rr.ref_max !== null && rr.ref_max !== undefined && rr.ref_max > yMax) yMax = rr.ref_max + pad;

            var plugins = [];
            if (hasRef(key)) {
                var plugin = makeRefZonePlugin(getRefMin(key), getRefMax(key), chartColor);
                if (plugin) plugins.push(plugin);
            }

            var chart = new Chart(canvas, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: colName,
                        data: data,
                        borderColor: chartColor,
                        backgroundColor: 'transparent',
                        tension: 0.32,
                        borderWidth: 2.5,
                        pointRadius: 4.5,
                        pointHoverRadius: 7,
                        pointBackgroundColor: chartColor,
                        spanGaps: true,
                        fill: false,
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
                                    var txt = c.parsed.y === null ? colName + '：—' : colName + '：' + c.parsed.y;
                                    var rr2 = REFS[key] || {};
                                    if (rr2.ref_min !== null && rr2.ref_min !== undefined) txt += ' (下限' + rr2.ref_min + ')';
                                    if (rr2.ref_max !== null && rr2.ref_max !== undefined) txt += ' (上限' + rr2.ref_max + ')';
                                    return txt;
                                }
                            }
                        }
                    },
                    scales: {
                        x: { grid: { display: false }, ticks: { font: { size: 11 }, maxRotation: 45 } },
                        y: {
                            min: yMin, max: yMax,
                            grid: { color: '#eef1f4' },
                            ticks: { font: { size: 11 } }
                        }
                    }
                },
                plugins: plugins
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
        if (histLabels.length > 0) {
            predData[histLabels.length - 1] = p.history[histLabels.length - 1];
        }
        var idx = (DATA.columns || []).findIndex(function (c) { return c.key === predictCol; });
        var col = colorFor(idx);

        var plugins = [];
        if (predictCol && hasRef(predictCol)) {
            var plugin = makeRefZonePlugin(getRefMin(predictCol), getRefMax(predictCol), col);
            if (plugin) plugins.push(plugin);
        }

        if (predictChart) predictChart.destroy();
        predictChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: allLabels,
                datasets: [
                    { label: '历史数据', data: histData, borderColor: col, backgroundColor: 'transparent', tension: 0.3, borderWidth: 2.5, pointRadius: 5, spanGaps: true, fill: false },
                    { label: '预测趋势', data: predData, borderColor: '#ea580c', backgroundColor: 'transparent', borderDash: [6, 5], tension: 0.3, borderWidth: 2.5, pointRadius: 5, pointStyle: 'rectRot', spanGaps: true, fill: false }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { position: 'top', align: 'start', labels: { boxWidth: 12, usePointStyle: true, font: { size: 12 } } },
                    tooltip: { callbacks: { label: function (c) { return c.dataset.label + ': ' + (c.parsed.y === null ? '—' : c.parsed.y); } } }
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { grid: { color: '#eef1f4' }, ticks: { font: { size: 11 } } }
                }
            },
            plugins: plugins
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
            } else { showToast('保存失败', 'error'); }
        }).catch(function () { showToast('网络错误', 'error'); });
    }

    function bindInlineEdit() {
        $all('.num-input, .label-input').forEach(function (input) {
            var timer;
            function save() { clearTimeout(timer); timer = setTimeout(function () { saveCell(input); }, 400); }
            input.addEventListener('change', save);
            input.addEventListener('blur', save);
            input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { clearTimeout(timer); saveCell(input); input.blur(); } });
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
                        } else { showToast('删除失败', 'error'); }
                    }).catch(function () { showToast('网络错误', 'error'); });
            });
        });
    }

    function softRefreshCharts() {
        renderLineChart();
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
            $all('.new-col-input').forEach(function (i) { payload[i.dataset.field] = i.value; });
            fetch(apiUrl('/api/data/' + sheetKey + '/row'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(function (r) { return r.json(); }).then(function (res) {
                if (res.ok) { showToast('已新增记录', 'success'); location.reload(); }
                else { showToast('保存失败', 'error'); }
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

    // ---------- 添加指标 ----------
    function bindAddCol() {
        var modal = $('#addColModal');
        var openBtn = $('#addColBtn');
        if (!openBtn) return;
        var closeBtn = $('#addColCloseBtn');
        var cancelBtn = $('#addColCancelBtn');
        var saveBtn = $('#addColSaveBtn');

        function open() {
            $('#newColName').value = '';
            $('#newColType').value = 'numeric';
            modal.classList.add('show');
            setTimeout(function () { $('#newColName').focus(); }, 50);
        }
        function close() { modal.classList.remove('show'); }
        openBtn.addEventListener('click', open);
        closeBtn.addEventListener('click', close);
        cancelBtn.addEventListener('click', close);
        modal.addEventListener('click', function (e) { if (e.target === modal) close(); });
        saveBtn.addEventListener('click', function () {
            var name = $('#newColName').value.trim();
            var colType = $('#newColType').value;
            if (!name) { showToast('请输入指标名称', 'error'); return; }
            saveBtn.disabled = true;
            saveBtn.textContent = '添加中…';
            fetch(apiUrl('/api/columns/' + sheetKey + '/add'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, type: colType })
            }).then(function (r) { return r.json(); }).then(function (res) {
                if (res.ok) { showToast('指标 "' + name + '" 已添加', 'success'); location.reload(); }
                else { showToast(res.error || '添加失败', 'error'); saveBtn.disabled = false; saveBtn.textContent = '添加'; }
            }).catch(function () { showToast('网络错误', 'error'); saveBtn.disabled = false; saveBtn.textContent = '添加'; });
        });
    }

    // ---------- 导出 CSV ----------
    function bindExport() {
        var btn = $('#exportBtn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            window.location.href = apiUrl('/api/export/' + sheetKey);
        });
    }

    // ---------- 参考范围设置 ----------
    function bindRefRange() {
        var modal = $('#refModal');
        var closeBtn = $('#refCloseBtn');
        var cancelBtn = $('#refCancelBtn');
        var clearBtn = $('#refClearBtn');
        var saveBtn = $('#refSaveBtn');

        if (!modal) return;

        var currentCol = null;

        // 绑定所有参考范围设置按钮
        $all('.ref-set-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                currentCol = {
                    key: btn.dataset.col,
                    display: btn.dataset.display,
                    min: btn.dataset.min,
                    max: btn.dataset.max,
                };
                $('#refColDisplay').textContent = '设置 "' + currentCol.display + '" 的参考范围';
                $('#refColKey').value = currentCol.key;
                $('#refMinInput').value = currentCol.min || '';
                $('#refMaxInput').value = currentCol.max || '';
                modal.classList.add('show');
                setTimeout(function () { $('#refMinInput').focus(); }, 50);
            });
        });

        function close() { modal.classList.remove('show'); currentCol = null; }
        closeBtn.addEventListener('click', close);
        cancelBtn.addEventListener('click', close);
        modal.addEventListener('click', function (e) { if (e.target === modal) close(); });

        clearBtn.addEventListener('click', function () {
            if (!currentCol) return;
            // 发送空值清除参考范围
            saveRef(null, null);
        });

        saveBtn.addEventListener('click', function () {
            if (!currentCol) return;
            var min = $('#refMinInput').value.trim();
            var max = $('#refMaxInput').value.trim();
            saveRef(min || null, max || null);
        });

        function saveRef(min, max) {
            if (!currentCol) return;
            fetch(apiUrl('/api/refs/' + sheetKey), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ col_key: currentCol.key, ref_min: min, ref_max: max })
            }).then(function (r) { return r.json(); }).then(function (res) {
                if (res.ok) {
                    showToast('参考范围已保存', 'success');
                    location.reload();
                } else { showToast(res.error || '保存失败', 'error'); }
            }).catch(function () { showToast('网络错误', 'error'); });
        }
    }

    // ---------- 启动 ----------
    document.addEventListener('DOMContentLoaded', function () {
        initColChips();
        renderLineChart();
        initPredictSelect();
        bindInlineEdit();
        bindAddRow();
        bindAddCol();
        bindExport();
        bindRefRange();
        bindRefreshChart();
    });
})();
