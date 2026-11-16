odoo.define('cancel_delete_saaskul.list_action_menu', function (require) {
    'use strict';

    var ListController = require('web.ListController');
    var session = require('web.session');
    var core = require('web.core');

    var _t = core._t;

    var CPA_CD_MODELS = {
        'account.move': true,
        'account.payment': true,
        'sale.order': true,
        'purchase.order': true,
        'stock.picking': true,
        'stock.inventory': true,
        'hr.expense': true,
    };

    var CPA_CD_ITEMS = [
        {method: 'action_cpa_cd_cancel', label: 'Cancel'},
        {method: 'action_cpa_cd_cancel_lines', label: 'Cancel - Lines'},
        {method: 'action_cpa_cd_cancel_linked', label: 'Cancel - Linked Docs'},
        {method: 'action_cpa_cd_confirm_post', label: 'Confirm / Post'},
        {method: 'action_cpa_cd_delete', label: 'Delete'},
        {method: 'action_cpa_cd_delete_linked', label: 'Delete - Linked Docs'},
        {method: 'action_cpa_cd_reset_draft', label: 'Reset to Draft'},
        {method: 'action_cpa_cd_reverse', label: 'Reverse'},
    ];

    function menuHtml() {
        var items = CPA_CD_ITEMS.map(function (item) {
            return '<a class="dropdown-item" href="#" data-cpa-cd-method="' +
                item.method + '">' + item.label + '</a>';
        }).join('');
        return (
            '<div class="btn-group o_cpa_cd_doc_btns ml-1" role="group">' +
                '<button type="button" class="btn btn-secondary btn-sm o_cpa_cd_see_doc">' +
                    _t('See Doc') +
                '</button>' +
                '<button type="button" class="btn btn-primary btn-sm o_cpa_cd_edit">' +
                    _t('Edit') +
                '</button>' +
            '</div>' +
            '<div class="btn-group o_cpa_cd_action_dropdown ml-1" role="group">' +
                '<button type="button" class="btn btn-secondary btn-sm dropdown-toggle" ' +
                    'data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">' +
                    _t('Cancel / Delete') +
                '</button>' +
                '<div class="dropdown-menu">' + items + '</div>' +
            '</div>'
        );
    }

    ListController.include({
        renderButtons: function () {
            this._super.apply(this, arguments);
            this._cpaCdRenderActionMenu();
        },

        updateButtons: function () {
            this._super.apply(this, arguments);
            this._cpaCdRenderActionMenu();
        },

        start: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function (res) {
                self._cpaCdRenderActionMenu();
                window.setTimeout(function () {
                    self._cpaCdRenderActionMenu();
                }, 200);
                window.setTimeout(function () {
                    self._cpaCdRenderActionMenu();
                }, 600);
                return res;
            });
        },

        _cpaCdShouldShowMenu: function () {
            return !!(CPA_CD_MODELS[this.modelName] || this.modelName === 'account.move.line');
        },

        _cpaCdTargetModel: function () {
            return this.modelName === 'account.move.line' ? 'account.move' : this.modelName;
        },

        _cpaCdButtonHosts: function () {
            var $hosts = $();
            if (this.$buttons && this.$buttons.length) {
                $hosts = $hosts.add(this.$buttons);
            }
            var $modal = this.$el && this.$el.closest('.modal');
            if ((!$modal || !$modal.length) && this.$buttons) {
                $modal = this.$buttons.closest('.modal');
            }
            if ($modal && $modal.length) {
                $hosts = $hosts.add($modal.find('.o_cp_buttons'));
            }
            return $hosts;
        },

        _cpaCdRenderActionMenu: function () {
            var self = this;
            if (!this._cpaCdShouldShowMenu()) {
                return;
            }
            session.user_has_group('cancel_delete_saaskul.group_cpa_cancel_delete_global').then(function (hasGroup) {
                if (!hasGroup) {
                    return;
                }
                var $hosts = self._cpaCdButtonHosts();
                if (!$hosts.length) {
                    return;
                }
                $hosts.each(function () {
                    var $host = $(this);
                    if (!$host.length || $host.find('.o_cpa_cd_action_dropdown').length) {
                        return;
                    }
                    var $menu = $(menuHtml());
                    var $wrap = $host.find('.o_cpabooks_list_wrap_controls, .o_cpa_drill_export_excel_btn').last();
                    if ($wrap.length) {
                        $wrap.after($menu);
                    } else {
                        $host.append($menu);
                    }
                    $menu.on('click', 'a[data-cpa-cd-method]', function (ev) {
                        ev.preventDefault();
                        self._cpaCdRun($(ev.currentTarget).data('cpa-cd-method'));
                    });
                    $menu.on('click', '.o_cpa_cd_see_doc', function (ev) {
                        ev.preventDefault();
                        self._cpaCdOpenDoc(false);
                    });
                    $menu.on('click', '.o_cpa_cd_edit', function (ev) {
                        ev.preventDefault();
                        self._cpaCdOpenDoc(true);
                    });
                });
            });
        },

        _cpaCdSelectedIds: function () {
            var self = this;
            var ids = [];
            if (typeof this.getSelectedIds === 'function') {
                ids = this.getSelectedIds() || [];
            }
            if (this.modelName === 'account.move.line') {
                var moveIds = [];
                var seen = {};
                function addMove(mid) {
                    if (mid && typeof mid === 'object') {
                        if (_.isArray(mid)) {
                            mid = mid[0];
                        } else {
                            mid = mid.res_id || mid.id ||
                                (mid.data && (mid.data.id || mid.data.res_id));
                        }
                    }
                    mid = parseInt(mid, 10);
                    if (mid && !seen[mid]) {
                        seen[mid] = true;
                        moveIds.push(mid);
                    }
                }
                var records = [];
                if (typeof this.getSelectedRecords === 'function') {
                    records = this.getSelectedRecords() || [];
                }
                if (!records.length && this.selectedRecords && this.model) {
                    records = _.map(this.selectedRecords, function (dbId) {
                        try {
                            return self.model.get(dbId, {raw: true});
                        } catch (e) {
                            return false;
                        }
                    }).filter(Boolean);
                }
                _.each(records, function (rec) {
                    var data = (rec && rec.data) || rec || {};
                    addMove(data.move_id);
                });
                if (!moveIds.length && this.$el) {
                    this.$el.find('tbody .o_list_record_selector input:checked').closest('tr.o_data_row').each(function () {
                        var dp = $(this).data('id');
                        try {
                            var rec = self.model.get(dp, {raw: true});
                            addMove(rec && rec.data && rec.data.move_id);
                        } catch (e) {
                            return;
                        }
                    });
                }
                if (!moveIds.length && this._cpaCdLastId) {
                    addMove(this._cpaCdLastId);
                }
                return moveIds;
            }
            if (!ids.length && this._cpaCdLastId) {
                ids = [this._cpaCdLastId];
            }
            return ids;
        },

        _cpaCdOpenDoc: function (edit) {
            var self = this;
            var ids = this._cpaCdSelectedIds();
            if (!ids.length) {
                this.do_warn(_t('See Doc'), _t('Select or click a document first.'));
                return;
            }
            var resId = ids[0];
            var targetModel = this._cpaCdTargetModel();
            var inModal = this.$el && this.$el.closest('.modal').length;
            var openForm = function () {
                return self.do_action({
                    type: 'ir.actions.act_window',
                    name: edit ? _t('Edit') : _t('See Doc'),
                    res_model: targetModel,
                    res_id: parseInt(resId, 10),
                    view_mode: 'form',
                    views: [[false, 'form']],
                    target: inModal ? 'new' : 'current',
                    flags: {mode: edit ? 'edit' : 'readonly'},
                    context: {
                        form_view_initial_mode: edit ? 'edit' : 'readonly',
                    },
                }, {
                    replace_last_action: !inModal && self.viewType === 'form',
                });
            };
            if (edit && targetModel === 'account.move') {
                return this._rpc({
                    model: 'account.move',
                    method: 'action_cpa_cd_reset_draft',
                    args: [[resId]],
                    kwargs: {
                        context: {
                            active_model: 'account.move',
                            active_ids: [resId],
                            active_id: resId,
                        },
                    },
                }).then(openForm).guardedCatch(openForm);
            }
            return openForm();
        },

        _cpaCdRun: function (method) {
            var self = this;
            var ids = this._cpaCdSelectedIds();
            if (!ids.length) {
                this.do_warn(_t('Cancel / Delete'), _t('Select or click a document first.'));
                return;
            }
            var targetModel = this._cpaCdTargetModel();
            var ctx = {
                active_model: targetModel,
                active_ids: ids,
                active_id: ids[0],
            };
            if (this.action && this.action.id) {
                ctx.params = {action: this.action.id};
            }
            this._rpc({
                model: targetModel,
                method: method,
                args: [ids],
                kwargs: {context: ctx},
            }).then(function (action) {
                if (action && typeof action === 'object' && action.type === 'ir.actions.act_window' &&
                        action.target === 'new') {
                    var isDelete = method === 'action_cpa_cd_delete' ||
                        method === 'action_cpa_cd_delete_linked';
                    return self.do_action(action, {
                        on_close: function () {
                            if (isDelete && self.viewType === 'form') {
                                return;
                            }
                            self.reload();
                        },
                    });
                }
                return self.reload();
            });
        },
    });
});

odoo.define('cancel_delete_saaskul.scratch_lines', function (require) {
    'use strict';
    var ListRenderer = require('web.ListRenderer');
    ListRenderer.include({
        _renderRow: function (record) {
            var $row = this._super.apply(this, arguments);
            if (record && record.data && record.data.cpa_cd_scratched) {
                $row.addClass('o_cpa_cd_scratch');
            }
            return $row;
        },
    });
});
