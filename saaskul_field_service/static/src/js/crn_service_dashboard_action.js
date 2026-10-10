odoo.define('saaskul_field_service.crn_service_dashboard_action', function (require) {
'use strict';

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');
var rpc = require('web.rpc');
var AppShell = require('saaskul_field_service.crn_app_shell');

var _t = core._t;

var CrnServiceDashboardAction = AbstractAction.extend({
    contentTemplate: 'CrnServiceDashboard',
    xmlDependencies: ['/saaskul_field_service/static/src/xml/crn_service_dashboard.xml'],

    events: {
        'click .o_crn_dash_kpi': '_onKpiClick',
        'click .o_crn_dash_row': '_onRowClick',
        'click .o_crn_open_main_menu': '_onOpenMainMenu',
    },

    init: function (parent, action) {
        this._super(parent, action);
        this.data = {};
        this.activeNavKey = 'dashboard';
    },

    start: function () {
        this.set('title', _t('Complaint Registration Management'));
        AppShell.activate();
        AppShell.hideMainMenuBar();
        var self = this;
        return this._super.apply(this, arguments).then(function () {
            self._showLoadingState();
            return AppShell.getSidebarOptions().then(function (options) {
                self._sidebarOptions = options;
                return self._loadData().then(self._mountShell.bind(self));
            });
        });
    },

    _showLoadingState: function () {
        this.$('.o_crn_dash_title').text(_t('Complaint Registration Management'));
        this.$('.o_crn_dash_subtitle').text(_t('Loading dashboard...'));
        this.$('.o_crn_dash_kpis').html(
            '<div class="col-12 text-center text-muted py-5">' +
            '<i class="fa fa-spinner fa-spin fa-2x"/>' +
            '</div>'
        );
        this.$('.o_crn_dash_workflow').empty();
    },

    destroy: function () {
        AppShell.deactivate();
        return this._super.apply(this, arguments);
    },

    _loadData: function () {
        var self = this;
        return rpc.query({
            model: 'crn.service.dashboard',
            method: 'get_dashboard_data',
            args: [],
        }).then(function (data) {
            self.data = data || {};
        }).guardedCatch(function () {
            self.data = {
                title: _t('Complaint Registration Management'),
                kpis: [],
                workflow: [],
            };
        });
    },

    _doActionXmlid: function (xmlid, domain, title) {
        domain = domain || [];
        if (!xmlid) {
            return $.when();
        }
        var templates = this.data.action_templates || {};
        var action = templates[xmlid];
        var listOptions = _.extend({}, AppShell.listFirstOptions(), {
            on_reverse_breadcrumb: this._onReturnToDashboard.bind(this),
        });
        if (!action) {
            return this.do_action(xmlid, listOptions);
        }
        action = JSON.parse(JSON.stringify(action));
        delete action.res_id;
        if (domain.length) {
            action.domain = domain;
        }
        if (title) {
            action.name = title;
        }
        return this.do_action(AppShell.ensureTreeViewFirst(action), listOptions);
    },

    _onReturnToDashboard: function () {
        var self = this;
        return this._loadData().then(function () {
            self._renderDashboard();
        });
    },

    _mountShell: function () {
        var self = this;
        this._renderDashboard();
        var $root = this.$('.o_crn_dashboard_root');
        var $content = this.$('.o_content').first();
        if (!$content.length) {
            $content = this.$el;
        }
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
            $main = $('<div class="o_crn_app_content o_crn_dashboard_main"/>');
            $layout.append($sidebarHost).append($main);
            $content.empty().append($layout);
        }
        $main.addClass('o_crn_dashboard_main');
        if ($root.length && !$main.has($root).length) {
            $main.empty().append($root);
        }
        AppShell.mountSidebar($sidebarHost, this.activeNavKey, function (item) {
            if (item.special === 'open_app_menu') {
                return AppShell.openMainMenu();
            }
            if (item.xmlid) {
                return self.do_action(item.xmlid, AppShell.listFirstOptions());
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
        this.$('.o_crn_dash_title').text(d.title || _t('Complaint Registration Management'));
        this.$('.o_crn_dash_subtitle').text(d.subtitle || '');

        var $kpis = this.$('.o_crn_dash_kpis').empty();
        _.each(d.kpis || [], function (kpi) {
            $kpis.append(
                $('<a href="#" class="o_crn_dash_kpi"/>')
                    .attr('data-xmlid', kpi.action_xmlid || '')
                    .attr('data-domain', JSON.stringify(kpi.domain || []))
                    .append(
                        $('<div class="o_crn_dash_kpi_icon"><i class="fa ' + (kpi.icon || 'fa-circle') + '"/></div>'),
                        $('<div class="o_crn_dash_kpi_value"/>').text(kpi.value),
                        $('<div class="o_crn_dash_kpi_label"/>').text(kpi.label)
                    )
            );
        });

        var $workflow = this.$('.o_crn_dash_workflow').empty();
        _.each(d.workflow || [], function (section) {
            var theme = section.theme || 'intake';
            var $sec = $('<div class="o_crn_dash_section"/>').addClass('o_crn_theme_' + theme);
            $sec.append($('<h3 class="o_crn_dash_section_title"/>').text(section.title));
            var $list = $('<div class="o_crn_dash_section_list"/>');
            _.each(section.items || [], function (item) {
                $list.append(
                    $('<a href="#" class="o_crn_dash_row"/>')
                        .attr('data-xmlid', item.action_xmlid || '')
                        .attr('data-domain', JSON.stringify(item.domain || []))
                        .addClass('o_crn_status_' + (item.status || 'pending'))
                        .append(
                            $('<span class="o_crn_dash_row_label"/>').text(item.label),
                            $('<span class="o_crn_dash_row_badge"/>').text(item.count)
                        )
                );
            });
            $sec.append($list);
            $workflow.append($sec);
        });
    },

    _readDomain: function ($target) {
        try {
            return JSON.parse($target.attr('data-domain') || '[]');
        } catch (err) {
            return [];
        }
    },

    _onKpiClick: function (ev) {
        ev.preventDefault();
        var $target = $(ev.currentTarget);
        this._doActionXmlid(
            $target.attr('data-xmlid'),
            this._readDomain($target),
            $target.find('.o_crn_dash_kpi_label').text()
        );
    },

    _onRowClick: function (ev) {
        ev.preventDefault();
        var $target = $(ev.currentTarget);
        this._doActionXmlid(
            $target.attr('data-xmlid'),
            this._readDomain($target),
            $target.find('.o_crn_dash_row_label').text()
        );
    },
});

core.action_registry.add('crn_service_dashboard', CrnServiceDashboardAction);

return CrnServiceDashboardAction;
});
