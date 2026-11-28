# -*- coding: utf-8 -*-
import csv
import os

from odoo import api, fields, models


class CpaCoaSetupLine(models.Model):
    _name = "cpa.coa.setup.line"
    _description = "COA Setup File"
    _order = "sequence, id"

    sequence = fields.Integer(string="SR", default=10)
    code = fields.Char(string="Code")
    code_auto = fields.Char(string="Code Auto")
    account_name = fields.Char(string="Account Name")
    id_account = fields.Char(string="ID Account")
    account_name_revise = fields.Char(string="Ledger Name")
    type_name = fields.Char(string="Type")
    index = fields.Char(string="Index")
    type_revise = fields.Char(string="Type Revise")
    group_id_ref = fields.Char(string="Group ID")
    group_name = fields.Char(string="Account Group")
    prefix_from = fields.Char(string="From")
    prefix_to = fields.Char(string="To")
    qid = fields.Char(string="QID")
    create_item = fields.Char(string="Create Item")
    link_item_coa = fields.Char(string="Link Item COA")

    @api.model
    def action_load_setup_file(self):
        return True
