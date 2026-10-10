odoo.define('re_sequences_saaskul.resequence_list', function (require) {
    'use strict';

    var ListController = require('web.ListController');

    function isReSequenceAction(action) {
        return action
            && action.res_model === 'ir.sequence'
            && action.context
            && action.context.saaskul_resequence_list;
    }

    function getSelectedRows(controller) {
        return (controller.getSelectedRecords() || []).map(function (record) {
            return {
                id: record.res_id,
                data: record.data || {},
            };
        });
    }

    function hasUnlockedRows(rows) {
        return rows.some(function (row) {
            return !row.data.saaskul_sequence_locked;
        });
    }

    function allRowsLocked(rows) {
        return rows.length > 0 && rows.every(function (row) {
            return !!row.data.saaskul_sequence_locked;
        });
    }

    ListController.include({
        _updateSelectionBox: function () {
            this._super.apply(this, arguments);
            if (isReSequenceAction(this.action)) {
                this.$saaskulResetBtn = this.$buttons.find('.o_saaskul_reset_prefix_btn');
                this.$saaskulLockBtn = this.$buttons.find('.o_saaskul_lock_toggle_btn');
                this._saaskulUpdateHeaderButtons();
            }
        },

        _onFieldChanged: function (event) {
            var result = this._super.apply(this, arguments);
            if (
                isReSequenceAction(this.action)
                && event.data.changes
                && Object.prototype.hasOwnProperty.call(event.data.changes, 'saaskul_sequence_locked')
            ) {
                this._saaskulUpdateHeaderButtons();
            }
            return result;
        },

        _saaskulUpdateHeaderButtons: function () {
            var rows = getSelectedRows(this);

            if (this.$saaskulLockBtn && this.$saaskulLockBtn.length) {
                var hasSelection = rows.length > 0;
                this.$saaskulLockBtn.prop('disabled', !hasSelection);
                this.$saaskulLockBtn.toggleClass('disabled', !hasSelection);
                if (hasSelection) {
                    this.$saaskulLockBtn.text(
                        allRowsLocked(rows) ? 'Unlock' : 'Lock'
                    );
                } else {
                    this.$saaskulLockBtn.text('Lock');
                }
            }

            if (this.$saaskulResetBtn && this.$saaskulResetBtn.length) {
                var enabled = hasUnlockedRows(rows);
                this.$saaskulResetBtn.prop('disabled', !enabled);
                this.$saaskulResetBtn.toggleClass('disabled', !enabled);
            }
        },
    });
});
