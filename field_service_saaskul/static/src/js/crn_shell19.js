/** @odoo-module **/

import { Component, reactive, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

const FSM_ROOT_XMLID = "field_service_saaskul.crn_menu_root";
const SHELL_CLASS = "o_crn_app_shell";

const NAV_ITEMS = [
    {section: 'Home', sectionClass: 'o_crn_section_home', items: [
        {key: 'dashboard', label: 'Dashboard', xmlid: 'field_service_saaskul.action_crn_service_dashboard', tier: 'home'},
        {key: 'processing_cycle', label: 'CRN Processing Cycle', xmlid: 'field_service_saaskul.action_crn_processing_cycle', tier: 'home'},
    ]},
    {section: 'CRNs', sectionClass: 'o_crn_section_crns', items: [
        {key: 'my_crns', label: 'My CRNs', xmlid: 'field_service_saaskul.crn_task_action_my'},
        {key: 'all_crns', label: 'All CRNs', xmlid: 'field_service_saaskul.crn_task_action_all'},
        {key: 'to_quotation', label: 'To Quotation / Issue', xmlid: 'field_service_saaskul.action_fsm_project_task_to_quotation_issue'},
        {key: 'to_invoice', label: 'To Invoice', xmlid: 'field_service_saaskul.action_fsm_project_task_to_invoice'},
    ]},
    {section: 'Reporting', sectionClass: 'o_crn_section_reporting', items: [
        {key: 'service_dashboard', label: 'Service Charts Dashboard', xmlid: 'field_service_saaskul.action_fsm_service_monitor_dashboard'},
        {key: 'task_analysis', label: 'CRN Analysis', xmlid: 'field_service_saaskul.action_fsm_task_analysis_monitor'},
        {key: 'timesheet_analysis', label: 'Timesheet Analysis', xmlid: 'field_service_saaskul.action_fsm_timesheet_analysis_monitor'},
        {key: 'material_consumption', label: 'Material Consumption Analysis', xmlid: 'field_service_saaskul.action_fsm_material_consumption_analysis'},
    ]},
    {section: 'Store', sectionClass: 'o_crn_section_store', items: [
        {key: 'stock_issue', label: 'Material Issue Note', xmlid: 'field_service_saaskul.issue_action'},
        {key: 'stock_return', label: 'Material Return Note', xmlid: 'field_service_saaskul.return_issue_action'},
        {key: 'mat_request', label: 'Material Request Pending', xmlid: 'field_service_saaskul.action_fsm_store_material_request_pending'},
        {key: 'mat_issued', label: 'Material Issued', xmlid: 'field_service_saaskul.action_fsm_store_material_issued'},
        {key: 'do_pending', label: 'DO Pending', xmlid: 'field_service_saaskul.action_fsm_store_do_pending'},
        {key: 'do_issued', label: 'DO Issued', xmlid: 'field_service_saaskul.action_fsm_store_do_issued'},
    ]},
    {section: 'Timesheets', sectionClass: 'o_crn_section_timesheet', items: [
        {key: 'timesheet_mine', label: 'My Timesheets', xmlid: 'hr_timesheet.act_hr_timesheet_line'},
        {key: 'timesheet_all', label: 'All Timesheets', xmlid: 'hr_timesheet.timesheet_action_all'},
    ]},
    {section: 'Settings', sectionClass: 'o_crn_section_settings', items: [
        {key: 'test_data', label: 'FSM Test Data', xmlid: 'field_service_saaskul.action_fsm_test_data_wizard', admin_only: true},
        {key: 'all_apps', label: 'All Odoo Apps', special: 'open_app_menu'},
    ]},
];

const XMLID_TO_KEY = {};
for (const block of NAV_ITEMS) {
    for (const item of block.items) {
        if (item.xmlid) {
            XMLID_TO_KEY[item.xmlid] = item.key;
        }
    }
}

const SHELL_TAGS = ["crn_service_dashboard", "crn_processing_cycle", "fsm_service_monitor_dashboard"];
const SHELL_MODELS = ["material.request.line", "crn.service.dashboard", "cpabooks.fsm.test.data.wizard", "fsm.material.consumption.report"];

function actionContext(action) {
    const ctx = action && action.context;
    if (!ctx) {
        return {};
    }
    if (typeof ctx === "string") {
        return /fsm_mode|default_is_fsm|default_check_fsm/.test(ctx) ? { fsm_mode: true } : {};
    }
    return ctx;
}

/** True for Field Service / CRN screens that use the left app shell. */
export function isFsmShellAction(action) {
    if (!action) {
        return false;
    }
    if (SHELL_TAGS.includes(action.tag)) {
        return true;
    }
    const xmlid = action.xml_id || action.xmlid;
    if (xmlid && XMLID_TO_KEY[xmlid]) {
        return true;
    }
    const ctx = actionContext(action);
    if (ctx.fsm_mode || ctx.default_is_fsm || ctx.default_check_fsm) {
        return true;
    }
    if (SHELL_MODELS.includes(action.res_model)) {
        return true;
    }
    const name = String(action.name || "").toLowerCase();
    if (action.res_model === "project.task") {
        const domain = JSON.stringify(action.domain || []);
        if (name.includes("crn") || name.includes("field service") || /is_fsm|check_fsm|CRN/.test(domain)) {
            return true;
        }
    }
    return /waiting for approval|approved crn|rejected crn/.test(name);
}

function activeKeyFromAction(action) {
    if (!action) {
        return "dashboard";
    }
    if (action.tag === "crn_processing_cycle") {
        return "processing_cycle";
    }
    if (action.tag === "crn_service_dashboard") {
        return "dashboard";
    }
    if (action.tag === "fsm_service_monitor_dashboard") {
        return "service_dashboard";
    }
    const xmlid = action.xml_id || action.xmlid;
    if (xmlid && XMLID_TO_KEY[xmlid]) {
        return XMLID_TO_KEY[xmlid];
    }
    const name = String(action.name || "").toLowerCase();
    if (action.res_model === "project.task") {
        return name.includes("my crn") ? "my_crns" : "all_crns";
    }
    if (action.res_model === "material.request.line") {
        return "mat_request";
    }
    if (action.res_model === "stock.picking") {
        const domain = JSON.stringify(action.domain || []);
        if (domain.includes("is_stock_return_note") || name.includes("return")) {
            return "stock_return";
        }
        if (domain.includes("is_stock_issue_note") || name.includes("issue note")) {
            return "stock_issue";
        }
        if (domain.includes("outgoing") || name.includes("do pending") || name.includes("do issued")) {
            return name.includes("issued") || name.includes("done") ? "do_issued" : "do_pending";
        }
        return "mat_issued";
    }
    if (action.res_model === "account.analytic.line") {
        return "timesheet_analysis";
    }
    if (action.res_model === "cpabooks.fsm.test.data.wizard") {
        return "test_data";
    }
    if (action.res_model === "fsm.material.consumption.report") {
        return "material_consumption";
    }
    return "dashboard";
}

export const crnShellState = reactive({ active: false, activeKey: "dashboard" });

export class CrnShell extends Component {
    static template = "field_service_saaskul.CrnShell";
    static props = {};

    setup() {
        this.menu = this.env.services.menu;
        this.action = this.env.services.action;
        this.shell = useState(crnShellState);
        this.isAdmin = user.isSystem;
        this.sync();
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => this.sync());
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this.sync());
    }

    sync() {
        if (!this.menu || !this.action) {
            return;
        }
        const current = this.action.currentController?.action;
        const app = this.menu.getCurrentApp();
        const inApp = Boolean(app && app.xmlid === FSM_ROOT_XMLID);
        const settings = current && current.res_model === "res.config.settings";
        crnShellState.active = !settings && (inApp || isFsmShellAction(current));
        crnShellState.activeKey = activeKeyFromAction(current);
        document.body.classList.toggle(SHELL_CLASS, crnShellState.active);
    }

    get blocks() {
        return NAV_ITEMS.map((block) => ({
            ...block,
            items: block.items.filter((item) => !item.admin_only || this.isAdmin),
        })).filter((block) => block.items.length);
    }

    async open(item) {
        if (item.special === "open_app_menu") {
            document.querySelector(".o_navbar_apps_menu button, .o_navbar_apps_menu .dropdown-toggle")?.click();
            return;
        }
        if (item.xmlid) {
            crnShellState.activeKey = item.key;
            await this.action.doAction(item.xmlid, { clearBreadcrumbs: true, viewType: "list" });
        }
    }
}

registry.category("main_components").add("field_service_saaskul.CrnShell", { Component: CrnShell });
