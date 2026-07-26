/**
 * REST API Client for Authentication Service Backend.
 * 
 * Handles:
 * - Automatic token injection
 * - 401 auto-refresh token
 * - JSON serialization/deserialization
 * - Error normalization
 */
const ApiClient = {
    _accessToken: null,
    _refreshPromise: null,
    _defaultTimeoutMs: 20000,

    /**
     * Initialize with access token from memory.
     */
    init(accessToken) {
        this._accessToken = accessToken;
    },

    /**
     * Get current access token.
     */
    getAccessToken() {
        return this._accessToken;
    },

    /**
     * Set access token (after login/refresh).
     */
    setAccessToken(token) {
        this._accessToken = token;
    },

    /**
     * Clear access token (on logout).
     */
    clearAccessToken() {
        this._accessToken = null;
        if (typeof sessionStorage !== 'undefined') {
            sessionStorage.removeItem(CONFIG.TOKEN.ACCESS_TOKEN_KEY);
        }
    },

    /**
     * Build full URL for an endpoint.
     */
    _url(endpoint) {
        const base = CONFIG.API_BASE_URL.replace(/\/+$/, '');
        const path = endpoint.startsWith('/') ? endpoint : '/' + endpoint;
        return base + path;
    },

    /**
     * Core request method.
     */
    async _request(endpoint, options = {}) {
        const url = this._url(endpoint);
        const headers = {
            'Content-Type': 'application/json',
            ...options.headers,
        };

        // Attach access token if available
        if (this._accessToken) {
            headers['Authorization'] = `Bearer ${this._accessToken}`;
        }

        const timeoutMs = options.timeoutMs || this._defaultTimeoutMs;
        const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
        const timeoutId = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;

        const fetchOptions = {
            method: options.method || 'GET',
            headers,
            credentials: 'include', // Send cookies (refresh_token)
        };

        if (controller) {
            fetchOptions.signal = controller.signal;
        }

        if (options.body) {
            fetchOptions.body = JSON.stringify(options.body);
        }

        let response;
        try {
            response = await fetch(url, fetchOptions);
        } catch (err) {
            if (err && err.name === 'AbortError') {
                throw { success: false, code: 'TIMEOUT', message: 'The server is taking too long to respond. Please try again.' };
            }
            throw { success: false, code: 'NETWORK_ERROR', message: 'Cannot connect to server. Please check your connection.' };
        } finally {
            if (timeoutId) clearTimeout(timeoutId);
        }

        // Handle 401 - try token refresh
        if (response.status === 401 && !options._isRetry) {
            const refreshed = await this._tryRefresh();
            if (refreshed) {
                return this._request(endpoint, { ...options, _isRetry: true });
            }
        }

        // Parse response
        let data;
        try {
            data = await response.json();
        } catch (err) {
            data = { success: false, code: 'PARSE_ERROR', message: 'Invalid server response.' };
        }

        if (!response.ok) {
            throw data;
        }

        return data;
    },

    /**
     * Try to refresh the access token using the HttpOnly cookie.
     */
    async _tryRefresh() {
        if (this._refreshPromise) {
            return this._refreshPromise;
        }

        this._refreshPromise = this._request(CONFIG.ENDPOINTS.REFRESH, {
            method: 'POST',
            _isRetry: true,
        })
        .then(data => {
            if (data.success && data.accessToken) {
                this._accessToken = data.accessToken;
                if (typeof sessionStorage !== 'undefined') {
                    sessionStorage.setItem(CONFIG.TOKEN.ACCESS_TOKEN_KEY, data.accessToken);
                }
                return true;
            }
            this._accessToken = null;
            if (typeof sessionStorage !== 'undefined') {
                sessionStorage.removeItem(CONFIG.TOKEN.ACCESS_TOKEN_KEY);
            }
            return false;
        })
        .catch(() => {
            this._accessToken = null;
            if (typeof sessionStorage !== 'undefined') {
                sessionStorage.removeItem(CONFIG.TOKEN.ACCESS_TOKEN_KEY);
            }
            return false;
        })
        .finally(() => {
            this._refreshPromise = null;
        });

        return this._refreshPromise;
    },

    // === Convenience Methods ===

    get(endpoint, headers = {}) {
        return this._request(endpoint, { method: 'GET', headers });
    },

    post(endpoint, body = {}, headers = {}) {
        return this._request(endpoint, { method: 'POST', body, headers });
    },

    put(endpoint, body = {}, headers = {}) {
        return this._request(endpoint, { method: 'PUT', body, headers });
    },

    delete(endpoint, headers = {}) {
        return this._request(endpoint, { method: 'DELETE', headers });
    },

    // === Auth-specific API Calls ===

    register(username, email, password) {
        return this.post(CONFIG.ENDPOINTS.REGISTER, { username, email, password });
    },

    login(usernameOrEmail, password) {
        return this.post(CONFIG.ENDPOINTS.LOGIN, { usernameOrEmail, password });
    },

    googleLogin(idToken) {
        return this.post(CONFIG.ENDPOINTS.GOOGLE, { idToken });
    },

    logout() {
        return this.post(CONFIG.ENDPOINTS.LOGOUT);
    },

    logoutAll() {
        return this.post(CONFIG.ENDPOINTS.LOGOUT_ALL);
    },

    getMe() {
        return this.get(CONFIG.ENDPOINTS.ME);
    },

    verifySession() {
        return this.post(CONFIG.ENDPOINTS.VERIFY);
    },

    checkUsername(username) {
        return this.post(CONFIG.ENDPOINTS.CHECK_USERNAME, { username });
    },

    checkEmail(email) {
        return this.post(CONFIG.ENDPOINTS.CHECK_EMAIL, { email });
    },

    updateProfile(data) {
        return this.put(CONFIG.ENDPOINTS.UPDATE_PROFILE, data);
    },

    changePassword(currentPassword, newPassword) {
        return this.post(CONFIG.ENDPOINTS.CHANGE_PASSWORD, {
            currentPassword,
            newPassword,
        });
    },

    linkGoogle(idToken) {
        return this.post(CONFIG.ENDPOINTS.LINK_GOOGLE, { idToken });
    },

    unlinkGoogle() {
        return this.post(CONFIG.ENDPOINTS.UNLINK_GOOGLE);
    },
};
