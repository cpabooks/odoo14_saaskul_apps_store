odoo.define("cpabooks_cafm.CafmDashboard", function (require) {
    "use strict";

    var AbstractAction = require("web.AbstractAction");
    var core = require("web.core");

    var CafmDashboard = AbstractAction.extend({
        contentTemplate: "CpabooksCafmDashboard",
        xmlDependencies: ["/cpabooks_cafm/static/src/xml/cafm_dashboard_main.xml"],
        THEME_KEY: "cpa_cafm_dashboard_theme",
        events: {
            "click .o_cfd_dash_kpi": "_onDrillClick",
            "click .o_cfd_dash_row": "_onDrillClick",
            "click .o_cfd_completion_kpi": "_onDrillClick",
            "click .o_cfd_open_main_menu": "_onOpenMainMenu",
            "click .cpa-cafm-theme-btn": "_onThemeClick",
        },

        init: function (parent, action) {
            this._super(parent, action);
            this.dashboardData = null;
            this._charts = {};
            this._chartLibPromise = null;
            this._theme = "default";
        },

        start: function () {
            var self = this;
            this.set("title", "CAFM Operations Dashboard");
            return this._super.apply(this, arguments).then(function () {
                try {
                    require("cpabooks_cafm.shell").requestSyncSidebar(true);
                } catch (error) {
                    // shell loads globally; dashboard still works without it
                }
                try {
                    var UiTheme = require("cpabooks_cafm.ui_theme");
                    self._theme = UiTheme.syncShellTheme();
                    UiTheme.applyUiTheme(self._theme);
                    UiTheme.syncNavbarToggleState();
                } catch (e) {
                    self._theme = "default";
                }
                $(window).off("cafm_ui_theme_changed.cafm_dash").on("cafm_ui_theme_changed.cafm_dash", function (ev, theme) {
                    self._theme = theme === "dark" ? "dark" : "default";
                    if (self.dashboardData) {
                        self._renderCharts((self.dashboardData && self.dashboardData.charts) || {});
                    }
                });
                return self._loadDashboardData();
            });
        },

        destroy: function () {
            $(window).off("cafm_ui_theme_changed.cafm_dash");
            this._destroyCharts();
            return this._super.apply(this, arguments);
        },

        _readStoredTheme: function () {
            try {
                return require("cpabooks_cafm.ui_theme").readTheme();
            } catch (e) {
                return "default";
            }
        },

        _applyTheme: function (theme) {
            try {
                this._theme = require("cpabooks_cafm.ui_theme").applyUiTheme(theme);
            } catch (e) {
                this._theme = theme === "dark" ? "dark" : "default";
            }
            if (!_.isEmpty(this._charts) && this.dashboardData) {
                this._renderCharts((this.dashboardData && this.dashboardData.charts) || {});
            }
        },

        _onThemeClick: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            this._applyTheme(ev.currentTarget.getAttribute("data-theme"));
        },

        _injectNavbarThemeToggle: function () {
            try {
                require("cpabooks_cafm.ui_theme").injectNavbarThemeToggle();
            } catch (e) { /* ignore */ }
        },

        _chartTheme: function () {
            var dark = this._theme === "dark";
            return {
                tick: dark ? "#86efac" : "#64748b",
                grid: dark ? "rgba(74, 222, 128, 0.12)" : "rgba(148, 163, 184, 0.25)",
                legend: dark ? "#86efac" : "#334155",
            };
        },

        _loadDashboardData: function () {
            this._setLoading(true);
            this._setLoadError("");
            return this._rpc({
                model: "project.project",
                method: "get_cafm_dashboard_data",
                args: [],
            }).then(function (result) {
                this.dashboardData = result;
                this._renderDashboard();
            }.bind(this)).guardedCatch(function (error) {
                this._setLoadError(
                    error.message ||
                        "Dashboard data could not be loaded. Upgrade cpabooks_cafm and restart Odoo."
                );
            }.bind(this)).finally(function () {
                this._setLoading(false);
            }.bind(this));
        },

        _setLoading: function (loading) {
            this.$("#cfd_loading").toggle(!!loading);
        },

        _setLoadError: function (message) {
            var $error = this.$("#cfd_load_error");
            if (!message) {
                $error.hide().text("");
                return;
            }
            $error.text(message).show();
        },

        _onOpenMainMenu: function (ev) {
            ev.preventDefault();
            var $toggle = this.$el.closest(".o_action_manager").find(".o_menu_toggle").first();
            if (!$toggle.length) {
                $toggle = $(".o_main_navbar .o_menu_toggle").first();
            }
            if ($toggle.length) {
                $toggle.trigger("click");
            }
        },

        _normalizeLegacyShell: function () {
            var $root = this.$(".o_cfd_dashboard_root");
            if (!$root.length) {
                $root = this.$(".cfd_shell");
            }
            if (!$root.length) {
                return;
            }
            $root.find(
                ".cfd_demo_bar, .o_cfd_pipeline_panel, .cfd_chart_grid, .cfd_table_grid, .cfd_focus_grid, .cfd_kpi_grid, .cfd_hero"
            ).remove();

            if (!this.$("#cfd_loading").length) {
                $root.find(".o_cfd_dash_header").first().after(
                    $("<div class='cfd_loading' id='cfd_loading'/>").text("Loading dashboard…")
                );
            }
            if (!this.$("#cfd_load_error").length) {
                $root.append($("<div class='cfd_load_error' id='cfd_load_error' style='display:none;'/>"));
            }
            if (!this.$(".o_cfd_analytics_panel").length) {
                $root.find(".o_cfd_dash_header").first().after(
                    $(
                        "<section class='o_cfd_analytics_panel'>" +
                            "<div class='o_cfd_completion_head'><div>" +
                            "<h2 class='o_cfd_analytics_title' id='cfd_completion_title'>Call completion</h2>" +
                            "<p class='o_cfd_analytics_hint' id='cfd_completion_hint'></p>" +
                            "</div></div>" +
                            "<div class='o_cfd_completion_kpis' id='cfd_completion_kpis'></div>" +
                            "<div class='o_cfd_charts_grid'>" +
                            "<article class='o_cfd_chart_card'>" +
                            "<div class='o_cfd_chart_head'>" +
                            "<h3 class='o_cfd_chart_title' id='cfd_chart_month_title'></h3>" +
                            "<p class='o_cfd_chart_subtitle' id='cfd_chart_month_subtitle'></p>" +
                            "</div><div class='o_cfd_chart_canvas_wrap'><canvas id='cfd_chart_month'></canvas></div>" +
                            "</article>" +
                            "<article class='o_cfd_chart_card'>" +
                            "<div class='o_cfd_chart_head'>" +
                            "<h3 class='o_cfd_chart_title' id='cfd_chart_year_title'></h3>" +
                            "<p class='o_cfd_chart_subtitle' id='cfd_chart_year_subtitle'></p>" +
                            "</div><div class='o_cfd_chart_canvas_wrap'><canvas id='cfd_chart_year'></canvas></div>" +
                            "</article></div></section>"
                    )
                );
            }
            if (!this.$(".o_cfd_dash_kpis").length) {
                $root.append($("<div class='o_cfd_dash_kpis'/>"));
            }
            if (!this.$(".o_cfd_dash_workflow").length) {
                $root.append($("<div class='o_cfd_dash_workflow'/>"));
            }
            this.$(".cfd_root").addClass("o_cfd_dashboard_main");
        },

        _renderDashboard: function () {
            if (!this.dashboardData) {
                return;
            }
            this._normalizeLegacyShell();
            var data = this.dashboardData;
            this.$("#cfd_eyebrow").text(data.eyebrow || "CAFM");
            this.$("#cfd_title").text(data.title || "CAFM Operations Dashboard");
            this.$("#cfd_subtitle").text(data.subtitle || "");
            this._renderCompletion(data.completion || {});
            this._renderCharts(data.charts || {});
            this._renderKpis(data.kpis || []);
            this._renderWorkflow(data.workflow || []);
        },

        _renderDrillButton: function (className, drill, contents) {
            return $("<button type='button'/>")
                .addClass(className)
                .attr("data-drill-json", JSON.stringify(drill || {}))
                .append(contents);
        },

        _renderCompletion: function (completion) {
            this.$("#cfd_completion_title").text(completion.label || "Call completion");
            this.$("#cfd_completion_hint").text(completion.hint || "");
            var $wrap = this.$("#cfd_completion_kpis").empty();
            _.each(completion.tiles || [], function (tile) {
                var display = this._number(tile.value) + (tile.suffix || "");
                $wrap.append(
                    this._renderDrillButton("o_cfd_completion_kpi", tile.drill || {}, [
                        $("<div class='o_cfd_completion_kpi_icon'><i class='fa " + (tile.icon || "fa-circle") + "'/></div>"),
                        $("<div class='o_cfd_completion_kpi_body'/>").append(
                            $("<div class='o_cfd_completion_kpi_value'/>").text(display),
                            $("<div class='o_cfd_completion_kpi_label'/>").text(tile.label || "")
                        ),
                    ])
                );
            }, this);
        },

        _ensureChartLib: function () {
            if (window.Chart) {
                return Promise.resolve();
            }
            if (this._chartLibPromise) {
                return this._chartLibPromise;
            }
            this._chartLibPromise = new Promise(function (resolve, reject) {
                $.getScript("/web/static/lib/Chart/Chart.js")
                    .done(function () {
                        if (window.Chart) {
                            resolve();
                        } else {
                            reject(new Error("Chart.js loaded but Chart global is missing."));
                        }
                    })
                    .fail(function () {
                        reject(new Error("Chart.js could not be loaded."));
                    });
            });
            return this._chartLibPromise;
        },

        _destroyCharts: function () {
            _.each(this._charts, function (chart) {
                if (chart && chart.destroy) {
                    chart.destroy();
                }
            });
            this._charts = {};
        },

        _renderCharts: function (charts) {
            var self = this;
            this._destroyCharts();
            this._ensureChartLib().then(function () {
                window.setTimeout(function () {
                    self._renderChart("month", charts.month || {}, charts.labels || [], "cfd_chart_month");
                    self._renderChart("year", charts.year || {}, charts.labels || [], "cfd_chart_year");
                }, 0);
            }).guardedCatch(function (error) {
                self.$(".o_cfd_chart_canvas_wrap").html(
                    $("<p class='cfd_load_error'/>").text(
                        (error && error.message) || "Charts unavailable. Hard-refresh the browser after upgrading cpabooks_cafm."
                    )
                );
            });
        },

        _renderChart: function (key, chartData, labels, canvasId) {
            this.$("#cfd_chart_" + key + "_title").text(chartData.title || "");
            this.$("#cfd_chart_" + key + "_subtitle").text(chartData.subtitle || "");
            var canvas = this.$("#" + canvasId)[0];
            if (!canvas) {
                return;
            }
            var datasets = _.map(chartData.series || [], function (series) {
                return {
                    label: series.label,
                    data: series.values || [],
                    backgroundColor: series.color || "#4ade80",
                    borderColor: series.color || "#4ade80",
                    borderWidth: 1,
                };
            });
            this._charts[key] = new window.Chart(canvas.getContext("2d"), {
                type: "bar",
                data: {
                    labels: labels,
                    datasets: datasets,
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    legend: {
                        labels: {
                            fontColor: this._chartTheme().legend,
                        },
                    },
                    tooltips: {
                        mode: "index",
                        intersect: false,
                    },
                    scales: {
                        xAxes: [{
                            ticks: {fontColor: this._chartTheme().tick},
                            gridLines: {color: this._chartTheme().grid},
                        }],
                        yAxes: [{
                            ticks: {
                                beginAtZero: true,
                                fontColor: this._chartTheme().tick,
                                precision: 0,
                            },
                            gridLines: {color: this._chartTheme().grid},
                        }],
                    },
                },
            });
        },

        _renderKpis: function (kpis) {
            var $wrap = this.$(".o_cfd_dash_kpis").empty();
            _.each(kpis, function (kpi) {
                $wrap.append(
                    this._renderDrillButton("o_cfd_dash_kpi", kpi.drill || {}, [
                        $("<div class='o_cfd_dash_kpi_icon'><i class='fa " + (kpi.icon || "fa-circle") + "'/></div>"),
                        $("<div class='o_cfd_dash_kpi_value'/>").text(this._number(kpi.value)),
                        $("<div class='o_cfd_dash_kpi_label'/>").text(kpi.label || ""),
                    ])
                );
            }, this);
        },

        _renderWorkflow: function (sections) {
            var $wrap = this.$(".o_cfd_dash_workflow").empty();
            _.each(sections, function (section) {
                var theme = section.theme || "intake";
                var $sec = $("<div class='o_cfd_dash_section'/>").addClass("o_cfd_theme_" + theme);
                $sec.append($("<h3 class='o_cfd_dash_section_title'/>").text(section.title || ""));
                var $list = $("<div class='o_cfd_dash_section_list'/>");
                _.each(section.items || [], function (item) {
                    $list.append(
                        this._renderDrillButton("o_cfd_dash_row o_cfd_status_" + (item.status || "pending"), item.drill || {}, [
                            $("<span class='o_cfd_dash_row_label'/>").text(item.label || ""),
                            $("<span class='o_cfd_dash_row_badge'/>").text(this._number(item.count)),
                        ])
                    );
                }, this);
                $sec.append($list);
                $wrap.append($sec);
            }, this);
        },

        _normalizeSearchViewId: function (searchViewId) {
            if (searchViewId === false || searchViewId === null || searchViewId === undefined) {
                return null;
            }
            if (_.isNumber(searchViewId)) {
                return [searchViewId, "search"];
            }
            if (_.isArray(searchViewId) && searchViewId.length) {
                return [searchViewId[0], searchViewId[1] || "search"];
            }
            return null;
        },

        _onDrillClick: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var drillJson = $(ev.currentTarget).attr("data-drill-json");
            var drill = null;
            if (drillJson) {
                try {
                    drill = JSON.parse(drillJson);
                } catch (error) {
                    drill = null;
                }
            }
            if (!drill || !drill.res_model) {
                return;
            }
            var self = this;
            this._rpc({
                model: "cafm.dashboard",
                method: "get_drill_action",
                args: [drill],
            }).then(function (action) {
                action = action || {};
                action.context = action.context || {};
                var searchViewId = self._normalizeSearchViewId(action.search_view_id);
                if (searchViewId) {
                    action.search_view_id = searchViewId;
                } else {
                    delete action.search_view_id;
                }
                delete action.view_id;
                delete action.id;
                // Odoo 14 web client registers the list controller as "list" (not "tree").
                var modes = _.map(action.views || [], function (view) {
                    return view && view[1];
                });
                var preferList = _.contains(modes, "list") || _.contains(modes, "tree");
                self.do_action(action, {
                    viewType: preferList ? "list" : undefined,
                    clear_breadcrumbs: false,
                });
            });
        },

        _number: function (value) {
            if (typeof value === "number" && value % 1 !== 0) {
                return new Intl.NumberFormat("en-US", {maximumFractionDigits: 1}).format(value);
            }
            return new Intl.NumberFormat("en-US", {maximumFractionDigits: 0}).format(Number(value || 0));
        },
    });

    core.action_registry.add("cpabooks_cafm_dashboard", CafmDashboard);
    return CafmDashboard;
});
