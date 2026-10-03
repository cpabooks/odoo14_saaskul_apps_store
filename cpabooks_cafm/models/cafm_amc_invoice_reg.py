# -*- coding: utf-8 -*-

from odoo import api, fields, models


class CafmAmcInvoiceReg(models.Model):
    _name = 'cpabooks.cafm.amc.invoice.reg'
    _description = 'AMC Invoice Follow-up'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'invoice_date desc, id desc'
    _rec_name = 'ref_no'

    invoice_date = fields.Date(string='Inv. Date', tracking=True, index=True)
    ref_no = fields.Char(string='ref. no (tally)', tracking=True, index=True)
    project_name = fields.Char(
        string='Project Name',
        tracking=True,
        help='Excel Project Name; also used to resolve L3 Level (Project) on import.',
    )
    # Same as VAR Work: Client Name / L2 / L3 Many2one
    partner_id = fields.Many2one(
        'res.partner', string='Client Name', tracking=True,
        help='Defaults from L3 Level (Project) name; user may change.',
    )
    l2_level_id = fields.Many2one(
        'cpabooks.cafm.customer.group', string='L2 Level (Client Group)', tracking=True,
    )
    l3_level_id = fields.Many2one(
        'project.project', string='L3 Level (Project)', tracking=True,
    )
    invoice_amount = fields.Float(string='Inv. Amount', digits=(16, 2), tracking=True)
    ubs_no = fields.Char(string='UBS No.', tracking=True)
    contract_lpo_no = fields.Char(string='Contract/LPO No.', tracking=True)
    due_day = fields.Char(
        string='Due Day (import)',
        help='Raw Due Day from Excel import; UI shows Due Days (computed).',
    )
    due_days = fields.Integer(
        string='Due Days',
        compute='_compute_due_days',
        help='Days from invoice date to today.',
    )
    invoice_type = fields.Char(string='Inv. Type', default='AMC')
    follow_up = fields.Char(
        string='Follow up (text)',
        tracking=True,
        help='Legacy / Excel text; prefer Follow up by user.',
    )
    follow_up_user_id = fields.Many2one(
        'res.users',
        string='Follow up by',
        tracking=True,
        index=True,
    )
    remarks = fields.Text(string='Remarks')
    status = fields.Selection(
        [
            ('waiting_kpi', 'Waiting for KPI'),
            ('waiting_csr', 'Waiting for CSR'),
            ('not_submitted', 'Not Submitted'),
            ('submitted', 'Submitted'),
        ],
        string='Status',
        default='not_submitted',
        required=True,
        tracking=True,
        index=True,
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'cafm_amc_invoice_reg_attachment_rel',
        'invoice_id',
        'attachment_id',
        string='Additional Files',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )

    @api.depends('invoice_date')
    def _compute_due_days(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.invoice_date:
                rec.due_days = (today - rec.invoice_date).days
            else:
                rec.due_days = 0

    @api.model
    def _get_or_create_partner_from_name(self, name):
        name = (name or '').strip()
        if not name:
            return self.env['res.partner']
        Partner = self.env['res.partner']
        partner = Partner.search([('name', '=', name)], limit=1)
        if not partner:
            partner = Partner.create({'name': name})
        return partner

    @api.model
    def _get_or_create_l2_from_name(self, name):
        name = (name or '').strip()
        if not name:
            return self.env['cpabooks.cafm.customer.group']
        Group = self.env['cpabooks.cafm.customer.group']
        group = Group.search([('name', '=', name)], limit=1)
        if not group:
            group = Group.create({'name': name})
        return group

    @api.model
    def _get_or_create_l3_from_name(self, name):
        name = (name or '').strip()
        if not name:
            return self.env['project.project']
        Project = self.env['project.project']
        project = Project.search([('name', '=', name)], limit=1)
        if not project:
            project = Project.create({'name': name})
        return project

    def _default_client_from_l3(self, vals, force=False):
        """Set Client Name from L3 Level (Project) name when missing / forced."""
        if not vals.get('l3_level_id'):
            return vals
        if vals.get('partner_id') and not force:
            return vals
        project = self.env['project.project'].browse(vals['l3_level_id'])
        partner = self._get_or_create_partner_from_name(project.name)
        if partner:
            vals['partner_id'] = partner.id
        return vals

    def _sync_project_name_to_l3(self, vals):
        """Excel Project Name → L3 Level (Project) when L3 not set explicitly."""
        vals = dict(vals or {})
        if vals.get('l3_level_id'):
            project = self.env['project.project'].browse(vals['l3_level_id'])
            if project and not vals.get('project_name'):
                vals['project_name'] = project.name
            return vals
        project_name = (vals.get('project_name') or '').strip()
        if project_name:
            project = self._get_or_create_l3_from_name(project_name)
            if project:
                vals['l3_level_id'] = project.id
        return vals

    @api.model
    def create(self, vals):
        vals = dict(vals or {})
        vals = self._sync_project_name_to_l3(vals)
        if vals.get('l3_level_id') and not vals.get('partner_id'):
            vals = self._default_client_from_l3(vals, force=False)
        vals = self._resolve_follow_up_user(vals)
        return super().create(vals)

    def write(self, vals):
        vals = dict(vals or {})
        vals = self._sync_project_name_to_l3(vals)
        if vals.get('l3_level_id') and 'partner_id' not in vals:
            vals = self._default_client_from_l3(vals, force=True)
        vals = self._resolve_follow_up_user(vals)
        return super().write(vals)

    @api.onchange('l3_level_id')
    def _onchange_l3_level_id(self):
        if self.l3_level_id:
            self.partner_id = self._get_or_create_partner_from_name(self.l3_level_id.name)
            self.project_name = self.l3_level_id.name
        else:
            self.partner_id = False

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields=allfields, attributes=attributes)
        aliases = {
            'partner_id': ['Client Name', 'Party Name (client)', 'Party Name'],
            'l2_level_id': ['L2 Level (Client Group)', 'L2 Level', 'L2 Level (Project Group)'],
            'l3_level_id': ['L3 Level (Project)', 'L3 Level', 'Project Name'],
            'project_name': ['Project Name'],
        }
        for fname, labels in aliases.items():
            if fname in res:
                res[fname]['string'] = labels[0]
        return res

    @api.model
    def backfill_l2_l3_client_from_project_name(self):
        """Link existing imported rows (project_name only) to L3 + Client Name."""
        Invoice = self.sudo()
        records = Invoice.search([
            ('project_name', '!=', False),
            ('l3_level_id', '=', False),
        ])
        for rec in records:
            project = Invoice._get_or_create_l3_from_name(rec.project_name)
            vals = {'l3_level_id': project.id}
            if not rec.partner_id and project:
                partner = Invoice._get_or_create_partner_from_name(project.name)
                if partner:
                    vals['partner_id'] = partner.id
            rec.write(vals)
        # Also fill Client Name when L3 exists but partner empty
        for rec in Invoice.search([('l3_level_id', '!=', False), ('partner_id', '=', False)]):
            partner = Invoice._get_or_create_partner_from_name(rec.l3_level_id.name)
            if partner:
                rec.write({'partner_id': partner.id})
        return True

    def _resolve_follow_up_user(self, vals):
        """Map Excel/text Follow up → Follow up by user when possible."""
        vals = dict(vals or {})
        if vals.get('follow_up_user_id'):
            user = self.env['res.users'].browse(vals['follow_up_user_id'])
            if user and not vals.get('follow_up'):
                vals['follow_up'] = user.name
            return vals
        text = (vals.get('follow_up') or '').strip()
        if not text:
            return vals
        user = self.env['res.users'].sudo().with_context(active_test=False).search([
            '|', ('name', '=ilike', text), ('login', '=ilike', text),
        ], limit=1)
        if user:
            vals['follow_up_user_id'] = user.id
        return vals

    @api.model
    def ensure_amc_follow_up_users(self):
        """Create Nihil / Ragesh follow-up users and link Char follow_up text.

        Soft-fail on DBs where user/partner create hits unrelated schema gaps
        (e.g. missing res_company columns) so module upgrades still complete.
        """
        import logging
        _logger = logging.getLogger(__name__)
        Users = self.env['res.users'].sudo().with_context(
            active_test=False,
            no_reset_password=True,
            mail_create_nolog=True,
            tracking_disable=True,
        )
        group_user = self.env.ref('base.group_user')
        specs = [
            ('Nihil', 'nihil@gmail.com'),
            ('Ragesh', 'ragesh@gmail.com'),
        ]
        for name, login in specs:
            try:
                with self.env.cr.savepoint():
                    user = Users.search([
                        '|', ('login', '=', login), ('name', '=ilike', name),
                    ], limit=1)
                    if not user:
                        Users.create({
                            'name': name,
                            'login': login,
                            'email': login,
                            'groups_id': [(6, 0, [group_user.id])],
                        })
                    else:
                        user.write({'name': name, 'login': login, 'email': login})
            except Exception as exc:
                _logger.warning(
                    'AMC follow-up user ensure skipped for %s (%s): %s',
                    name, login, exc,
                )

        try:
            with self.env.cr.savepoint():
                for rec in self.sudo().search([
                    ('follow_up_user_id', '=', False),
                    ('follow_up', '!=', False),
                ]):
                    text = (rec.follow_up or '').strip()
                    if not text:
                        continue
                    user = Users.search([
                        '|', ('name', '=ilike', text), ('login', '=ilike', text),
                    ], limit=1)
                    if user:
                        rec.write({'follow_up_user_id': user.id})
        except Exception as exc:
            _logger.warning('AMC follow-up user linking skipped: %s', exc)
        return True
