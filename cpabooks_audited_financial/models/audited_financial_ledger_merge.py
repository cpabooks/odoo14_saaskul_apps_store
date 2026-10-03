# -*- coding: utf-8 -*-
"""Merge Ledger wizard: load report ledgers, then Modify (rename) or Merge (move AMLs)."""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_AFG_MERGE_REPORT_SECTIONS = [
    ("pl", "Statement of Profit or Loss"),
    ("bs", "Statement of Financial Position"),
    ("equity", "Statement of Changes in Equity"),
    ("tb", "Trial Balance"),
    ("tb_x", "Trial Balance_x"),
    ("cashflow", "Cash Flow Statement"),
    ("fixed_assets", "Fixed Assets Schedule"),
]


class AuditedFinancialLedgerMergeWizard(models.TransientModel):
    _name = "audited.financial.ledger.merge.wizard"
    _description = "AFG Merge Ledger — modify name or merge into one ledger"

    version_id = fields.Many2one("audited.financial.version", required=True, ondelete="cascade")
    report_section = fields.Selection(
        _AFG_MERGE_REPORT_SECTIONS,
        string="Report",
        required=True,
        default="bs",
    )
    company_ids = fields.Many2many(
        "res.company",
        string="Companies",
        help="Add or remove companies, then Load ledgers.",
    )
    focus_company_id = fields.Many2one(
        "res.company",
        string="Work on company",
        help="Recommended. Load / Merge / Modify for one company at a time.",
    )
    filter_mode = fields.Selection(
        [
            ("afg_group", "AFG group"),
            ("account_group", "Account group"),
            ("ledger", "Single ledger(s)"),
        ],
        string="Select by",
        required=True,
        default="afg_group",
    )
    afg_group_ids = fields.Many2many(
        "audited.financial.group",
        "afg_ledger_merge_wiz_afg_group_rel",
        "wizard_id",
        "group_id",
        string="AFG groups",
    )
    account_group_ids = fields.Many2many(
        "account.group",
        "afg_ledger_merge_wiz_acc_group_rel",
        "wizard_id",
        "account_group_id",
        string="Account groups",
    )
    account_ids = fields.Many2many(
        "account.account",
        "afg_ledger_merge_wiz_account_rel",
        "wizard_id",
        "account_id",
        string="Ledgers",
    )
    action_mode = fields.Selection(
        [
            ("modify", "Modify name"),
            ("merge", "Merge into one ledger"),
            ("archive", "Archive ledger(s)"),
            ("delete", "Delete ledger(s)"),
        ],
        string="Action",
        required=True,
        default="modify",
        help="Modify: edit Current name, Save, Confirm. "
             "Merge: Include 2+, pick Merge into, Merge. "
             "Archive: deprecate Include rows. "
             "Delete: remove Include rows (or archive if still linked).",
    )
    merge_into_id = fields.Many2one(
        "account.account",
        string="Merge into",
        help="Empty until you choose. Target ledger that keeps all transactions (same company).",
    )
    line_ids = fields.One2many(
        "audited.financial.ledger.merge.line",
        "wizard_id",
        string="Ledgers",
    )
    info_message = fields.Text(string="Status", readonly=True)
    line_count = fields.Integer(compute="_compute_line_count")

    @api.depends("line_ids")
    def _compute_line_count(self):
        for wiz in self:
            wiz.line_count = len(wiz.line_ids)

    @api.onchange("action_mode")
    def _onchange_action_mode(self):
        if self.action_mode != "merge":
            self.merge_into_id = False

    @api.onchange("focus_company_id", "company_ids")
    def _onchange_company_scope(self):
        if self.merge_into_id and self.focus_company_id:
            if self.merge_into_id.company_id != self.focus_company_id:
                self.merge_into_id = False

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ver = self.env["audited.financial.version"].browse(
            self.env.context.get("default_version_id") or self.env.context.get("active_id")
        )
        if ver and ver.exists():
            res["version_id"] = ver.id
            cids = ver.company_ids.ids or [ver.company_id.id]
            res["company_ids"] = [(6, 0, list(cids))]
            if len(cids) == 1:
                res["focus_company_id"] = cids[0]
        section = self.env.context.get("afg_merge_section") or "bs"
        if section not in dict(_AFG_MERGE_REPORT_SECTIONS):
            section = "bs"
        res["report_section"] = section
        res["info_message"] = _(
            "Load ledgers for this report. "
            "Modify / Merge / Archive / Delete: tick Include, then the matching footer button. "
            "Window stays open until Close."
        )
        return res

    def _reload_action(self):
        self.ensure_one()
        self._purge_stale_lines()
        return {
            "type": "ir.actions.act_window",
            "name": _("Merge Ledger"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
            "context": dict(
                self.env.context,
                default_version_id=self.version_id.id,
                afg_merge_section=self.report_section,
            ),
        }

    def _purge_stale_lines(self):
        """Drop wizard rows / M2M pointing at deleted CoA (transient has no real FK)."""
        self.ensure_one()
        Line = self.env["audited.financial.ledger.merge.line"]
        self.env.cr.execute(
            """
            SELECT l.id
              FROM audited_financial_ledger_merge_line l
         LEFT JOIN account_account a ON a.id = l.account_id
             WHERE l.wizard_id = %s
               AND (l.account_id IS NULL OR a.id IS NULL)
            """,
            [self.id],
        )
        stale_ids = [row[0] for row in self.env.cr.fetchall()]
        if stale_ids:
            Line.browse(stale_ids).unlink()
        if self.merge_into_id and not self.merge_into_id.exists():
            self.merge_into_id = False
        if self.account_ids:
            alive = self.account_ids.exists()
            if alive != self.account_ids:
                self.account_ids = alive
        self.invalidate_cache()

    def _included_lines(self):
        self.ensure_one()
        return self.line_ids.filtered(
            lambda l: l.include and l.account_id and l.account_id.exists()
        )

    def _drop_lines_for_accounts(self, accounts):
        """Unlink wizard lines for accounts by id before/after CoA delete."""
        self.ensure_one()
        aids = set(accounts.ids)
        if not aids:
            return
        drop = self.line_ids.filtered(lambda l: l.account_id.id in aids)
        drop.unlink()
        if self.account_ids:
            self.account_ids = [(3, aid) for aid in aids if aid in self.account_ids.ids]
        if self.merge_into_id and self.merge_into_id.id in aids:
            self.merge_into_id = False

    def _delete_or_archive_accounts(self, accounts):
        """Try unlink; archive (deprecated) when Odoo blocks deletion."""
        accounts = accounts.exists()
        deleted_names = []
        archived_names = []
        failed = []
        for account in accounts:
            name = account.display_name
            try:
                with self.env.cr.savepoint():
                    account.sudo().unlink()
                deleted_names.append(name)
            except Exception:
                try:
                    with self.env.cr.savepoint():
                        account.sudo().write({"deprecated": True})
                    archived_names.append(name)
                except Exception as dep_error:
                    failed.append("%s (%s)" % (name, dep_error))
        return {
            "deleted": deleted_names,
            "archived": archived_names,
            "failed": failed,
        }

    def _report_line_sections(self):
        sec = self.report_section or "bs"
        if sec in ("tb", "tb_x"):
            return ("pl", "bs", "equity")
        if sec == "cashflow":
            return ("pl", "bs")
        if sec == "fixed_assets":
            return ("bs", "fixed_assets")
        if sec in ("pl", "bs", "equity"):
            return (sec,)
        return ("bs",)

    def _accounts_in_report_scope(self, company_ids):
        self.ensure_one()
        ver = self.version_id
        if not ver or not company_ids:
            return self.env["account.account"]
        sections = self._report_line_sections()
        lines = ver.line_ids.filtered(
            lambda l: l.report_section in sections and l.level == 3
        )
        aid_set = set()
        for line in lines:
            for aid in ver._line_leaf_account_ids(line):
                aid_set.add(aid)
        Account = self.env["account.account"].with_context(active_test=False).sudo()
        return Account.browse(list(aid_set)).exists().filtered(
            lambda a: a.company_id.id in company_ids and not a.deprecated
        )

    def _loaded_account_ids(self):
        return self.line_ids.mapped("account_id").ids

    def _ledger_usage_stats(self, account_ids):
        """Posted balance (debit−credit) and distinct JV count per account."""
        if not account_ids:
            return {}
        self.env.cr.execute(
            """
            SELECT aml.account_id,
                   COALESCE(SUM(aml.debit), 0) - COALESCE(SUM(aml.credit), 0),
                   COUNT(DISTINCT aml.move_id)
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
             WHERE aml.account_id = ANY(%s)
               AND am.state = 'posted'
             GROUP BY aml.account_id
            """,
            [list(account_ids)],
        )
        return {
            row[0]: {"balance": float(row[1] or 0.0), "jv_qty": int(row[2] or 0)}
            for row in self.env.cr.fetchall()
        }

    def action_load_ledgers(self):
        self.ensure_one()
        ver = self.version_id
        if not ver:
            raise UserError(_("No AFG version selected."))
        cids = list(self.company_ids.ids or ver.company_ids.ids or [ver.company_id.id])
        if not cids:
            raise UserError(_("Select at least one company."))
        self.company_ids = [(6, 0, cids)]
        if self.focus_company_id and self.focus_company_id.id not in cids:
            raise UserError(_("Work on company must be one of the selected Companies."))
        load_cids = [self.focus_company_id.id] if self.focus_company_id else cids

        scope = self._accounts_in_report_scope(load_cids)
        if not scope:
            self.line_ids = [(5, 0, 0)]
            self.merge_into_id = False
            self.info_message = _(
                "No ledgers on report “%s” for the selected companies. "
                "Load default data on AFG first."
            ) % dict(_AFG_MERGE_REPORT_SECTIONS).get(self.report_section, self.report_section)
            return self._reload_action()

        mode = self.filter_mode
        if mode == "afg_group":
            if not self.afg_group_ids:
                raise UserError(_("Select at least one AFG group, then Load ledgers."))
            group_ids = set(self.afg_group_ids.ids)
            sections = self._report_line_sections()
            lines = ver.line_ids.filtered(
                lambda l: l.report_section in sections
                and l.level == 3
                and l.group_id
                and l.group_id.id in group_ids
            )
            aids = set()
            for line in lines:
                aids.update(ver._line_leaf_account_ids(line))
            accounts = scope.filtered(lambda a: a.id in aids)
        elif mode == "account_group":
            if not self.account_group_ids:
                raise UserError(_("Select at least one Account group, then Load ledgers."))
            ag_ids = set(self.account_group_ids.ids)
            accounts = scope.filtered(lambda a: a.group_id and a.group_id.id in ag_ids)
        else:
            if not self.account_ids:
                raise UserError(_("Select one or more ledgers, then Load ledgers."))
            pick = set(self.account_ids.ids)
            accounts = scope.filtered(lambda a: a.id in pick)
            if not accounts:
                raise UserError(_(
                    "Selected ledgers are not on this report for the chosen companies."
                ))

        accounts = accounts.sorted(
            lambda a: (a.company_id.name or "", a.code or "", a.name or "", a.id)
        )
        stats = self._ledger_usage_stats(accounts.ids)
        line_cmds = [(5, 0, 0)]
        seq = 10
        for acc in accounts:
            name = (acc.name or "").strip()
            usage = stats.get(acc.id) or {}
            line_cmds.append((0, 0, {
                "sequence": seq,
                "include": False,
                "account_id": acc.id,
                "company_id": acc.company_id.id,
                "current_name": name,
                "balance": usage.get("balance", 0.0),
                "jv_qty": usage.get("jv_qty", 0),
                "line_state": "pending",
            }))
            seq += 10
        self.line_ids = line_cmds
        self.merge_into_id = False
        self.info_message = _(
            "Loaded %(n)s ledger(s) — report “%(r)s”. "
            "Balance / JV Qty = posted. "
            "Modify: edit Current name → Save → Confirm. "
            "Merge: Include 2+ → set Merge into → Merge."
        ) % {
            "n": len(accounts),
            "r": dict(_AFG_MERGE_REPORT_SECTIONS).get(self.report_section, self.report_section),
        }
        return self._reload_action()

    def action_save(self):
        """Modify mode: remember edited Current name values — keep popup open."""
        self.ensure_one()
        if self.action_mode != "modify":
            raise UserError(_("Switch Action to “Modify name” to Save name edits."))
        saved = 0
        for line in self.line_ids.filtered("include"):
            name = (line.current_name or "").strip()
            if not name:
                continue
            line.write({"current_name": name, "line_state": "saved"})
            saved += 1
        if not saved:
            raise UserError(_("Tick Include and edit Current name on at least one row, then Save."))
        self.info_message = _(
            "Saved %(n)s name edit(s). Click Confirm to apply on CoA. Window stays open."
        ) % {"n": saved}
        return self._reload_action()

    def action_confirm(self):
        """Modify mode: apply Current name to account.account — keep popup open."""
        self.ensure_one()
        if self.action_mode != "modify":
            raise UserError(_("Switch Action to “Modify name” to Confirm renames."))
        lines = self.line_ids.filtered(lambda l: l.include and (l.current_name or "").strip())
        if not lines:
            raise UserError(_("Tick Include on rows to rename, then Confirm."))
        companies = lines.mapped("company_id")
        if len(companies) > 1:
            raise UserError(_(
                "Modify one company at a time. Untick other companies or set Work on company."
            ))
        renamed = 0
        for line in lines:
            target = (line.current_name or "").strip()
            acc = line.account_id
            if not acc or not acc.exists():
                continue
            if (acc.name or "").strip() != target:
                acc.sudo().write({"name": target})
                renamed += 1
            line.write({"line_state": "confirmed"})
        self.info_message = _(
            "Confirmed on %(co)s: %(n)s ledger name(s) updated. "
            "Load default data on AFG to refresh. Use Close when done."
        ) % {"co": companies[:1].display_name, "n": renamed}
        return self._reload_action()

    def action_merge(self):
        """Merge included ledgers into Merge into — move all journal items; keep popup open."""
        self.ensure_one()
        if self.action_mode != "merge":
            raise UserError(_("Switch Action to “Merge into one ledger”, then Merge."))
        target = self.merge_into_id.exists()
        if not target:
            raise UserError(_("Select Merge into (empty until you pick the ledger that remains)."))
        included = self._included_lines()
        if not included:
            raise UserError(_("Tick Include on the ledgers to merge from (and optionally the target)."))
        sources = included.mapped("account_id").exists() - target
        if not sources:
            raise UserError(_(
                "Include at least one other ledger besides Merge into. "
                "All of their transactions will move to %s."
            ) % target.display_name)
        companies = (sources | target).mapped("company_id")
        if len(companies) > 1:
            raise UserError(_("Merge only within the same company."))
        if self.focus_company_id and target.company_id != self.focus_company_id:
            raise UserError(_("Merge into must belong to Work on company."))

        # Unlink wizard rows for sources BEFORE CoA delete (no FK on transient).
        target_name = target.display_name
        self._drop_lines_for_accounts(sources)
        result = self._do_merge_accounts(target, sources)
        self.env.invalidate_cache()
        keep = self.line_ids.filtered(lambda l: l.account_id.id == target.id)
        usage = (self._ledger_usage_stats(target.ids) or {}).get(target.id) or {}
        for line in keep:
            line.write({
                "current_name": (target.name or "").strip(),
                "include": False,
                "balance": usage.get("balance", 0.0),
                "jv_qty": usage.get("jv_qty", 0),
                "line_state": "confirmed",
            })
        parts = [
            _("Merged into %s. %s journal item(s) moved.")
            % (target_name, result.get("lines_moved", 0)),
        ]
        if result.get("deleted"):
            parts.append(_("Deleted source COA: %s") % ", ".join(result["deleted"]))
        if result.get("deprecated"):
            parts.append(
                _("Deprecated source COA: %s") % ", ".join(result["deprecated"])
            )
        parts.append(_("Window stays open — Load again or Close."))
        self.info_message = "\n".join(parts)
        return self._reload_action()

    def action_archive(self):
        """Archive (deprecate) included ledgers — keep popup open."""
        self.ensure_one()
        if self.action_mode != "archive":
            raise UserError(_("Switch Action to “Archive ledger(s)”, then Archive."))
        included = self._included_lines()
        if not included:
            raise UserError(_("Tick Include on ledger(s) to archive."))
        companies = included.mapped("company_id")
        if len(companies) > 1:
            raise UserError(_("Archive one company at a time."))
        accounts = included.mapped("account_id").exists()
        names = accounts.mapped("display_name")
        accounts.sudo().write({"deprecated": True})
        self._drop_lines_for_accounts(accounts)
        self.info_message = _(
            "Archived (deprecated) %(n)s ledger(s) on %(co)s: %(names)s. "
            "Window stays open — Load again or Close."
        ) % {
            "n": len(names),
            "co": companies[:1].display_name,
            "names": ", ".join(names),
        }
        return self._reload_action()

    def action_delete(self):
        """Delete included ledgers; archive if still linked. Block if posted JV/balance."""
        self.ensure_one()
        if self.action_mode != "delete":
            raise UserError(_("Switch Action to “Delete ledger(s)”, then Delete."))
        included = self._included_lines()
        if not included:
            raise UserError(_("Tick Include on ledger(s) to delete."))
        companies = included.mapped("company_id")
        if len(companies) > 1:
            raise UserError(_("Delete one company at a time."))
        busy = included.filtered(lambda l: l.jv_qty or abs(l.balance or 0.0) > 0.00001)
        if busy:
            raise UserError(_(
                "Cannot delete ledger(s) that still have posted Balance or JV Qty: %s. "
                "Merge them into another ledger first, or use Action → Archive."
            ) % ", ".join(busy.mapped(lambda l: l.current_name or l.account_id.display_name)))
        accounts = included.mapped("account_id").exists()
        # Drop wizard lines first so MissingError cannot hit after unlink.
        self._drop_lines_for_accounts(accounts)
        result = self._delete_or_archive_accounts(accounts)
        parts = []
        if result["deleted"]:
            parts.append(_("Deleted: %s") % ", ".join(result["deleted"]))
        if result["archived"]:
            parts.append(
                _("Could not delete (still linked) — archived instead: %s")
                % ", ".join(result["archived"])
            )
        if result["failed"]:
            parts.append(_("Failed: %s") % "; ".join(result["failed"]))
        if not parts:
            parts.append(_("No ledgers removed."))
        parts.append(_("Window stays open — Load again or Close."))
        self.info_message = "\n".join(parts)
        return self._reload_action()

    def _do_merge_accounts(self, target, sources):
        """Prefer CPABooks CoA merge helper; fallback to AML reassignment."""
        if "coa.bulk.actions.wizard" in self.env:
            Bulk = self.env["coa.bulk.actions.wizard"]
            if hasattr(Bulk, "_cpabooks_merge_accounts_into"):
                try:
                    with self.env.cr.savepoint():
                        return Bulk._cpabooks_merge_accounts_into(target, sources)
                except UserError:
                    raise
                except Exception as error:
                    _logger.exception("AFG merge ledger failed via COA helper")
                    detail = error.args[0] if getattr(error, "args", None) else str(error)
                    raise UserError(_("Could not merge ledgers: %s") % detail) from error

        # Fallback: move posted/draft journal items, then deprecate sources
        MoveLine = self.env["account.move.line"].sudo()
        lines = MoveLine.search([("account_id", "in", sources.ids)])
        lines_moved = len(lines)
        if lines:
            self.env.cr.execute(
                "UPDATE account_move_line SET account_id = %s WHERE account_id IN %s",
                (target.id, tuple(sources.ids)),
            )
        deprecated = []
        for source in sources:
            try:
                with self.env.cr.savepoint():
                    source.unlink()
            except Exception:
                try:
                    source.write({"deprecated": True})
                    deprecated.append(source.display_name)
                except Exception as dep_err:
                    deprecated.append("%s (%s)" % (source.display_name, dep_err))
        self.env.invalidate_cache()
        return {"lines_moved": lines_moved, "deleted": [], "deprecated": deprecated}

    def action_close(self):
        return {"type": "ir.actions.act_window_close"}


class AuditedFinancialLedgerMergeLine(models.TransientModel):
    _name = "audited.financial.ledger.merge.line"
    _description = "AFG Merge Ledger line"
    _order = "company_id, sequence, id"

    wizard_id = fields.Many2one(
        "audited.financial.ledger.merge.wizard",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    include = fields.Boolean(string="Include", default=False)
    account_id = fields.Many2one("account.account", required=True, ondelete="cascade")
    company_id = fields.Many2one("res.company", string="Company", required=True)
    current_name = fields.Char(
        string="Current name",
        help="Editable in Modify mode. Save then Confirm to rename this ledger.",
    )
    balance = fields.Float(
        string="Balance",
        digits=(16, 2),
        readonly=True,
        help="Posted debit − credit for this ledger (company currency).",
    )
    jv_qty = fields.Integer(
        string="JV Qty",
        readonly=True,
        help="Count of posted journal entries (JV) that touch this ledger.",
    )
    line_state = fields.Selection(
        [
            ("pending", "Pending"),
            ("saved", "Saved"),
            ("confirmed", "Confirmed"),
        ],
        default="pending",
        string="Status",
    )
