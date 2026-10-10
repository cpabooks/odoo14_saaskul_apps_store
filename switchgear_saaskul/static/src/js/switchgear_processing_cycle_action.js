odoo.define('switchgear_saaskul.switchgear_processing_cycle', function (require) {
'use strict';

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');
var AppShell = require('switchgear_saaskul.switchgear_app_shell');

var _t = core._t;

var CYCLE_STEPS = [
    {step: 1, label: 'Enquiry (CRM)', xmlid: 'crm.crm_lead_action_pipeline', theme: 'customer'},
    {step: 2, label: 'Estimation', xmlid: 'switchgear_saaskul.action_job_estimate', theme: 'customer'},
    {step: 3, label: 'Quotation', xmlid: 'sale.action_quotations_with_onboarding', theme: 'customer'},
    {step: 4, label: 'Design Documents', xmlid: 'switchgear_saaskul.action_switchgear_design_document', theme: 'engineering'},
    {step: 5, label: 'Bill of Material', xmlid: 'mrp.mrp_bom_form_action', theme: 'engineering'},
    {step: 6, label: 'Manuf. Order (MO)', xmlid: 'mrp.mrp_production_action', theme: 'engineering'},
    {step: 7, label: 'Purchase Requisition', xmlid: 'switchgear_saaskul.action_material_purchase_requisition', theme: 'engineering'},
    {step: 8, label: 'Quality Control', xmlid: 'switchgear_saaskul.quality_alert_team_action', theme: 'engineering'},
    {step: 9, label: 'Stock Check', xmlid: 'stock.stock_picking_type_action', theme: 'purchase'},
    {step: 10, label: 'LPO (Purchase)', xmlid: 'purchase.purchase_rfq', theme: 'purchase'},
    {step: 11, label: 'GRN', xmlid: 'switchgear_saaskul.action_switchgear_stock_incoming', theme: 'purchase'},
    {step: 12, label: 'Delivery', xmlid: 'switchgear_saaskul.action_switchgear_stock_outgoing', theme: 'purchase'},
    {step: 13, label: 'Tax Invoice', xmlid: 'account.action_move_out_invoice_type', theme: 'accounting'},
    {step: 14, label: 'Customer Payment', xmlid: 'account.action_account_payments', theme: 'accounting'},
    {step: 15, label: 'Bills Entry', xmlid: 'account.action_move_in_invoice_type', theme: 'accounting'},
    {step: 16, label: 'Vendor Payment', xmlid: 'account.action_account_payments_payable', theme: 'accounting'},
];

var SwitchgearProcessingCycleAction = AbstractAction.extend({
    contentTemplate: 'SwitchgearProcessingCycle',
    xmlDependencies: ['/switchgear_saaskul/static/src/xml/switchgear_processing_cycle.xml'],
    hasSidebar: true,

    events: {
        'click .o_sg_cycle_node': '_onNodeClick',
    },

    init: function (parent, action) {
        this._super(parent, action);
        this.activeNavKey = 'processing_cycle';
        this.cycleSteps = CYCLE_STEPS;
    },

    start: function () {
        this.set('title', _t('Switchgear processing cycle'));
        AppShell.activate();
        var self = this;
        return this._super.apply(this, arguments).then(function () {
            return AppShell.getSidebarOptions().then(function (options) {
                self._sidebarOptions = options;
                return self._mountShell();
            });
        });
    },

    _mountShell: function () {
        var self = this;
        var $content = this.$('.o_content');
        if (!$content.length) {
            $content = this.$el;
        }
        var $layout = $('<div class="o_switchgear_app_layout"/>');
        var $sidebarHost = $('<div class="o_switchgear_sidebar_host"/>');
        var $main = $('<div class="o_switchgear_app_content o_switchgear_processing_cycle_main"/>');
        var $root = this.$('.o_sg_processing_cycle_root');
        $main.append($root);
        $layout.append($sidebarHost).append($main);
        $content.empty().append($layout);
        AppShell.mountSidebar($sidebarHost, this.activeNavKey, function (item) {
            if (item.special === 'open_app_menu') {
                return AppShell.openMainMenu();
            }
            if (item.xmlid) {
                return self.do_action(item.xmlid);
            }
            return $.when();
        }, this._sidebarOptions || {});
        this._renderCycle($main.find('.o_sg_cycle_ring'));
    },

    _renderCycle: function ($ring) {
        if (!$ring || !$ring.length) {
            return;
        }
        $ring.empty();
        var total = this.cycleSteps.length;
        var self = this;
        _.each(this.cycleSteps, function (step, index) {
            var angle = (360 / total) * index - 90;
            var $node = $('<a href="#" class="o_sg_cycle_node o_sg_cycle_theme_' + step.theme + '"/>');
            $node.attr({
                'data-xmlid': step.xmlid,
                'data-step': step.step,
                title: step.label,
                style: '--sg-angle: ' + angle + 'deg;',
            });
            $node.append($('<span class="o_sg_cycle_step"/>').text(step.step));
            $node.append($('<span class="o_sg_cycle_label"/>').text(step.label));
            $ring.append($node);
        });
        $ring.css('--sg-cycle-total', total);
    },

    _onNodeClick: function (ev) {
        ev.preventDefault();
        var xmlid = $(ev.currentTarget).data('xmlid');
        if (xmlid) {
            this.do_action(xmlid);
        }
    },
});

core.action_registry.add('switchgear_processing_cycle', SwitchgearProcessingCycleAction);

return SwitchgearProcessingCycleAction;
});
