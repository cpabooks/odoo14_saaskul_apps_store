odoo.define("cpabooks_cafm.shell", function (require) {
    "use strict";

    /**
     * CAFM chrome (left sidebar / dark shell) lives in cpabooks_leftsidebar_view.
     * Keep brand helpers so invoice toolbar and other CAFM JS keep working.
     */
    var CAFM_APP_NAME = "CAFM";

    function isNavbarCafmBrand() {
        var brand = document.querySelector(".o_main_navbar .o_menu_brand");
        if (!brand) {
            return false;
        }
        var brandText = (brand.textContent || "").trim();
        return brandText === CAFM_APP_NAME || brandText.indexOf(CAFM_APP_NAME) === 0;
    }

    function isCafmAppActive() {
        if (document.body.classList.contains("o_cafm_app_active")) {
            return true;
        }
        if (document.querySelector(
            ".o_cfd_dashboard_main, .o_cafm_amc_register_tree, .o_cafm_x_view_action, " +
            ".o_cafm_invoice_status_action, .o_cafm_amc_invoice_screen"
        )) {
            return true;
        }
        var hash = window.location.hash || "";
        if (hash.indexOf("model=cpabooks.cafm") >= 0) {
            return true;
        }
        if (hash.indexOf("model=account.move") >= 0 && isNavbarCafmBrand()) {
            return true;
        }
        if (document.querySelector(".o_main_navbar [data-menu-xmlid^='cpabooks_cafm.']")) {
            return true;
        }
        return isNavbarCafmBrand();
    }

    function requestSyncSidebar(immediate) {
        try {
            var nav = require("cpabooks_leftsidebar_view.shell");
            if (nav && typeof nav.requestSyncSidebar === "function") {
                return nav.requestSyncSidebar(immediate);
            }
        } catch (e) {
            // leftsidebar module not loaded
        }
    }

    return {
        requestSyncSidebar: requestSyncSidebar,
        syncSidebar: requestSyncSidebar,
        isCafmAppActive: isCafmAppActive,
        isNavbarCafmBrand: isNavbarCafmBrand,
    };
});
