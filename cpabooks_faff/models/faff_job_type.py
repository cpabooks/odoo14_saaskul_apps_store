# -*- coding: utf-8 -*-
from odoo import fields, models


class FaffJobType(models.Model):
    _name = "cpabooks.faff.job.type"
    _description = "FAFF Job Type"
    _order = "sequence, name"

    name = fields.Char(required=True)
    code = fields.Char()
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text()
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company
    )
