odoo.define('cpabooks_cafm.var_import_confirm', function (require) {
'use strict';

/**
 * Before Test/Import on VAR Work Report: ask to create missing L2/L3/etc.
 */
var DataImport = require('base_import.import').DataImport;

DataImport.include({
    call_import: function (kwargs) {
        var self = this;
        var _super = this._super.bind(this);
        if (this.res_model !== 'cpabooks.cafm.var.work') {
            return _super(kwargs);
        }
        var fields = this.$('.oe_import_fields input.oe_import_match_field').map(function (index, el) {
            return $(el).select2('val') || false;
        }).get();
        var columns = this.$('.oe_import_grid-header .oe_import_grid-cell .o_import_header_name').map(function () {
            return $(this).text().trim().toLowerCase() || false;
        }).get();
        var opts = this.import_options();
        return this._rpc({
            model: 'base_import.import',
            method: 'var_preview_missing_related',
            args: [this.id, fields, columns, opts],
        }).then(function (preview) {
            if (preview && preview.message) {
                if (!window.confirm(preview.message)) {
                    return $.Deferred().reject();
                }
            }
            return _super(kwargs);
        });
    },
});
});
