/** @odoo-module **/

import { Component, markup, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { KEY_TO_ITEM, openAppsMenu } from "./sg_shell19";

const CYCLE_STEPS = [
    {step: 1, label: 'Enquiry (CRM)', xmlid: 'crm.crm_lead_action_pipeline', theme: 'customer'},
    {step: 2, label: 'Estimation', xmlid: 'switchgear_saaskul.action_job_estimate', theme: 'customer'},
    {step: 3, label: 'Quotation', xmlid: 'sale.action_quotations_with_onboarding', theme: 'customer'},
    {step: 4, label: 'Design Documents', xmlid: 'switchgear_saaskul.action_switchgear_design_document', theme: 'engineering'},
    {step: 5, label: 'Bill of Material', xmlid: 'mrp.mrp_bom_form_action', theme: 'engineering'},
    {step: 6, label: 'Manuf. Order (MO)', xmlid: 'mrp.mrp_production_action', theme: 'engineering'},
    {step: 7, label: 'Purchase Requisition', xmlid: 'switchgear_saaskul.action_material_purchase_requisition', theme: 'engineering'},
    {step: 8, label: 'Quality Control', xmlid: 'switchgear_saaskul.quality_alert_team_action', theme: 'engineering'},
    {step: 9, label: 'Stock Check', xmlid: 'stock.stock_picking_type_action', theme: 'purchase'},
    {step: 10, label: 'LPO (Purchase)', xmlid: 'purchase.purchase_rfq', theme: 'purchase'},
    {step: 11, label: 'GRN', xmlid: 'switchgear_saaskul.action_switchgear_stock_incoming', theme: 'purchase'},
    {step: 12, label: 'Delivery', xmlid: 'switchgear_saaskul.action_switchgear_stock_outgoing', theme: 'purchase'},
    {step: 13, label: 'Tax Invoice', xmlid: 'account.action_move_out_invoice_type', theme: 'accounting'},
    {step: 14, label: 'Customer Payment', xmlid: 'account.action_account_payments', theme: 'accounting'},
    {step: 15, label: 'Bills Entry', xmlid: 'account.action_move_in_invoice_type', theme: 'accounting'},
    {step: 16, label: 'Vendor Payment', xmlid: 'account.action_account_payments_payable', theme: 'accounting'},
];

export class SgDashboard extends Component {
    static template = "switchgear_saaskul.SgDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: {} });
        onWillStart(async () => {
            try {
                this.state.data = (await this.orm.call("switchgear.dashboard", "get_dashboard_data", [])) || {};
            } catch {
                this.state.data = { title: "Switchgear Dashboard", kpis: [], workflow: [] };
            }
        });
    }

    open(xmlid) {
        if (xmlid) {
            this.action.doAction(xmlid);
        }
    }

    openMainMenu() {
        openAppsMenu();
    }
}

export class SgProcessingCycle extends Component {
    static template = "switchgear_saaskul.SgProcessingCycle";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.steps = CYCLE_STEPS.map((step, index) => ({ ...step, angle: (360 / CYCLE_STEPS.length) * index - 90 }));
    }

    open(step) {
        if (step.xmlid) {
            this.action.doAction(step.xmlid);
        }
    }
}

export class SgFlowchartHome extends Component {
    static template = "switchgear_saaskul.SgFlowchartHome";
    static props = ["*"];

    setup() {
        this.action = useService("action");
    }

    open(key) {
        const item = KEY_TO_ITEM[key];
        if (item && item.xmlid) {
            this.action.doAction(item.xmlid);
        }
    }
}

export class SgTutorialProgressHtml extends Component {
    static template = "switchgear_saaskul.SgTutorialProgressHtml";
    static props = { ...standardFieldProps };

    get html() {
        let text = String(this.props.record.data[this.props.name] || "");
        if (text.includes("&lt;") || text.includes("&#")) {
            const area = document.createElement("textarea");
            area.innerHTML = text;
            text = area.value;
        }
        return text ? markup(text) : false;
    }
}

registry.category("actions").add("switchgear_dashboard", SgDashboard);
registry.category("actions").add("switchgear_flowchart", SgDashboard);
registry.category("actions").add("switchgear_processing_cycle", SgProcessingCycle);
registry.category("fields").add("sg_tutorial_progress_html", {
    component: SgTutorialProgressHtml,
    supportedTypes: ["html", "char", "text"],
});
