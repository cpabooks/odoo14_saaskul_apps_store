odoo.define('saaskul_field_service.crn_app_shell', function (require) {
'use strict';

var ActionManager = require('web.ActionManager');
var core = require('web.core');

var SHELL_CLASS = 'o_crn_app_shell';
var MAIN_MENU_CLASS = 'o_crn_show_main_menu';
var FSM_ROOT_XMLID = 'industry_fsm.fsm_menu_root';

var NAV_ITEMS = [
    {section: 'Home', sectionClass: 'o_crn_section_home', items: [
        {key: 'dashboard', label: 'Dashboard', xmlid: 'saaskul_field_service.action_crn_service_dashboard', tier: 'home'},
        {key: 'processing_cycle', label: 'CRN Processing Cycle', xmlid: 'saaskul_field_service.action_crn_processing_cycle', tier: 'home'},
    ]},
    {section: 'CRNs', sectionClass: 'o_crn_section_crns', items: [
        {key: 'my_crns', label: 'My CRNs', xmlid: 'industry_fsm.project_task_action_fsm'},
        {key: 'all_crns', label: 'All CRNs', xmlid: 'industry_fsm.project_task_action_all_fsm'},
        {key: 'crn_map', label: 'CRN Map', xmlid: 'industry_fsm.project_task_action_fsm_map'},
        {key: 'to_quotation', label: 'To Quotation / Issue', xmlid: 'saaskul_field_service.action_fsm_project_task_to_quotation_issue'},
        {key: 'to_invoice', label: 'To Invoice', xmlid: 'saaskul_field_service.action_fsm_project_task_to_invoice'},
    ]},
    {section: 'Reporting', sectionClass: 'o_crn_section_reporting', items: [
        {key: 'service_dashboard', label: 'Service Charts Dashboard', xmlid: 'saaskul_field_service.action_fsm_service_monitor_dashboard'},
        {key: 'task_analysis', label: 'CRN Analysis', xmlid: 'saaskul_field_service.action_fsm_task_analysis_monitor'},
        {key: 'timesheet_analysis', label: 'Timesheet Analysis', xmlid: 'saaskul_field_service.action_fsm_timesheet_analysis_monitor'},
        {key: 'material_consumption', label: 'Material Consumption Analysis', xmlid: 'saaskul_field_service.action_fsm_material_consumption_analysis'},
    ]},
    {section: 'Store', sectionClass: 'o_crn_section_store', items: [
        {key: 'stock_issue', label: 'Material Issue Note', xmlid: 'saaskul_field_service.issue_action'},
        {key: 'stock_return', label: 'Material Return Note', xmlid: 'saaskul_field_service.return_issue_action'},
        {key: 'mat_request', label: 'Material Request Pending', xmlid: 'saaskul_field_service.action_fsm_store_material_request_pending'},
        {key: 'mat_issued', label: 'Material Issued', xmlid: 'saaskul_field_service.action_fsm_store_material_issued'},
        {key: 'do_pending', label: 'DO Pending', xmlid: 'saaskul_field_service.action_fsm_store_do_pending'},
        {key: 'do_issued', label: 'DO Issued', xmlid: 'saaskul_field_service.action_fsm_store_do_issued'},
    ]},
    {section: 'Timesheets', sectionClass: 'o_crn_section_timesheet', items: [
        {key: 'timesheet_mine', label: 'My Timesheets', xmlid: 'hr_timesheet.act_hr_timesheet_line'},
        {key: 'timesheet_all', label: 'All Timesheets', xmlid: 'hr_timesheet.timesheet_action_all'},
    ]},
    {section: 'Settings', sectionClass: 'o_crn_section_settings', items: [
        {key: 'test_data', label: 'FSM Test Data', xmlid: 'saaskul_field_service.action_fsm_test_data_wizard', admin_only: true},
        {key: 'all_apps', label: 'All Odoo Apps', special: 'open_app_menu'},
    ]},
];

var XMLID_TO_KEY = {};
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
    var html = '<aside class="o_crn_app_sidebar">' +
        '<div class="o_crn_app_sidebar_title">Complaint Registration Management</div>' +
        '<ul class="list-group list-group-flush o_crn_app_sidebar_nav">';
    _.each(filterNavItems(options), function (block) {
        if (block.section) {
            var sectionCls = block.sectionClass ? (' ' + block.sectionClass) : '';
            html += '<li class="list-group-item o_crn_app_sidebar_section' + sectionCls + '">' +
                _.escape(block.section) + '</li>';
        }
        var isMainSection = block.sectionClass === 'o_crn_section_home';
        _.each(block.items, function (item) {
            var cls = item.key === activeKey ? ' active' : '';
            var tierCls = isMainSection ? ' o_crn_app_sidebar_item_main' : ' o_crn_app_sidebar_item_sub';
            html += '<li class="list-group-item' + tierCls + cls + '">' +
                '<a href="#" data-nav-key="' + item.key + '">' + _.escape(item.label) + '</a></li>';
        });
    });
    html += '</ul></aside>';
    return html;
}

function bindSidebarNav($sidebar, doActionFn) {
    $sidebar.find('.o_crn_app_sidebar_nav a').off('click').on('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var navKey = $(ev.currentTarget).data('navKey');
        var selectedItem = null;
        _.each(NAV_ITEMS, function (block) {
            _.each(block.items, function (item) {
                if (!selectedItem && item.key === navKey) {
                    selectedItem = item;
                }
            });
        });
        if (selectedItem) {
            if (selectedItem.special === 'open_app_menu') {
                return AppShell.openMainMenu();
            }
            if (selectedItem.xmlid && doActionFn) {
                return doActionFn(selectedItem);
            }
        }
    });
}

