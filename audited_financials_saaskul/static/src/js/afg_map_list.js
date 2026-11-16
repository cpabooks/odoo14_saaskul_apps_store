/** @odoo-module **/

import { onMounted, onPatched, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { ListRenderer } from "@web/views/list/list_renderer";

function isAfgList(props) {
    const model = props.resModel || (props.list && props.list.resModel) || "";
    const ctx = props.context || (props.list && props.list.context) || {};
    return (
        model === "audited.financial.group" ||
        model === "audited.financial.ctf.group" ||
        model === "account.group" ||
        ctx.afg_map_list
    );
}

export class AfgMapListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        onWillStart(async () => {
            if (!isAfgList(this.props)) {
                return;
            }
            const model = this.props.resModel;
            const ctx = this.props.context || {};
            if (model === "audited.financial.ctf.group" || ctx.afg_map_mode === "ctf") {
                await this.orm.call("audited.financial.ctf.group", "action_setup_default_ctf_groups", []);
                await this.orm.call("account.account", "action_afg_ensure_ctf_map", []);
            } else if (model === "audited.financial.group") {
                await this.orm.call("audited.financial.group", "action_afg_ensure_standard_map", []);
            }
        });
        onMounted(() => this._afgInstallButtons());
    }

    _afgInstallButtons() {
        if (!isAfgList(this.props) || document.querySelector(".o_afg_btn_expand_ledgers")) {
            return;
        }
        const slot = document.querySelector(".o_control_panel_main_buttons");
        if (!slot) {
            return;
        }
        const expand = document.createElement("button");
        expand.type = "button";
        expand.className = "btn btn-secondary o_afg_btn_expand_ledgers";
        expand.textContent = "Expand ledgers";
        expand.addEventListener("click", (ev) => {
            ev.preventDefault();
            const renderer = this._afgRenderer;
            if (!renderer) {
                return;
            }
            const expanded = expand.classList.toggle("o_afg_ledgers_expanded");
            expand.textContent = expanded ? "Collapse ledgers" : "Expand ledgers";
            if (expanded) {
                renderer.afgExpandAll();
            } else {
                renderer.afgCollapseAll();
            }
        });
        slot.appendChild(expand);
    }
}

export class AfgMapListRenderer extends ListRenderer {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
        this._afgExpanded = {};
        this._afgChildren = {};
        if (this.env.controller) {
            // filled below if the controller asks
        }
        onMounted(() => {
            this._afgRegister();
            this._afgBindMenu();
        });
        onPatched(() => {
            this._afgRestore();
            this._afgBindMenu();
        });
    }

    _afgRegister() {
        const controller = this.env.searchModel ? null : null;
        // The list controller is the parent component in Odoo 19.
        let parent = this.__owl__ && this.__owl__.parent;
        while (parent) {
            const comp = parent.component;
            if (comp && comp instanceof AfgMapListController) {
                comp._afgRenderer = this;
                break;
            }
            parent = parent.parent;
        }
    }

    _afgActive() {
        return isAfgList(this.props);
    }

    async onCellClicked(record, column, ev, newWindow) {
        if (!this._afgActive() || (column && column.widget === "handle")) {
            return super.onCellClicked(record, column, ev, newWindow);
        }
        if (ev && ev.target && ev.target.closest(".o_list_record_selector, button, a")) {
            return super.onCellClicked(record, column, ev, newWindow);
        }
        if (ev) {
            ev.stopPropagation();
            ev.preventDefault();
        }
        await this._afgToggle(record);
    }

    _afgRow(record) {
        const table = this.tableRef && this.tableRef.el;
        if (!table || !record) {
            return null;
        }
        return table.querySelector(`tr.o_data_row[data-id="${record.id}"]`);
    }

    _afgClearChildren(row) {
        if (!row) {
            return;
        }
        let next = row.nextElementSibling;
        while (next && next.classList.contains("o_afg_child_row")) {
            const drop = next;
            next = next.nextElementSibling;
            drop.remove();
        }
    }

    _afgInsertChildren(row, children) {
        this._afgClearChildren(row);
        let last = row;
        const colspan = Math.max(1, (this.columns || []).length);
        (children || []).forEach((child) => {
            const tr = document.createElement("tr");
            tr.className = "o_data_row o_afg_child_row";
            tr.dataset.accountId = String(child.id || "");
            const td = document.createElement("td");
            td.colSpan = colspan;
            td.className = "o_afg_child_cell";
            td.textContent = `${child.code || ""}  ${child.name || ""}`.trim();
            tr.appendChild(td);
            last.insertAdjacentElement("afterend", tr);
            last = tr;
        });
    }

    async _afgToggle(record) {
        const resId = record.resId;
        const row = this._afgRow(record);
        if (!resId || !row) {
            return;
        }
        if (this._afgExpanded[resId]) {
            delete this._afgExpanded[resId];
            this._afgClearChildren(row);
            return;
        }
        const rows = await this.orm.call(this.props.list.resModel, "afg_map_fetch_children", [[resId]]);
        this._afgExpanded[resId] = true;
        this._afgChildren[resId] = rows || [];
        this._afgInsertChildren(row, rows || []);
    }

    _afgRestore() {
        if (!this._afgActive()) {
            return;
        }
        (this.props.list.records || []).forEach((record) => {
            if (!this._afgExpanded[record.resId]) {
                return;
            }
            const row = this._afgRow(record);
            if (row) {
                this._afgInsertChildren(row, this._afgChildren[record.resId] || []);
            }
        });
    }

    async afgExpandAll() {
        const records = this.props.list.records || [];
        const ids = records.map((record) => record.resId).filter(Boolean);
        if (!ids.length) {
            return;
        }
        const mapped = await this.orm.call(this.props.list.resModel, "afg_map_fetch_children_multi", [ids]);
        ids.forEach((resId) => {
            this._afgExpanded[resId] = true;
            this._afgChildren[resId] = (mapped && (mapped[resId] || mapped[String(resId)])) || [];
        });
        this._afgRestore();
    }

    afgCollapseAll() {
        this._afgExpanded = {};
        const table = this.tableRef && this.tableRef.el;
        if (!table) {
            return;
        }
        table.querySelectorAll("tr.o_afg_child_row").forEach((row) => row.remove());
    }

    _afgBindMenu() {
        const table = this.tableRef && this.tableRef.el;
        if (!table || table.dataset.afgMenu === "1" || !this._afgActive()) {
            return;
        }
        table.dataset.afgMenu = "1";
        table.addEventListener("contextmenu", (ev) => {
            const row = ev.target.closest("tr");
            if (!row) {
                return;
            }
            if (row.classList.contains("o_afg_child_row")) {
                ev.preventDefault();
                const accId = parseInt(row.dataset.accountId, 10);
                if (!accId) {
                    return;
                }
                this.orm.call("account.account", "get_formview_action", [[accId]]).then((action) => {
                    if (action) {
                        this.actionService.doAction(action);
                    }
                });
                return;
            }
            const dataRow = row.classList.contains("o_data_row") ? row : null;
            if (!dataRow) {
                return;
            }
            const record = (this.props.list.records || []).find((item) => String(item.id) === dataRow.dataset.id);
            if (!record || !record.resId) {
                return;
            }
            ev.preventDefault();
            this.orm.call(this.props.list.resModel, "action_afg_map_popup", [[record.resId]]).then((action) => {
                if (action) {
                    this.actionService.doAction(action);
                }
            });
        });
    }
}

export const afgMapListView = {
    ...listView,
    Controller: AfgMapListController,
    Renderer: AfgMapListRenderer,
};

registry.category("views").add("afg_map_list", afgMapListView);
