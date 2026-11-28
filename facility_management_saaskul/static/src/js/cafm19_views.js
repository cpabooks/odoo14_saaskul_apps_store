/** @odoo-module **/

import { Component, markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/** Read-only HTML report widget (no editor). */
export class CafmReadonlyHtml extends Component {
    static template = "facility_management_saaskul.CafmReadonlyHtml";
    static props = { ...standardFieldProps };

    get html() {
        const value = this.props.record.data[this.props.name];
        return value ? markup(String(value)) : false;
    }
}

registry.category("fields").add("cafm_readonly_html", {
    component: CafmReadonlyHtml,
    supportedTypes: ["html", "text", "char"],
});

// Odoo 19: the Tally / AMC register lists use the standard list view.
registry.category("views").add("cafm_tally_list", listView);
registry.category("views").add("cafm_amc_register_list", listView);
registry.category("views").add("cafm_amc_invoice_list", listView);
