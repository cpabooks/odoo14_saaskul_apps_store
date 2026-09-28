odoo.define("cpabooks_cafm.amc_x_view", function (require) {
    "use strict";

    var AbstractAction = require("web.AbstractAction");
    var core = require("web.core");
    var _t = core._t;

    function formatAmount(value) {
        var n = parseFloat(value);
        if (isNaN(n)) {
            return "0.00";
        }
        return n.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function escapeHtml(text) {
        return String(text || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function renderCell(cell) {
        if (!cell || !cell.status) {
            return "<td class='o_cafm_x_cell o_cafm_x_empty'></td>";
        }
        var cls = cell.status === "billed" ? "o_cafm_x_billed" : "o_cafm_x_unbilled";
        return (
            "<td class='o_cafm_x_cell " + cls + "'><span class='o_cafm_x_mark'>X</span></td>"
        );
    }

    function renderAmountCell(amount) {
        var val = formatAmount(amount);
        var cls = amount ? "o_cafm_x_amount_cell" : "o_cafm_x_amount_empty";
        return "<td class='" + cls + "'>" + (amount ? val : "") + "</td>";
    }

    function rpcErrorMessage(err, fallback) {
        if (!err) {
            return fallback;
        }
        if (err.data && err.data.message) {
            return err.data.message;
        }
        if (err.message && err.message.data && err.message.data.message) {
            return err.message.data.message;
        }
        if (typeof err.message === "string") {
            return err.message;
        }
        return fallback;
    }

    var AmcRegisterXView = AbstractAction.extend({
        contentTemplate: "CpabooksCafmAmcXView",
        xmlDependencies: ["/cpabooks_cafm/static/src/xml/cafm_amc_x_view.xml"],

        init: function (parent, action) {
            this._super(parent, action);
            var ctx = (action && action.context) || {};
            this.domain = (action.params && action.params.domain)
                || ctx.cafm_x_view_domain
                || [["active", "=", true]];
            this.year = (action.params && action.params.year) || ctx.cafm_x_view_year || false;
            this.xViewData = null;
            this.loadError = "";
        },

        willStart: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                if (self.xmlDependencies && self.xmlDependencies.length) {
                    return self._loadTemplates();
                }
                return Promise.resolve();
            });
        },

        start: function () {
            var self = this;
            this.set("title", _t("X View"));
            return this._super.apply(this, arguments).then(function () {
                self.$el.addClass("o_cafm_x_view_action");
                return self._loadData();
            }).then(function () {
                self._render();
                try {
                    require("cpabooks_cafm.shell").requestSyncSidebar(true);
                } catch (e) { /* ignore */ }
            });
        },

        _loadData: function () {
            var self = this;
            self.loadError = "";
            return this._rpc({
                model: "cpabooks.cafm.contract.month.line",
                method: "cafm_register_x_view_data",
                kwargs: {
                    domain: self.domain,
                    year: self.year || false,
                },
            }).then(function (data) {
                self.xViewData = data || {};
            }).guardedCatch(function (err) {
                self.xViewData = { rows: [], months: [], monthly_totals: [] };
                self.loadError = rpcErrorMessage(err, _t("Could not load X View data."));
            });
        },

        _render: function () {
            var self = this;
            var $mount = this.$(".o_cafm_x_mount");
            if (!$mount.length) {
                $mount = this.$(".o_cafm_x_view_root");
            }
            if (!$mount.length) {
                $mount = this.$(".o_content");
            }
            var data = this.xViewData || {};
            var months = data.months || [];
            var rows = data.rows || [];
            var totals = data.monthly_totals || [];
            var html = [];

            html.push("<div class='o_cafm_x_toolbar'>");
            html.push(
                "<button type='button' class='btn btn-secondary btn-sm o_cafm_x_back_btn'>" +
                "<i class='fa fa-arrow-left'/> " + _t("Back to Register") + "</button>"
            );
            html.push(
                "<h2 class='o_cafm_x_title'>" +
                escapeHtml(data.title || _t("Revenue Schedule")) +
                "</h2>"
            );
            html.push("</div>");

            if (this.loadError) {
                html.push(
                    "<div class='alert alert-danger o_cafm_x_error'>" +
                    escapeHtml(this.loadError) + "</div>"
                );
            }

            html.push("<div class='o_cafm_x_panels'>");
            html.push("<div class='o_cafm_x_schedule_panel'>");
            html.push("<table class='o_cafm_x_table o_cafm_x_schedule_table'><thead><tr>");
            html.push("<th>SL</th><th>Type</th><th>Description</th>");
            html.push("<th>Client Number</th><th>Client Name</th><th>Inv Type</th>");
            months.forEach(function (label) {
                html.push("<th class='o_cafm_x_month_col'>" + escapeHtml(label) + "</th>");
            });
            html.push("</tr></thead><tbody>");

            if (!rows.length) {
                html.push(
                    "<tr><td colspan='" + (6 + months.length) + "' class='o_cafm_x_empty_msg'>" +
                    _t("No AMC schedule rows for this year.") + "</td></tr>"
                );
            }
            rows.forEach(function (row, idx) {
                html.push("<tr>");
                html.push("<td>" + escapeHtml(row.sl || idx + 1) + "</td>");
                html.push("<td>" + escapeHtml(row.type || "") + "</td>");
                html.push("<td class='o_cafm_x_desc'>" + escapeHtml(row.description || "") + "</td>");
                html.push("<td>" + escapeHtml(row.client_number || "") + "</td>");
                html.push("<td>" + escapeHtml(row.client_name || "") + "</td>");
                html.push("<td class='o_cafm_x_inv_type'>" + escapeHtml(row.inv_type || "") + "</td>");
                (row.months || []).forEach(function (cell) {
                    html.push(renderCell(cell));
                });
                html.push("</tr>");
            });
            html.push("</tbody></table></div>");

            html.push("<div class='o_cafm_x_amount_panel'>");
            html.push("<table class='o_cafm_x_table o_cafm_x_amount_table'><thead><tr>");
            html.push(
                "<th colspan='" + Math.max(months.length, 1) + "' class='o_cafm_x_amount_title'>" +
                _t("Monthly Invoicing") + "</th></tr><tr>"
            );
            months.forEach(function (label) {
                html.push("<th class='o_cafm_x_month_col'>" + escapeHtml(label) + "</th>");
            });
            html.push("</tr></thead><tbody><tr>");
            if (!totals.length && months.length) {
                months.forEach(function () {
                    html.push(renderAmountCell(0));
                });
            } else {
                totals.forEach(function (amount) {
                    html.push(renderAmountCell(amount));
                });
            }
            html.push("</tr></tbody></table></div>");
            html.push("</div>");

            html.push("<div class='o_cafm_x_legend'>");
            html.push(
                "<span class='o_cafm_x_legend_item o_cafm_x_billed'>" +
                "<span class='o_cafm_x_mark'>X</span> " + _t("Billed") + "</span>"
            );
            html.push(
                "<span class='o_cafm_x_legend_item o_cafm_x_unbilled'>" +
                "<span class='o_cafm_x_mark'>X</span> " + _t("Unbilled") + "</span>"
            );
            html.push("</div>");

            $mount.html(html.join(""));
            $mount.find(".o_cafm_x_back_btn").on("click", function (ev) {
                ev.preventDefault();
                self.do_action("cpabooks_cafm.action_cpabooks_cafm_amc");
            });
        },
    });

    core.action_registry.add("cpabooks_cafm_amc_x_view", AmcRegisterXView);
});
