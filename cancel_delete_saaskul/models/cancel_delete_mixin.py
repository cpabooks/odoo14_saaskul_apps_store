# -*- coding: utf-8 -*-
import json

from lxml import etree

from odoo import api, models, _

_PAYMENT_CANCELLED = ("canceled", "cancelled", "cancel", "rejected")


CPA_CD_HEADER_NAMES = frozenset({
    "action_cpa_cd_cancel",
    "action_cpa_cd_cancel_lines",
    "action_cpa_cd_cancel_linked",
    "action_cpa_cd_confirm_post",
    "action_cpa_cd_delete",
    "action_cpa_cd_delete_linked",
    "action_cpa_cd_reset_draft",
    "action_cpa_cd_reverse",
    "action_duplicate",
})
CPA_CD_HEADER_STRINGS = frozenset({
    "Cancel",
    "Cancel - Lines",
    "Cancel - Linked Docs",
    "Confirm / Post",
    "Delete",
    "Delete - Linked Docs",
        "Reverse",
        "Duplicate",
        "Create for Multico",
    })


class CpaCancelDeleteMixin(models.AbstractModel):
    _name = "cpa.cancel.delete.mixin"
    _description = "Saaskul global cancel/delete helpers"

    # Standard header buttons replaced by the Actions menu (every occurrence in the form).
    _cpa_cd_hidden_header_buttons = ()

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == "form":
            self._cpa_cd_strip_header_action_buttons(arch)
        return arch, view

    @api.model
    def _cpa_cd_strip_header_action_buttons(self, arch):
        """Keep Cancel/Delete/Clone set in Action menu only — not form header."""
        for header in arch.xpath(".//header"):
            for button in list(header):
                if button.tag != "button":
                    continue
                name = button.get("name") or ""
                string = (button.get("string") or "").strip()
                if (name.startswith("action_cpa_cd_") or name in CPA_CD_HEADER_NAMES
                        or name in self._cpa_cd_hidden_header_buttons):
                    header.remove(button)
                    continue
                if string in CPA_CD_HEADER_STRINGS:
                    header.remove(button)
        return arch

    def _cpa_cd_ctx(self):
        return {
            "force_delete": True,
            "check_move_validity": False,
            "skip_account_move_synchronization": True,
            "disable_cancel_warning": True,
            "force_quotation_delete": True,
        }

    def _cpa_cd_target(self):
        if self.env.context.get("active_model") == self._name:
            ids = list(self.env.context.get("active_ids") or [])
            if not ids and self.env.context.get("active_id"):
                ids = [self.env.context["active_id"]]
            if ids:
                recs = self.browse(ids).exists()
                if recs:
                    return self._cpa_cd_power(recs)
        return self._cpa_cd_power(self.exists())

    def _cpa_cd_power(self, records):
        """Run as superuser with the document company, past record rules."""
        records = records.exists()
        if not records:
            return records
        company_ids = list(self.env.context.get("allowed_company_ids") or [])
        if "company_id" in records._fields:
            company_ids.extend(records.mapped("company_id").ids)
        company_ids = [cid for cid in dict.fromkeys(company_ids) if cid]
        if company_ids:
            records = records.with_context(allowed_company_ids=company_ids)
        return records.sudo()

    def _cpa_cd_chatter(self, body):
        for rec in self:
            if hasattr(rec, "message_post"):
                rec.message_post(body=body)

    def _cpa_cd_payments_from_moves(self, moves):
        Payment = self.env["account.payment"]
        payments = Payment.browse()
        for move in moves.exists():
            if move.name and move.name != "/":
                payments |= Payment.search([("memo", "ilike", move.name)])
            payments |= move.matched_payment_ids
            widget = move.sudo().invoice_payments_widget
            data = {}
            if isinstance(widget, dict):
                data = widget
            elif widget:
                try:
                    data = json.loads(widget) or {}
                except (TypeError, ValueError):
                    data = {}
            for info in data.get("content") or []:
                pid = info.get("account_payment_id")
                if pid:
                    payments |= Payment.browse(pid)
            rec_lines = move.line_ids.filtered(
                lambda line: line.account_id.account_type in ("asset_receivable", "liability_payable")
            )
            # Odoo 19: the journal entry of a payment links back through origin_payment_id.
            payments |= rec_lines.mapped("matched_debit_ids.debit_move_id.move_id.origin_payment_id")
            payments |= rec_lines.mapped("matched_credit_ids.credit_move_id.move_id.origin_payment_id")
        return payments.exists()

    def _cpa_cd_unreconcile_moves(self, moves):
        for move in moves.exists().sudo():
            rec_lines = move.line_ids.filtered(
                lambda line: line.matched_debit_ids or line.matched_credit_ids
            )
            if not rec_lines:
                continue
            try:
                with self.env.cr.savepoint():
                    rec_lines.remove_move_reconcile()
            except Exception:
                partials = rec_lines.mapped("matched_debit_ids") | rec_lines.mapped("matched_credit_ids")
                if partials:
                    partials.sudo().unlink()

    def _cpa_cd_force_button_draft(self, moves):
        ctx = self._cpa_cd_ctx()
        for move in moves.exists().sudo():
            if move.state == "draft":
                continue
            try:
                with self.env.cr.savepoint():
                    move.with_context(**ctx).button_draft()
            except Exception:
                try:
                    with self.env.cr.savepoint():
                        move.with_context(**ctx).write({"name": "/"})
                        move.with_context(**ctx).button_draft()
                except Exception:
                    try:
                        with self.env.cr.savepoint():
                            move.with_context(**ctx).write({
                                "state": "draft",
                                "is_move_sent": False,
                                "posted_before": False,
                            })
                    except Exception:
                        self._cpa_cd_sql_move_state(move, "draft")

    def _cpa_cd_force_button_cancel(self, moves):
        ctx = self._cpa_cd_ctx()
        for move in moves.exists().sudo():
            if move.state == "cancel":
                continue
            try:
                with self.env.cr.savepoint():
                    move.with_context(**ctx).button_cancel()
            except Exception:
                try:
                    with self.env.cr.savepoint():
                        self._cpa_cd_force_button_draft(move)
                        move.with_context(**ctx).button_cancel()
                except Exception:
                    try:
                        with self.env.cr.savepoint():
                            move.with_context(**ctx).write({
                                "auto_post": "no",
                                "state": "cancel",
                            })
                    except Exception:
                        self._cpa_cd_sql_move_state(move, "cancel")

    def _cpa_cd_sql_move_state(self, moves, state):
        """Last resort when button_draft / button_cancel / write are blocked."""
        moves = moves.exists().sudo()
        if not moves or moves._name != "account.move":
            return
        if state == "draft":
            self.env.cr.execute(
                "UPDATE account_move "
                "SET state = %s, posted_before = false, is_move_sent = false "
                "WHERE id IN %s",
                (state, tuple(moves.ids)),
            )
        else:
            self.env.cr.execute(
                "UPDATE account_move SET state = %s, auto_post = 'no' WHERE id IN %s",
                (state, tuple(moves.ids)),
            )
        moves.invalidate_recordset()

    def _cpa_cd_force_cancel_move(self, moves):
        moves = moves.exists().sudo()
        self._cpa_cd_unreconcile_moves(moves)
        posted = moves.filtered(lambda m: m.state == "posted")
        if posted:
            self._cpa_cd_force_button_draft(posted)
        to_cancel = moves.exists().filtered(lambda m: m.state != "cancel")
        if to_cancel:
            self._cpa_cd_force_button_cancel(to_cancel)

    def _cpa_cd_scratch_move_lines(self, move):
        """Keep every line. Zero the money and mark the row scratched."""
        ctx = dict(self._cpa_cd_ctx())
        ctx.pop("skip_account_move_synchronization", None)
        ctx["check_move_validity"] = False
        text_types = ("line_section", "line_subsection", "line_note")
        # Odoo 19 rebuilds tax / payment term lines when a product line changes,
        # so zero the product lines first and only then touch what is left.
        product_lines = move.line_ids.filtered(lambda line: line.display_type == "product")
        if product_lines:
            product_lines.with_context(**ctx).write({"price_unit": 0.0, "cpa_cd_scratched": True})
        for line in move.line_ids.exists():
            if line.display_type in text_types:
                line.with_context(**ctx).write({"cpa_cd_scratched": True})
                continue
            if line.debit or line.credit or line.price_unit or line.amount_currency or not line.cpa_cd_scratched:
                line.with_context(
                    check_move_validity=False,
                    skip_account_move_synchronization=True,
                ).write({
                    "debit": 0.0,
                    "credit": 0.0,
                    "amount_currency": 0.0,
                    "price_unit": 0.0,
                    "cpa_cd_scratched": True,
                })

    def _cpa_cd_unlink_pickings(self, pickings):
        """Delete transfers. Done transfers were returned and cancelled first;
        Odoo never deletes done stock moves, so those stay as cancelled history.
        Returns the transfers that were kept."""
        kept = self.env["stock.picking"]
        for picking in pickings.exists().sudo():
            try:
                with self.env.cr.savepoint():
                    picking.unlink()
            except Exception:
                kept |= picking
                picking.message_post(body=_(
                    "Kept as cancelled: this transfer was done, so it was returned and cancelled. "
                    "Odoo does not allow deleting done stock moves."
                ))
        return kept

    def _cpa_cd_kept_notification(self, kept):
        if not kept:
            return False
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "warning",
                "sticky": False,
                "message": _(
                    "Done transfer(s) %s were returned and cancelled, not deleted "
                    "(Odoo keeps done stock moves)."
                ) % ", ".join(kept.mapped("name")),
                "next": {"type": "ir.actions.client", "tag": "cpa_cd_back"},
            },
        }

    def _cpa_cd_remove_move_lines_and_cancel(self, moves):
        for move in moves.exists().sudo():
            payments = self._cpa_cd_payments_from_moves(move)
            if payments:
                self._cpa_cd_cancel_payment_lines(payments)
            self._cpa_cd_unreconcile_moves(move)
            if move.state != "draft":
                self._cpa_cd_force_button_draft(move)
            self._cpa_cd_scratch_move_lines(move)
            if move.state != "cancel":
                self._cpa_cd_force_button_cancel(move)

    def _cpa_cd_cancel_payment_lines(self, payments):
        ctx = self._cpa_cd_ctx()
        for payment in payments.exists().sudo():
            move = payment.move_id
            rec_lines = move.line_ids.filtered(
                lambda line: line.matched_debit_ids or line.matched_credit_ids
            ) if move else self.env["account.move.line"]
            if rec_lines:
                rec_lines.remove_move_reconcile()
            if payment.state not in ("draft", "canceled", "cancelled", "cancel", "rejected"):
                try:
                    with self.env.cr.savepoint():
                        payment.with_context(**ctx).action_cancel()
                except Exception:
                    payment.write({"state": "canceled"})
            if payment.state in ("canceled", "cancelled", "cancel", "rejected") and hasattr(payment, "action_draft"):
                try:
                    with self.env.cr.savepoint():
                        payment.with_context(**ctx).action_draft()
                except Exception:
                    pass
            if move and move.exists():
                if move.state == "posted":
                    self._cpa_cd_force_button_draft(move)
                elif move.state == "cancel":
                    self._cpa_cd_force_button_draft(move)
                if move.line_ids:
                    move.with_context(**ctx).line_ids.unlink()
                if move.state != "cancel":
                    self._cpa_cd_force_button_cancel(move)
            if payment.state not in ("canceled", "cancelled", "cancel", "rejected"):
                try:
                    with self.env.cr.savepoint():
                        payment.with_context(**ctx).action_cancel()
                except Exception:
                    payment.write({"state": "canceled"})

    def _cpa_cd_force_cancel_payment(self, payments):
        ctx = self._cpa_cd_ctx()
        for pay in payments.exists().sudo():
            move = pay.move_id
            if move:
                self._cpa_cd_force_cancel_move(move)
            if pay.state not in ("canceled", "cancelled", "cancel", "rejected"):
                try:
                    with self.env.cr.savepoint():
                        pay.with_context(**ctx).action_cancel()
                except Exception:
                    pay.write({"state": "canceled"})

    def _cpa_cd_delete_linked_attachments(self, moves):
        attachments = self.env["ir.attachment"]
        message_ids = moves.mapped("message_ids").ids
        if message_ids:
            attachments |= self.env["ir.attachment"].search([
                ("res_model", "=", "mail.message"),
                ("res_id", "in", message_ids),
            ])
        if moves:
            attachments |= self.env["ir.attachment"].search([
                ("res_model", "=", "account.move"),
                ("res_id", "in", moves.ids),
            ])
        if attachments:
            attachments.sudo().unlink()

    def _cpa_cd_delete_moves(self, moves):
        moves = moves.exists().sudo()
        if not moves:
            return
        self._cpa_cd_force_cancel_move(moves)
        ctx = self._cpa_cd_ctx()
        for move in moves.exists():
            try:
                with self.env.cr.savepoint():
                    move.with_context(**ctx).write({
                        "posted_before": False,
                        "message_main_attachment_id": False,
                    })
            except Exception:
                pass
        self._cpa_cd_delete_linked_attachments(moves.exists())
        leftover = moves.exists()
        if leftover:
            try:
                with self.env.cr.savepoint():
                    leftover.with_context(**ctx).unlink()
            except Exception:
                self._cpa_cd_sql_move_state(leftover.exists(), "draft")
                leftover.exists().with_context(**ctx).sudo().unlink()

    def _cpa_cd_leave_action(self):
        """Close the form of a record that was just deleted."""
        return {
            "type": "ir.actions.client",
            "tag": "cpa_cd_back",
        }

    def _cpa_cd_web_action(self, result=None):
        """Do not return act_window (stacks breadcrumbs) or True (closes the window).

        Confirm wizards still pass a dict. Form/list JS reloads the current view.
        """
        if isinstance(result, dict):
            return result
        return False

    def _cpa_cd_open_confirm(self, method_name, title):
        records = self._cpa_cd_target()
        wizard = self.env["cpa.cd.confirm.wizard"].create({
            "res_model": self._name,
            "res_ids": ",".join(str(i) for i in records.ids),
            "method_name": method_name,
            "note": title,
        })
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "cpa.cd.confirm.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }
