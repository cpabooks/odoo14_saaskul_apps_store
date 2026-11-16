# -*- coding: utf-8 -*-
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

ISO_COA_FILE = "audited_financials_saaskul/data/iso_coa/iso_chart_of_accounts.json"


class AuditedFinancialIsoCoaWizard(models.TransientModel):
    _name = "audited.financial.iso.coa.wizard"
    _description = "Load ISO (Nigeria) Chart of Accounts"

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company,
    )
    load_groups = fields.Boolean(string="Account groups", default=True)
    load_accounts = fields.Boolean(string="Ledgers", default=True)
    apply_afg_mapping = fields.Boolean(string="AFG mapping", default=True)
    update_names = fields.Boolean(
        string="Rename existing ledgers",
        help="Ledgers that already exist with the same code get the ISO name.",
    )
    summary = fields.Text(readonly=True)

    @api.model
    def _iso_coa_data(self):
        with file_open(ISO_COA_FILE, "r") as handle:
            return json.load(handle)

    def _iso_load_groups(self, data, company, stats):
        Group = self.env["account.group"].sudo().with_company(company)
        root = company.root_id
        existing = {
            (g.code_prefix_start, g.code_prefix_end)
            for g in Group.search([("company_id", "=", root.id)])
        }
        for row in data.get("groups") or []:
            key = (row["start"], row["end"])
            if key in existing:
                continue
            Group.create({
                "name": row["name"],
                "code_prefix_start": row["start"],
                "code_prefix_end": row["end"],
                "company_id": root.id,
            })
            existing.add(key)
            stats["groups"] += 1

    def _iso_find_account(self, company, code):
        return self.env["account.account"].sudo().with_company(company).with_context(
            active_test=False, afg_skip_collapse=True
        ).search([("code", "=", code), ("company_ids", "in", company.id)], limit=1)

    def _iso_load_accounts(self, data, company, stats):
        Account = self.env["account.account"].sudo().with_company(company).with_context(
            afg_skip_same_name_sync=True
        )
        has_unaffected = bool(Account.search([
            ("account_type", "=", "equity_unaffected"),
            ("company_ids", "in", company.id),
        ], limit=1))
        accounts = {}
        for row in data.get("accounts") or []:
            account = self._iso_find_account(company, row["code"])
            if account:
                if self.update_names and account.name != row["name"]:
                    account.name = row["name"]
                    stats["renamed"] += 1
                accounts[row["code"]] = account
                continue
            if not self.load_accounts:
                continue
            if row["account_type"] == "equity_unaffected" and has_unaffected:
                stats["skipped"] += 1
                continue
            vals = {
                "code": row["code"],
                "name": row["name"],
                "account_type": row["account_type"],
                "reconcile": row["reconcile"],
                "company_ids": [(6, 0, [company.id])],
            }
            if row.get("ctf_category"):
                vals["ctf_category"] = row["ctf_category"]
            account = Account.create(vals)
            if row["account_type"] == "equity_unaffected":
                has_unaffected = True
            accounts[row["code"]] = account
            stats["accounts"] += 1
        return accounts

    def _iso_apply_mapping(self, data, accounts, stats):
        Group = self.env["audited.financial.group"].sudo()
        Line = self.env["audited.financial.group.line"].sudo().with_context(afg_skip_collapse=True)
        self.env["audited.financial.version"].sudo()._ensure_afg_presets()
        by_code = {g.code: g for g in Group.search([("company_id", "=", False)])}
        touched = self.env["account.account"]
        primary = {}
        for row in data.get("accounts") or []:
            account = accounts.get(row["code"])
            codes = [c for c in row.get("afg_groups") or [] if c in by_code]
            if not account or not codes:
                continue
            Line.search([("account_id", "=", account.id)]).unlink()
            for code in codes:
                Line.create({"group_id": by_code[code].id, "account_id": account.id})
            statement = [c for c in codes if by_code[c].report_section in ("pl", "bs")]
            primary[account.id] = by_code[(statement or codes)[0]].id
            touched |= account
            stats["mapped"] += 1
        if touched:
            # Plain SQL: the field inverse would replace the extra cash-flow / equity mappings.
            for account_id, group_id in primary.items():
                self.env.cr.execute(
                    "UPDATE account_account SET afg_group_id = %s WHERE id = %s",
                    (group_id, account_id),
                )
            touched.invalidate_recordset(["afg_group_id"])
            self.env["audited.financial.version"].sudo()._afg_rebuild_after_coa_map(touched)

    def action_load(self):
        self.ensure_one()
        if not self.env.user.has_group("account.group_account_manager"):
            raise UserError(_("Only accounting administrators can load the ISO chart of accounts."))
        data = self._iso_coa_data()
        company = self.company_id
        stats = dict(groups=0, accounts=0, renamed=0, skipped=0, mapped=0)
        if self.load_groups:
            self._iso_load_groups(data, company, stats)
        accounts = self._iso_load_accounts(data, company, stats)
        if self.apply_afg_mapping:
            self._iso_apply_mapping(data, accounts, stats)
        self.summary = _(
            "%(groups)s account groups and %(accounts)s ledgers created, %(renamed)s renamed, "
            "%(mapped)s ledgers mapped to AFG groups, %(skipped)s skipped "
            "(company already has a Current Year Earnings ledger)."
        ) % stats
        _logger.info("ISO COA loaded on %s: %s", company.display_name, stats)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
