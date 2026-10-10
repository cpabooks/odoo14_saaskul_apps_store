odoo.define('field_service_saaskul.crn_processing_cycle', function (require) {
'use strict';

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');
var AppShell = require('field_service_saaskul.crn_app_shell');

var _t = core._t;

var CYCLE_STEPS = [
    {step: 1, label: '1. Registered', xmlid: 'industry_fsm.project_task_action_all_fsm', theme: 'intake'},
    {step: 2, label: '2. Site Visited', xmlid: 'industry_fsm.project_task_action_all_fsm', theme: 'intake'},
    {step: 3, label: '3. Quotation Issued', xmlid: 'field_service_saaskul.action_fsm_project_task_to_quotation_issue', theme: 'quotation'},
    {step: 4, label: '4. QTN Approved', xmlid: 'industry_fsm.project_task_action_all_fsm', theme: 'quotation'},
    {step: 5, label: '5. Work in Progress', xmlid: 'industry_fsm.project_task_action_all_fsm', theme: 'execution'},
    {step: 6, label: '6. Waiting Invoice', xmlid: 'field_service_saaskul.action_fsm_project_task_to_invoice', theme: 'billing'},
    {step: 7, label: '7. Job Complete FOC', xmlid: 'industry_fsm.project_task_action_all_fsm', theme: 'billing'},
    {step: 8, label: '8. Job Invoiced', xmlid: 'industry_fsm.project_task_action_all_fsm', theme: 'billing'},
    {step: 9, label: '9. Approved', xmlid: 'field_service_saaskul.action_fsm_task_analysis_monitor', theme: 'closed'},
];

var CrnProcessingCycleAction = AbstractAction.extend({
    contentTemplate: 'CrnProcessingCycle',
    xmlDependencies: ['/field_service_saaskul/static/src/xml/crn_processing_cycle.xml'],

    events: {
        'click .o_crn_cycle_node': '_onNodeClick',
    },

    init: function (parent, action) {
        this._super(parent, action);
        this.activeNavKey = 'processing_cycle';
        this.cycleSteps = CYCLE_STEPS;
    },

    start: function () {
        this.set('title', _t('CRN Processing Cycle'));
        AppShell.activate();
        var self = this;
        return this._super.apply(this, arguments).then(function () {
            return AppShell.getSidebarOptions().then(function (options) {
                self._sidebarOptions = options;
                return self._mountShell();
            });
        });
    },

    destroy: function () {
        AppShell.deactivate();
        return this._super.apply(this, arguments);
    },

    _mountShell: function () {
        var self = this;
        var $content = this.$('.o_content').first();
        if (!$content.length) {
            $content = this.$el;
        }
        var $root = this.$('.o_crn_processing_cycle_root');
        var $layout = $content.children('.o_crn_app_layout').first();
        var $sidebarHost;
        var $main;
        if ($layout.length) {
            $sidebarHost = $layout.children('.o_crn_sidebar_host').first();
            $main = $layout.children('.o_crn_app_content').first();
            if (!$main.length) {
                $main = $layout.find('.o_crn_app_content').first();
            }
        } else {
            $layout = $('<div class="o_crn_app_layout"/>');
            $sidebarHost = $('<div class="o_crn_sidebar_host"/>');
            $main = $('<div class="o_crn_app_content o_crn_processing_cycle_main"/>');
            $layout.append($sidebarHost).append($main);
            $content.empty().append($layout);
        }
        $main.addClass('o_crn_processing_cycle_main');
        if ($root.length && !$main.has($root).length) {
            $main.empty().append($root);
        }
        AppShell.mountSidebar($sidebarHost, this.activeNavKey, function (item) {
            if (item.xmlid) {
                return self.do_action(item.xmlid, AppShell.listFirstOptions());
            }
            return $.when();
        }, this._sidebarOptions || {});
        this._renderCycle($main.find('.o_crn_cycle_ring'));
    },

    _renderCycle: function ($ring) {
        if (!$ring || !$ring.length) {
            return;
        }
        $ring.empty();
        var total = this.cycleSteps.length;
        _.each(this.cycleSteps, function (step, index) {
            var angle = (360 / total) * index - 90;
            var $node = $('<a href="#" class="o_crn_cycle_node o_crn_cycle_theme_' + step.theme + '"/>');
            $node.attr({
                'data-xmlid': step.xmlid,
                'data-step': step.step,
                title: step.label,
                style: '--crn-angle: ' + angle + 'deg;',
            });
            $node.append($('<span class="o_crn_cycle_step"/>').text(step.step));
            $node.append($('<span class="o_crn_cycle_label"/>').text(step.label));
            $ring.append($node);
        });
        $ring.css('--crn-cycle-total', total);
    },

    _onNodeClick: function (ev) {
        ev.preventDefault();
        var xmlid = $(ev.currentTarget).data('xmlid');
        if (xmlid) {
            this.do_action(xmlid, AppShell.listFirstOptions());
        }
    },
});

core.action_registry.add('crn_processing_cycle', CrnProcessingCycleAction);

return CrnProcessingCycleAction;
});
