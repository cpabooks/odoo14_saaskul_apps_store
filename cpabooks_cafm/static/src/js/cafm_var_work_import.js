odoo.define('cpabooks_cafm.var_work_import', function (require) {
    'use strict';

    var ListController = require('web.ListController');

    ListController.include({
        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            if (!this.$buttons) {
                return;
            }
            if (this.modelName === 'cpabooks.cafm.var.work') {
                if (this.$buttons.find('.o_cpabooks_var_work_format_btn').length === 0) {
                    var $formatBtn = $('<button/>', {
                        type: 'button',
                        class: 'btn btn-secondary btn-sm o_cpabooks_var_work_format_btn ml-1',
                        text: 'Format',
                    });
                    
                    // Insert the button before wrap controls if they exist, else append
                    var $wrapControls = this.$buttons.find('.o_cpabooks_list_wrap_controls');
                    if ($wrapControls.length) {
                        $wrapControls.before($formatBtn);
                    } else {
                        var $wrapToggle = this.$buttons.find('.o_cpabooks_wrap_toggle');
                        if ($wrapToggle.length) {
                            $wrapToggle.parent().before($formatBtn);
                        } else {
                            this.$buttons.append($formatBtn);
                        }
                    }
                    
                    var self = this;
                    $formatBtn.on('click', function () {
                        self.do_action({
                            type: 'ir.actions.act_window',
                            name: 'Import VAR Work',
                            res_model: 'cpabooks.cafm.var.import',
                            views: [[false, 'form']],
                            target: 'new',
                        });
                    });
                }
            }
        },
    });
});
