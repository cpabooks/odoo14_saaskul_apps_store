/** @odoo-module **/

import { Component, markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

/** Read-only HTML progress strip used in the FAFF job wizard. */
export class FaffWizardProgressHtml extends Component {
    static template = "fire_alarm_saaskul.FaffWizardProgressHtml";
    static props = { ...standardFieldProps };

    get html() {
        let text = this.props.record.data[this.props.name] || "";
        text = String(text);
        if (text.includes("&lt;") || text.includes("&#")) {
            const area = document.createElement("textarea");
            area.innerHTML = text;
            text = area.value;
        }
        return markup(text);
    }
}

registry.category("fields").add("faff_wizard_progress_html", {
    component: FaffWizardProgressHtml,
    supportedTypes: ["html", "char", "text"],
});
