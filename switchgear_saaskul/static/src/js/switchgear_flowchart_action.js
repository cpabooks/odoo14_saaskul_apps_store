odoo.define('switchgear_saaskul.switchgear_flowchart_action', function (require) {
'use strict';

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');
var AppShell = require('switchgear_saaskul.switchgear_app_shell');

var _t = core._t;

var SwitchgearFlowchartAction = AbstractAction.extend({
    contentTemplate: 'SwitchgearFlowchartHome',
    hasSidebar: true,

    events: {
        'click .o_switchgear_home_card': '_onHomeCardClick',
    },

    init: function (parent, action) {
        this._super(parent, action);
        this.activeNavKey = 'overview';
    },

    start: function () {
        this.set('title', _t('Switchgear Work'));
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
        return this._super.apply(this, arguments);
    },

    _doNavItem: function (item) {
        if (!item) {
            return $.when();
        }
        if (item.xmlid) {
            return this.do_action(item.xmlid);
        }
        return $.when();
    },

    _mountShell: function () {
        var self = this;
        var $root = this.$('.o_switchgear_flowchart_root');
        if (!$root.length) {
            $root = this.$el;
        }
        var $content = this.$('.o_content');
        if (!$content.length) {
            $content = this.$el;
        }
        var $layout = $('<div class="o_switchgear_app_layout"/>');
        var $sidebarHost = $('<div class="o_switchgear_sidebar_host"/>');
        var $main = $('<div class="o_switchgear_app_content"/>');
        $main.append($root);
        $layout.append($sidebarHost).append($main);
        $content.empty().append($layout);
        AppShell.mountSidebar($sidebarHost, this.activeNavKey, function (item) {
            return self._doNavItem(item);
        }, this._sidebarOptions || {});
    },

    _onHomeCardClick: function (ev) {
        ev.preventDefault();
        var navKey = $(ev.currentTarget).data('navKey');
        var item = AppShell.findNavItemByKey(navKey);
        if (item) {
            this._doNavItem(item);
        }
    },
});

core.action_registry.add('switchgear_flowchart', SwitchgearFlowchartAction);

return SwitchgearFlowchartAction;
});
