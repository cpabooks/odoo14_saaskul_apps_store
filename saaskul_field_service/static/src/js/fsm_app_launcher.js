odoo.define('saaskul_field_service.fsm_app_launcher', function (require) {
'use strict';

var FSM_ROOT_XMLID = 'industry_fsm.fsm_menu_root';
var FSM_DASHBOARD_ACTION_XMLID = 'saaskul_field_service.action_crn_service_dashboard';
var AppShell = require('saaskul_field_service.crn_app_shell');

var HomeMenu;
var WebClient;

try {
    HomeMenu = require('web_enterprise.HomeMenu');
    WebClient = require('web.WebClient');
} catch (error) {
    return;
}

function _isFsmRootApp(menu) {
    return !!(menu && menu.xmlid === FSM_ROOT_XMLID);
}

function _fsmDashboardActionId(menu) {
    if (menu && menu.action) {
        return menu.action;
    }
    return FSM_DASHBOARD_ACTION_XMLID;
}

if (HomeMenu && HomeMenu.prototype._openMenu) {
    var _origOpenMenu = HomeMenu.prototype._openMenu;
    HomeMenu.prototype._openMenu = function (params) {
        var menu = params && params.menu;
        var isApp = params && params.isApp;
        if (isApp && _isFsmRootApp(menu) && !menu.action) {
            params = _.extend({}, params, {
                menu: _.extend({}, menu, {action: FSM_DASHBOARD_ACTION_XMLID}),
            });
        }
        if (isApp && _isFsmRootApp(menu)) {
            // Entering Field Service: prepare left shell before action paints.
            AppShell.activate();
        }
        return _origOpenMenu.call(this, params);
    };
}

if (WebClient && WebClient.prototype.on_app_clicked) {
    var _origOnAppClicked = WebClient.prototype.on_app_clicked;
    WebClient.prototype.on_app_clicked = async function (ev) {
        if (ev && ev.detail && !ev.detail.action_id && ev.detail.menu_id) {
            var homeMenu = this.homeMenuManager && this.homeMenuManager.homeMenu;
            var apps = homeMenu && (homeMenu.availableApps || homeMenu.props.apps || []);
            var app = _.find(apps, function (item) {
                return item.id === ev.detail.menu_id;
            });
            if (_isFsmRootApp(app)) {
                ev.detail.action_id = _fsmDashboardActionId(app);
                AppShell.activate();
            }
        } else if (ev && ev.detail && ev.detail.menu_id) {
            var homeMenu2 = this.homeMenuManager && this.homeMenuManager.homeMenu;
            var apps2 = homeMenu2 && (homeMenu2.availableApps || homeMenu2.props.apps || []);
            var app2 = _.find(apps2, function (item) {
                return item.id === ev.detail.menu_id;
            });
            if (_isFsmRootApp(app2)) {
                AppShell.activate();
            }
        }
        return _origOnAppClicked.apply(this, arguments);
    };
}

});
