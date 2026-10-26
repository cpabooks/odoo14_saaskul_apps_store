odoo.define("chart_of_accounts_saaskul.account_form_pager", function (require) {
    "use strict";

    var FormController = require("web.FormController");
    var FormView = require("web.FormView");
    var viewRegistry = require("web.view_registry");

    var AccountFormController = FormController.extend({
        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                return self._loadLedgerPager();
            });
        },

        _loadLedgerPager: function () {
            var self = this;
            var state = this.model.get(this.handle, {raw: true});
            if (!state || state.model !== "account.account") {
                return Promise.resolve();
            }
            if (state.res_ids && state.res_ids.length > 1) {
                return Promise.resolve();
            }
            var domain = state.domain || [];
            var onlyOne = domain.length === 1 && domain[0][0] === "id";
            var companies = (state.context && (state.context.allowed_company_ids || state.context.company_ids)) || [];
            if (!domain.length || onlyOne) {
                if (!companies.length) {
                    return Promise.resolve();
                }
                domain = [["company_id", "in", companies]];
            }
            return this._rpc({
                model: "account.account",
                method: "search",
                args: [domain],
                kwargs: {
                    order: "code, id",
                    context: state.context || {},
                },
            }).then(function (ids) {
                if (!ids || ids.length < 2) {
                    return;
                }
                var datapoint = self.model.localData[self.handle];
                if (!datapoint) {
                    return;
                }
                var index = ids.indexOf(state.res_id);
                datapoint.res_ids = ids;
                datapoint.count = ids.length;
                datapoint.offset = index < 0 ? 0 : index;
                self._updateControlPanel();
            });
        },
    });

    var AccountFormView = FormView.extend({
        config: _.extend({}, FormView.prototype.config, {
            Controller: AccountFormController,
        }),
    });

    viewRegistry.add("account_form_pager", AccountFormView);
});
