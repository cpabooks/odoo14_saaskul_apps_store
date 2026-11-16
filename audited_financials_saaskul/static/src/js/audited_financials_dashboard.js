/** @odoo-module **/
import { Component, onMounted, onWillUnmount, useRef } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { session } from "@web/session";
import { user } from "@web/core/user";

function $(selector, context) {
    const jq = window.jQuery;
    if (!jq) {
        throw new Error("Audited Financials: jQuery did not load.");
    }
    return jq(selector, context);
}
Object.defineProperty($, "extend", {
    get() {
        return window.jQuery && window.jQuery.extend;
    },
});
if (!Promise.prototype.guardedCatch) {
    Promise.prototype.guardedCatch = function (handler) {
        return this.catch(handler);
    };
}

Object.defineProperty(session, "uid", {
    configurable: true,
    get() {
        return user.userId;
    },
});
Object.defineProperty(session, "user_context", {
    configurable: true,
    get() {
        return user.context || {};
    },
});

const rpc = {
    query(spec) {
        const orm = rpc._orm;
        if (!orm) {
            return Promise.reject(new Error("Audited Financials ORM is not ready"));
        }
        return orm.call(spec.model, spec.method, spec.args || [], spec.kwargs || {});
    },
};

const HTML_ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#x27;", "`": "&#x60;" };
const _ = {
    escape(value) {
        return String(value === null || value === undefined ? "" : value).replace(/[&<>"'`]/g, (ch) => HTML_ESCAPES[ch]);
    },
};

const core = {
    _t,
    qweb: { templates: { "AuditedFinancialsDashboard.v136": true } },
};

const dashboardMethods = {
        events: {
            "click .o_afg_nav a": "_onNavClick",
            "click .o_afg_btn_reload_periods": "_onReloadPeriods",
            "click .o_afg_btn_load_default": "_onLoadDefault",
            "click .o_afg_btn_load_sample": "_onLoadSample",
            "click .o_afg_btn_clear_adj": "_onClearAdjustments",
            "click .o_afg_btn_save_internal_notes": "_onSaveInternalNotes",
            "click .o_afg_btn_print_audit": "_onPrintAudit",
            "click .o_afg_btn_print_simple": "_onPrintSimple",
            "click .o_afg_btn_print_fta": "_onPrintFta",
            "click .o_afg_btn_print_setup": "_onPrintSetup",
            "click .o_afg_dpi_btn": "_onDpiStep",
            "click .o_afg_btn_export": "_onExport",
            "click .o_afg_btn_export_xlsx": "_onExportAuditXlsx",
            "click .o_afg_btn_ct_master": "_onExportCtFilingMaster",
            "click .o_afg_btn_export_word": "_onExportAuditWord",
            "click .o_afg_btn_save": "_onSave",
            "click .o_afg_btn_toggle": "_onToggleEdit",
            "click .o_afg_btn_open_form": "_onOpenForm",
            "click .o_afg_btn_merge_ledger": "_onMergeLedger",
            "click .o_afg_btn_save_report_text": "_onSaveReportText",
            "click .o_afg_btn_multco": "_onToggleMultco",
            "click .o_afg_btn_print_page": "_onPrintPage",
            "click .o_afg_btn_pdf_page": "_onPdfPage",
            "click .o_afg_btn_excel_page": "_onExcelPage",
            "click .o_afg_btn_remove_group": "_onToggleRemoveGroup",
            "change .o_afg_amount_input": "_onAmountChange",
            "change .o_afg_export_level": "_onExportLevelChange",
            "change .o_afg_page_setup": "_onPageSetupChange",
            "click .o_afg_btn_save_margins": "_onSavePageMargins",
            "click .o_afg_btn_stop_empty_page": "_onStopPrintEmptyPage",
            "click .o_afg_period_card": "_onPeriodPresetClick",
            "click .o_afg_btn_apply_custom": "_onApplyCustomPeriod",
            "click .o_afg_btn_year_order": "_onToggleYearOrder",
            "click .o_afg_btn_period_span": "_onPeriodSpanCardClick",
            "change .o_afg_period_span_select": "_onPeriodSpanSelect",
            "click .o_afg_l0_toggle, .o_afg_l1_toggle, tr.o_afg_l1_row td.o_afg_desc_cell": "_onRowToggle",
            "click .o_afg_btn_toggle_codes": "_onToggleCodes",
            "click tr.o_afg_drillable": "_onDrillJournal",
            "contextmenu tr.o_afg_map_group": "_onMapGroupContext",
            "contextmenu tr.o_afg_map_ledger": "_onMapLedgerContext",
            "contextmenu tr.o_afg_kind_ledger": "_onMapLedgerContext",
            "contextmenu tr.o_afg_under_ungrouped": "_onMapLedgerContext",
            "click .o_afg_fa_col_mode": "_onFaColumnModeClick",
        },

        init: function (parent, action) {
            this._super(parent, action);
            action = action || {};
            var ctx = action.context || {};
            this.section = this._afgResolveInitialSection(ctx);
            this.versionId = null;
            this.data = {};
            this._rowSeq = 0;
            this._detailLevel = "ledger";
            this._viewMaxLevel = this._afgResolveInitialDepth();
            this._depthLoaded = true;
            this._typeOpen = {};
            this._rootOpen = {};
            this._hideL3Globally = false;
            this._hideL4Globally = true;
            this._hideAccountGroups = this._viewMaxLevel === 3;
            this._hideL1Globally = false;
            this._hideL0Globally = this._viewMaxLevel === 3;
            this._hideLedgersPack = this._viewMaxLevel <= 2;
            this._hideLgColumn = this._viewMaxLevel <= 3;
            this._hideHashColumn = this._viewMaxLevel <= 2;
            this._rootForceLedger = {};
            this._showCodes = false;
            // false = ascending (prior then current); true = descending (current then prior)
            // Default ascending until server preference loads; only user toggle may change it.
            this._yearsDescending = false;
            this._periodSpan = "2y";
            this._yearsOrderLoaded = false;
            this._yearsDirty = false;
            this._customPeriodOpen = false;
            // Fixed Assets: single (totals only) | multi (ledger-wise columns). Default single.
            this._faColumnMode = this._afgResolveFaColumnMode();
            this._internalActionNotes = "";
        },

        _afgFaColumnStorageKey: function () {
            return "cpabooks_afg.fa_column_mode." + String(session.uid || 0);
        },

        _afgNormalizeFaColumnMode: function (mode) {
            var m = String(mode || "").toLowerCase();
            return m === "multi" ? "multi" : "single";
        },

        _afgReadFaColumnMode: function () {
            try {
                if (!window.localStorage) {
                    return null;
                }
                var raw = localStorage.getItem(this._afgFaColumnStorageKey());
                if (raw === null || raw === undefined || raw === "") {
                    return null;
                }
                return this._afgNormalizeFaColumnMode(raw);
            } catch (e) {
                return null;
            }
        },

        _afgSaveFaColumnMode: function (mode) {
            var m = this._afgNormalizeFaColumnMode(mode);
            try {
                if (window.localStorage) {
                    localStorage.setItem(this._afgFaColumnStorageKey(), m);
                }
            } catch (e) {
                // ignore
            }
            return m;
        },

        _afgResolveFaColumnMode: function () {
            var saved = this._afgReadFaColumnMode();
            var mode = saved !== null && saved !== undefined ? saved : "single";
            return this._afgSaveFaColumnMode(mode);
        },

        _onFaColumnModeClick: function (ev) {
            ev.preventDefault();
            var mode = this._afgNormalizeFaColumnMode($(ev.currentTarget).data("faMode"));
            this._faColumnModeUserSet = true;
            this._faColumnMode = this._afgSaveFaColumnMode(mode);
            if (this.section === "fixed_assets" && this.data) {
                this._renderSection(this.section);
            }
        },

        _afgDepthStorageKey: function () {
            return "cpabooks_afg.report_level." + String(session.uid || 0);
        },

        _afgLegacyDepthStorageKey: function () {
            return "cpabooks_afg.print_max_level." + String(session.uid || 0);
        },

        _afgLegacyDepthToPack: function (depth) {
            var map = {0: 1, 1: 2, 2: 4, 3: 4, 4: 3, 5: 3};
            var n = parseInt(depth, 10);
            if (isNaN(n)) {
                return 3;
            }
            return map[n] !== undefined ? map[n] : 3;
        },

        /** Report pack L1–L4 (Official → Working Papers). */
        _afgNormalizeDepth: function (lvl) {
            return this._afgNormalizeReportPack(lvl);
        },

        /** Non-UAE (non-AED) companies only get L1 Official and L4 Working Papers. */
        _afgTwoLevelOnly: function () {
            var d = this.data || {};
            return !!d.currency && d.currency !== "AED";
        },

        _afgNormalizeReportPack: function (lvl) {
            var n = parseInt(lvl, 10);
            if (this._afgTwoLevelOnly()) {
                // Non-UAE: L1 Official only (L2 Working Papers removed from dropdown).
                return 1;
            }
            if (isNaN(n)) {
                return 3;
            }
            // Pack 5 = L1 Official Arabic (not legacy depth 5)
            if (n === 5) {
                return 5;
            }
            // Legacy hierarchy depths accidentally still in storage
            if (n === 0) {
                return this._afgLegacyDepthToPack(n);
            }
            return Math.max(1, Math.min(4, n));
        },

        _afgReadSavedDepth: function () {
            try {
                if (!window.localStorage) {
                    return null;
                }
                var raw = localStorage.getItem(this._afgDepthStorageKey());
                if (raw === null || raw === undefined || raw === "") {
                    var legacy = localStorage.getItem(this._afgLegacyDepthStorageKey());
                    if (legacy === null || legacy === undefined || legacy === "") {
                        return null;
                    }
                    return this._afgLegacyDepthToPack(legacy);
                }
                return this._afgNormalizeReportPack(raw);
            } catch (e) {
                return null;
            }
        },

        _afgSaveDepth: function (lvl) {
            var n = this._afgNormalizeReportPack(lvl);
            try {
                if (window.localStorage) {
                    localStorage.setItem(this._afgDepthStorageKey(), String(n));
                }
            } catch (e) {
                // ignore
            }
            return n;
        },

        _afgResolveInitialDepth: function () {
            var saved = this._afgReadSavedDepth();
            var depth = saved !== null && saved !== undefined ? saved : 3;
            return this._afgSaveDepth(depth);
        },

        _afgPackSpec: function () {
            var pack = this._afgNormalizeReportPack(this._viewMaxLevel || 3);
            var d = this.data || {};
            if (d.report_pack && parseInt(d.report_pack.pack, 10) === pack) {
                return d.report_pack;
            }
            // Client-side fallback mirroring Python _afg_report_pack_spec
            var hp = pack === 5 ? 1 : pack;
            var sections = ["pl", "bs", "equity", "cashflow", "fixed_assets", "notes", "review"];
            var print_chapters = ["pl", "bs", "equity", "cashflow", "fixed_assets", "notes"];
            if (hp >= 4) {
                sections = sections.concat(["tb", "tb_x", "fs_recon"]);
                print_chapters = ["pl", "bs", "tb", "equity", "cashflow", "fixed_assets", "notes", "validation", "fs_recon"];
            }
            return {
                pack: pack,
                hierarchy_pack: hp,
                hide_lg: hp <= 3,
                hide_codes: hp <= 2,
                hide_hash: hp <= 2,
                hide_merge_ledger: hp <= 2,
                hide_remove_group: hp <= 3,
                hide_full_editor: hp <= 2,
                show_tb: hp >= 4,
                show_ledgers: hp >= 2,
                show_account_groups: hp === 3,
                show_coa_types: hp === 1 || hp === 2,
                show_afg_groups: hp !== 2,
                arabic: pack === 5,
                rtl: pack === 5,
                sections_allowed: sections,
                print_chapters: print_chapters,
                tree_max_level: hp <= 1 ? 1 : 4,
            };
        },

        _afgValidSections: {
            pl: 1,
            bs: 1,
            fta: 1,
            equity: 1,
            cashflow: 1,
            fixed_assets: 1,
            tb: 1,
            tb_x: 1,
            notes: 1,
            review: 1,
        },

        _afgIsValidSection: function (sec) {
            return !!(sec && this._afgValidSections[String(sec)]);
        },

        _afgSectionStorageKey: function () {
            return "cpabooks_afg.last_section." + String(session.uid || 0);
        },

        _afgIsBrowserReload: function () {
            try {
                var nav = window.performance && performance.getEntriesByType &&
                    performance.getEntriesByType("navigation")[0];
                if (nav && nav.type) {
                    return nav.type === "reload";
                }
                if (window.performance && performance.navigation) {
                    return performance.navigation.type === 1;
                }
            } catch (e) {
                // ignore
            }
            return false;
        },

        _afgReadSavedSection: function () {
            try {
                if (!window.localStorage) {
                    return null;
                }
                var saved = localStorage.getItem(this._afgSectionStorageKey());
                return this._afgIsValidSection(saved) ? String(saved) : null;
            } catch (e) {
                return null;
            }
        },

        _afgSaveSection: function (sec) {
            if (!this._afgIsValidSection(sec)) {
                return;
            }
            try {
                if (window.localStorage) {
                    localStorage.setItem(this._afgSectionStorageKey(), String(sec));
                }
            } catch (e) {
                // ignore quota / private mode
            }
        },

        /**
         * Keep the last sidebar report on browser reload (e.g. Fixed Assets Register).
         * Fresh menu open still uses action context (afg_section).
         */
        _afgResolveInitialSection: function (ctx) {
            ctx = ctx || {};
            var fromCtx = ctx.afg_section;
            var saved = this._afgReadSavedSection();
            var section;
            if (this._afgIsBrowserReload() && saved) {
                section = saved;
            } else if (this._afgIsValidSection(fromCtx)) {
                section = String(fromCtx);
            } else if (saved) {
                section = saved;
            } else {
                section = "bs";
            }
            this._afgSaveSection(section);
            return section;
        },

        _getRpcContext: function () {
            var ctx = $.extend(true, {}, session.user_context || {});
            var cids = null;
            if (window.$ && $.bbq && $.bbq.getState) {
                var st = $.bbq.getState();
                if (st && st.cids) {
                    cids = Array.isArray(st.cids) ? st.cids[0] : st.cids;
                }
            }
            if (cids) {
                var parts = String(cids).split(",").map(function (s) {
                    return parseInt(s.trim(), 10);
                }).filter(function (n) { return !isNaN(n); });
                if (parts.length) {
                    ctx.allowed_company_ids = parts;
                }
            }
            // Match on-screen year column order in Excel / Word / PDF exports.
            ctx.afg_years_descending = !!this._yearsDescending;
            ctx.afg_export_dpi = this._dpiValue();
            return ctx;
        },

        /** Opening + (Tx + Closing)×years: descending → current year pair after Opening. */
        _tbAmountOrder: function () {
            // Indices: 0 Opening, 1 Tx prior, 2 Closing prior, 3 Tx current, 4 Closing current
            return this._yearsDescending ? [0, 3, 4, 1, 2] : [0, 1, 2, 3, 4];
        },

        _tbReorderAmounts: function (vals, width) {
            var src = (vals || []).slice();
            while (src.length < width) {
                src.push(null);
            }
            if (src.length > width) {
                src = src.slice(0, width);
            }
            if (width < 4) {
                return src;
            }
            var order = this._tbAmountOrder();
            if (width >= 5 && order.length >= 5) {
                return order.slice(0, 5).map(function (i) {
                    return src[i];
                });
            }
            // Legacy 6-col (duplicated Opening for year 2)
            if (width >= 6) {
                var legacy6 = this._yearsDescending ? [3, 4, 5, 0, 1, 2] : [0, 1, 2, 3, 4, 5];
                return legacy6.map(function (i) {
                    return src[i];
                });
            }
            // Legacy 4-col Opening/Closing pairs
            if (width === 4) {
                var legacy = this._yearsDescending ? [2, 3, 0, 1] : [0, 1, 2, 3];
                return legacy.map(function (i) {
                    return src[i];
                });
            }
            return order.map(function (i) {
                return src[i];
            });
        },

        _tbOrderedColumns: function (tb) {
            var cols = tb.columns || [];
            var width = cols.length || 5;
            var order = this._tbAmountOrder();
            if (width >= 5 && width < 6) {
                return order.slice(0, 5).map(function (i) {
                    return cols[i] || {};
                });
            }
            if (width >= 6) {
                var legacy6 = this._yearsDescending ? [3, 4, 5, 0, 1, 2] : [0, 1, 2, 3, 4, 5];
                return legacy6.map(function (i) {
                    return cols[i] || {};
                });
            }
            if (width === 4) {
                var legacy = this._yearsDescending ? [2, 3, 0, 1] : [0, 1, 2, 3];
                return legacy.map(function (i) {
                    return cols[i] || {};
                });
            }
            return cols;
        },

        _tbHeaderRowHtml: function (tb) {
            var self = this;
            var ordered = self._tbOrderedColumns(tb);
            // Flat headers: Opening | Transactions 2024 | Closing | Transactions 2025 | Closing
            // Year/month only on Transactions (Opening/Closing are bare bridge labels).
            var cells = [
                "<th>#</th>",
                "<th class='o_afg_th_lg'>" + _.escape(_t("LG")) + "</th>",
                "<th class='o_afg_tb_th_desc'>" + _.escape(_t("Description")) + "</th>",
                "<th class='o_afg_tb_th_notes'>" + _.escape(_t("Notes")) + "</th>",
            ];
            ordered.forEach(function (col) {
                var lab = (col && col.label) || "";
                var role = (col && col.role) || "";
                if (col && col.year && role === "transactions") {
                    cells.push(
                        "<th class='text-right small o_afg_tb_amt_th o_afg_tb_th_wrap'>"
                        + "<span class='o_afg_tb_h1'>" + _.escape(String(lab || _t("Transactions"))) + "</span><br/>"
                        + "<span class='o_afg_tb_h2'>" + _.escape(String(col.year)) + "</span></th>"
                    );
                    return;
                }
                cells.push(
                    "<th class='text-right small o_afg_tb_amt_th'>" + _.escape(lab) + "</th>"
                );
            });
            return "<tr>" + cells.join("") + "</tr>";
        },

        _renderTbPanels: function (tb, d) {
            var self = this;
            var $host = this.$(".o_afg_tb_panels").empty().show();
            d._tbFiveColumn = true;
            d._tbAmountWidth = (tb.columns && tb.columns.length) ? tb.columns.length : 5;
            this._rowSeq = 0;
            var $table = $("<table class='table table-sm o_afg_table o_afg_tb_panel_table o_afg_tb_unified'/>");
            $table.append($("<thead/>").html(self._tbHeaderRowHtml(tb)));
            var $tbody = $("<tbody/>");
            (tb.panels || []).forEach(function (panel) {
                var colCount = 4 + ((tb.columns || []).length || 0);
                var $banner = $("<tr class='o_afg_tb_section_banner o_afg_main_line_fill'/>");
                $banner.append(
                    $("<td/>").attr("colspan", colCount).text(panel.title || "")
                );
                $tbody.append($banner);
                (panel.roots || []).forEach(function (root) {
                    self._renderLineRow(root, $tbody, d, 0, "");
                });
            });
            $table.append($tbody);
            $host.append($table);
            if (tb.balance_ok === false) {
                $host.append(
                    $("<div class='alert alert-warning o_afg_tb_balance_warn'/>").text(
                        _t("Trial Balance is not nil. Net difference: ") +
                        self._fmt(tb.balance_diff || 0)
                    )
                );
            } else if ((tb.panels || []).length) {
                $host.append(
                    $("<div class='alert alert-success o_afg_tb_balance_ok py-1 px-2 small'/>").text(
                        _t("TOTAL (Net — must be nil) — balanced like Accounting Trial Balance.")
                    )
                );
            }
        },

        _afgBindContentTemplate: function () {
            var qweb = core.qweb;
            var names = [
                "AuditedFinancialsDashboard.v136",
                "AuditedFinancialsDashboard",
                "AuditedFinancialsDashboard.v134",
                "AuditedFinancialsDashboard.v133",
                "AuditedFinancialsDashboard.v132",
            ];
            var i;
            var name;
            for (i = 0; i < names.length; i++) {
                name = names[i];
                if (qweb.templates && qweb.templates[name]) {
                    this.contentTemplate = name;
                    return;
                }
            }
        },

        start: function () {
            this.set("title", _t("Financial Statements"));
            $("body").addClass("o_afg_single_sidebar_shell");
            var self = this;
            this._afgBindContentTemplate();
            return Promise.resolve(this._super.apply(this, arguments)).then(function () {
                self._ensureExportToolbarControls();
                self._ensureYearOrderButton();
                self._syncYearOrderButton();
                self._bindAfgRowClicks();
                return self._loadData();
            }).guardedCatch(function () {
                try {
                    if (self.$el && !self.$el.find(".o_afg_root, .o_afg_empty").length) {
                        self.$el.html(
                            "<div class='o_afg_root p-3'><div class='o_afg_empty'></div></div>"
                        );
                    }
                } catch (e2) { /* ignore */ }
                return self._loadData();
            });
        },

        /**
         * Guarantee Export depth + Remove Group exist even if an old QWeb cache is served.
         * Inserts at the exact spots the user expects (after Reload / before Full editor).
         */
        _ensureExportToolbarControls: function () {
            var $toolbar = this.$(".o_afg_toolbar .col-12");
            if ($toolbar.length && !this.$(".o_afg_export_level").length) {
                var $reload = $toolbar.find(".o_afg_btn_reload_periods");
                var $exportHtml = $(
                    '<label class="small mb-0 ml-2 mr-1 o_afg_export_depth_label">Report level</label>' +
                    '<select class="form-control form-control-sm d-inline-block o_afg_export_level" ' +
                    'style="width:26rem;vertical-align:middle;background:#0f172a;border-color:#475569;color:#e2e8f0;">' +
                    '<option value="1">L1 — Official (FTA / banks)</option>' +
                    '<option value="5">L1 — Official (FTA / Bank) — Arabic Version</option>' +
                    '<option value="2">L2 — Management (with Type)</option>' +
                    '<option value="3" selected="selected">L3 — Detailed (with Group)</option>' +
                    '<option value="4">L4 — Working Papers</option>' +
                    "</select>"
                );
                if ($reload.length) {
                    $reload.after($exportHtml);
                } else {
                    var $print = $toolbar.find(".o_afg_btn_print").first();
                    if ($print.length) {
                        $print.before($exportHtml);
                    } else {
                        $toolbar.append($exportHtml);
                    }
                }
            }
            this.$(".o_afg_btn_remove_group, .o_afg_btn_open_form, .o_afg_btn_toggle, .o_afg_btn_save, .o_afg_btn_print_simple, .o_afg_btn_toggle_codes").remove();
            // Drop legacy hierarchy options if old QWeb/cache still injected them.
            this.$(".o_afg_export_level option[value='0']").remove();
            // Keep value=5 as Arabic Official (do not treat as legacy depth)
            this.$(".o_afg_export_level option[value='2']").text("L2 — Management (with Type)");
            this.$(".o_afg_export_level option[value='3']").text("L3 — Detailed (with Group)");
            if (!this.$(".o_afg_export_level option[value='5']").length) {
                this.$(".o_afg_export_level option[value='1']").after(
                    '<option value="5">L1 — Official (FTA / Bank) — Arabic Version</option>'
                );
            } else {
                this.$(".o_afg_export_level option[value='5']").text(
                    "L1 — Official (FTA / Bank) — Arabic Version"
                );
            }
            // Non-UAE: keep L1 (official summary + schedules) only.
            if (this._afgTwoLevelOnly()) {
                this.$(".o_afg_export_level option").filter(function () {
                    return String(this.value) !== "1";
                }).remove();
                this.$(".o_afg_export_level option[value='1']").text("L1 — Official (summary with schedules)");
                var twoLvl = this._afgNormalizeDepth(this._viewMaxLevel);
                if (twoLvl !== this._viewMaxLevel) {
                    this._viewMaxLevel = twoLvl;
                    this._afgSaveDepth(twoLvl);
                    if (this.versionId) {
                        rpc.query({
                            model: "audited.financial.version",
                            method: "afg_dashboard_set_print_max_level",
                            args: [[this.versionId], twoLvl],
                            kwargs: {context: this._getRpcContext()},
                        });
                    }
                }
                this.$(".o_afg_export_level").val(String(this._viewMaxLevel));
            }
            this.$(".o_afg_btn_print_setup, .o_afg_page_setup, .o_afg_margin_header, .o_afg_margin_footer, .o_afg_btn_save_margins, .o_afg_btn_stop_empty_page").remove();
            this._loadSavedDpi();
            if ($toolbar.length && !this.$(".o_afg_btn_ct_master").length) {
                var $ct = $(
                    '<button type="button" class="btn btn-sm btn-primary o_afg_btn_ct_master">' +
                    'Export CT Master File</button>'
                );
                var $xlsx = $toolbar.find(".o_afg_btn_export_xlsx").first();
                if ($xlsx.length) {
                    $xlsx.before($ct);
                } else {
                    $toolbar.append($ct);
                }
            } else {
                this.$(".o_afg_btn_ct_master").text(_t("Export CT Master File"));
            }
            // Non-UAE: no UAE Corporate Tax master file export.
            if (this._afgTwoLevelOnly()) {
                this.$(".o_afg_btn_ct_master").remove();
            }
        },

        destroy: function () {
            if (this.$el) {
                this.$el.off(".afgRow");
            }
            this._afgCloseLedgerMenu();
            $("body").removeClass("o_afg_single_sidebar_shell");
            return this._super.apply(this, arguments);
        },

        _bindAfgRowClicks: function () {
            var self = this;
            if (!this.$el) {
                return;
            }
            this.$el.off(".afgRow");
            this.$el.on("contextmenu.afgRow", "tr[data-afg-level]", function (ev) {
                var $tr = $(this);
                if ($tr.hasClass("o_afg_map_ledger") || $tr.hasClass("o_afg_kind_ledger")
                        || $tr.hasClass("o_afg_under_ungrouped")) {
                    return self._onMapLedgerContext(ev);
                }
                if ($tr.hasClass("o_afg_map_group")) {
                    return self._onMapGroupContext(ev);
                }
            });
        },

        _toggleGroupRow: function ($tr) {
            var rid = String($tr.attr("data-line-id") || $tr.data("lineId") || $tr.data("line-id") || "");
            if (!rid) {
                return false;
            }
            var nextOpen = this._rootOpen[rid] !== true;
            this._rootOpen[rid] = nextOpen;
            this._rootForceLedger[rid] = nextOpen;
            this._applyRowTreeVisibility();
            return true;
        },

        _loadData: function () {
            var self = this;
            var ctx = this._getRpcContext();
            if (!this._afgFullLoad) {
                ctx.afg_dashboard_light = true;
            }
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_dashboard_data",
                args: [this.versionId || false],
                kwargs: {context: ctx},
            }).then(function (data) {
                self.data = data || {};
                self.versionId = data.version_id;
                if (data && data.error) {
                    var errMsg = data.empty_message || data.error;
                    self.$(".o_afg_empty").text(errMsg).show();
                    return;
                }
                // View/print depth: keep user choice across reload / report switch.
                // Never overwrite from server unless we have no local preference yet.
                if (!self._depthLoaded) {
                    var savedDepth = self._afgReadSavedDepth();
                    if (savedDepth !== null && savedDepth !== undefined) {
                        self._viewMaxLevel = savedDepth;
                    } else {
                        var serverLvl = parseInt(data.print_max_level, 10);
                        self._viewMaxLevel = self._afgNormalizeDepth(
                            !isNaN(serverLvl) ? serverLvl : 4
                        );
                    }
                    self._depthLoaded = true;
                    self._afgSaveDepth(self._viewMaxLevel);
                } else {
                    self._viewMaxLevel = self._afgNormalizeDepth(self._viewMaxLevel);
                }
                // Restore global Column order preference (all reports share one setting).
                // Never invent a flip on reload — only trust server after user toggle saved it.
                if (Object.prototype.hasOwnProperty.call(data, "print_years_descending")) {
                    self._yearsDescending = !!data.print_years_descending;
                    self._yearsOrderLoaded = true;
                }
                if (data.period_span) {
                    self._periodSpan = String(data.period_span);
                }
                var finOn = true;
                if (data && (data.print_financials === false || data.print_financials === 0 || data.print_financials === "0")) {
                    finOn = false;
                }
                self.$(".o_afg_print_financials").prop("checked", finOn);
                self._yearsDirty = false;
                self._internalActionNotes = data.internal_action_notes || "";
                self._renderChromeAndSection({resetYears: true});
                self._syncCodeToggleUi();
                self.$(".o_afg_export_level").val(String(self._viewMaxLevel));
                self._applyExportLevelToView(self._viewMaxLevel);
                if (data.print_page_setup) {
                    self.$(".o_afg_page_setup").val(String(data.print_page_setup));
                }
                if (data.print_page_setup_flags) {
                    self._afgApplyPageSetupFlags(data.print_page_setup_flags);
                }
            }).guardedCatch(function (err) {
                var msg = _t(
                    "Audited Financials module is not loaded. " +
                    "Install or upgrade module audited_financials, then restart Odoo and hard-refresh (Ctrl+F5)."
                );
                if (err && err.data && err.data.message) {
                    msg += " (" + err.data.message + ")";
                }
                self.$(".o_afg_empty").text(msg).show();
            });
        },

        _syncCodeToggleUi: function () {
            var root = this.$(".o_afg_root");
            root.toggleClass("o_afg_ledger_codes_off", !this._showCodes);
            root.toggleClass("o_afg_group_codes_off", !this._showCodes);
            this.$(".o_afg_btn_toggle_codes").text(
                this._showCodes ? _t("Hide code") : _t("Show code")
            );
        },

        _onToggleCodes: function (ev) {
            ev.preventDefault();
            this._showCodes = !this._showCodes;
            this._syncCodeToggleUi();
        },

        _onDrillJournal: function (ev) {
            if ($(ev.target).closest("input,button,a,.o_afg_caret").length) {
                return;
            }
            if (
                !$(ev.currentTarget).hasClass("o_afg_ungrouped_reassign") &&
                $(ev.target).closest(".o_afg_l0_toggle,.o_afg_l1_toggle").length
            ) {
                return;
            }
            var self = this;
            if (!this.versionId) {
                return;
            }
            var $tr = $(ev.currentTarget);
            if ($tr.hasClass("o_afg_l1_row")
                    && !$(ev.target).closest(".o_afg_amt_cell, td.text-right").length) {
                this._toggleGroupRow($tr);
                return;
            }
            if ($tr.hasClass("o_afg_map_group")
                    && !$(ev.target).closest(".o_afg_amt_cell, td.text-right").length) {
                this._toggleGroupRow($tr);
                return;
            }
            if ($tr.hasClass("o_afg_kind_ledger") || $tr.hasClass("o_afg_map_ledger")) {
                return;
            }
            var payload = {};
            var acc = $tr.data("afgDrillAccountId");
            if (acc) {
                payload.account_id = acc;
                payload.l3_line_id = $tr.data("afgDrillL3LineId");
                payload.branch_company_id = $tr.data("afgDrillCompanyId");
            } else {
                payload.line_id = $tr.data("afgDrillLineId");
            }
            if (!payload.line_id && !payload.account_id) {
                return;
            }
            var rawIds = $tr.attr("data-afg-account-ids") || "";
            if (rawIds) {
                payload.account_ids = rawIds.split(",").map(function (part) {
                    return parseInt(part, 10);
                }).filter(function (n) { return !isNaN(n); });
            }
            payload.section = this.section;
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_open_vouchers",
                args: [[this.versionId], payload],
                kwargs: {context: ctx},
            }).then(function (action) {
                if (action) {
                    self.do_action(action, {
                        clear_breadcrumbs: false,
                    });
                }
            }).guardedCatch(function (err) {
                var msg = err && err.message && err.message.data && err.message.data.message;
                if (msg) {
                    window.alert(msg);
                }
            });
        },

        _onMapGroupContext: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var $tr = $(ev.currentTarget);
            var gid = $tr.attr("data-afg-group-id") || $tr.data("afgGroupId");
            var cat = $tr.attr("data-afg-ctf-category") || $tr.data("afgCtfCategory");
            if (!this.versionId) {
                return;
            }
            var payload = {};
            if (gid) {
                payload.group_id = parseInt(gid, 10);
            }
            if (cat) {
                payload.ctf_category = cat;
            }
            var self = this;
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_open_group_ledgers",
                args: [[this.versionId], payload],
                kwargs: {context: ctx},
            }).then(function (action) {
                if (action) {
                    self.do_action(action, {clear_breadcrumbs: false});
                }
            }).guardedCatch(function (err) {
                var msg = err && err.message && err.message.data && err.message.data.message;
                if (msg) {
                    window.alert(msg);
                }
            });
        },

        _onMapLedgerContext: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            this._afgShowLedgerMenu(ev, $(ev.currentTarget));
        },

        _afgCloseLedgerMenu: function () {
            if (this._afgLedgerMenu) {
                this._afgLedgerMenu.remove();
                this._afgLedgerMenu = null;
            }
            $(document).off(".afgLedgerMenu");
        },

        _afgLedgerPayload: function ($tr) {
            var payload = {section: this.section};
            var acc = $tr.data("afgDrillAccountId") || $tr.attr("data-afg-account-id");
            if (acc) {
                payload.account_id = parseInt(acc, 10);
                payload.l3_line_id = $tr.data("afgDrillL3LineId");
                payload.branch_company_id = $tr.data("afgDrillCompanyId");
            } else {
                payload.line_id = $tr.data("afgDrillLineId");
            }
            var rawIds = $tr.attr("data-afg-account-ids") || "";
            if (rawIds && rawIds.charAt(0) !== "[") {
                payload.account_ids = rawIds.split(",").map(function (part) {
                    return parseInt(part, 10);
                }).filter(function (n) { return !isNaN(n); });
            }
            return payload;
        },

        _afgOpenLedgerAction: function (method, payload) {
            var self = this;
            if (!this.versionId) {
                return;
            }
            return rpc.query({
                model: "audited.financial.version",
                method: method,
                args: [[this.versionId], payload || {}],
                kwargs: {context: this._getRpcContext()},
            }).then(function (action) {
                if (action) {
                    self.do_action(action, {clear_breadcrumbs: false});
                }
            }).guardedCatch(function (err) {
                var msg = err && err.message && err.message.data && err.message.data.message;
                if (msg) {
                    window.alert(msg);
                }
            });
        },

        _afgShowLedgerMenu: function (ev, $tr) {
            var self = this;
            this._afgCloseLedgerMenu();
            var $menu = $("<div class='o_afg_ledger_menu'/>").css({
                position: "fixed",
                zIndex: 2000,
                left: ev.clientX + "px",
                top: ev.clientY + "px",
                background: "#fff",
                color: "#212529",
                border: "1px solid #c8c8c8",
                minWidth: "190px",
                boxShadow: "0 2px 8px rgba(0,0,0,.18)",
                padding: "4px 0",
            });
            var items = [
                {label: _t("Show Vouchers"), fold: "vouchers"},
                {label: _t("Show Monthly"), fold: "monthly"},
                {label: _t("Show Yearly"), fold: "yearly"},
                {label: _t("Show Branch Wise"), fold: "vouchers", branch: true},
                {label: _t("Journal Items"), journal: true},
                {label: _t("Modify Ledger"), coa: true},
            ];
            items.forEach(function (item) {
                var $a = $("<a href='#'/>").text(item.label).css({
                    display: "block",
                    padding: "6px 14px",
                    color: "#212529",
                    textDecoration: "none",
                });
                $a.on("mouseenter", function () { $a.css("background", "#f0f4f8"); });
                $a.on("mouseleave", function () { $a.css("background", "#fff"); });
                $a.on("click", function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    self._afgCloseLedgerMenu();
                    if (item.coa) {
                        self._openCoaForLedger($tr);
                        return;
                    }
                    var payload = self._afgLedgerPayload($tr);
                    if (item.journal) {
                        self._afgOpenLedgerAction("afg_open_journal_items", payload);
                        return;
                    }
                    payload.fold_mode = item.fold;
                    payload.branch_wise = !!item.branch;
                    self._afgOpenLedgerAction("afg_open_vouchers", payload);
                });
                $menu.append($a);
            });
            $("body").append($menu);
            this._afgLedgerMenu = $menu;
            setTimeout(function () {
                $(document).on("click.afgLedgerMenu contextmenu.afgLedgerMenu", function () {
                    self._afgCloseLedgerMenu();
                });
            }, 0);
        },

        _onUngroupedLedgerContext: function (ev) {
            return this._onMapLedgerContext(ev);
        },

        _openCoaForLedger: function ($tr) {
            var self = this;
            var acc = $tr.data("afgDrillAccountId") || $tr.attr("data-afg-account-id");
            if (!acc) {
                try {
                    var ids = JSON.parse($tr.attr("data-afg-account-ids") || "[]");
                    if (ids && ids.length) {
                        acc = ids[0];
                    }
                } catch (e) {
                    acc = null;
                }
            }
            if (!acc || !this.versionId) {
                return this._openUngroupedReassign($tr, []);
            }
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_open_coa_form",
                args: [[this.versionId], {account_id: parseInt(acc, 10)}],
                kwargs: {context: ctx},
            }).then(function (action) {
                if (action) {
                    self.do_action(action, {clear_breadcrumbs: false});
                }
            }).guardedCatch(function (err) {
                var msg = err && err.message && err.message.data && err.message.data.message;
                if (msg) {
                    window.alert(msg);
                }
            });
        },

        _openUngroupedReassign: function ($tr, accIds) {
            var self = this;
            if (!this.versionId) {
                return;
            }
            accIds = accIds || [];
            if (!accIds.length) {
                try {
                    accIds = JSON.parse($tr.attr("data-afg-account-ids") || "[]");
                } catch (e) {
                    accIds = [];
                }
            }
            var code = $tr.attr("data-afg-ungrouped-code") || "AFG_UNGRP_BS";
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_open_ungrouped_reassign",
                args: [[this.versionId], {
                    account_ids: accIds,
                    ungrouped_code: code,
                }],
                kwargs: {context: ctx},
            }).then(function (action) {
                if (action) {
                    self.do_action(action, {clear_breadcrumbs: false});
                }
            }).guardedCatch(function (err) {
                var msg = err && err.message && err.message.data && err.message.data.message;
                if (msg) {
                    window.alert(msg);
                }
            });
        },

        _fmt: function (v) {
            if (v === undefined || v === null) { return "-"; }
            var n = Number(v);
            if (isNaN(n)) { return "-"; }
            if (Math.abs(n) < 0.005) { return "-"; }
            var abs = Math.abs(n).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            });
            // Accounting style: losses / credits shown in parentheses
            return n < 0 ? "(" + abs + ")" : abs;
        },

        _afgAlertFlags: function (line, yearsDesc) {
            var flags = [];
            if (line && line.ct_check && line.ct_check.length) {
                flags = line.ct_check.slice();
            } else if (line && line.pl_match && line.pl_match.length) {
                flags = line.pl_match.slice();
            }
            if (yearsDesc && flags.length > 1) {
                flags = flags.slice().reverse();
            }
            return flags;
        },

        _afgStatementAmtCell: function (v, flag, extraClass) {
            var text = flag === "error" ? "Error" : this._fmt(v);
            var cell = $("<td class='text-right o_afg_amt_cell'/>").text(text);
            if (extraClass) {
                cell.addClass(extraClass);
            }
            if (flag === "bad" || flag === "error") {
                cell.addClass("o_afg_amt_alert");
            }
            return cell;
        },

        /**
         * Trial Balance face amount by account nature (debit−credit signed in):
         * Asset/Expense normal = debit (+); Liability/Equity/Income normal = credit.
         * Display always as unsigned magnitude; opposite nature → leading "-" (red).
         */
        _tbNatureFace: function (signed, internalGroup) {
            var n = Number(signed);
            if (isNaN(n)) {
                return 0;
            }
            var ig = String(internalGroup || "asset").toLowerCase();
            if (ig === "liability" || ig === "equity" || ig === "income") {
                return -n;
            }
            return n;
        },

        _fmtTbNature: function (signed, internalGroup) {
            var face = this._tbNatureFace(signed, internalGroup);
            if (Math.abs(face) < 0.005) {
                return {text: "—", neg: false};
            }
            var abs = Math.abs(face).toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            });
            if (face < 0) {
                return {text: "-" + abs, neg: true};
            }
            return {text: abs, neg: false};
        },

        _tbLineNatureKey: function (line) {
            if (!line) {
                return "asset";
            }
            if (line.internal_group) {
                return String(line.internal_group);
            }
            var tk = String(line.type_key || "");
            if (tk === "asset" || tk === "liability" || tk === "equity" ||
                    tk === "income" || tk === "expense") {
                return tk;
            }
            if (tk === "sales" || tk === "other_income") {
                return "income";
            }
            if (tk === "expenses" || tk === "cost_of_revenue" || tk === "cogs") {
                return "expense";
            }
            return "asset";
        },

        _appendTbAmtCell: function (tr, signed, natureKey, bold) {
            var fmt = this._fmtTbNature(signed, natureKey);
            var cell = $("<td class='text-right small o_afg_amt_cell'/>").text(fmt.text);
            if (fmt.neg) {
                cell.addClass("o_afg_tb_nature_neg");
            }
            if (bold) {
                cell.addClass("font-weight-bold");
            }
            tr.append(cell);
        },

        /** Hide ledger / company rows with zero in both year columns (dashboard display). */
        _lineHasBalance: function (line, d) {
            if (d.trial_balance && d.trial_balance.five_column && line.tb_amounts && line.tb_amounts.length) {
                return line.tb_amounts.some(function (v) {
                    var n = Number(v);
                    return !isNaN(n) && Math.abs(n) > 1e-9;
                });
            }
            var hideAud = !!d.statement_hide_audited_totals;
            var nCo = (d.company_columns || []).length;
            var p = line.prior;
            var c = line.current;
            if (hideAud && nCo === 1 && line.co_prior && line.co_prior.length && line.co_curr && line.co_curr.length) {
                p = line.co_prior[0];
                c = line.co_curr[0];
            }
            var np = Number(p);
            var nc = Number(c);
            if (isNaN(np)) { np = 0; }
            if (isNaN(nc)) { nc = 0; }
            return Math.abs(np) > 1e-9 || Math.abs(nc) > 1e-9;
        },

        /** Full re-render: after RPC reload. options.resetYears forces Prior/Current from server. */
        _renderChromeAndSection: function (options) {
            options = options || {};
            var d = this.data;
            this._ensureExportToolbarControls();
            this.set("title", _t("Financial Statements"));
            this.$(".o_afg_company").text("");
            this.$(".o_afg_period").text(
                this._yearsDescending
                    ? ((d.period_label_current || d.year_current || "") + " / " + (d.period_label_prior || d.year_prior || ""))
                    : ((d.period_label_prior || d.year_prior || "") + " / " + (d.period_label_current || d.year_current || ""))
            );
            this._syncYearOrderButton();
            this.$(".o_afg_curr").text(" — " + (d.currency || "AED"));
            // Corporate Tax Filing (FTA) is UAE-only: hide it for non-AED companies.
            this.$('.o_afg_nav li[data-section="fta"]').toggleClass("d-none", (d.currency || "AED") !== "AED");
            this.$(".o_afg_state").text(d.state || "draft");
            var ds = d.data_state || "";
            this.$(".o_afg_data_state").text(ds).toggleClass("d-none", !ds);
            if (d.empty_message) {
                this.$(".o_afg_empty").text(d.empty_message).show();
            } else {
                this.$(".o_afg_empty").hide().text("");
            }
            this._renderPeriodPresets(d);
            this._syncLevelButtons();
            this._renderSectionNavOnly();
        },

        _periodLabelPrior: function (d) {
            d = d || this.data || {};
            return d.period_label_prior || d.year_prior || "";
        },

        _periodLabelCurrent: function (d) {
            d = d || this.data || {};
            return d.period_label_current || d.year_current || "";
        },

        _renderPeriodPresets: function (d) {
            var self = this;
            var $host = this.$(".o_afg_period_presets");
            if (!$host.length) {
                return;
            }
            $host.empty();
            var active = (d && d.period_preset) || "years";
            var presets = (d && d.period_presets) || [];
            if (!presets.length) {
                presets = [
                    {key: "years", title: _t("Last 2 years"), hint: _t("Full calendar years (default)"), caption: "", is_default: true},
                    {key: "mom", title: _t("Last 2 months"), hint: _t("Last month vs month before"), caption: "", is_default: false},
                    {key: "yoy_month", title: _t("Same month YoY"), hint: _t("Last month vs same month last year"), caption: "", is_default: false},
                    {key: "custom", title: _t("Custom period"), hint: _t("Choose prior & current date ranges"), caption: _t("Pick dates…"), is_default: false},
                ];
            }
            presets.forEach(function (p) {
                var $card = $("<button type='button' class='o_afg_period_card'/>")
                    .attr("data-preset", p.key || "")
                    .toggleClass("o_afg_period_card_active", String(p.key) === String(active))
                    .toggleClass("o_afg_period_card_default", !!p.is_default);
                $card.append($("<div class='o_afg_period_card_title'/>").text(p.title || p.key || ""));
                $card.append($("<div class='o_afg_period_card_caption'/>").text(p.caption || ""));
                $card.append($("<div class='o_afg_period_card_hint'/>").text(p.hint || ""));
                if (p.is_default) {
                    $card.append($("<span class='o_afg_period_card_badge'/>").text(_t("Default")));
                }
                $host.append($card);
            });
            // Column order control sits with period cards (always visible).
            var $order = $("<button type='button' class='o_afg_period_card o_afg_btn_year_order o_afg_column_order_card'/>");
            $order.append($("<div class='o_afg_period_card_title'/>").text(
                self._yearsDescending ? _t("Column descending") : _t("Column ascending")
            ));
            $order.append($("<div class='o_afg_period_card_caption'/>").text(
                self._yearsDescending
                    ? ((d && (d.period_label_current || d.year_current)) || "") + " → " + ((d && (d.period_label_prior || d.year_prior)) || "")
                    : ((d && (d.period_label_prior || d.year_prior)) || "") + " → " + ((d && (d.period_label_current || d.year_current)) || "")
            ));
            $order.append($("<div class='o_afg_period_card_hint'/>").text(
                _t("Toggle statement column order")
            ));
            $host.append($order);
            self._syncYearOrderButton();

            // Show N years / months (right of Column ascending)
            var span = (d && d.period_span) || self._periodSpan || "2y";
            self._periodSpan = span;
            var spanLabel = (d && d.period_span_label) || span;
            var spanOpts = (d && d.period_spans) || [];
            var $spanCard = $("<div class='o_afg_period_card o_afg_period_span_card'/>");
            $spanCard.append($("<div class='o_afg_period_card_title'/>").text(_t("Show periods")));
            var labs = (d && d.period_labels) || [];
            var cap = labs.length ? labs.join(" → ") : spanLabel;
            $spanCard.append($("<div class='o_afg_period_card_caption'/>").text(cap));
            $spanCard.append($("<div class='o_afg_period_card_hint'/>").text(
                _t("1–5 years or 1–4 months")
            ));
            var $sel = $("<select class='o_afg_period_span_select form-control form-control-sm mt-1'/>");
            if (!spanOpts.length) {
                spanOpts = [
                    {key: "1y", title: _t("1 year")},
                    {key: "2y", title: _t("2 years"), is_default: true},
                    {key: "3y", title: _t("3 years")},
                    {key: "4y", title: _t("4 years")},
                    {key: "5y", title: _t("5 years")},
                    {key: "1m", title: _t("1 month")},
                    {key: "2m", title: _t("2 months")},
                    {key: "3m", title: _t("3 months")},
                    {key: "4m", title: _t("4 months")},
                ];
            }
            spanOpts.forEach(function (opt) {
                $sel.append(
                    $("<option/>")
                        .attr("value", opt.key || "")
                        .prop("selected", String(opt.key) === String(span))
                        .text(opt.title || opt.key || "")
                );
            });
            $spanCard.append($sel);
            $host.append($spanCard);

            self._fillCustomPeriodInputs(d);
            var $panel = self.$(".o_afg_custom_period_panel");
            if ($panel.length) {
                $panel.toggle(String(active) === "custom" || !!self._customPeriodOpen);
            }
        },

        _fillCustomPeriodInputs: function (d) {
            d = d || this.data || {};
            var map = {
                ".o_afg_custom_dfp": d.date_from_prior,
                ".o_afg_custom_dtp": d.date_to_prior,
                ".o_afg_custom_dfc": d.date_from_current,
                ".o_afg_custom_dtc": d.date_to_current,
            };
            Object.keys(map).forEach(function (sel) {
                var $inp = this.$(sel);
                if ($inp.length && map[sel]) {
                    $inp.val(String(map[sel]).slice(0, 10));
                }
            }.bind(this));
        },

        _onPeriodPresetClick: function (ev) {
            if (ev) {
                ev.preventDefault();
            }
            var self = this;
            var $card = $(ev.currentTarget);
            if ($card.hasClass("o_afg_btn_year_order") || $card.hasClass("o_afg_period_span_card")) {
                return;
            }
            var preset = $card.data("preset");
            if (!preset || !this.versionId) {
                return;
            }
            if (String(preset) === "custom") {
                this._customPeriodOpen = true;
                this.$(".o_afg_custom_period_panel").show();
                this._fillCustomPeriodInputs(this.data);
                this.$(".o_afg_period_card").removeClass("o_afg_period_card_active");
                $card.addClass("o_afg_period_card_active");
                return;
            }
            this._customPeriodOpen = false;
            this.$(".o_afg_custom_period_panel").hide();
            if (String(preset) === String((this.data || {}).period_preset || "years")) {
                return;
            }
            var $cards = this.$(".o_afg_period_card").not(".o_afg_btn_year_order").prop("disabled", true);
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_dashboard_apply_period_preset",
                args: [[this.versionId]],
                kwargs: {
                    preset: preset,
                    context: ctx,
                },
            }).then(function (res) {
                if (res && res.empty) {
                    window.alert(_t(
                        "Period applied (%s / %s), but no posted journals were found in that window."
                    ).replace("%s", String(res.period_label_prior || res.year_prior || ""))
                     .replace("%s", String(res.period_label_current || res.year_current || "")));
                }
                return self._loadData();
            }).guardedCatch(function (err) {
                var msg = err && err.message && err.message.data && err.message.data.message;
                if (!msg && err && err.data && err.data.message) {
                    msg = err.data.message;
                }
                window.alert(msg || _t("Could not apply period. Try again."));
            }).then(function () {
                $cards.prop("disabled", false);
            }, function () {
                $cards.prop("disabled", false);
            });
        },

        _onApplyCustomPeriod: function (ev) {
            if (ev) {
                ev.preventDefault();
            }
            var self = this;
            if (!this.versionId) {
                return;
            }
            var dfp = this.$(".o_afg_custom_dfp").val();
            var dtp = this.$(".o_afg_custom_dtp").val();
            var dfc = this.$(".o_afg_custom_dfc").val();
            var dtc = this.$(".o_afg_custom_dtc").val();
            if (!dfp || !dtp || !dfc || !dtc) {
                window.alert(_t("Enter all four custom period dates."));
                return;
            }
            var $btn = this.$(".o_afg_btn_apply_custom").prop("disabled", true);
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_dashboard_apply_custom_period",
                args: [[this.versionId]],
                kwargs: {
                    date_from_prior: dfp,
                    date_to_prior: dtp,
                    date_from_current: dfc,
                    date_to_current: dtc,
                    context: ctx,
                },
            }).then(function (res) {
                self._customPeriodOpen = true;
                if (res && res.empty) {
                    window.alert(_t(
                        "Custom period applied (%s / %s), but no posted journals were found in that window."
                    ).replace("%s", String(res.period_label_prior || ""))
                     .replace("%s", String(res.period_label_current || "")));
                }
                return self._loadData();
            }).guardedCatch(function (err) {
                var msg = err && err.message && err.message.data && err.message.data.message;
                if (!msg && err && err.data && err.data.message) {
                    msg = err.data.message;
                }
                window.alert(msg || _t("Could not apply custom period. Try again."));
            }).then(function () {
                $btn.prop("disabled", false);
            }, function () {
                $btn.prop("disabled", false);
            });
        },

        _onYearInputDirty: function () {
            this._yearsDirty = true;
        },

        _onYearInputKeydown: function (ev) {
            if (ev && (ev.key === "Enter" || ev.keyCode === 13)) {
                ev.preventDefault();
                this._onApplyYears(ev);
            }
        },

        /** Fast path: sidebar + main section only (same cached data). */
        _renderSectionNavOnly: function () {
            this.$(".o_afg_nav li").removeClass("active");
            this.$('.o_afg_nav li[data-section="' + this.section + '"]').addClass("active");
            this._renderSection(this.section);
        },

        _isStatementSection: function (section) {
            var s = section || this.section;
            if (s === "tb_x" || s === "notes" || s === "review") {
                return false;
            }
            var fallback = ["pl", "bs", "equity", "cashflow", "fixed_assets", "tb", "fta"];
            var raw = this.data && this.data.statement_sections;
            var list = fallback;
            if (Array.isArray(raw) && raw.length) {
                list = raw;
            } else if (raw && typeof raw === "object" && Object.keys(raw).length) {
                list = Object.keys(raw);
            }
            return list.indexOf(s) >= 0;
        },

        _tbPayloadForSection: function (section) {
            if (section === "tb_x") {
                return this.data.trial_balance || {};
            }
            // Prefer TB2 = full CoA (Accounting Trial Balance parity)
            return this.data.trial_balance2 || this.data.trial_balance || {};
        },

        _collectLinesForExpansion: function () {
            var section = this.section;
            if (section === "tb" || section === "tb_x") {
                var tb = this._tbPayloadForSection(section);
                var lines = [];
                (tb.panels || []).forEach(function (panel) {
                    (panel.roots || []).forEach(function (r) {
                        lines.push(r);
                    });
                });
                if (!lines.length) {
                    lines = tb.roots || [];
                }
                return lines;
            }
            return (this.data.sections && this.data.sections[section]) || [];
        },

        _applyExportLevelToView: function (maxLevel) {
            var pack = this._afgNormalizeReportPack(maxLevel);
            this._viewMaxLevel = pack;
            var spec = this._afgPackSpec();
            this._hideLgColumn = !!spec.hide_lg;
            this._hideHashColumn = !!spec.hide_hash;
            // L1 Official (+ Arabic): type + AFG (no ledgers / no account.group)
            // L2 Management (with Type): type → ledger (no AFG / no account.group)
            // L3 Detailed (with Group): AFG → account.group → ledger (no CoA type)
            // L4 Working Papers: AFG → ledger (no CoA type / no account.group)
            var hp = pack === 5 ? 1 : pack;
            if (hp <= 1) {
                this._applyGlobalExpansion("afg");
                this._hideL0Globally = false;
                this._hideL1Globally = false;
                this._hideAccountGroups = true;
                this._hideLedgersPack = true;
            } else if (hp === 2) {
                this._applyGlobalExpansion("ledger");
                this._hideL0Globally = false;
                this._hideL1Globally = true;
                this._hideAccountGroups = true;
                this._hideLedgersPack = false;
            } else if (hp === 3) {
                this._applyGlobalExpansion("ledger");
                this._hideL0Globally = true;
                this._hideL1Globally = false;
                this._hideAccountGroups = false;
                this._hideLedgersPack = false;
            } else {
                this._applyGlobalExpansion("ledger");
                this._hideL0Globally = true;
                this._hideL1Globally = false;
                this._hideAccountGroups = true;
                this._hideLedgersPack = false;
            }
            this.$(".o_afg_btn_print_fta").toggle(this.section === "fta");
            this.$(".o_afg_btn_merge_ledger").toggle(!spec.hide_merge_ledger);
            var $overview = this.$(".o_afg_nav li").filter(function () {
                return $(this).text().replace(/\s+/g, " ").trim() === "Overview";
            }).first();
            if ($overview.length && !this.$(".o_afg_nav [data-section='report_text']").length) {
                $overview.after(
                    "<li class='list-group-item' data-section='report_text'><a href='#'>Word File Texts</a></li>"
                );
            }
            if (!this.$(".o_afg_btn_multco").length) {
                this.$(".o_afg_btn_merge_ledger").after(
                    $("<button type='button' class='btn btn-sm btn-secondary ml-2 o_afg_btn_multco' title='Show each company under the ledger'/>").text("Multco")
                );
            }
            if (!this.$(".o_afg_btn_print_page").length) {
                this.$(".o_afg_btn_multco").after(
                    $("<button type='button' class='btn btn-sm btn-primary ml-2 o_afg_btn_print_page'/>").text("Print"),
                    $("<button type='button' class='btn btn-sm btn-primary ml-2 o_afg_btn_pdf_page'/>").text("PDF"),
                    $("<button type='button' class='btn btn-sm btn-primary ml-2 o_afg_btn_excel_page'/>").text("Excel")
                );
            }
            this.$(".o_afg_nav_tb").toggle(!!spec.show_tb);
            this.$(".o_afg_root").toggleClass("o_afg_pack_official", hp === 1);
            this.$(".o_afg_root").toggleClass("o_afg_pack_management", hp === 2);
            this.$(".o_afg_root").toggleClass("o_afg_pack_arabic", pack === 5);
            this.$(".o_afg_root").attr("data-afg-report-level", String(pack));
            // SOFP, Income and Corporate Tax open on the face lines.
            // A click expands the ledgers under that line.
            if (this.section === "bs" || this.section === "pl" || this.section === "fta") {
                this._applyGlobalExpansion("afg");
                this._hideLedgersPack = true;
                this._hideL3Globally = true;
                this._hideL0Globally = false;
                this._hideL1Globally = false;
            }
            // If current section not allowed, jump to P&L
            if (this.section === "tb" || this.section === "tb_x") {
                if (!spec.show_tb) {
                    this.section = "pl";
                }
            }
            this._applyRowTreeVisibility();
            this._applyPackColumnVisibility();
        },

        _applyPackColumnVisibility: function () {
            var hideLg = !!this._hideLgColumn;
            var hideHash = !!this._hideHashColumn;
            // Never use :first-child — when # is omitted from rows, Description becomes first td.
            this.$(".o_afg_th_lg, .o_afg_cell_lg").toggle(!hideLg);
            this.$(".o_afg_th_hash, .o_afg_cell_num").toggle(!hideHash);
            if (hideLg) {
                this.$(".o_afg_table").addClass("o_afg_hide_lg");
            } else {
                this.$(".o_afg_table").removeClass("o_afg_hide_lg");
            }
        },

        _onExportLevelChange: function () {
            var maxLevel = this._afgNormalizeDepth(this.$(".o_afg_export_level").val());
            this._afgSaveDepth(maxLevel);
            this._applyExportLevelToView(maxLevel);
            this.$(".o_afg_export_level").val(String(maxLevel));
            // Persist for PDF/Excel/Word — only when the user changes depth.
            if (this.versionId) {
                var ctx = this._getRpcContext();
                rpc.query({
                    model: "audited.financial.version",
                    method: "afg_dashboard_set_print_max_level",
                    args: [[this.versionId], maxLevel],
                    kwargs: {context: ctx},
                });
            }
        },

        _onPageSetupChange: function () {
            var mode = (this.$(".o_afg_page_setup").val() || "default").toString();
            if (!this.versionId) {
                return;
            }
            var self = this;
            var ctx = this._getRpcContext();
            var mh = parseInt(this.$(".o_afg_margin_header").val(), 10);
            var mf = parseInt(this.$(".o_afg_margin_footer").val(), 10);
            rpc.query({
                model: "audited.financial.version",
                method: "afg_dashboard_set_page_setup",
                args: [[this.versionId], mode],
                kwargs: {
                    context: ctx,
                    margin_header: isNaN(mh) ? null : mh,
                    margin_footer: isNaN(mf) ? null : mf,
                },
            }).then(function (res) {
                self._afgApplyPageSetupFlags(res);
                window.alert(_t("Page setup saved. Re-print PDF to apply."));
            });
        },

        _onSavePageMargins: function () {
            if (!this.versionId) {
                return;
            }
            var self = this;
            var ctx = this._getRpcContext();
            var mode = (this.$(".o_afg_page_setup").val() || "default").toString();
            var mh = parseInt(this.$(".o_afg_margin_header").val(), 10);
            var mf = parseInt(this.$(".o_afg_margin_footer").val(), 10);
            if (isNaN(mh)) {
                mh = 10;
            }
            if (isNaN(mf)) {
                mf = 10;
            }
            rpc.query({
                model: "audited.financial.version",
                method: "afg_dashboard_set_page_setup",
                args: [[this.versionId], mode],
                kwargs: {
                    context: ctx,
                    margin_header: mh,
                    margin_footer: mf,
                },
            }).then(function (res) {
                self._afgApplyPageSetupFlags(res);
                window.alert(_t("Header/footer margins saved (mm → paperformat). Re-print PDF (Ctrl+F5)."));
            });
        },

        _afgApplyPageSetupFlags: function (res) {
            if (!res) {
                return;
            }
            if (res.print_page_setup) {
                this.$(".o_afg_page_setup").val(String(res.print_page_setup));
            }
            if (res.margin_header !== undefined && res.margin_header !== null) {
                this.$(".o_afg_margin_header").val(String(res.margin_header));
            }
            if (res.margin_footer !== undefined && res.margin_footer !== null) {
                this.$(".o_afg_margin_footer").val(String(res.margin_footer));
            }
        },

        _onStopPrintEmptyPage: function () {
            if (!this.versionId) {
                return;
            }
            var self = this;
            var ctx = this._getRpcContext();
            rpc.query({
                model: "audited.financial.version",
                method: "afg_dashboard_stop_print_empty_page",
                args: [[this.versionId]],
                kwargs: {context: ctx},
            }).then(function (res) {
                self._afgApplyPageSetupFlags(res);
                var msg = (res && res.message) || _t("Empty / signature-only pages will be skipped on next print.");
                if (res && res.empty_titles && res.empty_titles.length) {
                    msg += "\n" + res.empty_titles.slice(0, 8).join("\n");
                }
                window.alert(msg);
            });
        },

        _tbIsStatementStyleRoots: function (roots) {
            return (roots || []).some(function (r) {
                var tk = String(r.type_key || "");
                var lbl = String(r.label || "");
                return tk === "pl" || tk === "bs" || lbl.indexOf("Statement of Profit") >= 0
                    || lbl.indexOf("Statement of Financial Position") >= 0;
            });
        },

        _collectAfgRootIds: function (lines, out) {
            out = out || [];
            (lines || []).forEach(function (ln) {
                var lvl = ln.level || 1;
                var lid = String(ln.id || "");
                if (lvl === 1 && typeof ln.id === "number") {
                    out.push(ln.id);
                } else if (lvl === 1 && lid.indexOf("tb-gr-") === 0) {
                    out.push(ln.id);
                }
                if (ln.children && ln.children.length) {
                    this._collectAfgRootIds(ln.children, out);
                }
            }, this);
            return out;
        },

        _collectTypeIds: function (lines, out) {
            out = out || [];
            (lines || []).forEach(function (ln) {
                if ((ln.level || 0) === 0 && ln.id) {
                    out.push(ln.id);
                }
                if (ln.children && ln.children.length) {
                    this._collectTypeIds(ln.children, out);
                }
            }, this);
            return out;
        },

        _applyGlobalExpansion: function (mode) {
            this._detailLevel = mode;
            this._rootForceLedger = {};
            var lines = this._collectLinesForExpansion();
            var self = this;
            this._collectTypeIds(lines).forEach(function (tid) {
                self._typeOpen[tid] = true;
            });
            if (mode === "afg") {
                this._hideL3Globally = true;
                this._hideL4Globally = true;
                this._collectAfgRootIds(lines).forEach(function (rid) {
                    self._rootOpen[rid] = false;
                });
            } else if (mode === "group") {
                this._hideL3Globally = true;
                this._hideL4Globally = true;
                this._collectAfgRootIds(lines).forEach(function (rid) {
                    self._rootOpen[rid] = true;
                });
            } else if (mode === "ledger") {
                this._hideL3Globally = false;
                this._hideL4Globally = true;
                this._collectAfgRootIds(lines).forEach(function (rid) {
                    self._rootOpen[rid] = true;
                });
            } else if (mode === "company" || mode === "journal") {
                this._hideL3Globally = false;
                this._hideL4Globally = false;
                this._collectAfgRootIds(lines).forEach(function (rid) {
                    self._rootOpen[rid] = true;
                });
            }
            this.$(".o_afg_root").toggleClass("o_afg_mode_journal", mode === "journal");
            this._syncLevelButtons();
            this._applyRowTreeVisibility();
        },

        _applyRowTreeVisibility: function () {
            var self = this;
            var $tb = this.$(".o_afg_table tbody");
            if (!$tb.length) { return; }
            if (this.section === "fta") {
                $tb.find("tr[data-afg-level]").each(function () {
                    var $tr = $(this);
                    var lvl = parseInt($tr.attr("data-afg-level"), 10);
                    if (isNaN(lvl) || lvl <= 2) {
                        $tr.removeClass("d-none");
                        return;
                    }
                    var rid = String($tr.attr("data-afg-under-root") || "");
                    var open = !rid || self._rootOpen[rid] === true;
                    $tr.toggleClass("d-none", !open);
                });
                $tb.find("tr.o_afg_l0_row").each(function () {
                    var $tr = $(this);
                    var tid = $tr.data("afg-type-id");
                    var open = self._typeOpen[tid] !== false;
                    $tr.find(".o_afg_caret").first().text(open ? "▾" : "▸");
                });
                $tb.find("tr.o_afg_l1_row").each(function () {
                    var $tr = $(this);
                    var rid = String($tr.attr("data-line-id") || "");
                    var open = self._rootOpen[rid] === true;
                    $tr.find(".o_afg_caret").first().text(open ? "▾" : "▸");
                });
                return;
            }
            $tb.find("tr[data-afg-level]").each(function () {
                var $tr = $(this);
                var lvl = parseInt($tr.attr("data-afg-level"), 10);
                if (isNaN(lvl)) {
                    return;
                }
                if (lvl === 0) {
                    if (self._hideL0Globally) {
                        // Keep computed / grand-total type rows; hide CoA type buckets.
                        var keepL0 = !!$tr.data("afgComputed") || $tr.hasClass("o_afg_tb_section_total")
                            || $tr.hasClass("o_afg_tb_difference");
                        $tr.toggleClass("d-none", !keepL0);
                    }
                    return;
                }
                var typeId = $tr.data("afgUnderType");
                var rid = $tr.attr("data-afg-under-root");
                if (rid === undefined || rid === null || rid === "") {
                    rid = $tr.data("afgUnderRoot");
                }
                rid = rid === undefined || rid === null ? "" : String(rid);
                var typeOpen = !typeId || self._typeOpen[typeId] !== false;
                // When L0 types are hidden, still show L1/ledgers under those types.
                if (self._hideL0Globally) {
                    typeOpen = true;
                }
                var afgOpen = !rid || self._rootOpen[rid] === true;
                // When AFG bands are hidden (L2 Type→ledger), still show ledgers under them.
                if (self._hideL1Globally) {
                    afgOpen = true;
                }
                var ledgerVisible = !rid || !self._hideL3Globally || self._rootForceLedger[rid] === true;
                if (self._hideAccountGroups || self._hideL1Globally) {
                    ledgerVisible = true;
                }
                var show = typeOpen && afgOpen;
                if (lvl === 1) {
                    var lid = String($tr.data("line-id") || "");
                    if (self._hideL1Globally) {
                        show = false;
                    } else if (lid.indexOf("tb-gr-") === 0) {
                        show = typeOpen && afgOpen;
                    } else {
                        show = typeOpen;
                    }
                } else if (lvl === 2) {
                    show = typeOpen && afgOpen && (
                        !self._hideAccountGroups || self._rootForceLedger[rid] === true
                    ) && (!self._hideLedgersPack || self._rootForceLedger[rid] === true);
                } else if (lvl === 3) {
                    var underUngrouped = $tr.hasClass("o_afg_under_ungrouped");
                    var forceLed = self._rootForceLedger[rid] === true;
                    show = typeOpen && afgOpen && (
                        underUngrouped || forceLed || (ledgerVisible && !self._hideLedgersPack)
                    );
                } else if (lvl === 4) {
                    show = typeOpen && afgOpen && ledgerVisible && !self._hideL4Globally
                        && (!self._hideLedgersPack || self._rootForceLedger[rid] === true);
                }
                $tr.toggleClass("d-none", !show);
            });
            $tb.find("tr.o_afg_l0_row").each(function () {
                var $tr = $(this);
                var tid = $tr.data("afg-type-id");
                var open = self._typeOpen[tid] !== false;
                $tr.find(".o_afg_caret").first().text(open ? "▾" : "▸");
            });
            $tb.find("tr.o_afg_l1_row").each(function () {
                var $tr = $(this);
                var rid = String($tr.attr("data-line-id") || $tr.data("line-id") || "");
                var open = self._rootOpen[rid] === true;
                $tr.find(".o_afg_caret").first().text(open ? "▾" : "▸");
            });
        },

        _onRowToggle: function (ev) {
            if ($(ev.target).closest(".o_afg_amt_cell, td.text-right").length) {
                return;
            }
            var $tr = $(ev.currentTarget).closest("tr");
            if ($tr.hasClass("o_afg_l0_row")) {
                var tid = $tr.data("afg-type-id");
                if (!tid || $tr.data("afgComputed")) { return; }
                ev.preventDefault();
                ev.stopPropagation();
                this._typeOpen[tid] = this._typeOpen[tid] === false;
                this._applyRowTreeVisibility();
                return;
            }
            if (this._toggleGroupRow($tr)) {
                ev.preventDefault();
                ev.stopPropagation();
            }
        },

        _renderReportText: function () {
            var self = this;
            this.$(".o_afg_table_wrap").hide();
            var $host = this.$(".o_afg_report_text");
            if (!$host.length) {
                $host = $("<div class='o_afg_report_text p-3'/>");
                this.$(".o_afg_table_wrap").after($host);
            }
            $host.show().html("<div class='text-muted'>Loading report pages...</div>");
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_report_text_load",
                args: [[this.versionId]],
            }).then(function (pages) {
                self._reportTextPages = pages || [];
                var $box = $("<div/>");
                $box.append($("<p class='text-muted small'/>").text(
                    "These titles, page numbers and narrative lines are used on PDF and Word. Excel is unchanged. Schedule amounts stay calculated."
                ));
                (pages || []).forEach(function (page, idx) {
                    var $card = $("<div class='o_afg_report_text_card mb-3 p-2'/>").css({
                        border: "1px solid #334155",
                        borderRadius: "6px",
                    });
                    $card.append($("<div class='small text-info mb-1'/>").text(page.key || ""));
                    var $title = $("<input class='form-control form-control-sm mb-1 o_afg_rt_title'/>").val(page.title || "");
                    var $period = $("<input class='form-control form-control-sm mb-1 o_afg_rt_period'/>").val(page.period || "");
                    var $page = $("<input class='form-control form-control-sm mb-1 o_afg_rt_page'/>").val(page.page || "").attr("placeholder", "Page number");
                    $card.append($title, $period, $page);
                    if (page.narrative) {
                        $card.append($("<textarea class='form-control form-control-sm o_afg_rt_lines' rows='8'/>").val((page.lines || []).join("\n")));
                    } else if (page.schedule) {
                        $card.append($("<div class='small text-muted'/>").text("Schedule amounts are filled from the ledgers when you print."));
                    }
                    $card.data("rtIndex", idx);
                    $box.append($card);
                });
                $box.append($("<button type='button' class='btn btn-sm btn-primary o_afg_btn_save_report_text'/>").text("Save report text"));
                $host.empty().append($box);
            });
        },

        _onSaveReportText: function (ev) {
            ev.preventDefault();
            var self = this;
            var pages = [];
            this.$(".o_afg_report_text_card").each(function () {
                var $card = $(this);
                var idx = $card.data("rtIndex");
                var base = (self._reportTextPages || [])[idx] || {};
                var lines = base.lines || [];
                var $lines = $card.find(".o_afg_rt_lines");
                if ($lines.length) {
                    lines = $lines.val().split(/\n/);
                }
                pages.push({
                    key: base.key,
                    title: $card.find(".o_afg_rt_title").val(),
                    period: $card.find(".o_afg_rt_period").val(),
                    page: $card.find(".o_afg_rt_page").val(),
                    company: base.company || "",
                    place: base.place || "",
                    lines: lines,
                });
            });
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_report_text_save",
                args: [[this.versionId], pages],
            }).then(function () {
                window.alert("Report text saved. PDF and Word will use it.");
            });
        },

        _renderSection: function (section) {
            var self = this;
            var d = this.data;
            if (section === "report_text") {
                this.$(".o_afg_title").text("Report text");
                return this._renderReportText();
            }
            this.$(".o_afg_report_text").hide();
            this.$(".o_afg_table_wrap").show();
            var labels = d.section_labels || {};
            var fallback = {
                pl: _t("Statement of Profit or Loss"),
                bs: _t("Statement of Financial Position"),
                fta: _t("CORPORATE TAX FILING- FTA"),
                equity: _t("Statement of Changes in Equity"),
                cashflow: _t("Statement of Cash Flows"),
                fixed_assets: _t("Property, Plant and Equipment"),
                notes: _t("Notes to the Financial Statements"),
                review: _t("Validation & Review"),
                tb: _t("Trial Balance"),
            };
            this.$(".o_afg_section_title").text(labels[section] || fallback[section] || section);
            var lines = (d.sections && d.sections[section]) || [];
            var tbody = this.$(".o_afg_tbody").empty();
            this._rowSeq = 0;
            this.$(".o_afg_table").removeClass("o_afg_hide_l2 o_afg_hide_l3 o_afg_cf_table").addClass("table-striped");
            this.$(".o_afg_fa_wrap").hide().empty();
            this.$(".o_afg_tb_panels").hide().empty();
            var tbPayload = (section === "tb" || section === "tb_x") ? self._tbPayloadForSection(section) : {};
            var tbRoots = tbPayload.roots || [];
            var tbFlat = tbPayload.rows || [];
            var tbPanels = tbPayload.panels || [];
            var tbHierarchical = (section === "tb" || section === "tb_x") && (tbRoots.length > 0 || tbPanels.length > 0);
            var cfStmt = (d.schedules && d.schedules.cashflow_statement) || null;
            var faRecon = (d.schedules && d.schedules.fixed_assets_recon) || null;
            var soceStmt = (d.schedules && d.schedules.equity_statement) || null;
            var useCf = section === "cashflow" && cfStmt && (cfStmt.rows || []).length;
            var useFa = section === "fixed_assets" && faRecon && (faRecon.items || []).length;
            var useSoce = section === "equity" && soceStmt && (soceStmt.rows || []).length;
            this.$(".o_afg_table_wrap").toggle(
                section !== "review" && section !== "notes" && ((section !== "tb" && section !== "tb_x") || (tbHierarchical && !tbPanels.length)) && !useFa && !useSoce
            );
            this.$(".o_afg_tb_wrap").toggle((section === "tb" || section === "tb_x") && !tbHierarchical);
            this.$(".o_afg_tb_asof").toggle((section === "tb" || section === "tb_x") && !tbHierarchical);
            this.$(".o_afg_notes").toggle(section === "notes");
            this.$(".o_afg_review").toggle(section === "review");
            this.$(".o_afg_filters_row").toggle(this._isStatementSection(section) && !useCf && !useFa);

            if (section === "notes") {
                this.$(".o_afg_tb_asof").hide().text("");
                var nb = this.$(".o_afg_notes_body").empty();
                (d.notes || []).forEach(function (n) {
                    var title = $("<div/>").text(n.title || "").html();
                    nb.append(
                        $("<div class='o_afg_note card mb-2'/>")
                            .append($("<div class='card-header'/>").html(title))
                            .append($("<div class='card-body'/>").html(n.body || ""))
                    );
                });
                this._renderAlerts(d.alerts || []);
                return;
            }
            if (section === "review") {
                this.$(".o_afg_tb_asof").hide().text("");
                var $rev = this.$(".o_afg_review");
                var $alertsBox = $rev.find(".o_afg_alerts").empty();
                var vals = d.validations || [];
                if (vals.length) {
                    var $tbl = $("<table class='table table-sm o_afg_validation_table'/>");
                    $tbl.append(
                        "<thead><tr><th>" + _.escape(_t("Check")) + "</th><th>" +
                        _.escape(_t("Status")) + "</th><th>" + _.escape(_t("Detail")) +
                        "</th></tr></thead>"
                    );
                    var $tb = $("<tbody/>");
                    vals.forEach(function (v) {
                        var st = String(v.status || (v.ok ? "PASS" : "FAIL")).toUpperCase();
                        var cls = "font-weight-bold";
                        if (st === "PASS") {
                            cls += " text-success";
                        } else if (st === "WARN") {
                            cls += " text-warning";
                        } else {
                            cls += " text-danger";
                        }
                        $tb.append(
                            $("<tr/>")
                                .append($("<td/>").text(v.name || ""))
                                .append($("<td/>").addClass(cls).text(st))
                                .append($("<td class='small text-muted'/>").text(v.detail || ""))
                        );
                    });
                    $tbl.append($tb);
                    var overall = "PASS";
                    if (vals.some(function (v) { return String(v.status || "") === "FAIL"; })) {
                        overall = "FAIL";
                    } else if (vals.some(function (v) { return String(v.status || "") === "WARN"; })) {
                        overall = "WARN";
                    }
                    $alertsBox.append(
                        $("<h4 class='mt-0'/>").text(_t("Validation") + " — " + overall)
                    );
                    if (overall === "FAIL") {
                        $alertsBox.append(
                            $("<div class='alert alert-danger font-weight-bold'/>").text(
                                _t("FINANCIAL STATEMENTS NOT RECONCILED")
                            )
                        );
                    }
                    $alertsBox.append($tbl);
                }
                this._renderAlertList($alertsBox, d.alerts || []);
                this._renderAlerts(d.alerts || []);
                return;
            }
            if (useSoce) {
                this.$(".o_afg_tb_asof").hide().text("");
                this.$(".o_afg_fa_wrap").show();
                this._renderEquitySoce(soceStmt, d);
                this._syncCodeToggleUi();
                this._renderAlerts(d.alerts || []);
                return;
            }
            if (useCf) {
                this.$(".o_afg_tb_asof").hide().text("");
                this._renderCashflowStatement(cfStmt, d);
                this._syncCodeToggleUi();
                this._renderAlerts(d.alerts || []);
                return;
            }
            if (useFa) {
                this.$(".o_afg_tb_asof").hide().text("");
                this._renderFixedAssetsRecon(faRecon, d);
                this._syncCodeToggleUi();
                this._renderAlerts(d.alerts || []);
                return;
            }
            if (section === "tb" || section === "tb_x") {
                this.$(".o_afg_filters_row").show();
                d._tbFiveColumn = !!(tbPayload.five_column || tbPayload.tb_account_mode || tbPayload.afg_style);
                d._tbAmountWidth = (tbPayload.columns && tbPayload.columns.length)
                    ? tbPayload.columns.length
                    : 6;
                d.trial_balance = tbPayload; // header helpers read d.trial_balance
                if (tbPanels.length) {
                    this.$(".o_afg_table_wrap").hide();
                    this._renderTbPanels(tbPayload, d);
                    if (section === "tb" || tbPayload.afg_style) {
                        self._applyExportLevelToView(self._viewMaxLevel);
                    } else {
                        this._applyRowTreeVisibility();
                    }
                } else if (tbHierarchical && self._tbIsStatementStyleRoots(tbRoots)) {
                    this._buildTbHeader(d);
                    tbody.append(
                        $("<tr class='o_afg_tb_empty'/>").append(
                            $("<td colspan='10' class='text-center text-warning py-4'/>").text(
                                _t("Trial balance is out of date. Upgrade audited_financials and audited_financials, restart Odoo, then hard-refresh the browser.")
                            )
                        )
                    );
                } else if (tbHierarchical) {
                    this._buildTbHeader(d);
                    tbRoots.forEach(function (root) {
                        self._renderLineRow(root, tbody, d, 0, "");
                    });
                    // Second layout pass after tbody exists — fixes stacked OTC headers
                    // when navigating from SOFP/P&L without a full browser reload.
                    self._prepareMainTableLayout("tb");
                    if (section === "tb" || tbPayload.afg_style) {
                        self._applyExportLevelToView(self._viewMaxLevel);
                    } else {
                        this._applyRowTreeVisibility();
                    }
                } else if (tbFlat.length) {
                    this._renderTrialBalance(d);
                } else {
                    this._buildStatementHeader(d);
                    tbody.append(
                        $("<tr class='o_afg_tb_empty'/>").append(
                            $("<td colspan='7' class='text-center text-muted py-4'/>").text(
                                _t("No trial balance data. Load default or sample data, or map chart accounts.")
                            )
                        )
                    );
                }
                this._syncCodeToggleUi();
                this._renderAlerts(d.alerts || []);
                return;
            }
            this.$(".o_afg_tb_asof").hide().text("");
            this._buildStatementHeader(d);
            if (section === "bs") {
                this._renderSofpLikeTrialBalance(lines, tbody, d);
            } else {
                lines.forEach(function (root) {
                    self._renderLineRow(root, tbody, d, 0, "");
                });
            }
            if (this._isStatementSection(section) && section !== "fta") {
                this._applyExportLevelToView(this._viewMaxLevel);
            } else {
                this._applyRowTreeVisibility();
            }
            this._syncCodeToggleUi();
            this._renderAlerts(d.alerts || []);
        },

        /** Column count for SOFP banner colspan (# LG Desc Notes + amount cols). */
        _sofpBannerColCount: function (d) {
            var hideAud = !!(d && d.statement_hide_audited_totals);
            var cols = [];
            var nCo = 0;
            var base = 4;
            if (hideAud && nCo === 1) {
                return base + 2;
            }
            return base + (nCo ? nCo * 2 : 0) + 2;
        },

        _isSofpTypeBucket: function (line) {
            if (!line) {
                return false;
            }
            if (line.is_computed || line.is_tb_section_total || line.is_tb_difference) {
                return false;
            }
            var tk = String(line.type_key || "");
            return tk === "asset" || tk === "liability" || tk === "equity";
        },

        /**
         * Statement of Financial Position: TB-style layout
         * ASSETS → groups → TOTAL ASSETS → LIABILITIES AND EQUITY → groups → other totals.
         */
        _renderSofpLikeTrialBalance: function (roots, tbody, d) {
            var self = this;
            var assets = [];
            var totalAssets = [];
            var liabilities = [];
            var totalLiab = [];
            var equity = [];
            var totalEqLiab = [];
            var other = [];
            (roots || []).forEach(function (r) {
                var tk = String(r.type_key || "");
                if (tk === "asset") {
                    assets.push(r);
                } else if (tk === "total_assets") {
                    totalAssets.push(r);
                } else if (tk === "liability") {
                    liabilities.push(r);
                } else if (tk === "total_liabilities") {
                    totalLiab.push(r);
                } else if (tk === "equity") {
                    equity.push(r);
                } else if (tk === "total_equity_liabilities") {
                    totalEqLiab.push(r);
                } else {
                    other.push(r);
                }
            });
            var colCount = this._sofpBannerColCount(d);

            function addBanner(title) {
                var $banner = $("<tr class='o_afg_tb_section_banner o_afg_sofp_section_banner o_afg_main_line_fill'/>");
                $banner.append(
                    $("<td/>").attr("colspan", colCount).text(title)
                );
                tbody.append($banner);
            }

            function renderBucketRoots(list) {
                (list || []).forEach(function (root) {
                    if (self._isSofpTypeBucket(root)) {
                        (root.children || []).forEach(function (ch) {
                            self._renderLineRow(ch, tbody, d, 1, root.id);
                        });
                    } else {
                        self._renderLineRow(root, tbody, d, 0, "");
                    }
                });
            }

            function renderTotals(list) {
                (list || []).forEach(function (root) {
                    self._renderLineRow(root, tbody, d, 0, "");
                });
            }

            // Match Trial Balance: TOTAL ASSETS sits above LIABILITIES AND EQUITY
            if (assets.length || totalAssets.length) {
                addBanner(_t("ASSETS"));
                renderBucketRoots(assets);
                renderTotals(totalAssets);
            }
            if (liabilities.length || equity.length || totalLiab.length || totalEqLiab.length) {
                addBanner(_t("LIABILITIES AND EQUITY"));
                renderBucketRoots(liabilities);
                renderTotals(totalLiab);
                renderBucketRoots(equity);
                renderTotals(totalEqLiab);
            }
            other.forEach(function (root) {
                self._renderLineRow(root, tbody, d, 0, "");
            });
        },

        _fmtDash: function (v) {
            if (v === null || v === undefined || v === "") {
                return "—";
            }
            var n = parseFloat(v);
            if (isNaN(n)) {
                return "—";
            }
            if (Math.abs(n) < 0.005) {
                return "—";
            }
            return this._fmt(n);
        },

        _renderEquitySoce: function (soce, d) {
            var self = this;
            var $wrap = this.$(".o_afg_fa_wrap").empty().show();
            var cols = soce.columns || [];
            var rows = soce.rows || [];
            var yp = soce.year_prior || d.year_prior || "";
            var yc = soce.year_current || d.year_current || "";
            var curr = soce.currency || d.currency || "AED";
            var yearsDesc = !!this._yearsDescending;
            var $table = $("<table class='o_afg_fa_table o_afg_soce_table'/>");
            var $thead = $("<thead/>");
            var $hr = $("<tr/>");
            $hr.append($("<th/>").text(_t("Particulars")));
            cols.forEach(function (c) {
                $hr.append($("<th class='amt' colspan='2'/>").text(c.name || ""));
            });
            $hr.append($("<th class='amt o_afg_fa_total' colspan='2'/>").text(_t("Total")));
            $thead.append($hr);
            var $hr2 = $("<tr/>");
            $hr2.append($("<th/>").text(""));
            cols.forEach(function () {
                $hr2.append($("<th class='amt small'/>").text(yearsDesc ? yc : yp));
                $hr2.append($("<th class='amt small'/>").text(yearsDesc ? yp : yc));
            });
            $hr2.append($("<th class='amt small'/>").text(yearsDesc ? yc : yp));
            $hr2.append($("<th class='amt small'/>").text(yearsDesc ? yp : yc));
            $thead.append($hr2);
            $table.append($thead);
            var $tbody = $("<tbody/>");
            rows.forEach(function (row) {
                var $tr = $("<tr/>");
                if (row.bold) {
                    $tr.addClass("o_afg_main_line_fill");
                }
                $tr.append($("<td class='o_afg_fa_row_label'/>").text(row.label || ""));
                cols.forEach(function (c) {
                    var cell = (row.cells || {})[c.key] || {};
                    var a = cell.prior;
                    var b = cell.current;
                    if (yearsDesc) {
                        $tr.append($("<td class='amt'/>").text(self._fmtDash(b)));
                        $tr.append($("<td class='amt'/>").text(self._fmtDash(a)));
                    } else {
                        $tr.append($("<td class='amt'/>").text(self._fmtDash(a)));
                        $tr.append($("<td class='amt'/>").text(self._fmtDash(b)));
                    }
                });
                var tot = row.total || {};
                if (yearsDesc) {
                    $tr.append($("<td class='amt o_afg_fa_total'/>").text(self._fmtDash(tot.current)));
                    $tr.append($("<td class='amt o_afg_fa_total'/>").text(self._fmtDash(tot.prior)));
                } else {
                    $tr.append($("<td class='amt o_afg_fa_total'/>").text(self._fmtDash(tot.prior)));
                    $tr.append($("<td class='amt o_afg_fa_total'/>").text(self._fmtDash(tot.current)));
                }
                $tbody.append($tr);
            });
            $table.append($tbody);
            $wrap.append(
                $("<div class='small text-muted mb-2'/>").text(
                    _t("Statement of Changes in Equity") + " (" + curr + ")"
                )
            );
            $wrap.append($table);
        },

        _renderCashflowStatement: function (stmt, d) {
            var self = this;
            var tbody = this.$(".o_afg_tbody").empty();
            var $newThead = $("<thead class='o_afg_thead'/>");
            var yp = stmt.year_prior || d.year_prior || "";
            var yc = stmt.year_current || d.year_current || "";
            var curr = stmt.currency || d.currency || "";
            var yearsDesc = !!this._yearsDescending;
            var yFirst = yearsDesc ? yc : yp;
            var ySecond = yearsDesc ? yp : yc;
            var trh = $("<tr/>");
            var spec = this._afgPackSpec();
            if (!spec.hide_hash) {
                trh.append($("<th/>").text("#"));
            }
            if (!spec.hide_lg) {
                trh.append($("<th class='o_afg_th_lg'/>").text(_t("LG")));
            }
            trh.append($("<th/>").text(_t("Particulars")));
            trh.append($("<th class='text-right'/>").text(String(yFirst) + (curr ? " " + curr : "")));
            trh.append($("<th class='text-right'/>").text(String(ySecond) + (curr ? " " + curr : "")));
            if (spec.pack >= 3) {
                trh.append($("<th/>").text(_t("Remark")));
            }
            $newThead.append(trh);
            var $old = this.$(".o_afg_thead");
            if ($old.length) {
                $old.replaceWith($newThead);
            } else {
                this.$(".o_afg_table").prepend($newThead);
            }
            this._prepareMainTableLayout("cf");
            var cfSeq = 0;
            (stmt.rows || []).forEach(function (r) {
                var kind = r.kind || "ledger";
                // Pack depth: L1/L2 section+group; L3 skip group bands; L4 full
                if (spec.pack <= 2 && kind === "ledger") {
                    return;
                }
                if (spec.pack === 3 && kind === "group") {
                    return;
                }
                var tr = $("<tr/>");
                cfSeq += 1;
                function addMeta(lg) {
                    if (!spec.hide_hash) {
                        tr.append($("<td/>").text(String(cfSeq)));
                    }
                    if (!spec.hide_lg) {
                        tr.append($("<td class='o_afg_cell_lg'/>").text(lg));
                    }
                }
                if (kind === "section") {
                    tr.addClass(
                        "o_afg_cf_section o_afg_kind_group o_afg_main_line_fill o_afg_tb_section_banner"
                    );
                    addMeta("L0");
                    var span = 2 + (spec.pack >= 3 ? 1 : 0);
                    tr.append($("<td colspan='" + span + "'/>").text(self._afgCaps(r.label || "")));
                } else if (kind === "group") {
                    tr.addClass("o_afg_cf_group o_afg_kind_group o_afg_afg_band_contrast");
                    addMeta("L2");
                    tr.append($("<td class='o_afg_desc_cell'/>").text(self._afgCaps(r.label || "")));
                    tr.append($("<td class='text-right'/>").text(self._fmtDash(yearsDesc ? r.current : r.prior)));
                    tr.append($("<td class='text-right'/>").text(self._fmtDash(yearsDesc ? r.prior : r.current)));
                    if (spec.pack >= 3) {
                        tr.append($("<td class='small text-muted'/>").text(r.remark || ""));
                    }
                } else {
                    tr.addClass("o_afg_cf_ledger o_afg_kind_ledger");
                    addMeta("L3");
                    tr.append($("<td class='o_afg_desc_cell o_afg_cf_ledger_label'/>").text(r.label || ""));
                    tr.append($("<td class='text-right'/>").text(self._fmtDash(yearsDesc ? r.current : r.prior)));
                    tr.append($("<td class='text-right'/>").text(self._fmtDash(yearsDesc ? r.prior : r.current)));
                    if (spec.pack >= 3) {
                        tr.append($("<td class='small text-muted'/>").text(r.remark || ""));
                    }
                }
                tbody.append(tr);
            });
        },

        _renderFixedAssetsRecon: function (recon, d) {
            var self = this;
            var $wrap = this.$(".o_afg_fa_wrap").empty().show();
            var faMode = this._afgNormalizeFaColumnMode(this._faColumnMode || "single");
            this._faColumnMode = faMode;
            // Valued named asset columns only — drop blank / zero ghosts (gap before Total)
            var rawItems = recon.items || [];
            var items = rawItems.filter(function (it) {
                var nm = ((it && it.name) || "").toString().trim();
                if (!nm || nm === "-" || nm.toLowerCase() === "total" || nm.toLowerCase() === "amount") {
                    return false;
                }
                var keys = [
                    "cost_prior", "cost_current", "additions", "disposals",
                    "dep_prior", "dep_current", "charge", "dep_disposals",
                    "nbv_prior", "nbv_current",
                ];
                return keys.some(function (k) {
                    var n = Number(it[k]);
                    return !isNaN(n) && Math.abs(n) > 1e-9;
                });
            });
            var totals = recon.totals || {};
            if (!items.length) {
                $wrap.append($("<div class='alert alert-info'/>").text(
                    _t("No property, plant and equipment ledgers with balances for this period. Map FAA / Acc. Depn. under Balance Sheet PPE, then refresh.")
                ));
                return;
            }
            // Prefer multi-column when several asset classes exist (matches SOFP ledgers)
            if (items.length > 1 && faMode === "single" && !this._faColumnModeUserSet) {
                faMode = "multi";
                this._faColumnMode = "multi";
            }
            // Recompute totals from visible columns so Total matches headers
            var totKeys = [
                "cost_prior", "cost_current", "additions", "disposals",
                "dep_prior", "dep_current", "charge", "dep_disposals",
                "nbv_prior", "nbv_current",
            ];
            totKeys.forEach(function (k) {
                totals[k] = items.reduce(function (s, it) {
                    var n = Number(it[k]);
                    return s + (isNaN(n) ? 0 : n);
                }, 0);
            });
            var yp = recon.year_prior || d.year_prior || "";
            var yc = recon.year_current || d.year_current || "";
            var curr = recon.currency || d.currency || "AED";
            var multi = faMode === "multi";

            // Toggle: Single column (totals) | Multi column (ledger-wise) — default single
            var $toolbar = $("<div class='o_afg_fa_toolbar d-flex flex-wrap align-items-center mb-2'/>");
            $toolbar.append(
                $("<span class='o_afg_fa_toolbar_label small mr-2'/>").text(_t("Fixed Assets columns"))
            );
            var $grp = $("<div class='btn-group btn-group-sm o_afg_fa_col_toggle' role='group'/>");
            $grp.append(
                $("<button type='button' class='btn o_afg_fa_col_mode'/>")
                    .attr("data-fa-mode", "single")
                    .toggleClass("btn-primary active", !multi)
                    .toggleClass("btn-secondary", multi)
                    .text(_t("Single column"))
            );
            $grp.append(
                $("<button type='button' class='btn o_afg_fa_col_mode'/>")
                    .attr("data-fa-mode", "multi")
                    .toggleClass("btn-primary active", multi)
                    .toggleClass("btn-secondary", !multi)
                    .text(_t("Multi column"))
            );
            $toolbar.append($grp);
            $toolbar.append(
                $("<span class='small text-muted ml-2'/>").text(
                    multi
                        ? _t("Ledger-wise columns")
                        : _t("All assets in one Total column")
                )
            );
            $wrap.append($toolbar);

            function dash(v) {
                return self._fmtDash(v);
            }
            function valsForKey(key) {
                if (key === null || key === undefined || key === "") {
                    return {
                        values: items.map(function () { return null; }),
                        total: null,
                    };
                }
                return {
                    values: items.map(function (it) { return it[key]; }),
                    total: totals[key],
                };
            }
            function buildBlock(title, rows) {
                var $block = $("<div class='o_afg_fa_block'/>");
                $block.append($("<h5/>").text(title));
                var $table = $("<table class='o_afg_fa_table'/>");
                if (!multi) {
                    $table.addClass("o_afg_fa_table_single");
                }
                var $thead = $("<thead/>");
                var $hr = $("<tr/>");
                $hr.append($("<th/>").text(_t("Particulars")));
                if (multi) {
                    items.forEach(function (it) {
                        $hr.append(
                            $("<th class='amt o_afg_fa_ledger_th'/>").text(it.name || "")
                        );
                    });
                }
                $hr.append($("<th class='amt o_afg_fa_total'/>").text(
                    multi ? _t("Total") : _t("Amount")
                ));
                $thead.append($hr);
                $table.append($thead);
                var $tbody = $("<tbody/>");
                rows.forEach(function (row) {
                    var $tr = $("<tr/>");
                    if (row.isTotal) {
                        $tr.addClass("o_afg_fa_total o_afg_main_line_fill");
                    }
                    $tr.append($("<td class='o_afg_fa_row_label'/>").text(row.label));
                    if (multi) {
                        (row.values || []).forEach(function (v) {
                            $tr.append($("<td class='amt'/>").text(dash(v)));
                        });
                    }
                    $tr.append($("<td class='amt o_afg_fa_total'/>").text(dash(row.total)));
                    $tbody.append($tr);
                });
                $table.append($tbody);
                $block.append($table);
                return $block;
            }
            function renderYearSchedule(sched) {
                var keys = sched.keys || {};
                var yOpen = sched.opening_year;
                var yClose = sched.closing_year;
                var $sec = $("<div class='o_afg_fa_year'/>");
                $sec.append($("<h4 class='o_afg_fa_year_title'/>").text(
                    sched.title || (_t("Property, Plant and Equipment — Year") + " " + (sched.year || ""))
                ));
                var costOpen = valsForKey(keys.cost_open);
                var costMove = valsForKey(keys.cost_move);
                var costDisp = valsForKey(keys.cost_disp);
                var costClose = valsForKey(keys.cost_close);
                var depOpen = valsForKey(keys.dep_open);
                var depMove = valsForKey(keys.dep_move);
                var depDisp = valsForKey(keys.dep_disp);
                var depClose = valsForKey(keys.dep_close);
                var nbvClose = valsForKey(keys.nbv_close);
                var nbvOpen = valsForKey(keys.nbv_open);
                $sec.append(buildBlock(_t("COST") + " (" + curr + ")", [
                    {
                        label: _t("Opening cost"),
                        values: costOpen.values,
                        total: costOpen.total,
                        isTotal: true,
                    },
                    {
                        label: _t("Additions"),
                        values: costMove.values,
                        total: costMove.total,
                    },
                    {
                        label: _t("Disposals"),
                        values: costDisp.values,
                        total: costDisp.total,
                    },
                    {
                        label: _t("Closing cost"),
                        values: costClose.values,
                        total: costClose.total,
                        isTotal: true,
                    },
                ]));
                $sec.append(buildBlock(_t("ACCUMULATED DEPRECIATION") + " (" + curr + ")", [
                    {
                        label: _t("Opening accumulated depreciation"),
                        values: depOpen.values,
                        total: depOpen.total,
                        isTotal: true,
                    },
                    {
                        label: _t("Charge for the year"),
                        values: depMove.values,
                        total: depMove.total,
                    },
                    {
                        label: _t("Disposals"),
                        values: depDisp.values,
                        total: depDisp.total,
                    },
                    {
                        label: _t("Closing accumulated depreciation"),
                        values: depClose.values,
                        total: depClose.total,
                        isTotal: true,
                    },
                ]));
                $sec.append(buildBlock(_t("NET BOOK VALUE") + " (" + curr + ")", [
                    {
                        label: _t("Closing net book value"),
                        values: nbvClose.values,
                        total: nbvClose.total,
                        isTotal: true,
                    },
                    {
                        label: _t("Opening net book value"),
                        values: nbvOpen.values,
                        total: nbvOpen.total,
                        isTotal: true,
                    },
                ]));
                return $sec;
            }

            var schedules = recon.year_schedules || [];
            if (!schedules.length) {
                // Legacy: one combined prior→current set
                schedules = [{
                    year: yc,
                    title: _t("Property, Plant and Equipment — Year") + " " + yc,
                    opening_year: yp,
                    closing_year: yc,
                    keys: {
                        cost_open: "cost_prior",
                        cost_move: "additions",
                        cost_close: "cost_current",
                        dep_open: "dep_prior",
                        dep_move: "charge",
                        dep_close: "dep_current",
                        nbv_close: "nbv_current",
                        nbv_open: "nbv_prior",
                    },
                }];
            }
            schedules.forEach(function (sched) {
                $wrap.append(renderYearSchedule(sched));
            });
        },

        _syncLevelButtons: function () {
            // Bulk L1/L2/Ledgers buttons removed — View/print depth is the single control.
            return;
        },

        _onLevelClick: function (ev) {
            // Kept for compatibility if stale QWeb still has buttons.
            var mode = $(ev.currentTarget).data("afg-level-mode");
            if (!mode) { return; }
            this._applyGlobalExpansion(mode);
        },

        _onToggleRemoveGroup: function () {
            var self = this;
            this._hideAccountGroups = !this._hideAccountGroups;
            if (this._hideAccountGroups) {
                this._hideL3Globally = false;
                var lines = this._collectLinesForExpansion();
                this._collectAfgRootIds(lines).forEach(function (rid) {
                    self._rootOpen[rid] = true;
                });
            }
            // Optional: when groups shown, keep ledgers expanded under AFG
            if (!this._hideAccountGroups) {
                this._hideL0Globally = false;
            } else {
                this._hideL0Globally = true;
            }
            this.$(".o_afg_btn_remove_group")
                .toggleClass("active btn-warning", this._hideAccountGroups)
                .toggleClass("btn-secondary", !this._hideAccountGroups)
                .text(this._hideAccountGroups ? _t("Show Group") : _t("Remove Group"));
            this._applyRowTreeVisibility();
        },

        _afgLgLabel: function (lvl) {
            if (lvl === 0 || lvl === "0") { return "L0"; }
            if (lvl === 1) { return "L1"; }
            if (lvl === 2) { return "L2"; }
            if (lvl === 3) { return "L3"; }
            if (lvl === 4) { return "L4"; }
            return "L0";
        },

        _afgProperCase: function (text) {
            var ACRONYMS = {
                VAT: 1, IFRS: 1, FTA: 1, AED: 1, USD: 1, EUR: 1, GBP: 1, UAE: 1, GCC: 1,
                EBITDA: 1, COGS: 1, NBV: 1, PPE: 1, EOS: 1, ITC: 1, GST: 1, WHT: 1, CPA: 1,
                "P&L": 1, TB: 1, BS: 1, PL: 1, ROI: 1, ERP: 1, FY: 1, YTD: 1, AP: 1, AR: 1,
                COS: 1, EBIT: 1, EPS: 1, FX: 1, OCI: 1, SOCE: 1,
            };
            var SMALL = {
                a: 1, an: 1, and: 1, as: 1, at: 1, but: 1, by: 1, for: 1, from: 1, in: 1,
                into: 1, nor: 1, of: 1, on: 1, or: 1, the: 1, to: 1, vs: 1, via: 1, with: 1,
            };
            var raw = String(text || "").trim();
            if (!raw) {
                return raw;
            }
            var wordIndex = 0;
            return raw.split(/(\s+|[–—/()\[\]|,])/).map(function (part) {
                if (!part || /^(\s+|[–—/()\[\]|,])$/.test(part)) {
                    return part;
                }
                var m = part.match(/^([A-Za-z0-9&]+)(.*)$/);
                if (!m) {
                    return part;
                }
                var word = m[1];
                var rest = m[2];
                var up = word.toUpperCase();
                var low = word.toLowerCase();
                var out;
                if (ACRONYMS[up]) {
                    out = up + rest;
                } else if (wordIndex > 0 && SMALL[low]) {
                    out = low + rest;
                } else {
                    out = word.charAt(0).toUpperCase() + word.slice(1).toLowerCase() + rest;
                }
                wordIndex += 1;
                return out;
            }).join("");
        },

        _afgCaps: function (text) {
            return this._afgProperCase(text);
        },

        /** L0 headers in ALL CAPS except Equity (keeps Proper Case like before). */
        _afgTypeLabel: function (line, desc) {
            var tk = String((line && line.type_key) || "");
            if (tk === "equity") {
                return this._afgCaps(desc);
            }
            var forceCaps = {
                asset: 1,
                total_assets: 1,
                liability: 1,
                total_liabilities: 1,
                total_equity_liabilities: 1,
                sales: 1,
                cost_of_revenue: 1,
                expenses: 1,
                profit_before_tax: 1,
                tax_for_year: 1,
                net_profit: 1,
            };
            if (forceCaps[tk] || !(line && line.type_key)) {
                return String(desc || "").toUpperCase();
            }
            return this._afgCaps(desc);
        },

        _buildTbHeader: function (d) {
            var tb = d.trial_balance || {};
            // Replace <thead> node entirely — empty()+html() leaves rowspan/colspan
            // layout broken when switching from SOFP/P&L single-row headers.
            var $newThead = $("<thead class='o_afg_thead'/>").html(this._tbHeaderRowHtml(tb));
            var $old = this.$(".o_afg_thead");
            if ($old.length) {
                $old.replaceWith($newThead);
            } else {
                this.$(".o_afg_table").prepend($newThead);
            }
            this._prepareMainTableLayout("tb");
        },

        _buildStatementHeader: function (d) {
            var $newThead = $("<thead class='o_afg_thead'/>");
            var tr = $("<tr/>");
            var spec = this._afgPackSpec();
            if (!spec.hide_hash) {
                tr.append($("<th class='o_afg_th_hash'/>").text("#"));
            }
            if (!spec.hide_lg) {
                tr.append($("<th class='o_afg_th_lg'/>").text(_t("LG")));
            }
            tr.append($("<th class='o_afg_th_desc'/>").text(_t("Description")));
            tr.append($("<th class='o_afg_th_notes'/>").text(_t("Notes")));
            var cols = [];
            var hideAud = !!d.statement_hide_audited_totals;
            var nCo = 0;
            var yearsDesc = !!this._yearsDescending;
            var periodLabs = this._periodLabelsOrdered(d);
            // Statements (P&L / SOFP / Equity): N comparative period columns.
            // Opening / Closing bookends are Trial Balance only.
            if (periodLabs.length) {
                if (hideAud && nCo === 1) {
                    periodLabs.forEach(function (lab) {
                        tr.append($("<th class='text-right small'/>").text(lab));
                    });
                } else {
                    cols.forEach(function (co) {
                        var prefix = (co.name || "") + " — ";
                        periodLabs.forEach(function (lab) {
                            tr.append($("<th class='text-right small'/>").text(prefix + lab));
                        });
                    });
                    periodLabs.forEach(function (lab, idx) {
                        var cls = "text-right";
                        if (idx === 0) {
                            cls += " o_afg_y1";
                        }
                        if (idx === periodLabs.length - 1) {
                            cls += " o_afg_y2";
                        }
                        tr.append($("<th class='" + cls + "'/>").text(lab));
                    });
                }
            } else {
                var yPrior = String(this._periodLabelPrior(d));
                var yCurrent = String(this._periodLabelCurrent(d));
                var yFirst = yearsDesc ? yCurrent : yPrior;
                var ySecond = yearsDesc ? yPrior : yCurrent;
                if (hideAud && nCo === 1) {
                    tr.append($("<th class='text-right small'/>").text(yFirst));
                    tr.append($("<th class='text-right small'/>").text(ySecond));
                } else {
                    cols.forEach(function (co) {
                        var prefix = (co.name || "") + " — ";
                        tr.append($("<th class='text-right small'/>").text(prefix + yFirst));
                        tr.append($("<th class='text-right small'/>").text(prefix + ySecond));
                    });
                    tr.append($("<th class='text-right o_afg_y1'/>").text(yFirst || _t("Prior")));
                    tr.append($("<th class='text-right o_afg_y2'/>").text(ySecond || _t("Current")));
                }
            }
            $newThead.append(tr);
            var $old = this.$(".o_afg_thead");
            if ($old.length) {
                $old.replaceWith($newThead);
            } else {
                this.$(".o_afg_table").prepend($newThead);
            }
            if (d) {
                d._tbFiveColumn = false;
                d._tbAmountWidth = null;
            }
            this._prepareMainTableLayout("statement");
        },

        /**
         * Reset table column-width cache when switching SOFP/P&L ↔ Trial Balance.
         * Without this, TB Opening/Transactions/Closing headers stack on top of each other
         * until a full browser reload.
         */
        _prepareMainTableLayout: function (mode) {
            var $table = this.$(".o_afg_table");
            if (!$table.length) {
                return;
            }
            $table.removeClass("o_afg_tb_unified o_afg_cf_table");
            if (mode === "tb") {
                $table.addClass("o_afg_tb_unified table-striped");
            } else if (mode === "cf") {
                $table.addClass("o_afg_cf_table").removeClass("table-striped");
            } else {
                $table.addClass("table-striped");
            }
            // Force browser to drop cached column widths from the previous section.
            var el = $table[0];
            if (el) {
                $table.css("table-layout", "auto");
                void el.offsetWidth;
                // TB: keep auto + horizontal scroll (fixed layout crushed OTC columns).
                if (mode !== "tb") {
                    $table.css("table-layout", "");
                }
            }
        },

        _renderTrialBalance: function (d) {
            var self = this;
            var tb = d.trial_balance || {columns: [], rows: [], as_of: ""};
            d._tbFiveColumn = !!(tb.five_column || tb.tb_account_mode);
            var asof = tb.as_of ? (_t("As of ") + tb.as_of) : "";
            this.$(".o_afg_tb_asof").text(asof);
            var thead = this.$(".o_afg_tb_thead").empty();
            var trh = $("<tr/>");
            trh.append($("<th/>").text("#"));
            trh.append($("<th class='o_afg_tb_th_code'/>").text(_t("Code")));
            trh.append($("<th/>").text(_t("Account")));
            trh.append($("<th class='o_afg_tb_th_group'/>").text(_t("Odoo group")));
            (tb.columns || []).forEach(function (c) {
                trh.append($("<th class='text-right'/>").text(c.label || c.name || ""));
            });
            thead.append(trh);
            var tbody = this.$(".o_afg_tb_tbody").empty();
            var seq = 0;
            (tb.rows || []).forEach(function (r) {
                seq += 1;
                var tr = $("<tr/>");
                tr.append($("<td/>").text(String(seq)));
                tr.append($("<td class='o_afg_tb_cell_code'/>").text(r.code || ""));
                tr.append($("<td/>").text(r.name || ""));
                tr.append($("<td class='o_afg_tb_cell_group'/>").text(r.group || ""));
                (r.tb_amounts || []).forEach(function (v) {
                    tr.append($("<td class='text-right'/>").text(self._fmt(v)));
                });
                tbody.append(tr);
            });
        },

        _afgLineIsRealLedger: function (line) {
            if (!line) {
                return false;
            }
            var lvl = line.level !== undefined && line.level !== null ? line.level : 0;
            var lid = String(line.id || "");
            var tk = String(line.type_key || "");
            if (tk === "retained_earnings" || lid === "bs-retained-earnings" || lid === "bs-cy-pnl") {
                return true;
            }
            if (line.account_id) {
                return true;
            }
            if (lvl === 4 || lid.indexOf("l4-") === 0) {
                return true;
            }
            if (lvl === 3) {
                return true;
            }
            if (lid.indexOf("tb-") === 0
                    && lid.indexOf("tb-gr-") !== 0
                    && lid.indexOf("tb-type-") !== 0
                    && lid.indexOf("tb-total-") !== 0) {
                return true;
            }
            return false;
        },

        _afgSubtreeHasRealLedger: function (line) {
            if (!line) {
                return false;
            }
            if (this._afgLineIsRealLedger(line)) {
                return true;
            }
            var kids = line.children || [];
            for (var i = 0; i < kids.length; i++) {
                if (this._afgSubtreeHasRealLedger(kids[i])) {
                    return true;
                }
            }
            return false;
        },

        _afgApplyRowTone: function (tr, line, isLedgerRow) {
            var tone = "structure";
            if (isLedgerRow && this._afgLineIsRealLedger(line)) {
                tone = "ledger";
            } else if (!line.is_computed && this._afgSubtreeHasRealLedger(line)) {
                tone = "has_ledgers";
            }
            tr.removeClass("o_afg_tone_ledger o_afg_tone_has_ledgers o_afg_tone_structure");
            tr.addClass("o_afg_tone_" + tone);
            tr.attr("data-afg-tone", tone);
        },

        _renderLineRow: function (line, tbody, d, depth, typeParentId, underUngrouped) {
            var self = this;
            var lvl = line.level !== undefined && line.level !== null ? line.level : (depth + 1);
            underUngrouped = !!(underUngrouped || line.is_ungrouped_review);
            var tk = String(line.type_key || "");
            var lid = String(line.id || "");
            var isEquityLedgerFace = (
                tk === "retained_earnings"
                || lid === "bs-retained-earnings"
                || lid === "bs-cy-pnl"
            );
            // TB folded Profit/(Loss) stays L0 main total (not a second L3 under Equity)
            if (isEquityLedgerFace) {
                lvl = 3;
            }
            var isTypeRow = lvl === 0;
            var isL4 = lvl === 4 || (typeof line.id === "string" && String(line.id).indexOf("l4-") === 0);
            var isComputed = !!(line.is_computed && isTypeRow);
            var isGrandTotal = isTypeRow && String(line.type_key || "") === "grand_total";
            var nameBlob = [
                line.label || "",
                line.afg_caption || "",
                line.group_caption || "",
                line.ledger_caption || "",
            ].join(" ").toLowerCase();
            var isUngroupName = nameBlob.indexOf("ungroup") >= 0
                || underUngrouped
                || !!line.is_ungrouped_review;
            if (!isComputed && !isGrandTotal && !isEquityLedgerFace
                    && (lvl === 1 || lvl === 2 || lvl === 3 || isL4)
                    && !self._lineHasBalance(line, d)) {
                if (!isUngroupName) {
                    return;
                }
            }
            this._rowSeq += 1;
            var tr = $("<tr/>");
            if (isUngroupName) {
                tr.addClass("o_afg_ungrouped_warn");
            }
            tr.attr("data-afg-level", lvl);
            var underType = line.type_parent_id || typeParentId || "";
            if (lvl === 1 && underType) {
                tr.attr("data-afg-under-type", underType);
            }
            if (lvl >= 2 || (lvl === 1 && underType)) {
                if (underType) {
                    tr.attr("data-afg-under-type", underType);
                }
            }
            if (lvl >= 2) {
                tr.attr("data-afg-under-root", line.root_id || "");
            }
            underUngrouped = !!(underUngrouped || line.is_ungrouped_review);
            if (underUngrouped && lvl >= 2) {
                tr.addClass("o_afg_under_ungrouped");
                tr.attr(
                    "data-afg-ungrouped-code",
                    line.ungrouped_code || $("tr.o_afg_ungrouped_reassign[data-line-id='" + (line.root_id || "") + "']").attr("data-afg-ungrouped-code") || "AFG_UNGRP_BS"
                );
                    tr.attr("title", _t("Click ledger for journal items. Right-click to allocate AFG group"));
            }

            var numCell = $("<td class='o_afg_cell_num'/>");
            var desc = line.label || "";
            var gcode = (line.group_code || "").trim();
            var gcapt = (line.group_caption || line.label || "").trim();
            var lcode = (line.ledger_code || "").trim();
            var lcapt = (line.ledger_caption || "").trim();
            if (isEquityLedgerFace && !lcapt) {
                lcapt = (line.afg_caption || desc || "").trim();
            }
            var isTbLedger = !!(line.is_ledger) || (
                String(line.id || "").indexOf("tb-") === 0 &&
                String(line.id || "").indexOf("tb-gr-") !== 0 &&
                String(line.id || "").indexOf("tb-type-") !== 0 &&
                String(line.id || "").indexOf("tb-total-") !== 0
            );
            var isLedgerRow = lvl === 3 || isL4 || isTbLedger || isEquityLedgerFace;
            var isGroupRow = (lvl === 2 && !isTbLedger && !isEquityLedgerFace);
            var isTbGroup = lvl === 1 && String(line.id || "").indexOf("tb-gr-") === 0;
            var isTbSectionTotal = !!(line.is_tb_section_total);
            // Groups flush left; ledgers indent further right (~4–5 spaces / double prior)
            var hasKids = (line.children || []).length > 0;
            var indentPx = (lvl >= 3 || isL4) ? 28 : 0;

            if (isTbSectionTotal) {
                tr.addClass(
                    "o_afg_kind_type o_afg_tb_section_total o_afg_main_line_fill o_afg_tb_section_banner"
                );
                numCell.addClass("o_afg_kind_type");
            } else if (line.is_tb_difference) {
                tr.addClass("o_afg_kind_type o_afg_tb_difference");
                numCell.addClass("o_afg_kind_type");
            } else if (isTypeRow) {
                tr.addClass("o_afg_kind_type o_afg_l0_row");
                numCell.addClass("o_afg_kind_type");
                tr.attr("data-afg-type-id", line.id);
                if (line.is_computed) {
                    tr.attr("data-afg-computed", "1");
                    tr.addClass("o_afg_kind_type_computed");
                }
                // All reports: main L0 totals / capital lines get contrast fill
                // (TOTAL ASSETS, TOTAL SALES, Net Profit, …). Equity type bucket stays plain.
                var mainTk = String(line.type_key || "");
                if (mainTk !== "equity") {
                    tr.addClass("o_afg_type_caps_row o_afg_tb_section_banner o_afg_main_line_fill");
                }
            } else if (lvl === 1 && isTbGroup) {
                tr.addClass("o_afg_kind_group o_afg_l1_row o_afg_afg_band_contrast");
                numCell.addClass("o_afg_kind_group");
                tr.attr("data-line-id", line.id);
            } else if (lvl === 1) {
                // All reports: AFG main rows — contrast fill (not only at L4 depth)
                tr.addClass("o_afg_kind_l1 o_afg_l1_row o_afg_afg_band_contrast");
                numCell.addClass("o_afg_kind_l1");
                if (line.is_ungrouped_review) {
                    tr.addClass("o_afg_drillable o_afg_ungrouped_reassign o_afg_map_group");
                    tr.attr("title", _t("Click name to expand ledgers. Right-click to list / add ledgers"));
                    tr.attr("data-afg-ungrouped-code", line.ungrouped_code || "AFG_UNGRP_PL");
                    tr.attr("data-afg-account-ids", JSON.stringify(line.drill_account_ids || []));
                } else if (typeof line.id === "number") {
                    tr.addClass("o_afg_drillable");
                    tr.attr("title", _t("Click name to expand ledgers. Click amount for Show Vouchers"));
                    tr.data("afgDrillLineId", line.id);
                } else if (line.drill_account_ids && line.drill_account_ids.length) {
                    tr.addClass("o_afg_drillable");
                    tr.attr("title", _t("Click name to expand ledgers. Click amount for Show Vouchers"));
                    tr.data("afgDrillAccountId", line.drill_account_ids[0]);
                }
            } else if (isGroupRow) {
                tr.addClass("o_afg_kind_group o_afg_l1_row");
                numCell.addClass("o_afg_kind_group");
                tr.attr("data-line-id", line.id);
                if (typeof line.id === "number") {
                    tr.addClass("o_afg_drillable");
                    tr.attr("title", _t("Click name to expand ledgers. Click amount for Show Vouchers"));
                    tr.data("afgDrillLineId", line.id);
                } else if (line.drill_account_ids && line.drill_account_ids.length) {
                    tr.addClass("o_afg_drillable");
                    tr.attr("title", _t("Click name to expand ledgers. Click amount for Show Vouchers"));
                    tr.data("afgDrillAccountId", line.drill_account_ids[0]);
                }
            } else if (isLedgerRow) {
                tr.addClass("o_afg_kind_ledger o_afg_drillable o_afg_map_ledger");
                numCell.addClass("o_afg_kind_ledger");
                tr.attr("title", _t("Right-click for Show Vouchers, Tally, Journal Items"));
                if (line.l3_line_id && line.account_id) {
                    tr.data("afgDrillAccountId", line.account_id);
                    tr.data("afgDrillL3LineId", line.l3_line_id);
                    if (line.branch_company_id) {
                        tr.data("afgDrillCompanyId", line.branch_company_id);
                    }
                } else if (line.account_id) {
                    tr.data("afgDrillAccountId", line.account_id);
                    tr.attr("data-afg-account-id", line.account_id);
                    if (typeof line.id === "number") {
                        tr.data("afgDrillL3LineId", line.id);
                    }
                } else if (typeof line.id === "number") {
                    tr.data("afgDrillLineId", line.id);
                } else if (line.drill_account_ids && line.drill_account_ids.length) {
                    tr.data("afgDrillAccountId", line.drill_account_ids[0]);
                    tr.attr("data-afg-account-id", line.drill_account_ids[0]);
                    if (typeof line.id === "number") {
                        tr.data("afgDrillL3LineId", line.id);
                    }
                }
            }
            if (underUngrouped && isLedgerRow) {
                tr.attr("title", _t("Click for journal items. Right-click to allocate AFG group"));
            }
            if (!isLedgerRow && !line.is_computed) {
                if (line.group_id) {
                    tr.addClass("o_afg_map_group");
                    tr.attr("data-afg-group-id", line.group_id);
                }
                if (line.ctf_category) {
                    tr.addClass("o_afg_map_group");
                    tr.attr("data-afg-ctf-category", line.ctf_category);
                }
                if (tr.hasClass("o_afg_map_group")) {
                    tr.attr("title", _t("Click name to expand ledgers. Right-click to list / add ledgers. Click amount for journals"));
                }
            }
            var drillIds = line.drill_account_ids || [];
            if (line.account_id && drillIds.indexOf(line.account_id) < 0) {
                drillIds = [line.account_id].concat(drillIds);
            }
            if (drillIds.length) {
                tr.attr("data-afg-account-ids", drillIds.join(","));
            }
            this._afgApplyRowTone(tr, line, isLedgerRow);

            numCell.text(this._rowSeq);
            if (!this._hideHashColumn) {
                tr.append(numCell);
            }
            if (!this._hideLgColumn) {
                tr.append($("<td class='o_afg_cell_lg'/>").text(this._afgLgLabel(lvl)));
            }

            var descCell = $("<td class='o_afg_desc_cell'/>").css("padding-left", indentPx + "px");
            if (line.sensitive) {
                desc = "[Sensitive] " + desc;
            }
            var showCodes = !!self._showCodes;
            if (isTypeRow) {
                descCell.addClass("o_afg_l0");
                if (!line.is_computed && hasKids) {
                    descCell.addClass("o_afg_l0_toggle");
                    descCell.append($("<span class='o_afg_caret mr-1'/>").text("▸"));
                } else if (line.is_computed) {
                    descCell.addClass("o_afg_l0_computed");
                }
                var typeLabel = self._afgTypeLabel(line, desc);
                var $typeName = $("<span class='o_afg_desc_text o_afg_type_name'/>").text(typeLabel);
                    if (String(line.type_key || "") !== "equity") {
                    $typeName.addClass("o_afg_type_caps");
                    // Reuse Trial Balance section banner fill (ASSETS / TOTAL SALES, etc.)
                    tr.addClass("o_afg_type_caps_row o_afg_tb_section_banner o_afg_main_line_fill");
                }
                descCell.append($typeName);
            } else if (lvl === 1 && isTbGroup) {
                tr.addClass("o_afg_l1_row");
                descCell.addClass("o_afg_l2");
                if (hasKids) {
                    descCell.addClass("o_afg_l1_toggle");
                    descCell.append($("<span class='o_afg_caret mr-1'/>").text("▸"));
                }
                if (showCodes && gcode) {
                    descCell.append($("<span class='o_afg_group_code_part'/>").text(gcode + " "));
                }
                descCell.append($("<span class='o_afg_name_part o_afg_group_name'/>").text(self._afgCaps(gcapt || desc)));
            } else if (lvl === 1) {
                tr.addClass("o_afg_l1_row");
                tr.attr("data-line-id", line.id);
                descCell.addClass("o_afg_l1");
                if (hasKids || tr.hasClass("o_afg_map_group")) {
                    descCell.addClass("o_afg_l1_toggle");
                    descCell.append($("<span class='o_afg_caret mr-1'/>").text("▸"));
                }
                var acode = (line.afg_code || "").trim();
                var acapt = (line.afg_caption || desc).trim();
                if (showCodes && acode) {
                    descCell.append($("<span class='o_afg_group_code_part o_afg_afg_code_part'/>").text(acode + " "));
                }
                var $afgName = $("<span class='o_afg_desc_text o_afg_afg_name'/>").text(
                    self._afgCaps(acapt || desc)
                );
                // L4 depth: force CAPITAL CASE on AFG group labels (like prior L1+ledgers view)
                if (self._viewMaxLevel === 4 || self._hideAccountGroups) {
                    $afgName.addClass("o_afg_type_caps");
                }
                descCell.append($afgName);
            } else if (isGroupRow) {
                descCell.addClass("o_afg_l2");
                if (hasKids) {
                    descCell.addClass("o_afg_l1_toggle");
                    descCell.append($("<span class='o_afg_caret mr-1'/>").text("▸"));
                }
                if (showCodes && gcode) {
                    descCell.append($("<span class='o_afg_group_code_part'/>").text(gcode + " "));
                }
                descCell.append($("<span class='o_afg_name_part o_afg_group_name'/>").text(self._afgCaps(gcapt || desc)));
            } else if (isLedgerRow) {
                // L3/L4: keep Chart of Accounts casing (do not force UPPERCASE)
                descCell.addClass(isL4 ? "o_afg_l4" : "o_afg_l3");
                if (isL4) {
                    descCell.append(
                        $("<span class='o_afg_name_part o_afg_company_name'/>").text(
                            line.label || lcapt || desc
                        )
                    );
                } else {
                    if (showCodes && lcode) {
                        descCell.append($("<span class='o_afg_ledger_code_part'/>").text(lcode + " "));
                    }
                    descCell.append($("<span class='o_afg_name_part o_afg_ledger_name'/>").text(
                        lcapt || desc
                    ));
                }
            } else {
                descCell.text(self._afgCaps(desc));
            }
            tr.append(descCell);
            tr.append($("<td/>").text(line.note || ""));

            if ((d._tbFiveColumn || self.section === "tb" || self.section === "tb_x") && line.tb_amounts && line.tb_amounts.length) {
                var needW = d._tbAmountWidth || line.tb_amounts.length;
                var tbVals = self._tbReorderAmounts(line.tb_amounts, needW);
                var natureKey = self._tbLineNatureKey(line);
                // Net / difference row stays signed (must be nil) — plain magnitude + red if off
                var isNetRow = !!(line.is_tb_difference) || String(line.type_key || "") === "difference";
                tbVals.forEach(function (v) {
                    if (isNetRow) {
                        var nf = self._fmtTbNature(v, "asset"); // signed as-is (asset rule = raw)
                        var cell = $("<td class='text-right small o_afg_amt_cell font-weight-bold'/>")
                            .text(nf.text);
                        if (nf.neg) {
                            cell.addClass("o_afg_tb_nature_neg");
                        }
                        tr.append(cell);
                    } else {
                        self._appendTbAmtCell(tr, v, natureKey, isGrandTotal || isTbSectionTotal);
                    }
                });
            } else if (d._tbFiveColumn || self.section === "tb" || self.section === "tb_x") {
                // Keep grid aligned even when a row has no tb_amounts yet.
                var padN = d._tbAmountWidth || 6;
                for (var ti = 0; ti < padN; ti++) {
                    tr.append($("<td class='text-right small o_afg_amt_cell'/>").text("—"));
                }
            } else {
            var hideAud = !!d.statement_hide_audited_totals;
            var companyCols = d.company_columns || [];
            var cols = [];
            var nCo = 0;
            var yearsDesc = !!self._yearsDescending;
            var periodLabs = self._periodLabelsOrdered(d);
            var periodAmts = listSlice(line.period_amounts);
            if (yearsDesc && periodAmts.length > 1) {
                periodAmts = periodAmts.slice().reverse();
            }
            var alertFlags = self._afgAlertFlags(line, yearsDesc);
            if (alertFlags.some(function (flag) { return flag === "bad" || flag === "error"; })) {
                tr.addClass("o_afg_row_alert");
            }
            if (!periodAmts.length && periodLabs.length) {
                // Fallback prior/current → N slots
                if (periodLabs.length === 1) {
                    periodAmts = [line.current !== undefined && line.current !== null ? line.current : line.prior];
                } else {
                    periodAmts = [line.prior, line.current];
                    while (periodAmts.length < periodLabs.length) {
                        periodAmts.splice(1, 0, 0);
                    }
                    if (yearsDesc) {
                        periodAmts = periodAmts.slice().reverse();
                    }
                }
            }

            if (periodLabs.length && periodAmts.length) {
                if (hideAud && nCo === 1) {
                    periodAmts.forEach(function (v) {
                        tr.append($("<td class='text-right small o_afg_branch_amt o_afg_amt_cell'/>").text(self._fmt(v)));
                    });
                } else {
                    if (nCo) {
                        for (var i = 0; i < nCo; i++) {
                            // Multi-co still 2-period; pad with prior/current only
                            var pv0 = (line.co_prior && line.co_prior[i] !== undefined) ? line.co_prior[i] : null;
                            var cv0 = (line.co_curr && line.co_curr[i] !== undefined) ? line.co_curr[i] : null;
                            if (periodLabs.length === 1) {
                                tr.append($("<td class='text-right small text-muted o_afg_amt_cell'/>").text(self._fmt(cv0 !== null ? cv0 : pv0)));
                            } else if (periodLabs.length === 2) {
                                var a0 = yearsDesc ? cv0 : pv0;
                                var b0 = yearsDesc ? pv0 : cv0;
                                tr.append($("<td class='text-right small text-muted o_afg_amt_cell'/>").text(self._fmt(a0)));
                                tr.append($("<td class='text-right small text-muted o_afg_amt_cell'/>").text(self._fmt(b0)));
                            } else {
                                periodAmts.forEach(function (v) {
                                    tr.append($("<td class='text-right small text-muted o_afg_amt_cell'/>").text(self._fmt(v)));
                                });
                            }
                        }
                    }
                    var editLeaf = d.edit_mode && line.level === 3 && !line.sensitive && typeof line.id === "number";
                    if (editLeaf && periodLabs.length <= 2) {
                        var faceScale = (line.face_scale !== undefined && line.face_scale !== null)
                            ? line.face_scale : 1;
                        var mkInput = function (field, val) {
                            return $("<input type='number' step='0.01' class='form-control form-control-sm o_afg_amount_input'/>")
                                .attr("data-line-id", line.id)
                                .attr("data-field", field)
                                .attr("data-face-scale", faceScale)
                                .val(val);
                        };
                        if (periodLabs.length === 1) {
                            tr.append($("<td class='text-right o_afg_amt_cell'/>").append(
                                mkInput("amount_current", line.current)
                            ));
                        } else if (yearsDesc) {
                            tr.append($("<td class='text-right o_afg_amt_cell'/>").append(
                                mkInput("amount_current", line.current)
                            ));
                            tr.append($("<td class='text-right o_afg_amt_cell'/>").append(
                                mkInput("amount_prior", line.prior)
                            ));
                        } else {
                            tr.append($("<td class='text-right o_afg_amt_cell'/>").append(
                                mkInput("amount_prior", line.prior)
                            ));
                            tr.append($("<td class='text-right o_afg_amt_cell'/>").append(
                                mkInput("amount_current", line.current)
                            ));
                        }
                    } else {
                        periodAmts.forEach(function (v, idx) {
                            tr.append(self._afgStatementAmtCell(v, alertFlags[idx] || ""));
                        });
                    }
                }
            } else if (hideAud && nCo === 1) {
                // Prefer co_*; fall back to prior/current (CY / BS plug lines have no co_* until synced)
                var pv = (line.co_prior && line.co_prior.length && line.co_prior[0] !== undefined && line.co_prior[0] !== null)
                    ? line.co_prior[0] : line.prior;
                var cv = (line.co_curr && line.co_curr.length && line.co_curr[0] !== undefined && line.co_curr[0] !== null)
                    ? line.co_curr[0] : line.current;
                var first = yearsDesc ? cv : pv;
                var second = yearsDesc ? pv : cv;
                tr.append($("<td class='text-right small o_afg_branch_amt o_afg_amt_cell'/>").text(self._fmt(first)));
                tr.append($("<td class='text-right small o_afg_branch_amt o_afg_amt_cell'/>").text(self._fmt(second)));
            } else {
                if (nCo) {
                    for (var j = 0; j < nCo; j++) {
                        var pv1 = (line.co_prior && line.co_prior[j] !== undefined) ? line.co_prior[j] : null;
                        var cv1 = (line.co_curr && line.co_curr[j] !== undefined) ? line.co_curr[j] : null;
                        var a1 = yearsDesc ? cv1 : pv1;
                        var b1 = yearsDesc ? pv1 : cv1;
                        tr.append($("<td class='text-right small text-muted o_afg_amt_cell'/>").text(self._fmt(a1)));
                        tr.append($("<td class='text-right small text-muted o_afg_amt_cell'/>").text(self._fmt(b1)));
                    }
                }
                var editLeaf2 = d.edit_mode && line.level === 3 && !line.sensitive && typeof line.id === "number";
                if (editLeaf2) {
                    var faceScale2 = (line.face_scale !== undefined && line.face_scale !== null)
                        ? line.face_scale : 1;
                    var mkInput2 = function (field, val) {
                        return $("<input type='number' step='0.01' class='form-control form-control-sm o_afg_amount_input'/>")
                            .attr("data-line-id", line.id)
                            .attr("data-field", field)
                            .attr("data-face-scale", faceScale2)
                            .val(val);
                    };
                    if (yearsDesc) {
                        tr.append($("<td class='text-right o_afg_amt_cell'/>").append(
                            mkInput2("amount_current", line.current)
                        ));
                        tr.append($("<td class='text-right o_afg_amt_cell'/>").append(
                            mkInput2("amount_prior", line.prior)
                        ));
                    } else {
                        tr.append($("<td class='text-right o_afg_amt_cell'/>").append(
                            mkInput2("amount_prior", line.prior)
                        ));
                        tr.append($("<td class='text-right o_afg_amt_cell'/>").append(
                            mkInput2("amount_current", line.current)
                        ));
                    }
                } else if (yearsDesc) {
                    tr.append(self._afgStatementAmtCell(line.current, alertFlags[0] || ""));
                    tr.append(self._afgStatementAmtCell(line.prior, alertFlags[1] || ""));
                } else {
                    tr.append(self._afgStatementAmtCell(line.prior, alertFlags[0] || ""));
                    tr.append(self._afgStatementAmtCell(line.current, alertFlags[1] || ""));
                }
            }

            function listSlice(arr) {
                return (arr && arr.length) ? arr.slice() : [];
            }
            }
            tbody.append(tr);
            var splitRows = (line.company_splits || []).filter(function (co) {
                return co && (co.prior || co.current);
            });
            if (isLedgerRow && self._showMultco && splitRows.length) {
                var nPeriods = (typeof periodLabs !== "undefined" && periodLabs && periodLabs.length) ? periodLabs.length : 2;
                splitRows.forEach(function (co) {
                    var pv = co.prior || 0;
                    var cv = co.current || 0;
                    var sub = $("<tr class='o_afg_multco_row'/>");
                    sub.attr("data-afg-level", String(lvl));
                    if (line.root_id) {
                        sub.attr("data-afg-under-root", line.root_id);
                    }
                    if (underType) {
                        sub.attr("data-afg-under-type", underType);
                    }
                    if (!self._hideHashColumn) {
                        sub.append($("<td class='o_afg_cell_num'/>"));
                    }
                    if (!self._hideLgColumn) {
                        sub.append($("<td class='o_afg_cell_lg'/>"));
                    }
                    sub.append(
                        $("<td class='o_afg_desc_cell o_afg_multco_name'/>")
                            .css("padding-left", "48px")
                            .text(co.name || "")
                    );
                    sub.append($("<td class='o_afg_notes_cell'/>"));
                    if (nPeriods <= 1) {
                        sub.append($("<td class='text-right small o_afg_amt_cell'/>").text(self._fmt(yearsDesc ? cv : pv)));
                    } else {
                        var a = yearsDesc ? cv : pv;
                        var b = yearsDesc ? pv : cv;
                        sub.append($("<td class='text-right small o_afg_amt_cell'/>").text(self._fmt(a)));
                        sub.append($("<td class='text-right small o_afg_amt_cell'/>").text(self._fmt(b)));
                    }
                    tbody.append(sub);
                });
            }

            var childTypeId = isTypeRow ? line.id : underType;
            (line.children || []).forEach(function (ch) {
                if (isTypeRow) {
                    ch.type_parent_id = line.id;
                } else {
                    ch.root_id = line.id;
                    ch.type_parent_id = childTypeId;
                    ch.ungrouped_code = ch.ungrouped_code || line.ungrouped_code;
                }
                self._renderLineRow(ch, tbody, d, depth + 1, childTypeId, underUngrouped || line.is_ungrouped_review);
            });
        },

        _renderAlerts: function (alerts) {
            this._renderAlertList(this.$(".o_afg_alerts_side"), alerts);
            this._syncInternalNotes();
        },

        _syncInternalNotes: function () {
            var $ta = this.$(".o_afg_internal_notes");
            if (!$ta.length) {
                return;
            }
            if ($ta.is(":focus")) {
                return;
            }
            $ta.val(this._internalActionNotes || "");
        },

        _onSaveInternalNotes: function (ev) {
            if (ev) {
                ev.preventDefault();
            }
            var self = this;
            if (!this.versionId) {
                return;
            }
            var notes = this.$(".o_afg_internal_notes").val() || "";
            this._internalActionNotes = notes;
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_dashboard_save_internal_notes",
                args: [[this.versionId], notes],
            }).then(function () {
                self.$(".o_afg_internal_notes_status").text(_t("Saved"));
            });
        },

        _renderAlertList: function ($container, alerts) {
            $container.empty();
            if (!alerts.length) {
                $container.append($("<p class='text-muted mb-0'/>").text(_t("No alerts.")));
                return;
            }
            alerts.forEach(function (a) {
                var cls = "alert-info";
                if (a.severity === "warning") { cls = "alert-warning"; }
                if (a.severity === "critical") { cls = "alert-danger"; }
                $container.append(
                    $("<div/>")
                        .addClass("alert " + cls)
                        .append($("<strong/>").text(a.title || ""))
                        .append($("<div/>").text(a.message || ""))
                );
            });
        },

        _onNavClick: function (ev) {
            ev.preventDefault();
            var $li = $(ev.currentTarget).closest("li");
            var actionXmlid = $li.data("actionXmlid");
            if (actionXmlid) {
                return this.do_action(actionXmlid);
            }
            var sec = $li.data("section");
            if (!sec || sec === this.section) {
                return;
            }
            this.section = sec;
            this._afgSaveSection(sec);
            var lightSections = {bs: true, pl: true, fta: true};
            if (this.data && this.data.light && !lightSections[sec] && !this._afgFullLoad) {
                this._afgFullLoad = true;
                return this._loadData();
            }
            this._renderSectionNavOnly();
        },

        _onApplyYears: function (ev) {
            if (ev) {
                ev.preventDefault();
            }
            var self = this;
            if (!this.versionId) {
                window.alert(_t("Working paper not loaded yet. Wait a moment and try again."));
                return;
            }
            var $row = this.$(".o_afg_period_row").first();
            var yp = parseInt($row.find(".o_afg_year_prior").val(), 10);
            var yc = parseInt($row.find(".o_afg_year_current").val(), 10);
            if (isNaN(yp) || isNaN(yc)) {
                window.alert(_t("Enter valid prior and current years."));
                return;
            }
            var $btn = this.$(".o_afg_btn_apply_years");
            $btn.prop("disabled", true);
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_dashboard_apply_years",
                args: [[this.versionId]],
                kwargs: {
                    year_prior: yp,
                    year_current: yc,
                    context: ctx,
                },
            }).then(function (res) {
                self._yearsDirty = false;
                if (res && res.empty) {
                    window.alert(_t(
                        "Years applied (%s / %s), but no posted journals were found in that window."
                    ).replace("%s", String(res.year_prior)).replace("%s", String(res.year_current)));
                }
                return self._loadData();
            }).guardedCatch(function (err) {
                var msg = err && err.message && err.message.data && err.message.data.message;
                if (!msg && err && err.data && err.data.message) {
                    msg = err.data.message;
                }
                window.alert(msg || _t("Could not apply years. Try again."));
            }).then(function () {
                $btn.prop("disabled", false);
            }, function () {
                $btn.prop("disabled", false);
            });
        },

        _syncYearOrderButton: function () {
            var $btn = this.$(".o_afg_btn_year_order");
            if (!$btn.length) {
                return;
            }
            var d = this.data || {};
            var title = this._yearsDescending ? _t("Column descending") : _t("Column ascending");
            var caption = this._yearsDescending
                ? ((d.period_label_current || d.year_current || "") + " → " + (d.period_label_prior || d.year_prior || ""))
                : ((d.period_label_prior || d.year_prior || "") + " → " + (d.period_label_current || d.year_current || ""));
            $btn.find(".o_afg_period_card_title").first().text(title);
            $btn.find(".o_afg_period_card_caption").first().text(caption);
            $btn.attr(
                "title",
                this._yearsDescending
                    ? _t("Now: current period column first. Click for ascending.")
                    : _t("Now: prior period column first. Click for descending.")
            );
            $btn.toggleClass("o_afg_column_order_desc", !!this._yearsDescending);
            $btn.toggleClass("o_afg_column_order_asc", !this._yearsDescending);
        },

        _ensureYearOrderButton: function () {
            // Column order card is created inside _renderPeriodPresets.
            if (this.$(".o_afg_btn_year_order").length) {
                return;
            }
            var $host = this.$(".o_afg_period_presets");
            if (!$host.length) {
                return;
            }
            var $order = $("<button type='button' class='o_afg_period_card o_afg_btn_year_order o_afg_column_order_card'/>");
            $order.append($("<div class='o_afg_period_card_title'/>").text(_t("Column descending")));
            $order.append($("<div class='o_afg_period_card_caption'/>").text(""));
            $order.append($("<div class='o_afg_period_card_hint'/>").text(_t("Toggle statement column order")));
            $host.append($order);
        },

        _onToggleYearOrder: function (ev) {
            if (ev) {
                ev.preventDefault();
                ev.stopPropagation();
            }
            this._yearsDescending = !this._yearsDescending;
            this._syncYearOrderButton();
            this._persistYearOrder();
            if (this.data && Object.keys(this.data).length) {
                this._renderChromeAndSection();
            }
        },

        _persistYearOrder: function () {
            if (!this.versionId) {
                return;
            }
            var self = this;
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_dashboard_set_years_descending",
                args: [[this.versionId], !!this._yearsDescending],
                kwargs: {context: ctx},
            }).then(function (res) {
                self._yearsOrderLoaded = true;
                if (self.data && res && Object.prototype.hasOwnProperty.call(res, "print_years_descending")) {
                    self.data.print_years_descending = !!res.print_years_descending;
                }
            });
        },

        _onPeriodSpanCardClick: function (ev) {
            // Card itself is not a button — select handles change
            if (ev && $(ev.target).closest("select").length) {
                return;
            }
            if (ev) {
                ev.preventDefault();
                ev.stopPropagation();
            }
        },

        _onPeriodSpanSelect: function (ev) {
            if (ev) {
                ev.preventDefault();
                ev.stopPropagation();
            }
            var self = this;
            var span = $(ev.currentTarget).val();
            if (!span || !this.versionId) {
                return;
            }
            if (String(span) === String(this._periodSpan || "2y")) {
                return;
            }
            var $sel = this.$(".o_afg_period_span_select").prop("disabled", true);
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_dashboard_set_period_span",
                args: [[this.versionId], span],
                kwargs: {context: ctx},
            }).then(function (res) {
                self._periodSpan = (res && res.period_span) || span;
                return self._loadData();
            }).guardedCatch(function () {
                $sel.prop("disabled", false);
            });
        },

        _periodLabelsOrdered: function (d) {
            d = d || this.data || {};
            var labels = listSlice(d.period_labels);
            if (!labels.length) {
                var yp = String(this._periodLabelPrior(d) || "");
                var yc = String(this._periodLabelCurrent(d) || "");
                if (d.hide_comparative) {
                    labels = yc ? [yc] : (yp ? [yp] : []);
                } else if (yp || yc) {
                    labels = [yp, yc];
                }
            }
            if (this._yearsDescending && labels.length > 1) {
                labels = labels.slice().reverse();
            }
            return labels;

            function listSlice(arr) {
                return (arr && arr.length) ? arr.slice() : [];
            }
        },

        _onYearsDefault: function () {
            if (!window.confirm(_t("Reset to the default two calendar years and reload posted data?"))) {
                return;
            }
            return this._rpcVer("action_reload_to_default_periods");
        },

        _rpcVer: function (method, extraArgs) {
            var self = this;
            if (!this.versionId) { return this._loadData(); }
            var args = [[this.versionId]];
            if (extraArgs && extraArgs.length) {
                args = args.concat(extraArgs);
            }
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: method,
                args: args,
                kwargs: {context: ctx},
            }).then(function () {
                return self._loadData();
            });
        },

        _onReloadPeriods: function () {
            var self = this;
            if (!window.confirm(_t("Reset to Last 2 years (default) and rebuild from posted journals?"))) {
                return;
            }
            return this._rpcVer("action_reload_to_default_periods");
        },

        _onLoadDefault: function () {
            return this._rpcVer("action_load_default_data");
        },

        _onLoadSample: function () {
            if (!window.confirm(_t("Replace the working paper with illustrative sample numbers?"))) {
                return;
            }
            return this._rpcVer("action_load_sample_data");
        },

        _onClearAdjustments: function () {
            return this._rpcVer("action_clear_adjustments");
        },

        _onPrint: function () {
            return this._rpcExportAudit("action_print_audit_report_pdf");
        },

        _dpiValue: function () {
            var n = parseInt(this._exportDpi, 10);
            if (isNaN(n)) {
                try {
                    n = parseInt(window.localStorage && localStorage.getItem("cpabooks_afg.dpi"), 10);
                } catch (e) {
                    n = 90;
                }
            }
            if (isNaN(n)) {
                n = 90;
            }
            n = Math.max(50, Math.min(160, n));
            this._exportDpi = n;
            return n;
        },

        _renderDpi: function () {
            this.$(".o_afg_dpi_value").text(String(this._dpiValue()));
        },

        _loadSavedDpi: function () {
            var self = this;
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_get_print_dpi",
                args: [],
            }).then(function (dpi) {
                var n = parseInt(dpi, 10);
                if (!isNaN(n)) {
                    self._exportDpi = n;
                }
                self._renderDpi();
            }).guardedCatch(function () {
                self._renderDpi();
            });
        },

        _onDpiStep: function (ev) {
            var self = this;
            var delta = parseInt($(ev.currentTarget).data("dpi-delta"), 10) || 0;
            var n = this._dpiValue() + delta;
            n = Math.max(50, Math.min(160, n));
            this._exportDpi = n;
            this._renderDpi();
            return rpc.query({
                model: "audited.financial.version",
                method: "afg_set_print_dpi",
                args: [n],
            }).then(function (saved) {
                var applied = parseInt(saved, 10);
                if (!isNaN(applied)) {
                    self._exportDpi = applied;
                    self._renderDpi();
                }
            });
        },

        _onPrintSetup: function () {
            if (!this.versionId) { return; }
            var self = this;
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "action_open_print_setup",
                args: [[this.versionId]],
                kwargs: {context: ctx},
            }).then(function (action) {
                if (!action) {
                    return;
                }
                return self.do_action(action, {
                    on_close: function () {
                        return self._loadData();
                    },
                });
            });
        },

        _onPrintAudit: function () {
            // Open PDF in a new tab — do_action(report) replaces this client action and leaves a blank screen
            return this._rpcExportAudit("action_print_audit_report_pdf");
        },

        _onPrintSimple: function () {
            return this._rpcExportAudit("action_print_afg_simple_pdf");
        },

        _pageTitle: function () {
            return (this.$(".o_afg_section_title").text() || "Audited Financial").replace(/\s+/g, " ").trim();
        },

        _visiblePageTables: function () {
            return this.$(".o_afg_main table, .o_afg_table, .o_afg_tb_table").filter(function () {
                return $(this).is(":visible") && $(this).closest(".o_afg_sidebar").length === 0;
            });
        },

        _visibleTableMatrix: function () {
            var rows = [];
            this._visiblePageTables().each(function () {
                $(this).find("tr").each(function () {
                    if (!$(this).is(":visible")) {
                        return;
                    }
                    var cells = [];
                    $(this).children("th,td").each(function () {
                        if (!$(this).is(":visible")) {
                            return;
                        }
                        cells.push($(this).text().replace(/\s+/g, " ").trim());
                    });
                    if (cells.length) {
                        rows.push(cells);
                    }
                });
            });
            return rows;
        },

        _pageHtml: function () {
            var title = this._pageTitle();
            var body = "";
            this._visiblePageTables().each(function () {
                var table = $("<table/>");
                $(this).find("tr:visible").each(function () {
                    var tr = $("<tr/>");
                    $(this).children("th,td").filter(":visible").each(function () {
                        tr.append($("<td/>").text($(this).text().replace(/\s+/g, " ").trim()));
                    });
                    if (tr.children().length) {
                        table.append(tr);
                    }
                });
                body += "<table>" + table.html() + "</table><br/>";
            });
            return "<h2>" + $("<div/>").text(title).html() + "</h2>" + body;
        },

        _openPagePrint: function () {
            var win = window.open("", "_blank");
            if (!win) {
                window.alert("Allow pop-ups to print this page.");
                return;
            }
            win.document.write(
                "<html><head><title>" + $("<div/>").text(this._pageTitle()).html() +
                "</title><style>body{font-family:Arial,sans-serif}table{border-collapse:collapse;width:100%;margin-bottom:12px}td{border:1px solid #ccc;padding:4px 6px;font-size:12px}</style></head><body>" +
                this._pageHtml() +
                "<script>window.onload=function(){window.print();}<' + '/script></body></html>"
            );
            win.document.close();
        },

        _onPrintPage: function () {
            if (this.section === "fta") {
                return this._rpcExportAudit("action_print_fta_pdf");
            }
            this._openPagePrint();
        },

        _onPdfPage: function () {
            if (this.section === "fta") {
                return this._rpcExportAudit("action_print_fta_pdf");
            }
            this._openPagePrint();
        },

        _onExcelPage: function () {
            if (this.section === "fta") {
                return this._rpcExportAudit("action_export_fta_xlsx");
            }
            var title = this._pageTitle();
            var rows = this._visibleTableMatrix();
            var html = "<table><tr><td colspan='8'>" + $("<div/>").text(title).html() + "</td></tr>";
            rows.forEach(function (row) {
                html += "<tr>";
                row.forEach(function (cell) {
                    html += "<td>" + $("<div/>").text(cell).html() + "</td>";
                });
                html += "</tr>";
            });
            html += "</table>";
            var blob = new Blob(["\ufeff" + html], {type: "application/vnd.ms-excel"});
            var link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.download = title.replace(/[^A-Za-z0-9]+/g, "_") + ".xls";
            link.click();
        },

        _onPrintFta: function () {
            return this._rpcExportAudit("action_print_fta_pdf");
        },

        _onExportAuditXlsx: function () {
            return this._rpcExportAudit("action_export_audit_xlsx");
        },

        _onExportCtFilingMaster: function () {
            return this._rpcExportAudit("action_export_ct_filing_master");
        },

        _onExportAuditWord: function () {
            return this._rpcExportAudit("action_export_audit_docx");
        },

        _rpcExportAudit: function (method) {
            if (!this.versionId) { return; }
            var self = this;
            var ctx = this._getRpcContext() || {};
            if (method === "action_print_audit_report_pdf" || method === "action_export_audit_docx" || method === "action_print_afg_simple_pdf") {
                ctx.afg_print_financials = this.$(".o_afg_print_financials").is(":checked") ? 1 : 0;
            }
            var maxLevel = this._afgNormalizeDepth(
                this.$(".o_afg_export_level").val() || this._viewMaxLevel
            );
            this._viewMaxLevel = maxLevel;
            this._afgSaveDepth(maxLevel);
            return rpc.query({
                model: "audited.financial.version",
                method: method,
                args: [[this.versionId], maxLevel],
                kwargs: {context: ctx},
            }).then(function (action) {
                if (!action) {
                    return;
                }
                // L1 gate wizard (or other act_window) — no UserError popup
                if (action.type === "ir.actions.act_window") {
                    return self.do_action(action, {
                        on_close: function () {
                            return self._loadData();
                        },
                    });
                }
                if (action.type === "ir.actions.client") {
                    return self.do_action(action);
                }
                if (action.url) {
                    window.open(action.url, action.target === "self" ? "_self" : "_blank");
                }
            });
        },

        _onExport: function () {
            if (!this.versionId) { return; }
            var self = this;
            var ctx = this._getRpcContext();
            return rpc.query({
                model: "audited.financial.version",
                method: "action_export_csv",
                args: [[this.versionId]],
                kwargs: {context: ctx},
            }).then(function (action) {
                if (action && action.url) {
                    window.open(action.url, "_blank");
                }
                return self._loadData();
            });
        },

        _onSave: function () {
            return this._rpcVer("action_save_version");
        },

        _onToggleEdit: function () {
            return this._rpcVer("action_toggle_edit");
        },

        _onOpenForm: function () {
            if (!this.versionId) { return; }
            this.do_action({
                type: "ir.actions.act_window",
                res_model: "audited.financial.version",
                res_id: this.versionId,
                views: [[false, "form"]],
                target: "current",
            });
        },

        _onToggleMultco: function (ev) {
            ev.preventDefault();
            this._showMultco = !this._showMultco;
            this.$(".o_afg_btn_multco").toggleClass("btn-warning", !!this._showMultco);
            this.$(".o_afg_btn_multco").toggleClass("btn-secondary", !this._showMultco);
            if (this.data) {
                this._renderSection(this.section);
            }
        },

        _onMergeLedger: function () {
            var self = this;
            if (!this.versionId) {
                return;
            }
            return rpc.query({
                model: "audited.financial.version",
                method: "action_open_ledger_merge_wizard",
                args: [[this.versionId], this.section || "bs"],
            }).then(function (action) {
                if (action) {
                    return self.do_action(action);
                }
            });
        },

        _onAmountChange: function (ev) {
            var self = this;
            var $inp = $(ev.currentTarget);
            var lineId = parseInt($inp.data("line-id"), 10);
            var field = $inp.data("field");
            var val = parseFloat($inp.val());
            if (!lineId || !field) { return; }
            // Face presentation: UI shows natural amounts; store Odoo signed balances.
            var scale = parseFloat($inp.data("face-scale"));
            if (isNaN(scale) || !scale) {
                scale = 1;
            }
            var payload = {};
            payload[field] = (isNaN(val) ? 0 : val) * scale;
            return rpc.query({
                model: "audited.financial.line",
                method: "write",
                args: [[lineId], payload],
            }).then(function () {
                return self._loadData();
            }).guardedCatch(function (err) {
                if (err && err.message && err.message.data && err.message.data.message) {
                    window.alert(err.message.data.message);
                }
            });
        },

};