function getActionContext(action) {
    var ctx = action && action.context;
    if (!ctx) {
        return {};
    }
    if (typeof ctx === 'string') {
        if (ctx.indexOf('fsm_mode') !== -1 || ctx.indexOf('default_is_fsm') !== -1 ||
                ctx.indexOf('default_check_fsm') !== -1) {
            return {fsm_mode: true};
        }
        return {};
    }
    return ctx;
}

function activeKeyFromAction(action) {
    if (!action) {
        return 'dashboard';
    }
    if (action.tag === 'crn_processing_cycle') {
        return 'processing_cycle';
    }
    if (action.tag === 'crn_service_dashboard') {
        return 'dashboard';
    }
    if (action.xml_id && XMLID_TO_KEY[action.xml_id]) {
        return XMLID_TO_KEY[action.xml_id];
    }
    if (action.res_model === 'project.task') {
        var name = String(action.name || '').toLowerCase();
        if (name.indexOf('my crn') !== -1) {
            return 'my_crns';
        }
        return 'all_crns';
    }
    if (action.res_model === 'material.request.line') {
        return 'mat_request';
    }
    if (action.res_model === 'stock.picking') {
        var domainStr = JSON.stringify(action.domain || []);
        var actName = String(action.name || '').toLowerCase();
        if (domainStr.indexOf('is_stock_return_note') !== -1 || actName.indexOf('return') !== -1) {
            return 'stock_return';
        }
        if (domainStr.indexOf('is_stock_issue_note') !== -1 || actName.indexOf('issue note') !== -1) {
            return 'stock_issue';
        }
        if (domainStr.indexOf('outgoing') !== -1 || actName.indexOf('do pending') !== -1 || actName.indexOf('do issued') !== -1) {
            if (actName.indexOf('issued') !== -1 || actName.indexOf('done') !== -1) {
                return 'do_issued';
            }
            return 'do_pending';
        }
        return 'mat_issued';
    }
    if (action.res_model === 'account.analytic.line') {
        return 'timesheet_analysis';
    }
    if (action.tag === 'fsm_service_monitor_dashboard') {
        return 'service_dashboard';
    }
    if (action.res_model === 'cpabooks.fsm.test.data.wizard') {
        return 'test_data';
    }
    if (action.res_model === 'fsm.material.consumption.report') {
        return 'material_consumption';
    }
    if (action.name && String(action.name).toLowerCase().indexOf('waiting for approval') !== -1) {
        return 'approval_waiting';
    }
    if (action.name && String(action.name).toLowerCase().indexOf('approved crn') !== -1) {
        return 'approval_approved';
    }
    if (action.name && String(action.name).toLowerCase().indexOf('rejected crn') !== -1) {
        return 'approval_rejected';
    }
    return 'dashboard';
}

