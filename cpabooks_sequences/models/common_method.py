import re
from datetime import date, datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.addons.cpabooks_sequences.models.sequence_format import format_year


class CommonMetthod(models.AbstractModel):
    _name = "common.method"

    @api.model
    def _cpabooks_prefix_year(self, date_obj):
        """Match stored document names (2- or 4-digit year per company setting)."""
        company = self.env.company
        year_digits = getattr(company, 'cpabooks_sequence_year_digits', None) or '2'
        if isinstance(date_obj, datetime):
            year = date_obj.year
        elif isinstance(date_obj, date):
            year = date_obj.year
        else:
            year = fields.Datetime.to_datetime(date_obj).year
        return format_year(year, year_digits)

    @api.model
    def _cpabooks_ref_datetime(self, date_obj):
        if isinstance(date_obj, datetime):
            return date_obj
        if isinstance(date_obj, date):
            return datetime.combine(date_obj, datetime.min.time())
        return fields.Datetime.to_datetime(date_obj)

    @api.model
    def parse_sequence_datetime(self, value, offset_hours=6):
        """Accept str, date, or datetime (Odoo 14 create() may pass any of these)."""
        if not value:
            dt = datetime.now()
        elif isinstance(value, datetime):
            dt = value
        elif isinstance(value, date):
            dt = datetime.combine(value, datetime.min.time())
        elif isinstance(value, str):
            text = value.strip()
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d'):
                try:
                    chunk = text[:19] if fmt == '%Y-%m-%d %H:%M:%S' and len(text) > 19 else text
                    dt = datetime.strptime(chunk, fmt)
                    break
                except ValueError:
                    continue
            else:
                raise ValueError('Invalid date value: %r' % value)
        else:
            dt = fields.Datetime.to_datetime(value)
        if offset_hours:
            dt += timedelta(hours=offset_hours)
        return dt

    def _cpabooks_highest_domain(self, model, record_id=None, extra_domain=None):
        domain = [('company_id', '=', self.env.company.id)]
        if record_id:
            domain.append(('id', '!=', record_id))
        if extra_domain:
            domain.extend(extra_domain)
        return domain

    def _cpabooks_sequence_name_field(self, model):
        if model == 'project.task':
            return 'task_seq'
        return 'name'

    def get_highest_seq_no_for_current_pattern(
        self, sequence_obj, date_obj, model,
        name_field=None, record_id=None, extra_domain=None,
    ):
        """Highest suffix for the active prefix/pattern/padding (not other patterns)."""
        from odoo.addons.cpabooks_sequences.models.sequence_format import (
            replace_prefix_placeholders,
        )
        name_field = name_field or self._cpabooks_sequence_name_field(model)
        ref = self._cpabooks_ref_datetime(date_obj)
        field_date = ref.date() if hasattr(ref, 'date') else ref
        prefix_template = (sequence_obj.prefix or '').replace('%(y)s', '%(year)s')
        seq_prefix = replace_prefix_placeholders(
            prefix_template,
            field_date,
            sequence_obj._cpabooks_year_digits(),
        )
        padding = int(sequence_obj.padding or 1)
        pattern = re.compile(rf'^{re.escape(seq_prefix)}\d{{{padding}}}$')
        domain = self._cpabooks_highest_domain(
            model, record_id=record_id, extra_domain=extra_domain,
        )
        domain.append((name_field, '=like', seq_prefix + '%'))
        orders = self.env[model].sudo().search(domain, order='%s desc' % name_field, limit=40)
        best = 0
        for order in orders:
            label = order[name_field]
            if not label or not pattern.match(label):
                continue
            try:
                best = max(best, int(str(label)[len(seq_prefix):]))
            except (ValueError, IndexError):
                continue
        return best

    def get_highest_seq_for_year_yearly(
        self, get_sequence_object, date_obj, model,
        extra_condition=False, record_id=None, extra_domain=None,
    ):
        padding = get_sequence_object.padding
        actual_prefix = get_sequence_object.prefix.split('%')
        ref = self._cpabooks_ref_datetime(date_obj)
        prefix = f'{actual_prefix[0]}{self._cpabooks_stored_document_year(ref)}'
        pattern = re.compile(
            rf'^{re.escape(prefix)}/\d{{{int(padding)}}}$')
        domain = self._cpabooks_highest_domain(
            model, record_id=record_id, extra_domain=extra_domain,
        )
        domain.append(('name', '=like', prefix + '%'))
        orders = self.env[model].sudo().search(domain, order='name desc', limit=40)
        highest_order = None
        best_num = -1
        for order in orders:
            if not pattern.match(order.name):
                continue
            try:
                num = int(order.name.split('/')[-1])
            except (ValueError, IndexError):
                continue
            if num > best_num:
                best_num = num
                highest_order = order
        return highest_order

    def get_highest_seq_for_month_year_monthly(
        self, get_sequence_object, date_obj, model,
        extra_condition=False, record_id=None, extra_domain=None,
    ):
        padding = get_sequence_object.padding
        actual_prefix = get_sequence_object.prefix.split('%')
        ref = self._cpabooks_ref_datetime(date_obj)
        month = ref.strftime('%m')
        prefix = f'{actual_prefix[0]}{self._cpabooks_stored_document_year(ref)}/{month}'
        pattern = re.compile(
            rf'^{re.escape(prefix)}/\d{{{int(padding)}}}$')
        domain = self._cpabooks_highest_domain(
            model, record_id=record_id, extra_domain=extra_domain,
        )
        domain.append(('name', '=like', prefix + '%'))
        orders = self.env[model].sudo().search(domain, order='name desc', limit=40)
        highest_order = None
        best_num = -1
        for order in orders:
            if not pattern.match(order.name):
                continue
            try:
                num = int(order.name.split('/')[-1])
            except (ValueError, IndexError):
                continue
            if num > best_num:
                best_num = num
                highest_order = order
        return highest_order

    def _cpabooks_stored_document_year(self, date_obj):
        """Calendar year used in account.move names (see _set_sequence_component)."""
        ref = self._cpabooks_ref_datetime(date_obj)
        return str(ref.year)

    def _cpabooks_search_highest_sequence_number(self, model, domain):
        """Highest sequence_number for domain; safe under JV list view context.

        Journal list actions put cpabooks_jv_view_mode=latest_20 in the context.
        That can rewrite nested account.move searches so limit=1 is lost and
        ``search(...).sequence_number`` raises Expected singleton.
        """
        Move = self.env[model].sudo().with_context(
            cpabooks_jv_view_mode=False,
            cpabooks_odoo_fix_jv_view_mode=False,
        )
        highest_rec = Move.search(
            domain, limit=1, order="sequence_number desc, id desc",
        )[:1]
        return highest_rec.sequence_number if highest_rec else 0

    def get_highest_seq_no(
        self, get_sequence_object, date_obj, model,
        record_id=None, extra_domain=None,
    ):
        padding = get_sequence_object.padding
        actual_prefix = get_sequence_object.prefix.split('%')
        ref = self._cpabooks_ref_datetime(date_obj)
        prefix = f'{actual_prefix[0]}{self._cpabooks_stored_document_year(ref)}/'
        domain = self._cpabooks_highest_domain(
            model, record_id=record_id, extra_domain=extra_domain,
        )
        domain.append(('sequence_prefix', '=', prefix))
        highest = self._cpabooks_search_highest_sequence_number(model, domain)
        if highest:
            return highest
        highest_rec = self.get_highest_seq_for_year_yearly(
            get_sequence_object, date_obj, model,
            record_id=record_id, extra_domain=extra_domain,
        )
        if highest_rec and highest_rec.name:
            try:
                return int(highest_rec.name.split('/')[-1])
            except (ValueError, IndexError):
                pass
        return 0

    def get_highest_seq_no_month_year_monthly(
        self, get_sequence_object, date_obj, model,
        record_id=None, extra_domain=None,
    ):
        padding = get_sequence_object.padding
        actual_prefix = get_sequence_object.prefix.split('%')
        ref = self._cpabooks_ref_datetime(date_obj)
        month = ref.strftime('%m')
        prefix = f'{actual_prefix[0]}{self._cpabooks_stored_document_year(ref)}/{month}/'
        domain = self._cpabooks_highest_domain(
            model, record_id=record_id, extra_domain=extra_domain,
        )
        domain.append(('sequence_prefix', '=', prefix))
        highest = self._cpabooks_search_highest_sequence_number(model, domain)
        if highest:
            return highest
        highest_rec = self.get_highest_seq_for_month_year_monthly(
            get_sequence_object, date_obj, model,
            record_id=record_id, extra_domain=extra_domain,
        )
        if highest_rec and highest_rec.name:
            try:
                return int(highest_rec.name.split('/')[-1])
            except (ValueError, IndexError):
                pass
        return 0
