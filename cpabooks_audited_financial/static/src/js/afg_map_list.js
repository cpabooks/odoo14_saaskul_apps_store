odoo.define('cpabooks_audited_financial.afg_map_list', function (require) {
    'use strict';

    var ListController = require('web.ListController');
    var ListRenderer = require('web.ListRenderer');
    var core = require('web.core');

    var _t = core._t;

    function afgActionXmlId(widget) {
        var cur = widget;
        var n = 0;
        while (cur && n < 8) {
            if (cur.action && (cur.action.xml_id || cur.action.xmlId)) {
                return cur.action.xml_id || cur.action.xmlId;
            }
            cur = cur.getParent && cur.getParent();
            n += 1;
        }
        return '';
    }

    function afgContext(widget) {
        var ctx = (widget.state && widget.state.context) || {};
        var cur = widget;
        var n = 0;
        while (cur && n < 8) {
            if (cur.action && cur.action.context) {
                ctx = _.extend({}, cur.action.context, ctx);
                break;
            }
            cur = cur.getParent && cur.getParent();
            n += 1;
        }
        return ctx;
    }

    function isAfgMapList(widget) {
        var model = (widget.state && widget.state.model) || widget.modelName || '';
        if (model === 'audited.financial.group' || model === 'audited.financial.ctf.group') {
            return true;
        }
        var ctx = afgContext(widget);
        if (ctx.afg_map_list) {
            return true;
        }
        var xml = afgActionXmlId(widget) || '';
        return xml.indexOf('action_afg_l') !== -1
            || xml.indexOf('action_audited_financial_group') !== -1;
    }

    function groupValue(group) {
        var val = group && group.value;
        if (_.isArray(val)) {
            return val[0];
        }
        return val || '';
    }

    function afgDoAction(widget, action) {
        var cur = widget;
        var n = 0;
        while (cur && n < 10) {
            if (cur.do_action) {
                return cur.do_action(action);
            }
            cur = cur.getParent && cur.getParent();
            n += 1;
        }
        return Promise.resolve();
    }

    function afgSyncLedgerToggle($buttons, expanded) {
        if (!$buttons) {
            return;
        }
        $buttons.find('.o_cpabooks_show_ledgers_toggle').each(function () {
            var $btn = $(this);
            $btn.toggleClass('o_afg_ledgers_expanded active', !!expanded);
            $btn.text(expanded ? _t('Collapse ledgers') : _t('Expand ledgers'));
        });
    }

    ListRenderer.include({
        events: _.extend({}, ListRenderer.prototype.events, {
            'contextmenu tbody tr.o_data_row': '_onAfgContextMenu',
            'contextmenu tbody tr.o_group_header': '_onAfgOdooGroupContextMenu',
        }),

        init: function () {
            this._super.apply(this, arguments);
            this._afgExpanded = {};
            this._afgChildren = {};
        },

        _afgMode: function () {
            return afgContext(this).afg_map_mode || '';
        },

        _afgIsOdooGrouped: function () {
            return !!(this.state.groupedBy && this.state.groupedBy.length);
        },

        _renderGroupRow: function (group, groupLevel) {
            var $row = this._super.apply(this, arguments);
            if (isAfgMapList(this)) {
                $row.attr('data-afg-group-value', groupValue(group));
            }
            return $row;
        },

        _renderView: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                if (isAfgMapList(self) && !self._afgIsOdooGrouped()) {
                    self._afgRestoreExpanded();
                }
            });
        },

        _onRowClicked: function (ev) {
            if (!isAfgMapList(this)) {
                return this._super.apply(this, arguments);
            }
            var $tr = $(ev.currentTarget);
            if ($tr.hasClass('o_group_header')) {
                return this._super.apply(this, arguments);
            }
            if ($tr.hasClass('o_afg_child_row')) {
                ev.stopPropagation();
                ev.preventDefault();
                return;
            }
            if (this._afgIsOdooGrouped()) {
                return this._super.apply(this, arguments);
            }
            if (ev.target.closest('.o_list_record_selector')) {
                return this._super.apply(this, arguments);
            }
            ev.stopPropagation();
            ev.preventDefault();
            var rec = this._afgRecordFromRow($tr);
            if (rec) {
                this._afgToggle(rec.res_id, $tr);
            }
        },

        _afgRecordFromRow: function ($tr) {
            var id = $tr.attr('data-id');
            return _.find(this.state.data || [], function (rec) {
                return String(rec.id) === String(id);
            });
        },

        _afgColspan: function () {
            var cols = (this.columns && this.columns.length) || 1;
            if (this.hasSelectors) {
                cols += 1;
            }
            return cols;
        },

        _renderAfgChildRow: function (child) {
            var $tr = $('<tr/>', {
                'class': 'o_data_row o_afg_child_row',
                'data-account-id': child.id,
            });
            var label = ((child.code || '') + '  ' + (child.name || '')).trim();
            if (this.hasSelectors) {
                $tr.append($('<td/>', {'class': 'o_list_record_selector'}));
            }
            $tr.append($('<td/>', {
                'class': 'o_afg_child_cell',
                colspan: Math.max(1, this._afgColspan() - (this.hasSelectors ? 1 : 0)),
            }).text(label));
            return $tr;
        },

        _afgClearChildRows: function ($tr) {
            var $next = $tr.next();
            while ($next.length && $next.hasClass('o_afg_child_row')) {
                var $drop = $next;
                $next = $next.next();
                $drop.remove();
            }
        },

        _afgInsertChildren: function ($tr, rows) {
            this._afgClearChildRows($tr);
            var $last = $tr;
            var self = this;
            _.each(rows || [], function (child) {
                var $c = self._renderAfgChildRow(child);
                $last.after($c);
                $last = $c;
            });
        },

        _afgRowByResId: function (resId) {
            var self = this;
            var $found = $();
            this.$('tbody tr.o_data_row').not('.o_afg_child_row').each(function () {
                var rec = self._afgRecordFromRow($(this));
                if (rec && rec.res_id === resId) {
                    $found = $(this);
                    return false;
                }
            });
            return $found;
        },

        _afgRestoreExpanded: function () {
            var self = this;
            _.each(this._afgExpanded, function (on, resId) {
                if (!on) {
                    return;
                }
                var $tr = self._afgRowByResId(parseInt(resId, 10) || resId);
                if ($tr.length) {
                    self._afgInsertChildren($tr, self._afgChildren[resId] || []);
                }
            });
        },

        _afgToggle: function (resId, $tr) {
            var self = this;
            if (this._afgExpanded[resId]) {
                delete this._afgExpanded[resId];
                this._afgClearChildRows($tr);
                return Promise.resolve();
            }
            return this._rpc({
                model: this.state.model,
                method: 'afg_map_fetch_children',
                args: [[resId]],
            }).then(function (rows) {
                self._afgExpanded[resId] = true;
                self._afgChildren[resId] = rows || [];
                self._afgInsertChildren($tr, rows || []);
            });
        },

        _afgExpandAll: function (depth) {
            var self = this;
            depth = depth || 0;
            if (depth > 60) {
                return Promise.resolve();
            }
            if (this._afgIsOdooGrouped()) {
                var $closed = this.$('.o_group_header .fa-caret-right').closest('.o_group_header');
                if (!$closed.length) {
                    return Promise.resolve();
                }
                var before = $closed.length;
                $closed.first().trigger('click');
                return new Promise(function (resolve) {
                    setTimeout(function () {
                        var after = self.$('.o_group_header .fa-caret-right').closest('.o_group_header').length;
                        if (after >= before) {
                            resolve();
                            return;
                        }
                        self._afgExpandAll(depth + 1).then(resolve);
                    }, 50);
                });
            }
            var ids = _.map(this.state.data || [], function (rec) { return rec.res_id; });
            if (!ids.length) {
                return Promise.resolve();
            }
            return this._rpc({
                model: this.state.model,
                method: 'afg_map_fetch_children_multi',
                args: [ids],
            }).then(function (map) {
                map = map || {};
                _.each(ids, function (rid) {
                    self._afgExpanded[rid] = true;
                    self._afgChildren[rid] = map[String(rid)] || [];
                    var $tr = self._afgRowByResId(rid);
                    if ($tr.length) {
                        self._afgInsertChildren($tr, self._afgChildren[rid]);
                    }
                });
            });
        },

        _afgCollapseAll: function (depth) {
            var self = this;
            depth = depth || 0;
            if (depth > 60) {
                return Promise.resolve();
            }
            if (this._afgIsOdooGrouped()) {
                var $open = this.$('.o_group_header .fa-caret-down').closest('.o_group_header');
                if (!$open.length) {
                    return Promise.resolve();
                }
                var before = $open.length;
                $open.first().trigger('click');
                return new Promise(function (resolve) {
                    setTimeout(function () {
                        var after = self.$('.o_group_header .fa-caret-down').closest('.o_group_header').length;
                        if (after >= before) {
                            resolve();
                            return;
                        }
                        self._afgCollapseAll(depth + 1).then(resolve);
                    }, 40);
                });
            }
            this._afgExpanded = {};
            this.$('tr.o_afg_child_row').remove();
            return Promise.resolve();
        },

        _onAfgContextMenu: function (ev) {
            if (!isAfgMapList(this)) {
                return;
            }
            var $tr = $(ev.currentTarget);
            if ($tr.hasClass('o_afg_child_row')) {
                ev.preventDefault();
                ev.stopPropagation();
                var accId = parseInt($tr.attr('data-account-id'), 10);
                if (!accId) {
                    return;
                }
                var self = this;
                this._rpc({
                    model: 'account.account',
                    method: 'get_formview_action',
                    args: [[accId]],
                }).then(function (action) {
                    afgDoAction(self, action);
                });
                return;
            }
            if (this._afgIsOdooGrouped()) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            var rec = this._afgRecordFromRow($tr);
            if (!rec) {
                return;
            }
            var widget = this;
            this._rpc({
                model: this.state.model,
                method: 'action_afg_map_popup',
                args: [[rec.res_id]],
            }).then(function (action) {
                afgDoAction(widget, action);
            });
        },

        _onAfgOdooGroupContextMenu: function (ev) {
            if (!isAfgMapList(this)) {
                return;
            }
            ev.preventDefault();
            ev.stopPropagation();
            var val = $(ev.currentTarget).attr('data-afg-group-value') || '';
            var mode = this._afgMode();
            var widget = this;
            var def;
            if (mode === 'ctf' || this.state.groupedBy && this.state.groupedBy[0] === 'ctf_category') {
                def = this._rpc({
                    model: 'account.account',
                    method: 'action_afg_map_popup_ctf',
                    args: [val],
                });
            } else {
                var gid = parseInt(val, 10);
                if (!gid) {
                    return;
                }
                def = this._rpc({
                    model: 'account.group',
                    method: 'action_afg_map_popup',
                    args: [[gid]],
                });
            }
            def.then(function (action) {
                afgDoAction(widget, action);
            });
        },
    });

    ListController.include({
        willStart: function () {
            var self = this;
            var args = arguments;
            var superFn = this._super.bind(this);
            var model = this.modelName || (this.action && this.action.res_model) || '';
            var xml = (this.action && (this.action.xml_id || this.action.xmlId)) || '';
            var ctx = (this.action && this.action.context) || {};
            var isAfg = model === 'audited.financial.group'
                || model === 'audited.financial.ctf.group'
                || ctx.afg_map_list
                || xml.indexOf('action_afg_l') !== -1
                || xml.indexOf('action_audited_financial_group') !== -1;
            var prep = Promise.resolve();
            if (isAfg && (model === 'audited.financial.ctf.group' || ctx.afg_map_mode === 'ctf' || xml.indexOf('action_afg_l1') !== -1)) {
                prep = this._rpc({
                    model: 'audited.financial.ctf.group',
                    method: 'action_setup_default_ctf_groups',
                    args: [],
                }).then(function () {
                    return self._rpc({
                        model: 'account.account',
                        method: 'action_afg_ensure_ctf_map',
                        args: [],
                    });
                });
            } else if (isAfg && model === 'audited.financial.group') {
                prep = this._rpc({
                    model: 'audited.financial.group',
                    method: 'action_afg_ensure_standard_map',
                    args: [],
                });
            } else if (isAfg && (ctx.afg_map_mode === 'ctf' || xml.indexOf('action_afg_l1') !== -1)) {
                prep = this._rpc({
                    model: 'account.account',
                    method: 'action_afg_ensure_ctf_map',
                    args: [],
                });
            }
            return prep.then(function () {
                return superFn.apply(self, args);
            });
        },

        renderButtons: function () {
            this._super.apply(this, arguments);
            if (!this.$buttons) {
                return;
            }
            var model = this.modelName || (this.action && this.action.res_model) || '';
            var xml = (this.action && (this.action.xml_id || this.action.xmlId)) || '';
            var ctx = (this.action && this.action.context) || {};
            var isAfg = model === 'audited.financial.group'
                || model === 'audited.financial.ctf.group'
                || ctx.afg_map_list
                || xml.indexOf('action_afg_l') !== -1
                || xml.indexOf('action_audited_financial_group') !== -1;
            if (!isAfg) {
                return;
            }
            var self = this;
            if (!this.$buttons.find('.o_afg_btn_collapse').length) {
                var $collapse = $('<button type="button" class="btn btn-secondary o_afg_btn_collapse"/>')
                    .text(_t('Collapse'));
                this.$buttons.append($collapse);
                $collapse.on('click', function () {
                    self.renderer && self.renderer._afgCollapseAll && self.renderer._afgCollapseAll();
                    afgSyncLedgerToggle(self.$buttons, false);
                });
            }
            setTimeout(function () {
                if (!self.$buttons) {
                    return;
                }
                self.$buttons.find('.o_afg_btn_expand').remove();
                self.$buttons.find('.o_cpabooks_show_ledgers_toggle').each(function () {
                    var el = this;
                    if (el.getAttribute('data-afg-bound') === '1') {
                        return;
                    }
                    el.setAttribute('data-afg-bound', '1');
                    el.addEventListener('click', function (ev) {
                        ev.preventDefault();
                        ev.stopImmediatePropagation();
                        var $btn = $(el);
                        var on = !$btn.hasClass('o_afg_ledgers_expanded');
                        afgSyncLedgerToggle(self.$buttons, on);
                        if (on) {
                            self.renderer && self.renderer._afgExpandAll && self.renderer._afgExpandAll();
                        } else {
                            self.renderer && self.renderer._afgCollapseAll && self.renderer._afgCollapseAll();
                        }
                    }, true);
                });
            }, 300);
        },
    });
});