/**
 * True for Field Service / CRN screens that should use the left app shell.
 * Does not require global Settings → Menu layout = crm_fsm.
 */
function isFsmShellAction(action) {
    if (!action) {
        return false;
    }
    if (action.tag === 'crn_service_dashboard' || action.tag === 'crn_processing_cycle' ||
            action.tag === 'fsm_service_monitor_dashboard') {
        return true;
    }
    if (action.xml_id && XMLID_TO_KEY[action.xml_id]) {
        return true;
    }
    var ctx = getActionContext(action);
    if (ctx.fsm_mode || ctx.default_is_fsm || ctx.default_check_fsm) {
        return true;
    }
    if (action.res_model === 'material.request.line' ||
            action.res_model === 'crn.service.dashboard' ||
            action.res_model === 'cpabooks.fsm.test.data.wizard' ||
            action.res_model === 'fsm.material.consumption.report') {
        return true;
    }
    if (action.res_model === 'project.task') {
        var name = String(action.name || '').toLowerCase();
        if (name.indexOf('crn') !== -1 || name.indexOf('field service') !== -1) {
            return true;
        }
        var domainStr = JSON.stringify(action.domain || []);
        if (domainStr.indexOf('is_fsm') !== -1 || domainStr.indexOf('check_fsm') !== -1 ||
                domainStr.indexOf('CRN') !== -1) {
            return true;
        }
    }
    if (action.name && String(action.name).toLowerCase().indexOf('waiting for approval') !== -1) {
        return true;
    }
    if (action.name && String(action.name).toLowerCase().indexOf('approved crn') !== -1) {
        return true;
    }
    if (action.name && String(action.name).toLowerCase().indexOf('rejected crn') !== -1) {
        return true;
    }
    return false;
}

function findMenuWidget(actionManager) {
    var widget = actionManager;
    var guard = 0;
    while (widget && guard < 12) {
        if (widget.menu) {
            return widget.menu;
        }
        widget = widget.getParent ? widget.getParent() : null;
        guard += 1;
    }
    return null;
}

function findAppById(nodes, id) {
    var list = nodes || [];
    for (var i = 0; i < list.length; i++) {
        if (list[i].id === id) {
            return list[i];
        }
        var child = findAppById(list[i].children, id);
        if (child) {
            return child;
        }
    }
    return null;
}

function isFieldServicePrimaryMenu(actionManager) {
    try {
        var menu = findMenuWidget(actionManager);
        if (menu && menu.current_primary_menu && menu.menu_data) {
            var apps = menu.menu_data.children || [];
            var app = _.find(apps, function (item) {
                return item.id === menu.current_primary_menu;
            });
            if (app && app.xmlid === FSM_ROOT_XMLID) {
                return true;
            }
            // Secondary: primary id is under FSM root tree
            var fsmRoot = _.find(apps, function (item) {
                return item.xmlid === FSM_ROOT_XMLID;
            });
            if (fsmRoot && findAppById([fsmRoot], menu.current_primary_menu)) {
                return true;
            }
        }
    } catch (e) {
        // ignore
    }
    // DOM fallback while Field Service top menus are still painted
    var sections = ($('.o_main_navbar .o_menu_sections').text() || '');
    if (sections.indexOf('CRN Processing Cycle') !== -1 || sections.indexOf('All CRNs') !== -1) {
        return true;
    }
    return false;
}

function isListViewMode(mode) {
    return mode === 'tree' || mode === 'list';
}

