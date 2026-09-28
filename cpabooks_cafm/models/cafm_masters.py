# -*- coding: utf-8 -*-

from odoo import fields, models


class CafmLocation(models.Model):
    _name = 'cpabooks.cafm.location'
    _description = 'CAFM Location'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    note = fields.Text()

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Location must be unique.'),
    ]


class CafmContactPerson(models.Model):
    _name = 'cpabooks.cafm.contact.person'
    _description = 'CAFM Contact Person'
    _order = 'name'
    _rec_name = 'name'

    name = fields.Char(required=True)
    mobile = fields.Char(string='Mobile')
    active = fields.Boolean(default=True)
    note = fields.Text()


class CafmCustomerGroup(models.Model):
    _name = 'cpabooks.cafm.customer.group'
    _description = 'CAFM Customer Group'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    note = fields.Text()

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Customer group must be unique.'),
    ]


class CafmPriority(models.Model):
    _name = 'cpabooks.cafm.priority'
    _description = 'CAFM Priority'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Priority must be unique.'),
    ]


class CafmJobType(models.Model):
    _name = 'cpabooks.cafm.job.type'
    _description = 'CAFM Type of Job'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Type of Job must be unique.'),
    ]


class CafmWorkType(models.Model):
    _name = 'cpabooks.cafm.work.type'
    _description = 'CAFM Type of Work'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Type of Work must be unique.'),
    ]


class CafmProblemReported(models.Model):
    _name = 'cpabooks.cafm.problem.reported'
    _description = 'CAFM Problem Reported'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Problem Reported must be unique.'),
    ]


class CafmClientManager(models.Model):
    _name = 'cpabooks.cafm.client.manager'
    _description = 'CAFM Client Manager'
    _order = 'name'

    name = fields.Char(required=True)
    partner_id = fields.Many2one('res.partner', string='Contact')
    user_id = fields.Many2one('res.users', string='Linked User', domain="[('share', '=', False)]")
    mobile = fields.Char()
    email = fields.Char()
    active = fields.Boolean(default=True)
    note = fields.Text()


class CafmTechnician(models.Model):
    _name = 'cpabooks.cafm.technician'
    _description = 'CAFM Technician'
    _order = 'name'

    name = fields.Char(required=True)
    user_id = fields.Many2one('res.users', string='User', domain="[('share', '=', False)]")
    mobile = fields.Char()
    active = fields.Boolean(default=True)
    note = fields.Text()


class CafmDepartment(models.Model):
    _name = 'cpabooks.cafm.department'
    _description = 'CAFM Department'
    _order = 'name'

    name = fields.Char(required=True)
    code = fields.Char()
    active = fields.Boolean(default=True)
    user_ids = fields.Many2many(
        'res.users',
        'cpabooks_cafm_department_user_rel',
        'department_id',
        'user_id',
        string='Users',
    )
    project_ids = fields.Many2many(
        'project.project',
        'cpabooks_cafm_department_project_rel',
        'department_id',
        'project_id',
        string='Projects / L1',
    )

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Department must be unique.'),
    ]
