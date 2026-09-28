odoo.define("cpabooks_faff.dashboard", function (require) {
    "use strict";

    var AbstractAction = require("web.AbstractAction");
    var core = require("web.core");
    var rpc = require("web.rpc");

    var _t = core._t;

    var FaffDashboardAction = AbstractAction.extend({
        contentTemplate: "FaffDashboard",
        xmlDependencies: ["/cpabooks_faff/static/src/xml/faff_dashboard.xml"],

        events: {
            "click .o_faff_dash_kpi": "_onKpiClick",
            "click .o_faff_dash_row": "_onRowClick",
        },

        init: function (parent, action) {
            this._super(parent, action);
            this.data = {};
        },

        start: function () {
            var self = this;
            this.set("title", _t("FAFF Dashboard"));
            try {
                require("cpabooks_faff.shell").requestSyncSidebar(true);
            } catch (e) { /* ignore */ }
            return this._super.apply(this, arguments).then(function () {
                return self._loadData().then(function () {
                    self._renderDashboard();
                });
            });
        },

        _loadData: function () {
            var self = this;
            return rpc
                .query({
                    model: "cpabooks.faff.dashboard",
                    method: "get_dashboard_data",
                    args: [],
                })
                .then(function (data) {
                    self.data = data || {};
                })
                .guardedCatch(function () {
                    self.data = { title: _t("FAFF Dashboard"), kpis: [], workflow: [] };
                });
        },

        _renderDashboard: function () {
            var d = this.data;
            this.$(".o_faff_dash_title").text(d.title || _t("FAFF Dashboard"));
            this.$(".o_faff_dash_subtitle").text(d.subtitle || "");

            var $kpis = this.$(".o_faff_dash_kpis").empty();
            _.each(d.kpis || [], function (kpi) {
                $kpis.append(
                    $('<a href="#" class="o_faff_dash_kpi"/>')
                        .attr("data-xmlid", kpi.action_xmlid || "")
                        .append(
                            $(
                                '<div class="o_faff_dash_kpi_icon"><i class="fa ' +
                                    (kpi.icon || "fa-circle") +
                                    '"/></div>'
                            ),
                            $('<div class="o_faff_dash_kpi_value"/>').text(kpi.value),
                            $('<div class="o_faff_dash_kpi_label"/>').text(kpi.label)
                        )
                );
            });

            var $workflow = this.$(".o_faff_dash_workflow").empty();
            _.each(d.workflow || [], function (section) {
                var theme = section.theme || "customer";
                var $sec = $('<div class="o_faff_dash_section"/>').addClass(
                    "o_faff_theme_" + theme
                );
                $sec.append(
                    $('<h3 class="o_faff_dash_section_title"/>').text(section.title)
                );
                var $list = $('<div class="o_faff_dash_section_list"/>');
                _.each(section.items || [], function (item) {
                    $list.append(
                        $('<a href="#" class="o_faff_dash_row"/>')
                            .attr("data-xmlid", item.action_xmlid || "")
                            .addClass("o_faff_status_" + (item.status || "pending"))
                            .append(
                                $('<span class="o_faff_dash_row_label"/>').text(item.label),
                                $('<span class="o_faff_dash_row_badge"/>').text(item.count)
                            )
                    );
                });
                $sec.append($list);
                $workflow.append($sec);
            });
        },

        _doActionXmlid: function (xmlid) {
            if (!xmlid) {
                return $.when();
            }
            return this.do_action(xmlid);
        },

        _onKpiClick: function (ev) {
            ev.preventDefault();
            this._doActionXmlid($(ev.currentTarget).data("xmlid"));
        },

        _onRowClick: function (ev) {
            ev.preventDefault();
            this._doActionXmlid($(ev.currentTarget).data("xmlid"));
        },
    });

    core.action_registry.add("faff_dashboard", FaffDashboardAction);
    return FaffDashboardAction;
});
