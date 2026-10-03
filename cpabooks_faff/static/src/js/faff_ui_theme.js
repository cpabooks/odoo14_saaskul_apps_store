odoo.define("cpabooks_faff.ui_theme", function (require) {
    "use strict";

    /**
     * FAFF UI theme (Default = light, Dark = fire/red shell).
     * Persists in localStorage; navbar Dark / Default toggle like CAFM.
     */
    var THEME_KEY = "cpa_faff_ui_theme";
    var NAV_CLASS = "o_cpa_faff_navbar_theme";

    function readTheme() {
        try {
            var t = window.localStorage.getItem(THEME_KEY);
            if (t === "dark" || t === "default") {
                return t;
            }
        } catch (e) { /* ignore */ }
        return "default";
    }

    function applyUiTheme(theme) {
        theme = theme === "dark" ? "dark" : "default";
        var body = document.body;
        if (!body) {
            return theme;
        }
        body.classList.remove("o_faff_ui_default", "o_faff_ui_dark");
        body.classList.add(theme === "dark" ? "o_faff_ui_dark" : "o_faff_ui_default");
        try {
            window.localStorage.setItem(THEME_KEY, theme);
        } catch (e) { /* ignore */ }

        var $btns = $(".cpa-faff-theme-btn");
        $btns.removeClass("active");
        $btns.filter('[data-theme="' + theme + '"]').addClass("active");
        return theme;
    }

    function injectNavbarThemeToggle() {
        var $nav = $(".o_main_navbar");
        if (!$nav.length) {
            return;
        }
        $nav.find("." + NAV_CLASS).remove();
        if (!$("body").hasClass("o_faff_dark_shell")) {
            return;
        }
        var theme = readTheme();
        var $wrap = $(
            '<div class="' + NAV_CLASS + ' cpa-faff-theme-toggle" role="group" aria-label="FAFF theme">' +
            '<button type="button" class="cpa-faff-theme-btn" data-theme="dark"><i class="fa fa-moon-o"/> Dark</button>' +
            '<button type="button" class="cpa-faff-theme-btn" data-theme="default"><i class="fa fa-sun-o"/> Default</button>' +
            "</div>"
        );
        var $brand = $nav.find(".o_menu_brand").first();
        if ($brand.length) {
            $brand.after($wrap);
        } else {
            $nav.prepend($wrap);
        }
        $wrap.on("click", ".cpa-faff-theme-btn", function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            applyUiTheme(ev.currentTarget.getAttribute("data-theme"));
            try {
                $(window).trigger("faff_ui_theme_changed", [readTheme()]);
            } catch (e) { /* ignore */ }
        });
        $wrap.find('.cpa-faff-theme-btn[data-theme="' + theme + '"]').addClass("active");
    }

    function syncShellTheme() {
        if (!$("body").hasClass("o_faff_dark_shell")) {
            $(".o_main_navbar ." + NAV_CLASS).remove();
            document.body.classList.remove("o_faff_ui_default", "o_faff_ui_dark");
            return readTheme();
        }
        var theme = applyUiTheme(readTheme());
        injectNavbarThemeToggle();
        return theme;
    }

    return {
        THEME_KEY: THEME_KEY,
        readTheme: readTheme,
        applyUiTheme: applyUiTheme,
        injectNavbarThemeToggle: injectNavbarThemeToggle,
        syncShellTheme: syncShellTheme,
    };
});
