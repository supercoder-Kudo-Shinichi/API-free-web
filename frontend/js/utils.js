/**
 * Shared utility functions for the Authentication Service frontend.
 */
const Utils = {
    /**
     * Format a date string to GMT+7 (Asia/Bangkok) timezone (24h format).
     */
    formatDate(dateString) {
        if (!dateString) return 'N/A';
        const date = new Date(dateString);
        // Convert to GMT+7 manually for reliable 24h display
        const utcMs = date.getTime();
        const gmt7Ms = utcMs + (7 * 60 * 60 * 1000);
        const gmt7 = new Date(gmt7Ms);
        
        const year = gmt7.getUTCFullYear();
        const month = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][gmt7.getUTCMonth()];
        const day = String(gmt7.getUTCDate()).padStart(2, '0');
        const hour = String(gmt7.getUTCHours()).padStart(2, '0');
        const minute = String(gmt7.getUTCMinutes()).padStart(2, '0');
        
        return `${month} ${day}, ${year}, ${hour}:${minute}`;
    },

    /**
     * Mask an API key for display: ak_live_xxxxx********
     */
    maskApiKey(key) {
        if (!key) return '';
        if (key.length <= 15) return key;
        const prefix = key.substring(0, 15);
        return prefix + '*'.repeat(8);
    },

    /**
     * Copy text to clipboard.
     */
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (err) {
            // Fallback
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            return true;
        }
    },

    /**
     * Show a toast notification.
     */
    showToast(message, type = 'success', duration = 4000) {
        const container = document.getElementById('toast-container');
        if (!container) {
            const div = document.createElement('div');
            div.id = 'toast-container';
            div.className = 'toast-container';
            document.body.appendChild(div);
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-icon">
                ${type === 'success' ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 12l2 2 4-4"/></svg>' : ''}
                ${type === 'error' ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M15 9l-6 6M9 9l6 6"/></svg>' : ''}
                ${type === 'info' ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>' : ''}
            </div>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
        `;

        const containerEl = document.getElementById('toast-container');
        containerEl.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('toast-hiding');
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },

    /**
     * Debounce function for search/input handlers.
     */
    debounce(func, wait = 300) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    /**
     * Validate email (Gmail only).
     */
    isValidGmail(email) {
        return /^[a-z0-9._%+-]+@gmail\.com$/i.test(email.trim());
    },

    /**
     * Validate username.
     */
    isValidUsername(username) {
        return /^[a-zA-Z0-9_]{3,20}$/.test(username);
    },

    /**
     * Validate password strength.
     */
    isValidPassword(password) {
        return password && password.length >= 8;
    },

    /**
     * Get query parameter from URL.
     */
    getQueryParam(name) {
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get(name);
    },

    /**
     * Escape HTML to prevent XSS.
     */
    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },
};
