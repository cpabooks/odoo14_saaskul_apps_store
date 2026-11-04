import logging
import re
from collections import Counter, defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class CoaBulkActionsWizardLine(models.TransientModel):
    _name = 'coa.bulk.actions.wizard.line'
    _description = 'COA Bulk Action Preview Line'
    _rec_name = 'name'

    wizard_id = fields.Many2one('coa.bulk.actions.wizard', required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    code = fields.Char(readonly=True)
    name = fields.Char(readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    user_type_id = fields.Many2one('account.account.type', string='Type', readonly=True)
    group_id = fields.Many2one('account.group', readonly=True)
    move_line_count = fields.Integer(string='Journal Items', readonly=True)
    balance = fields.Float(string='Balance', readonly=True, digits=(16, 2))
    can_delete = fields.Boolean(string='Unused', readonly=True)
    is_used = fields.Boolean(string='Used', readonly=True)
    usage_label = fields.Char(string='Status', compute='_compute_usage_label', readonly=True)
    selected = fields.Boolean(string='Select', default=False)

    @api.depends('is_used', 'move_line_count', 'balance')
    def _compute_usage_label(self):
        for line in self:
            if line.is_used:
                line.usage_label = _('Used (%s items, balance %s)') % (
                    line.move_line_count or 0,
                    line.balance,
                )
            elif line.balance:
                line.usage_label = _('Unused (no items, balance %s)') % line.balance
            else:
                line.usage_label = _('Unused (no entries)')


class CoaResetCodePreviewWizardLine(models.TransientModel):
    _name = 'coa.reset.code.preview.wizard.line'
    _description = 'COA Reset Code Preview Line'

    wizard_id = fields.Many2one('coa.reset.code.preview.wizard', required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    company_id = fields.Many2one('res.company', readonly=True)
    current_code = fields.Char(readonly=True)
    suggested_code = fields.Char(readonly=True)
    name = fields.Char(readonly=True)
    user_type_id = fields.Many2one('account.account.type', string='Type', readonly=True)
    group_key = fields.Char(string='Match Group', readonly=True)
    issue = fields.Selection([
        ('ok', 'Aligned'),
        ('company_duplicate', 'Duplicate in Company'),
        ('changed', 'Will Change'),
    ], readonly=True)
    suggested_fix = fields.Char(readonly=True)


class CoaResetCodePreviewWizard(models.TransientModel):
    _name = 'coa.reset.code.preview.wizard'
    _description = 'COA Reset Code Preview'

    line_ids = fields.One2many('coa.reset.code.preview.wizard.line', 'wizard_id', readonly=True)
    message = fields.Text(readonly=True)
    code_digit_length = fields.Selection([('4', '4'), ('6', '6')], readonly=True)
    company_code_mode = fields.Selection(
        [('shared', 'Shared'), ('company_prefix', 'Company prefix')],
        readonly=True,
    )

    def action_apply_reset(self):
        accounts = self.line_ids.mapped('account_id').exists()
        options = {
            'code_digits': int(self.code_digit_length or 4),
            'company_code_mode': self.company_code_mode or 'shared',
        }
        result = accounts.with_context(cpa_reset_code_options=options).action_reset_code_digits()
        accounts.mapped('company_id').sudo().write({
            'cpabooks_coa_code_digits': self.code_digit_length or '4',
        })
        self.env['ir.ui.view'].clear_caches()
        return result


class CoaBulkActionsWizard(models.TransientModel):
    _name = 'coa.bulk.actions.wizard'
    _description = 'Merge COA'

    def _auto_init(self):
        res = super()._auto_init()
        from odoo.tools.sql import column_exists, create_column
        if not column_exists(self._cr, self._table, 'limit_to_merge_ledgers'):
            create_column(self._cr, self._table, 'limit_to_merge_ledgers', 'boolean')
        return res

    operation_mode = fields.Selection(
        [
            ('merge', 'Merge COA'),
            ('delete_unused', 'Delete Unused COA'),
        ],
        default='merge',
        required=True,
    )
    show_only_unused = fields.Boolean(
        string='Show only unused ledgers',
        default=True,
        help='When enabled, hide ledgers that already have journal items.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.companies.ids)],
    )
    show_company_selector = fields.Boolean(
        compute='_compute_show_company_selector',
    )
    account_ids = fields.Many2many('account.account', string='Accounts')
    line_ids = fields.One2many('coa.bulk.actions.wizard.line', 'wizard_id', string='Accounts')
    source_account_ids = fields.Many2many(
        'account.account',
        'coa_bulk_actions_source_account_rel',
        'wizard_id',
        'account_id',
        string='Merge From',
        domain="[('company_id', '=', company_id)]",
    )
    target_account_id = fields.Many2one(
        'account.account',
        string='Merge Into',
        domain="[('company_id', '=', company_id)]",
    )
    limit_to_merge_ledgers = fields.Boolean(
        string='Show only merge ledgers',
        help='List only the "Merge from" / "Merge into" ledgers. '
             'Untick to browse every ledger of the company.',
    )
    message = fields.Text(readonly=True)

    @api.depends_context('allowed_company_ids')
    def _compute_show_company_selector(self):
        multi = len(self.env.companies) > 1
        for wizard in self:
            wizard.show_company_selector = multi

    @api.model
    def _cpabooks_accounts_for_company(self, company):
        company = company or self.env.company
        return self.env['account.account'].search([('company_id', '=', company.id)])

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        company = self.env.company
        active_ids = self.env.context.get('active_ids') or []
        accounts = self.env['account.account'].browse(active_ids).exists()
        prefill_sources = self.env.context.get('cpabooks_merge_prefill_sources')
        if accounts:
            account_companies = accounts.mapped('company_id')
            if len(account_companies) == 1:
                company = account_companies
            else:
                accounts = accounts.filtered(lambda account: account.company_id == company)
        else:
            prefill_sources = False
            accounts = self._cpabooks_accounts_for_company(company)
        values['company_id'] = company.id
        values['account_ids'] = [(6, 0, accounts.ids)]
        if prefill_sources and accounts:
            # Clicked / selected ledgers become Merge From, with a suggested target.
            values['source_account_ids'] = [(6, 0, accounts.ids)]
            values['limit_to_merge_ledgers'] = True
            suggestion = self._suggest_move_target_account(accounts, company)
            if suggestion:
                values['target_account_id'] = suggestion.id
        if self.env.context.get('default_operation_mode'):
            values['operation_mode'] = self.env.context['default_operation_mode']
        if 'default_show_only_unused' in self.env.context:
            values['show_only_unused'] = self.env.context['default_show_only_unused']
        return values

    @api.model
    def create(self, vals):
        if vals.get('operation_mode') == 'delete_unused':
            vals.setdefault('show_only_unused', True)
        wizard = super().create(vals)
        wizard._sync_accounts_for_company()
        wizard._refresh_lines()
        return wizard

    def write(self, vals):
        res = super().write(vals)
        if 'company_id' in vals:
            self._sync_accounts_for_company()
            self._refresh_lines()
        elif 'limit_to_merge_ledgers' in vals:
            self._refresh_lines()
        return res

    @api.onchange('company_id', 'show_only_unused')
    def _onchange_company_id(self):
        company = self.company_id
        # Keep prefilled Merge From / Merge Into when they belong to this company.
        if company:
            self.source_account_ids = self.source_account_ids.filtered(
                lambda account: account.company_id == company
            )
            if self.target_account_id and self.target_account_id.company_id != company:
                self.target_account_id = False
        else:
            self.source_account_ids = self.env['account.account']
            self.target_account_id = False
        self._sync_accounts_for_company()
        self._refresh_lines()
        self._cpabooks_suggest_target_account()

    @api.onchange('source_account_ids')
    def _onchange_source_account_ids(self):
        self._cpabooks_suggest_target_account()
        if self.limit_to_merge_ledgers:
            self._refresh_lines()

    @api.onchange('target_account_id')
    def _onchange_target_account_id(self):
        if self.limit_to_merge_ledgers:
            self._refresh_lines()

    @api.onchange('limit_to_merge_ledgers')
    def _onchange_limit_to_merge_ledgers(self):
        self._refresh_lines()

    def _cpabooks_suggest_target_account(self):
        """Suggest Merge Into for the current Merge From selection."""
        for wizard in self:
            sources = wizard.source_account_ids
            if not sources:
                continue
            target = wizard.target_account_id
            if target and target not in sources:
                continue
            suggestion = wizard._suggest_move_target_account(sources, wizard.company_id)
            wizard.target_account_id = suggestion or False

    def _sync_accounts_for_company(self):
        for wizard in self:
            if not wizard.company_id:
                continue
            wizard.account_ids = wizard._cpabooks_accounts_for_company(wizard.company_id)

    @api.onchange('account_ids')
    def _onchange_account_ids(self):
        self._refresh_lines()

    def _cpabooks_line_accounts(self):
        """Ledgers listed below the merge fields."""
        self.ensure_one()
        if self.operation_mode == 'merge' and self.limit_to_merge_ledgers:
            picked = self.source_account_ids | self.target_account_id
            if picked:
                return picked
        return self.account_ids

    def _refresh_lines(self):
        for wizard in self:
            selected_account_ids = set(
                wizard.line_ids.filtered('selected').mapped('account_id').ids
            )
            commands = [(5, 0, 0)]
            listed_accounts = wizard._cpabooks_line_accounts()
            account_ids = listed_accounts.ids
            move_data = wizard._move_line_counts(account_ids)
            balance_data = wizard._account_balances(account_ids)
            ordered_accounts = listed_accounts.sorted(
                lambda account: (account.company_id.name or '', account.code or '', account.name or '')
            )
            for account in ordered_accounts:
                move_count = move_data.get(account.id, 0)
                is_used = bool(move_count)
                if wizard.operation_mode == 'delete_unused' and wizard.show_only_unused and is_used:
                    continue
                commands.append((0, 0, {
                    'account_id': account.id,
                    'code': account.code,
                    'name': account.name,
                    'company_id': account.company_id.id,
                    'user_type_id': account.user_type_id.id,
                    'group_id': account.group_id.id,
                    'move_line_count': move_count,
                    'balance': balance_data.get(account.id, 0.0),
                    'can_delete': not is_used,
                    'is_used': is_used,
                    'selected': account.id in selected_account_ids,
                }))
            wizard.line_ids = commands

    def _get_selected_lines(self):
        self.ensure_one()
        if self.line_ids:
            self.line_ids.flush(['selected'])
        lines = self.line_ids.filtered('selected')
        if not lines:
            lines = self.env['coa.bulk.actions.wizard.line'].search([
                ('wizard_id', '=', self.id),
                ('selected', '=', True),
            ])
        return lines

    def _get_selected_accounts(self):
        return self._get_selected_lines().mapped('account_id').exists()

    @api.model
    def _suggest_move_target_account(self, source_accounts, company=None):
        """Pick a same-company ledger to receive journal items (similar type when possible)."""
        source_accounts = source_accounts.exists()
        if not source_accounts:
            return self.env['account.account']
        company = company or source_accounts[0].company_id
        exclude_ids = source_accounts.ids
        base_domain = [
            ('company_id', '=', company.id),
            ('id', 'not in', exclude_ids),
            ('deprecated', '=', False),
        ]
        user_types = source_accounts.mapped('user_type_id')
        if len(user_types) == 1:
            match = self.env['account.account'].search(
                base_domain + [('user_type_id', '=', user_types.id)],
                order='code, id',
                limit=1,
            )
            if match:
                return match
        return self.env['account.account'].search(
            base_domain, order='code, id', limit=1,
        )

    def action_select_all_visible(self):
        self.ensure_one()
        if self.line_ids:
            self.line_ids.write({'selected': True})
        return self._reload()

    def action_select_all_unused(self):
        self.ensure_one()
        if self.line_ids:
            self.line_ids.filtered('is_used').write({'selected': False})
            self.line_ids.filtered(lambda line: not line.is_used).write({'selected': True})
        return self._reload()

    def action_clear_selection(self):
        self.ensure_one()
        if self.line_ids:
            self.line_ids.write({'selected': False})
        return self._reload()

    def _move_line_counts(self, account_ids):
        if not account_ids:
            return {}
        self.env.cr.execute("""
            SELECT account_id, COUNT(*)
              FROM account_move_line
             WHERE account_id = ANY(%s)
             GROUP BY account_id
        """, [account_ids])
        return dict(self.env.cr.fetchall())

    def _account_balances(self, account_ids):
        if not account_ids:
            return {}
        self.env.cr.execute("""
            SELECT account_id,
                   COALESCE(SUM(debit), 0) - COALESCE(SUM(credit), 0)
              FROM account_move_line
             WHERE account_id = ANY(%s)
             GROUP BY account_id
        """, [account_ids])
        return dict(self.env.cr.fetchall())

    def _table_column_exists(self, table_name, column_name):
        self.env.cr.execute("""
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = %s
               AND column_name = %s
             LIMIT 1
        """, [table_name, column_name])
        return bool(self.env.cr.fetchone())

    def _reload(self):
        self.ensure_one()
        if self.operation_mode == 'delete_unused':
            view = self.env.ref(
                'chart_of_accounts_saaskul.view_coa_delete_unused_wizard_form',
            )
            title = _('Delete Unused COA')
        else:
            view = self.env.ref('chart_of_accounts_saaskul.view_coa_bulk_actions_wizard_form')
            title = _('Merge COA')
        return {
            'type': 'ir.actions.act_window',
            'name': title,
            'res_model': self._name,
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'res_id': self.id,
        }

    def action_refresh(self):
        self.ensure_one()
        self._refresh_lines()
        return self._reload()

    def action_archive_selected(self):
        self.ensure_one()
        accounts = self._get_selected_accounts()
        if not accounts:
            raise UserError(_(
                'No ledgers selected. Tick Select on rows, or click '
                '"Select all unused" / "Select all on page", then Archive.'
            ))
        if any(account.company_id != self.company_id for account in accounts):
            raise UserError(_('Selected ledgers must belong to %s.') % self.company_id.display_name)

        accounts.write({'deprecated': True})
        self.write({
            'message': _('Archived (deprecated): %s') % ', '.join(accounts.mapped('display_name')),
        })
        self._sync_accounts_for_company()
        self._refresh_lines()
        return self._reload()

    def action_delete_selected(self):
        self.ensure_one()
        lines = self._get_selected_lines()
        if not lines:
            raise UserError(_(
                'No ledgers selected. Tick Select on each row, or use '
                '"Select all unused" (recommended), then click Delete.\n\n'
                'Ledgers with journal items: use Delete to open "move entries" '
                'or pick a target ledger and Archive if delete is blocked.'
            ))

        accounts = lines.mapped('account_id').exists()
        if any(account.company_id != self.company_id for account in accounts):
            raise UserError(_('Selected ledgers must belong to %s.') % self.company_id.display_name)

        unused_lines = lines.filtered(lambda line: not line.is_used)
        used_lines = lines.filtered('is_used')

        if used_lines and not unused_lines:
            return self._open_delete_move_wizard(used_lines.mapped('account_id'))

        messages = []
        if unused_lines:
            delete_result = self._delete_or_archive_accounts(unused_lines.mapped('account_id'))
            messages.extend(delete_result.get('messages', []))

        if used_lines:
            move_action = self._open_delete_move_wizard(used_lines.mapped('account_id'))
            if messages:
                self.write({'message': '\n'.join(messages)})
            return move_action

        if messages:
            self.write({'message': '\n'.join(messages)})
        self._sync_accounts_for_company()
        self._refresh_lines()
        return self._reload()

    def _delete_or_archive_accounts(self, accounts):
        """Try unlink; archive (deprecated) when Odoo blocks deletion."""
        self.ensure_one()
        accounts = accounts.exists()
        deleted_names = []
        archived_names = []
        failed = []
        for account in accounts:
            name = account.display_name
            try:
                with self.env.cr.savepoint():
                    account.unlink()
                deleted_names.append(name)
            except Exception as error:
                try:
                    with self.env.cr.savepoint():
                        account.write({'deprecated': True})
                    archived_names.append(name)
                except Exception as dep_error:
                    failed.append('%s (%s)' % (name, dep_error))

        messages = []
        if deleted_names:
            messages.append(_('Deleted: %s') % ', '.join(deleted_names))
        if archived_names:
            messages.append(
                _('Could not delete (still linked in configuration) — archived instead: %s')
                % ', '.join(archived_names)
            )
        if failed:
            messages.append(
                _('Could not delete or archive: %s. Move journal items to another ledger first.')
                % '; '.join(failed)
            )
        return {'messages': messages, 'deleted': deleted_names, 'archived': archived_names}

    def _delete_accounts_direct(self, accounts):
        self.ensure_one()
        result = self._delete_or_archive_accounts(accounts)
        if result.get('messages'):
            self.write({
                'source_account_ids': [(6, 0, (self.source_account_ids - accounts).ids)],
                'message': '\n'.join(result['messages']),
            })
        self._sync_accounts_for_company()
        self._refresh_lines()
        return self._reload()

    def _open_delete_move_wizard(self, accounts):
        self.ensure_one()
        accounts = accounts.exists()
        suggestion = self._suggest_move_target_account(accounts, self.company_id)
        vals = {
            'bulk_wizard_id': self.id,
            'company_id': self.company_id.id,
            'account_ids': [(6, 0, accounts.ids)],
        }
        if suggestion:
            vals['target_account_id'] = suggestion.id
        delete_wizard = self.env['coa.bulk.delete.wizard'].create(vals)
        view = self.env.ref('chart_of_accounts_saaskul.view_coa_bulk_delete_wizard_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Move entries and delete'),
            'res_model': 'coa.bulk.delete.wizard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'res_id': delete_wizard.id,
        }

    def _cpabooks_reassign_move_lines(self, target, sources):
        source_ids = tuple(sources.ids)
        if not source_ids:
            return 0
        self.env.cr.execute(
            """
            UPDATE account_move_line
               SET account_id = %s
             WHERE account_id IN %s
            """,
            (target.id, source_ids),
        )
        updated = self.env.cr.rowcount
        self.env['account.move.line'].invalidate_cache()
        return updated

    def _cpabooks_reassign_bank_statement_lines(self, target, sources):
        if not self._table_column_exists('account_bank_statement_line', 'account_id'):
            return 0
        source_ids = tuple(sources.ids)
        if not source_ids:
            return 0
        self.env.cr.execute(
            """
            UPDATE account_bank_statement_line
               SET account_id = %s
             WHERE account_id IN %s
            """,
            (target.id, source_ids),
        )
        return self.env.cr.rowcount

    def _cpabooks_reassign_audited_financial_group_lines(self, target, sources):
        """Merge AFG mappings; drop source row when target is already in the same group."""
        if 'audited.financial.group.line' not in self.env:
            return 0
        AfgLine = self.env['audited.financial.group.line'].sudo()
        source_lines = AfgLine.search([('account_id', 'in', sources.ids)])
        if not source_lines:
            return 0
        merged = 0
        for line in source_lines:
            conflict = AfgLine.search(
                [
                    ('group_id', '=', line.group_id.id),
                    ('account_id', '=', target.id),
                    ('id', '!=', line.id),
                ],
                limit=1,
            )
            if conflict:
                line.unlink()
            else:
                line.write({'account_id': target.id})
                merged += 1
        return merged

    def _cpabooks_reassign_audited_financial_lines(self, target, sources):
        if 'audited.financial.line' not in self.env:
            return 0
        table = self.env['audited.financial.line']._table
        if not self._table_column_exists(table, 'account_id'):
            return 0
        source_ids = tuple(sources.ids)
        if not source_ids:
            return 0
        self.env.cr.execute(
            """
            UPDATE audited_financial_line
               SET account_id = %s
             WHERE account_id IN %s
            """,
            (target.id, source_ids),
        )
        return self.env.cr.rowcount

    def _cpabooks_reassign_ir_properties(self, target, sources):
        Property = self.env['ir.property'].sudo()
        source_refs = ['account.account,%s' % account_id for account_id in sources.ids]
        target_ref = 'account.account,%s' % target.id
        for prop in Property.search([('value_reference', 'in', source_refs)]):
            conflict = Property.search(
                [
                    ('fields_id', '=', prop.fields_id.id),
                    ('company_id', '=', prop.company_id.id),
                    ('res_id', '=', prop.res_id),
                    ('id', '!=', prop.id),
                    ('value_reference', '=', target_ref),
                ],
                limit=1,
            )
            if conflict:
                prop.unlink()
            else:
                prop.write({'value_reference': target_ref})

    def _cpabooks_merge_skip_models(self):
        return {
            'account.account',
            'account.move.line',
            'coa.bulk.actions.wizard',
            'coa.bulk.actions.wizard.line',
            'ir.property',
            'audited.financial.group.line',
            'audited.financial.line',
            'account.aged.partner',
            'account.aged.receivable',
            'account.aged.payable',
            'account.accounting.report',
            'account.invoice.report',
        }

    def _cpabooks_merge_skip_model_name(self, model_name):
        if not model_name:
            return True
        if model_name in self._cpabooks_merge_skip_models():
            return True
        if 'report' in model_name or model_name.endswith('.wizard'):
            return True
        if model_name not in self.env:
            return True
        if self.env[model_name]._transient:
            return True
        return False

    def _cpabooks_sql_update_account_m2o(self, table, column, target, sources):
        if not sources or not self._table_column_exists(table, column):
            return 0
        # Table/column names come from the ORM registry (not user input).
        self.env.cr.execute(
            """
            UPDATE "%s"
               SET "%s" = %%s
             WHERE "%s" IN %%s
            """ % (table.replace('"', ''), column.replace('"', ''), column.replace('"', '')),
            (target.id, tuple(sources.ids)),
        )
        return self.env.cr.rowcount

    def _cpabooks_sql_delete_account_m2o(self, table, column, sources):
        if not sources or not self._table_column_exists(table, column):
            return 0
        self.env.cr.execute(
            """
            DELETE FROM "%s"
             WHERE "%s" IN %%s
            """ % (table.replace('"', ''), column.replace('"', '')),
            (tuple(sources.ids),),
        )
        return self.env.cr.rowcount

    def _cpabooks_clear_accounting_report_rows(self, sources):
        """Remove cached report rows; ORM write triggers report_options KeyError."""
        cleared = 0
        for model_name in (
            'account.aged.partner',
            'account.aged.receivable',
            'account.aged.payable',
        ):
            if model_name not in self.env:
                continue
            table = self.env[model_name]._table
            cleared += self._cpabooks_sql_delete_account_m2o(table, 'account_id', sources)
        return cleared

    def _cpabooks_reassign_stored_many2one_refs(self, target, sources):
        """Reassign stored Many2one fields via SQL (avoids report/wizard ORM side effects)."""
        skip_models = self._cpabooks_merge_skip_models()
        field_recs = self.env['ir.model.fields'].sudo().search([
            ('relation', '=', 'account.account'),
            ('ttype', '=', 'many2one'),
            ('store', '=', True),
        ])
        for field_rec in field_recs:
            model_name = field_rec.model_id.model
            field_name = field_rec.name
            if self._cpabooks_merge_skip_model_name(model_name):
                continue
            Model = self.env[model_name]
            if field_name not in Model._fields:
                continue
            table = Model._table
            try:
                with self.env.cr.savepoint():
                    self._cpabooks_sql_update_account_m2o(
                        table, field_name, target, sources,
                    )
            except Exception as error:
                _logger.warning(
                    'COA merge: could not reassign %s.%s via SQL: %s',
                    model_name, field_name, error,
                )
                continue

    def _cpabooks_merge_accounts_into(self, target, sources):
        # Odoo 14 Environment has no .sudo(); use env(su=True) / recordset.sudo().
        env = self.env(su=True)
        target = target.sudo()
        sources = (sources - target).sudo().exists()
        if not sources:
            return {'lines_moved': 0, 'deleted': [], 'deprecated': []}

        lines_moved = self._cpabooks_reassign_move_lines(target, sources)
        self._cpabooks_reassign_bank_statement_lines(target, sources)
        self._cpabooks_reassign_ir_properties(target, sources)
        self._cpabooks_clear_accounting_report_rows(sources)
        self._cpabooks_reassign_audited_financial_group_lines(target, sources)
        self._cpabooks_reassign_audited_financial_lines(target, sources)
        self._cpabooks_reassign_stored_many2one_refs(target, sources)
        env['ir.property'].flush()
        if 'audited.financial.group.line' in env:
            env['audited.financial.group.line'].flush()

        deleted = []
        deprecated = []
        Account = env['account.account']
        for source_id in sources.ids:
            source = Account.browse(source_id)
            # Capture label before unlink — display_name after delete raises MissingError.
            name = source.display_name
            try:
                with env.cr.savepoint():
                    source.unlink()
                deleted.append(name)
            except Exception as error:
                try:
                    with env.cr.savepoint():
                        source.write({'deprecated': True})
                    deprecated.append('%s (%s)' % (name, error))
                except Exception as dep_error:
                    deprecated.append(
                        '%s (unlink: %s; deprecate: %s)'
                        % (name, error, dep_error)
                    )

        # Direct SQL above bypasses ORM cache.  In Odoo 14 invalidate the
        # environment cache object; Environment itself has no invalidate_cache.
        env.cache.invalidate()
        return {
            'lines_moved': lines_moved,
            'deleted': deleted,
            'deprecated': deprecated,
        }

    def action_merge_coa(self):
        self.ensure_one()
        target = self.target_account_id.exists()
        source_accounts = self.source_account_ids
        if not source_accounts:
            # Fall back to the ticked rows when "Merge from" was left empty.
            source_accounts = self._get_selected_accounts()
        sources = (source_accounts - target).exists()
        if not self.company_id:
            raise UserError(_('Select a company.'))
        if not target:
            raise UserError(_('Select the ledger to merge into (keep this account).'))
        if not sources:
            if source_accounts and target in source_accounts:
                raise UserError(
                    _('The merge-from and merge-into ledgers must be different. '
                      'Remove %s from "Merge from" or pick another target.')
                    % target.display_name
                )
            raise UserError(_('Select at least one ledger to merge from.'))
        if target.company_id != self.company_id:
            raise UserError(_('The target ledger must belong to %s.') % self.company_id.display_name)
        if any(source.company_id != self.company_id for source in sources):
            raise UserError(_('Merge ledgers only within %s.') % self.company_id.display_name)

        try:
            with self.env.cr.savepoint():
                merge_result = self._cpabooks_merge_accounts_into(target, sources)
        except UserError:
            raise
        except Exception as error:
            _logger.exception('COA merge failed for target %s', target.display_name)
            detail = error.args[0] if getattr(error, 'args', None) else str(error)
            raise UserError(
                _('Could not merge ledgers: %s')
                % detail
            ) from error

        remaining_accounts = self._cpabooks_accounts_for_company(self.company_id)
        parts = [
            _('Merged into %s (%s). %s journal item(s) moved.')
            % (target.display_name, self.company_id.display_name, merge_result['lines_moved']),
        ]
        if merge_result['deleted']:
            parts.append(_('Deleted source COA: %s') % ', '.join(merge_result['deleted']))
        if merge_result['deprecated']:
            parts.append(
                _('Deprecated source COA (still linked elsewhere): %s')
                % ', '.join(merge_result['deprecated'])
            )
        self.write({
            'account_ids': [(6, 0, remaining_accounts.ids)],
            'source_account_ids': [(5, 0, 0)],
            'target_account_id': target.id,
            'message': '\n'.join(parts),
        })
        self._refresh_lines()
        return self._reload()


class CoaBulkDeleteWizard(models.TransientModel):
    _name = 'coa.bulk.delete.wizard'
    _description = 'Move journal entries then delete ledgers'

    bulk_wizard_id = fields.Many2one(
        'coa.bulk.actions.wizard',
        string='Merge COA wizard',
        ondelete='cascade',
    )
    company_id = fields.Many2one('res.company', required=True, readonly=True)
    account_ids = fields.Many2many(
        'account.account',
        'coa_bulk_delete_wizard_account_rel',
        'wizard_id',
        'account_id',
        string='Ledgers to remove',
        readonly=True,
    )
    target_account_id = fields.Many2one(
        'account.account',
        string='Move entries into',
        required=True,
        domain="[('company_id', '=', company_id), ('id', 'not in', account_ids)]",
        help='Journal items on the selected ledgers are moved here before deletion.',
    )
    summary_html = fields.Html(compute='_compute_summary_html', sanitize=False)
    suggested_target_id = fields.Many2one(
        'account.account',
        string='Suggested target',
        compute='_compute_suggested_target_id',
        help='Suggested ledger to receive journal items (same company / similar type).',
    )

    @api.depends('account_ids', 'company_id')
    def _compute_suggested_target_id(self):
        BulkWizard = self.env['coa.bulk.actions.wizard']
        for wizard in self:
            wizard.suggested_target_id = BulkWizard._suggest_move_target_account(
                wizard.account_ids, wizard.company_id,
            )

    @api.model
    def create(self, vals):
        wizard = super().create(vals)
        if wizard.account_ids and not vals.get('target_account_id'):
            suggestion = self.env['coa.bulk.actions.wizard']._suggest_move_target_account(
                wizard.account_ids, wizard.company_id,
            )
            if suggestion:
                wizard.target_account_id = suggestion
        return wizard

    @api.depends('account_ids', 'account_ids.code', 'target_account_id')
    def _compute_summary_html(self):
        BulkWizard = self.env['coa.bulk.actions.wizard']
        for wizard in self:
            if not wizard.account_ids:
                wizard.summary_html = '<p class="mb-0">%s</p>' % _('No ledgers selected.')
                continue
            move_data = BulkWizard._move_line_counts(wizard.account_ids.ids)
            rows = []
            for account in wizard.account_ids.sorted(
                lambda rec: (rec.code or '', rec.name or '')
            ):
                count = move_data.get(account.id, 0)
                if count:
                    status = _('Used — %s journal item(s) will move') % count
                    css = 'text-warning'
                else:
                    status = _('Unused — no journal items')
                    css = 'text-success'
                rows.append(
                    '<tr><td>%s</td><td>%s</td><td class="%s">%s</td></tr>'
                    % (account.code or '', account.name or '', css, status)
                )
            suggestion = BulkWizard._suggest_move_target_account(
                wizard.account_ids, wizard.company_id,
            )
            suggest_html = ''
            if suggestion:
                suggest_html = (
                    '<p class="mb-2 text-info"><strong>%s</strong> %s — %s</p>'
                ) % (
                    _('Suggested target:'),
                    suggestion.code or '',
                    suggestion.display_name,
                )
            wizard.summary_html = (
                '<p class="mb-2">%s</p>'
                '%s'
                '<table class="table table-sm table-bordered mb-0">'
                '<thead><tr><th>%s</th><th>%s</th><th>%s</th></tr></thead>'
                '<tbody>%s</tbody></table>'
            ) % (
                _('These ledgers have journal items. Move them to another ledger, then delete.'),
                suggest_html,
                _('Code'),
                _('Name'),
                _('Status'),
                ''.join(rows),
            )

    def action_move_and_delete(self):
        self.ensure_one()
        accounts = self.account_ids.exists()
        target = self.target_account_id.exists()
        if not accounts:
            raise UserError(_('No ledgers to delete.'))
        if not target:
            raise UserError(_('Select the ledger to move journal entries into.'))
        if target in accounts:
            raise UserError(
                _('The target ledger cannot be one of the ledgers you are deleting.')
            )
        if target.company_id != self.company_id:
            raise UserError(_('The target ledger must belong to %s.') % self.company_id.display_name)

        bulk = self.bulk_wizard_id
        if not bulk:
            bulk = self.env['coa.bulk.actions.wizard'].create({
                'company_id': self.company_id.id,
                'account_ids': [(6, 0, self.env['coa.bulk.actions.wizard']._cpabooks_accounts_for_company(self.company_id).ids)],
            })
            bulk._refresh_lines()

        try:
            with self.env.cr.savepoint():
                merge_result = bulk._cpabooks_merge_accounts_into(target, accounts)
        except UserError:
            raise
        except Exception as error:
            _logger.exception('COA delete/move failed for target %s', target.display_name)
            detail = error.args[0] if getattr(error, 'args', None) else str(error)
            raise UserError(
                _('Could not move entries and delete ledgers: %s') % detail
            ) from error

        parts = [
            _('Moved journal items into %s (%s item(s)).')
            % (target.display_name, merge_result['lines_moved']),
        ]
        if merge_result['deleted']:
            parts.append(_('Deleted: %s') % ', '.join(merge_result['deleted']))
        if merge_result['deprecated']:
            parts.append(
                _('Could not delete (marked deprecated): %s')
                % ', '.join(merge_result['deprecated'])
            )

        bulk.write({
            'account_ids': [(6, 0, bulk._cpabooks_accounts_for_company(self.company_id).ids)],
            'source_account_ids': [(6, 0, (bulk.source_account_ids - accounts).ids)],
            'message': '\n'.join(parts),
        })
        bulk._refresh_lines()
        return bulk._reload()


class AccountAccount(models.Model):
    _inherit = 'account.account'

    def _cpa_coa_menu_accounts(self):
        return self.env['account.account'].search([
            ('company_id', 'in', self.env.companies.ids),
        ])

    def _cpa_coa_action_recordset(self, selection_only=False):
        """Match list-view header buttons: empty recordset, or selected lines."""
        if self:
            return self
        active_ids = self.env.context.get('active_ids') or []
        if active_ids:
            return self.env['account.account'].browse(active_ids).exists()
        if selection_only:
            return self.browse()
        return self.env['account.account']

    def _cpa_coa_menu_notification(self, title, message):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }

    def _cpa_coa_run_menu_method(self, method_name, title, message, selection_only=False):
        accounts = self._cpa_coa_action_recordset(selection_only=selection_only)
        method = getattr(accounts, method_name, None)
        if not callable(method):
            raise UserError(_(
                'COA action "%s" is not available. Upgrade module '
                'chart_of_accounts_saaskul, then restart Odoo.'
            ) % method_name)
        if selection_only and not accounts:
            raise UserError(_('Select one or more ledgers in the list, then run this action.'))
        result = method()
        if isinstance(result, dict):
            return result
        return self._cpa_coa_menu_notification(title, message)

    def cpa_coa_menu_reset_all(self):
        return self._cpa_coa_run_menu_method('reset_all', _('COA'), _('Reset all completed.'))

    def cpa_coa_menu_factory_reset(self):
        return self._cpa_coa_run_menu_method('delete_wizard', _('COA'), _('Factory reset wizard opened.'))

    def cpa_coa_menu_view_rules(self):
        return self._cpa_coa_run_menu_method('action_view_rules', _('COA'), _('Rules opened.'))

    def cpa_coa_menu_remove_groups(self):
        return self._cpa_coa_run_menu_method('action_remove_group', _('COA'), _('Groups removed.'))

    def _cpa_template_ledger_key(self, account):
        Version = self.env.get("audited.financial.version")
        if Version is not None and hasattr(Version, "_afg_pl_unique_ledger_key"):
            return Version._afg_pl_unique_ledger_key(account) or ""
        return (account.name or "").strip().lower()

    def _cpa_account_group_for_company(self, group, company):
        if not group or not company:
            return False
        if not group.company_id or group.company_id.id == company.id:
            return group.id
        cache = getattr(self.env.cr, "_cpa_group_company_cache", None)
        if cache is None:
            cache = {}
            self.env.cr._cpa_group_company_cache = cache
        cache_key = (group.id, company.id)
        if cache_key in cache:
            return cache[cache_key]
        Group = self.env["account.group"].sudo()
        found = Group.search([
            ("company_id", "=", company.id),
            ("name", "=", group.name),
        ], limit=1)
        if not found and group.code_prefix_start:
            found = Group.search([
                ("company_id", "=", company.id),
                ("code_prefix_start", "=", group.code_prefix_start),
                ("name", "=", group.name),
            ], limit=1)
        if not found:
            found = Group.with_context(skip_prefix_constraint=True).create({
                "name": group.name,
                "company_id": company.id,
                "code_prefix_start": group.code_prefix_start or False,
                "code_prefix_end": group.code_prefix_end or group.code_prefix_start or False,
            })
        cache[cache_key] = found.id
        return found.id

    def _cpa_afg_for_company(self, group, company):
        if not group:
            return False
        if "company_id" not in group._fields or not group.company_id or group.company_id.id == company.id:
            return group.id
        Group = self.env["audited.financial.group"].sudo()
        found = Group.search([("code", "=", group.code), ("company_id", "=", False)], limit=1)
        if not found:
            found = Group.search([("code", "=", group.code), ("company_id", "=", company.id)], limit=1)
        return (found or group).id

    def action_cpa_copy_group_setup(self, kinds, only_keys=None):
        """Copy grouping from the current company. Does not rename ledgers."""
        source = self.env.company
        Account = self.env["account.account"].sudo()
        templates = Account.search([("company_id", "=", source.id)])
        buckets = {}
        for account in Account.search([("company_id", "!=", False)]):
            key = self._cpa_template_ledger_key(account)
            if key:
                buckets.setdefault(key, Account.browse())
                buckets[key] |= account
        Line = None
        if "afg" in kinds and "audited.financial.group.line" in self.env:
            Line = self.env["audited.financial.group.line"].sudo().with_context(afg_skip_collapse=True)
        updated = 0
        for tmpl in templates:
            key = self._cpa_template_ledger_key(tmpl)
            if not key or (only_keys is not None and key not in only_keys):
                continue
            peers = (buckets.get(key) or Account.browse()).filtered(
                lambda account: account.company_id.id != source.id
            )
            if not peers:
                continue
            if "group" in kinds and tmpl.group_id:
                for peer in peers:
                    gid = self._cpa_account_group_for_company(tmpl.group_id, peer.company_id)
                    if gid and peer.group_id.id != gid:
                        self.env.cr.execute(
                            "UPDATE account_account SET group_id = %s WHERE id = %s",
                            (gid, peer.id),
                        )
                        updated += 1
            if "afg" in kinds and "afg_group_id" in tmpl._fields and tmpl.afg_group_id:
                gid = tmpl.afg_group_id.id
                if Line is not None:
                    Line.search([("account_id", "in", peers.ids)]).unlink()
                    for peer in peers:
                        target_gid = self._cpa_afg_for_company(tmpl.afg_group_id, peer.company_id) or gid
                        Line.create({"group_id": target_gid, "account_id": peer.id})
                        self.env.cr.execute(
                            "UPDATE account_account SET afg_group_id = %s WHERE id = %s",
                            (target_gid, peer.id),
                        )
                updated += len(peers)
            if "ctg" in kinds and "ctf_category" in tmpl._fields:
                category = tmpl.ctf_category or False
                ctf_group = tmpl.ctf_group_id if "ctf_group_id" in tmpl._fields else False
                if not category and ctf_group:
                    category = ctf_group.ctf_category
                if category or ctf_group:
                    payload = {}
                    if category:
                        payload["ctf_category"] = category
                    if ctf_group and "ctf_group_id" in Account._fields:
                        payload["ctf_group_id"] = ctf_group.id
                    if payload:
                        peers.with_context(afg_skip_same_name_sync=True).write(payload)
                        updated += len(peers)
        if "afg" in kinds:
            Account.invalidate_cache(fnames=["afg_group_id"])
        return updated

    def _cpa_selected_template_keys(self):
        accounts = self._cpa_coa_action_recordset()
        if not accounts:
            return None
        return {self._cpa_template_ledger_key(account) for account in accounts if self._cpa_template_ledger_key(account)}

    def cpa_coa_menu_update_all_groups(self):
        count = self.action_cpa_copy_group_setup(("group", "afg", "ctg"))
        return self._cpa_coa_menu_notification(
            _("Update all Groups"),
            _("Account group, AFG and CTG copied from %s to %s ledgers in other companies. Ledger names were not changed.")
            % (self.env.company.name, count),
        )

    def _cpa_setup_line_indexes(self):
        """Map COA Setup File rows by identity code, ledger code, and name."""
        by_identity = {}
        by_code_auto = {}
        by_code = {}
        by_revise = {}
        by_account_name = {}
        for line in self.env["cpa.coa.setup.line"].sudo().search([]):
            if not (line.group_name or "").strip():
                continue
            identity = (line.code or "").strip()
            if identity and identity.lower() != "new":
                by_identity[identity] = line
                by_code[identity] = line
            auto = re.sub(r"\D+", "", line.code_auto or "")
            if auto:
                by_code_auto[auto] = line
            revise = (line.account_name_revise or "").strip().lower()
            if revise and revise != "new":
                by_revise[revise] = line
            account_name = (line.account_name or "").strip().lower()
            if account_name and account_name != "new":
                by_account_name[account_name] = line
        return by_identity, by_code_auto, by_code, by_revise, by_account_name

    def _cpa_setup_line_for_account(self, account, indexes):
        by_identity, by_code_auto, by_code, by_revise, by_account_name = indexes
        if isinstance(account, dict):
            identity = account.get("identity_code") or ""
            code = account.get("code") or ""
            name = account.get("name") or ""
        else:
            identity = getattr(account, "identity_code", None) or ""
            code = account.code or ""
            name = account.name or ""
        identity = identity.strip()
        if identity and identity in by_identity:
            return by_identity[identity]
        digits = re.sub(r"\D+", "", code)
        if digits and digits in by_code_auto:
            return by_code_auto[digits]
        code = code.strip()
        if code and code in by_code:
            return by_code[code]
        name = name.strip().lower()
        if name and name in by_revise:
            return by_revise[name]
        if name and name in by_account_name:
            return by_account_name[name]
        return None

    def action_cpa_apply_setup_file_groups(self):
        """Set account group from the COA Setup File. Does not rename ledgers."""
        indexes = self._cpa_setup_line_indexes()
        Group = self.env["account.group"].sudo().with_context(
            skip_prefix_constraint=True,
            cpa_apply_setup_groups=True,
        )
        Account = self.env["account.account"].sudo().with_context(
            cpa_apply_setup_groups=True,
        )
        rows = Account.search_read(
            [],
            ["name", "code", "identity_code", "company_id", "group_id"],
        )
        pending = []
        group_names = {}
        for row in rows:
            line = self._cpa_setup_line_for_account(row, indexes)
            if not line:
                continue
            company_id = row["company_id"][0]
            gname = line.group_name.strip()
            group_names.setdefault(company_id, {})
            group_names[company_id].setdefault(gname, line)
            pending.append((row["id"], company_id, row["group_id"] and row["group_id"][0], gname))
        cache = {}
        for company_id, names in group_names.items():
            for gname, line in names.items():
                group = Group.search([
                    ("company_id", "=", company_id),
                    ("name", "=", gname),
                ], limit=1)
                if not group:
                    group = Group.create({
                        "name": gname,
                        "company_id": company_id,
                        "code_prefix_start": line.prefix_from or False,
                        "code_prefix_end": line.prefix_to or line.prefix_from or False,
                    })
                cache[(company_id, gname)] = group.id
        updated = 0
        for account_id, company_id, current_group_id, gname in pending:
            group_id = cache.get((company_id, gname))
            if group_id and current_group_id != group_id:
                self.env.cr.execute(
                    "UPDATE account_account SET group_id = %s WHERE id = %s",
                    (group_id, account_id),
                )
                updated += 1
        Account.invalidate_cache(fnames=["group_id", "cpabooks_group_code", "cpabooks_group_name"])
        return updated

    def cpa_coa_menu_reset_groups(self):
        return self.env['account.group'].action_cpa_reset_account_groups()

    def cpa_coa_menu_reset_groups_factory(self):
        return self.env['account.group'].action_cpa_reset_account_groups_factory()

    def cpa_coa_menu_reset_afg(self):
        count = self.action_cpa_copy_group_setup(("afg",), self._cpa_selected_template_keys())
        return self._cpa_coa_menu_notification(
            _("Reset AFG"),
            _("AFG copied from %s onto %s ledgers. Ledger names were not changed.")
            % (self.env.company.name, count),
        )

    def cpa_coa_menu_reset_ctf(self):
        count = self.action_cpa_copy_group_setup(("ctg",), self._cpa_selected_template_keys())
        return self._cpa_coa_menu_notification(
            _("Reset CTG"),
            _("CTG copied from %s onto %s ledgers. Ledger names were not changed.")
            % (self.env.company.name, count),
        )

    def action_cpa_update_all_groups(self):
        """Used when Chart of Accounts V1 is updated. Current company is the default."""
        self.sudo().action_cpa_copy_group_setup(("group", "afg", "ctg"))
        return True

    @api.model
    def cpa_coa_menu_view_duplicate_codes(self):
        return self.action_cpa_view_duplicate_codes()

    @api.model
    def cpa_coa_menu_fix_duplicate_codes(self):
        return self.action_cpa_fix_duplicate_codes()

    def cpa_coa_menu_create_prepaid_rules(self):
        return self._cpa_coa_run_menu_method('create_deferred_expense_model', _('COA'), _('Prepaid rules created.'))

    def cpa_coa_menu_toggle_code(self):
        return self._cpa_coa_run_menu_method('action_toggle_code', _('COA'), _('Code display toggled.'))

    def cpa_coa_menu_show_code_true(self):
        return self._cpa_coa_run_menu_method('action_show_code_true', _('COA'), _('Show Code enabled.'))

    def cpa_coa_menu_update_specific_ledger(self):
        return self._cpa_coa_run_menu_method(
            'action_update_selected',
            _('COA'),
            _('Specific ledgers updated.'),
            selection_only=True,
        )

    def cpa_coa_menu_create_far_rules(self):
        return self._cpa_coa_run_menu_method('action_create_far_rules', _('COA'), _('FAR rules created.'))

    def cpa_coa_menu_create_journals(self):
        return self._cpa_coa_run_menu_method('action_create_journals_from_coa', _('COA'), _('Journals created.'))

    def cpa_coa_menu_bulk_actions(self):
        return self.cpa_coa_menu_merge_coa()

    def cpa_coa_menu_merge_coa(self):
        accounts = self._cpa_coa_action_recordset()
        if accounts:
            return accounts.action_open_coa_merge_coa()
        return self._cpa_coa_menu_accounts().action_open_coa_merge_coa(
            prefill_sources=False,
        )

    def _cpa_unused_account_ids(self):
        """Ledgers in the open companies that have no journal items."""
        companies = self.env.companies.ids or self.env.company.ids
        self.env.cr.execute(
            """
            SELECT a.id
              FROM account_account a
             WHERE a.company_id = ANY(%s)
               AND NOT EXISTS (
                    SELECT 1 FROM account_move_line l WHERE l.account_id = a.id
               )
            """,
            (list(companies),),
        )
        return [row[0] for row in self.env.cr.fetchall()]

    def _cpa_unused_result_message(self, title, done, skipped):
        parts = []
        if done:
            shown = done[:30]
            extra = len(done) - len(shown)
            line = "%s: %s" % (title, ", ".join(shown))
            if extra:
                line += " and %s more" % extra
            parts.append(line)
        else:
            parts.append("%s: none." % title)
        if skipped:
            shown = skipped[:30]
            extra = len(skipped) - len(shown)
            line = "Skipped: %s" % "; ".join(shown)
            if extra:
                line += " and %s more" % extra
            parts.append(line)
        return "\n".join(parts)

    @api.model
    def cpa_coa_menu_delete_unused_coa(self):
        """Delete unused ledgers. Skip any that are still linked and report them."""
        accounts = self.browse(self._cpa_unused_account_ids()).exists()
        deleted = []
        skipped = []
        for account in accounts:
            label = account.display_name
            try:
                with self.env.cr.savepoint():
                    account.unlink()
                deleted.append(label)
            except Exception as error:
                reason = (str(error) or "could not delete").split("\n")[0][:180]
                skipped.append("%s (%s)" % (label, reason))
        message = self._cpa_unused_result_message("Deleted", deleted, skipped)
        return self._cpa_coa_menu_notification(_("Delete Unused COA"), message)

    @api.model
    def cpa_coa_menu_archive_unused_coa(self):
        """Archive unused ledgers. Skip any that cannot be archived and report them."""
        accounts = self.browse(self._cpa_unused_account_ids()).exists().filtered(
            lambda account: not account.deprecated
        )
        archived = []
        skipped = []
        for account in accounts:
            label = account.display_name
            try:
                with self.env.cr.savepoint():
                    account.write({"deprecated": True})
                archived.append(label)
            except Exception as error:
                reason = (str(error) or "could not archive").split("\n")[0][:180]
                skipped.append("%s (%s)" % (label, reason))
        message = self._cpa_unused_result_message("Archived", archived, skipped)
        return self._cpa_coa_menu_notification(_("Archive Unused COA"), message)

    def action_open_delete_unused_coa(self):
        accounts = self.exists()
        view = self.env.ref('chart_of_accounts_saaskul.view_coa_delete_unused_wizard_form')
        company = self.env.company
        if accounts:
            account_companies = accounts.mapped('company_id')
            if len(account_companies) == 1:
                company = account_companies
            else:
                accounts = accounts.filtered(lambda account: account.company_id == company)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delete Unused COA'),
            'res_model': 'coa.bulk.actions.wizard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': {
                'active_model': 'account.account',
                'active_ids': accounts.ids,
                'default_company_id': company.id,
                'default_operation_mode': 'delete_unused',
                'default_show_only_unused': True,
            },
        }

    def cpa_coa_menu_open_action_chooser(self):
        wizard = self.env['coa.menu.action.wizard'].create({})
        view = self.env.ref('chart_of_accounts_saaskul.view_coa_menu_action_wizard_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('COA Actions'),
            'res_model': 'coa.menu.action.wizard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'res_id': wizard.id,
        }

    def cpa_coa_menu_add_opening_balance(self):
        return self.env['account.move'].action_cpabooks_open_opening_balance_entry()

    def cpa_coa_menu_reset_code_digits(self):
        return self._cpa_coa_menu_accounts().action_open_reset_code_options()

    def cpa_coa_menu_ifrs_coding(self):
        accounts = self._cpa_coa_action_recordset()
        if accounts:
            return accounts.action_open_ifrs_coding_wizard()
        return self._cpa_coa_menu_accounts().action_open_ifrs_coding_wizard()

    def cpa_coa_menu_preview_reset_code_digits(self):
        return self.cpa_coa_menu_reset_code_digits()

    def action_open_ifrs_coding_wizard(self):
        accounts = self.exists() or self._cpa_coa_menu_accounts()
        wizard = self.env['coa.ifrs.reset.confirm.wizard'].create({
            'account_ids': [(6, 0, accounts.ids)],
        })
        view = self.env.ref('chart_of_accounts_saaskul.view_coa_ifrs_reset_confirm_wizard_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('IFRS Reset / Recode'),
            'res_model': 'coa.ifrs.reset.confirm.wizard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'res_id': wizard.id,
        }

    def action_open_reset_code_options(self):
        accounts = self.exists() or self._cpa_coa_menu_accounts()
        wizard = self.env['coa.reset.code.options.wizard'].create({
            'account_ids': [(6, 0, accounts.ids)],
        })
        view = self.env.ref('chart_of_accounts_saaskul.view_coa_reset_code_options_wizard_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reset Account Codes'),
            'res_model': 'coa.reset.code.options.wizard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'res_id': wizard.id,
        }

    @api.model
    def _cpa_reset_code_options(self):
        options = dict(self.env.context.get('cpa_reset_code_options') or {})
        code_digits = int(options.get('code_digits') or 4)
        if code_digits not in (4, 6):
            code_digits = 4
        company_code_mode = options.get('company_code_mode') or 'shared'
        if company_code_mode not in ('shared', 'company_prefix'):
            company_code_mode = 'shared'
        return code_digits, company_code_mode

    def _cpa_code_max_value(self, code_digits):
        return (10 ** code_digits) - 1

    def _cpa_companies_for_prefix(self, accounts):
        companies = accounts.mapped('company_id').sorted('id')
        if len(companies) > 9:
            raise UserError(
                _('Company prefix mode supports up to 9 companies (codes use one leading digit). '
                  'Use “Same code in every company” or reduce the selection.')
            )
        return companies

    def _cpa_company_prefix_digit(self, company, companies):
        return str(list(companies.ids).index(company.id) + 1)

    def _cpa_format_company_prefixed_code(self, company, companies, sequence_num, code_digits):
        prefix = self._cpa_company_prefix_digit(company, companies)
        suffix_width = code_digits - len(prefix)
        if suffix_width < 1:
            raise UserError(_('Code length %s is too short for company prefix mode.') % code_digits)
        max_suffix = (10 ** suffix_width) - 1
        if sequence_num > max_suffix:
            raise UserError(_('No available account code left for company %s.') % company.display_name)
        return '%s%s' % (prefix, str(sequence_num).zfill(suffix_width))

    def _cpa_normalize_coa_name(self, name):
        return re.sub(r'\s+', ' ', (name or '').strip().lower())

    def _cpa_reset_code_group_key(self, account):
        identity_code = (account.identity_code or '').strip() if 'identity_code' in account._fields else ''
        if identity_code and identity_code.lower() != 'new':
            return ('identity', identity_code.lower())
        return (
            'name_type',
            self._cpa_normalize_coa_name(account.name),
            account.user_type_id.id or False,
        )

    def _cpa_reset_base_code(self, accounts, code_digits):
        base_codes = []
        for account in accounts:
            digits = re.sub(r'\D+', '', account.code or '')
            if digits:
                if code_digits == 6 and len(digits) == 4:
                    group_prefix = (
                        account.group_id.code_prefix_start
                        or account.group_id.code_prefix_end
                        or ''
                    ).strip()
                    if len(group_prefix) != 3 or not group_prefix.isdigit():
                        group_prefix = digits[:3]
                    base_codes.append('%s%s' % (group_prefix, digits[-2:].zfill(3)))
                else:
                    base_codes.append(digits[:code_digits].rjust(code_digits, '0'))
        if base_codes:
            return Counter(base_codes).most_common(1)[0][0]
        return str(min(accounts.ids)).zfill(code_digits)[-code_digits:]

    def _cpa_reset_group_label(self, account):
        key = self._cpa_reset_code_group_key(account)
        if key[0] == 'identity':
            return 'Identity: %s' % key[1]
        return '%s / %s' % (account.name or '', account.user_type_id.display_name or '')

    def _cpa_reset_shared_candidate(self, base_code, companies, used_codes_by_company, code_digits):
        candidate_number = int(base_code)
        max_value = self._cpa_code_max_value(code_digits)
        while candidate_number <= max_value:
            candidate = str(candidate_number).zfill(code_digits)
            if all(candidate not in used_codes_by_company[company.id] for company in companies):
                for company in companies:
                    used_codes_by_company[company.id].add(candidate)
                return candidate
            candidate_number += 1
        raise UserError(
            _('No available %(digits)s-digit account code left for the selected companies.')
            % {'digits': code_digits}
        )

    def _cpa_reset_unique_candidate(self, base_code, used_codes, code_digits):
        candidate_number = int(base_code)
        max_value = self._cpa_code_max_value(code_digits)
        while candidate_number <= max_value:
            candidate = str(candidate_number).zfill(code_digits)
            if candidate not in used_codes:
                used_codes.add(candidate)
                return candidate
            candidate_number += 1
        raise UserError(
            _('No available %(digits)s-digit account code left.')
            % {'digits': code_digits}
        )

    def _cpa_reset_company_prefixed_candidate(
        self, company, companies, sequence_num, used_codes_by_company, code_digits,
    ):
        candidate_number = sequence_num
        max_suffix = (10 ** (code_digits - 1)) - 1
        while candidate_number <= max_suffix:
            candidate = self._cpa_format_company_prefixed_code(
                company, companies, candidate_number, code_digits,
            )
            if candidate not in used_codes_by_company[company.id]:
                used_codes_by_company[company.id].add(candidate)
                return candidate
            candidate_number += 1
        raise UserError(
            _('No available %(digits)s-digit account code left for %s.')
            % {'digits': code_digits, 'company': company.display_name}
        )

    def _cpa_reset_duplicate_group_concerns(self, grouped_accounts):
        concerns = []
        for group_accounts in grouped_accounts.values():
            by_company = defaultdict(list)
            for account in group_accounts:
                by_company[account.company_id].append(account)
            for company, company_accounts in by_company.items():
                if len(company_accounts) <= 1:
                    continue
                sample = company_accounts[0]
                concerns.append(
                    '%s: %s / %s (%s)'
                    % (
                        company.display_name,
                        sample.name,
                        sample.user_type_id.display_name,
                        ', '.join(account.code or '-' for account in company_accounts),
                    )
                )
        return concerns

    def _cpa_reset_code_plan(self, accounts, code_digits=None, company_code_mode=None):
        if code_digits is None or company_code_mode is None:
            code_digits, company_code_mode = self._cpa_reset_code_options()

        grouped_accounts = defaultdict(lambda: self.env['account.account'])
        for account in accounts:
            grouped_accounts[self._cpa_reset_code_group_key(account)] |= account

        companies_for_prefix = (
            self._cpa_companies_for_prefix(accounts)
            if company_code_mode == 'company_prefix'
            else accounts.mapped('company_id')
        )

        used_codes_by_company = {}
        for company in accounts.mapped('company_id'):
            company_accounts = accounts.filtered(lambda account: account.company_id == company)
            outside_accounts = self.env['account.account'].search([
                ('company_id', '=', company.id),
                ('id', 'not in', company_accounts.ids),
            ])
            used_codes_by_company[company.id] = set(outside_accounts.mapped('code'))

        final_codes = {}
        issues = {}
        issue_counts = defaultdict(int)
        ordered_groups = sorted(
            grouped_accounts.values(),
            key=lambda group: (
                self._cpa_reset_base_code(group, code_digits),
                group[0].name or '',
                group[0].id,
            ),
        )
        next_company_prefix_sequence = 1

        for group_accounts in ordered_groups:
            by_company = defaultdict(lambda: self.env['account.account'])
            for account in group_accounts:
                by_company[account.company_id] |= account

            has_company_duplicates = any(len(company_accounts) > 1 for company_accounts in by_company.values())
            if not has_company_duplicates:
                if company_code_mode == 'company_prefix':
                    sequence_num = next_company_prefix_sequence
                    next_company_prefix_sequence += 1
                    for account in group_accounts:
                        new_code = self._cpa_reset_company_prefixed_candidate(
                            account.company_id,
                            companies_for_prefix,
                            sequence_num,
                            used_codes_by_company,
                            code_digits,
                        )
                        final_codes[account.id] = new_code
                        issues[account.id] = 'changed' if account.code != new_code else 'ok'
                else:
                    base_code = self._cpa_reset_base_code(group_accounts, code_digits)
                    companies = group_accounts.mapped('company_id')
                    new_code = self._cpa_reset_shared_candidate(
                        base_code, companies, used_codes_by_company, code_digits,
                    )
                    for account in group_accounts:
                        final_codes[account.id] = new_code
                        issues[account.id] = 'changed' if account.code != new_code else 'ok'
                continue

            issue_counts['company_duplicate'] += 1
            ordered_by_company = {}
            for company, company_accounts in by_company.items():
                ordered_by_company[company] = company_accounts.sorted(
                    lambda account: (
                        0 if account.code and re.sub(r'\D+', '', account.code or '') else 1,
                        account.code or '',
                        account.id,
                    )
                )

            max_slot_count = max(len(company_accounts) for company_accounts in ordered_by_company.values())
            for slot_index in range(max_slot_count):
                shared_slot_accounts = self.env['account.account']
                for company, company_accounts in ordered_by_company.items():
                    if len(company_accounts) <= slot_index:
                        continue
                    account = company_accounts[slot_index]
                    if len(company_accounts) > 1:
                        base_code = self._cpa_reset_base_code(company_accounts, code_digits)
                        if company_code_mode == 'company_prefix':
                            sequence_num = next_company_prefix_sequence
                            next_company_prefix_sequence += 1
                            new_code = self._cpa_reset_company_prefixed_candidate(
                                account.company_id,
                                companies_for_prefix,
                                sequence_num,
                                used_codes_by_company,
                                code_digits,
                            )
                        else:
                            new_code = self._cpa_reset_unique_candidate(
                                base_code,
                                used_codes_by_company[company.id],
                                code_digits,
                            )
                        final_codes[account.id] = new_code
                        issues[account.id] = 'company_duplicate'
                    else:
                        shared_slot_accounts |= account

                if not shared_slot_accounts:
                    continue
                if company_code_mode == 'company_prefix':
                    sequence_num = next_company_prefix_sequence
                    next_company_prefix_sequence += 1
                    for account in shared_slot_accounts:
                        new_code = self._cpa_reset_company_prefixed_candidate(
                            account.company_id,
                            companies_for_prefix,
                            sequence_num,
                            used_codes_by_company,
                            code_digits,
                        )
                        final_codes[account.id] = new_code
                        issues[account.id] = 'company_duplicate'
                else:
                    base_code = self._cpa_reset_base_code(shared_slot_accounts, code_digits)
                    companies = shared_slot_accounts.mapped('company_id')
                    new_code = self._cpa_reset_shared_candidate(
                        base_code, companies, used_codes_by_company, code_digits,
                    )
                    for account in shared_slot_accounts:
                        final_codes[account.id] = new_code
                        issues[account.id] = 'company_duplicate'

        return final_codes, issues, issue_counts

    def _cpa_reset_validate_unique_codes(self, accounts, final_codes):
        """Duplicate ledger codes per company are allowed (no hard stop)."""
        return

    def _cpa_sync_groups_for_code_digits(self, accounts, code_digits):
        prefix_width = 2 if code_digits == 4 else 3
        Group = self.env['account.group'].sudo()
        engine = self.env['coa.ifrs.coding']
        group_cache = {}
        updated = 0
        for account in accounts:
            digits = re.sub(r'\D+', '', account.code or '')
            prefix = digits[:prefix_width]
            if len(prefix) != prefix_width:
                continue
            cache_key = (account.company_id.id, prefix)
            target_group = group_cache.get(cache_key)
            if target_group is None:
                target_group = Group.search([
                    ('company_id', '=', account.company_id.id),
                    '|',
                    ('code_prefix_start', '=', prefix),
                    ('code_prefix_end', '=', prefix),
                ], order='id', limit=1)
                if not target_group:
                    continue
                group_cache[cache_key] = target_group
            if account.group_id != target_group:
                account.with_context(cpabooks_skip_ifrs_auto_setup=True).write({
                    'group_id': target_group.id,
                })
                updated += 1
        return updated


    def action_preview_reset_code_digits(self):
        accounts = self.exists()
        if not accounts:
            accounts = self._cpa_coa_menu_accounts()
        accounts = accounts.filtered(lambda account: account.company_id)
        code_digits, company_code_mode = self._cpa_reset_code_options()
        final_codes, issues, issue_counts = self._cpa_reset_code_plan(
            accounts, code_digits, company_code_mode,
        )

        line_commands = []
        for account in accounts.sorted(lambda rec: (rec.company_id.name or '', rec.name or '', rec.code or '', rec.id)):
            issue = issues.get(account.id) or 'ok'
            if issue == 'company_duplicate':
                suggested_fix = _(
                    'Duplicate ledger in this company — a unique code is assigned. '
                    'Consider Merge COA to combine duplicates.'
                )
            elif account.code != final_codes.get(account.id):
                suggested_fix = _('Will reset to digit-only code.')
            else:
                suggested_fix = _('Already aligned.')
            line_commands.append((0, 0, {
                'account_id': account.id,
                'company_id': account.company_id.id,
                'current_code': account.code,
                'suggested_code': final_codes.get(account.id),
                'name': account.name,
                'user_type_id': account.user_type_id.id,
                'group_key': self._cpa_reset_group_label(account),
                'issue': issue,
                'suggested_fix': suggested_fix,
            }))

        duplicate_groups = issue_counts.get('company_duplicate', 0)
        mode_label = dict(self.env['coa.reset.code.options.wizard']._fields['company_code_mode'].selection).get(
            company_code_mode, company_code_mode,
        )
        message = _(
            'Preview: %(digits)s-digit codes, %(mode)s. '
            '%(dup)s duplicate group(s) inside a company need review/merge.'
        ) % {
            'digits': code_digits,
            'mode': mode_label,
            'dup': duplicate_groups,
        }
        wizard = self.env['coa.reset.code.preview.wizard'].create({
            'message': message,
            'line_ids': line_commands,
            'code_digit_length': str(code_digits),
            'company_code_mode': company_code_mode,
        })
        view = self.env.ref('chart_of_accounts_saaskul.view_coa_reset_code_preview_wizard_form')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reset Code Digits Preview'),
            'res_model': 'coa.reset.code.preview.wizard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'res_id': wizard.id,
        }

    def action_open_coa_bulk_actions(self):
        return self.action_open_coa_merge_coa()

    def action_open_coa_merge_coa(self, prefill_sources=True):
        accounts = self.exists()
        view = self.env.ref('chart_of_accounts_saaskul.view_coa_bulk_actions_wizard_form')
        company = self.env.company
        if accounts:
            account_companies = accounts.mapped('company_id')
            if len(account_companies) == 1:
                company = account_companies
            else:
                accounts = accounts.filtered(lambda account: account.company_id == company)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Merge COA'),
            'res_model': 'coa.bulk.actions.wizard',
            'view_mode': 'form',
            'views': [(view.id, 'form')],
            'target': 'new',
            'context': {
                'active_model': 'account.account',
                'active_ids': accounts.ids,
                'default_company_id': company.id,
                'cpabooks_merge_prefill_sources': bool(prefill_sources and accounts),
            },
        }

    def action_reset_code_digits(self):
        accounts = self.exists()
        if not accounts:
            accounts = self.env['account.account'].search([
                ('company_id', 'in', self.env.companies.ids),
            ])
        accounts = accounts.filtered(lambda account: account.company_id)
        if not accounts:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Reset Code Digits'),
                    'message': _('No chart of accounts found to update.'),
                    'type': 'warning',
                    'sticky': False,
                },
            }

        code_digits, company_code_mode = self._cpa_reset_code_options()
        final_codes, issues, issue_counts = self._cpa_reset_code_plan(
            accounts, code_digits, company_code_mode,
        )
        self._cpa_reset_validate_unique_codes(accounts, final_codes)

        accounts = accounts.with_context(cpabooks_skip_ifrs_auto_setup=True)
        original_codes = {account.id: account.code or '' for account in accounts}
        temporary_prefix = '__reset_digits_%s_' % self.env.uid
        for account in accounts:
            account.sudo().write({'code': '%s%s' % (temporary_prefix, account.id)})
        updated = 0
        for account in accounts:
            new_code = final_codes.get(account.id)
            if not new_code:
                continue
            values = {'code': new_code}
            old_code = original_codes.get(account.id) or ''
            if old_code != new_code and 'cpabooks_previous_code' in account._fields:
                values['cpabooks_previous_code'] = old_code
                updated += 1
            account.sudo().write(values)

        group_updates = self._cpa_sync_groups_for_code_digits(accounts, code_digits)
        accounts.mapped('company_id').sudo().write({
            'cpabooks_coa_code_digits': str(code_digits),
        })
        self.env['ir.ui.view'].clear_caches()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reset Code Digits'),
                'message': _(
                    'Updated %s account codes and %s groups (%s digits, %s). '
                    '%s duplicate group(s) need review.'
                ) % (
                    updated,
                    group_updates,
                    code_digits,
                    company_code_mode,
                    issue_counts.get('company_duplicate', 0),
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            },
        }