function bindDashboardEvents(host) {
    const root = host.el;
    if (!root || host._afgEventsBound) {
        return;
    }
    host._afgEventsBound = true;
    const specs = host.events || {};
    Object.keys(specs).forEach((spec) => {
        const space = spec.indexOf(" ");
        const eventName = space === -1 ? spec : spec.slice(0, space);
        const selector = space === -1 ? null : spec.slice(space + 1);
        const method = specs[spec];
        $(root).on(eventName, selector, function (ev) {
            if (typeof host[method] === "function") {
                return host[method](ev);
            }
        });
    });
}

function createDashboardHost(component, action) {
    const host = Object.assign({}, dashboardMethods);
    host.el = component.rootRef.el;
    host.$el = $(host.el);
    host.$ = (selector) => (selector === undefined ? host.$el : host.$el.find(selector));
    host.actionService = component.actionService;
    host.do_action = (act, options) => component.actionService.doAction(act, options);
    host.set = () => {};
    host._super = () => Promise.resolve();
    host._afgEventsBound = false;
    const originalStart = host.start;
    host.start = function () {
        bindDashboardEvents(host);
        return originalStart.apply(host, arguments);
    };
    host.init(component, action);
    return host;
}

export class AuditedFinancialsDashboard extends Component {
    static template = "audited_financials_saaskul.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.rootRef = useRef("root");
        rpc._orm = this.orm;
        onMounted(() => {
            const action = this.props.action || this.props;
            this.host = createDashboardHost(this, action);
            const started = this.host.start();
            if (started && typeof started.catch === "function") {
                started.catch(() => {});
            }
        });
        onWillUnmount(() => {
            if (this.host && typeof this.host.destroy === "function") {
                this.host.destroy();
            }
        });
    }
}

registry.category("actions").add("audited_financials_dashboard", AuditedFinancialsDashboard);
