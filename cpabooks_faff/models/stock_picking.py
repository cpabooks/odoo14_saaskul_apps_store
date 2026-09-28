# -*- coding: utf-8 -*-
from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    faff_job_id = fields.Many2one(
        "cpabooks.faff.job", string="FAFF Job", copy=False, index=True
    )
