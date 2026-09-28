odoo.define('cpabooks_cafm.amc_invoice_import', function (require) {
    'use strict';

    require('cpabooks_cafm.amc_invoice_status_view');

    var ListController = require('web.ListController');
    var ListView = require('web.ListView');
    var viewRegistry = require('web.view_registry');
    var toolbar = require('cpabooks_cafm.amc_invoice_toolbar');

    function enhanceInvoiceListController(controller) {
        if (!toolbar.isCafmInvoiceList(controller)) {
            return;
        }
        toolbar.scheduleEnhanceInvoiceToolbar(controller, { mode: 'list' });
    }

    function onInvoiceListAttach(controller) {
        if (!toolbar.isCafmInvoiceList(controller)) {
            toolbar.setCafmInvoiceScreenActive(false);
            return;
        }
        toolbar.setCafmInvoiceScreenActive(true);
        toolbar.scheduleEnhanceInvoiceToolbar(controller, { mode: 'list' });
        toolbar.bootstrapCafmInvoiceList(controller);
        try {
            require('cpabooks_cafm.shell').requestSyncSidebar(true);
        } catch (e) { /* ignore */ }
    }

    var AmcInvoiceListController = ListController.extend({
        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            if ($node && $node.length && (!this.$buttons || !this.$buttons.length)) {
                this.$buttons = $node;
            }
            enhanceInvoiceListController(this);
        },
        on_attach_callback: function () {
            if (this._super) {
                this._super.apply(this, arguments);
            }
            onInvoiceListAttach(this);
        },
    });

    var AmcInvoiceListView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: AmcInvoiceListController,
        }),
    });

    viewRegistry.add('cafm_amc_invoice_list', AmcInvoiceListView);

    try {
        var accountTreeView = viewRegistry.get('account_tree');
        if (accountTreeView && accountTreeView.prototype.config && accountTreeView.prototype.config.Controller) {
            var AccountTreeController = accountTreeView.prototype.config.Controller;
            accountTreeView.config.Controller = AccountTreeController.extend({
                renderButtons: function ($node) {
                    var result = this._super.apply(this, arguments);
                    if (toolbar.isCafmInvoiceList(this)) {
                        enhanceInvoiceListController(this);
                    }
                    return result;
                },
                on_attach_callback: function () {
                    if (this._super) {
                        this._super.apply(this, arguments);
                    }
                    if (toolbar.isCafmInvoiceList(this)) {
                        onInvoiceListAttach(this);
                    }
                },
            });
        }
    } catch (e) {
        // ignore if account_tree is unavailable
    }

    ListController.include({
        init: function () {
            this._super.apply(this, arguments);
            toolbar.registerInvoiceListController(this);
        },
        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            if (toolbar.isCafmInvoiceList(this)) {
                enhanceInvoiceListController(this);
            }
            if (!this.$buttons) {
                return;
            }
            if (this.modelName === 'cpabooks.cafm.amc.invoice.reg') {
                if (this.$buttons.find('.o_cpabooks_amc_invoice_format_btn').length === 0) {
                    var $formatBtn = $('<button/>', {
                        type: 'button',
                        class: 'btn btn-secondary btn-sm o_cpabooks_amc_invoice_format_btn ml-1',
                        text: 'Format',
                    });
                    this.$buttons.append($formatBtn);
                    var self = this;
                    $formatBtn.on('click', function () {
                        self.do_action({
                            type: 'ir.actions.act_window',
                            name: 'Import AMC Invoices',
                            res_model: 'cpabooks.cafm.amc.invoice.import',
                            views: [[false, 'form']],
                            target: 'new',
                        });
                    });
                }
            }
        },
        on_attach_callback: function () {
            if (this._super) {
                this._super.apply(this, arguments);
            }
            if (toolbar.isCafmInvoiceList(this)) {
                onInvoiceListAttach(this);
            }
        },
    });
});
