// 共享逻辑：侧边栏移动端切换
(function () {
    var toggle = document.getElementById('menuToggle');
    var sidebar = document.querySelector('.sidebar');
    var overlay = document.getElementById('overlay');
    if (!toggle || !sidebar) return;
    function open() {
        sidebar.classList.add('open');
        if (overlay) overlay.classList.add('show');
    }
    function close() {
        sidebar.classList.remove('open');
        if (overlay) overlay.classList.remove('show');
    }
    toggle.addEventListener('click', function () {
        if (sidebar.classList.contains('open')) { close(); } else { open(); }
    });
    if (overlay) overlay.addEventListener('click', close);
})();

// AJAX 请求 URL 辅助函数
function apiUrl(path) {
    return path;
}
