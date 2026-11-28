# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoaResetCodeOptionsWizard(models.TransientModel):
    _name = 'coa.reset.code.options.wizard'
    _description = 'COA Reset Code Options'

    account_ids = fields.Many2many('account.account', string='Accounts')
    code_digit_length = fields.Selection(
        [
            ('4', '4 digits (e.g. 1001)'),
            ('6', '6 digits (e.g. 100001)'),
        ],
        string='Code length',
        required=True,
        default='4',
    )
    company_code_mode = fields.Selection(
        [
            ('shared', 'Same code in every company (default)'),
            ('company_prefix', 'Company prefix (Co.1 → 1001, Co.2 → 2001, …)'),
        ],
        string='Multi-company codes',
        required=True,
        default='shared',
        help=(
            'Shared: matching accounts in different companies keep the same code.\n'
            'Company prefix: the first digit is the company number (by company ID order); '
            'the remaining digits identify the account (e.g. Auditing fees → 1001, 2001, 3001).'
        ),
    )
    help_html = fields.Html(compute='_compute_help_html', sanitize=False)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        accounts = self.env['account.account'].browse(active_ids).exists()
        if not accounts:
            accounts = self.env['account.account'].search([
                ('company_id', 'in', self.env.companies.ids),
            ])
        values['account_ids'] = [(6, 0, accounts.ids)]
        return values

    @api.depends('code_digit_length', 'company_code_mode')
    def _compute_help_html(self):
        for wizard in self:
            if wizard.company_code_mode == 'company_prefix':
                example = {
                    '4': _('Auditing fees → 1001 in company 1, 2001 in company 2, 3001 in company 3'),
                    '6': _('Auditing fees → 100001 in company 1, 200001 in company 2, 300001 in company 3'),
                }.get(wizard.code_digit_length or '4', '')
                wizard.help_html = (
                    '<p class="mb-0"><strong>%s</strong></p><p class="text-muted mb-0">%s</p>'
                ) % (_('Company prefix mode'), example)
            else:
                wizard.help_html = (
                    '<p class="mb-0">%s</p>'
                ) % _(
                    'Same logical account keeps one code in all selected companies '
                    '(when names/types match or identity code matches).'
                )

    def _options_dict(self):
        self.ensure_one()
        return {
            'code_digits': int(self.code_digit_length),
            'company_code_mode': self.company_code_mode,
        }

    def action_preview(self):
        self.ensure_one()
        accounts = self.account_ids.exists()
        if not accounts:
            raise UserError(_('No chart of accounts found for the current companies.'))
        return self.env['account.account'].browse(accounts.ids).with_context(
            cpa_reset_code_options=self._options_dict(),
        ).action_preview_reset_code_digits()


class CoaMenuActionWizard(models.TransientModel):
    _name = 'coa.menu.action.wizard'
    _description = 'COA Menu Action Chooser'

    action_key = fields.Selection(
        selection='_selection_action_key',
        string='Action',
        required=True,
    )

    @api.model
    def _selection_action_key(self):
        return [
            ('reset_all', 'Reset All'),
            ('factory_reset', 'Factory Reset'),
            ('add_opening_balance', 'Add Opening Balance'),
            ('view_rules', 'View Rules (VR)'),
            ('remove_groups', 'Remove Groups'),
            ('reset_groups', 'Reset Groups'),
            ('view_duplicate_codes', 'View Duplicate Codes'),
            ('fix_duplicate_codes', 'Fix Duplicate Codes'),
            ('create_prepaid_rules', 'Create Prepaid Rules'),
            ('toggle_code', 'Toggle Code'),
            ('show_code_true', 'Show Code (SCT)'),
            ('update_specific_ledger', 'Update Specific Ledger'),
            ('create_far_rules', 'Create FAR Rules'),
            ('create_journals', 'Create Journals (JV)'),
            ('merge_coa', 'Merge COA'),
            ('delete_unused_coa', 'Delete Unused COA'),
            ('ifrs_coding', 'IFRS Reset / Recode'),
            ('reset_code_digits', 'Reset Code Digits (legacy 4/6)'),
        ]

    def action_run(self):
        self.ensure_one()
        Account = self.env['account.account']
        dispatch = {
            'reset_all': lambda: Account.cpa_coa_menu_reset_all(),
            'add_opening_balance': lambda: Account.cpa_coa_menu_add_opening_balance(),
            'merge_coa': lambda: Account.cpa_coa_menu_merge_coa(),
            'delete_unused_coa': lambda: Account.cpa_coa_menu_delete_unused_coa(),
            'fix_duplicate_codes': lambda: Account.action_cpa_fix_duplicate_codes(),
            'view_duplicate_codes': lambda: Account.action_cpa_view_duplicate_codes(),
            'ifrs_coding': lambda: Account.cpa_coa_menu_ifrs_coding(),
            'reset_code_digits': lambda: Account.cpa_coa_menu_reset_code_digits(),
            'factory_reset': lambda: Account.cpa_coa_menu_factory_reset(),
            'view_rules': lambda: Account.cpa_coa_menu_view_rules(),
            'remove_groups': lambda: Account.cpa_coa_menu_remove_groups(),
            'reset_groups': lambda: Account.cpa_coa_menu_reset_groups(),
            'create_prepaid_rules': lambda: Account.cpa_coa_menu_create_prepaid_rules(),
            'toggle_code': lambda: Account.cpa_coa_menu_toggle_code(),
            'show_code_true': lambda: Account.cpa_coa_menu_show_code_true(),
            'update_specific_ledger': lambda: Account.cpa_coa_menu_update_specific_ledger(),
            'create_far_rules': lambda: Account.cpa_coa_menu_create_far_rules(),
            'create_journals': lambda: Account.cpa_coa_menu_create_journals(),
        }
        handler = dispatch.get(self.action_key)
        if not handler:
            raise UserError(_('Unknown COA action.'))
        return handler()
