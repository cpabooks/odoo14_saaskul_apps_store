odoo.define('switchgear_saaskul.switchgear_dashboard_action', function (require) {
'use strict';

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');
var rpc = require('web.rpc');
var AppShell = require('switchgear_saaskul.switchgear_app_shell');

var _t = core._t;

var SwitchgearDashboardAction = AbstractAction.extend({
    contentTemplate: 'SwitchgearDashboard',
    xmlDependencies: ['/switchgear_saaskul/static/src/xml/switchgear_dashboard.xml'],

    events: {
        'click .o_sg_dash_kpi': '_onKpiClick',
        'click .o_sg_dash_row': '_onRowClick',
        'click .o_sg_open_main_menu': '_onOpenMainMenu',
    },

    init: function (parent, action) {
        this._super(parent, action);
        this.data = {};
        this.activeNavKey = 'dashboard';
    },

    start: function () {
        this.set('title', _t('Switchgear Dashboard'));
        AppShell.activate();
        AppShell.hideMainMenuBar();
        var self = this;
        return this._super.apply(this, arguments).then(function () {
            return AppShell.getSidebarOptions().then(function (options) {
                self._sidebarOptions = options;
                return self._loadData().then(self._mountShell.bind(self));
            });
        });
    },

    destroy: function () {
        // Do not deactivate here — navigating to CRM/SO forms would unwrap the
        // shell mid-transition and make the design flash/change. Home-menu bus
        // and syncActionManager handle leave-Switchgear cleanup.
        return this._super.apply(this, arguments);
    },

    _loadData: function () {
        var self = this;
        return rpc.query({
            model: 'switchgear.dashboard',
            method: 'get_dashboard_data',
            args: [],
        }).then(function (data) {
            self.data = data || {};
        }).guardedCatch(function () {
            self.data = {title: _t('Switchgear Dashboard'), kpis: [], workflow: []};
        });
    },

    _doActionXmlid: function (xmlid) {
        if (!xmlid) {
            return $.when();
        }
        return this.do_action(xmlid);
    },

    _mountShell: function () {
        var self = this;
        this._renderDashboard();
        var $root = this.$('.o_switchgear_dashboard_root');
        var $content = this.$('.o_content');
        if (!$content.length) {
            $content = this.$el;
        }
        var $layout = $('<div class="o_switchgear_app_layout"/>');
        var $sidebarHost = $('<div class="o_switchgear_sidebar_host"/>');
        var $main = $('<div class="o_switchgear_app_content o_switchgear_dashboard_main"/>');
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
    },

    _onOpenMainMenu: function (ev) {
        ev.preventDefault();
        AppShell.openMainMenu();
    },

    _renderDashboard: function () {
        var d = this.data;
        this.$('.o_sg_dash_title').text(d.title || _t('Switchgear Dashboard'));
        this.$('.o_sg_dash_subtitle').text(d.subtitle || '');

        var $kpis = this.$('.o_sg_dash_kpis').empty();
        _.each(d.kpis || [], function (kpi) {
            $kpis.append(
                $('<a href="#" class="o_sg_dash_kpi"/>')
                    .attr('data-xmlid', kpi.action_xmlid || '')
                    .append(
                        $('<div class="o_sg_dash_kpi_icon"><i class="fa ' + (kpi.icon || 'fa-circle') + '"/></div>'),
                        $('<div class="o_sg_dash_kpi_value"/>').text(kpi.value),
                        $('<div class="o_sg_dash_kpi_label"/>').text(kpi.label)
                    )
            );
        });

        var $workflow = this.$('.o_sg_dash_workflow').empty();
        _.each(d.workflow || [], function (section) {
            var theme = section.theme || 'customer';
            var $sec = $('<div class="o_sg_dash_section"/>').addClass('o_sg_theme_' + theme);
            $sec.append($('<h3 class="o_sg_dash_section_title"/>').text(section.title));
            var $list = $('<div class="o_sg_dash_section_list"/>');
            _.each(section.items || [], function (item) {
                $list.append(
                    $('<a href="#" class="o_sg_dash_row"/>')
                        .attr('data-xmlid', item.action_xmlid || '')
                        .addClass('o_sg_status_' + (item.status || 'pending'))
                        .append(
                            $('<span class="o_sg_dash_row_label"/>').text(item.label),
                            $('<span class="o_sg_dash_row_badge"/>').text(item.count)
                        )
                );
            });
            $sec.append($list);
            $workflow.append($sec);
        });
    },

    _onKpiClick: function (ev) {
        ev.preventDefault();
        this._doActionXmlid($(ev.currentTarget).data('xmlid'));
    },

    _onRowClick: function (ev) {
        ev.preventDefault();
        this._doActionXmlid($(ev.currentTarget).data('xmlid'));
    },
});

core.action_registry.add('switchgear_dashboard', SwitchgearDashboardAction);
core.action_registry.add('switchgear_flowchart', SwitchgearDashboardAction);

return SwitchgearDashboardAction;
});
