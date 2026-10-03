odoo.define("cpabooks_faff.shell", function (require) {
    "use strict";

    var FAFF_APP_NAME = "FAFF";
    var SIDEBAR_ID = "o_faff_shell_sidebar";
    var TOGGLE_ID = "o_faff_sidebar_toggle";
    var BACKDROP_ID = "o_faff_sidebar_backdrop";
    var DRAWER_MQ = "(max-width: 992px)";
    var FAFF_MODULE = "cpabooks_faff";
    var _shellState = {
        active: false,
        menuSignature: "",
    };
    var _syncTimer = null;
    var _navbarObserver = null;

    function menuXmlId(recordId) {
        return FAFF_MODULE + "." + recordId;
    }

    function menuGroupsSignature(groups) {
        return groups
            .map(function (group) {
                return (
                    (group.key || group.title) +
                    ":" +
                    group.items
                        .map(function (item) {
                            return item[1];
                        })
                        .join(",")
                );
            })
            .join("|");
    }

    function requestSyncSidebar(immediate) {
        window.clearTimeout(_syncTimer);
        if (immediate) {
            syncSidebar();
            return;
        }
        _syncTimer = window.setTimeout(syncSidebar, 350);
    }

    function attachNavbarObserver() {
        var navbar = document.querySelector(".o_main_navbar");
        if (!navbar || navbar._faffObserved) {
            return;
        }
        navbar._faffObserved = true;
        _navbarObserver = new MutationObserver(function () {
            requestSyncSidebar();
        });
        _navbarObserver.observe(navbar, { childList: true, subtree: true, characterData: true });
    }

    function isDrawerMode() {
        return window.matchMedia(DRAWER_MQ).matches;
    }

    function syncSidebarAria() {
        var side = document.getElementById(SIDEBAR_ID);
        if (!side) {
            return;
        }
        if (isDrawerMode()) {
            side.setAttribute(
                "aria-hidden",
                document.body.classList.contains("o_faff_sidebar_drawer_open") ? "false" : "true"
            );
        } else {
            side.setAttribute("aria-hidden", "false");
        }
    }

    function closeDrawer() {
        document.body.classList.remove("o_faff_sidebar_drawer_open");
        var toggle = document.getElementById(TOGGLE_ID);
        if (toggle) {
            toggle.setAttribute("aria-expanded", "false");
        }
        syncSidebarAria();
    }

    function toggleDrawer() {
        document.body.classList.toggle("o_faff_sidebar_drawer_open");
        var toggle = document.getElementById(TOGGLE_ID);
        if (toggle) {
            toggle.setAttribute(
                "aria-expanded",
                document.body.classList.contains("o_faff_sidebar_drawer_open") ? "true" : "false"
            );
        }
        syncSidebarAria();
    }

    function removeMobileChrome() {
        closeDrawer();
        var toggle = document.getElementById(TOGGLE_ID);
        if (toggle && toggle.parentNode) {
            toggle.parentNode.removeChild(toggle);
        }
        var backdrop = document.getElementById(BACKDROP_ID);
        if (backdrop && backdrop.parentNode) {
            backdrop.parentNode.removeChild(backdrop);
        }
    }

    function ensureBackdrop() {
        if (!isDrawerMode()) {
            var bd = document.getElementById(BACKDROP_ID);
            if (bd && bd.parentNode) {
                bd.parentNode.removeChild(bd);
            }
            return;
        }
        var backdrop = document.getElementById(BACKDROP_ID);
        if (backdrop) {
            return;
        }
        backdrop = document.createElement("div");
        backdrop.id = BACKDROP_ID;
        backdrop.className = "o_faff_sidebar_backdrop";
        backdrop.setAttribute("aria-hidden", "true");
        backdrop.addEventListener("click", closeDrawer);
        document.body.appendChild(backdrop);
    }

    function ensureSidebarCloseButton(sidebar) {
        if (!sidebar || sidebar.querySelector(".o_faff_sidebar_close")) {
            return;
        }
        var header = sidebar.querySelector(".o_faff_sidebar_header");
        if (!header) {
            return;
        }
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "o_faff_sidebar_close";
        btn.setAttribute("aria-label", "Close menu");
        btn.innerHTML = "<i class='fa fa-times'></i>";
        btn.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            closeDrawer();
        });
        header.appendChild(btn);
    }

    function ensureToolbarToggle() {
        var navbar = document.querySelector(".o_main_navbar");
        if (!navbar) {
            return;
        }
        if (!isDrawerMode()) {
            var orphan = document.getElementById(TOGGLE_ID);
            if (orphan && orphan.parentNode) {
                orphan.parentNode.removeChild(orphan);
            }
            return;
        }
        if (document.getElementById(TOGGLE_ID)) {
            return;
        }
        var toggle = document.createElement("button");
        toggle.id = TOGGLE_ID;
        toggle.type = "button";
        toggle.className = "btn btn-link o_faff_sidebar_toggle";
        toggle.setAttribute("title", "FAFF menu");
        toggle.setAttribute("aria-label", "Open FAFF menu");
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-controls", SIDEBAR_ID);
        toggle.innerHTML = "<i class='fa fa-bars'></i>";
        toggle.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            toggleDrawer();
        });
        var menuToggle = navbar.querySelector(".o_menu_toggle");
        if (menuToggle && menuToggle.parentNode) {
            menuToggle.parentNode.insertBefore(toggle, menuToggle.nextSibling);
        } else {
            navbar.insertBefore(toggle, navbar.firstChild);
        }
    }

    var GROUP_ICON_BY_TITLE = {
        Operations: "fa-fire",
        Jobs: "fa-briefcase",
        Reports: "fa-bar-chart",
        "MIS Reports": "fa-bar-chart",
        Configuration: "fa-cog",
        Dashboard: "fa-th-large",
    };

    var DEFAULT_MENU_GROUPS = [
        {
            key: "operations",
            title: "Operations",
            icon: "fa-fire",
            items: [
                ["Dashboard", menuXmlId("menu_faff_dashboard")],
                ["Process Flow", menuXmlId("menu_faff_process_flow")],
                ["New FAFF Job", menuXmlId("menu_faff_new_job")],
                ["1. CRM", menuXmlId("menu_faff_crm")],
                ["2. Site Visit / Inspection", menuXmlId("menu_faff_inspections")],
                ["3. Estimation", menuXmlId("menu_faff_estimations")],
                ["4. Quotation", menuXmlId("menu_faff_quotations")],
                ["5. Confirm Quotation", menuXmlId("menu_faff_confirmed")],
                ["6. Project + Tasks", menuXmlId("menu_faff_projects")],
                ["Tasks", menuXmlId("menu_faff_tasks")],
                ["7. Material Arrangement", menuXmlId("menu_faff_materials")],
                ["Purchase", menuXmlId("menu_faff_purchases")],
                ["8. Execution", menuXmlId("menu_faff_execution")],
                ["9. Testing", menuXmlId("menu_faff_testing")],
                ["10. Delivery / Completion", menuXmlId("menu_faff_completion")],
                ["11. Invoice", menuXmlId("menu_faff_invoices")],
                ["12. Payment", menuXmlId("menu_faff_payments")],
                ["13. Job Closing", menuXmlId("menu_faff_closed")],
                ["All Jobs", menuXmlId("menu_faff_jobs")],
                ["My Jobs", menuXmlId("menu_faff_my_jobs")],
            ],
        },
        {
            key: "reports",
            title: "MIS Reports",
            icon: "fa-bar-chart",
            items: [
                ["Jobs Analysis", menuXmlId("menu_faff_report_jobs")],
                ["Profitability Summary", menuXmlId("menu_faff_mis_profit_summary")],
                ["Profitability Detail", menuXmlId("menu_faff_mis_profit_detail")],
                ["Comparison Summary", menuXmlId("menu_faff_mis_comparison_summary")],
                ["Comparison Detail", menuXmlId("menu_faff_mis_comparison_detail")],
                ["Daily Job Activity", menuXmlId("menu_faff_mis_daily")],
                ["Print MIS Report", menuXmlId("menu_faff_mis_print")],
                ["FAFF Invoices", menuXmlId("menu_faff_mis_invoices")],
                ["Outstanding Receivable", menuXmlId("menu_faff_mis_receivable")],
                ["Sales Analysis", menuXmlId("menu_faff_mis_sales_analysis")],
                ["Invoice Analysis", menuXmlId("menu_faff_mis_invoice_analysis")],
                ["Purchase Analysis", menuXmlId("menu_faff_mis_purchase_analysis")],
                ["Stock Moves", menuXmlId("menu_faff_mis_stock_moves")],
                ["Inventory Quantities", menuXmlId("menu_faff_mis_stock_qty")],
                ["Project Dashboard", menuXmlId("menu_faff_mis_pd_project")],
                ["Financial Dashboard", menuXmlId("menu_faff_mis_pd_financial")],
                ["Multi-level P&L", menuXmlId("menu_faff_mis_pd_pl")],
            ],
        },
        {
            key: "configuration",
            title: "Configuration",
            icon: "fa-cog",
            items: [
                ["Job Types", menuXmlId("menu_faff_job_types")],
                ["Default Tasks", menuXmlId("menu_faff_default_tasks")],
                ["Load Demo Data", menuXmlId("menu_faff_load_demo")],
                ["Clean Demo Data", menuXmlId("menu_faff_clean_demo")],
            ],
        },
    ];

    function cloneDefaultMenuGroups() {
        return DEFAULT_MENU_GROUPS.map(function (group) {
            return {
                key: group.key,
                title: group.title,
                icon: group.icon,
                flat: group.flat,
                items: group.items.map(function (item) {
                    return item.slice();
                }),
            };
        });
    }

    function groupIcon(title) {
        return GROUP_ICON_BY_TITLE[title] || "fa-folder-o";
    }

    function collectMenuLiNodes(menuSections) {
        var lis = [];
        Array.prototype.forEach.call(menuSections.children, function (child) {
            if (child.tagName === "LI") {
                lis.push(child);
                return;
            }
            if (child.tagName === "SECTION") {
                Array.prototype.forEach.call(child.children, function (li) {
                    if (li && li.tagName === "LI") {
                        lis.push(li);
                    }
                });
            }
        });
        return lis;
    }

    function appendMenuGroupFromLi(li, groups) {
        var dropdownToggle = li.querySelector("a.dropdown-toggle.o_menu_header_lvl_1");
        if (dropdownToggle) {
            var title = dropdownToggle.textContent.trim();
            var items = [];
            li.querySelectorAll(".dropdown-menu a[data-menu-xmlid]").forEach(function (anchor) {
                var label = anchor.textContent.trim();
                var xmlid = anchor.getAttribute("data-menu-xmlid");
                if (xmlid && label) {
                    items.push([label, xmlid]);
                }
            });
            if (title && items.length) {
                groups.push({
                    key: dropdownToggle.getAttribute("data-menu-xmlid") || title,
                    title: title,
                    icon: groupIcon(title),
                    items: items,
                });
            }
            return;
        }
        var direct = li.querySelector("a[data-menu-xmlid][role='menuitem']");
        if (direct && !direct.classList.contains("dropdown-toggle")) {
            var dLabel = direct.textContent.trim();
            var dXmlid = direct.getAttribute("data-menu-xmlid");
            if (dLabel && dXmlid) {
                groups.push({
                    key: dXmlid,
                    title: dLabel,
                    icon: groupIcon(dLabel),
                    items: [[dLabel, dXmlid]],
                    flat: true,
                });
            }
        }
    }

    function collectMenuGroupsFromNavbar() {
        var groups = [];
        var menuSections = document.querySelector(".o_main_navbar .o_menu_sections");
        if (!menuSections) {
            return null;
        }
        var lis = collectMenuLiNodes(menuSections);
        if (!lis.length) {
            return null;
        }
        lis.forEach(function (li) {
            appendMenuGroupFromLi(li, groups);
        });
        return groups.length ? groups : null;
    }

    function resolveMenuGroups() {
        // Prefer curated FAFF groups so flat top menus become left accordion sections.
        return cloneDefaultMenuGroups();
    }

    function isFaffAppActive() {
        var brand = document.querySelector(".o_main_navbar .o_menu_brand");
        if (!brand) {
            return false;
        }
        var brandText = brand.textContent.trim();
        return brandText === FAFF_APP_NAME || brandText.indexOf(FAFF_APP_NAME + " ") === 0;
    }

    function isAppsLauncherVisible() {
        var launcher = document.querySelector(".o_apps, #oe_applications");
        return !!(launcher && launcher.offsetParent !== null);
    }

    function hasBackendAction() {
        return !!document.querySelector(".o_action_manager .o_view_controller, .o_action_manager .o_content");
    }

    function removeFaffShell() {
        if (!_shellState.active && !document.getElementById(SIDEBAR_ID)) {
            document.body.classList.remove("o_faff_apps_launcher_open");
            return;
        }
        document.body.classList.remove("o_faff_dark_shell");
        document.body.classList.remove("o_faff_ui_default", "o_faff_ui_dark");
        document.body.classList.remove("o_faff_apps_launcher_open");
        $(".o_main_navbar .o_cpa_faff_navbar_theme").remove();
        removeMobileChrome();
        var sidebar = document.getElementById(SIDEBAR_ID);
        if (sidebar && sidebar.parentNode) {
            sidebar.parentNode.removeChild(sidebar);
        }
        _shellState.active = false;
        _shellState.menuSignature = "";
    }

    function findOriginalMenu(xmlid, label) {
        var selector = ".o_main_navbar [data-menu-xmlid='" + xmlid + "']";
        var direct = document.querySelector(selector);
        if (direct) {
            return direct;
        }
        var links = document.querySelectorAll(
            ".o_main_navbar .o_menu_sections a, .o_main_navbar .dropdown-menu a"
        );
        for (var i = 0; i < links.length; i++) {
            if (links[i].textContent.trim() === label) {
                return links[i];
            }
        }
        return null;
    }

    function escapeHtml(value) {
        return String(value || "").replace(/[&<>"']/g, function (char) {
            return {
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;",
            }[char];
        });
    }

    function setActiveItem(xmlid) {
        var sidebar = document.getElementById(SIDEBAR_ID);
        if (!sidebar) {
            return;
        }
        Array.prototype.forEach.call(sidebar.querySelectorAll(".o_faff_sidebar_item"), function (item) {
            item.classList.toggle("active", item.getAttribute("data-menu-xmlid") === xmlid);
        });
    }

    function renderSidebarItem(item, extraClass) {
        return (
            "<a href='#' class='o_faff_sidebar_item" +
            (extraClass ? " " + extraClass : "") +
            "' data-menu-xmlid='" +
            escapeHtml(item[1]) +
            "' data-menu-label='" +
            escapeHtml(item[0]) +
            "'>" +
            "<i class='fa fa-circle-o'></i><span>" +
            escapeHtml(item[0]) +
            "</span></a>"
        );
    }

    function renderSidebarNav(groups) {
        var html = ["<div class='o_faff_sidebar_nav'>"];
        var openAssigned = false;
        groups.forEach(function (group) {
            if (group.flat && group.items.length === 1) {
                html.push(renderSidebarItem(group.items[0], "o_faff_sidebar_item_flat"));
                return;
            }
            html.push(
                "<details class='o_faff_sidebar_group'" + (!openAssigned ? " open='open'" : "") + ">"
            );
            if (!openAssigned) {
                openAssigned = true;
            }
            html.push(
                "<summary><span><i class='fa " +
                    escapeHtml(group.icon) +
                    "'></i></span><strong>" +
                    escapeHtml(group.title) +
                    "</strong><i class='fa fa-angle-down'></i></summary>"
            );
            html.push("<nav class='o_faff_sidebar_group_items'>");
            group.items.forEach(function (item) {
                html.push(renderSidebarItem(item));
            });
            html.push("</nav></details>");
        });
        html.push("</div>");
        return html.join("");
    }

    function bindSidebarNav(sidebar) {
        sidebar.addEventListener("click", function (event) {
            var link = event.target.closest(".o_faff_sidebar_item");
            if (!link) {
                return;
            }
            event.preventDefault();
            var original = findOriginalMenu(
                link.getAttribute("data-menu-xmlid"),
                link.getAttribute("data-menu-label")
            );
            if (original) {
                original.click();
                setActiveItem(link.getAttribute("data-menu-xmlid"));
                if (isDrawerMode()) {
                    closeDrawer();
                }
            }
        });
    }

    function refreshSidebarMenus(sidebar, groups, signature) {
        if (!groups.length) {
            return false;
        }
        if (signature && sidebar.getAttribute("data-menu-signature") === signature) {
            return true;
        }
        var nav = sidebar.querySelector(".o_faff_sidebar_nav");
        var navHtml = renderSidebarNav(groups);
        if (nav) {
            nav.outerHTML = navHtml;
        } else {
            sidebar.insertAdjacentHTML("beforeend", navHtml);
        }
        sidebar.setAttribute("data-menu-signature", signature);
        return true;
    }

    function buildSidebar(groups, signature) {
        var sidebar = document.getElementById(SIDEBAR_ID);
        if (sidebar) {
            refreshSidebarMenus(sidebar, groups, signature);
            return sidebar;
        }
        sidebar = document.createElement("aside");
        sidebar.id = SIDEBAR_ID;
        sidebar.className = "o_faff_services_sidebar";
        sidebar.setAttribute("aria-hidden", "true");
        sidebar.innerHTML =
            "<div class='o_faff_sidebar_header'>" +
            "<div class='o_faff_sidebar_logo'><i class='fa fa-fire'></i></div>" +
            "<strong>" +
            escapeHtml(FAFF_APP_NAME) +
            "</strong>" +
            "</div>";
        refreshSidebarMenus(sidebar, groups, signature);
        bindSidebarNav(sidebar);
        document.body.insertBefore(sidebar, document.body.firstChild);
        ensureSidebarCloseButton(sidebar);
        return sidebar;
    }

    function syncSidebar() {
        attachNavbarObserver();

        if (isAppsLauncherVisible()) {
            document.body.classList.add("o_faff_apps_launcher_open");
            removeFaffShell();
            return;
        }
        document.body.classList.remove("o_faff_apps_launcher_open");

        if (!isFaffAppActive()) {
            removeFaffShell();
            return;
        }

        var groups = resolveMenuGroups();
        if (!groups.length) {
            return;
        }

        var signature = menuGroupsSignature(groups);
        if (_shellState.active && _shellState.menuSignature === signature) {
            try {
                require("cpabooks_faff.ui_theme").syncShellTheme();
            } catch (e) { /* ignore */ }
            return;
        }

        try {
            buildSidebar(groups, signature);
            var side = document.getElementById(SIDEBAR_ID);
            if (side) {
                ensureSidebarCloseButton(side);
            }
            ensureBackdrop();
            ensureToolbarToggle();
            if (!isDrawerMode()) {
                closeDrawer();
            }
            syncSidebarAria();
            document.body.classList.add("o_faff_dark_shell");
            _shellState.active = true;
            _shellState.menuSignature = signature;
            try {
                require("cpabooks_faff.ui_theme").syncShellTheme();
            } catch (themeErr) {
                document.body.classList.add("o_faff_ui_default");
            }
            if (!window.location.hash || window.location.hash === "#") {
                window.setTimeout(function () {
                    if (hasBackendAction()) {
                        return;
                    }
                    var dashboard = document.querySelector(
                        ".o_faff_sidebar_item[data-menu-xmlid='cpabooks_faff.menu_faff_dashboard']"
                    );
                    if (dashboard) {
                        dashboard.click();
                    }
                }, 0);
            }
        } catch (error) {
            window.console && window.console.error && window.console.error("FAFF shell failed", error);
        }
    }

    function scheduleInitialSync() {
        requestSyncSidebar(true);
        [300, 800, 1500, 2500, 4000].forEach(function (delay) {
            window.setTimeout(function () {
                requestSyncSidebar();
            }, delay);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", scheduleInitialSync);
    } else {
        scheduleInitialSync();
    }
    document.addEventListener(
        "click",
        function (event) {
            if (
                event.target.closest(
                    ".o_menu_toggle, #oe_main_menu_navbar .dropdown-toggle, #oe_applications .dropdown-toggle, .o_menu_apps a.o_app"
                )
            ) {
                requestSyncSidebar();
            }
        },
        true
    );

    window.addEventListener(
        "keydown",
        function (event) {
            if (event.key !== "Escape") {
                return;
            }
            if (document.body.classList.contains("o_faff_sidebar_drawer_open")) {
                closeDrawer();
            }
        },
        true
    );

    function onDrawerMediaChange() {
        if (!isDrawerMode()) {
            closeDrawer();
            var t = document.getElementById(TOGGLE_ID);
            if (t && t.parentNode) {
                t.parentNode.removeChild(t);
            }
            var b = document.getElementById(BACKDROP_ID);
            if (b && b.parentNode) {
                b.parentNode.removeChild(b);
            }
        } else if (document.body.classList.contains("o_faff_dark_shell")) {
            ensureBackdrop();
            ensureToolbarToggle();
            syncSidebarAria();
        }
    }

    if (window.matchMedia) {
        var mqDrawer = window.matchMedia(DRAWER_MQ);
        if (mqDrawer.addEventListener) {
            mqDrawer.addEventListener("change", onDrawerMediaChange);
        } else if (mqDrawer.addListener) {
            mqDrawer.addListener(onDrawerMediaChange);
        }
    }

    window.addEventListener("hashchange", function () {
        requestSyncSidebar();
    });

    return {
        requestSyncSidebar: requestSyncSidebar,
        syncSidebar: syncSidebar,
    };
});
