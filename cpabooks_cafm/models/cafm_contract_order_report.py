# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class CafmContractOrderReport(models.Model):
    _inherit = 'cpabooks.cafm.contract.order'

    style = fields.Many2one(
        'report.template.settings',
        string='Report Style',
        help='Professional template style used when printing this contract order.',
    )
    project_title = fields.Char(
        string='Project Title',
        compute='_compute_project_title',
        store=True,
    )
    show_title = fields.Boolean(string='Show Title', default=True)
    show_trn = fields.Boolean(string='Show TRN', default=True)
    show_theme_color = fields.Boolean(string='Show Theme Color', default=True)
    num_word = fields.Char(string='Amount in Words', compute='_compute_num_word')
    attention = fields.Char(string='Attention', compute='_compute_attention', store=True)
    report_line_description = fields.Char(
        string='Report Line Description',
        compute='_compute_report_line_description',
    )

    @api.model
    def _get_default_report_style(self):
        company = self.env.company
        if company.df_style:
            return company.df_style
        return self.env.ref(
            'professional_templates_v1.df_style_for_all_reports',
            raise_if_not_found=False,
        ) or self.env['report.template.settings'].sudo().search([], limit=1)

    @api.depends('contract_id', 'contract_id.project_id', 'contract_id.name', 'name')
    def _compute_project_title(self):
        for order in self:
            contract = order.contract_id
            if contract and contract.project_id:
                order.project_title = contract.project_id.name
            elif contract:
                order.project_title = contract.name
            else:
                order.project_title = order.name or ''

    @api.depends('contact_person_id', 'contact_person_id.name')
    def _compute_attention(self):
        for order in self:
            order.attention = order.contact_person_id.name if order.contact_person_id else False

    @api.depends('contract_id', 'period_label', 'date_from', 'date_to', 'name')
    def _compute_report_line_description(self):
        for order in self:
            contract = order.contract_id
            base = contract.name if contract else order.name or _('AMC Contract')
            label = order.period_label or order.name or _('Contract Order')
            desc = '%s - %s' % (base, label)
            if order.date_from and order.date_to:
                desc = '%s (%s - %s)' % (
                    desc,
                    fields.Date.to_string(order.date_from),
                    fields.Date.to_string(order.date_to),
                )
            order.report_line_description = desc

    @api.depends('amount', 'currency_id')
    def _compute_num_word(self):
        for order in self:
            order.num_word = ''
            if order.currency_id and order.amount is not None:
                order.num_word = str(
                    order.currency_id.amount_to_text(order.amount)
                ).replace('And', 'and')

    @api.onchange('partner_id')
    def onchange_partner_style(self):
        default_style = self._get_default_report_style()
        for rec in self:
            rec.style = rec.style or default_style or rec.partner_id.style

    @api.model_create_multi
    def create(self, vals_list):
        default_style = self._get_default_report_style()
        for vals in vals_list:
            if not vals.get('style') and default_style:
                vals['style'] = default_style.id
        return super().create(vals_list)

    def _get_report_title(self):
        self.ensure_one()
        if self.state == 'draft':
            return _('QUOTATION')
        if self.state == 'cancelled':
            return _('CANCELLED CONTRACT ORDER')
        return _('CONTRACT ORDER')

    def action_print_contract_order(self):
        self.ensure_one()
        report = self.env.ref(
            'cpabooks_cafm.action_report_cafm_contract_order',
            raise_if_not_found=False,
        )
        if not report:
            return False
        return report.report_action(self)
