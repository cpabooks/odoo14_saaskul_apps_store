# -*- coding: utf-8 -*-
from odoo import api, fields, models

class CRMGCL(models.Model):
    _name = "crm.gcl"
    _description = "CRM GCL"

    tenant = fields.Text(string='Tenant')
    mobile = fields.Text(string='Mobile Number', required=True)
    email = fields.Text(string='Email Address')
    building = fields.Text(string='Building')
    flat = fields.Text(string='Flat')

    problem_type = fields.Text(string='Problem Type')
    problem_category = fields.Text(string='Problem Category')

    property = fields.Text(string='Property')
    problem = fields.Text(string='Problem')
    work_type = fields.Text(string='Type of Work')
    problem_detail = fields.Text(string='Problem Detail')
    priority = fields.Text(string='Priority')
    address = fields.Text(string='Address')
    ticket_no = fields.Text(string='Ticket Number')
    #option = fields.Text(string='Option')