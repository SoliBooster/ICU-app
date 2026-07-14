// 搜索页：指标趋势折线图
(function () {
    var PALETTE = [
        '#0d9488', '#ea580c', '#7c3aed', '#db2777', '#2563eb',
        '#65a30d', '#0891b2', '#c026d3', '#f59e0b', '#059669'
    ];
    var charts = {};

    function colorFor(i) { return PALETTE[i % PALETTE.length]; }

    // 绑定所有 chart-toggle 按钮
    document.querySelectorAll('.chart-toggle').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var chartId = btn.dataset.chartId;
            var container = document.getElementById(chartId);
            if (!container) return;
            var isHidden = container.style.display === 'none';
            container.style.display = isHidden ? 'block' : 'none';
            btn.querySelector('span').textContent = isHidden ? '收起趋势图' : '查看趋势图';
            if (isHidden && !charts[chartId]) {
                renderSearchChart(chartId);
            }
        });
    });

    function renderSearchChart(containerId) {
        var container = document.getElementById(containerId);
        if (!container) return;
        var canvas = container.querySelector('canvas');
        if (!canvas) return;

        // 从父级 card 中读取表格数据
        var card = container.closest('.card');
        if (!card) return;
        var table = card.querySelector('.data-table');
        if (!table) return;

        // 解析表头，找到数值列（跳过 # 和 日期/编号）
        var headers = [];
        var headerCells = table.querySelectorAll('thead th');
        var numericColIdx = -1;
        headerCells.forEach(function (th, i) {
            var txt = th.textContent.trim();
            if (i === 0) return; // skip #
            if (i === 1) { headers.push('label'); return; } // date column
            headers.push(txt);
            numericColIdx = i;
        });

        // 解析数据
        var labels = [];
        var data = [];
        var tbody = table.querySelector('tbody');
        if (tbody) {
            tbody.querySelectorAll('tr').forEach(function (tr) {
                var cells = tr.querySelectorAll('td');
                if (cells.length < 3) return;
                var label = cells[1].textContent.trim();
                if (!label) return;
                labels.push(label);
                if (numericColIdx >= 0 && cells[numericColIdx]) {
                    var v = cells[numericColIdx].textContent.trim();
                    data.push(v === '—' || v === '' ? null : parseFloat(v));
                }
            });
        }

        if (labels.length < 2) {
            container.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--text-muted)">数据不足，无法绘制趋势图（至少需要 2 条数据）</div>';
            return;
        }

        var title = headers.length > 1 ? headers[1] : '数值';
        var color = colorFor(0);

        var ctx = canvas.getContext('2d');
        charts[containerId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: title,
                    data: data,
                    borderColor: color,
                    backgroundColor: color + '22',
                    tension: 0.3,
                    borderWidth: 2.5,
                    pointRadius: 4.5,
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
                                return c.parsed.y === null ? title + '：—' : title + '：' + c.parsed.y;
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
                        grid: { color: '#eef1f4' },
                        ticks: { font: { size: 11 } }
                    }
                }
            }
        });
    }

    // 工具函数
    function $(s, p) { return (p || document).querySelector(s); }
    function $all(s, p) { return Array.prototype.slice.call((p || document).querySelectorAll(s)); }
})();
