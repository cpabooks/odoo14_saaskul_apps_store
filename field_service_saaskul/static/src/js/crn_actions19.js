/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";

const CYCLE_STEPS = [
    {step: 1, label: '1. Registered', xmlid: 'field_service_saaskul.crn_task_action_all', theme: 'intake'},
    {step: 2, label: '2. Site Visited', xmlid: 'field_service_saaskul.crn_task_action_all', theme: 'intake'},
    {step: 3, label: '3. Quotation Issued', xmlid: 'field_service_saaskul.action_fsm_project_task_to_quotation_issue', theme: 'quotation'},
    {step: 4, label: '4. QTN Approved', xmlid: 'field_service_saaskul.crn_task_action_all', theme: 'quotation'},
    {step: 5, label: '5. Work in Progress', xmlid: 'field_service_saaskul.crn_task_action_all', theme: 'execution'},
    {step: 6, label: '6. Waiting Invoice', xmlid: 'field_service_saaskul.action_fsm_project_task_to_invoice', theme: 'billing'},
    {step: 7, label: '7. Job Complete FOC', xmlid: 'field_service_saaskul.crn_task_action_all', theme: 'billing'},
    {step: 8, label: '8. Job Invoiced', xmlid: 'field_service_saaskul.crn_task_action_all', theme: 'billing'},
    {step: 9, label: '9. Approved', xmlid: 'field_service_saaskul.action_fsm_task_analysis_monitor', theme: 'closed'},
];

/** Complaint Registration Management dashboard (KPIs + workflow lists). */
export class CrnServiceDashboard extends Component {
    static template = "field_service_saaskul.CrnServiceDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: true, data: {} });
        onWillStart(() => this.load());
    }

    async load() {
        try {
            this.state.data = (await this.orm.call("crn.service.dashboard", "get_dashboard_data", [])) || {};
        } catch {
            this.state.data = { title: "Complaint Registration Management", kpis: [], workflow: [] };
        }
        this.state.loading = false;
    }

    open(xmlid, domain, title) {
        if (!xmlid) {
            return;
        }
        const template = (this.state.data.action_templates || {})[xmlid];
        if (!template) {
            return this.action.doAction(xmlid, { viewType: "list", onClose: () => this.load() });
        }
        const action = JSON.parse(JSON.stringify(template));
        delete action.res_id;
        if (domain && domain.length) {
            action.domain = domain;
        }
        if (title) {
            action.name = title;
        }
        if (action.views) {
            const list = action.views.filter((v) => v[1] === "list" || v[1] === "tree").map((v) => [v[0], "list"]);
            const rest = action.views.filter((v) => !["list", "tree"].includes(v[1]));
            action.views = (list.length ? list : [[false, "list"]]).concat(rest);
        }
        return this.action.doAction(action, { viewType: "list" });
    }

    openMainMenu() {
        document.querySelector(".o_navbar_apps_menu button, .o_navbar_apps_menu .dropdown-toggle")?.click();
    }
}

/** Clickable CRN processing cycle (9 steps around a ring). */
export class CrnProcessingCycle extends Component {
    static template = "field_service_saaskul.CrnProcessingCycle";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.steps = CYCLE_STEPS.map((step, index) => ({
            ...step,
            angle: (360 / CYCLE_STEPS.length) * index - 90,
        }));
    }

    open(step) {
        if (step.xmlid) {
            this.action.doAction(step.xmlid, { viewType: "list" });
        }
    }
}

const BAR_COLORS = ["#ca6a3b", "#d8a75f", "#2f7a72", "#3f556b", "#93a67f", "#b85c5c", "#8b6f47"];

