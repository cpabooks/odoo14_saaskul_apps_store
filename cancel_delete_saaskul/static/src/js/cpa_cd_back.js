/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { FetchRecordError } from "@web/model/relational_model/errors";

const CPA_CD_MODELS = new Set([
    "account.move",
    "account.payment",
    "sale.order",
    "purchase.order",
    "stock.picking",
    "hr.expense",
]);

/**
 * Returned after a Delete confirm: close the dialog. The view that opened the
 * Actions menu then reloads (list) or leaves the deleted record (form, below).
 */
registry.category("actions").add("cpa_cd_back", () => ({ type: "ir.actions.act_window_close" }));

patch(FormController.prototype, {
    get cogMenuProps() {
        const props = super.cogMenuProps;
        const reload = props.onActionExecuted;
        props.onActionExecuted = async (params) => {
            try {
                return await reload(params);
            } catch (error) {
                if (error instanceof FetchRecordError && CPA_CD_MODELS.has(this.props.resModel)) {
                    // The record was deleted by a Cancel / Delete action: go back to the list.
                    return this.env.config.historyBack();
                }
                throw error;
            }
        };
        return props;
    },
});
