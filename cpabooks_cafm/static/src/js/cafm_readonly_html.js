odoo.define("cpabooks_cafm.readonly_html", function (require) {
    "use strict";

    /**
     * Readonly HTML for CAFM report tables (Monthly Billing, PPM grid, …).
     *
     * Community registers widget "html" as FieldText → .text() shows markup as
     * plain text. web_editor FieldHtml also loads Wysiwyg even for readonly and
     * can still fall through to text in edit mode. Always paint with .html().
     */
    var AbstractField = require("web.AbstractField");
    var fieldRegistry = require("web.field_registry");

    function decodeHtmlMarkup(value) {
        value = value || "";
        if (value.indexOf("<div") !== -1 || value.indexOf("<table") !== -1) {
            return value;
        }
        if (value.indexOf("&lt;") === -1) {
            return value;
        }
        return $("<textarea/>").html(value).text();
    }

    function paintHtml($el, value) {
        if (!$el || !$el.length) {
            return;
        }
        var html = decodeHtmlMarkup(String(value || ""));
        if ($el.is("textarea")) {
            var $host = $(
                '<div class="o_field_widget o_field_cafm_readonly_html o_readonly"/>'
            );
            $host.attr("name", $el.attr("name") || "");
            $('<div class="cafm_readonly_html"/>').html(html).appendTo($host);
            $el.replaceWith($host);
            return $host;
        }
        $el.empty();
        $el.removeClass("o_field_text o_field_html").addClass(
            "o_field_cafm_readonly_html o_readonly"
        );
        $('<div class="cafm_readonly_html"/>').html(html).appendTo($el);
        return $el;
    }

    var FieldCafmReadonlyHtml = AbstractField.extend({
        className: "o_field_cafm_readonly_html",
        supportedFieldTypes: ["html", "char", "text"],
        formatType: "html",
        _render: function () {
            paintHtml(this.$el, this.value);
        },
        _renderEdit: function () {
            paintHtml(this.$el, this.value);
        },
        _renderReadonly: function () {
            paintHtml(this.$el, this.value);
        },
    });

    if (fieldRegistry.contains("cafm_readonly_html")) {
        fieldRegistry.map.cafm_readonly_html = FieldCafmReadonlyHtml;
    } else {
        fieldRegistry.add("cafm_readonly_html", FieldCafmReadonlyHtml);
    }

    return FieldCafmReadonlyHtml;
});
