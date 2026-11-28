/** @odoo-module **/

import { Component, markup, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const TMC_TAB_NAMES = ["timesheets_tab", "client_tms", "material_request", "internal_timesheet", "customer_material", "customer_labour_cost"];
const TAB_STORAGE_PREFIX = "cpabooks_crn_task_tab_";
const FSM_BLINK_CLASS = "cpabooks_fsm_nav_bubble_red";
const FSM_BLINK_MS = 2600;
const FSM_SERIAL_TO_FIELD = {
        '4': 'partner_id',
        '5': 'site_location',
        '6': 'client_person',
        '7': 'client_contact',
        '8': 'client_email',
        '9': 'complaint_type',
        '10': 'invoice_id',
        '11': 'qt_no',
        '12': 'item_des',
        '13': 'invoice_type',
        '14': 'crn_done_before',
        '15': 'project_id',
        '16': 'complaint_title',
        '17': 'complaint_details',
        '18': 'deadline',
        '19': 'importance',
        '20': 'total_print_row',
        '21': 'visited_by',
        '22': 'visited_date',
        '23': 'site_visit',
        '24': 'next_action',
        '27': 'fsm_assigned_employee_id',
        '28': 'assign_date',
        '29': 'date_end',
        '30': 'fsm_invoice_progress_status',
        '32': 'material_cost_total',
        '33': 'timesheet_cost_total',
        '34': 'fsm_transport_cost',
        '35': 'fsm_other_cost',
        '36': 'total_service_cost',
        '37': 'closing_remarks',
    };
const FSM_STAGE_FIELD_NAMES = {
        0: ['partner_id', 'site_location', 'client_person', 'client_contact', 'client_email', 'complaint_type', 'invoice_id', 'qt_no', 'qt_no_text', 'item_des', 'invoice_type', 'project_id', 'complaint_title', 'deadline', 'importance', 'total_print_row', 'crn_done_before'],
        1: ['visited_by', 'visited_date', 'site_visit', 'next_action'],
        2: ['fsm_quotation_id', 'fsm_quotation_status'],
        3: ['fsm_quotation_approval_status'],
        4: ['fsm_assigned_employee_id', 'assign_date', 'date_end'],
        5: ['select_invoice'],
        6: ['closing_remarks', 'material_cost_total', 'timesheet_cost_total', 'total_service_cost'],
    };

function isFsmTask(record) {
    const data = record && record.data;
    return Boolean(record && record.resModel === "project.task" && data && (data.is_fsm || data.check_fsm || data.fsm_crn_form));
}

function pendingSerials(data) {
    const serials = [];
    if (data.fsm_pending_banner_html) {
        const tmp = document.createElement("div");
        tmp.innerHTML = String(data.fsm_pending_banner_html);
        for (const li of tmp.querySelectorAll("li")) {
            const match = li.textContent.trim().match(/^(\d+)\./);
            if (match && !serials.includes(match[1])) {
                serials.push(match[1]);
            }
        }
    }
    if (serials.length) {
        return serials;
    }
    const compact = String(data.fsm_workflow_pending_serials_display || "")
        .replace(/^Pending\s+/i, "")
        .replace(/\s*\.\.\.\s*$/, "");
    return compact.split(",").map((part) => part.trim()).filter(Boolean);
}

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.props.resModel !== "project.task") {
            return;
        }
        this._fsmNavIndex = 0;
        this._fsmRestoredTabFor = false;
        const onUpdate = () => requestAnimationFrame(() => this._cpabooksApplyFsmUi());
        onMounted(() => {
            this.model.bus.addEventListener("update", onUpdate);
            onUpdate();
            this._fsmTabListener = (ev) => {
                const link = ev.target.closest(".o_notebook_headers .nav-link");
                const root = this.rootRef?.el;
                if (!link || !root || !root.contains(link)) {
                    return;
                }
                const key = this._fsmTabKey();
                const name = link.getAttribute("name");
                if (key && name) {
                    window.sessionStorage.setItem(key, name);
                }
            };
            document.addEventListener("click", this._fsmTabListener, true);
        });
        onWillUnmount(() => {
            this.model.bus.removeEventListener("update", onUpdate);
            document.removeEventListener("click", this._fsmTabListener, true);
            document.body.classList.remove("o_cpabooks_fsm_form_active");
        });
    },

    _fsmTabKey() {
        const resId = this.model.root && this.model.root.resId;
        return resId ? TAB_STORAGE_PREFIX + resId : null;
    },

    /** Stage locks, tone classes, hidden New button and remembered tab (was jQuery DOM work in 14). */
    _cpabooksApplyFsmUi() {
        const root = this.rootRef && this.rootRef.el;
        const record = this.model.root;
        const active = isFsmTask(record);
        document.body.classList.toggle("o_cpabooks_fsm_form_active", active);
        if (!root || !active) {
            return;
        }
        const data = record.data;
        const fullEdit = Boolean(data.fsm_workflow_edit_mode);
        root.classList.toggle("cpabooks_fsm_full_edit_mode", fullEdit);
        const tone = (name, value, prefix, tones) => {
            const el = root.querySelector(`.o_field_widget[name="${name}"]`);
            if (!el) {
                return;
            }
            for (const t of tones) {
                el.classList.remove(prefix + t);
            }
            if (value && value !== "none") {
                el.classList.add(prefix + value);
            }
        };
        tone("fsm_invoice_progress_status", data.fsm_invoice_progress_tone, "cpabooks_fsm_invoice_tone_", ["in_progress", "draft", "issued"]);
        tone("fsm_stage7_approval_status", data.fsm_stage7_approval_tone, "cpabooks_fsm_stage7_tone_", ["waiting", "approved", "rejected"]);
        const sheet = root.querySelector(".cpabooks_fsm_task_sheet") || root;
        for (let i = 0; i <= 6; i++) {
            const locked = !fullEdit && Boolean(data[`fsm_stage_${i}_readonly`]);
            sheet.querySelector(`.cpabooks_fsm_stage_panel_${i}`)?.classList.toggle("cpabooks_fsm_stage_locked", locked);
            for (const fieldName of FSM_STAGE_FIELD_NAMES[i] || []) {
                for (const el of sheet.querySelectorAll(`.o_field_widget[name="${fieldName}"]`)) {
                    el.classList.toggle("cpabooks_fsm_field_locked", locked);
                }
            }
        }
        // Restore the last Timesheet / Material tab once per record.
        const key = this._fsmTabKey();
        if (key && this._fsmRestoredTabFor !== key) {
            this._fsmRestoredTabFor = key;
            const tab = window.sessionStorage.getItem(key);
            if (tab && TMC_TAB_NAMES.includes(tab)) {
                const link = root.querySelector(`.o_notebook_headers .nav-link[name="${tab}"]`);
                if (link && !link.classList.contains("active")) {
                    link.click();
                }
            }
        }
    },

    /** NEXT: scroll to the next pending checklist field and blink it. */
    _cpabooksFsmFocusNext() {
        const root = this.rootRef && this.rootRef.el;
        const serials = pendingSerials(this.model.root.data);
        if (!root || !serials.length) {
            return;
        }
        for (let tries = 0; tries < serials.length; tries++) {
            const serial = serials[this._fsmNavIndex % serials.length];
            this._fsmNavIndex = (this._fsmNavIndex + 1) % serials.length;
            const fieldName = FSM_SERIAL_TO_FIELD[serial];
            const field = fieldName && root.querySelector(`.o_field_widget[name="${fieldName}"]`);
            if (!field) {
                continue;
            }
            const target = field.closest(".o_wrap_field, .o_cell, tr") || field;
            target.scrollIntoView({ behavior: "smooth", block: "center" });
            target.classList.remove(FSM_BLINK_CLASS);
            void target.offsetWidth;
            target.classList.add(FSM_BLINK_CLASS);
            setTimeout(() => target.classList.remove(FSM_BLINK_CLASS), FSM_BLINK_MS);
            field.querySelector("input:not([type=hidden]), textarea, select")?.focus({ preventScroll: true });
            return;
        }
    },

    async beforeExecuteActionButton(clickParams) {
        if (this.props.resModel === "project.task") {
            const name = clickParams.name;
            if (name === "action_fsm_dismiss_pending_banner") {
                return false;
            }
            if (name === "action_fsm_workflow_next") {
                this._cpabooksFsmFocusNext();
                return false;
            }
            if (name === "action_fsm_workflow_full_edit") {
                if (!(await this.model.root.save())) {
                    return false;
                }
                await this.orm.call("project.task", "action_fsm_workflow_edit", [[this.model.root.resId]]);
                await this.model.root.load();
                return false;
            }
        }
        return super.beforeExecuteActionButton(...arguments);
    },
});

/** Read-only HTML (no editor) for the CRN workflow banners. */
export class FsmReadonlyHtml extends Component {
    static template = "field_service_saaskul.FsmReadonlyHtml";
    static props = { ...standardFieldProps };

    get html() {
        const value = this.props.record.data[this.props.name];
        return value ? markup(String(value)) : false;
    }
}

registry.category("fields").add("fsm_readonly_html", {
    component: FsmReadonlyHtml,
    supportedTypes: ["html"],
});
