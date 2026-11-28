/** @odoo-module **/

import { Component, reactive, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";
import { NavBar } from "@web/webclient/navbar/navbar";

const FAFF_ROOT_XMLID = "fire_alarm_saaskul.menu_faff_root";
const THEME_KEY = "cpa_faff_ui_theme";
const DRAWER_MQ = "(max-width: 992px)";

const DEFAULT_MENU_GROUPS = [
        {
            key: "operations",
            title: "Operations",
            icon: "fa-fire",
            items: [
                ["Dashboard", "fire_alarm_saaskul.menu_faff_dashboard"],
                ["Process Flow", "fire_alarm_saaskul.menu_faff_process_flow"],
                ["New FAFF Job", "fire_alarm_saaskul.menu_faff_new_job"],
                ["1. CRM", "fire_alarm_saaskul.menu_faff_crm"],
                ["2. Site Visit / Inspection", "fire_alarm_saaskul.menu_faff_inspections"],
                ["3. Estimation", "fire_alarm_saaskul.menu_faff_estimations"],
                ["4. Quotation", "fire_alarm_saaskul.menu_faff_quotations"],
                ["5. Confirm Quotation", "fire_alarm_saaskul.menu_faff_confirmed"],
                ["6. Project + Tasks", "fire_alarm_saaskul.menu_faff_projects"],
                ["Tasks", "fire_alarm_saaskul.menu_faff_tasks"],
                ["7. Material Arrangement", "fire_alarm_saaskul.menu_faff_materials"],
                ["Purchase", "fire_alarm_saaskul.menu_faff_purchases"],
                ["8. Execution", "fire_alarm_saaskul.menu_faff_execution"],
                ["9. Testing", "fire_alarm_saaskul.menu_faff_testing"],
                ["10. Delivery / Completion", "fire_alarm_saaskul.menu_faff_completion"],
                ["11. Invoice", "fire_alarm_saaskul.menu_faff_invoices"],
                ["12. Payment", "fire_alarm_saaskul.menu_faff_payments"],
                ["13. Job Closing", "fire_alarm_saaskul.menu_faff_closed"],
                ["All Jobs", "fire_alarm_saaskul.menu_faff_jobs"],
                ["My Jobs", "fire_alarm_saaskul.menu_faff_my_jobs"],
            ],
        },
        {
            key: "reports",
            title: "MIS Reports",
            icon: "fa-bar-chart",
            items: [
                ["Jobs Analysis", "fire_alarm_saaskul.menu_faff_report_jobs"],
                ["Profitability Summary", "fire_alarm_saaskul.menu_faff_mis_profit_summary"],
                ["Profitability Detail", "fire_alarm_saaskul.menu_faff_mis_profit_detail"],
                ["Comparison Summary", "fire_alarm_saaskul.menu_faff_mis_comparison_summary"],
                ["Comparison Detail", "fire_alarm_saaskul.menu_faff_mis_comparison_detail"],
                ["Daily Job Activity", "fire_alarm_saaskul.menu_faff_mis_daily"],
                ["Print MIS Report", "fire_alarm_saaskul.menu_faff_mis_print"],
                ["FAFF Invoices", "fire_alarm_saaskul.menu_faff_mis_invoices"],
                ["Outstanding Receivable", "fire_alarm_saaskul.menu_faff_mis_receivable"],
                ["Sales Analysis", "fire_alarm_saaskul.menu_faff_mis_sales_analysis"],
                ["Invoice Analysis", "fire_alarm_saaskul.menu_faff_mis_invoice_analysis"],
                ["Purchase Analysis", "fire_alarm_saaskul.menu_faff_mis_purchase_analysis"],
                ["Stock Moves", "fire_alarm_saaskul.menu_faff_mis_stock_moves"],
                ["Inventory Quantities", "fire_alarm_saaskul.menu_faff_mis_stock_qty"],
                ["Project Dashboard", "fire_alarm_saaskul.menu_faff_mis_pd_project"],
                ["Financial Dashboard", "fire_alarm_saaskul.menu_faff_mis_pd_financial"],
                ["Multi-level P&L", "fire_alarm_saaskul.menu_faff_mis_pd_pl"],
            ],
        },
        {
            key: "configuration",
            title: "Configuration",
            icon: "fa-cog",
            items: [
                ["Job Types", "fire_alarm_saaskul.menu_faff_job_types"],
                ["Default Tasks", "fire_alarm_saaskul.menu_faff_default_tasks"],
                ["Load Demo Data", "fire_alarm_saaskul.menu_faff_load_demo"],
                ["Clean Demo Data", "fire_alarm_saaskul.menu_faff_clean_demo"],
            ],
        },
    ];

function readTheme() {
    try {
        const theme = window.localStorage.getItem(THEME_KEY);
        if (theme === "dark" || theme === "default") {
            return theme;
        }
    } catch {
        // ignore
    }
    return "default";
}

/** Shared by the sidebar (main component) and the navbar buttons. */
export const faffShellState = reactive({ active: false, theme: readTheme(), drawerOpen: false });

function applyBodyClasses() {
    const body = document.body;
    body.classList.toggle("o_faff_dark_shell", faffShellState.active);
    body.classList.toggle("o_faff_ui_dark", faffShellState.active && faffShellState.theme === "dark");
    body.classList.toggle("o_faff_ui_default", faffShellState.active && faffShellState.theme !== "dark");
    body.classList.toggle("o_faff_sidebar_drawer_open", faffShellState.active && faffShellState.drawerOpen);
}

export function setFaffTheme(theme) {
    faffShellState.theme = theme === "dark" ? "dark" : "default";
    try {
        window.localStorage.setItem(THEME_KEY, faffShellState.theme);
    } catch {
        // ignore
    }
    applyBodyClasses();
}

export class FaffShell extends Component {
    static template = "fire_alarm_saaskul.FaffShell";
    static props = {};

    setup() {
        this.menu = this.env.services.menu;
        this.shell = useState(faffShellState);
        this.state = useState({ activeXmlid: false, open: { 0: true } });
        this.sync();
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => this.sync());
        this.onKeydown = (ev) => {
            if (ev.key === "Escape" && faffShellState.drawerOpen) {
                this.closeDrawer();
            }
        };
        onMounted(() => window.addEventListener("keydown", this.onKeydown, true));
        onWillUnmount(() => window.removeEventListener("keydown", this.onKeydown, true));
    }

    sync() {
        const app = this.menu?.getCurrentApp();
        faffShellState.active = Boolean(app && app.xmlid === FAFF_ROOT_XMLID);
        if (!faffShellState.active) {
            faffShellState.drawerOpen = false;
        }
        applyBodyClasses();
    }

    get groups() {
        if (!this.menu) {
            return [];
        }
        const byXmlid = {};
        for (const menu of this.menu.getAll()) {
            if (menu.xmlid) {
                byXmlid[menu.xmlid] = menu;
            }
        }
        const groups = [];
        for (const group of DEFAULT_MENU_GROUPS) {
            // Only menus the user can see (the menu service already applies groups).
            const items = group.items
                .map(([label, xmlid]) => ({ label, xmlid, menu: byXmlid[xmlid] }))
                .filter((item) => item.menu);
            if (items.length) {
                groups.push({ ...group, items });
            }
        }
        return groups;
    }

    toggleGroup(index, ev) {
        ev.preventDefault();
        this.state.open[index] = !this.state.open[index];
    }

    async openItem(item) {
        this.state.activeXmlid = item.xmlid;
        if (window.matchMedia(DRAWER_MQ).matches) {
            this.closeDrawer();
        }
        await this.menu.selectMenu(item.menu);
    }

    closeDrawer() {
        faffShellState.drawerOpen = false;
        applyBodyClasses();
    }
}

registry.category("main_components").add("fire_alarm_saaskul.FaffShell", { Component: FaffShell });

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);
        this.faffShell = useState(faffShellState);
    },
    onFaffTheme(theme) {
        setFaffTheme(theme);
    },
    onFaffDrawerToggle() {
        faffShellState.drawerOpen = !faffShellState.drawerOpen;
        applyBodyClasses();
    },
});
