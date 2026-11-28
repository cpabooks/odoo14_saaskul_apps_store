/** @odoo-module **/

import { Component, reactive, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useBus } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

const SG_ROOT_XMLID = "switchgear_saaskul.menu_flowchart_kanban_root";
const SHELL_CLASS = "o_switchgear_app_shell";

const NAV_ITEMS = [
    {section: 'Home', sectionClass: 'o_switchgear_section_home', items: [
        {key: 'dashboard', label: 'Dashboard', xmlid: 'switchgear_saaskul.action_switchgear_dashboard'},
        {key: 'tutorial', label: 'Tutorial Wizard', xmlid: 'switchgear_saaskul.action_switchgear_tutorial_wizard'},
        {key: 'processing_cycle', label: 'Switchgear processing cycle', xmlid: 'switchgear_saaskul.action_switchgear_processing_cycle'},
        {key: 'flowchart', label: 'Process Flowchart', xmlid: 'switchgear_saaskul.action_flowchart_kanban'},
        {key: 'main_menu', label: 'Apps Home', special: 'open_app_menu'},
    ]},
    {section: 'CRM', sectionClass: 'o_switchgear_section_crm', items: [
        {key: 'enquiry', label: 'Pipeline (Opportunities)', xmlid: 'crm.crm_lead_action_pipeline'},
        {key: 'crm_leads', label: 'Leads', xmlid: 'crm.crm_lead_all_leads'},
        {key: 'estimation', label: 'Estimation', xmlid: 'switchgear_saaskul.action_job_estimate'},
        {key: 'quotation', label: 'Quotation (Sales)', xmlid: 'sale.action_quotations_with_onboarding'},
    ]},
    {section: 'Manufacturing', sectionClass: 'o_switchgear_section_manufacturing', items: [
        {key: 'mrp_order', label: 'Manufacturing Orders', xmlid: 'mrp.mrp_production_action'},
        {key: 'mrp_workorders', label: 'Work Orders', xmlid: 'mrp.mrp_workorder_todo'},
        {key: 'bom', label: 'Bills of Materials', xmlid: 'mrp.mrp_bom_form_action'},
        {key: 'design', label: 'Design (Documents)', xmlid: 'switchgear_saaskul.action_switchgear_design_document'},
        {key: 'purchase_req', label: 'Purchase Requisition', xmlid: 'switchgear_saaskul.action_material_purchase_requisition'},
    ]},
    {section: 'Inventory', sectionClass: 'o_switchgear_section_inventory', items: [
        {key: 'stock_check', label: 'Operations Overview', xmlid: 'stock.stock_picking_type_action'},
        {key: 'stock_transfers', label: 'Transfers', xmlid: 'stock.action_picking_tree_all'},
        {key: 'grn', label: 'Receipts (GRN)', xmlid: 'switchgear_saaskul.action_switchgear_stock_incoming'},
        {key: 'delivery', label: 'Delivery Orders', xmlid: 'switchgear_saaskul.action_switchgear_stock_outgoing'},
        {key: 'stock_adjustments', label: 'Inventory Adjustments', xmlid: 'stock.action_inventory_form'},
        {key: 'stock_replenish', label: 'Reordering Rules', xmlid: 'stock.action_orderpoint'},
        {key: 'stock_products', label: 'Products', xmlid: 'stock.product_template_action_product'},
        {key: 'inv_valuation_live', label: 'Inventory Valuation', xmlid: 'stock_account.stock_valuation_layer_action'},
        {key: 'lpo_purchase', label: 'Purchase (LPO / RFQ)', xmlid: 'purchase.purchase_rfq'},
    ]},
    {section: 'Quality', sectionClass: 'o_switchgear_section_quality', items: [
        {key: 'quality', label: 'Quality Overview', xmlid: 'switchgear_saaskul.quality_alert_team_action'},
        {key: 'quality_checks', label: 'Quality Checks', xmlid: 'switchgear_saaskul.quality_check_action_main'},
        {key: 'quality_alerts', label: 'Quality Alerts', xmlid: 'switchgear_saaskul.quality_alert_action'},
    ]},
    {section: 'Timesheet', sectionClass: 'o_switchgear_section_timesheet', items: [
        {key: 'timesheet_mine', label: 'My Timesheets', xmlid: 'hr_timesheet.act_hr_timesheet_line'},
        {key: 'timesheet_all', label: 'All Timesheets', xmlid: 'hr_timesheet.timesheet_action_all'},
        {key: 'timesheet_report', label: 'Timesheet Analysis', xmlid: 'hr_timesheet.act_hr_timesheet_report'},
    ]},
    {section: 'Employees', sectionClass: 'o_switchgear_section_employees', items: [
        {key: 'hr_employees', label: 'Employees', xmlid: 'hr.open_view_employee_list_my'},
        {key: 'hr_directory', label: 'Employee Directory', xmlid: 'hr.hr_employee_public_action'},
        {key: 'hr_departments', label: 'Departments', xmlid: 'hr.hr_department_tree_action'},
        {key: 'hr_jobs', label: 'Job Positions', xmlid: 'hr.action_hr_job'},
    ]},
    {section: 'Projects', sectionClass: 'o_switchgear_section_projects', items: [
        {key: 'project_list', label: 'Project List', xmlid: 'switchgear_saaskul.action_switchgear_project_list'},
        {key: 'tasks_by_client', label: 'Tasks by Customer', xmlid: 'switchgear_saaskul.action_switchgear_tasks_by_client'},
    ]},
    {section: 'Activities', sectionClass: 'o_switchgear_section_activities', items: [
        {key: 'my_activities', label: 'My Activities', xmlid: 'switchgear_saaskul.action_switchgear_activity_my'},
        {key: 'all_activities', label: 'All Activities', xmlid: 'switchgear_saaskul.action_switchgear_activity_all'},
        {key: 'job_tasks', label: 'Job Tasks', xmlid: 'project.action_view_all_task'},
        {key: 'activity_reporting', label: 'Activity Reporting', xmlid: 'switchgear_saaskul.action_switchgear_activity_reporting'},
    ]},
    {section: 'Accounting', sectionClass: 'o_switchgear_section_accounting', items: [
        {key: 'tax_invoice', label: 'Tax Invoice', xmlid: 'account.action_move_out_invoice_type'},
        {key: 'customer_payment', label: 'Customer Payment Receipt', xmlid: 'account.action_account_payments'},
        {key: 'vendor_bill', label: 'Bills Entry', xmlid: 'account.action_move_in_invoice_type'},
        {key: 'vendor_payment', label: 'Vendor Payment', xmlid: 'account.action_account_payments_payable'},
    ]},
    {section: 'Settings', sectionClass: 'o_switchgear_section_settings', items: [
        {
            key: 'configuration',
            label: 'Configuration',
            xmlid: 'switchgear_saaskul.action_switchgear_configuration',
            admin_only: true,
        },
    ]},
];

