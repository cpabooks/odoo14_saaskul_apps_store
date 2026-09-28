odoo.define("cpabooks_faff.wizard_progress_html", function (require) {
    "use strict";

    var AbstractField = require("web.AbstractField");
    var fieldRegistry = require("web.field_registry");

    var FaffWizardProgressHtml = AbstractField.extend({
        className: "o_field_faff_wiz_progress_html",
        supportedFieldTypes: ["html", "char", "text"],

        _decodeEntities: function (value) {
            if (!value) {
                return "";
            }
            var text = String(value);
            if (text.indexOf("&lt;") === -1 && text.indexOf("&#") === -1) {
                return text;
            }
            var textarea = document.createElement("textarea");
            textarea.innerHTML = text;
            return textarea.value;
        },

        _renderReadonly: function () {
            this.$el.empty();
            var html = this._decodeEntities(this.value || "");
            if (html) {
                $('<div class="o_faff_wiz_progress_wrap"/>').html(html).appendTo(this.$el);
            }
        },

        _renderEdit: function () {
            this._renderReadonly();
        },

        reset: function (record, event) {
            this._super.apply(this, arguments);
            if (!event || event.target !== this) {
                this._render();
            }
        },
    });

    fieldRegistry.add("faff_wizard_progress_html", FaffWizardProgressHtml);
    return FaffWizardProgressHtml;
});
