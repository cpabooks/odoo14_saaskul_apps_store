# -*- coding: utf-8 -*-
"""Shared helpers for CPABooks document sequence prefix and preview formatting."""
from datetime import date

from odoo import _


def format_year(year, year_digits="4"):
    year = int(year)
    if year_digits == "2":
        return str(year % 100).zfill(2)
    return str(year)


def build_sequence_number(
    document_code,
    company_prefix,
    granularity="yearly",
    year_digits="4",
    padding=5,
    next_number=1,
    ref_date=None,
):
    """Build a human-readable example like INV/KCS/2026/05/00001."""
    ref_date = ref_date or date.today()
    company_prefix = (company_prefix or "").strip() or "PREFIX"
    document_code = document_code or "DOC"
    year_str = format_year(ref_date.year, year_digits)
    month_str = "%02d" % ref_date.month
    pad = int(padding or 0)
    number_str = str(int(next_number or 1)).zfill(pad) if pad else str(int(next_number or 1))

    if granularity == "monthly":
        return "%s/%s/%s/%s/%s" % (
            document_code, company_prefix, year_str, month_str, number_str,
        )
    return "%s/%s/%s/%s" % (document_code, company_prefix, year_str, number_str)


def build_format_preview_html(
    company_prefix,
    granularity="yearly",
    year_digits="4",
    number_digits="5",
):
    """Compact HTML preview for the active wizard selection only."""
    prefix = (company_prefix or "").strip() or "PREFIX"
    ref_date = date.today()
    try:
        num_pad = int(number_digits or 5)
    except (TypeError, ValueError):
        num_pad = 5
    gran = granularity or "yearly"
    ydig = year_digits or ("2" if gran == "monthly" else "4")

    active = build_sequence_number(
        "INV",
        prefix,
        gran,
        ydig,
        padding=num_pad,
        next_number=1,
        ref_date=ref_date,
    )

    period_label = _("Monthly") if gran == "monthly" else _("Yearly")
    year_label = _("2-digit year") if ydig == "2" else _("4-digit year")
    num_label = "{0}-digit number".format(num_pad)

    example = _("Example (sale invoice)")
    prefix_label = _("prefix")

    return (
        '<div class="cpabooks-sequence-format-preview text-muted">'
        '<p class="mb-1"><strong>{example}</strong> '
        '<span>({prefix_label}: <code>{prefix}</code> · {period} · {year} · {number})</span></p>'
        '<p class="mb-0"><code style="font-size:14px;">{active}</code></p>'
        '</div>'
    ).format(
        example=example,
        prefix_label=prefix_label,
        prefix=prefix.replace("{", "{{").replace("}", "}}"),
        period=period_label,
        year=year_label,
        number=num_label,
        active=active.replace("{", "{{").replace("}", "}}"),
    )


def replace_prefix_placeholders(prefix, field_date, year_digits="4"):
    """Substitute %(year)s / %(month)s / %(day)s in a sequence prefix."""
    if isinstance(field_date, str):
        from odoo import fields as odoo_fields
        field_date = odoo_fields.Date.to_date(field_date)
    day = field_date.day
    month = field_date.month
    year = field_date.year
    year_str = format_year(year, year_digits)
    result = prefix or ""
    if "%(year)s" in result:
        result = result.replace("%(year)s", year_str)
    if "%(month)s" in result:
        result = result.replace("%(month)s", "%02d" % month)
    if "%(day)s" in result:
        result = result.replace("%(day)s", "%02d" % day)
    return result
