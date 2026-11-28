/** @odoo-module **/
/* Minimal Odoo 14 legacy adapter for the CAFM client actions (Odoo 19).
 * Old files call odoo.define-style factories; this shim provides AbstractAction,
 * core.action_registry, rpc and session, and mounts each action as an OWL component. */

import { Component, onMounted, onWillUnmount, useRef, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";

const $ = window.jQuery;
const TEMPLATES = {
 "SaaskulCafmDashboard": "<div class=\"cfd_root o_cfd_dashboard_main cpa-cafm-theme-default\">\n            <div class=\"o_cfd_dashboard_root\">\n                <section class=\"o_cfd_dash_header\">\n                    <div class=\"o_cfd_dash_header_row\">\n                        <div class=\"o_cfd_dash_header_left\">\n                            <div class=\"cfd_eyebrow\" id=\"cfd_eyebrow\">CAFM</div>\n                            <h1 class=\"o_cfd_dash_title\" id=\"cfd_title\">CAFM Operations Dashboard</h1>\n                            <p class=\"o_cfd_dash_subtitle\" id=\"cfd_subtitle\"></p>\n                        </div>\n                        <div class=\"o_cfd_dash_header_actions\">\n                            <div class=\"cpa-cafm-theme-toggle\" role=\"group\" aria-label=\"Dashboard theme\">\n                                <button type=\"button\" class=\"cpa-cafm-theme-btn\" data-theme=\"dark\" title=\"Dark theme\">\n                                    <i class=\"fa fa-moon-o\"/> Dark\n                                </button>\n                                <button type=\"button\" class=\"cpa-cafm-theme-btn active\" data-theme=\"default\" title=\"Default (light) theme\">\n                                    <i class=\"fa fa-sun-o\"/> Default\n                                </button>\n                            </div>\n                            <button type=\"button\" class=\"btn btn-sm o_cfd_open_main_menu\" title=\"Open apps menu\">\n                                <i class=\"fa fa-th\"/> Main Menu\n                            </button>\n                        </div>\n                    </div>\n                </section>\n\n                <div class=\"cfd_loading\" id=\"cfd_loading\">Loading dashboard\u2026</div>\n                <div class=\"cfd_load_error\" id=\"cfd_load_error\" style=\"display:none;\"/>\n\n                <section class=\"o_cfd_analytics_panel\">\n                    <div class=\"o_cfd_completion_head\">\n                        <div>\n                            <h2 class=\"o_cfd_analytics_title\" id=\"cfd_completion_title\">Call completion</h2>\n                            <p class=\"o_cfd_analytics_hint\" id=\"cfd_completion_hint\"></p>\n                        </div>\n                    </div>\n                    <div class=\"o_cfd_completion_kpis\" id=\"cfd_completion_kpis\"/>\n\n                    <div class=\"o_cfd_charts_grid\">\n                        <article class=\"o_cfd_chart_card\">\n                            <div class=\"o_cfd_chart_head\">\n                                <h3 class=\"o_cfd_chart_title\" id=\"cfd_chart_month_title\">Last Month vs Current Month</h3>\n                                <p class=\"o_cfd_chart_subtitle\" id=\"cfd_chart_month_subtitle\"></p>\n                            </div>\n                            <div class=\"o_cfd_chart_canvas_wrap\">\n                                <canvas id=\"cfd_chart_month\"/>\n                            </div>\n                        </article>\n                        <article class=\"o_cfd_chart_card\">\n                            <div class=\"o_cfd_chart_head\">\n                                <h3 class=\"o_cfd_chart_title\" id=\"cfd_chart_year_title\">Last Year vs Current Year</h3>\n                                <p class=\"o_cfd_chart_subtitle\" id=\"cfd_chart_year_subtitle\"></p>\n                            </div>\n                            <div class=\"o_cfd_chart_canvas_wrap\">\n                                <canvas id=\"cfd_chart_year\"/>\n                            </div>\n                        </article>\n                    </div>\n                </section>\n\n                <div class=\"o_cfd_dash_kpis\"/>\n\n                <div class=\"o_cfd_dash_workflow\"/>\n            </div>\n        </div>",
 "SaaskulCafmHowItWorks": "<div class=\"o_cafm_how_root\">\n            <div class=\"o_cafm_how_header text-center mb-3\">\n                <h2 t-esc=\"widget.pageTitle\"/>\n                <p class=\"text-muted mb-0\">\n                    Vertical flowchart (top) and round process cycle (bottom). Click any step to open that screen.\n                </p>\n            </div>\n\n            <h3 class=\"o_cafm_how_section_title\">Flow Chart (vertical)</h3>\n            <div class=\"o_cafm_flow_tree o_cafm_how_flow\"/>\n\n            <hr class=\"o_cafm_how_divider\"/>\n\n            <h3 class=\"o_cafm_how_section_title\">Process Cycle (round)</h3>\n            <div class=\"o_cafm_cycle_viewport\">\n                <div class=\"o_cafm_cycle_stage\">\n                    <div class=\"o_cafm_cycle_center\">\n                        <div class=\"o_cafm_cycle_center_title\" t-esc=\"widget.centerTitle\"/>\n                        <div class=\"o_cafm_cycle_center_sub\">Full Process</div>\n                    </div>\n                    <div class=\"o_cafm_cycle_ring\"/>\n                    <svg class=\"o_cafm_cycle_arrow_ring\" viewBox=\"0 0 520 520\" aria-hidden=\"true\">\n                        <circle cx=\"260\" cy=\"260\" r=\"210\" fill=\"none\"\n                                stroke=\"rgba(255,255,255,0.12)\" stroke-width=\"2\"\n                                stroke-dasharray=\"8 10\"/>\n                    </svg>\n                </div>\n            </div>\n            <div class=\"o_cafm_cycle_legend row justify-content-center mt-3 mb-4\">\n                <div class=\"col-auto\"><span class=\"o_cafm_cycle_legend_dot o_cafm_theme_contract\"/> Contract</div>\n                <div class=\"col-auto\"><span class=\"o_cafm_cycle_legend_dot o_cafm_theme_ops\"/> Operations</div>\n                <div class=\"col-auto\"><span class=\"o_cafm_cycle_legend_dot o_cafm_theme_materials\"/> Materials</div>\n                <div class=\"col-auto\"><span class=\"o_cafm_cycle_legend_dot o_cafm_theme_billing\"/> Billing</div>\n            </div>\n        </div>",
 "SaaskulCafmAmcXView": "<div class=\"o_cafm_x_view_root\">\n            <div class=\"o_cafm_x_mount\"/>\n        </div>",
 "SaaskulCafmAmcInvoiceStatusView": "<div class=\"o_cafm_invoice_status_root\">\n\n            <div class=\"o_cafm_invoice_status_mount\"/>\n\n        </div>"
};

function withGuarded(promise) {
    promise.guardedCatch = (fn) => withGuarded(promise.catch(fn));
    const then = promise.then.bind(promise);
    promise.then = (a, b) => withGuarded(then(a, b));
    return promise;
}

function callKw(params) {
    return withGuarded(rpc(`/web/dataset/call_kw/${params.model}/${params.method}`, {
        model: params.model,
        method: params.method,
        args: params.args || [],
        kwargs: params.kwargs || {},
    }));
}

/** Renders the small static legacy templates (only t-esc="widget.x" is used). */
function renderTemplate(name, widget) {
    const host = document.createElement("div");
    host.innerHTML = TEMPLATES[name] || "";
    for (const el of host.querySelectorAll("[t-esc]")) {
        const expr = el.getAttribute("t-esc");
        el.removeAttribute("t-esc");
        const value = expr.startsWith("widget.") ? widget[expr.slice(7)] : "";
        el.textContent = value === undefined || value === null ? "" : value;
    }
    return host.innerHTML;
}

function wrapSuper(proto, base) {
    const out = {};
    for (const [key, value] of Object.entries(proto)) {
        if (typeof value === "function" && typeof base[key] === "function" && /_super/.test(value.toString())) {
            out[key] = function (...args) {
                const prev = this._super;
                this._super = base[key];
                try {
                    return value.apply(this, args);
                } finally {
                    this._super = prev;
                }
            };
        } else {
            out[key] = value;
        }
    }
    return out;
}

const BaseAction = {
    init(parent, action) {
        this.action = action || {};
    },
    start() {
        return withGuarded(Promise.resolve());
    },
    destroy() {},
    on_attach_callback() {},
    set() {},
    $(selector) {
        return this.$el.find(selector);
    },
    _rpc(params) {
        return callKw(params);
    },
    do_action(action, options) {
        return withGuarded(Promise.resolve(this.__env.services.action.doAction(action, options || {})));
    },
    do_warn(title, message) {
        this.__env.services.notification.add(message || title, { type: "warning", title });
    },
    do_notify(title, message) {
        this.__env.services.notification.add(message || title, { title });
    },
};

function makeClass(proto) {
    const Cls = { prototype: proto };
    Cls.extend = (child) => makeClass(Object.assign(Object.create(proto), wrapSuper(child, proto)));
    return Cls;
}

function toOwl(LegacyCls) {
    return class LegacyCafmAction extends Component {
        static template = xml`<div class="o_action o_cafm_legacy_action h-100 overflow-auto" t-ref="root"/>`;
        static props = ["*"];

        setup() {
            this.root = useRef("root");
            onMounted(async () => {
                const w = Object.create(LegacyCls.prototype);
                w.__env = this.env;
                w.init(null, this.props.action);
                w.$el = $(this.root.el);
                if (w.className) {
                    w.$el.addClass(w.className);
                }
                if (w.contentTemplate) {
                    w.$el.html(renderTemplate(w.contentTemplate, w));
                }
                for (const [spec, handler] of Object.entries(w.events || {})) {
                    const idx = spec.indexOf(" ");
                    const evt = idx < 0 ? spec : spec.slice(0, idx);
                    const sel = idx < 0 ? undefined : spec.slice(idx + 1);
                    const fn = typeof handler === "string" ? w[handler] : handler;
                    w.$el.on(evt, sel, fn.bind(w));
                }
                this.widget = w;
                await w.start();
                w.on_attach_callback();
            });
            onWillUnmount(() => this.widget && this.widget.destroy());
        }
    };
}

const session = {
    get uid() {
        return user.userId;
    },
    user_has_group(group) {
        return withGuarded(Promise.resolve(user.hasGroup(group)));
    },
};

const MODULES = {
    "web.AbstractAction": makeClass(BaseAction),
    "web.core": {
        _t: (s) => s,
        _lt: (s) => s,
        bus: { on() {}, off() {}, trigger() {} },
        action_registry: {
            add(tag, Cls) {
                registry.category("actions").add(tag, toOwl(Cls), { force: true });
            },
        },
    },
    "web.rpc": { query: callKw },
    "web.session": session,
};

function legacyRequire(name) {
    if (!(name in MODULES)) {
        throw new Error(`Legacy module ${name} is not available in Odoo 19`);
    }
    return MODULES[name];
}

function define(name, factory) {
    try {
        MODULES[name] = factory(legacyRequire);
    } catch (error) {
        console.error(`CAFM legacy module ${name} failed`, error);
    }
}

const queue = window.__cafmLegacyQueue || [];
window.__cafmLegacyQueue = { push: ([name, factory]) => define(name, factory) };
for (const [name, factory] of queue) {
    define(name, factory);
}
