/**
 * Theme Switcher - 7 Color Schemes
 * Lưu theme vào localStorage + backend backup (khi đã đăng nhập)
 * Khi load web: ưu tiên theme từ backend, fallback localStorage, cuối cùng 'white'
 */
(function() {
    'use strict';

    const THEME_KEY = 'chuotchat_theme';
    const DEFAULT_THEME = 'white';

    // 14 themes data - pastel palette
    const THEMES = [
        { id: 'blue', label: 'Xanh dương pastel', rgb: '(122, 181, 240)' },
        { id: 'darkgreen', label: 'Xanh lá pastel', rgb: '(126, 207, 122)' },
        { id: 'yellowgreen', label: 'Vàng xanh pastel', rgb: '(197, 217, 117)' },
        { id: 'lightgreen', label: 'Xanh lá nhạt pastel', rgb: '(212, 230, 160)' },
        { id: 'olive', label: 'Ô liu pastel', rgb: '(168, 196, 138)' },
        { id: 'black', label: 'Đen', rgb: '(0, 0, 0)' },
        { id: 'white', label: 'Trắng', rgb: '(255, 255, 255)' },
        { id: 'skyblue', label: 'Xanh bầu trời', rgb: '(184, 225, 255)' },
        { id: 'rose', label: 'Hồng', rgb: '(233, 141, 158)' },
        { id: 'blush', label: 'Hồng phấn', rgb: '(255, 220, 227)' },
        { id: 'beige', label: 'Be', rgb: '(238, 220, 206)' },
        { id: 'steelblue', label: 'Xanh thép', rgb: '(88, 131, 173)' },
        { id: 'lavender', label: 'Oải hương', rgb: '(97, 92, 132)' },
        { id: 'coral', label: 'San hô', rgb: '(255, 154, 162)' },
    ];

    /**
     * Apply theme to document
     */
    function setTheme(themeId) {
        document.documentElement.setAttribute('data-theme', themeId);
        try {
            localStorage.setItem(THEME_KEY, themeId);
        } catch (e) {}
        
        // Update active state in panel
        document.querySelectorAll('.theme-option').forEach(function(el) {
            el.classList.toggle('active', el.dataset.theme === themeId);
        });
    }

    /**
     * Get saved theme from localStorage
     */
    function getLocalTheme() {
        try {
            return localStorage.getItem(THEME_KEY) || DEFAULT_THEME;
        } catch (e) {
            return DEFAULT_THEME;
        }
    }

    /**
     * Load theme from backend API (nếu đã đăng nhập)
     * Ưu tiên: backend > localStorage > 'white'
     */
    async function loadThemeFromBackend() {
        try {
            if (typeof ApiClient === 'undefined' || !ApiClient.getAccessToken()) {
                return null;
            }
            var data = await ApiClient.get(CONFIG.ENDPOINTS.THEME);
            if (data.success && data.theme) {
                return data.theme;
            }
        } catch (e) {
            // Silent fail - fallback to localStorage
        }
        return null;
    }

    /**
     * Save theme to backend API
     */
    async function saveThemeToBackend(themeId) {
        try {
            if (typeof ApiClient === 'undefined' || !ApiClient.getAccessToken()) {
                return;
            }
            await ApiClient.put(CONFIG.ENDPOINTS.THEME, { theme: themeId });
        } catch (e) {
            // Silent fail - theme still saved in localStorage
        }
    }

    /**
     * Build theme panel HTML
     */
    function buildThemePanel() {
        var currentTheme = getLocalTheme();
        
        var html = '<div class="theme-panel-overlay" id="theme-panel-overlay"></div>';
        html += '<div class="theme-panel" id="theme-panel">';
        html += '  <div class="theme-panel-header">';
        html += '    <div class="theme-panel-title">🎨 Chọn giao diện</div>';
        html += '    <button class="theme-panel-close" onclick="closeThemePanel()">&times;</button>';
        html += '  </div>';
        html += '  <div class="theme-grid">';
        
        THEMES.forEach(function(t) {
            var isActive = t.id === currentTheme ? ' active' : '';
            html += '    <div class="theme-option' + isActive + '" data-theme="' + t.id + '" onclick="switchTheme(\'' + t.id + '\')">';
            html += '      <div class="theme-swatch theme-swatch-' + t.id + '"></div>';
            html += '      <div class="theme-label">' + t.label + '</div>';
            html += '    </div>';
        });
        
        html += '  </div>';
        html += '</div>';
        
        return html;
    }

    /**
     * Open theme panel
     */
    window.openThemePanel = function() {
        var overlay = document.getElementById('theme-panel-overlay');
        var panel = document.getElementById('theme-panel');
        if (overlay && panel) {
            overlay.classList.add('active');
            panel.classList.add('active');
        }
    };

    /**
     * Close theme panel
     */
    window.closeThemePanel = function() {
        var overlay = document.getElementById('theme-panel-overlay');
        var panel = document.getElementById('theme-panel');
        if (overlay && panel) {
            overlay.classList.remove('active');
            panel.classList.remove('active');
        }
    };

    /**
     * Switch to a theme
     */
    window.switchTheme = function(themeId) {
        setTheme(themeId);
        // Lưu lên backend (nếu đã đăng nhập)
        saveThemeToBackend(themeId);
        // Close panel after brief delay for visual feedback
        setTimeout(closeThemePanel, 300);
    };

    /**
     * Create and inject theme panel HTML into body
     */
    function injectThemePanel() {
        if (document.getElementById('theme-panel')) return; // already injected
        var panelHtml = buildThemePanel();
        var panelContainer = document.createElement('div');
        panelContainer.innerHTML = panelHtml;
        document.body.appendChild(panelContainer.firstElementChild);
        document.body.appendChild(panelContainer.lastElementChild);
        
        var overlay = document.getElementById('theme-panel-overlay');
        if (overlay) {
            overlay.addEventListener('click', closeThemePanel);
        }
    }

    /**
     * Create a theme switcher button and add to container
     */
    function createThemeButton(container) {
        if (!container || container.querySelector('.theme-switcher-btn')) return;
        var themeBtn = document.createElement('button');
        themeBtn.className = 'theme-switcher-btn';
        themeBtn.setAttribute('onclick', 'openThemePanel()');
        themeBtn.setAttribute('title', 'Chọn giao diện');
        themeBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>';
        container.appendChild(themeBtn);
    }

    /**
     * Add theme switcher button to all navigation bars
     */
    function addThemeButton() {
        injectThemePanel();
        
        var selectors = [
            '.nav-links',             // landing page
            '.topbar-left',           // dashboard
            '.social-page-nav .nav-left', // social page
            '.sidebar-footer',        // dashboard sidebar bottom
        ];
        
        selectors.forEach(function(sel) {
            var containers = document.querySelectorAll(sel);
            containers.forEach(function(container) {
                createThemeButton(container);
            });
        });
    }

    /**
     * Init theme on page load
     */
    function init() {
        // Bước 1: Áp dụng theme từ localStorage ngay lập tức (tránh flash)
        var localTheme = getLocalTheme();
        setTheme(localTheme);
        
        // Bước 2: Thêm nút theme và panel sau khi DOM sẵn sàng
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', addThemeButton);
        } else {
            addThemeButton();
        }
        
        // Bước 3: Load theme từ backend (nếu đã đăng nhập) và ghi đè
        // Chờ một chút để ApiClient có thể được init bởi script khác
        setTimeout(function() {
            loadThemeFromBackend().then(function(backendTheme) {
                if (backendTheme && backendTheme !== getLocalTheme()) {
                    setTheme(backendTheme);
                }
            });
        }, 500);
    }

    init();
})();