/** Service Monitoring Dashboard with Chart.js drill-down charts. */
export class FsmServiceDashboard extends Component {
    static template = "field_service_saaskul.FsmServiceDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, period: "90", company_id: "0" });
        this.charts = {};
        this.stageRef = useRef("stage");
        this.complaintRef = useRef("complaint");
        this.trendRef = useRef("trend");
        this.teamRef = useRef("team");
        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.load({});
        });
        onMounted(() => this.renderCharts());
        onWillUnmount(() => Object.values(this.charts).forEach((chart) => chart.destroy()));
    }

    async load(filters) {
        const data = await this.orm.call("project.task", "get_fsm_dashboard_data", [filters || {}]);
        this.state.data = data;
        this.state.period = String((data.filters || {}).period || "90");
        this.state.company_id = String((data.filters || {}).company_id || "0");
    }

    async apply() {
        await this.load({ period: this.state.period, company_id: this.state.company_id });
        this.renderCharts();
    }

    async reset() {
        await this.load({ period: "90", company_id: "0" });
        this.renderCharts();
    }

    formatValue(value, isMonetary) {
        const numeric = Number(value || 0);
        if (!isMonetary) {
            return numeric.toLocaleString();
        }
        const currency = (this.state.data && this.state.data.currency) || {};
        const formatted = numeric.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        return currency.position === "after" ? `${formatted} ${currency.symbol || ""}` : `${currency.symbol || ""} ${formatted}`;
    }

    openTasks(extraDomain, title) {
        const action = JSON.parse(JSON.stringify((this.state.data && this.state.data.task_action) || {}));
        action.domain = (action.domain || []).concat(extraDomain || []);
        if (title) {
            action.name = title;
        }
        this.action.doAction(action);
    }

    openTask(task) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "CRN",
            res_model: "project.task",
            res_id: task.id,
            views: [[false, "form"]],
            target: "current",
            context: { fsm_mode: true },
        });
    }

    chart(key, ref, config, onClick) {
        if (this.charts[key]) {
            this.charts[key].destroy();
        }
        if (!ref.el) {
            return;
        }
        config.options = config.options || {};
        config.options.responsive = true;
        config.options.maintainAspectRatio = false;
        if (onClick) {
            config.options.onClick = (event, elements) => {
                if (elements && elements.length) {
                    onClick(elements[0].index, elements[0].datasetIndex);
                }
            };
        }
        this.charts[key] = new Chart(ref.el, config);
    }

    renderCharts() {
        const d = this.state.data;
        if (!d) {
            return;
        }
        const stage = d.stage_chart || [];
        this.chart("stage", this.stageRef, {
            type: "bar",
            data: { labels: stage.map((r) => r.label), datasets: [{ data: stage.map((r) => r.value), backgroundColor: BAR_COLORS, borderRadius: 8 }] },
            options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } },
        }, (i) => this.openTasks(stage[i].domain, stage[i].label));
        const complaint = d.complaint_chart || [];
        this.chart("complaint", this.complaintRef, {
            type: "pie",
            data: { labels: complaint.map((r) => r.label), datasets: [{ data: complaint.map((r) => r.value), backgroundColor: ["#2f7a72", "#ca6a3b", "#d8a75f", "#3f556b", "#93a67f"] }] },
            options: { plugins: { legend: { position: "bottom" } } },
        }, (i) => this.openTasks(complaint[i].domain, complaint[i].label));
        const trend = d.trend_chart || { labels: [], created: [], closed: [] };
        this.chart("trend", this.trendRef, {
            type: "line",
            data: {
                labels: trend.labels,
                datasets: [
                    { label: "Created", data: trend.created, borderColor: "#ca6a3b", backgroundColor: "rgba(202, 106, 59, 0.16)", fill: true, tension: 0.35 },
                    { label: "Closed", data: trend.closed, borderColor: "#2f7a72", backgroundColor: "rgba(47, 122, 114, 0.10)", fill: true, tension: 0.35 },
                ],
            },
            options: { scales: { y: { beginAtZero: true } } },
        }, (i, ds) => {
            const bucket = (trend.domains || [])[i] || {};
            const label = trend.labels[i] || "";
            this.openTasks(ds === 1 ? bucket.closed || [] : bucket.created || [], (ds === 1 ? "Closed - " : "Created - ") + label);
        });
        const team = d.team_chart || [];
        this.chart("team", this.teamRef, {
            type: "bar",
            data: { labels: team.map((r) => r.label), datasets: [{ label: "Timesheet Cost", data: team.map((r) => r.value), backgroundColor: "#3f556b", borderRadius: 8 }] },
            options: { indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } },
        }, (i) => this.openTasks([], team[i].label));
    }
}

registry.category("actions").add("crn_service_dashboard", CrnServiceDashboard);
registry.category("actions").add("crn_processing_cycle", CrnProcessingCycle);
registry.category("actions").add("fsm_service_monitor_dashboard", FsmServiceDashboard);
