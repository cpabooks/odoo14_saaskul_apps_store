# -*- coding: utf-8 -*-

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class AfgSimpleFsPdfReport(models.AbstractModel):
    _name = "report.audited_financials_saaskul.afg_simple_fs_pdf"
    _description = "Financial Statements (quick print) PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["audited.financial.version"].browse(docids).exists()
        document = {
            "cover": {},
            "chapters": [],
            "year_prior": "",
            "year_current": "",
            "currency": "AED",
            "alerts": [],
            "signatory": {},
            "signatory_label": "Authorized Signatory",
            "print_cover": True,
            "contents_titles": [],
            "compact_hf": True,
            "sign_last_only": True,
            "margin_header": 8,
            "margin_footer": 8,
            "sign_gap_pt": 20,
        }
        if docs:
            try:
                ver = docs[0]
                cids = (
                    list(ver.report_column_company_ids.ids)
                    or list(ver.company_ids.ids)
                    or [ver.company_id.id]
                )
                built = ver.with_context(
                    afg_statutory_pdf=True,
                    afg_export_max_level=1,
                    afg_simple_print=True,
                    afg_skip_hierarchy_rebuild=bool(ver.line_ids),
                    allowed_company_ids=cids,
                )._afg_build_simple_print_chapters() or {}
            except Exception:
                _logger.exception(
                    "AFG simple PDF: chapter build failed for version %s",
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
                    elif kind == "equity_soce":
                        soce = ch.get("soce") if isinstance(ch.get("soce"), dict) else {}
                        ch = dict(ch, soce=soce, header=header)
                    else:
                        rows = [r for r in (ch.get("rows") or []) if isinstance(r, dict)]
                        ch = dict(ch, rows=rows, header=header)
                    clean_chapters.append(ch)
                signatory = built.get("signatory") if isinstance(built.get("signatory"), dict) else {}
                if not signatory:
                    try:
                        signatory = docs[0]._afg_signatory_block() or {}
                    except Exception:
                        signatory = {}
                stmt_chapters = [
                    c for c in clean_chapters
                    if (c.get("kind") or "") != "cover" and (c.get("key") or "") != "cover"
                ]
                contents_titles = [c.get("title") or "" for c in stmt_chapters if c.get("title")]
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
                    "print_cover": not any((c.get("kind") or "") == "statutory_page" for c in stmt_chapters),
                    "contents_titles": contents_titles,
                    "year_prior": built.get("year_prior") or docs[0].year_prior or "",
                    "year_current": built.get("year_current") or docs[0].year_current or "",
                    "currency": built.get("currency") or (docs[0].currency_id.name or "AED"),
                    "alerts": [],
                    "signatory": signatory,
                    "signatory_label": (
                        built.get("signatory_label")
                        or signatory.get("signatory_label")
                        or "Authorized Signatory"
                    ),
                    "compact_hf": True,
                    "sign_last_only": True,
                    "margin_header": int(built.get("margin_header") or 8),
                    "margin_footer": int(built.get("margin_footer") or 8),
                    "sign_gap_pt": int(built.get("sign_gap_pt") or 20),
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
            "alerts": [],
            "rtl": False,
            "arabic": False,
            "schedules": {},
            "notes": [],
            "sections": [],
            "version": {},
            "tree_by_section": {},
        }
