odoo.define('saaskul_field_service.fsm_task_form', function (require) {
    "use strict";

    var basicFields = require('web.basic_fields');
    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');
    var FormController = require('web.FormController');
    var core = require('web.core');
    var _t = core._t;

    var FieldText = basicFields.FieldText;
    var SINGLE_LINE_FSM_TEXT_FIELDS = ['site_visit', 'closing_remarks'];
    var TMC_TAB_NAMES = ['timesheets_tab', 'client_tms', 'material_request', 'internal_timesheet', 'customer_material', 'customer_labour_cost'];
    var TAB_STORAGE_PREFIX = 'cpabooks_crn_task_tab_';
    var FSM_STAGE_FOCUS_FIELDS = {
        0: 'partner_id',
        1: 'visited_by',
        2: 'fsm_assigned_employee_id',
        3: 'fsm_assigned_employee_id',
        4: 'date_end',
        5: 'select_invoice',
        6: 'closing_remarks',
    };
    var FSM_SERIAL_TO_FIELD = {
        '4': 'partner_id',
        '5': 'site_location',
        '6': 'client_person',
        '7': 'client_contact',
        '8': 'client_email',
        '9': 'complaint_type',
        '10': 'invoice_id',
        '11': 'qt_no',
        '12': 'item_des',
        '13': 'invoice_type',
        '14': 'crn_done_before',
        '15': 'project_id',
        '16': 'complaint_title',
        '17': 'complaint_details',
        '18': 'deadline',
        '19': 'importance',
        '20': 'total_print_row',
        '21': 'visited_by',
        '22': 'visited_date',
        '23': 'site_visit',
        '24': 'next_action',
        '27': 'fsm_assigned_employee_id',
        '28': 'assign_date',
        '29': 'date_end',
        '30': 'fsm_invoice_progress_status',
        '32': 'material_cost_total',
        '33': 'timesheet_cost_total',
        '34': 'fsm_transport_cost',
        '35': 'fsm_other_cost',
        '36': 'total_service_cost',
        '37': 'closing_remarks',
    };
    var FSM_BLINK_CLASS = 'cpabooks_fsm_nav_bubble_red';
    var FSM_BLINK_MS = 2600;
    var FSM_PENDING_PREVIEW_COUNT = 5;
    var FSM_POINTER_TRAIL_COUNT = 5;
    var FSM_GUIDE_RAY_MS = 1400;
    var FSM_SCROLL_OFFSET = 180;
    var FSM_STAGE_FIELD_NAMES = {
        0: ['partner_id', 'site_location', 'client_person', 'client_contact', 'client_email', 'complaint_type', 'invoice_id', 'qt_no', 'qt_no_text', 'item_des', 'invoice_type', 'project_id', 'complaint_title', 'deadline', 'importance', 'total_print_row', 'crn_done_before'],
        1: ['visited_by', 'visited_date', 'site_visit', 'next_action'],
        2: ['fsm_quotation_id', 'fsm_quotation_status'],
        3: ['fsm_quotation_approval_status'],
        4: ['fsm_assigned_employee_id', 'assign_date', 'date_end'],
        5: ['select_invoice'],
        6: ['closing_remarks', 'material_cost_total', 'timesheet_cost_total', 'total_service_cost'],
    };

    FieldText.include({
        init: function () {
            this._super.apply(this, arguments);
            if (this.model === 'project.task' && SINGLE_LINE_FSM_TEXT_FIELDS.indexOf(this.name) !== -1) {
                this.autoResizeOptions = _.extend({}, this.autoResizeOptions, {
                    min_height: 24,
                });
            }
        },
    });

    FormController.include({
        /**
         * Always place FULL EDIT under the control-panel EDIT button for CRN forms.
         */
        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            if (this.modelName === 'project.task') {
                this._cpabooksEnsureFsmFormChrome();
            }
        },

        on_attach_callback: function () {
            this._super.apply(this, arguments);
            if (this.modelName === 'project.task') {
                this._cpabooksEnsureFsmFormChrome();
            }
        },

        _cpabooksEnsureFsmFormChrome: function () {
            this._cpabooksHideFsmFormCreateButton();
            this._cpabooksEnsureFsmFullEditButton();
        },

        /**
         * CRN form: hide control-panel CREATE (create from list only).
         */
        _cpabooksHideFsmFormCreateButton: function () {
            var state = this.renderer && this.renderer.state;
            var $create = $();
            if (this.$buttons && this.$buttons.length) {
                $create = $create.add(this.$buttons.find('.o_form_button_create'));
            }
            $create = $create.add($('.o_control_panel .o_cp_buttons .o_form_button_create'));
            if (this.modelName === 'project.task' && this._cpabooksFsmFormActive(state)) {
                $create.addClass('d-none o_hidden').hide();
            } else {
                $create.removeClass('d-none o_hidden').show();
            }
        },

        _cpabooksEnsureFsmProjectBeforeSave: function () {
            var self = this;
            if (!this.renderer || !this.handle) {
                return Promise.resolve();
            }
            var state = this.renderer.state;
            if (!this._cpabooksFsmFormActive(state) || state.data.project_id) {
                return Promise.resolve();
            }
            var ctx = (this.initialState && this.initialState.context) || {};
            return this._rpc({
                model: 'project.task',
                method: 'default_get',
                args: [['project_id']],
                kwargs: {context: ctx},
            }).then(function (defaults) {
                if (defaults && defaults.project_id) {
                    return self.model.notifyChanges(self.handle, {
                        project_id: defaults.project_id,
                    });
                }
            });
        },

        _cpabooksGetFsmResId: function () {
            if (this.handle && this.model) {
                var record = this.model.get(this.handle);
                if (record && record.res_id) {
                    return record.res_id;
                }
            }
            if (this.renderer && this.renderer.state && this.renderer.state.res_id) {
                return this.renderer.state.res_id;
            }
            if (this.initialState && this.initialState.res_id) {
                return this.initialState.res_id;
            }
            return false;
        },

        _cpabooksGetTaskTabStorageKey: function () {
            var resId = this._cpabooksGetFsmResId();
            return resId ? TAB_STORAGE_PREFIX + resId : null;
        },

        _cpabooksSaveActiveTaskTab: function ($notebook) {
            var key = this._cpabooksGetTaskTabStorageKey();
            if (!key || !$notebook || !$notebook.length) {
                return;
            }
            var $active = $notebook.find('.nav-tabs .nav-link.active');
            if ($active.length) {
                var tabName = $active.attr('data-name') || $active.data('name');
                if (tabName) {
                    window.sessionStorage.setItem(key, tabName);
                }
            }
        },

        _cpabooksRestoreActiveTaskTab: function () {
            if (this.modelName !== 'project.task') {
                return;
            }
            var key = this._cpabooksGetTaskTabStorageKey();
            if (!key || !this.renderer) {
                return;
            }
            var tabName = window.sessionStorage.getItem(key);
            if (!tabName || TMC_TAB_NAMES.indexOf(tabName) === -1) {
                return;
            }
            var self = this;
            this.renderer.$('.o_notebook').each(function () {
                var $notebook = $(this);
                var $link = $notebook.find('.nav-tabs .nav-link[data-name="' + tabName + '"]');
                if ($link.length) {
                    $link.tab('show');
                }
            });
            this.renderer.$('.o_notebook').off('shown.bs.tab.cpabooks').on('shown.bs.tab.cpabooks', '.nav-tabs .nav-link', function () {
                self._cpabooksSaveActiveTaskTab($(this).closest('.o_notebook'));
            });
        },

        _cpabooksGetFsmActiveStage: function () {
            var state = this.renderer && this.renderer.state;
            if (!state || !state.data) {
                return 0;
            }
            var stage = state.data.fsm_ui_active_stage;
            if (stage === undefined || stage === null || stage === false) {
                return 0;
            }
            return parseInt(stage, 10) || 0;
        },

        _cpabooksFsmFormActive: function (state) {
            if (!state || !state.data) {
                return false;
            }
            return !!(
                state.data.is_fsm
                || state.data.check_fsm
                || state.data.fsm_crn_form
            );
        },

        _cpabooksApplyFsmInvoiceTone: function (state) {
            if (!this.renderer || !state || !state.data) {
                return;
            }
            var tone = state.data.fsm_invoice_progress_tone || 'none';
            var toneClasses = 'cpabooks_fsm_invoice_tone_in_progress cpabooks_fsm_invoice_tone_draft cpabooks_fsm_invoice_tone_issued';
            var $status = this.renderer.$('.o_field_widget[name="fsm_invoice_progress_status"]');
            $status.removeClass(toneClasses);
            if (tone && tone !== 'none') {
                $status.addClass('cpabooks_fsm_invoice_tone_' + tone);
            }
        },

        _cpabooksApplyFsmStage7ApprovalTone: function (state) {
            if (!this.renderer || !state || !state.data) {
                return;
            }
            var tone = state.data.fsm_stage7_approval_tone || 'none';
            var toneClasses = 'cpabooks_fsm_stage7_tone_waiting cpabooks_fsm_stage7_tone_approved cpabooks_fsm_stage7_tone_rejected';
            var $status = this.renderer.$('.o_field_widget[name="fsm_stage7_approval_status"]');
            $status.removeClass(toneClasses);
            if (tone && tone !== 'none') {
                $status.addClass('cpabooks_fsm_stage7_tone_' + tone);
            }
        },

        _cpabooksApplyFsmStageUi: function () {
            if (this.modelName !== 'project.task' || !this.renderer) {
                return;
            }
            var state = this.renderer.state;
            if (!this._cpabooksFsmFormActive(state)) {
                if (this._cpabooksEnsureFsmFullEditButton) {
                    this._cpabooksEnsureFsmFullEditButton();
                }
                return;
            }
            var activeStage = this._cpabooksGetFsmActiveStage();
            var fullEditMode = !!state.data.fsm_workflow_edit_mode;
            var inFormEdit = this.mode === 'edit';
            var $form = this.$el;
            var $sheet = this.renderer.$('.cpabooks_fsm_task_sheet');

            this._cpabooksApplyFsmInvoiceTone(state);
            this._cpabooksApplyFsmStage7ApprovalTone(state);
            $form.toggleClass('cpabooks_fsm_full_edit_mode', fullEditMode);
            for (var i = 0; i <= 6; i++) {
                var stageReadonly = (fullEditMode || inFormEdit)
                    ? false
                    : !!state.data['fsm_stage_' + i + '_readonly'];
                var $panel = $sheet.find('.cpabooks_fsm_stage_panel_' + i);
                $panel.toggleClass('cpabooks_fsm_stage_locked', stageReadonly);
                _.each(FSM_STAGE_FIELD_NAMES[i] || [], function (fieldName) {
                    $sheet.find('.o_field_widget[name="' + fieldName + '"]')
                        .toggleClass('cpabooks_fsm_field_locked', stageReadonly);
                });
            }
            if (this._cpabooksEnsureFsmFullEditButton) {
                this._cpabooksEnsureFsmFullEditButton();
                // Control panel can remount after _update; retry once.
                var self = this;
                window.setTimeout(function () {
                    self._cpabooksEnsureFsmFullEditButton();
                }, 50);
            }
            this._cpabooksBindFsmNavProminentControls();
            this._cpabooksBindFsmSidebarResize();
            this._cpabooksPositionFsmSidebar();

            if (this._cpabooksFsmShouldFocus && !this._cpabooksFsmSuppressFocusOnce) {
                this._cpabooksFsmShouldFocus = false;
                this._cpabooksFocusFsmStage(activeStage, {
                    blink: this._cpabooksFsmFocusBlink,
                    preferPending: this._cpabooksFsmFocusPreferPending,
                    pointerOrigin: this._cpabooksFsmPointerOrigin,
                });
                this._cpabooksFsmFocusBlink = false;
                this._cpabooksFsmFocusPreferPending = false;
            }
            this._cpabooksFsmSuppressFocusOnce = false;
        },

        _cpabooksBindFsmSidebarResize: function () {
            if (this._cpabooksFsmSidebarResizeBound) {
                return;
            }
            this._cpabooksFsmSidebarResizeBound = true;
            var self = this;
            $(window).on('resize.cpabooks_fsm_sidebar', function () {
                if (self.modelName === 'project.task') {
                    self._cpabooksPositionFsmSidebar();
                }
            });
        },

        _cpabooksPositionFsmSidebar: function () {
            if (!this.renderer) {
                return;
            }
            var $sheet = this.renderer.$('.cpabooks_fsm_task_sheet');
            var $sidebar = this.renderer.$('.cpabooks_fsm_sidebar');
            if (!$sheet.length || !$sidebar.length || !$sidebar.is(':visible')) {
                return;
            }
            var $anchor = this.renderer.$('.cpabooks_fsm_next_prominent').filter(':visible').last();
            if (!$anchor.length) {
                $anchor = this.renderer.$('div[name="cpabooks_fsm_document_button_box"]').filter(':visible').last();
            }
            if (!$anchor.length) {
                $anchor = this.renderer.$('.cpabooks_crn_form_caption').filter(':visible').last();
            }
            var sheetTop = $sheet.offset().top;
            var anchorBottom = $anchor.length
                ? ($anchor.offset().top + $anchor.outerHeight(true))
                : sheetTop;
            var top = Math.max(Math.round(anchorBottom - sheetTop + 10), 10);
            $sidebar.css('top', top + 'px');
        },

        _cpabooksResetFsmPendingNavIndex: function () {
            this._cpabooksFsmPendingNavIndex = 0;
        },

        _cpabooksGetFsmPendingNavIndex: function (serials) {
            if (!serials || !serials.length) {
                return 0;
            }
            if (this._cpabooksFsmPendingNavIndex === undefined || this._cpabooksFsmPendingNavIndex === null) {
                this._cpabooksFsmPendingNavIndex = 0;
            }
            if (this._cpabooksFsmPendingNavIndex >= serials.length) {
                this._cpabooksFsmPendingNavIndex = 0;
            }
            return this._cpabooksFsmPendingNavIndex;
        },

        _cpabooksGetPendingLabelForSerial: function ($scope, serial) {
            var $label = this._cpabooksFindFsmSerialLabel($scope, serial);
            if ($label.length) {
                return $label.text().trim();
            }
            return serial + '.';
        },

        _cpabooksGetNextPendingPreviewLabels: function (state, count) {
            count = count || FSM_PENDING_PREVIEW_COUNT;
            var serials = this._cpabooksGetPendingSerialsFromState(state);
            if (!serials.length) {
                return [];
            }
            var $scope = this._cpabooksGetFsmOverviewScope();
            var start = this._cpabooksGetFsmPendingNavIndex(serials);
            var labels = [];
            var i;
            for (i = 0; i < serials.length && labels.length < count; i++) {
                var serial = serials[(start + i) % serials.length];
                labels.push(this._cpabooksGetPendingLabelForSerial($scope, serial));
            }
            return labels;
        },

        _cpabooksGetCurrentPendingSerial: function (state) {
            var serials = this._cpabooksGetPendingSerialsFromState(state);
            if (!serials.length) {
                return null;
            }
            return serials[this._cpabooksGetFsmPendingNavIndex(serials)];
        },

        _cpabooksParseFirstPendingSerial: function (displayText) {
            if (!displayText) {
                return null;
            }
            var text = String(displayText).trim();
            var match = text.match(/^(\d+)/);
            if (match) {
                return match[1];
            }
            match = text.match(/Pending\s+(\d+)/i);
            if (match) {
                return match[1];
            }
            return null;
        },

        _cpabooksGetFsmOverviewScope: function () {
            if (!this.renderer) {
                return $();
            }
            var $sheet = this.renderer.$('.cpabooks_fsm_task_sheet');
            var $scope = $sheet.find('.cpabooks_fsm_overview_fields').first();
            if (!$scope.length) {
                $scope = $sheet.find('.cpabooks_fsm_overview').first();
            }
            return $scope;
        },

        _cpabooksGetFsmNextButton: function () {
            if (!this.renderer) {
                return $();
            }
            return this.renderer.$('.cpabooks_fsm_next_prominent .cpabooks_fsm_btn_next_main').first();
        },

        _cpabooksFetchFsmPendingData: function () {
            var self = this;
            var record = this.model.get(this.handle);
            if (!record || !record.res_id) {
                return Promise.resolve(null);
            }
            return this._rpc({
                model: 'project.task',
                method: 'read',
                args: [[record.res_id], [
                    'fsm_pending_banner_html',
                    'fsm_workflow_pending_serials_display',
                    'fsm_stage_progress',
                    'fsm_action_nav_html',
                ]],
            }).then(function (rows) {
                if (!rows || !rows.length) {
                    return null;
                }
                return self.model.notifyChanges(self.handle, rows[0]).then(function () {
                    return rows[0];
                });
            });
        },

        _cpabooksFindFsmFieldWidget: function ($scope, fieldName, pendingSerial) {
            if (!$scope || !$scope.length) {
                return $();
            }
            if (pendingSerial) {
                var $bySerial = this._cpabooksFindFsmFieldBySerial($scope, pendingSerial);
                if ($bySerial.length) {
                    return $bySerial;
                }
            }
            var $field = $scope.find('.o_field_widget[name="' + fieldName + '"]').first();
            if (fieldName === 'qt_no') {
                var $qtText = $scope.find('.o_field_widget[name="qt_no_text"]').first();
                if ($qtText.length && !$scope.find('.o_field_widget[name="qt_no"] .o_input_dropdown:visible').length) {
                    $field = $qtText;
                }
            }
            return $field;
        },

        _cpabooksFindFsmFieldBySerial: function ($scope, serial) {
            var $label = this._cpabooksFindFsmSerialLabel($scope, serial);
            if (!$label.length) {
                return $();
            }
            var $row = $label.closest('tr');
            if ($row.length) {
                return $row.find('.o_field_widget').first();
            }
            return $();
        },

        _cpabooksFindFsmPointerTarget: function ($scope, $field, pendingSerial) {
            var $label = this._cpabooksFindFsmSerialLabel($scope, pendingSerial);
            if ($label.length) {
                return $label;
            }
            var $row = $field.closest('tr');
            if ($row.length) {
                return $row;
            }
            return $field;
        },

        _cpabooksFindFsmSerialLabel: function ($scope, serial) {
            if (!$scope || !$scope.length || !serial) {
                return $();
            }
            var prefix = serial + '.';
            var $found = $();
            $scope.find('.o_td_label label').each(function () {
                var txt = $(this).text().trim();
                if (txt.indexOf(prefix) === 0) {
                    $found = $(this);
                    return false;
                }
            });
            return $found;
        },

        _cpabooksGetFirstPendingFieldName: function (data) {
            if (!data) {
                return null;
            }
            var serial = this._cpabooksParseFirstPendingSerial(data.fsm_workflow_pending_serials_display);
            if (serial && FSM_SERIAL_TO_FIELD[serial]) {
                return FSM_SERIAL_TO_FIELD[serial];
            }
            return null;
        },

        _cpabooksStageForField: function (fieldName) {
            for (var stage = 0; stage <= 6; stage++) {
                if ((FSM_STAGE_FIELD_NAMES[stage] || []).indexOf(fieldName) !== -1) {
                    return stage;
                }
            }
            return 0;
        },

        _cpabooksBlinkFsmTargets: function ($targets) {
            if (!$targets || !$targets.length) {
                return;
            }
            $targets.removeClass(FSM_BLINK_CLASS);
            // Force reflow so repeated NEXT clicks retrigger animation.
            void $targets.get(0).offsetWidth;
            $targets.addClass(FSM_BLINK_CLASS);
            window.setTimeout(function () {
                $targets.removeClass(FSM_BLINK_CLASS);
            }, FSM_BLINK_MS);
        },

        _cpabooksBlinkFsmPendingTarget: function ($field, serial) {
            if (!$field || !$field.length) {
                return;
            }
            var $scope = this._cpabooksGetFsmOverviewScope();
            var $row = $field.closest('tr');
            if (!$row.length) {
                $row = $field;
            }
            $row.removeClass(FSM_BLINK_CLASS);
            void $row.get(0).offsetWidth;
            $row.addClass(FSM_BLINK_CLASS);
            window.setTimeout(function () {
                $row.removeClass(FSM_BLINK_CLASS);
            }, FSM_BLINK_MS);
        },

        _cpabooksRemoveFsmGuideLayers: function () {
            $('body > .cpabooks_fsm_pointer_trail_layer').empty();
        },

        _cpabooksGetFsmPointerLayer: function () {
            var $layer = $('body > .cpabooks_fsm_pointer_trail_layer');
            if (!$layer.length) {
                $layer = $('<div class="cpabooks_fsm_pointer_trail_layer" aria-hidden="true"/>');
                $('body').append($layer);
            }
            return $layer;
        },

        _cpabooksGetElementCenter: function ($el) {
            if (!$el || !$el.length) {
                return null;
            }
            var rect = $el[0].getBoundingClientRect();
            return {
                x: rect.left + (rect.width / 2),
                y: rect.top + (rect.height / 2),
            };
        },

        _cpabooksEaseOutCubic: function (t) {
            return 1 - Math.pow(1 - t, 3);
        },

        _cpabooksAnimateFsmGuideRay: function ($origin, $target, done) {
            var origin = this._cpabooksGetElementCenter($origin);
            var target = this._cpabooksGetElementCenter($target);
            if (!origin || !target) {
                if (done) {
                    done();
                }
                return;
            }
            var $layer = this._cpabooksGetFsmPointerLayer();
            $layer.empty();

            var viewW = $(window).width();
            var viewH = $(window).height();
            var ns = 'http://www.w3.org/2000/svg';
            var svgEl = document.createElementNS(ns, 'svg');
            svgEl.setAttribute('class', 'cpabooks_fsm_guide_ray_svg');
            svgEl.setAttribute('width', String(viewW));
            svgEl.setAttribute('height', String(viewH));
            svgEl.setAttribute('viewBox', '0 0 ' + viewW + ' ' + viewH);
            var lineEl = document.createElementNS(ns, 'line');
            lineEl.setAttribute('class', 'cpabooks_fsm_guide_ray_line');
            lineEl.setAttribute('x1', String(origin.x));
            lineEl.setAttribute('y1', String(origin.y));
            lineEl.setAttribute('x2', String(origin.x));
            lineEl.setAttribute('y2', String(origin.y));
            svgEl.appendChild(lineEl);
            $layer.append(svgEl);

            var angle = Math.atan2(target.y - origin.y, target.x - origin.x) * 180 / Math.PI;
            var $head = $(
                '<div class="cpabooks_fsm_guide_ray_head">' +
                '<i class="fa fa-long-arrow-right" aria-hidden="true"></i>' +
                '</div>'
            );
            $head.css({
                left: origin.x,
                top: origin.y,
                transform: 'translate(-50%, -50%) rotate(' + angle + 'deg)',
            });
            $layer.append($head);

            var pointers = [];
            var i;
            for (i = 0; i < FSM_POINTER_TRAIL_COUNT; i++) {
                var $pointer = $(
                    '<div class="cpabooks_fsm_pointer_ghost cpabooks_fsm_pointer_ghost_red">' +
                    '<i class="fa fa-hand-pointer-o" aria-hidden="true"></i>' +
                    '</div>'
                );
                $pointer.css({
                    left: origin.x,
                    top: origin.y,
                    opacity: Math.max(0.25, 1 - (i * 0.16)),
                });
                $layer.append($pointer);
                pointers.push($pointer);
            }

            var start = window.performance && window.performance.now
                ? window.performance.now()
                : Date.now();
            var self = this;
            var tick = function (now) {
                var elapsed = now - start;
                var progress = Math.min(elapsed / FSM_GUIDE_RAY_MS, 1);
                var eased = self._cpabooksEaseOutCubic(progress);
                var cx = origin.x + ((target.x - origin.x) * eased);
                var cy = origin.y + ((target.y - origin.y) * eased);
                lineEl.setAttribute('x2', String(cx));
                lineEl.setAttribute('y2', String(cy));
                $head.css({
                    left: cx,
                    top: cy,
                    transform: 'translate(-50%, -50%) rotate(' + angle + 'deg)',
                });
                _.each(pointers, function ($pointer, index) {
                    var lag = index * 0.09;
                    var local = Math.max(progress - lag, 0) / Math.max(1 - lag, 0.01);
                    var localEased = self._cpabooksEaseOutCubic(Math.min(local, 1));
                    $pointer.css({
                        left: origin.x + ((target.x - origin.x) * localEased),
                        top: origin.y + ((target.y - origin.y) * localEased),
                    });
                });
                if (progress < 1) {
                    window.requestAnimationFrame(tick);
                } else {
                    window.setTimeout(function () {
                        $layer.empty();
                        if (done) {
                            done();
                        }
                    }, 350);
                }
            };
            window.requestAnimationFrame(tick);
        },

        _cpabooksGetPendingSerialsFromState: function (state) {
            if (!state || !state.data) {
                return [];
            }
            var html = state.data.fsm_pending_banner_html;
            var serials = [];
            if (html) {
                var $tmp = $('<div/>').html(html);
                $tmp.find('li').each(function () {
                    var match = $(this).text().trim().match(/^(\d+)\./);
                    if (match && serials.indexOf(match[1]) === -1) {
                        serials.push(match[1]);
                    }
                });
            }
            if (serials.length) {
                return serials;
            }
            var compact = state.data.fsm_workflow_pending_serials_display || '';
            compact = String(compact).replace(/^Pending\s+/i, '').replace(/\s*\.\.\.\s*$/, '');
            if (!compact) {
                return [];
            }
            return _.map(compact.split(','), function (part) {
                return String(part).trim();
            }).filter(Boolean);
        },

        _cpabooksGetNextPendingLabelText: function (state) {
            if (!state || !state.data) {
                return '';
            }
            var html = state.data.fsm_pending_banner_html;
            if (html) {
                var $tmp = $('<div/>').html(html);
                var $first = $tmp.find('li').first();
                if ($first.length) {
                    return $first.text().trim();
                }
            }
            var serial = this._cpabooksParseFirstPendingSerial(
                state.data.fsm_workflow_pending_serials_display
            );
            if (serial) {
                var $scope = this._cpabooksGetFsmOverviewScope();
                var $label = this._cpabooksFindFsmSerialLabel($scope, serial);
                if ($label.length) {
                    return $label.text().trim();
                }
            }
            return '';
        },

        _cpabooksBindFsmNavProminentControls: function () {
            this._cpabooksPositionFsmSidebar();
        },

        _cpabooksRunFsmNextFocusOnly: function ($pointerOrigin) {
            var self = this;
            var run = function () {
                var state = self.renderer && self.renderer.state;
                var serials = self._cpabooksGetPendingSerialsFromState(state);
                if (!serials.length) {
                    return;
                }
                self._cpabooksFocusFsmPendingAtIndex(
                    self._cpabooksGetFsmPendingNavIndex(serials),
                    {scrollOnly: true}
                );
                self._cpabooksFsmPendingNavIndex = (
                    self._cpabooksGetFsmPendingNavIndex(serials) + 1
                ) % serials.length;
            };
            var state = this.renderer && this.renderer.state && this.renderer.state.data;
            if (!state || !state.fsm_workflow_pending_serials_display) {
                return this._cpabooksFetchFsmPendingData().then(function () {
                    self._cpabooksResetFsmPendingNavIndex();
                    run();
                });
            }
            run();
            return Promise.resolve();
        },

        _cpabooksFocusFsmPendingAtIndex: function (index, options) {
            if (!this.renderer) {
                return;
            }
            options = options || {};
            var state = this.renderer.state;
            var serials = this._cpabooksGetPendingSerialsFromState(state);
            if (!serials.length) {
                return;
            }
            index = index % serials.length;
            var pendingSerial = serials[index];
            var fieldName = FSM_SERIAL_TO_FIELD[pendingSerial];
            var $scope = this._cpabooksGetFsmOverviewScope();
            if (!fieldName) {
                return;
            }
            var $field = this._cpabooksFindFsmFieldWidget($scope, fieldName, pendingSerial);
            if (!$field.length) {
                return;
            }
            var $pointerTarget = this._cpabooksFindFsmPointerTarget($scope, $field, pendingSerial);
            var targetTop = Math.max($pointerTarget.offset().top - FSM_SCROLL_OFFSET, 0);
            $('html, body').stop(true).animate({
                scrollTop: targetTop,
            }, 450, 'swing', function () {
                var $input = $field.find('input:not([type="hidden"]), textarea, select').filter(':visible').first();
                if ($input.length) {
                    $input.trigger('focus');
                }
            });
        },

        _cpabooksFocusFsmStage: function (stage, options) {
            if (!this.renderer) {
                return;
            }
            options = options || {};
            var $scope = this._cpabooksGetFsmOverviewScope();
            var $sheet = this.renderer.$('.cpabooks_fsm_task_sheet');
            var state = this.renderer.state;
            var fieldName = null;
            var targetStage = stage;
            var pendingSerial = null;

            if (options.preferPending && state && state.data) {
                pendingSerial = this._cpabooksParseFirstPendingSerial(
                    state.data.fsm_workflow_pending_serials_display
                );
                fieldName = this._cpabooksGetFirstPendingFieldName(state.data);
                if (fieldName) {
                    targetStage = this._cpabooksStageForField(fieldName);
                }
            }
            if (!fieldName && pendingSerial) {
                fieldName = FSM_SERIAL_TO_FIELD[pendingSerial];
                if (fieldName) {
                    targetStage = this._cpabooksStageForField(fieldName);
                }
            }
            if (!fieldName) {
                fieldName = FSM_STAGE_FOCUS_FIELDS[targetStage] || FSM_STAGE_FOCUS_FIELDS[0];
            }

            var $field = this._cpabooksFindFsmFieldWidget($scope, fieldName, pendingSerial);
            if (!$field.length && $scope.length) {
                var $panel = $scope.find('.cpabooks_fsm_stage_panel_' + targetStage).first();
                $field = $panel.find('.o_field_widget').filter(':visible').first();
            }
            if (!$field.length) {
                return;
            }

            var $pointerTarget = this._cpabooksFindFsmPointerTarget($scope, $field, pendingSerial);
            var targetTop = Math.max($pointerTarget.offset().top - FSM_SCROLL_OFFSET, 0);
            var self = this;
            var $pointerOrigin = options.pointerOrigin
                || this._cpabooksFsmPointerOrigin
                || this._cpabooksGetFsmNextButton();

            this._cpabooksFsmPointerOrigin = null;

            $('html, body').stop(true).animate({
                scrollTop: targetTop,
            }, 650, 'swing', function () {
                // Re-measure after scroll so the ray lands on the checklist row, not header widgets.
                $pointerTarget = self._cpabooksFindFsmPointerTarget($scope, $field, pendingSerial);
                $pointerOrigin = options.pointerOrigin || self._cpabooksGetFsmNextButton();
                if (options.blink && $pointerOrigin.length && $pointerTarget.length) {
                    self._cpabooksAnimateFsmGuideRay($pointerOrigin, $pointerTarget, function () {
                        self._cpabooksBlinkFsmPendingTarget($field, pendingSerial);
                    });
                } else if (options.blink) {
                    self._cpabooksBlinkFsmPendingTarget($field, pendingSerial);
                }
                var $input = $field.find('input:not([type="hidden"]), textarea, select').filter(':visible').first();
                if ($input.length) {
                    $input.trigger('focus');
                } else {
                    $field.trigger('click');
                }
            });
        },

        _cpabooksGetFsmEditButton: function () {
            var $edit = $();
            if (this.$buttons && this.$buttons.length) {
                $edit = this.$buttons.find('.o_form_button_edit').first();
            }
            if (!$edit.length) {
                $edit = $('.o_control_panel .o_cp_buttons .o_form_button_edit').first();
            }
            if (!$edit.length) {
                $edit = this.$('.o_form_button_edit').first();
            }
            return $edit;
        },

        _cpabooksEnsureFsmFullEditButton: function () {
            var state = this.renderer && this.renderer.state;
            // Always drop header-form FULL EDIT (duplicate of control-panel button).
            this.$('.cpabooks_fsm_header_full_edit, button[name="action_fsm_workflow_full_edit"]').addClass('d-none o_hidden').hide();

            var $existing = $();
            if (this.$buttons && this.$buttons.length) {
                $existing = $existing.add(this.$buttons.find('.o_cpabooks_fsm_full_edit_btn'));
            }
            $existing = $existing
                .add($('.o_control_panel .o_cpabooks_fsm_full_edit_btn'))
                .add(this.$('.o_cpabooks_fsm_full_edit_btn'));

            if (this.modelName !== 'project.task' || !this._cpabooksFsmFormActive(state)) {
                $existing.remove();
                this.$buttons && this.$buttons.find('.o_cpabooks_fsm_edit_stack').children().unwrap();
                return;
            }
            // Hide while already in full-edit mode (editing unlocked stages).
            if (state.data.fsm_workflow_edit_mode && this.mode === 'edit') {
                $existing.remove();
                return;
            }
            // Only show beside EDIT in readonly mode (same as original UX).
            if (this.mode !== 'readonly') {
                $existing.remove();
                return;
            }

            var $edit = this._cpabooksGetFsmEditButton();
            if (!$edit.length) {
                $existing.remove();
                return;
            }

            var $stack = $edit.closest('.o_cpabooks_fsm_edit_stack');
            if (!$stack.length) {
                $edit.wrap('<div class="o_cpabooks_fsm_edit_stack"/>');
                $stack = $edit.parent();
            }
            // Keep a single FULL EDIT under EDIT; remove any extras first.
            $existing.not($stack.find('.o_cpabooks_fsm_full_edit_btn').first()).remove();
            var $btn = $stack.find('.o_cpabooks_fsm_full_edit_btn').first();
            if (!$btn.length) {
                $btn = $('<button type="button" class="btn btn-secondary o_cpabooks_fsm_full_edit_btn cpabooks_fsm_btn_full_edit">FULL EDIT</button>');
                $btn.on('click', this._cpabooksOnFsmFullEditClick.bind(this));
                $edit.after($btn);
            } else if ($btn.nextAll('.o_cpabooks_fsm_full_edit_btn').length) {
                $btn.nextAll('.o_cpabooks_fsm_full_edit_btn').remove();
            }
        },

        _cpabooksOnFsmFullEditClick: function (ev) {
            if (ev && ev.preventDefault) {
                ev.preventDefault();
            }
            if (ev && ev.stopPropagation) {
                ev.stopPropagation();
            }
            var self = this;
            var resId = this._cpabooksGetFsmResId();
            if (!resId) {
                return Promise.resolve();
            }
            if (this.mode === 'edit' && this.renderer && this.renderer.state.data.fsm_workflow_edit_mode) {
                return Promise.resolve();
            }
            this._cpabooksFsmSuppressFocusOnce = true;
            this._disableButtons();
            return this.mutex.getUnlockedDef()
                .then(function () {
                    return self._rpc({
                        model: 'project.task',
                        method: 'action_fsm_workflow_edit',
                        args: [[resId]],
                    });
                })
                .then(function () {
                    return self._cpabooksRefreshFsmWorkflowFields();
                })
                .then(function () {
                    return self._setMode('edit');
                })
                .then(function () {
                    self._cpabooksApplyFsmStageUi();
                })
                .then(this._enableButtons.bind(this))
                .guardedCatch(this._enableButtons.bind(this));
        },

        _cpabooksRefreshFsmWorkflowFields: function () {
            var self = this;
            var record = this.model.get(this.handle);
            if (!record || !record.res_id) {
                return Promise.resolve();
            }
            return this._rpc({
                model: 'project.task',
                method: 'read',
                args: [[record.res_id], [
                    'fsm_ui_active_stage',
                    'fsm_workflow_edit_mode',
                    'fsm_stage_0_readonly',
                    'fsm_stage_1_readonly',
                    'fsm_stage_2_readonly',
                    'fsm_stage_3_readonly',
                    'fsm_stage_4_readonly',
                    'fsm_stage_5_readonly',
                    'fsm_stage_6_readonly',
                    'fsm_workflow_progress_html',
                    'fsm_stage_banner_html',
                    'fsm_action_nav_html',
                    'fsm_pending_banner_html',
                    'fsm_nav_suggested_label',
                    'fsm_workflow_pending_serials_display',
                    'fsm_stage_progress',
                    'complaint_type',
                    'fsm_stage7_approval_status',
                    'fsm_stage7_approval_tone',
                    'fsm_stage7_job_complete',
                    'fsm_invoice_progress_status',
                    'fsm_invoice_number_display',
                    'fsm_invoice_progress_tone',
                    'select_invoice',
                ]],
            }).then(function (rows) {
                if (!rows || !rows.length) {
                    return;
                }
                return self.model.notifyChanges(self.handle, rows[0]);
            });
        },

        _callButtonAction: function (ev, data) {
            var self = this;
            if (
                this.modelName === 'project.task'
                && data
                && data.attrs
                && data.attrs.name === 'action_fsm_workflow_full_edit'
            ) {
                return this._cpabooksOnFsmFullEditClick();
            }
            if (
                this.modelName === 'project.task'
                && data
                && data.attrs
                && data.attrs.name === 'action_fsm_dismiss_pending_banner'
            ) {
                return Promise.resolve();
            }
            if (
                this.modelName === 'project.task'
                && data
                && data.attrs
                && data.attrs.name === 'action_fsm_workflow_next'
            ) {
                return this._cpabooksRunFsmNextFocusOnly(
                    ev && ev.currentTarget ? $(ev.currentTarget) : this._cpabooksGetFsmNextButton()
                );
            }
            return this._super.apply(this, arguments);
        },

        destroy: function () {
            $(window).off('resize.cpabooks_fsm_sidebar');
            return this._super.apply(this, arguments);
        },

        willStart: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                if (
                    self.modelName === 'project.task'
                    && self.initialState
                    && self.initialState.context
                    && self.initialState.context.cpabooks_fsm_focus_stage !== undefined
                ) {
                    self._cpabooksFsmShouldFocus = true;
                }
            });
        },

        _update: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                if (self.modelName === 'project.task') {
                    self._cpabooksRestoreActiveTaskTab();
                    self._cpabooksApplyFsmStageUi();
                    self._cpabooksEnsureFsmFormChrome();
                    window.setTimeout(function () {
                        self._cpabooksPositionFsmSidebar();
                    }, 0);
                }
            });
        },

        saveRecord: function () {
            var self = this;
            var args = arguments;
            // _super is cleared when this method returns; capture before async .then().
            var superSaveRecord = this._super;

            if (this.modelName === 'project.task' && this.renderer) {
                this.renderer.$('.o_notebook').each(function () {
                    self._cpabooksSaveActiveTaskTab($(this));
                });
            }
            return superSaveRecord.apply(self, args);
        },
    });

    /**
     * Readonly HTML without web_editor Wysiwyg preload.
     * Standard widget="html" can show escaped markup when web_editor assets fail.
     */
    var FieldFsmReadonlyHtml = AbstractField.extend({
        className: 'o_field_fsm_readonly_html',
        supportedFieldTypes: ['html'],
        _render: function () {
            this.$el.empty();
            if (this.value) {
                $('<div class="cpabooks_fsm_readonly_html"/>')
                    .html(this.value)
                    .appendTo(this.$el);
            }
        },
    });

    fieldRegistry.add('fsm_readonly_html', FieldFsmReadonlyHtml);
});
