odoo.define("cpabooks_cafm.CafmGuide", function (require) {
    "use strict";

    var AbstractAction = require("web.AbstractAction");
    var core = require("web.core");

    var AMC_STEPS = [
        {step: 1, label: "Client / Project", xmlid: "cpabooks_cafm.action_cpabooks_cafm_projects", theme: "contract"},
        {step: 2, label: "Create AMC Contract", xmlid: "cpabooks_cafm.action_cpabooks_cafm_amc", theme: "contract"},
        {step: 3, label: "Setup SLA", xmlid: "cpabooks_cafm.action_cpabooks_cafm_priority", theme: "ops"},
        {step: 4, label: "PPM Setup", xmlid: "cpabooks_cafm.action_cafm_ppm_setup_wizard", theme: "ops"},
        {step: 5, label: "Generate PPM", xmlid: "cpabooks_cafm.action_cafm_ppm_generate_wizard", theme: "ops"},
        {step: 6, label: "AMC Call", xmlid: "cpabooks_cafm.action_cafm_amc_call_form", theme: "ops"},
        {step: 7, label: "Stock Issue", xmlid: "cpabooks_cafm.action_cafm_stock_issue_amc", theme: "materials"},
        {step: 8, label: "Cont. Order / Billing", xmlid: "cpabooks_cafm.action_cpabooks_cafm_contract_orders", theme: "billing"},
        {step: 9, label: "Invoice", xmlid: "cpabooks_cafm.action_cpabooks_cafm_amc_invoices", theme: "billing"},
        {step: 10, label: "Client SOA", xmlid: "cpabooks_cafm.action_cafm_client_soa_single_project", theme: "billing"},
    ];

    var VAR_STEPS = [
        {step: 1, label: "Create Quotation", xmlid: "sale.action_quotations_with_onboarding", theme: "contract"},
        {step: 2, label: "Create Project", xmlid: "cpabooks_cafm.action_cpabooks_cafm_projects", theme: "contract"},
        {step: 3, label: "Stock Issue", xmlid: "cpabooks_cafm.action_cafm_stock_issue_var", theme: "materials"},
        {step: 4, label: "Direct Purchase", xmlid: "purchase.purchase_rfq", theme: "materials"},
        {step: 5, label: "Invoice", xmlid: "account.action_move_out_invoice_type", theme: "billing"},
    ];

    function syncShell() {
        try {
            require("cpabooks_cafm.shell").requestSyncSidebar(true);
        } catch (e) {
            // optional
        }
    }

    function pathFromAction(action) {
        var ctx = (action && action.context) || {};
        if (ctx.cafm_path === "var" || ctx.cafm_path === "amc") {
            return ctx.cafm_path;
        }
        var tag = (action && action.tag) || "";
        return String(tag).indexOf("var") !== -1 ? "var" : "amc";
    }

    var CafmHowItWorks = AbstractAction.extend({
        contentTemplate: "CpabooksCafmHowItWorks",
        xmlDependencies: ["/cpabooks_cafm/static/src/xml/cafm_guide.xml"],
        events: {
            "click .o_cafm_flow_node": "_onNodeClick",
            "click .o_cafm_cycle_node": "_onNodeClick",
        },

        init: function (parent, action) {
            this._super(parent, action);
            this.pathKind = pathFromAction(action);
            this.steps = this.pathKind === "var" ? VAR_STEPS : AMC_STEPS;
            this.pageTitle =
                this.pathKind === "var" ? "Process Flow — VAR" : "Process Flow — AMC";
            this.centerTitle = this.pathKind === "var" ? "VAR" : "AMC";
        },

        start: function () {
            var self = this;
            this.set("title", this.pageTitle);
            syncShell();
            return this._super.apply(this, arguments).then(function () {
                self._renderFlow(self.$(".o_cafm_how_flow"));
                self._renderCycle(self.$(".o_cafm_cycle_ring"));
            });
        },

        _renderFlow: function ($tree) {
            if (!$tree || !$tree.length) {
                return;
            }
            $tree.empty();
            $tree.append(
                $('<div class="o_cafm_flow_root_node"/>').text(
                    this.pathKind === "var" ? "VAR (no AMC)" : "AMC Cycle"
                )
            );
            $tree.append($('<div class="o_cafm_flow_connector"/>'));
            var $col = $('<div class="o_cafm_flow_column"/>');
            _.each(this.steps, function (node) {
                var $n = $(
                    '<a href="#" class="o_cafm_flow_node o_cafm_theme_' + node.theme + '"/>'
                );
                $n.attr({"data-xmlid": node.xmlid, title: node.label});
                $n.text(node.step + ". " + node.label);
                $col.append($n);
                $col.append($('<div class="o_cafm_flow_connector short"/>'));
            });
            $col.children(".o_cafm_flow_connector.short").last().remove();
            $tree.append($col);
        },

        _renderCycle: function ($ring) {
            if (!$ring || !$ring.length) {
                return;
            }
            $ring.empty();
            var total = this.steps.length;
            _.each(this.steps, function (step, index) {
                var angle = (360 / total) * index - 90;
                var $node = $(
                    '<a href="#" class="o_cafm_cycle_node o_cafm_theme_' + step.theme + '"/>'
                );
                $node.attr({
                    "data-xmlid": step.xmlid,
                    "data-step": step.step,
                    title: step.label,
                    style: "--cafm-angle: " + angle + "deg;",
                });
                $node.append($('<span class="o_cafm_cycle_step"/>').text(step.step));
                $node.append($('<span class="o_cafm_cycle_label"/>').text(step.label));
                $ring.append($node);
            });
        },

        _onNodeClick: function (ev) {
            ev.preventDefault();
            var xmlid = $(ev.currentTarget).data("xmlid");
            if (xmlid) {
                this.do_action(xmlid).guardedCatch(function () {});
            }
        },
    });

    core.action_registry.add("cpabooks_cafm_how_amc", CafmHowItWorks);
    core.action_registry.add("cpabooks_cafm_how_var", CafmHowItWorks);
    // Legacy tags → AMC combined page
    core.action_registry.add("cpabooks_cafm_organogram", CafmHowItWorks);
    core.action_registry.add("cpabooks_cafm_process_cycle", CafmHowItWorks);
    core.action_registry.add("cpabooks_cafm_amc_flowchart", CafmHowItWorks);
    core.action_registry.add("cpabooks_cafm_amc_cycle", CafmHowItWorks);
    core.action_registry.add("cpabooks_cafm_var_flowchart", CafmHowItWorks);
    core.action_registry.add("cpabooks_cafm_var_cycle", CafmHowItWorks);

    return {CafmHowItWorks: CafmHowItWorks};
});
