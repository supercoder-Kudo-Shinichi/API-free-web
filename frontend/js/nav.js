/**
 * Navigation Auth State Manager.
 * Dynamically updates nav-actions based on authentication state.
 * Checks sessionStorage first for instant feedback, then updates after Auth.init().
 */
(function() {
    'use strict';

    const NAV_ACTIONS_SELECTOR = '.nav-actions';
    const TOKEN_KEY = 'authguard_access_token';

    /**
     * Render nav actions based on auth state.
     */
    function renderNavActions() {
        const navActions = document.querySelector(NAV_ACTIONS_SELECTOR);
        if (!navActions) return;

        // Check sessionStorage first for instant feedback
        const hasToken = !!sessionStorage.getItem(TOKEN_KEY);
        var user = null;
        var isAuthed = false;

        if (typeof Auth !== 'undefined' && Auth.isAuthenticated) {
            isAuthed = Auth.isAuthenticated();
        }
        if (typeof Auth !== 'undefined' && Auth.getUser) {
            user = Auth.getUser();
        }

        var loggedIn = isAuthed || (hasToken && user);

        if (loggedIn && user) {
            var displayName = user.displayName || user.username || 'User';
            var avatarLetter = displayName.charAt(0).toUpperCase();

            navActions.innerHTML = '' +
                '<a href="social.html" class="btn btn-ghost btn-sm" style="display:inline-flex;align-items:center;gap:4px;">' +
                    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>' +
                    'Social' +
                '</a>' +
                '<a href="dashboard.html" class="btn btn-ghost btn-sm nav-dashboard-btn">' +
                    '<span class="nav-user-avatar">' + avatarLetter + '</span>' +
                    'Dashboard' +
                '</a>' +
                '<button class="btn btn-primary btn-sm nav-logout-btn" onclick="handleNavLogout()">Sign Out</button>' +
                '<button class="nav-mobile-toggle" aria-label="Toggle menu">' +
                    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h18M3 6h18M3 18h18"/></svg>' +
                '</button>';
        } else {
            navActions.innerHTML = '' +
                '<a href="login.html" class="btn btn-ghost btn-sm">Sign In</a>' +
                '<a href="register.html" class="btn btn-primary btn-sm">Sign up</a>' +
                '<button class="nav-mobile-toggle" aria-label="Toggle menu">' +
                    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12h18M3 6h18M3 18h18"/></svg>' +
                '</button>';
        }

        // Re-bind mobile toggle
        var mobileToggle = navActions.querySelector('.nav-mobile-toggle');
        if (mobileToggle) {
            mobileToggle.addEventListener('click', function(e) {
                e.stopPropagation();
                var navLinks = document.querySelector('.nav-links');
                if (navLinks) {
                    navLinks.classList.toggle('mobile-open');
                }
            });
        }
    }

    /**
     * Global logout handler.
     */
    window.handleNavLogout = async function() {
        try {
            if (typeof Auth !== 'undefined' && Auth.logout) {
                await Auth.logout();
            } else {
                // Fallback if Auth module not available
                sessionStorage.removeItem(TOKEN_KEY);
                window.location.href = 'login.html';
            }
        } catch (err) {
            console.error('Logout failed:', err);
            sessionStorage.removeItem(TOKEN_KEY);
            window.location.href = 'login.html';
        }
    };

    /**
     * Initialize — try to load auth state and render nav.
     */
    function init() {
        // Immediate render based on sessionStorage (fast check)
        renderNavActions();

        // Wait for Auth module to be loaded
        function waitForAuth() {
            if (typeof Auth !== 'undefined' && Auth.init) {
                // Auth module loaded — call Auth.init() to verify token & fetch user
                Auth.init().then(function(authenticated) {
                    // Re-render after init completes (user data now available)
                    renderNavActions();
                    return authenticated;
                }).catch(function() {
                    // Not authenticated
                    renderNavActions();
                });

                // Subscribe to future auth state changes (login/logout in same tab)
                if (Auth.subscribe) {
                    Auth.subscribe(function() {
                        renderNavActions();
                    });
                }
            } else {
                // Auth not loaded yet (scripts load async?), retry
                setTimeout(waitForAuth, 50);
            }
        }

        // Start waiting
        waitForAuth();
    }

    // Run on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
