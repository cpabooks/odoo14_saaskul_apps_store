# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    faff_job_id = fields.Many2one(
        "saaskul.faff.job", string="FAFF Job", copy=False, index=True
    )
