/** @odoo-module **/

import { Component, reactive, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { useBus } from "@web/core/utils/hooks";
import { NavBar } from "@web/webclient/navbar/navbar";

const COLORS = ["#0f766e", "#1d4ed8", "#7c3aed", "#be185d", "#c2410c", "#15803d", "#0369a1", "#4338ca"];

/** Shared between the sidebar, the navbar button and the user menu item. */
export const ccsState = reactive({ showDefault: false });

function toggleDefaultMenu() {
    ccsState.showDefault = !ccsState.showDefault;
    document.body.classList.toggle("o_ccs_show_default_menu", ccsState.showDefault);
}

function letterColor(name) {
    let n = 0;
    for (const ch of name || "") {
        n = (n + ch.charCodeAt(0)) % COLORS.length;
    }
    return COLORS[n];
}

export class AppSidebar extends Component {
    static template = "app_sidebar_saaskul.AppSidebar";
    static props = {};

    setup() {
        // The menu service only exists in the backend web client.
        this.menu = this.env.services.menu;
        this.enabled = Boolean(this.menu);
        this.ccs = useState(ccsState);
        this.state = useState({
            query: "",
            open: {},
            activeMenu: false,
            currentApp: (this.enabled && this.menu.getCurrentApp()?.id) || false,
        });
        document.body.classList.toggle("o_ccs_active", this.enabled);
        if (this.state.currentApp) {
            this.state.open[this.state.currentApp] = true;
        }
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => {
            if (!this.enabled) {
                return;
            }
            const app = this.menu.getCurrentApp();
            this.state.currentApp = app ? app.id : false;
            if (app) {
                this.state.open[app.id] = true;
            }
        });
    }

    get apps() {
        if (!this.enabled) {
            return [];
        }
        const q = this.state.query.trim().toLowerCase();
        const apps = this.menu.getApps().map((app) => this.menu.getMenuAsTree(app.id));
        if (!q) {
            return apps;
        }
        const hit = (m) =>
            (m.name || "").toLowerCase().includes(q) || (m.childrenTree || []).some(hit);
        return apps.filter(hit);
    }

    isOpen(menu) {
        return Boolean(this.state.open[menu.id]) || Boolean(this.state.query.trim());
    }

    letter(app) {
        return (app.name || "A").charAt(0).toUpperCase();
    }

    letterStyle(app) {
        return `background: ${letterColor(app.name)};`;
    }

    toggle(menu, ev) {
        ev?.stopPropagation();
        this.state.open[menu.id] = !this.state.open[menu.id];
    }

    async openApp(app) {
        for (const other of this.menu.getApps()) {
            if (other.id !== app.id) {
                delete this.state.open[other.id];
            }
        }
        this.state.open[app.id] = true;
        this.state.activeMenu = false;
        await this.menu.selectMenu(app);
    }

    async openMenu(menu) {
        this.state.activeMenu = menu.id;
        if (menu.actionID) {
            await this.menu.selectMenu(menu);
        }
    }

    async toggleGroup(menu) {
        this.state.open[menu.id] = !this.state.open[menu.id];
        if (menu.actionID) {
            this.state.activeMenu = menu.id;
            await this.menu.selectMenu(menu);
        }
    }
}

registry.category("main_components").add("app_sidebar_saaskul.AppSidebar", {
    Component: AppSidebar,
});

patch(NavBar.prototype, {
    onCcsDefaultMenu(ev) {
        ev.preventDefault();
        toggleDefaultMenu();
    },
});

registry.category("user_menuitems").add("app_sidebar_saaskul_default_menu", () => ({
    type: "item",
    id: "app_sidebar_saaskul_default_menu",
    description: "Default menu",
    callback: toggleDefaultMenu,
    sequence: 69,
}));
