# -*- coding: utf-8 -*-

from odoo import _, api, fields, models


class SwitchgearQualityTestType(models.Model):
    _name = 'switchgear.quality.test.type'
    _description = 'Switchgear Quality Test Type'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    technical_name = fields.Char(required=True, index=True)


class SwitchgearQualityTeam(models.Model):
    _name = 'switchgear.quality.team'
    _description = 'Switchgear Quality Team'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    check_count = fields.Integer(compute='_compute_counts')
    todo_count = fields.Integer(compute='_compute_counts')
    alert_count = fields.Integer(compute='_compute_counts')

    def _compute_counts(self):
        Check = self.env['switchgear.quality.check']
        Alert = self.env['switchgear.quality.alert']
        for team in self:
            team.check_count = Check.search_count([('team_id', '=', team.id)])
            team.todo_count = Check.search_count([('team_id', '=', team.id), ('quality_state', '=', 'none')])
            team.alert_count = Alert.search_count([('team_id', '=', team.id), ('stage_id.done', '=', False)])

    def _action_for_team(self, xmlid, extra_domain=None):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(xmlid)
        action['domain'] = [('team_id', '=', self.id)] + (extra_domain or [])
        action['context'] = {'default_team_id': self.id}
        return action

    def action_open_checks(self):
        return self._action_for_team('saaskul_switchgear.quality_check_action_main')

    def action_open_todo_checks(self):
        return self._action_for_team('saaskul_switchgear.quality_check_action_main', [('quality_state', '=', 'none')])

    def action_open_alerts(self):
        return self._action_for_team('saaskul_switchgear.quality_alert_action')

    @api.model
    def _get_default_team(self, company=None):
        company = company or self.env.company
        team = self.search([('company_id', 'in', [False, company.id])], limit=1)
        if not team:
            team = self.create({'name': _('Quality Team'), 'company_id': company.id})
        return team


class SwitchgearQualityAlertStage(models.Model):
    _name = 'switchgear.quality.alert.stage'
    _description = 'Switchgear Quality Alert Stage'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    folded = fields.Boolean(string='Folded in Kanban')
    done = fields.Boolean(string='Alert Processed')


class SwitchgearQualityCheck(models.Model):
    _name = 'switchgear.quality.check'
    _description = 'Switchgear Quality Check'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', default=lambda self: _('New'), copy=False, readonly=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', index=True)
    picking_id = fields.Many2one('stock.picking', string='Transfer', index=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    team_id = fields.Many2one('switchgear.quality.team', string='Team', required=True,
                              default=lambda self: self.env['switchgear.quality.team']._get_default_team())
    test_type_id = fields.Many2one('switchgear.quality.test.type', string='Test Type', required=True,
                                   default=lambda self: self._default_test_type())
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Customer')
    project_id = fields.Many2one('project.project', string='Job Order', index=True)
    quality_state = fields.Selection([
        ('none', 'To Do'),
        ('pass', 'Passed'),
        ('fail', 'Failed'),
    ], string='Status', default='none', required=True, tracking=True, copy=False)
    control_date = fields.Datetime(string='Control Date', copy=False)
    note = fields.Text(string='Notes')
    alert_ids = fields.One2many('switchgear.quality.alert', 'check_id', string='Alerts')
    alert_count = fields.Integer(compute='_compute_alert_count')

    @api.model
    def _default_test_type(self):
        return (self.env.ref('saaskul_switchgear.test_type_passfail', raise_if_not_found=False)
                or self.env['switchgear.quality.test.type'].search([], limit=1))

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('switchgear.quality.check') or _('New')
        if vals.get('production_id') and not vals.get('project_id'):
            production = self.env['mrp.production'].browse(vals['production_id'])
            vals.setdefault('project_id', production.project_id.id)
            vals.setdefault('partner_id', production.partner_id.id)
        return super().create(vals)

    def _compute_alert_count(self):
        for check in self:
            check.alert_count = len(check.alert_ids)

    @api.onchange('production_id')
    def _onchange_production_id(self):
        if self.production_id:
            self.product_id = self.production_id.product_id
            self.project_id = self.production_id.project_id
            self.partner_id = self.production_id.partner_id

    def do_pass(self):
        self.write({'quality_state': 'pass', 'control_date': fields.Datetime.now()})
        return True

    def do_fail(self):
        self.write({'quality_state': 'fail', 'control_date': fields.Datetime.now()})
        return True

    def do_alert(self):
        self.ensure_one()
        alert = self.env['switchgear.quality.alert'].create({
            'name': _('Alert from %s') % (self.name or self.product_id.display_name),
            'team_id': self.team_id.id,
            'company_id': self.company_id.id,
            'check_id': self.id,
            'product_id': self.product_id.id,
            'production_id': self.production_id.id,
            'picking_id': self.picking_id.id,
            'project_id': self.project_id.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'switchgear.quality.alert',
            'res_id': alert.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_alerts(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('saaskul_switchgear.quality_alert_action')
        action['domain'] = [('check_id', '=', self.id)]
        action['context'] = {'default_check_id': self.id, 'default_team_id': self.team_id.id,
                             'default_product_id': self.product_id.id}
        return action


class SwitchgearQualityAlert(models.Model):
    _name = 'switchgear.quality.alert'
    _description = 'Switchgear Quality Alert'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(required=True, tracking=True)
    team_id = fields.Many2one('switchgear.quality.team', string='Team', required=True,
                              default=lambda self: self.env['switchgear.quality.team']._get_default_team())
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    stage_id = fields.Many2one('switchgear.quality.alert.stage', string='Stage', tracking=True,
                               group_expand='_read_group_stage_ids', default=lambda self: self._default_stage())
    check_id = fields.Many2one('switchgear.quality.check', string='Quality Check')
    picking_id = fields.Many2one('stock.picking', string='Transfer', index=True)
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', index=True)
    product_id = fields.Many2one('product.product', string='Product')
    project_id = fields.Many2one('project.project', string='Job Order')
    partner_id = fields.Many2one('res.partner', string='Customer')
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user)
    description = fields.Text()

    @api.model
    def _default_stage(self):
        return self.env['switchgear.quality.alert.stage'].search([], limit=1)

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        return self.env['switchgear.quality.alert.stage'].search([], order=order)
