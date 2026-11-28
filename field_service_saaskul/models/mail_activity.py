# -*- coding: utf-8 -*-

from odoo import models


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def action_create_crn(self):
        self.ensure_one()
        return self.env['project.task'].action_create_crn_from_activity(self.id)
