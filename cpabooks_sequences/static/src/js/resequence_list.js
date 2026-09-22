odoo.define('cpabooks_sequences.resequence_list', function (require) {
    'use strict';

    var ListController = require('web.ListController');

    function isReSequenceAction(action) {
        return action
            && action.res_model === 'ir.sequence'
            && action.context
            && action.context.cpabooks_resequence_list;
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
            return !row.data.cpabooks_sequence_locked;
        });
    }

    function allRowsLocked(rows) {
        return rows.length > 0 && rows.every(function (row) {
            return !!row.data.cpabooks_sequence_locked;
        });
    }

    ListController.include({
        _updateSelectionBox: function () {
            this._super.apply(this, arguments);
            if (isReSequenceAction(this.action)) {
                this.$cpabooksResetBtn = this.$buttons.find('.o_cpabooks_reset_prefix_btn');
                this.$cpabooksLockBtn = this.$buttons.find('.o_cpabooks_lock_toggle_btn');
                this._cpabooksUpdateHeaderButtons();
            }
        },

        _onFieldChanged: function (event) {
            var result = this._super.apply(this, arguments);
            if (
                isReSequenceAction(this.action)
                && event.data.changes
                && Object.prototype.hasOwnProperty.call(event.data.changes, 'cpabooks_sequence_locked')
            ) {
                this._cpabooksUpdateHeaderButtons();
            }
            return result;
        },

        _cpabooksUpdateHeaderButtons: function () {
            var rows = getSelectedRows(this);

            if (this.$cpabooksLockBtn && this.$cpabooksLockBtn.length) {
                var hasSelection = rows.length > 0;
                this.$cpabooksLockBtn.prop('disabled', !hasSelection);
                this.$cpabooksLockBtn.toggleClass('disabled', !hasSelection);
                if (hasSelection) {
                    this.$cpabooksLockBtn.text(
                        allRowsLocked(rows) ? 'Unlock' : 'Lock'
                    );
                } else {
                    this.$cpabooksLockBtn.text('Lock');
                }
            }

            if (this.$cpabooksResetBtn && this.$cpabooksResetBtn.length) {
                var enabled = hasUnlockedRows(rows);
                this.$cpabooksResetBtn.prop('disabled', !enabled);
                this.$cpabooksResetBtn.toggleClass('disabled', !enabled);
            }
        },
    });
});
