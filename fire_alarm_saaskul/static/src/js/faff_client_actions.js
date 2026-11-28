/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const FLOW_ROWS = [
        [
            {
                n: 1,
                title: "CRM Lead / Opportunity",
                system: "CRM",
                icon: "fa-users",
                color: "#2563eb",
                tasks: [
                    "Create Lead / Opportunity",
                    "Customer Details",
                    "Contact Person",
                    "Site / Project Location",
                    "Job Type (FA / FF)",
                    "Sales Person",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_crm",
            },
            {
                n: 2,
                title: "Site Visit / Inspection",
                system: "FAFF",
                icon: "fa-map-marker",
                color: "#16a34a",
                tasks: [
                    "Site Visit",
                    "Existing System",
                    "Requirement / Problem",
                    "Observations",
                    "Photos",
                    "Recommendation",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_visit",
            },
            {
                n: 3,
                title: "Estimation (BOQ + Costing)",
                system: "FAFF",
                icon: "fa-calculator",
                color: "#ea580c",
                tasks: [
                    "Prepare BOQ",
                    "Cost of Material",
                    "Labour Cost",
                    "Other Costs",
                    "Margin %",
                    "Selling Price",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_estimate",
            },
            {
                n: 4,
                title: "Quotation",
                system: "Sales",
                icon: "fa-file-text-o",
                color: "#7c3aed",
                tasks: [
                    "Create Quotation",
                    "Terms & Conditions",
                    "Validity",
                    "Attach BOQ",
                    "Send to Customer",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_quotations",
            },
            {
                n: 5,
                title: "Confirm Quotation",
                system: "Sales",
                icon: "fa-check-square-o",
                color: "#0f766e",
                tasks: [
                    "Customer Approval",
                    "Confirm Sale Order",
                    "Convert to Project",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_confirmed_orders",
            },
        ],
        [
            {
                n: 6,
                title: "Project + Tasks",
                system: "Project",
                icon: "fa-tasks",
                color: "#b45309",
                tasks: [
                    "Create Project",
                    "Default Tasks",
                    "Assign Engineer",
                    "Planned Dates",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_projects",
            },
            {
                n: 7,
                title: "Material Arrangement",
                system: "Inventory",
                icon: "fa-cubes",
                color: "#1e3a8a",
                tasks: [
                    "Check Material Requirement",
                    "In Stock → Issue",
                    "Not in Stock → RFQ / PO",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_material",
            },
            {
                n: 8,
                title: "Execution (Job Work)",
                system: "Project",
                icon: "fa-wrench",
                color: "#166534",
                tasks: [
                    "Execute Work as per Tasks",
                    "Manpower Hours",
                    "Progress Photos",
                    "Site Updates",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_execution_jobs",
            },
            {
                n: 9,
                title: "Testing & Commissioning",
                system: "FAFF",
                icon: "fa-check-circle",
                color: "#0891b2",
                tasks: [
                    "Panel / Devices / Pump",
                    "Alarm & Cause-Effect",
                    "Pass or Rectification",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_testing",
            },
        ],
        [
            {
                n: 10,
                title: "Delivery Note / Completion",
                system: "FAFF",
                icon: "fa-handshake-o",
                color: "#9333ea",
                tasks: [
                    "Work Completion",
                    "Customer Signature",
                    "Handover Note",
                    "Warranty",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_completion",
            },
            {
                n: 11,
                title: "Invoice",
                system: "Accounting",
                icon: "fa-file-text",
                color: "#be123c",
                tasks: [
                    "Create Invoice from SO",
                    "Post Invoice",
                    "Link to FAFF Job",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_invoices",
            },
            {
                n: 12,
                title: "Payment",
                system: "Accounting",
                icon: "fa-money",
                color: "#15803d",
                tasks: [
                    "Register Payment",
                    "Full or Partial",
                    "Update Job Balance",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_payments",
            },
            {
                n: 13,
                title: "Job Closing",
                system: "FAFF",
                icon: "fa-flag-checkered",
                color: "#334155",
                tasks: [
                    "All documents linked",
                    "Mark job Finished",
                    "Archive / Close",
                ],
                xmlid: "fire_alarm_saaskul.action_faff_job_closed",
            },
        ],
    ];

export class FaffDashboard extends Component {
    static template = "fire_alarm_saaskul.FaffDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: { title: _t("FAFF Dashboard"), kpis: [], workflow: [] } });
        onWillStart(async () => {
            try {
                this.state.data = (await this.orm.call("saaskul.faff.dashboard", "get_dashboard_data", [])) || this.state.data;
            } catch {
                // keep the empty dashboard
            }
        });
    }

    open(xmlid) {
        if (xmlid) {
            this.action.doAction(xmlid);
        }
    }
}

export class FaffProcessFlow extends Component {
    static template = "fire_alarm_saaskul.FaffProcessFlow";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.rows = FLOW_ROWS;
    }

    open(xmlid) {
        if (xmlid) {
            this.action.doAction(xmlid);
        }
    }

    startJob() {
        this.action.doAction("fire_alarm_saaskul.action_faff_job_wizard");
    }
}

registry.category("actions").add("faff_dashboard", FaffDashboard);
registry.category("actions").add("faff_process_flow", FaffProcessFlow);
