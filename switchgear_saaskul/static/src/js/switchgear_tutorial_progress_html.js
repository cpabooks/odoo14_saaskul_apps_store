odoo.define('switchgear_saaskul.tutorial_progress_html', function (require) {
'use strict';

var AbstractField = require('web.AbstractField');
var fieldRegistry = require('web.field_registry');

/**
 * Render tutorial sidebar HTML (avoid escaped markup as plain text).
 */
var TutorialProgressHtml = AbstractField.extend({
    className: 'o_field_sg_tutorial_progress_html',
    supportedFieldTypes: ['html', 'char', 'text'],

    _decodeEntities: function (value) {
        if (!value) {
            return '';
        }
        var text = String(value);
        if (text.indexOf('&lt;') === -1 && text.indexOf('&#') === -1) {
            return text;
        }
        var textarea = document.createElement('textarea');
        textarea.innerHTML = text;
        return textarea.value;
    },

    _renderReadonly: function () {
        this.$el.empty();
        var html = this._decodeEntities(this.value || '');
        if (html) {
            $('<div class="o_sg_tut_progress_wrap"/>').html(html).appendTo(this.$el);
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

fieldRegistry.add('sg_tutorial_progress_html', TutorialProgressHtml);

return TutorialProgressHtml;
});
