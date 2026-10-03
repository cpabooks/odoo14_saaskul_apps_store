odoo.define('cpabooks_cafm.amc_register_import', function (require) {
    'use strict';

    var ListController = require('web.ListController');
    var ListView = require('web.ListView');
    var viewRegistry = require('web.view_registry');
    var core = require('web.core');
    var _t = core._t;
    var MONTH_FILTER_KEY = 'cpa_cafm_amc_register_month_key';
    var NEXT_INVOICE_MODE_KEY = 'cpa_cafm_amc_next_invoice_mode';
    var MONTH_ALL = 'all';

    // Do not wipe optional-column prefs for month.line Register (3-dots).
    // Only clear very old prefs that targeted the old fat contract tree key.
    try {
        Object.keys(window.localStorage || {}).forEach(function (key) {
            if (
                key.indexOf('optional') !== -1 &&
                key.indexOf('cpabooks.cafm.contract.tree') !== -1 &&
                key.indexOf('month.line') === -1
            ) {
                window.localStorage.removeItem(key);
            }
        });
    } catch (e) {
        // ignore
    }

    function resolveToolbarRoot(controller) {
        if (controller.$buttons && controller.$buttons.length) {
            return controller.$buttons;
        }
        var $cp = controller.$el.closest('.o_action_manager').find('.o_control_panel').first();
        if (!$cp.length) {
            $cp = $('.o_control_panel:visible').first();
        }
        if (!$cp.length) {
            return null;
        }
        var $slot = $cp.find('.o_cpabooks_amc_toolbar_root').first();
        if (!$slot.length) {
            var $buttons = $cp.find('.o_cp_buttons').first();
            if ($buttons.length) {
                $slot = $('<div class="o_cpabooks_amc_toolbar_root d-inline-flex align-items-center flex-wrap mr-2"/>');
                $buttons.prepend($slot);
            } else {
                var $left = $cp.find('.o_cp_left').first();
                if (!$left.length) {
                    return null;
                }
                $slot = $('<div class="o_cpabooks_amc_toolbar_root d-inline-flex align-items-center flex-wrap"/>');
                $left.append($slot);
            }
        }
        controller.$buttons = $slot;
        return $slot;
    }

    function insertAfterCreateOrBeforeWrap(controller, $btn) {
        var $root = resolveToolbarRoot(controller);
        if (!$root || !$root.length) {
            return;
        }
        var $create = $root.find('.o_list_button_add, .o_cpabooks_amc_create_btn').first();
        if ($create.length) {
            $create.after($btn);
            return;
        }
        var $wrapControls = $root.find('.o_cpabooks_list_wrap_controls');
        if ($wrapControls.length) {
            $wrapControls.before($btn);
            return;
        }
        var $wrapToggle = $root.find('.o_cpabooks_wrap_toggle');
        if ($wrapToggle.length) {
            $wrapToggle.parent().before($btn);
            return;
        }
        $root.append($btn);
    }

    function addAmcRegisterFormatButton(controller) {
        var $root = resolveToolbarRoot(controller);
        if (!$root || !$root.length) {
            return;
        }
        if ($root.find('.o_cpabooks_amc_register_format_btn').length) {
            return;
        }
        var $formatBtn = $('<button/>', {
            type: 'button',
            class: 'btn btn-secondary btn-sm o_cpabooks_amc_register_format_btn ml-1',
            text: 'Format',
        });
        insertAfterCreateOrBeforeWrap(controller, $formatBtn);
        $formatBtn.on('click', function () {
            controller.do_action({
                type: 'ir.actions.act_window',
                name: 'Import AMC Contracts',
                res_model: 'cpabooks.cafm.amc.import',
                views: [[false, 'form']],
                target: 'new',
            });
        });
    }

    function readStoredMonthKey() {
        try {
            return window.sessionStorage.getItem(MONTH_FILTER_KEY) || '';
        } catch (e) {
            return '';
        }
    }

    function storeMonthKey(key) {
        try {
            if (key) {
                window.sessionStorage.setItem(MONTH_FILTER_KEY, key);
            } else {
                window.sessionStorage.removeItem(MONTH_FILTER_KEY);
            }
        } catch (e) {
            // ignore
        }
    }

    function readNextInvoiceMode() {
        try {
            var v = window.sessionStorage.getItem(NEXT_INVOICE_MODE_KEY);
            if (v === '0' || v === 'false') {
                return false;
            }
        } catch (e) {
            // ignore
        }
        return true;
    }

    function storeNextInvoiceMode(on) {
        try {
            window.sessionStorage.setItem(NEXT_INVOICE_MODE_KEY, on ? '1' : '0');
        } catch (e) {
            // ignore
        }
    }

    function baseActionContext(controller) {
        var context = _.extend({}, controller.initialState && controller.initialState.context);
        delete context.search_default_group_next_invoice;
        delete context.group_by;
        return context;
    }

    function applyViewMode(controller, nextInvoiceOn, monthKey) {
        if (!controller) {
            return Promise.resolve();
        }
        var context = baseActionContext(controller);
        var domain = [['active', '=', true]];
        var groupBy = [];

        if (!nextInvoiceOn) {
            return controller.reload({
                domain: domain,
                context: context,
                groupBy: [],
            });
        }

        monthKey = monthKey || MONTH_ALL;
        if (monthKey === MONTH_ALL) {
            groupBy = ['month_label'];
            context.group_by = groupBy;
            return controller._rpc({
                model: 'cpabooks.cafm.contract.month.line',
                method: 'cafm_register_rolling_month_keys',
                args: [],
            }).then(function (keys) {
                if (keys && keys.length) {
                    domain.push(['month_key', 'in', keys]);
                }
                return controller.reload({
                    domain: domain,
                    context: context,
                    groupBy: groupBy,
                });
            });
        }
        domain.push(['month_key', '=', monthKey]);
        return controller.reload({
            domain: domain,
            context: context,
            groupBy: [],
        });
    }

    function syncNextInvoiceToolbar(controller) {
        var $root = resolveToolbarRoot(controller);
        if (!$root) {
            return;
        }
        var on = readNextInvoiceMode();
        var $toggle = $root.find('.o_cpabooks_amc_next_invoice_toggle');
        var $wrap = $root.find('.o_cpabooks_amc_next_invoice_filter');
        $toggle.toggleClass('btn-success', on);
        $toggle.toggleClass('btn-secondary', !on);
        $toggle.attr('aria-pressed', on ? 'true' : 'false');
        $wrap.toggle(on);
    }

    function clearNextInvoiceSearchFacet(controller) {
        if (!controller.searchModel) {
            return;
        }
        try {
            var query = controller.searchModel.get('query') || [];
            var changed = false;
            var filtered = query.filter(function (leaf) {
                if (!leaf.groupBy) {
                    return true;
                }
                var gb = leaf.groupBy;
                if (gb === 'month_label' || (_.isArray(gb) && gb.indexOf('month_label') >= 0)) {
                    changed = true;
                    return false;
                }
                return true;
            });
            if (changed) {
                controller.searchModel.set('query', filtered);
            }
        } catch (e) {
            // ignore
        }
    }

    function formatAmount(value) {
        var n = parseFloat(value);
        if (isNaN(n)) {
            return '0.00';
        }
        return n.toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function injectGrandTotals(controller) {
        if (!controller || !controller.$el) {
            return;
        }
        var monthKey = readStoredMonthKey() || MONTH_ALL;
        controller.$el.find('.o_cpabooks_amc_grand_total_row').remove();
        if (!readNextInvoiceMode() || monthKey !== MONTH_ALL) {
            return;
        }
        var domain = [['active', '=', true]];
        try {
            if (controller.model && controller.handle) {
                domain = controller.model.get(controller.handle).getDomain() || domain;
            }
        } catch (e) {
            // keep default domain
        }
        controller._rpc({
            model: 'cpabooks.cafm.contract.month.line',
            method: 'cafm_register_amount_totals',
            args: [domain],
        }).then(function (totals) {
            if (!totals) {
                return;
            }
            var $table = controller.$('table.o_list_table');
            if (!$table.length) {
                return;
            }
            var $monthlyTh = $table.find('thead th[data-name="monthly_revenue"]');
            var $invoiceTh = $table.find('thead th[data-name="invoicing_value"]');
            if (!$monthlyTh.length || !$invoiceTh.length) {
                return;
            }
            var colCount = $table.find('thead th').length;
            var monthlyIdx = $monthlyTh.index();
            var invoiceIdx = $invoiceTh.index();
            var cells = [];
            var i;
            for (i = 0; i < colCount; i++) {
                if (i === 0) {
                    cells.push('<td class="o_cpabooks_amc_grand_total_label"><strong>Total</strong></td>');
                } else if (i === monthlyIdx) {
                    cells.push(
                        '<td class="o_cpabooks_amc_grand_total_cell o_data_cell">' +
                        '<strong>' + formatAmount(totals.monthly_revenue) + '</strong></td>'
                    );
                } else if (i === invoiceIdx) {
                    cells.push(
                        '<td class="o_cpabooks_amc_grand_total_cell o_data_cell">' +
                        '<strong>' + formatAmount(totals.invoicing_value) + '</strong></td>'
                    );
                } else {
                    cells.push('<td class="o_cpabooks_amc_grand_total_cell"></td>');
                }
            }
            var $tfoot = $table.children('tfoot');
            if (!$tfoot.length) {
                $tfoot = $('<tfoot class="o_cpabooks_amc_grand_total_foot"/>');
                $table.append($tfoot);
            }
            $tfoot.html('<tr class="o_cpabooks_amc_grand_total_row">' + cells.join('') + '</tr>');
        });
    }

    function scheduleGrandTotals(controller) {
        if (!controller) {
            return;
        }
        clearTimeout(controller._grandTotalTimer);
        controller._grandTotalTimer = setTimeout(function () {
            injectGrandTotals(controller);
        }, 400);
    }

    function addAmcRegisterNextInvoiceFilter(controller) {
        var $root = resolveToolbarRoot(controller);
        if (!$root || !$root.length) {
            return;
        }
        if ($root.find('.o_cpabooks_amc_next_invoice_toggle').length) {
            syncNextInvoiceToolbar(controller);
            return;
        }
        var $toggle = $('<button/>', {
            type: 'button',
            class: 'btn btn-sm o_cpabooks_amc_next_invoice_toggle ml-2',
            text: _t('Next Invoice'),
            title: _t('Toggle monthly Next Invoice view'),
        });
        var $wrap = $('<div class="o_cpabooks_amc_next_invoice_filter ml-1"/>');
        var $select = $('<select/>', {
            id: 'o_cpabooks_amc_next_invoice_select',
            class: 'custom-select custom-select-sm',
            'aria-label': _t('Next Invoice month'),
        });
        $wrap.append($select);
        var $print = $root.find('.o_cpabooks_amc_register_print_btn');
        if ($print.length) {
            $print.after($toggle);
            $toggle.after($wrap);
        } else {
            insertAfterCreateOrBeforeWrap(controller, $toggle);
            $toggle.after($wrap);
        }
        $toggle.on('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var on = !readNextInvoiceMode();
            storeNextInvoiceMode(on);
            syncNextInvoiceToolbar(controller);
            clearNextInvoiceSearchFacet(controller);
            applyViewMode(controller, on, readStoredMonthKey() || MONTH_ALL).then(function () {
                scheduleGrandTotals(controller);
            });
        });
        controller._rpc({
            model: 'cpabooks.cafm.contract.month.line',
            method: 'cafm_register_month_filter_options',
            args: [],
        }).then(function (options) {
            options = options || [];
            var stored = readStoredMonthKey();
            var defaultKey = stored || MONTH_ALL;
            $select.empty();
            $select.append($('<option/>', {
                value: MONTH_ALL,
                text: _t('All'),
            }));
            options.forEach(function (opt) {
                $select.append($('<option/>', {
                    value: opt.key,
                    text: opt.label,
                }));
            });
            $select.val(defaultKey);
            storeMonthKey(defaultKey);
            syncNextInvoiceToolbar(controller);
            clearNextInvoiceSearchFacet(controller);
            if (!controller._cpaAmcMonthFilterApplied) {
                controller._cpaAmcMonthFilterApplied = true;
                applyViewMode(controller, readNextInvoiceMode(), defaultKey).then(function () {
                    scheduleGrandTotals(controller);
                });
            } else {
                scheduleGrandTotals(controller);
            }
        });
        $select.on('change', function () {
            if (!readNextInvoiceMode()) {
                return;
            }
            var key = $select.val() || MONTH_ALL;
            storeMonthKey(key);
            clearNextInvoiceSearchFacet(controller);
            applyViewMode(controller, true, key).then(function () {
                scheduleGrandTotals(controller);
            });
        });
    }

    function addAmcRegisterPrintButton(controller) {
        var $root = resolveToolbarRoot(controller);
        if (!$root || !$root.length) {
            return;
        }
        if ($root.find('.o_cpabooks_amc_register_print_btn').length) {
            return;
        }
        var $printBtn = $('<button/>', {
            type: 'button',
            class: 'btn btn-secondary btn-sm o_cpabooks_amc_register_print_btn ml-1',
            text: _t('Print'),
            title: _t('Print AMC Contracts To be Invoiced'),
        });
        var $format = $root.find('.o_cpabooks_amc_register_format_btn');
        if ($format.length) {
            $format.after($printBtn);
        } else {
            insertAfterCreateOrBeforeWrap(controller, $printBtn);
        }
        $printBtn.on('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var domain = [];
            try {
                if (controller.model && controller.handle) {
                    domain = controller.model.get(controller.handle).getDomain() || [];
                }
            } catch (e) {
                domain = [];
            }
            // Domain from month.line list may include group leaves; keep only serializable domain
            try {
                domain = JSON.parse(JSON.stringify(domain));
            } catch (e2) {
                domain = [];
            }
            controller._rpc({
                model: 'cpabooks.cafm.contract',
                method: 'action_open_next_invoice_print_wizard',
                args: [domain],
            }).then(function (action) {
                if (!action) {
                    return controller.do_warn(
                        _t('Print'),
                        _t('Could not open print wizard.')
                    );
                }
                // Ensure modal form (some clients ignore view_mode-only actions)
                action.views = action.views || [[false, 'form']];
                action.view_mode = action.view_mode || 'form';
                action.target = 'new';
                return controller.do_action(action);
            }).guardedCatch(function () {
                controller.do_warn(
                    _t('Print'),
                    _t('Print wizard failed. Check access rights and try again.')
                );
            });
        });
    }

    function ensureAmcCreateButton(controller) {
        var $root = resolveToolbarRoot(controller);
        if (!$root || !$root.length) {
            return;
        }
        $root.find('.o_list_button_add').addClass('d-none');
        if ($root.find('.o_cpabooks_amc_create_btn').length) {
            return;
        }
        var $createBtn = $('<button/>', {
            type: 'button',
            class: 'btn btn-primary o_cpabooks_amc_create_btn',
            text: _t('Create AMC Contract'),
            title: _t('Create AMC Contract'),
        });
        insertAfterCreateOrBeforeWrap(controller, $createBtn);
        var $format = $root.find('.o_cpabooks_amc_register_format_btn');
        if ($format.length) {
            $format.before($createBtn);
        } else {
            $root.prepend($createBtn);
        }
        $createBtn.on('click', function (ev) {
            ev.preventDefault();
            controller.do_action({
                type: 'ir.actions.act_window',
                name: _t('Create AMC Contract'),
                res_model: 'cpabooks.cafm.contract',
                views: [[false, 'form']],
                target: 'current',
            });
        });
    }

    function getListDomain(controller) {
        var domain = [['active', '=', true]];
        try {
            if (controller.model && controller.handle) {
                domain = controller.model.get(controller.handle).getDomain() || domain;
            }
        } catch (e) {
            domain = [['active', '=', true]];
        }
        try {
            domain = JSON.parse(JSON.stringify(domain));
        } catch (e2) {
            domain = [['active', '=', true]];
        }
        return domain;
    }

    function addAmcRegisterXViewButton(controller) {
        var $root = resolveToolbarRoot(controller);
        if (!$root || !$root.length) {
            return;
        }
        if ($root.find('.o_cpabooks_amc_register_xview_btn').length) {
            return;
        }
        var $xBtn = $('<button/>', {
            type: 'button',
            class: 'btn btn-secondary btn-sm o_cpabooks_amc_register_xview_btn ml-1',
            text: _t('X View'),
            title: _t('Revenue schedule grid (Jan–Dec)'),
        });
        var $print = $root.find('.o_cpabooks_amc_register_print_btn');
        if ($print.length) {
            $print.after($xBtn);
        } else {
            insertAfterCreateOrBeforeWrap(controller, $xBtn);
        }
        $xBtn.on('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            if (!core.action_registry.contains('cpabooks_cafm_amc_x_view')) {
                controller.do_warn(
                    _t('X View'),
                    _t('X View is not loaded. Hard refresh (Ctrl+Shift+R) and try again.')
                );
                return;
            }
            var domain = getListDomain(controller);
            controller.do_action('cpabooks_cafm.action_cpabooks_cafm_amc_x_view', {
                additional_context: {
                    cafm_x_view_domain: domain,
                },
            }).guardedCatch(function (err) {
                var msg = (err && err.message && err.message.data && err.message.data.message) ||
                    (err && err.message) ||
                    _t('Could not open X View.');
                controller.do_warn(_t('X View'), msg);
            });
        });
    }

    function enhanceAmcRegisterButtons(controller) {
        resolveToolbarRoot(controller);
        try {
            $('.o_cpabooks_amc_title_create_btn').remove();
        } catch (e) {
            // ignore
        }
        ensureAmcCreateButton(controller);
        addAmcRegisterFormatButton(controller);
        addAmcRegisterPrintButton(controller);
        addAmcRegisterXViewButton(controller);
        addAmcRegisterNextInvoiceFilter(controller);
        try {
            require("cpabooks_leftsidebar_view.toggles").injectNow(true);
        } catch (e) {
            // leftsidebar module optional
        }
    }

    function extractContractId(recordData) {
        var c = recordData && recordData.contract_id;
        if (!c) {
            return false;
        }
        if (typeof c === 'number') {
            return c;
        }
        if (_.isArray(c)) {
            return c[0] || false;
        }
        if (c.res_id) {
            return c.res_id;
        }
        if (c.data && (c.data.id || c.data.res_id)) {
            return c.data.id || c.data.res_id;
        }
        if (c.id && typeof c.id === 'number') {
            return c.id;
        }
        return false;
    }

    var AmcRegisterListController = ListController.extend({
        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            if ($node && $node.length && (!this.$buttons || !this.$buttons.length)) {
                this.$buttons = $node;
            }
            var self = this;
            function runEnhance() {
                resolveToolbarRoot(self);
                enhanceAmcRegisterButtons(self);
            }
            runEnhance();
            window.setTimeout(runEnhance, 100);
            window.setTimeout(runEnhance, 500);
        },
        on_attach_callback: function () {
            if (this._super) {
                this._super.apply(this, arguments);
            }
            enhanceAmcRegisterButtons(this);
            clearNextInvoiceSearchFacet(this);
            scheduleGrandTotals(this);
        },
        update: function () {
            var result = this._super.apply(this, arguments);
            scheduleGrandTotals(this);
            return result;
        },
        /**
         * Row click uses open_record → _onOpenRecord (not openRecord).
         * Open the linked AMC contract form instead of month.line.
         */
        _onOpenRecord: function (ev) {
            ev.stopPropagation();
            var self = this;
            var record = this.model.get(ev.data.id, {raw: true});

            function openContract(cid) {
                if (!cid) {
                    return self.do_warn(
                        _t('AMC Contract'),
                        _t('No linked contract found for this row.')
                    );
                }
                return self.do_action({
                    type: 'ir.actions.act_window',
                    name: _t('AMC Contract'),
                    res_model: 'cpabooks.cafm.contract',
                    res_id: cid,
                    views: [[false, 'form']],
                    view_mode: 'form',
                    target: 'current',
                });
            }

            var contractId = extractContractId(record && record.data);
            if (contractId) {
                return openContract(contractId);
            }
            var lineId = record && record.res_id;
            if (!lineId) {
                return openContract(false);
            }
            return this._rpc({
                model: 'cpabooks.cafm.contract.month.line',
                method: 'read',
                args: [[lineId], ['contract_id']],
            }).then(function (rows) {
                var cid = rows && rows[0] && rows[0].contract_id && rows[0].contract_id[0];
                return openContract(cid);
            });
        },
    });

    var AmcRegisterListView = ListView.extend({
        config: _.extend({}, ListView.prototype.config, {
            Controller: AmcRegisterListController,
        }),
    });

    viewRegistry.add('cafm_amc_register_list', AmcRegisterListView);
});
