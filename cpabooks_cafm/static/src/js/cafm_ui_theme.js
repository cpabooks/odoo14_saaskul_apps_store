odoo.define("cpabooks_cafm.ui_theme", function (require) {
    "use strict";

    var THEME_KEY = "cpa_cafm_ui_theme";
    var LEGACY_KEY = "cpa_cafm_dashboard_theme";
    var LAYOUT_KEY = "cpa_cafm_nav_layout";
    var NAV_CLASS = "o_cpa_cafm_navbar_theme";

    function readTheme() {
        try {
            var session = require("web.session");
            if (session.cpabooks_leftsidebar_enabled) {
                return session.cpabooks_leftsidebar_color_mode === "dark" ? "dark" : "default";
            }
        } catch (sessErr) { /* ignore */ }
        try {
            var t = window.localStorage.getItem(THEME_KEY);
            if (t === "dark" || t === "default") {
                return t;
            }
            t = window.localStorage.getItem(LEGACY_KEY);
            if (t === "dark" || t === "default") {
                window.localStorage.setItem(THEME_KEY, t);
                return t;
            }
        } catch (e) { /* ignore */ }
        return "default";
    }

    function readLayout() {
        try {
            var session = require("web.session");
            if (session.cpabooks_leftsidebar_nav_layout === "topbar" ||
                    session.cpabooks_leftsidebar_nav_layout === "sidebar") {
                return session.cpabooks_leftsidebar_nav_layout;
            }
        } catch (e) { /* ignore */ }
        return "topbar";
    }

    function setLayout(layout) {
        try {
            var nav = require("cpabooks_leftsidebar_view.shell");
            if (nav && nav.requestSyncSidebar) {
                nav.requestSyncSidebar(true);
            }
        } catch (e) { /* ignore */ }
        return layout === "sidebar" ? "sidebar" : "topbar";
    }

    function applyUiTheme(theme) {
        theme = theme === "dark" ? "dark" : "default";
        var body = document.body;
        if (!body) {
            return theme;
        }
        body.classList.remove("o_cafm_ui_default", "o_cafm_ui_dark");
        body.classList.add(theme === "dark" ? "o_cafm_ui_dark" : "o_cafm_ui_default");
        try {
            window.localStorage.setItem(THEME_KEY, theme);
            window.localStorage.setItem(LEGACY_KEY, theme);
        } catch (e) { /* ignore */ }

        var $root = $(".cfd_root, .o_cfd_dashboard_main");
        if ($root.length) {
            $root.removeClass("cpa-cafm-theme-default cpa-cafm-theme-dark")
                .addClass(theme === "dark" ? "cpa-cafm-theme-dark" : "cpa-cafm-theme-default");
        }
        return theme;
    }

    function injectNavbarThemeToggle() {
        // Navbar Dark/Default moved to cpabooks_leftsidebar_view control-panel buttons.
        $(".o_main_navbar ." + NAV_CLASS).remove();
    }

    function syncNavbarToggleState() {
        return readTheme();
    }

    function syncShellTheme() {
        injectNavbarThemeToggle();
        return applyUiTheme(readTheme());
    }

    return {
        THEME_KEY: THEME_KEY,
        LAYOUT_KEY: LAYOUT_KEY,
        readTheme: readTheme,
        readLayout: readLayout,
        setLayout: setLayout,
        applyUiTheme: applyUiTheme,
        injectNavbarThemeToggle: injectNavbarThemeToggle,
        syncShellTheme: syncShellTheme,
        syncNavbarToggleState: syncNavbarToggleState,
    };
});