function normalizeViewModeForWeb(mode) {
    return isListViewMode(mode) ? 'list' : mode;
}

function getViewMode(view) {
    if (_.isArray(view)) {
        return view[1];
    }
    return view && view.type;
}

function getViewId(view) {
    if (_.isArray(view)) {
        return view[0] || false;
    }
    return (view && (view.viewID || view.view_id)) || false;
}

function isListFirstCandidate(action) {
    return action && action.type === 'ir.actions.act_window' && action.res_model &&
        !action.res_id && action.target !== 'new';
}

function ensureTreeViewFirst(action) {
    if (!isListFirstCandidate(action)) {
        return action;
    }
    var views = action.views || [];
    if (!views.length && action.view_mode) {
        views = _.map(String(action.view_mode).split(','), function (mode) {
            mode = $.trim(mode);
            return mode ? [false, mode] : null;
        });
        views = _.filter(views, Boolean);
    }
    if (views.length === 1 && getViewMode(views[0]) === 'form') {
        return action;
    }
    var treeViews = _.filter(views, function (view) { return isListViewMode(getViewMode(view)); });
    var formViews = _.filter(views, function (view) { return getViewMode(view) === 'form'; });
    var otherViews = _.filter(views, function (view) {
        return !isListViewMode(getViewMode(view)) && getViewMode(view) !== 'form';
    });
    if (treeViews.length) {
        action.views = treeViews.concat(otherViews).concat(formViews);
    } else {
        action.views = [[false, 'list']].concat(otherViews).concat(
            formViews.length ? formViews : [[false, 'form']]
        );
    }
    action.views = _.map(action.views, function (view) {
        return [getViewId(view), normalizeViewModeForWeb(getViewMode(view))];
    });
    action.view_mode = _.map(action.views, function (view) { return view[1]; }).join(',');
    return action;
}

function listFirstOptions(options) {
    return _.extend({}, options || {}, {viewType: 'list'});
}

function stackHasFsm(actionManager) {
    return _.some(actionManager.controllerStack || [], function (controller) {
        return controller && controller.action && isFsmShellAction(controller.action);
    });
}

