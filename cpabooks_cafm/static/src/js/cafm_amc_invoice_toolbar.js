odoo.define('cpabooks_cafm.amc_invoice_toolbar', function (require) {
    'use strict';

    var core = require('web.core');
    var rpc = require('web.rpc');
    var _t = core._t;

    var YEARLY_VIEW_KEY = 'cpa_cafm_invoice_yearly_view';
    var STATUS_VIEW_KEY = 'cpa_cafm_invoice_status_view';
    var cafmInvoiceActionId = null;

    rpc.query({
        model: 'ir.model.data',
        method: 'xmlid_to_res_id',
        args: ['cpabooks_cafm.action_cpabooks_cafm_amc_invoices', false],
    }).then(function (actionId) {
        cafmInvoiceActionId = actionId;
    });

    function parseHashActionId() {
        var match = (window.location.hash || '').match(/(?:^|[?&#])action=(\d+)/);
        return match ? parseInt(match[1], 10) : null;
    }

    function readYearlyViewMode() {
        try {
            var value = window.sessionStorage.getItem(YEARLY_VIEW_KEY);
            if (value === '1' || value === 'true') {
                return true;
            }
            if (value === '0' || value === 'false') {
                return false;
            }
        } catch (e) {
            // ignore
        }
        return false;
    }

    function storeYearlyViewMode(on) {
        try {
            window.sessionStorage.setItem(YEARLY_VIEW_KEY, on ? '1' : '0');
        } catch (e) {
            // ignore
        }
    }

    function readStatusViewMode() {
        try {
            return window.sessionStorage.getItem(STATUS_VIEW_KEY) === '1';
        } catch (e) {
            return false;
        }
    }

    function storeStatusViewMode(on) {
        try {
            window.sessionStorage.setItem(STATUS_VIEW_KEY, on ? '1' : '0');
        } catch (e) {
            // ignore
        }
    }

    function isCafmInvoiceActionOpen() {
        var actionId = parseHashActionId();
        if (cafmInvoiceActionId && actionId === cafmInvoiceActionId) {
            return true;
        }
        return false;
    }

    function resolveInvoiceToolbarRoot(widget) {
        if (widget && widget.$buttons && widget.$buttons.length) {
            return widget.$buttons;
        }
        var $cp = null;
        if (widget && widget.$el && widget.$el.length) {
            $cp = widget.$el.closest('.o_action_manager').find('.o_control_panel').first();
        }
        if (!$cp || !$cp.length) {
            $cp = $('.o_control_panel:visible').first();
        }
        if (!$cp.length) {
            return null;
        }
        var $slot = $cp.find('.o_cpabooks_cafm_invoice_toolbar_root').first();
        if (!$slot.length) {
            var $buttons = $cp.find('.o_cp_buttons').first();
            if ($buttons.length) {
                $slot = $('<div class="o_cpabooks_cafm_invoice_toolbar_root d-inline-flex align-items-center flex-wrap"/>');
                $buttons.prepend($slot);
            } else {
                var $left = $cp.find('.o_cp_left').first();
                if (!$left.length) {
                    return null;
                }
                $slot = $('<div class="o_cpabooks_cafm_invoice_toolbar_root d-inline-flex align-items-center flex-wrap"/>');
                $left.append($slot);
            }
        }
        if (widget) {
            widget.$buttons = $slot;
        }
        return $slot;
    }

    function insertInvoiceToolbarButton(widget, $btn) {
        var $root = resolveInvoiceToolbarRoot(widget);
        if (!$root || !$root.length) {
            return;
        }
        var $create = $root.closest('.o_cp_buttons').find('.o_list_button_add').first();
        if (!$create.length) {
            $create = $root.find('.o_list_button_add').first();
        }
        if ($create.length) {
            $create.after($btn);
            return;
        }
        $root.append($btn);
    }

    function getInvoiceDomain(widget) {
        if (widget && widget.cafmInvoiceDomain) {
            try {
                return JSON.parse(JSON.stringify(widget.cafmInvoiceDomain));
            } catch (e) {
                return widget.cafmInvoiceDomain;
            }
        }
        return [];
    }

    function parseHashModel() {
        var match = (window.location.hash || '').match(/model=([^&]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function isNavbarCafmBrand() {
        try {
            return require('cpabooks_cafm.shell').isNavbarCafmBrand();
        } catch (e) {
            var brand = document.querySelector('.o_main_navbar .o_menu_brand');
            if (!brand) {
                return false;
            }
            var t = (brand.textContent || '').trim();
            return t === 'CAFM' || t.indexOf('CAFM') === 0;
        }
    }

    function isCafmInvoiceScreen() {
        if (parseHashModel() !== 'account.move') {
            return false;
        }
        if (isCafmInvoiceActionOpen()) {
            return true;
        }
        if (!isNavbarCafmBrand()) {
            return false;
        }
        var hash = window.location.hash || '';
        if (hash.indexOf('view_type=list') < 0 && hash.indexOf('view_type=kanban') < 0) {
            return false;
        }
        var title = ($('.o_control_panel .o_last_breadcrumb_item').text() || '').trim();
        if (!title) {
            title = ($('.o_control_panel .breadcrumb-item.active').last().text() || '').trim();
        }
        return title === 'Invoice';
    }

    function isCafmInvoiceList(widget) {
        if ($('.o_cafm_invoice_status_action:visible').length) {
            return true;
        }
        if (isCafmInvoiceScreen()) {
            return true;
        }
        if (isCafmInvoiceActionOpen()) {
            return true;
        }
        if (!widget || widget.modelName !== 'account.move') {
            return false;
        }
        var ctx = {};
        try {
            if (widget.initialState && widget.initialState.context) {
                ctx = widget.initialState.context;
            } else if (widget.model && widget.handle) {
                ctx = widget.model.get(widget.handle).getContext() || {};
            }
        } catch (e) {
            ctx = {};
        }
        if (ctx.cafm_amc_invoice_list || ctx.cafm_yearly_view_on) {
            return true;
        }
        try {
            if (widget.arch && widget.arch.indexOf('cafm_amc_invoice_list') >= 0) {
                return true;
            }
            if (widget.initialState && widget.initialState.fieldsView &&
                widget.initialState.fieldsView.arch &&
                widget.initialState.fieldsView.arch.indexOf('cafm_amc_invoice_list') >= 0) {
                return true;
            }
        } catch (e0) {
            // ignore
        }
        try {
            var domain = getInvoiceDomain(widget);
            var flat = JSON.stringify(domain);
            if (flat.indexOf('cafm_contract_order_ids') >= 0 ||
                flat.indexOf('cafm_amc_call_ids') >= 0) {
                return true;
            }
        } catch (e2) {
            // ignore
        }
        try {
            if (require('cpabooks_cafm.shell').isCafmAppActive()) {
                var title = ($('.o_control_panel .o_last_breadcrumb_item').text() || '').trim();
                if (!title) {
                    title = ($('.o_control_panel .breadcrumb-item.active').last().text() || '').trim();
                }
                if (title === 'Invoice') {
                    return true;
                }
            }
        } catch (e3) {
            // ignore
        }
        return false;
    }

    var _lastCafmInvoiceListController = null;

    function registerInvoiceListController(controller) {
        if (controller && controller.modelName === 'account.move') {
            _lastCafmInvoiceListController = controller;
        }
    }

    function syncToggleButton($btn, on) {
        if (!$btn || !$btn.length) {
            return;
        }
        $btn.toggleClass('btn-success', on);
        $btn.toggleClass('btn-secondary', !on);
        $btn.attr('aria-pressed', on ? 'true' : 'false');
    }

    function syncHeaderToggleButtons() {
        var yearlyOn = readYearlyViewMode();
        var statusOn = readStatusViewMode() || $('.o_cafm_invoice_status_action:visible').length > 0;
        syncToggleButton($('.o_cpabooks_amc_status_view_hdr_btn'), statusOn);
        syncToggleButton($('.o_cpabooks_amc_yearly_view_hdr_btn'), yearlyOn);
        if (statusOn) {
            $('.o_cpabooks_amc_yearly_view_hdr_btn').hide();
        } else {
            $('.o_cpabooks_amc_yearly_view_hdr_btn').show();
        }
    }

    function clearYearGroupSearchFacet(widget) {
        if (!widget || !widget.searchModel) {
            return;
        }
        try {
            var query = widget.searchModel.get('query') || [];
            var changed = false;
            var filtered = query.filter(function (leaf) {
                if (!leaf.groupBy) {
                    return true;
                }
                var gb = leaf.groupBy;
                var isYear = gb === 'invoice_date:year' ||
                    (_.isArray(gb) && gb.indexOf('invoice_date:year') >= 0);
                if (isYear) {
                    changed = true;
                    return false;
                }
                return true;
            });
            if (changed) {
                widget.searchModel.set('query', filtered);
            }
        } catch (e) {
            // ignore
        }
    }

    function hasYearGroup(widget) {
        try {
            if (!widget || !widget.model || !widget.handle) {
                return false;
            }
            var groupBy = widget.model.get(widget.handle).groupBy || [];
            return groupBy.indexOf('invoice_date:year') >= 0;
        } catch (e) {
            return false;
        }
    }

    function openStatusView(widget) {
        if (!core.action_registry.contains('cpabooks_cafm_amc_invoice_status')) {
            if (widget && widget.do_warn) {
                widget.do_warn(
                    _t('Status View'),
                    _t('Status view is not loaded. Please hard refresh (Ctrl+Shift+R) and try again.')
                );
            }
            return Promise.resolve();
        }
        storeStatusViewMode(true);
        var domain = getInvoiceDomain(widget);
        if (!domain.length) {
            return widget._rpc({
                model: 'account.move',
                method: 'action_cafm_open_status_view',
                args: [],
            }).then(function (action) {
                return widget.do_action(action);
            });
        }
        return widget.do_action({
            type: 'ir.actions.client',
            tag: 'cpabooks_cafm_amc_invoice_status',
            name: _t('AMC Invoice Status'),
            target: 'current',
            params: { domain: domain },
            context: {
                cafm_invoice_status_domain: domain,
                cafm_amc_invoice_list: 1,
            },
        });
    }

    function openInvoiceList(widget) {
        storeStatusViewMode(false);
        return widget.do_action('cpabooks_cafm.action_cpabooks_cafm_amc_invoices');
    }

    function injectCafmInvoiceToolbar(widget, options) {
        options = options || {};
        var mode = options.mode || (readStatusViewMode() ? 'status' : 'list');
        if (!isCafmInvoiceList(widget) && mode !== 'status') {
            return;
        }
        var $root = resolveInvoiceToolbarRoot(widget);
        if (!$root || !$root.length) {
            syncHeaderToggleButtons();
            return;
        }

        if ($root.find('.o_cpabooks_amc_invoice_status_view_btn').length) {
            syncHeaderToggleButtons();
            return;
        }

        var statusOn = mode === 'status' || readStatusViewMode();
        var yearlyOn = readYearlyViewMode();

        var $statusBtn = $('<button/>', {
            type: 'button',
            class: 'btn btn-sm o_cpabooks_amc_invoice_status_view_btn ml-1',
            text: _t('Status View'),
            title: _t('Toggle AMC Invoice Status grid'),
        });
        syncToggleButton($statusBtn, statusOn);

        var $yearlyBtn = $('<button/>', {
            type: 'button',
            class: 'btn btn-sm o_cpabooks_amc_invoice_yearly_btn ml-1',
            text: _t('Yearly View'),
            title: _t('Toggle invoice list grouped by year'),
        });
        syncToggleButton($yearlyBtn, yearlyOn);
        if (statusOn) {
            $yearlyBtn.hide();
        }

        $statusBtn.on('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            if (readStatusViewMode()) {
                openInvoiceList(widget);
            } else {
                openStatusView(widget);
            }
        });

        $yearlyBtn.on('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            if (mode === 'status') {
                return;
            }
            var yearlyNext = !readYearlyViewMode();
            storeYearlyViewMode(yearlyNext);
            syncToggleButton($yearlyBtn, yearlyNext);
            if (yearlyNext) {
                clearYearGroupSearchFacet(widget);
                if (widget.reload) {
                    widget.reload({ groupBy: ['invoice_date:year'] });
                }
            } else {
                clearYearGroupSearchFacet(widget);
                if (widget.reload) {
                    widget.reload({ groupBy: [] });
                }
            }
            syncHeaderToggleButtons();
        });

        insertInvoiceToolbarButton(widget, $statusBtn);
        $statusBtn.after($yearlyBtn);
        syncHeaderToggleButtons();
    }

    function setCafmInvoiceScreenActive(active) {
        if (active) {
            $('body').addClass('o_cafm_amc_invoice_screen');
        } else if (!$('.o_cafm_invoice_status_action:visible').length) {
            $('body').removeClass('o_cafm_amc_invoice_screen');
        }
    }

    function bootstrapCafmInvoiceList(widget) {
        if (!isCafmInvoiceList(widget)) {
            setCafmInvoiceScreenActive(false);
            return;
        }
        setCafmInvoiceScreenActive(true);
        var ctx = {};
        try {
            if (widget.initialState && widget.initialState.context) {
                ctx = widget.initialState.context;
            } else if (widget.model && widget.handle) {
                ctx = widget.model.get(widget.handle).getContext() || {};
            }
        } catch (e) {
            ctx = {};
        }
        if (ctx.cafm_yearly_view_on) {
            storeYearlyViewMode(true);
        }
        syncHeaderToggleButtons();
        if (widget._cafmInvoiceYearlyBootstrapped) {
            return;
        }
        widget._cafmInvoiceYearlyBootstrapped = true;
        if (!readYearlyViewMode() || hasYearGroup(widget)) {
            return;
        }
        window.setTimeout(function () {
            if (!readYearlyViewMode() || hasYearGroup(widget)) {
                return;
            }
            clearYearGroupSearchFacet(widget);
            if (widget.reload) {
                widget.reload({ groupBy: ['invoice_date:year'] });
            }
        }, 400);
    }

    function scheduleEnhanceInvoiceToolbar(widget, options) {
        injectCafmInvoiceToolbar(widget, options);
        window.setTimeout(function () {
            injectCafmInvoiceToolbar(widget, options);
        }, 100);
        window.setTimeout(function () {
            injectCafmInvoiceToolbar(widget, options);
        }, 500);
    }

    function startInvoiceToolbarWatcher() {
        if (window._cpaCafmInvoiceToolbarWatcher) {
            return;
        }
        window._cpaCafmInvoiceToolbarWatcher = true;
        window.setInterval(function () {
            if ($('.o_cafm_invoice_status_action:visible').length) {
                var statusWidget = window._cpaCafmStatusActionWidget;
                if (statusWidget) {
                    scheduleEnhanceInvoiceToolbar(statusWidget, { mode: 'status' });
                }
                syncHeaderToggleButtons();
                return;
            }
            if (!isCafmInvoiceActionOpen() && !isCafmInvoiceScreen() &&
                !$('.o_action_manager .o_list_view:visible').length) {
                return;
            }
            var ctrl = _lastCafmInvoiceListController;
            if (ctrl && isCafmInvoiceList(ctrl)) {
                scheduleEnhanceInvoiceToolbar(ctrl, { mode: 'list' });
            }
            syncHeaderToggleButtons();
        }, 1000);
    }

    startInvoiceToolbarWatcher();

    return {
        readYearlyViewMode: readYearlyViewMode,
        storeYearlyViewMode: storeYearlyViewMode,
        readStatusViewMode: readStatusViewMode,
        storeStatusViewMode: storeStatusViewMode,
        isCafmInvoiceList: isCafmInvoiceList,
        isCafmInvoiceScreen: isCafmInvoiceScreen,
        isCafmInvoiceActionOpen: isCafmInvoiceActionOpen,
        registerInvoiceListController: registerInvoiceListController,
        resolveInvoiceToolbarRoot: resolveInvoiceToolbarRoot,
        insertInvoiceToolbarButton: insertInvoiceToolbarButton,
        injectCafmInvoiceToolbar: injectCafmInvoiceToolbar,
        scheduleEnhanceInvoiceToolbar: scheduleEnhanceInvoiceToolbar,
        bootstrapCafmInvoiceList: bootstrapCafmInvoiceList,
        setCafmInvoiceScreenActive: setCafmInvoiceScreenActive,
        openStatusView: openStatusView,
        openInvoiceList: openInvoiceList,
        getInvoiceDomain: getInvoiceDomain,
        syncHeaderToggleButtons: syncHeaderToggleButtons,
    };
});
