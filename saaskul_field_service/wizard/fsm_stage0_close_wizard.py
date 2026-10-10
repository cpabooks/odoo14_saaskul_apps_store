# -*- coding: utf-8 -*-

from markupsafe import Markup

from odoo import api, fields, models, _


class CpabooksFsmStage0CloseWizard(models.TransientModel):
    _name = 'cpabooks.fsm.stage0.close.wizard'
    _description = 'Confirm closing FSM registration stage'

    task_id = fields.Many2one(
        'project.task',
        string='CRN',
        required=True,
        readonly=True,
        ondelete='cascade',
    )
    pending_html = fields.Html(
        string='Pending Items',
        compute='_compute_pending_html',
        sanitize=False,
    )
    pending_count = fields.Integer(
        string='Pending Count',
        compute='_compute_pending_html',
    )

    @api.depends('task_id')
    def _compute_pending_html(self):
        for wizard in self:
            task = wizard.task_id
            if not task:
                wizard.pending_count = 0
                wizard.pending_html = False
                continue
            labels = task._fsm_stage0_pending_checklist_labels()
            wizard.pending_count = len(labels)
            if not labels:
                wizard.pending_html = Markup(
                    '<p class="cpabooks_fsm_stage0_close_none">%s</p>'
                    % _('No pending registration checklist items.')
                )
                continue
            items = ''.join(
                '<li>%s</li>' % label for label in labels
            )
            wizard.pending_html = Markup(
                '<p>%s</p><ul class="cpabooks_fsm_stage0_close_pending">%s</ul>'
                % (_('The following registration items are still open:'), items)
            )

    def action_confirm_close_stage(self):
        self.ensure_one()
        self.task_id.action_fsm_stage0_confirm_close()
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
