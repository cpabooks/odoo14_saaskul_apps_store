odoo.define('cpabooks_cafm.tally_list_view', function (require) {
    "use strict";

    var ListController = require('web.ListController');
    var ListRenderer = require('web.ListRenderer');
    var ListView = require('web.ListView');
    var viewRegistry = require('web.view_registry');

    // Odoo 14 does not set data-group-level; CSS year/month colors need it.
    ListRenderer.include({
        _renderGroupRow: function (group, groupLevel) {
            var $row = this._super.apply(this, arguments);
            $row.attr('data-group-level', String(groupLevel));
            return $row;
        },
    });

    var TallyListController = ListController.extend({
        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            if (!this.$buttons) {
                return;
            }
            // One Expand/Collapse toggle only (never duplicate on re-render).
            if (this.$buttons.find('.o_tally_toggle_expand_btn').length === 0) {
                var $toggleExpandBtn = $('<button type="button" class="btn btn-secondary o_tally_toggle_expand_btn" style="margin-left: 5px;">Expand</button>');
                $toggleExpandBtn.on('click', this._onToggleExpandCollapse.bind(this));
                this.$buttons.append($toggleExpandBtn);
            }
            if (this.$buttons.find('.o_tally_print_report_btn').length === 0) {
                var $printReportBtn = $('<button type="button" class="btn btn-primary o_tally_print_report_btn" style="margin-left: 5px;">Print Report</button>');
                $printReportBtn.on('click', this._onPrintReport.bind(this));
                this.$buttons.append($printReportBtn);
            }
            this._updateExpandCollapseLabel();
        },
        _hasCollapsedGroups: function () {
            return this.$el.find('tr.o_group_header:not(.o_group_open)').length > 0;
        },
        _updateExpandCollapseLabel: function () {
            if (!this.$buttons) {
                return;
            }
            var $btn = this.$buttons.find('.o_tally_toggle_expand_btn');
            if (!$btn.length) {
                return;
            }
            // Collapsed groups exist → next action is Expand; else Collapse.
            $btn.text(this._hasCollapsedGroups() ? 'Expand' : 'Collapse');
        },
        _onToggleExpandCollapse: function () {
            if (this._hasCollapsedGroups()) {
                this._onExpandAll();
            } else {
                this._onCollapseAll();
            }
        },
        _onExpandAll: function () {
            // Manual only — never call from update/start (re-triggers RPC storm on nested group_by).
            var self = this;
            if (this._cpabooksExpandInProgress) {
                return;
            }
            this._cpabooksExpandInProgress = true;
            var attempts = 0;
            function expandRecursively() {
                var $collapsed = self.$el.find('tr.o_group_header:not(.o_group_open)');
                if ($collapsed.length > 0 && attempts < 12) {
                    attempts++;
                    $collapsed.first().trigger('click');
                    setTimeout(expandRecursively, 400);
                } else {
                    self._cpabooksExpandInProgress = false;
                    self._updateExpandCollapseLabel();
                }
            }
            expandRecursively();
        },
        _onCollapseAll: function () {
            this._cpabooksExpandInProgress = false;
            var $expanded = this.$el.find('tr.o_group_header.o_group_open');
            $($expanded.get().reverse()).each(function () {
                $(this).trigger('click');
            });
            this._updateExpandCollapseLabel();
        },
        _onPrintReport: function () {
            var isAmcInvoice = this.modelName === 'cpabooks.cafm.amc.invoice.reg';
            this.do_action({
                name: isAmcInvoice ? 'Print AMC Invoices' : 'Print VAR Work Statement',
                type: 'ir.actions.act_window',
                res_model: isAmcInvoice
                    ? 'cpabooks.amc.invoice.print.wizard'
                    : 'cpabooks.var.print.wizard',
                views: [[false, 'form']],
                target: 'new',
                context: {},
            });
        },
    });

    var TallyListView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: TallyListController,
        }),
    });

    viewRegistry.add('cafm_tally_list', TallyListView);
    return TallyListView;
});
