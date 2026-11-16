# -*- coding: utf-8 -*-
"""Force AFG PDF to use dedicated paperformat + tight top margin (not company A4 40mm)."""
import logging

from odoo import models

_logger = logging.getLogger(__name__)

_AFG_REPORT_FRAGMENTS = (
    "afg_audit_report_pdf",
    "audited_financials_saaskul.afg_audit",
)


class IrActionsReportAfg(models.Model):
    _inherit = "ir.actions.report"

    def _afg_is_audit_pdf_report(self):
        self.ensure_one()
        name = (self.report_name or self.report_file or "") or ""
        return any(frag in name for frag in _AFG_REPORT_FRAGMENTS)

    def _afg_applies(self):
        if self.env.context.get("afg_audit_pdf"):
            return True
        return len(self) == 1 and self._afg_is_audit_pdf_report()

    def _afg_paperformat(self):
        return self.env.ref(
            "audited_financials_saaskul.paperformat_afg_audit",
            raise_if_not_found=False,
        )

    def get_paperformat(self):
        """Never fall back to company A4 (40mm + header_spacing 35) for AFG."""
        if len(self) == 1 and self._afg_is_audit_pdf_report():
            pf = self._afg_paperformat()
            if pf:
                # Keep action linked so UI / future prints stay consistent
                if self.paperformat_id.id != pf.id:
                    try:
                        self.sudo().write({"paperformat_id": pf.id})
                    except Exception:  # noqa: BLE001
                        _logger.debug("AFG: could not link paperformat on report action", exc_info=True)
                return pf
        return super().get_paperformat()

    def _build_wkhtmltopdf_args(
            self,
            paperformat_id,
            landscape,
            specific_paperformat_args=None,
            set_viewport_size=False):
        command_args = super()._build_wkhtmltopdf_args(
            paperformat_id,
            landscape,
            specific_paperformat_args=specific_paperformat_args,
            set_viewport_size=set_viewport_size,
        )
        if not self._afg_applies():
            return command_args

        # Resolve intended mm from ICP / paperformat (default tight 5mm top)
        top_mm = 5
        bottom_mm = 8
        flags = {}
        try:
            Version = self.env["audited.financial.version"]
            if hasattr(Version, "_afg_print_page_setup_flags"):
                flags = Version._afg_print_page_setup_flags()
                top_mm = int(flags.get("margin_header") or 5)
                bottom_mm = int(flags.get("margin_footer") or 8)
            elif paperformat_id:
                top_mm = int(paperformat_id.margin_top or 5)
                bottom_mm = int(paperformat_id.margin_bottom or 8)
        except Exception:  # noqa: BLE001
            _logger.debug("AFG: margin flags unavailable; using 5/8mm", exc_info=True)

        top_mm = max(3, min(40, top_mm))
        bottom_mm = max(3, min(40, bottom_mm))

        # HTML data-report-margin-top wins in core — override both to the same tight value
        if specific_paperformat_args is not None:
            specific_paperformat_args["data-report-margin-top"] = str(top_mm)
            specific_paperformat_args["data-report-header-spacing"] = "0"

        def _replace_arg(args, flag, value):
            out = []
            skip = False
            for i, a in enumerate(args):
                if skip:
                    skip = False
                    continue
                if a == flag and i + 1 < len(args):
                    out.extend([flag, str(value)])
                    skip = True
                    continue
                out.append(a)
            if flag not in out:
                out.extend([flag, str(value)])
            return out

        command_args = _replace_arg(command_args, "--margin-top", top_mm)
        command_args = _replace_arg(command_args, "--margin-bottom", bottom_mm)
        command_args = _replace_arg(command_args, "--header-spacing", 0)
        want_pages = bool(flags.get("show_page_numbers"))
        # Strip leftover footer page tokens, then add only when Print Setup enables numbers.
        stripped = []
        skip = False
        for i, a in enumerate(command_args):
            if skip:
                skip = False
                continue
            if a in ("--footer-center", "--footer-right", "--footer-left", "--footer-font-size"):
                skip = True
                continue
            stripped.append(a)
        command_args = stripped
        if want_pages:
            command_args.extend(["--footer-center", "[page]", "--footer-font-size", "8"])
        # Keep 10pt text (no wkhtmltopdf shrink-to-fit); tables already width:100%.
        command_args = [a for a in command_args if a != "--enable-smart-shrinking"]
        if "--disable-smart-shrinking" not in command_args:
            command_args.extend(["--disable-smart-shrinking"])
        # Drop --header-line if present (reserves visual chrome)
        cleaned = []
        for a in command_args:
            if a == "--header-line":
                continue
            cleaned.append(a)
        return cleaned

    def _run_wkhtmltopdf(
            self,
            bodies,
            report_ref=False,
            header=None,
            footer=None,
            landscape=False,
            specific_paperformat_args=None,
            set_viewport_size=False):
        report = self._get_report(report_ref) if report_ref else self
        if len(report) == 1 and report._afg_is_audit_pdf_report():
            # AFG paints its own in-body header — empty wkhtmltopdf header + company
            # header_spacing was leaving a huge blank band at the top of page 1.
            header = None
            footer = None
            if specific_paperformat_args is None:
                specific_paperformat_args = {}
            specific_paperformat_args.setdefault("data-report-header-spacing", "0")
            self = self.with_context(afg_audit_pdf=True)
        return super(IrActionsReportAfg, self)._run_wkhtmltopdf(
            bodies,
            report_ref=report_ref,
            header=header,
            footer=footer,
            landscape=landscape,
            specific_paperformat_args=specific_paperformat_args,
            set_viewport_size=set_viewport_size,
        )
