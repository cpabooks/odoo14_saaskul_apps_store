# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CoaIfrsCodingPreviewLine(models.TransientModel):
    _name = 'coa.ifrs.coding.preview.line'
    _description = 'IFRS COA Coding Preview Line'
    _order = 'company_id, proposed_code, name'

    wizard_id = fields.Many2one('coa.ifrs.coding.wizard', required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', readonly=True)
    group_id = fields.Many2one('account.group', readonly=True)
    current_code = fields.Char(string='Current Code', readonly=True)
    proposed_code = fields.Char(string='Proposed Code', readonly=True)
    branch_code = fields.Char(string='BC', readonly=True, help='Branch code assigned to the company in this preview.')
    branch_digit = fields.Char(string='BC Digit', readonly=True, help='Separate company/branch code; not part of ledger code.')
    name = fields.Char(string='Ledger Name', readonly=True)
    company_id = fields.Many2one('res.company', string='Company / Branch', readonly=True)
    user_type_id = fields.Many2one('account.account.type', string='Type', readonly=True)
    bs_pl = fields.Selection(
        [('BS', 'BS'), ('PL', 'PL')],
        string='B/P',
        readonly=True,
    )
    ifrs_group_name = fields.Char(string='IFRS Group', readonly=True)
    proposed_group_name = fields.Char(string='Proposed Group', readonly=True)
    proposed_group_code = fields.Char(string='Proposed Group Code', readonly=True)
    proposed_series_code = fields.Char(string='Series Code', readonly=True)
    name_needs_review = fields.Boolean(readonly=True)
    suggested_name = fields.Char(string='Suggested Name', readonly=True)
    previous_name = fields.Char(string='Previous Name', readonly=True)
    edited_name = fields.Char(string='Edited Name')
    issue = fields.Selection(
        [
            ('ok', 'OK'),
            ('code_change', 'Code will change'),
            ('name_review', 'Name review'),
            ('code_change_name_review', 'Code & name review'),
        ],
        readonly=True,
    )
    name_action = fields.Selection(
        [
            ('skip', 'Skip'),
            ('accept', 'Accept suggestion'),
            ('edit', 'Use edited name'),
        ],
        string='Name action',
        default='skip',
    )


class CoaIfrsResetConfirmWizard(models.TransientModel):
    _name = 'coa.ifrs.reset.confirm.wizard'
    _description = 'IFRS Reset / Recode Confirmation'

    account_ids = fields.Many2many('account.account', string='Accounts')
    company_ids = fields.Many2many('res.company', string='Companies')
    message = fields.Text(readonly=True, default=lambda self: _(
        'Do you want to reset and regenerate Chart of Accounts codes using IFRS group series?\n\n'
        'L3 Ledger (4 digits): [Group Code][Sequence] — e.g. 5801 = Other Expenses sequence 01.\n'
        'BC / Company branch is separate and is not part of the ledger code.\n\n'
        'You will see a preview (old vs new code) before anything is saved. '
        'Journal entry lines are not changed; previous codes are stored on each ledger.'
    ))

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        accounts = self.env['account.account'].browse(active_ids).exists()
        if not accounts:
            accounts = self.env['account.account'].search([
                ('company_id', 'in', self.env.companies.ids),
            ])
        engine = self.env['coa.ifrs.coding']
        branch_companies = engine.branch_companies_for_accounts(accounts)
        values['account_ids'] = [(6, 0, accounts.ids)]
        values['company_ids'] = [(6, 0, branch_companies.ids)]
        return values

    def _open_coding_wizard(self):
        wizard = self.env['coa.ifrs.coding.wizard'].create({
            'account_ids': [(6, 0, self.account_ids.ids)],
            'company_ids': [(6, 0, self.company_ids.ids)],
        })
        view = self.env.ref('chart_of_accounts_saaskul.view_coa_ifrs_coding_wizard_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('IFRS Reset / Recode'),
            'res_model': 'coa.ifrs.coding.wizard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'res_id': wizard.id,
        }

    def action_preview_new_codes(self):
        self.ensure_one()
        wizard = self.env['coa.ifrs.coding.wizard'].create({
            'account_ids': [(6, 0, self.account_ids.ids)],
            'company_ids': [(6, 0, self.company_ids.ids)],
        })
        return wizard.action_preview()

    def action_reset_and_generate(self):
        self.ensure_one()
        wizard = self.env['coa.ifrs.coding.wizard'].create({
            'account_ids': [(6, 0, self.account_ids.ids)],
            'company_ids': [(6, 0, self.company_ids.ids)],
        })
        return wizard.with_context(cpa_ifrs_reset_generate=True).action_preview()


class CoaIfrsCodingWizard(models.TransientModel):
    _name = 'coa.ifrs.coding.wizard'
    _description = 'IFRS 4-Digit Branch COA Coding'

    account_ids = fields.Many2many('account.account', string='Accounts')
    company_ids = fields.Many2many(
        'res.company',
        'coa_ifrs_coding_wizard_company_rel',
        'wizard_id',
        'company_id',
        string='Branch companies (max 9)',
        help='Company/branch selection. BC is displayed separately and is not part of ledger code.',
    )
    state = fields.Selection(
        [('options', 'Options'), ('preview', 'Preview')],
        default='options',
    )
    update_groups = fields.Boolean(
        string='Sync IFRS account groups',
        default=True,
        help=(
            'Preview 2-digit IFRS groups (first digit from ledger, second for subgroup). '
            'On apply, ledgers are linked to merged IFRS groups; empty legacy groups are removed.'
        ),
    )
    message = fields.Text(readonly=True)
    line_ids = fields.One2many('coa.ifrs.coding.preview.line', 'wizard_id', string='Preview')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids') or []
        accounts = self.env['account.account'].browse(active_ids).exists()
        if not accounts:
            accounts = self.env['account.account'].search([
                ('company_id', 'in', self.env.companies.ids),
            ])
        engine = self.env['coa.ifrs.coding']
        branch_companies = engine.branch_companies_for_accounts(accounts)
        values['company_ids'] = [(6, 0, branch_companies.ids)]
        values['account_ids'] = [(6, 0, accounts.ids)]
        return values

    def action_preview(self):
        self.ensure_one()
        engine = self.env['coa.ifrs.coding']
        accounts = self.account_ids.exists()
        if not accounts:
            raise UserError(_('No accounts selected.'))
        branch_companies = engine.branch_companies_for_accounts(
            accounts, preferred_company_ids=self.company_ids.ids,
        )
        self.company_ids = branch_companies
        branch_legend = ', '.join(
            '%s = BC%s' % (company.name, engine.company_branch_digit(company, branch_companies))
            for company in branch_companies
        )
        force_regenerate = bool(self.env.context.get('cpa_ifrs_reset_generate'))
        line_vals = engine.preview_lines(
            accounts,
            branch_companies,
            update_groups=self.update_groups,
            force_regenerate=force_regenerate,
        )
        self.write({
            'line_ids': [(5, 0, 0)] + [(0, 0, vals) for vals in line_vals],
            'state': 'preview',
            'message': _(
                'Preview L3 ledger codes (IFRS group code + sequence). '
                'BC: %s. %s '
                'Group controls the ledger code series. '
                'Review before applying; journal entries are not changed.'
            ) % (branch_legend, engine._ifrs_range_help_text()),
        })
        view = self.env.ref('chart_of_accounts_saaskul.view_coa_ifrs_coding_preview_form')
        action = {
            'type': 'ir.actions.act_window',
            'name': _('IFRS Reset / Recode Preview'),
            'res_model': self._name,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'res_id': self.id,
        }
        if self.env.context.get('cpa_ifrs_reset_generate'):
            action['context'] = dict(self.env.context, cpa_ifrs_show_reset_generate=True)
        return action

    def _validate_preview_lines(self):
        self.ensure_one()
        for line in self.line_ids:
            code = (line.proposed_code or '').strip()
            if len(code) != 4 or not code.isdigit():
                raise UserError(
                    _('Invalid proposed code %(code)s for %(name)s.')
                    % {'code': code, 'name': line.name}
                )

    def action_apply(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Run preview first.'))
        self._validate_preview_lines()
        count = self.env['coa.ifrs.coding'].apply_plan(
            self.line_ids, update_groups=self.update_groups,
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('IFRS Coding'),
                'message': _('Updated %s ledger(s). Existing postings were kept; only codes/names changed as selected.') % count,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }


class CoaIfrsNameSuggestionWizard(models.TransientModel):
    _name = 'coa.ifrs.name.suggestion.wizard'
    _description = 'IFRS Ledger / Group Name Suggestion'

    account_id = fields.Many2one('account.account', readonly=True)
    group_id = fields.Many2one('account.group', readonly=True)
    current_name = fields.Char(readonly=True)
    suggested_name = fields.Char(readonly=True)
    edited_name = fields.Char(string='Ledger / group name')
    previous_name = fields.Char(readonly=True)
    message = fields.Text(readonly=True)

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        account = self.env['account.account'].browse(
            self.env.context.get('default_account_id')
            or self.env.context.get('active_id')
        ).exists()
        group = self.env['account.group'].browse(
            self.env.context.get('default_group_id')
        ).exists()
        engine = self.env['coa.ifrs.coding']
        if account:
            values.update({
                'account_id': account.id,
                'current_name': account.name,
                'suggested_name': engine.suggest_ifrs_name(account),
                'edited_name': engine.suggest_ifrs_name(account),
                'previous_name': getattr(account, 'cpabooks_previous_name', '') or '',
                'message': _(
                    'This ledger/group name may need IFRS naming correction. '
                    'Do you want to update?'
                ),
            })
        elif group:
            values.update({
                'group_id': group.id,
                'current_name': group.name,
                'suggested_name': group.name,
                'edited_name': group.name,
                'message': _(
                    'This group name may need IFRS naming correction. '
                    'Do you want to update?'
                ),
            })
        return values

    @api.model
    def create_from_account(self, account):
        if not account or not self.env['coa.ifrs.coding'].name_needs_ifrs_review(account.name):
            return False
        wizard = self.create({
            'account_id': account.id,
            'current_name': account.name,
            'suggested_name': self.env['coa.ifrs.coding'].suggest_ifrs_name(account),
            'edited_name': self.env['coa.ifrs.coding'].suggest_ifrs_name(account),
            'previous_name': account.cpabooks_previous_name or '',
            'message': _(
                'This ledger/group name may need IFRS naming correction. '
                'Do you want to update?'
            ),
        })
        wizard_id = wizard.id
        partner = self.env.user.partner_id

        def open_wizard():
            action = self.browse(wizard_id).action_open()
            if partner:
                self.env['bus.bus'].sendone(
                    (self.env.cr.dbname, 'res.partner', partner.id),
                    {'type': 'ir.actions.act_window', 'action': action},
                )

        self.env.cr.postcommit.add(open_wizard)
        return True

    def action_open(self):
        self.ensure_one()
        view = self.env.ref('chart_of_accounts_saaskul.view_coa_ifrs_name_suggestion_wizard_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('IFRS naming suggestion'),
            'res_model': self._name,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'res_id': self.id,
        }

    def action_accept(self):
        self.ensure_one()
        self._apply_name(self.suggested_name)
        return {'type': 'ir.actions.act_window_close'}

    def action_edit(self):
        self.ensure_one()
        if not (self.edited_name or '').strip():
            raise UserError(_('Enter a name or click Skip.'))
        self._apply_name(self.edited_name.strip())
        return {'type': 'ir.actions.act_window_close'}

    def action_skip(self):
        return {'type': 'ir.actions.act_window_close'}

    def _apply_name(self, new_name):
        engine = self.env['coa.ifrs.coding']
        if self.account_id:
            account = self.account_id.with_context(cpabooks_skip_ifrs_name_wizard=True)
            old = account.name
            vals = {'name': new_name}
            if old != new_name:
                vals['cpabooks_previous_name'] = old
            account.write(vals)
        elif self.group_id:
            self.group_id.with_context(cpabooks_skip_ifrs_name_wizard=True).write({
                'name': new_name,
            })
