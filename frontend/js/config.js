/**
 * Authentication Service - Frontend Configuration
 * 
 * Chỉ cần thay đổi API_BASE_URL là có thể kết nối với Backend thật.
 * Override bằng window.__API_BASE_URL trước khi script load.
 */

const DEFAULT_API_BASE_URL = window.__API_BASE_URL || (window.location && window.location.origin ? window.location.origin : '');

const CONFIG = {
    API_BASE_URL: DEFAULT_API_BASE_URL,

    TOKEN: {
        ACCESS_TOKEN_KEY: 'authguard_access_token',
        REFRESH_TOKEN_KEY: 'authguard_refresh_token',
    },

    ENDPOINTS: {
        REGISTER: '/api/auth/register',
        LOGIN: '/api/auth/login',
        GOOGLE: '/api/auth/google',
        LOGOUT: '/api/auth/logout',
        LOGOUT_ALL: '/api/auth/logout-all',
        REFRESH: '/api/auth/refresh',
        ME: '/api/auth/me',
        VERIFY: '/api/auth/verify',
        CHECK_USERNAME: '/api/auth/check-username',
        CHECK_EMAIL: '/api/auth/check-email',
        LINK_GOOGLE: '/api/auth/link-google',
        UNLINK_GOOGLE: '/api/auth/unlink-google',
        UPDATE_PROFILE: '/api/auth/me',
        CHANGE_PASSWORD: '/api/auth/change-password',
        SESSIONS: '/api/auth/me',
        PROVIDERS: '/api/auth/me',
    },

    APP: {
        NAME: 'AuthGuard',
        TAGLINE: 'Enterprise Authentication Made Simple',
    },

    GOOGLE: {
        CLIENT_ID: '648734465354-641229rk3kehq9rhmc10lfhcticrf2hr.apps.googleusercontent.com',
        SCOPE: 'openid email profile',
    },

    PAYMENT: {
        REQUEST: '/api/purchase/request',
        REQUESTS: '/api/purchase/requests',
        PACKAGE: '/api/purchase/package',
        REUPLOAD: '/api/purchase/request',
    },

    ADMIN: {
        USERS: '/api/admin/users',
        PENDING_REQUESTS: '/api/admin/pending-requests',
        APPROVE: '/api/admin/approve',
        REJECT: '/api/admin/reject',
    }
};
