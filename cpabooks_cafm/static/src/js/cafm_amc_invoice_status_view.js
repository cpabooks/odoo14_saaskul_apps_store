odoo.define("cpabooks_cafm.amc_invoice_status_view", function (require) {
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

    function cellClass(base, extra) {
        return base + (extra ? " " + extra : "");
    }

    var AmcInvoiceStatusView = AbstractAction.extend({
        contentTemplate: "CpabooksCafmAmcInvoiceStatusView",
        xmlDependencies: ["/cpabooks_cafm/static/src/xml/cafm_amc_invoice_status_view.xml"],

        init: function (parent, action) {
            this._super(parent, action);
            var ctx = (action && action.context) || {};
            this.cafmInvoiceDomain = (action.params && action.params.domain)
                || ctx.cafm_invoice_status_domain
                || [];
            this.statusData = null;
            this.loadError = "";
        },

        start: function () {
            var self = this;
            var toolbar = require("cpabooks_cafm.amc_invoice_toolbar");
            this.set("title", _t("AMC Invoice Status"));
            return this._super.apply(this, arguments).then(function () {
                self.$el.addClass("o_cafm_invoice_status_action");
                window._cpaCafmStatusActionWidget = self;
                toolbar.storeStatusViewMode(true);
                toolbar.scheduleEnhanceInvoiceToolbar(self, { mode: "status" });
                return self._loadData();
            }).then(function () {
                self._render();
                toolbar.scheduleEnhanceInvoiceToolbar(self, { mode: "status" });
                try {
                    require("cpabooks_cafm.shell").requestSyncSidebar(true);
                } catch (e) { /* ignore */ }
            });
        },

        _loadData: function () {
            var self = this;
            self.loadError = "";
            return this._rpc({
                model: "account.move",
                method: "cafm_invoice_status_data",
                kwargs: {
                    domain: self.cafmInvoiceDomain,
                },
            }).then(function (data) {
                self.statusData = data || {};
            }).guardedCatch(function (err) {
                self.statusData = { rows: [], total_amount: 0 };
                self.loadError = (err && err.message)
                    ? err.message.data
                        ? err.message.data.message
                        : err.message
                    : _t("Could not load AMC Invoice Status.");
            });
        },

        _render: function () {
            var self = this;
            var $mount = this.$(".o_cafm_invoice_status_mount");
            if (!$mount.length) {
                $mount = this.$(".o_content");
            }
            var data = this.statusData || {};
            var rows = data.rows || [];
            var html = [];

            html.push("<div class='o_cafm_invoice_status_toolbar'>");
            html.push(
                "<button type='button' class='btn btn-secondary btn-sm o_cafm_invoice_status_back_btn'>" +
                "<i class='fa fa-arrow-left'/> " + _t("Back to Invoice List") + "</button>"
            );
            html.push(
                "<h2 class='o_cafm_invoice_status_title'>" +
                escapeHtml(data.title || _t("AMC Invoice Status")) +
                "</h2>"
            );
            html.push("</div>");

            if (this.loadError) {
                html.push(
                    "<div class='alert alert-danger o_cafm_invoice_status_error'>" +
                    escapeHtml(this.loadError) + "</div>"
                );
            }

            html.push("<div class='o_cafm_invoice_status_panel'>");
            html.push("<table class='o_cafm_invoice_status_table'><thead>");
            html.push("<tr class='o_cafm_invoice_status_banner'><th colspan='12'>" +
                escapeHtml(_t("AMC Invoice Status")) + "</th></tr>");
            html.push("<tr>");
            [
                _t("Sl.No"),
                _t("Property Name"),
                _t("AMC Invoice Period"),
                _t("Client"),
                _t("Month"),
                _t("Invoice No"),
                _t("Amount"),
                _t("Docs Status"),
                _t("Invoice Status"),
                _t("Invoice Submitted By"),
                _t("Received Copy Status"),
                _t("Remarks"),
            ].forEach(function (label) {
                html.push("<th>" + escapeHtml(label) + "</th>");
            });
            html.push("</tr></thead><tbody>");

            if (!rows.length) {
                html.push(
                    "<tr><td colspan='12' class='o_cafm_invoice_status_empty'>" +
                    _t("No AMC invoices found for the current list.") + "</td></tr>"
                );
            }

            rows.forEach(function (row) {
                var clientKey = row.client_key || "default";
                html.push("<tr>");
                html.push("<td class='o_cafm_invoice_status_sl'>" + escapeHtml(row.sl) + "</td>");
                html.push("<td class='o_cafm_invoice_status_property'>" +
                    escapeHtml(row.property_name) + "</td>");
                html.push("<td class='" + cellClass(
                    "o_cafm_invoice_status_period",
                    row.period_class === "ok" ? "o_cafm_invoice_status_ok" : ""
                ) + "'>" + escapeHtml(row.invoice_period) + "</td>");
                html.push("<td class='o_cafm_invoice_status_client o_cafm_invoice_status_client_" +
                    escapeHtml(clientKey) + "'>" + escapeHtml(row.client_name) + "</td>");
                html.push("<td>" + escapeHtml(row.month_label) + "</td>");
                if (row.invoice_id) {
                    html.push(
                        "<td class='o_cafm_invoice_status_invoice_no'>" +
                        "<a href='#' class='o_cafm_invoice_status_link' data-invoice-id='" +
                        row.invoice_id + "'>" + escapeHtml(row.invoice_no) + "</a></td>"
                    );
                } else {
                    html.push("<td>" + escapeHtml(row.invoice_no) + "</td>");
                }
                html.push("<td class='o_cafm_invoice_status_amount'>" +
                    formatAmount(row.amount) + "</td>");
                html.push("<td class='" + cellClass(
                    "o_cafm_invoice_status_docs",
                    row.docs_class === "ok" ? "o_cafm_invoice_status_ok" : ""
                ) + "'>" + escapeHtml(row.docs_status) + "</td>");
                html.push("<td class='" + cellClass(
                    "o_cafm_invoice_status_inv_status",
                    row.invoice_status_class === "ok"
                        ? "o_cafm_invoice_status_ok"
                        : (row.invoice_status_class === "danger" ? "o_cafm_invoice_status_danger" : "")
                ) + "'>" + escapeHtml(row.invoice_status) + "</td>");
                html.push("<td>" + escapeHtml(row.submitted_by) + "</td>");
                html.push("<td class='" + cellClass(
                    "",
                    row.received_copy_class === "ok" ? "o_cafm_invoice_status_ok" : ""
                ) + "'>" + escapeHtml(row.received_copy) + "</td>");
                html.push("<td class='o_cafm_invoice_status_remarks'>" +
                    escapeHtml(row.remarks) + "</td>");
                html.push("</tr>");
            });

            html.push("<tr class='o_cafm_invoice_status_total_row'>");
            html.push("<td colspan='6' class='o_cafm_invoice_status_total_label'>" +
                _t("Total") + "</td>");
            html.push("<td class='o_cafm_invoice_status_amount o_cafm_invoice_status_total_amount'>" +
                formatAmount(data.total_amount) + "</td>");
            html.push("<td colspan='5'></td>");
            html.push("</tr>");
            html.push("</tbody></table></div>");

            $mount.html(html.join(""));

            $mount.find(".o_cafm_invoice_status_back_btn").on("click", function (ev) {
                ev.preventDefault();
                toolbar.storeStatusViewMode(false);
                self.do_action("cpabooks_cafm.action_cpabooks_cafm_amc_invoices");
            });

            $mount.find(".o_cafm_invoice_status_link").on("click", function (ev) {
                ev.preventDefault();
                var invoiceId = parseInt($(ev.currentTarget).data("invoice-id"), 10);
                if (!invoiceId) {
                    return;
                }
                self.do_action({
                    type: "ir.actions.act_window",
                    res_model: "account.move",
                    res_id: invoiceId,
                    views: [[false, "form"]],
                    view_mode: "form",
                    target: "current",
                });
            });
        },
    });

    core.action_registry.add("cpabooks_cafm_amc_invoice_status", AmcInvoiceStatusView);
    return AmcInvoiceStatusView;
});