export const XMLID_TO_KEY = {};
export const KEY_TO_ITEM = {};
for (const block of NAV_ITEMS) {
    for (const item of block.items) {
        KEY_TO_ITEM[item.key] = item;
        if (item.xmlid) {
            XMLID_TO_KEY[item.xmlid] = item.key;
        }
    }
}
const SHELL_TAGS = { switchgear_dashboard: "dashboard", switchgear_flowchart: "dashboard", switchgear_processing_cycle: "processing_cycle" };

export const sgShellState = reactive({ active: false, activeKey: "dashboard" });

export function openAppsMenu() {
    document.querySelector(".o_navbar_apps_menu button, .o_navbar_apps_menu .dropdown-toggle")?.click();
}

/** Switchgear left app shell (Odoo 19: fixed sidebar while the Switchgear app is open). */
export class SgShell extends Component {
    static template = "switchgear_saaskul.SgShell";
    static props = {};

    setup() {
        this.menu = this.env.services.menu;
        this.action = this.env.services.action;
        this.shell = useState(sgShellState);
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
        const xmlid = current && (current.xml_id || current.xmlid);
        const own = current && (SHELL_TAGS[current.tag] || (xmlid && xmlid.startsWith("switchgear_saaskul.")));
        sgShellState.active = Boolean((app && app.xmlid === SG_ROOT_XMLID) || own) && !(current && current.res_model === "res.config.settings");
        sgShellState.activeKey = (current && (SHELL_TAGS[current.tag] || XMLID_TO_KEY[xmlid])) || sgShellState.activeKey;
        document.body.classList.toggle(SHELL_CLASS, sgShellState.active);
    }

    get blocks() {
        return NAV_ITEMS.map((block) => ({
            ...block,
            items: block.items.filter((item) => !item.admin_only || this.isAdmin),
        })).filter((block) => block.items.length);
    }

    async open(item) {
        if (item.special === "open_app_menu") {
            return openAppsMenu();
        }
        if (item.xmlid) {
            sgShellState.activeKey = item.key;
            await this.action.doAction(item.xmlid, { clearBreadcrumbs: true });
        }
    }
}

registry.category("main_components").add("switchgear_saaskul.SgShell", { Component: SgShell });
