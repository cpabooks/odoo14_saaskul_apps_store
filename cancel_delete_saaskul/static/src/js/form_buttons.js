odoo.define('cancel_delete_saaskul.form_buttons', function (require) {
    'use strict';

    var FormController = require('web.FormController');
    var ActionManager = require('web.ActionManager');
    var CrashManager = require('web.CrashManager').CrashManager;

    var CPA_CD_RELOAD = {
        action_cpa_cd_cancel: true,
        action_cpa_cd_cancel_lines: true,
        action_cpa_cd_cancel_linked: true,
        action_cpa_cd_confirm_post: true,
        action_cpa_cd_reset_draft: true,
    };

    var CPA_CD_WIZARD = {
        action_cpa_cd_delete: true,
        action_cpa_cd_delete_linked: true,
        action_cpa_cd_reverse: true,
    };

    var CPA_CD_MODELS = {
        'account.move': true,
        'account.payment': true,
        'sale.order': true,
        'purchase.order': true,
        'stock.picking': true,
        'stock.inventory': true,
        'hr.expense': true,
    };

    var cpaCdSuppressUntil = 0;
    var cpaCdLeaving = false;

    function cpaCdMissingRecord(error) {
        var raw = '';
        if (error && error.data) {
            raw += ' ' + (error.data.message || '');
            raw += ' ' + (error.data.name || '');
            raw += ' ' + (error.data.debug || '');
        }
        if (error && error.message) {
            raw += ' ' + error.message;
        }
        var match = /Record:\s*([a-z0-9_.]+)\((\d+)/i.exec(raw);
        if (!match || !CPA_CD_MODELS[match[1]]) {
            return null;
        }
        if (!/does not exist or has been deleted/i.test(raw) &&
                (error.data && error.data.name || '').indexOf('MissingError') < 0) {
            return null;
        }
        return {model: match[1], id: match[2]};
    }

    function cpaCdHashMatches(info) {
        var hash = window.location.hash || '';
        return hash.indexOf('model=' + info.model) >= 0 &&
            hash.indexOf('id=' + info.id) >= 0;
    }

    function cpaCdLeaveDeleted() {
        if (cpaCdLeaving) {
            return;
        }
        cpaCdLeaving = true;
        window.setTimeout(function () {
            cpaCdLeaving = false;
        }, 1500);
        var hash = window.location.hash || '';
        window.history.back();
        window.setTimeout(function () {
            if ((window.location.hash || '') !== hash) {
                return;
            }
            window.location.hash = hash
                .replace(/id=\d+&?/, '')
                .replace('view_type=form', 'view_type=list');
        }, 400);
    }

    var FormRenderer = require('web.FormRenderer');

    var CPA_CD_HIDE_HEADER_STRINGS = {
        'Cancel': true,
        'Cancel - Lines': true,
        'Cancel - Linked Docs': true,
        'Confirm / Post': true,
        'Delete': true,
        'Delete - Linked Docs': true,
        'Reverse': true,
        'Duplicate': true,
        'Create for Multico': true,
    };

    FormRenderer.include({
        _renderHeaderButton: function (node) {
            var name = node.attrs && node.attrs.name || '';
            var label = (node.attrs && node.attrs.string || '').trim();
            if (name.indexOf('action_cpa_cd_') === 0 || CPA_CD_HIDE_HEADER_STRINGS[label]) {
                return $();
            }
            return this._super.apply(this, arguments);
        },
    });

    FormController.include({
        _callButtonAction: function (attrs, record) {
            var self = this;
            var name = attrs && attrs.name;
            if (name && (CPA_CD_RELOAD[name] || CPA_CD_WIZARD[name])) {
                record = record || this.model.get(this.handle);
                var recId = record.data && record.data.id;
                if (!recId) {
                    return this._super.apply(this, arguments);
                }
                return this._rpc({
                    model: record.model,
                    method: name,
                    args: [[recId]],
                    kwargs: {context: record.getContext()},
                }).then(function (action) {
                    if (action && action.tag === 'cpa_cd_back') {
                        cpaCdSuppressUntil = Date.now() + 8000;
                        cpaCdLeaveDeleted();
                        return;
                    }
                    if (action && typeof action === 'object' && action.type === 'ir.actions.act_window') {
                        var isDelete = name === 'action_cpa_cd_delete' ||
                            name === 'action_cpa_cd_delete_linked';
                        return self.do_action(action, {
                            on_close: function () {
                                if (isDelete) {
                                    cpaCdSuppressUntil = Date.now() + 8000;
                                    cpaCdLeaveDeleted();
                                    return;
                                }
                                return self.reload();
                            },
                        });
                    }
                    return self.reload().then(function () {
                        if (name === 'action_cpa_cd_reset_draft' && typeof self._setMode === 'function') {
                            return self._setMode('edit');
                        }
                    });
                });
            }
            return this._super.apply(this, arguments);
        },
    });

    ActionManager.include({
        _handleAction: function (action, options) {
            if (action && action.tag === 'cpa_cd_back') {
                cpaCdSuppressUntil = Date.now() + 8000;
                $('.modal').modal('hide');
                cpaCdLeaveDeleted();
                return Promise.resolve();
            }
            return this._super.apply(this, arguments);
        },
    });

    CrashManager.include({
        rpc_error: function (error) {
            var info = cpaCdMissingRecord(error);
            if (info && (Date.now() < cpaCdSuppressUntil || cpaCdHashMatches(info))) {
                if (cpaCdHashMatches(info)) {
                    cpaCdLeaveDeleted();
                }
                return;
            }
            return this._super.apply(this, arguments);
        },
        show_warning: function (error) {
            var info = cpaCdMissingRecord(error);
            if (info && (Date.now() < cpaCdSuppressUntil || cpaCdHashMatches(info))) {
                if (cpaCdHashMatches(info)) {
                    cpaCdLeaveDeleted();
                }
                return;
            }
            return this._super.apply(this, arguments);
        },
    });
});
