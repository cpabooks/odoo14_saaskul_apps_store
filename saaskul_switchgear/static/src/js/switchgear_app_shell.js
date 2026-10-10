odoo.define('saaskul_switchgear.switchgear_app_shell', function (require) {
'use strict';

var ActionManager = require('web.ActionManager');
var core = require('web.core');

var SHELL_CLASS = 'o_switchgear_app_shell';
var MAIN_MENU_CLASS = 'o_switchgear_show_main_menu';

var NAV_ITEMS = [
    {section: 'Home', sectionClass: 'o_switchgear_section_home', items: [
        {key: 'dashboard', label: 'Dashboard', xmlid: 'saaskul_switchgear.action_switchgear_dashboard'},
        {key: 'tutorial', label: 'Tutorial Wizard', xmlid: 'saaskul_switchgear.action_switchgear_tutorial_wizard'},
        {key: 'processing_cycle', label: 'Saaskul Switchgear processing cycle', xmlid: 'saaskul_switchgear.action_switchgear_processing_cycle'},
        {key: 'flowchart', label: 'Process Flowchart', xmlid: 'saaskul_switchgear.action_flowchart_kanban'},
        {key: 'main_menu', label: 'Apps Home', special: 'open_app_menu'},
    ]},
    {section: 'CRM', sectionClass: 'o_switchgear_section_crm', items: [
        {key: 'enquiry', label: 'Pipeline (Opportunities)', xmlid: 'crm.crm_lead_action_pipeline'},
        {key: 'crm_leads', label: 'Leads', xmlid: 'crm.crm_lead_all_leads'},
        {key: 'estimation', label: 'Estimation', xmlid: 'saaskul_switchgear.action_job_estimate'},
        {key: 'quotation', label: 'Quotation (Sales)', xmlid: 'sale.action_quotations_with_onboarding'},
    ]},
    {section: 'Manufacturing', sectionClass: 'o_switchgear_section_manufacturing', items: [
        {key: 'mrp_order', label: 'Manufacturing Orders', xmlid: 'mrp.mrp_production_action'},
        {key: 'mrp_workorders', label: 'Work Orders', xmlid: 'mrp.mrp_workorder_todo'},
        {key: 'bom', label: 'Bills of Materials', xmlid: 'mrp.mrp_bom_form_action'},
        {key: 'design', label: 'Design (Documents)', xmlid: 'saaskul_switchgear.action_switchgear_design_document'},
        {key: 'purchase_req', label: 'Purchase Requisition', xmlid: 'saaskul_switchgear.action_material_purchase_requisition'},
    ]},
    {section: 'Inventory', sectionClass: 'o_switchgear_section_inventory', items: [
        {key: 'stock_check', label: 'Operations Overview', xmlid: 'stock.stock_picking_type_action'},
        {key: 'stock_transfers', label: 'Transfers', xmlid: 'stock.action_picking_tree_all'},
        {key: 'grn', label: 'Receipts (GRN)', xmlid: 'saaskul_switchgear.action_switchgear_stock_incoming'},
        {key: 'delivery', label: 'Delivery Orders', xmlid: 'saaskul_switchgear.action_switchgear_stock_outgoing'},
        {key: 'stock_adjustments', label: 'Inventory Adjustments', xmlid: 'stock.action_inventory_form'},
        {key: 'stock_replenish', label: 'Reordering Rules', xmlid: 'stock.action_orderpoint'},
        {key: 'stock_products', label: 'Products', xmlid: 'stock.product_template_action_product'},
        {key: 'inv_valuation_live', label: 'Inventory Valuation', xmlid: 'stock_account.stock_valuation_layer_action'},
        {key: 'lpo_purchase', label: 'Purchase (LPO / RFQ)', xmlid: 'purchase.purchase_rfq'},
    ]},
    {section: 'Quality', sectionClass: 'o_switchgear_section_quality', items: [
        {key: 'quality', label: 'Quality Overview', xmlid: 'saaskul_switchgear.quality_alert_team_action'},
        {key: 'quality_checks', label: 'Quality Checks', xmlid: 'saaskul_switchgear.quality_check_action_main'},
        {key: 'quality_alerts', label: 'Quality Alerts', xmlid: 'saaskul_switchgear.quality_alert_action'},
    ]},
    {section: 'Timesheet', sectionClass: 'o_switchgear_section_timesheet', items: [
        {key: 'timesheet_mine', label: 'My Timesheets', xmlid: 'hr_timesheet.act_hr_timesheet_line'},
        {key: 'timesheet_all', label: 'All Timesheets', xmlid: 'hr_timesheet.timesheet_action_all'},
        {key: 'timesheet_report', label: 'Timesheet Analysis', xmlid: 'hr_timesheet.act_hr_timesheet_report'},
    ]},
    {section: 'Employees', sectionClass: 'o_switchgear_section_employees', items: [
        {key: 'hr_employees', label: 'Employees', xmlid: 'hr.open_view_employee_list_my'},
        {key: 'hr_directory', label: 'Employee Directory', xmlid: 'hr.hr_employee_public_action'},
        {key: 'hr_departments', label: 'Departments', xmlid: 'hr.hr_department_tree_action'},
        {key: 'hr_jobs', label: 'Job Positions', xmlid: 'hr.action_hr_job'},
    ]},
    {section: 'Projects', sectionClass: 'o_switchgear_section_projects', items: [
        {key: 'project_list', label: 'Project List', xmlid: 'saaskul_switchgear.action_switchgear_project_list'},
        {key: 'tasks_by_client', label: 'Tasks by Customer', xmlid: 'saaskul_switchgear.action_switchgear_tasks_by_client'},
    ]},
    {section: 'Activities', sectionClass: 'o_switchgear_section_activities', items: [
        {key: 'my_activities', label: 'My Activities', xmlid: 'saaskul_switchgear.action_switchgear_activity_my'},
        {key: 'all_activities', label: 'All Activities', xmlid: 'saaskul_switchgear.action_switchgear_activity_all'},
        {key: 'job_tasks', label: 'Job Tasks', xmlid: 'project.action_view_all_task'},
        {key: 'activity_reporting', label: 'Activity Reporting', xmlid: 'saaskul_switchgear.action_switchgear_activity_reporting'},
    ]},
    {section: 'Accounting', sectionClass: 'o_switchgear_section_accounting', items: [
        {key: 'tax_invoice', label: 'Tax Invoice', xmlid: 'account.action_move_out_invoice_type'},
        {key: 'customer_payment', label: 'Customer Payment Receipt', xmlid: 'account.action_account_payments'},
        {key: 'vendor_bill', label: 'Bills Entry', xmlid: 'account.action_move_in_invoice_type'},
        {key: 'vendor_payment', label: 'Vendor Payment', xmlid: 'account.action_account_payments_payable'},
    ]},
    {section: 'Settings', sectionClass: 'o_switchgear_section_settings', items: [
        {
            key: 'configuration',
            label: 'Configuration',
            xmlid: 'saaskul_switchgear.action_switchgear_configuration',
            admin_only: true,
        },
    ]},
];

var XMLID_TO_KEY = {};
var SWITCHGEAR_RES_MODELS = {
    'flowchart.kanban': true,
    'crm.lead': true,
    'switchgear.estimate': true,
    'sale.order': true,
    'mrp.bom': true,
    'mrp.production': true,
    'mrp.workorder': true,
    'stock.picking': true,
    'stock.picking.type': true,
    'stock.warehouse.orderpoint': true,
    'stock.inventory': true,
    'stock.valuation.layer': true,
    'purchase.order': true,
    'account.move': true,
    'account.payment': true,
    'switchgear.design.document': true,
    'switchgear.purchase.requisition': true,
    'switchgear.quality.alert': true,
    'switchgear.quality.team': true,
    'switchgear.quality.check': true,
    'hr.employee': true,
    'hr.employee.public': true,
    'hr.department': true,
    'hr.job': true,
    'hr.payslip': true,
    'hr.payslip.run': true,
    'account.analytic.line': true,
    'product.template': true,
    'switchgear.dashboard': true,
    'switchgear.tutorial.wizard': true,
    'project.project': true,
    'project.task': true,
    'mail.activity': true,
};

_.each(NAV_ITEMS, function (block) {
    _.each(block.items, function (item) {
        if (item.xmlid) {
            XMLID_TO_KEY[item.xmlid] = item.key;
        }
    });
});

function filterNavItems(options) {
    options = options || {};
    var isAdmin = !!options.isSystemAdmin;
    return _.map(NAV_ITEMS, function (block) {
        var items = _.filter(block.items, function (item) {
            return !item.admin_only || isAdmin;
        });
        if (!items.length) {
            return null;
        }
        return _.extend({}, block, {items: items});
    }).filter(Boolean);
}

function renderSidebarHtml(activeKey, options) {
    var html = '<aside class="o_switchgear_app_sidebar">' +
        '<div class="o_switchgear_app_sidebar_title">Switchgear Work</div>' +
        '<ul class="list-group list-group-flush o_switchgear_app_sidebar_nav">';
    _.each(filterNavItems(options), function (block) {
        if (block.section) {
            var sectionCls = block.sectionClass ? (' ' + block.sectionClass) : '';
            html += '<li class="list-group-item o_switchgear_app_sidebar_section' + sectionCls + '">' +
                _.escape(block.section) + '</li>';
        }
        var isMainSection = block.sectionClass === 'o_switchgear_section_home';
        _.each(block.items, function (item) {
            var cls = item.key === activeKey ? ' active' : '';
            var tierCls = isMainSection ? ' o_switchgear_app_sidebar_item_main' : ' o_switchgear_app_sidebar_item_sub';
            html += '<li class="list-group-item' + tierCls + cls + '">' +
                '<a href="#" data-nav-key="' + item.key + '">' + _.escape(item.label) + '</a></li>';
        });
    });
    html += '</ul></aside>';
    return html;
}

function bindSidebarNav($sidebar, doActionFn) {
    $sidebar.find('.o_switchgear_app_sidebar_nav a').off('click').on('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var navKey = $(ev.currentTarget).data('navKey');
        if (!navKey || !doActionFn) {
            return;
        }
        var selectedItem = null;
        _.each(NAV_ITEMS, function (block) {
            _.each(block.items, function (item) {
                if (!selectedItem && item.key === navKey) {
                    selectedItem = item;
                }
            });
        });
        if (selectedItem) {
            return runNavItem(selectedItem, doActionFn);
        }
    });
}

function findNavItemByKey(navKey) {
    var found = null;
    _.each(NAV_ITEMS, function (block) {
        _.each(block.items, function (item) {
            if (!found && item.key === navKey) {
                found = item;
            }
        });
    });
    return found;
}

function activeKeyFromAction(action) {
    if (!action) {
        return 'dashboard';
    }
    if (action.tag === 'switchgear_processing_cycle') {
        return 'processing_cycle';
    }
    if (action.tag === 'switchgear_dashboard' || action.tag === 'switchgear_flowchart') {
        return 'dashboard';
    }
    if (action.xml_id === 'saaskul_switchgear.action_flowchart_kanban' ||
            action.res_model === 'flowchart.kanban') {
        return 'flowchart';
    }
    if (action.xml_id && XMLID_TO_KEY[action.xml_id]) {
        return XMLID_TO_KEY[action.xml_id];
    }
    if (action.res_model === 'switchgear.tutorial.wizard') {
        return 'tutorial';
    }
    if (action.res_model === 'switchgear.estimate') {
        return 'estimation';
    }
    if (action.res_model === 'crm.lead') {
        return 'enquiry';
    }
    if (action.res_model === 'sale.order') {
        return 'quotation';
    }
    if (action.res_model === 'mrp.bom') {
        return 'bom';
    }
    if (action.res_model === 'mrp.production') {
        return 'mrp_order';
    }
    if (action.res_model === 'mrp.workorder') {
        return 'mrp_workorders';
    }
    if (action.res_model === 'purchase.order') {
        return 'lpo_purchase';
    }
    if (action.res_model === 'stock.picking') {
        var domain = action.domain || [];
        var domainStr = JSON.stringify(domain);
        if (domainStr.indexOf('incoming') !== -1) {
            return 'grn';
        }
        if (domainStr.indexOf('outgoing') !== -1) {
            return 'delivery';
        }
        return 'stock_transfers';
    }
    if (action.res_model === 'stock.picking.type') {
        return 'stock_check';
    }
    if (action.res_model === 'account.move') {
        if (action.name && String(action.name).toLowerCase().indexOf('bill') !== -1) {
            return 'vendor_bill';
        }
        return 'tax_invoice';
    }
    if (action.res_model === 'account.payment') {
        return action.name && String(action.name).toLowerCase().indexOf('vendor') !== -1 ?
            'vendor_payment' : 'customer_payment';
    }
    if (action.res_model === 'switchgear.design.document') {
        return 'design';
    }
    if (action.res_model === 'switchgear.quality.check') {
        return 'quality_checks';
    }
    if (action.res_model === 'switchgear.quality.alert') {
        return 'quality_alerts';
    }
    if (action.res_model === 'switchgear.quality.team') {
        return 'quality';
    }
    if (action.res_model === 'hr.employee' || action.res_model === 'hr.employee.public') {
        return 'hr_employees';
    }
    if (action.res_model === 'hr.department') {
        return 'hr_departments';
    }
    if (action.res_model === 'hr.job') {
        return 'hr_jobs';
    }
    if (action.res_model === 'hr.payslip') {
        return 'payroll_payslips';
    }
    if (action.res_model === 'hr.payslip.run') {
        return 'payroll_batches';
    }
    if (action.res_model === 'account.analytic.line') {
        return 'timesheet_mine';
    }
    if (action.res_model === 'product.template') {
        return 'stock_products';
    }
    if (action.res_model === 'stock.warehouse.orderpoint') {
        return 'stock_replenish';
    }
    if (action.res_model === 'stock.inventory') {
        return 'stock_adjustments';
    }
    if (action.res_model === 'mail.activity') {
        if (action.xml_id && XMLID_TO_KEY[action.xml_id]) {
            return XMLID_TO_KEY[action.xml_id];
        }
        return 'all_activities';
    }
    if (action.xml_id === 'saaskul_switchgear.action_switchgear_configuration') {
        return 'configuration';
    }
    return 'dashboard';
}

function isSwitchgearAction(action) {
    if (!action) {
        return false;
    }
    if (action.tag === 'switchgear_dashboard' || action.tag === 'switchgear_flowchart' ||
            action.tag === 'switchgear_processing_cycle') {
        return true;
    }
    if (action.xml_id && XMLID_TO_KEY[action.xml_id]) {
        return true;
    }
    if (action.res_model && SWITCHGEAR_RES_MODELS[action.res_model]) {
        return true;
    }
    return false;
}

function stackHasSwitchgear(actionManager) {
    return _.some(actionManager.controllerStack || [], function (controller) {
        return controller && controller.action && isSwitchgearAction(controller.action);
    });
}

function isSwitchgearPrimaryMenu() {
    try {
        var brand = ($('.o_main_navbar .o_menu_brand').text() || '').trim().toLowerCase();
        if (brand.indexOf('switchgear') !== -1) {
            return true;
        }
        var sections = ($('.o_main_navbar .o_menu_sections').text() || '');
        if (sections.indexOf('Tutorial Wizard') !== -1 ||
                sections.indexOf('Saaskul Switchgear') !== -1) {
            return true;
        }
    } catch (e) {
        // ignore
    }
    return false;
}

function shouldUseSwitchgearShell(actionManager, action) {
    if (action && action.res_model === 'res.config.settings') {
        return false;
    }
    // Follow Switchgear app/actions even when Settings UI mode is default_odoo
    // (login often leaves app_web_ui_mode unset / default_odoo).
    return isSwitchgearAction(action) ||
        stackHasSwitchgear(actionManager) ||
        isSwitchgearPrimaryMenu();
}

function runNavItem(item, doActionFn) {
    if (!item) {
        return $.when();
    }
    if (item.special === 'open_app_menu') {
        return AppShell.openMainMenu();
    }
    if (item.xmlid && doActionFn) {
        return doActionFn(item);
    }
    return $.when();
}

var AppShell = {
    SHELL_CLASS: SHELL_CLASS,
    MAIN_MENU_CLASS: MAIN_MENU_CLASS,
    NAV_ITEMS: NAV_ITEMS,

    activate: function () {
        $('body').addClass(SHELL_CLASS);
        // Top app submenu + Icon View stay off — left sidebar is the only nav.
        $('body').removeClass(MAIN_MENU_CLASS);
        $('.o_main_navbar .o_menu_sections').hide();
        $('.o_cpabooks_icon_view_btn').hide();
    },

    showMainMenuBar: function () {
        // Kept for callers; Switchgear uses left sidebar only (no top tabs).
        $('body').removeClass(MAIN_MENU_CLASS);
        $('.o_main_navbar .o_menu_sections').hide();
        $('.o_cpabooks_icon_view_btn').hide();
    },

    hideMainMenuBar: function () {
        $('body').removeClass(MAIN_MENU_CLASS);
        $('.o_main_navbar .o_menu_sections').hide();
        $('.o_cpabooks_icon_view_btn').hide();
    },

    openMainMenu: function () {
        var $toggle = $('nav.o_main_navbar > a.o_menu_toggle, .o_main_navbar .o_menu_toggle').first();
        if ($toggle.length) {
            $toggle.trigger('click');
        }
        return $.when();
    },

    deactivate: function () {
        $('body').removeClass(SHELL_CLASS).removeClass(MAIN_MENU_CLASS);
        $('.o_main_navbar .o_menu_sections').show();
        $('.o_cpabooks_icon_view_btn').show();
        $('.o_switchgear_app_layout').each(function () {
            var $layout = $(this);
            var $content = $layout.closest('.o_content');
            if ($content.length) {
                $layout.find('.o_switchgear_app_content').children().appendTo($content);
                $layout.remove();
            }
        });
    },

    isSwitchgearAction: isSwitchgearAction,
    activeKeyFromAction: activeKeyFromAction,
    findNavItemByKey: findNavItemByKey,

    setSidebarActive: function ($root, activeKey) {
        if (!$root || !$root.length) {
            return;
        }
        $root.find('.o_switchgear_app_sidebar_nav .list-group-item').removeClass('active');
        $root.find('.o_switchgear_app_sidebar_nav a[data-nav-key="' + activeKey + '"]')
            .closest('.list-group-item').addClass('active');
    },

    mountSidebar: function ($host, activeKey, doActionFn, options) {
        if (!$host || !$host.length) {
            return $();
        }
        options = options || {};
        var $existing = $host.children('.o_switchgear_app_sidebar').first();
        if ($existing.length) {
            // Keep DOM stable during form/list entry — only refresh active state + binds.
            this.setSidebarActive($host, activeKey);
            bindSidebarNav($existing, doActionFn);
            return $existing;
        }
        $host.prepend($(renderSidebarHtml(activeKey, options)));
        var $sidebar = $host.children('.o_switchgear_app_sidebar').first();
        bindSidebarNav($sidebar, doActionFn);
        return $sidebar;
    },

    wrapActionContent: function ($content, activeKey, doActionFn, options) {
        if (!$content || !$content.length) {
            return $();
        }
        options = options || {};
        var $layout = $content.children('.o_switchgear_app_layout').first();
        if (!$layout.length) {
            // Avoid wrapping twice if children already include a layout (race / re-entry).
            var $nested = $content.find('> .o_switchgear_app_layout').first();
            if ($nested.length) {
                $layout = $nested;
            }
        }
        if (!$layout.length) {
            $layout = $('<div class="o_switchgear_app_layout"/>');
            var $sidebarHost = $('<div class="o_switchgear_sidebar_host"/>');
            var $main = $('<div class="o_switchgear_app_content"/>');
            $main.append($content.contents());
            $layout.append($sidebarHost).append($main);
            $content.append($layout);
        }
        this.mountSidebar($layout.children('.o_switchgear_sidebar_host').first(), activeKey, doActionFn, options);
        // Mark form/list screens so CSS can drop double padding that shifts layout.
        var $mainPane = $layout.find('.o_switchgear_app_content').first();
        var hasNativeView = $mainPane.children(
            '.o_view_controller, .o_form_view, .o_list_view, .o_kanban_view, .o_control_panel'
        ).length > 0 || $mainPane.find('> .o_content > .o_view_controller').length > 0;
        // Odoo 14 often nests controller under .o_content inside action content.
        if (!$mainPane.children('.o_form_view, .o_list_view, .o_kanban_view, .o_view_controller').length) {
            hasNativeView = $mainPane.find('.o_form_view, .o_list_view, .o_kanban_view').length > 0;
        }
        $mainPane.toggleClass('o_switchgear_app_content_native', !!hasNativeView);
        return $mainPane;
    },

    getSidebarOptions: function () {
        var session = require('web.session');
        return session.user_has_group('base.group_system').then(function (isSystemAdmin) {
            return {isSystemAdmin: !!isSystemAdmin};
        }).guardedCatch(function () {
            return {isSystemAdmin: false};
        });
    },

    isDefaultOdooMode: function () {
        var session = require('web.session');
        return session.app_web_ui_mode === 'default_odoo';
    },

    isSwitchgearSidebarMode: function () {
        // Legacy name: shell follows Switchgear app/actions, not only ICP mode.
        return true;
    },

    isNativeBackendScreen: function (action) {
        return action && action.res_model === 'res.config.settings';
    },

    shouldUseShell: shouldUseSwitchgearShell,

    syncActionManager: function (actionManager, action) {
        if (!actionManager) {
            return;
        }
        var self = this;
        if (!shouldUseSwitchgearShell(actionManager, action)) {
            this.deactivate();
            return;
        }
        this.activate();
        this.hideMainMenuBar();
        // Client actions (dashboard / processing cycle) mount their own layout.
        if (action && (action.tag === 'switchgear_dashboard' || action.tag === 'switchgear_flowchart' ||
                action.tag === 'switchgear_processing_cycle')) {
            return;
        }
        var activeKey = activeKeyFromAction(action);
        var $action = $('.o_action_manager .o_action').filter(':visible').last();
        var $content = $action.children('.o_content').first();
        if (!$content.length) {
            $content = $action.find('.o_content').first();
        }
        if (!$content.length) {
            return;
        }
        var doActionFn = function (item) {
            if (item.special === 'open_app_menu') {
                return AppShell.openMainMenu();
            }
            if (item.xmlid) {
                return actionManager.do_action(item.xmlid);
            }
            return $.when();
        };
        this.getSidebarOptions().then(function (options) {
            self.wrapActionContent($content, activeKey, doActionFn, options);
            self.setSidebarActive($content, activeKey);
        });
    },
};

ActionManager.include({
    _handleAction: function (action, options) {
        var self = this;
        return this._super(action, options).then(function () {
            AppShell.syncActionManager(self, action);
        });
    },
});

// Leaving Switchgear: remove shell classes so Settings tabs do not stick on the apps home screen.
core.bus.on('show_home_menu', null, function () {
    AppShell.deactivate();
});
core.bus.on('will_show_home_menu', null, function () {
    AppShell.deactivate();
});

return AppShell;
});
