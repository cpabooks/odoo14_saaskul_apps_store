odoo.define("cpabooks_cafm.invoice_tally_print_menu", function (require) {
    "use strict";

    require("professional_templates_v1.cpabooks_print_menu");
    var ActionMenus = require("web.ActionMenus");

    var previousSetPrintItems = ActionMenus.prototype._setPrintItems;
    var TALLY_LABEL = "tally format";

    function isTallyItem(item) {
        return ((item && item.description) || "").toLowerCase().indexOf(TALLY_LABEL) !== -1;
    }

    ActionMenus.prototype._setPrintItems = async function (props) {
        var printItems = await previousSetPrintItems.call(this, props);
        var action = this.env && this.env.action;
        if (!action || action.res_model !== "account.move") {
            return printItems;
        }
        var tally = [];
        var rest = [];
        printItems.forEach(function (item) {
            if (isTallyItem(item)) {
                tally.push(item);
            } else {
                rest.push(item);
            }
        });
        var activeIds = (props && props.activeIds) || [];
        if (!tally.length || !activeIds.length) {
            return tally.concat(rest);
        }
        try {
            var moves = await this.rpc({
                model: "account.move",
                method: "read",
                args: [activeIds, ["move_type"]],
            });
            var allCustomer = moves.length && moves.every(function (move) {
                return move.move_type === "out_invoice" || move.move_type === "out_refund";
            });
            if (!allCustomer) {
                return rest;
            }
        } catch (err) {
            return tally.concat(rest);
        }
        return tally.concat(rest);
    };
});
