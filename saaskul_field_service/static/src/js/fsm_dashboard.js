odoo.define("saaskul_field_service.FsmServiceDashboard", function (require) {
    "use strict";

    var AbstractAction = require("web.AbstractAction");
    var core = require("web.core");

    var FsmServiceDashboard = AbstractAction.extend({
        contentTemplate: "FsmServiceDashboard",
        xmlDependencies: ["/saaskul_field_service/static/src/xml/fsm_dashboard.xml"],
        events: {
            "click .fsd_apply_filters": "_onApplyFilters",
            "click .fsd_reset_filters": "_onResetFilters",
            "click .fsd_kpi_card": "_onKpiClick",
            "click .fsd_spotlight_card": "_onSpotlightClick",
        },

        init: function (parent, action) {
            this._super(parent, action);
            this.dashboardData = null;
            this.filters = {};
            this.charts = {};
        },

        start: function () {
            this.set("title", "Service Dashboard");
            return this._super.apply(this, arguments).then(this._loadDashboardData.bind(this));
        },

        _loadDashboardData: function (filters) {
            var self = this;
            return this._rpc({
                model: "project.task",
                method: "get_fsm_dashboard_data",
                args: [filters || {}],
            }).then(function (result) {
                self.dashboardData = result;
                self.filters = Object.assign({}, result.filters || {});
                self._renderDashboard();
            });
        },

        _renderDashboard: function () {
            if (!this.dashboardData) {
                return;
            }
            this._renderFilters();
            this._renderKpis();
            this._renderStageChart();
            this._renderComplaintChart();
            this._renderTrendChart();
            this._renderTeamChart();
            this._renderSpotlights();
        },

        _renderFilters: function () {
            var companies = this.dashboardData.companies || [];
            var $company = this.$("#fsd_company");
            $company.empty();
            companies.forEach(function (company) {
                $company.append($("<option>", {
                    value: company.id,
                    text: company.name,
                }));
            });
            this.$("#fsd_period").val(this.filters.period || "90");
            this.$("#fsd_company").val(this.filters.company_id || "0");
        },

        _renderKpis: function () {
            var self = this;
            var cardsHtml = (this.dashboardData.kpis || []).map(function (card) {
                return [
                    "<article class='fsd_kpi_card fsd_tone_", self._escape(card.tone || "sand"),
                    "' data-action-type='", self._escape(card.action_type || "task"),
                    "' data-domain='", self._escape(JSON.stringify(card.domain || [])),
                    "'>",
                    "<div class='fsd_kpi_label'>", self._escape(card.label), "</div>",
                    "<div class='fsd_kpi_value'>", self._escape(self._formatValue(card.value, card.is_monetary)), "</div>",
                    "<div class='fsd_kpi_subtitle'>", self._escape(card.subtitle || ""), "</div>",
                    "</article>",
                ].join("");
            }).join("");
            this.$("#fsd_kpi_grid").html(cardsHtml);
        },

        _renderStageChart: function () {
            var self = this;
            var rows = this.dashboardData.stage_chart || [];
            this._renderChart("stage_chart", "#fsd_stage_chart", {
                type: "bar",
                data: {
                    labels: rows.map(function (row) { return row.label; }),
                    datasets: [{
                        data: rows.map(function (row) { return row.value; }),
                        backgroundColor: ["#ca6a3b", "#d8a75f", "#2f7a72", "#3f556b", "#93a67f", "#b85c5c", "#8b6f47"],
                        borderRadius: 8,
                    }],
                },
                options: this._getBarOptions(),
            }, function (index) {
                self._openDashboardAction("task", rows[index].domain, rows[index].label);
            });
        },

        _renderComplaintChart: function () {
            var self = this;
            var rows = this.dashboardData.complaint_chart || [];
            this._renderChart("complaint_chart", "#fsd_complaint_chart", {
                type: "pie",
                data: {
                    labels: rows.map(function (row) { return row.label; }),
                    datasets: [{
                        data: rows.map(function (row) { return row.value; }),
                        backgroundColor: ["#2f7a72", "#ca6a3b", "#d8a75f", "#3f556b", "#93a67f"],
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    legend: {position: "bottom"},
                },
            }, function (index) {
                self._openDashboardAction("task", rows[index].domain, rows[index].label);
            });
        },

        _renderTrendChart: function () {
            var self = this;
            var trend = this.dashboardData.trend_chart || {labels: [], created: [], closed: []};
            this._renderChart("trend_chart", "#fsd_trend_chart", {
                type: "line",
                data: {
                    labels: trend.labels,
                    datasets: [{
                        label: "Created",
                        data: trend.created,
                        borderColor: "#ca6a3b",
                        backgroundColor: "rgba(202, 106, 59, 0.16)",
                        fill: true,
                        tension: 0.35,
                    }, {
                        label: "Closed",
                        data: trend.closed,
                        borderColor: "#2f7a72",
                        backgroundColor: "rgba(47, 122, 114, 0.10)",
                        fill: true,
                        tension: 0.35,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    legend: {position: "bottom"},
                    scales: {
                        yAxes: [{ticks: {beginAtZero: true}}],
                    },
                },
            }, function (index, item) {
                var datasetIndex = item && item._datasetIndex ? item._datasetIndex : 0;
                var bucket = (trend.domains || [])[index] || {};
                if (datasetIndex === 1) {
                    self._openDashboardAction("task", bucket.closed || [], "Closed - " + (trend.labels[index] || ""));
                } else {
                    self._openDashboardAction("task", bucket.created || [], "Created - " + (trend.labels[index] || ""));
                }
            });
        },

        _renderTeamChart: function () {
            var self = this;
            var rows = this.dashboardData.team_chart || [];
            this._renderChart("team_chart", "#fsd_team_chart", {
                type: "horizontalBar",
                data: {
                    labels: rows.map(function (row) { return row.label; }),
                    datasets: [{
                        label: "Timesheet Cost",
                        data: rows.map(function (row) { return row.value; }),
                        backgroundColor: "#3f556b",
                        borderRadius: 8,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    legend: {display: false},
                    scales: {
                        xAxes: [{ticks: {beginAtZero: true}}],
                    },
                },
            }, function (index) {
                self._openDashboardAction("task", [], rows[index].label);
            });
        },

        _renderSpotlights: function () {
            var self = this;
            var cardsHtml = (this.dashboardData.spotlights || []).map(function (task) {
                return [
                    "<article class='fsd_spotlight_card' data-task-id='", self._escape(String(task.id)), "'>",
                    "<div class='fsd_spotlight_crn'>", self._escape(task.crn || "-"), "</div>",
                    "<h3>", self._escape(task.title || "-"), "</h3>",
                    "<div class='fsd_spotlight_meta'>", self._escape(task.customer || "-"), "</div>",
                    "<div class='fsd_spotlight_meta'>", self._escape(task.stage || "-"), " • Age ", self._escape(String(task.age_days || 0)), " days</div>",
                    "<div class='fsd_spotlight_costs'>",
                    "<span>Material ", self._escape(self._formatValue(task.material_cost_total, true)), "</span>",
                    "<span>Timesheet ", self._escape(self._formatValue(task.timesheet_cost_total, true)), "</span>",
                    "</div>",
                    "</article>",
                ].join("");
            }).join("");
            this.$("#fsd_spotlight_grid").html(cardsHtml);
        },

        _renderChart: function (key, selector, config, onClick) {
            var canvas = this.$(selector);
            if (!canvas.length) {
                return;
            }
            if (this.charts[key]) {
                this.charts[key].destroy();
            }
            if (onClick) {
                config.options = config.options || {};
                config.options.onClick = function (event, items) {
                    if (items && items.length) {
                        onClick(items[0]._index, items[0]);
                    }
                };
            }
            this.charts[key] = new Chart(canvas, config);
        },

        _getBarOptions: function () {
            return {
                responsive: true,
                maintainAspectRatio: false,
                legend: {display: false},
                scales: {
                    yAxes: [{ticks: {beginAtZero: true}}],
                },
            };
        },

        _formatValue: function (value, isMonetary) {
            var numeric = Number(value || 0);
            if (!isMonetary) {
                return numeric.toLocaleString();
            }
            var currency = this.dashboardData.currency || {};
            var formatted = numeric.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
            return currency.position === "after" ? formatted + " " + (currency.symbol || "") : (currency.symbol || "") + " " + formatted;
        },

        _openDashboardAction: function (actionType, extraDomain, title) {
            var baseAction = this.dashboardData.task_action;
            var action = JSON.parse(JSON.stringify(baseAction || {}));
            action.domain = (action.domain || []).concat(extraDomain || []);
            if (title) {
                action.name = title;
            }
            this.do_action(action);
        },

        _onApplyFilters: function () {
            this._loadDashboardData({
                period: this.$("#fsd_period").val(),
                company_id: this.$("#fsd_company").val(),
            });
        },

        _onResetFilters: function () {
            this._loadDashboardData({
                period: "90",
                company_id: "0",
            });
        },

        _onKpiClick: function (ev) {
            var $target = $(ev.currentTarget);
            var actionType = $target.data("action-type");
            var domain = JSON.parse($target.attr("data-domain") || "[]");
            var title = $target.find(".fsd_kpi_label").text();
            this._openDashboardAction(actionType, domain, title);
        },

        _onSpotlightClick: function (ev) {
            var taskId = Number($(ev.currentTarget).data("task-id"));
            this.do_action({
                type: "ir.actions.act_window",
                name: "CRN",
                res_model: "project.task",
                res_id: taskId,
                views: [[false, "form"]],
                target: "current",
                context: {fsm_mode: true},
            });
        },

        _escape: function (value) {
            return $("<div/>").text(value || "").html();
        },
    });

    core.action_registry.add("fsm_service_monitor_dashboard", FsmServiceDashboard);

    return FsmServiceDashboard;
});
