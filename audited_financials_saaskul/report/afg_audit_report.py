# -*- coding: utf-8 -*-

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AfgAuditPdfReport(models.AbstractModel):
    """Canonical AFG PDF report (v105+). Legacy xmlid redirects here."""

    _name = "report.audited_financials_saaskul.afg_audit_report_pdf_v105"
    _description = "Financial Statements (AFG) PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["audited.financial.version"].browse(docids).exists()
        # Always rebuild from the version — report_action / wkhtmltopdf often drops
        # or nulls custom data keys (cover/chapters), which then crash QWeb .get().
        document = {
            "cover": {},
            "chapters": [],
            "year_prior": "",
            "year_current": "",
            "currency": "AED",
            "alerts": [],
            "signatory": {},
            "signatory_label": "Authorized Signatory",
        }
        if docs:
            try:
                docs[0]._afg_sync_paperformat_margins()
            except Exception:
                pass
            try:
                ver = docs[0]
                pack = ver._afg_coerce_to_report_pack(
                    ver.print_max_level or ver._afg_export_report_pack()
                )
                built = ver.with_context(
                    afg_statutory_pdf=True,
                    afg_export_max_level=pack,
                    afg_years_descending=ver._afg_years_descending(),
                    allowed_company_ids=(
                        list(ver.report_column_company_ids.ids)
                        or list(ver.company_ids.ids)
                        or [ver.company_id.id]
                    ),
                )._afg_build_print_chapters() or {}
            except Exception:
                _logger.exception(
                    "AFG PDF: chapter build failed for version %s",
                    docs[0].id if docs else None,
                )
                built = {}
            if isinstance(built, dict):
                cover = built.get("cover") if isinstance(built.get("cover"), dict) else {}
                chapters = built.get("chapters") if isinstance(built.get("chapters"), list) else []
                clean_chapters = []
                for ch in chapters:
                    if not isinstance(ch, dict):
                        continue
                    kind = ch.get("kind") or "statement"
                    header = ch.get("header") if isinstance(ch.get("header"), dict) else {}
                    if kind == "cover" or (ch.get("key") or "") == "cover":
                        cov = ch.get("cover") if isinstance(ch.get("cover"), dict) else {}
                        titles = [t for t in (ch.get("contents_titles") or []) if t]
                        ch = dict(ch, kind="cover", cover=cov, contents_titles=titles, header=header)
                    elif kind == "notes":
                        notes = [n for n in (ch.get("notes") or []) if isinstance(n, dict)]
                        ch = dict(ch, notes=notes, header=header)
                    elif kind == "ppe_matrix":
                        ppe = ch.get("ppe") if isinstance(ch.get("ppe"), dict) else {}
                        cats = [c for c in (ppe.get("categories") or []) if c is not None]
                        blocks = []
                        for block in ppe.get("blocks") or []:
                            if not isinstance(block, dict):
                                continue
                            brows = [r for r in (block.get("rows") or []) if isinstance(r, dict)]
                            blocks.append(dict(block, rows=brows))
                        ppe = dict(ppe, categories=cats, blocks=blocks)
                        ch = dict(ch, ppe=ppe, header=header)
                    elif kind == "tb_face":
                        rows = [r for r in (ch.get("rows") or []) if isinstance(r, dict)]
                        tb_cols = [c for c in (ch.get("tb_columns") or []) if c is not None]
                        ch = dict(ch, rows=rows, tb_columns=tb_cols, header=header)
                    elif kind == "equity_soce":
                        soce = ch.get("soce") if isinstance(ch.get("soce"), dict) else {}
                        ch = dict(ch, soce=soce, header=header)
                    elif kind == "validation":
                        vals = [v for v in (ch.get("validations") or []) if isinstance(v, dict)]
                        ch = dict(ch, validations=vals, header=header)
                    else:
                        rows = [r for r in (ch.get("rows") or []) if isinstance(r, dict)]
                        ch = dict(ch, rows=rows, header=header)
                    clean_chapters.append(ch)
                try:
                    clean_chapters = docs[0]._afg_filter_empty_print_chapters(clean_chapters)
                except Exception:
                    pass
                signatory = built.get("signatory") if isinstance(built.get("signatory"), dict) else {}
                if not signatory:
                    try:
                        signatory = docs[0]._afg_signatory_block() or {}
                    except Exception:
                        signatory = {}
                excl = set()
                try:
                    excl = docs[0]._afg_print_exclude_key_set() or set()
                except Exception:
                    excl = set()
                print_cover = not any((c.get("kind") or "") == "statutory_page" for c in clean_chapters)
                stmt_chapters = [
                    c for c in clean_chapters
                    if (c.get("kind") or "") != "cover" and (c.get("key") or "") != "cover"
                ]
                contents_titles = [
                    c.get("title") or ""
                    for c in stmt_chapters
                    if c.get("title")
                ]
                cover_ch = next(
                    (
                        c for c in clean_chapters
                        if (c.get("kind") or "") == "cover" or (c.get("key") or "") == "cover"
                    ),
                    {},
                )
                if isinstance(cover_ch, dict) and cover_ch.get("cover"):
                    cover = dict(cover or {}, **{
                        k: v for k, v in (cover_ch.get("cover") or {}).items() if v
                    })
                document = {
                    "cover": cover,
                    "chapters": stmt_chapters,
                    "print_cover": print_cover,
                    "contents_titles": contents_titles,
                    "year_prior": built.get("year_prior") or docs[0].year_prior or "",
                    "year_current": built.get("year_current") or docs[0].year_current or "",
                    "currency": built.get("currency") or (docs[0].currency_id.name or "AED"),
                    "alerts": built.get("alerts") if isinstance(built.get("alerts"), list) else [],
                    "signatory": signatory,
                    "signatory_label": (
                        built.get("signatory_label")
                        or signatory.get("signatory_label")
                        or "Authorized Signatory"
                    ),
                    "arabic": bool(built.get("arabic")),
                    "rtl": bool(built.get("rtl")),
                    "report_pack": built.get("report_pack") if isinstance(built.get("report_pack"), dict) else {},
                    "compact_hf": bool(built.get("compact_hf")),
                    "print_page_setup": built.get("print_page_setup") or "default",
                    "skip_empty_pages": bool(built.get("skip_empty_pages")),
                    "sign_last_only": bool(built.get("sign_last_only")),
                    "margin_header": int(built.get("margin_header") or 10),
                    "margin_footer": int(built.get("margin_footer") or 10),
                    "sign_gap_pt": int(built.get("sign_gap_pt") or 28),
                }

        from markupsafe import Markup

        cover = document.get("cover") if isinstance(document.get("cover"), dict) else {}
        chapters = document.get("chapters") if isinstance(document.get("chapters"), list) else []
        safe_chapters = []
        for chapter in chapters:
            if isinstance(chapter, dict) and chapter.get("notes"):
                chapter = dict(chapter)
                chapter["notes"] = [
                    dict(note, body=Markup(note.get("body") or "")) if isinstance(note, dict) else note
                    for note in chapter.get("notes") or []
                ]
            safe_chapters.append(chapter)
        chapters = safe_chapters
        signatory = document.get("signatory") if isinstance(document.get("signatory"), dict) else {}
        # Top-level keys must never be None — stale DB QWeb (Studio / old arch) may still
        # call schedules.get / cover.get / notes.get directly.
        return {
            "doc_ids": docs.ids,
            "doc_model": "audited.financial.version",
            "docs": docs,
            "document": document,
            "cover": cover,
            "chapters": chapters,
            "signatory": signatory,
            "year_prior": document.get("year_prior") or "",
            "year_current": document.get("year_current") or "",
            "currency": document.get("currency") or "AED",
            "signatory_label": document.get("signatory_label") or "Authorized Signatory",
            "alerts": document.get("alerts") if isinstance(document.get("alerts"), list) else [],
            "rtl": bool(document.get("rtl")),
            "arabic": bool(document.get("arabic")),
            "schedules": {},
            "notes": [],
            "sections": [],
            "version": {},
            "tree_by_section": {},
        }


class AfgAuditPdfReportLegacy(models.AbstractModel):
    """Keep old report.* model so leftover report_name still resolves values safely."""

    _name = "report.audited_financials_saaskul.afg_audit_report_pdf"
    _inherit = "report.audited_financials_saaskul.afg_audit_report_pdf_v105"
    _description = "Audited Financial Statements (AFG) PDF (legacy xmlid)"