var AppShell = {
    SHELL_CLASS: SHELL_CLASS,
    MAIN_MENU_CLASS: MAIN_MENU_CLASS,

    activate: function () {
        $('body').addClass(SHELL_CLASS).removeClass(MAIN_MENU_CLASS);
    },

    showMainMenuBar: function () {
        // Kept for API compat — Field Service always hides top submenu.
        $('body').removeClass(MAIN_MENU_CLASS);
    },

    hideMainMenuBar: function () {
        $('body').removeClass(MAIN_MENU_CLASS);
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
        $('.o_crn_app_layout').each(function () {
            var $layout = $(this);
            var $content = $layout.closest('.o_content');
            if ($content.length) {
                $layout.find('.o_crn_app_content').children().appendTo($content);
                $layout.remove();
            }
        });
    },

    /**
     * Legacy name kept for callers. Shell now follows Field Service app/actions,
     * not only Settings app_web_ui_mode=crm_fsm.
     */
    isCrmSidebarMode: function () {
        return true;
    },

    isNativeBackendScreen: function (action) {
        return action && action.res_model === 'res.config.settings';
    },

    shouldUseShell: function (actionManager, action) {
        if (this.isNativeBackendScreen(action)) {
            return false;
        }
        return isFsmShellAction(action) ||
            stackHasFsm(actionManager) ||
            isFieldServicePrimaryMenu(actionManager);
    },

    ensureTreeViewFirst: ensureTreeViewFirst,

    listFirstOptions: listFirstOptions,

    mountSidebar: function ($host, activeKey, doActionFn, options) {
        if (!$host || !$host.length) {
            return $();
        }
        options = options || {};
        var $existing = $host.children('.o_crn_app_sidebar');
        if ($existing.length) {
            $existing.replaceWith($(renderSidebarHtml(activeKey, options)));
        } else {
            $host.prepend($(renderSidebarHtml(activeKey, options)));
        }
        var $sidebar = $host.children('.o_crn_app_sidebar').first();
        bindSidebarNav($sidebar, doActionFn);
        return $sidebar;
    },

    wrapActionContent: function ($content, activeKey, doActionFn, options) {
        if (!$content || !$content.length) {
            return $();
        }
        options = options || {};
        var $layout = $content.children('.o_crn_app_layout').first();
        if (!$layout.length) {
            $layout = $('<div class="o_crn_app_layout"/>');
            var $sidebarHost = $('<div class="o_crn_sidebar_host"/>');
            var $main = $('<div class="o_crn_app_content"/>');
            $main.append($content.contents());
            $layout.append($sidebarHost).append($main);
            $content.empty().append($layout);
        }
        this.mountSidebar($layout.children('.o_crn_sidebar_host').first(), activeKey, doActionFn, options);
        return $layout.find('.o_crn_app_content').first();
    },

    getSidebarOptions: function () {
        return require('web.session').user_has_group('base.group_system').then(function (isSystemAdmin) {
            return {isSystemAdmin: !!isSystemAdmin};
        }).guardedCatch(function () {
            return {isSystemAdmin: false};
        });
    },

    syncActionManager: function (actionManager, action) {
        if (!actionManager) {
            return;
        }
        var self = this;
        if (!this.shouldUseShell(actionManager, action)) {
            this.deactivate();
            return;
        }
        this.activate();
        this.hideMainMenuBar();
        // Dashboard / processing-cycle client actions mount their own left sidebar.
        if (action && (action.tag === 'crn_service_dashboard' || action.tag === 'crn_processing_cycle')) {
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
            if (item.xmlid) {
                return actionManager.do_action(item.xmlid, AppShell.listFirstOptions());
            }
            return $.when();
        };
        this.getSidebarOptions().then(function (options) {
            self.wrapActionContent($content, activeKey, doActionFn, options);
            var $sidebar = $content.find('.o_crn_app_sidebar').first();
            if ($sidebar.length) {
                $sidebar.scrollTop(0);
            }
            $content.find('.o_crn_app_sidebar_nav .list-group-item').removeClass('active');
            $content.find('.o_crn_app_sidebar_nav a[data-nav-key="' + activeKey + '"]')
                .closest('.list-group-item').addClass('active');
        });
    },
};

var _lastActionManager = null;

ActionManager.include({
    _handleAction: function (action, options) {
        var self = this;
        _lastActionManager = this;
        var forceListFirst = isListFirstCandidate(action) &&
            (isFsmShellAction(action) || stackHasFsm(this));
        if (forceListFirst) {
            action = AppShell.ensureTreeViewFirst(action);
            options = AppShell.listFirstOptions(options);
        }
        return this._super(action, options).then(function () {
            AppShell.syncActionManager(self, action);
        });
    },

    _pushController: function (controller) {
        var self = this;
        _lastActionManager = this;
        var result = this._super.apply(this, arguments);
        var action = controller && controller.action;
        // Re-wrap after list↔form switches that rebuild .o_content.
        window.setTimeout(function () {
            AppShell.syncActionManager(self, action);
        }, 0);
        return result;
    },
});

core.bus.on('show_home_menu', null, function () {
    AppShell.deactivate();
});
core.bus.on('will_show_home_menu', null, function () {
    AppShell.deactivate();
});
core.bus.on('change_menu_section', null, function () {
    // When switching into Field Service primary menu, keep shell ready.
    window.setTimeout(function () {
        var am = _lastActionManager;
        if (!am) {
            return;
        }
        var controller = am.getCurrentController && am.getCurrentController();
        if (!controller && am.controllers && am.controllerStack && am.controllerStack.length) {
            controller = am.controllers[am.controllerStack[am.controllerStack.length - 1]];
        }
        var action = controller && controller.action;
        AppShell.syncActionManager(am, action);
    }, 50);
});

return AppShell;
});
