odoo.define("cpabooks_cafm.mbt_report", function (require) {
    "use strict";

    var pfx = "o_cafm_mbt";

    function show(el, on) {
        if (!el) {
            return;
        }
        if (on) {
            el.classList.remove(pfx + "_hidden");
        } else {
            el.classList.add(pfx + "_hidden");
        }
    }

    window[pfx + "_toggle_l1"] = function (ev, row) {
        if (ev.target.closest("a")) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        row.classList.toggle(pfx + "_open");
        var open = row.classList.contains(pfx + "_open");
        var cid = row.getAttribute("data-cafm-id");
        var table = row.closest("table");
        var l2 = table.querySelectorAll("tr." + pfx + "_child_of_" + cid + "[data-cafm-level='2']");
        for (var i = 0; i < l2.length; i++) {
            show(l2[i], open);
            if (!open) {
                var pid = l2[i].getAttribute("data-cafm-id");
                var l3 = table.querySelectorAll("tr." + pfx + "_child_of_" + pid + "[data-cafm-level='3']");
                for (var j = 0; j < l3.length; j++) {
                    show(l3[j], false);
                }
                l2[i].classList.remove(pfx + "_open");
            }
        }
    };

    window[pfx + "_toggle_l2"] = function (ev, row) {
        if (ev.target.closest("a")) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        var trC = row.getAttribute("data-cafm-parent");
        var table = row.closest("table");
        var crow = table.querySelector("tr[data-cafm-id='" + trC + "'][data-cafm-level='1']");
        if (!crow || !crow.classList.contains(pfx + "_open")) {
            return;
        }
        row.classList.toggle(pfx + "_open");
        var open = row.classList.contains(pfx + "_open");
        var pid = row.getAttribute("data-cafm-id");
        var l3 = table.querySelectorAll("tr." + pfx + "_child_of_" + pid + "[data-cafm-level='3']");
        for (var k = 0; k < l3.length; k++) {
            show(l3[k], open);
        }
    };

    window[pfx + "_apply_hierarchy_flags"] = function (wrap) {
        var t = wrap.querySelector("table." + pfx + "_table");
        if (!t) {
            return;
        }
        var ap = wrap.getAttribute("data-cafm-ap") === "1";
        var ao = wrap.getAttribute("data-cafm-ao") === "1";
        var l1rows = t.querySelectorAll("tr[data-cafm-level='1']");
        for (var a = 0; a < l1rows.length; a++) {
            var r1 = l1rows[a];
            if (ap) {
                r1.classList.add(pfx + "_open");
            } else {
                r1.classList.remove(pfx + "_open");
            }
            var id1 = r1.getAttribute("data-cafm-id");
            var l2s = t.querySelectorAll("tr." + pfx + "_child_of_" + id1 + "[data-cafm-level='2']");
            for (var b = 0; b < l2s.length; b++) {
                show(l2s[b], ap);
                if (ao) {
                    l2s[b].classList.add(pfx + "_open");
                } else {
                    l2s[b].classList.remove(pfx + "_open");
                }
                var id2 = l2s[b].getAttribute("data-cafm-id");
                var l3s = t.querySelectorAll("tr." + pfx + "_child_of_" + id2 + "[data-cafm-level='3']");
                for (var c = 0; c < l3s.length; c++) {
                    show(l3s[c], ap && ao);
                }
            }
        }
    };

    function applyAll() {
        var wraps = document.querySelectorAll("." + pfx + "_wrap");
        for (var i = 0; i < wraps.length; i++) {
            window[pfx + "_apply_hierarchy_flags"](wraps[i]);
        }
    }

    // Re-bind after Odoo form / HTML field updates
    var core = require("web.core");
    core.bus.on("DOM_updated", null, function () {
        window.setTimeout(applyAll, 0);
    });
    $(document).ready(function () {
        window.setTimeout(applyAll, 50);
    });

    return {
        applyAll: applyAll,
    };
});
