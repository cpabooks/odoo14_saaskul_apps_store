# -*- coding: utf-8 -*-

from collections import OrderedDict

from odoo import api, fields, models, _
from odoo.tools.misc import formatLang


class CafmContractClientSoa(models.Model):
    _inherit = 'cpabooks.cafm.contract'

    def action_print_client_soa(self):
        """Print Client SOA (single project) PDF for selected active contracts."""
        self.ensure_one()
        return self.env.ref('cpabooks_cafm.action_report_cafm_client_soa').report_action(self)

    def _cafm_soa_as_of_date(self):
        return fields.Date.context_today(self)

    def _cafm_soa_project_label(self):
        self.ensure_one()
        if self.project_id:
            return self.project_id.display_name
        if self.unit_id:
            return self.unit_id.display_name
        return self.name or ''

    def _cafm_soa_customer_id_label(self):
        self.ensure_one()
        return self.ubs_no or self.client_id.ref or ''

    def _cafm_soa_recipient_lines(self):
        """Return address block lines for the To: section."""
        self.ensure_one()
        client = self.client_id
        lines = []
        contact = self.contact_person_id
        if contact and contact.name:
            lines.append(contact.name)
        elif client.parent_id:
            lines.append(client.name)
        if client:
            # Company / commercial name (avoid duplicating contact line)
            commercial = client.commercial_partner_id or client
            if commercial.name and commercial.name not in lines:
                lines.append(commercial.name)
            city_bits = []
            if client.city:
                city_bits.append(client.city)
            if client.country_id:
                city_bits.append(client.country_id.name)
            if city_bits:
                lines.append(' | '.join(city_bits))
            street_bits = [p for p in (client.street, client.street2) if p]
            if street_bits:
                lines.append(', '.join(street_bits))
        if self.unit_id:
            lines.append(self.unit_id.display_name)
        elif self.location:
            lines.append(self.location)
        elif self.project_location_id:
            lines.append(self.project_location_id.display_name)
        # Keep a blank separator line like the sample when location follows city
        if len(lines) >= 3 and lines[-1] and '|' not in lines[-1]:
            # Insert a single-dot placeholder before last location line when useful
            pass
        return lines

    def _cafm_soa_fmt_amount(self, amount):
        self.ensure_one()
        currency = self.currency_id or self.env.company.currency_id
        return '%s Dr' % formatLang(self.env, abs(amount or 0.0), currency_obj=currency)

    def _cafm_soa_amount_words(self, amount):
        self.ensure_one()
        currency = self.currency_id or self.env.company.currency_id
        try:
            words = currency.with_context(lang='en_US').amount_to_text(abs(amount or 0.0))
        except Exception:
            words = ''
        symbol = currency.name or 'AED'
        formatted = formatLang(self.env, abs(amount or 0.0), currency_obj=currency)
        if words:
            # Odoo often returns "Thirty Thousand ..." — sample style adds currency prefix
            return 'Total %s %s (%s Only)' % (symbol, formatted, words)
        return 'Total %s %s' % (symbol, formatted)

    def _cafm_soa_age_days(self, inv_date, as_of):
        if not inv_date:
            return 0
        return max(0, (as_of - inv_date).days)

    def _cafm_soa_push_line(self, bucket, key, vals):
        """Deduplicate by invoice ref; keep highest residual / amount."""
        if not key:
            key = 'row-%s' % (len(bucket) + 1)
        prev = bucket.get(key)
        if prev and abs(prev.get('amount') or 0.0) >= abs(vals.get('amount') or 0.0):
            # Prefer existing if larger (e.g. residual already set); merge blank fields
            for field in ('description', 'lpo_no', 'inv_date'):
                if not prev.get(field) and vals.get(field):
                    prev[field] = vals[field]
            return
        bucket[key] = vals

    def _cafm_soa_collect_lines(self, as_of=None):
        """Outstanding lines for this contract's single project."""
        self.ensure_one()
        as_of = as_of or self._cafm_soa_as_of_date()
        project = self.project_id
        partner = self.client_id.commercial_partner_id or self.client_id
        bucket = OrderedDict()

        # 1) Contract orders → posted invoice residual
        orders = self.contract_order_ids.filtered(
            lambda o: o.state == 'invoiced' and o.invoice_id
        )
        for order in orders:
            move = order.invoice_id
            if move.state != 'posted':
                continue
            amount = move.amount_residual
            if move.move_type == 'out_refund':
                amount = -abs(amount)
            if abs(amount) < 0.00001:
                continue
            inv_date = move.invoice_date or order.invoice_date
            if inv_date and inv_date > as_of:
                continue
            desc = order.amc_period_display or order.period_label or order.property_name
            if not desc and order.date_from and order.date_to:
                desc = 'AMC - From %s to %s' % (
                    order.date_from.strftime('%d-%m-%Y'),
                    order.date_to.strftime('%d-%m-%Y'),
                )
            if not desc:
                desc = 'AMC Invoice'
            inv_no = move.name or order.invoice_display_ref or order.name
            self._cafm_soa_push_line(bucket, inv_no, {
                'inv_no': inv_no,
                'inv_date': inv_date,
                'description': desc,
                'amount': amount,
                'lpo_no': '',
                'age_days': self._cafm_soa_age_days(inv_date, as_of),
                'source': 'contract_order',
            })

        # 2) AMC invoice register for same L3 / project name / UBS
        AmcInv = self.env['cpabooks.cafm.amc.invoice.reg']
        amc_domain = [('company_id', '=', self.company_id.id)]
        if project:
            amc_domain = [
                '&',
                ('company_id', '=', self.company_id.id),
                '|', '|',
                ('l3_level_id', '=', project.id),
                ('project_name', '=ilike', project.name),
                ('ubs_no', '=', self.ubs_no),
            ] if self.ubs_no else [
                '&',
                ('company_id', '=', self.company_id.id),
                '|',
                ('l3_level_id', '=', project.id),
                ('project_name', '=ilike', project.name),
            ]
        elif partner:
            amc_domain.append(('partner_id', 'child_of', partner.id))
        for reg in AmcInv.search(amc_domain, order='invoice_date asc, id asc'):
            inv_date = reg.invoice_date
            if inv_date and inv_date > as_of:
                continue
            inv_no = (reg.ref_no or '').strip()
            amount = reg.invoice_amount or 0.0
            if abs(amount) < 0.00001:
                continue
            # Prefer residual from matching posted move when available
            move = False
            if inv_no:
                move = self.env['account.move'].search([
                    ('company_id', '=', self.company_id.id),
                    ('state', '=', 'posted'),
                    ('move_type', 'in', ('out_invoice', 'out_refund')),
                    '|', ('name', '=', inv_no), ('ref', '=', inv_no),
                ], limit=1)
            if move:
                amount = move.amount_residual
                if move.move_type == 'out_refund':
                    amount = -abs(amount)
                if abs(amount) < 0.00001:
                    continue
                inv_date = move.invoice_date or inv_date
            desc = reg.remarks or reg.project_name or 'AMC Invoice'
            # Prefer schedule-style description when linked by amount/date
            if not reg.remarks and project:
                desc = reg.project_name or 'AMC'
            self._cafm_soa_push_line(bucket, inv_no or 'amc-%s' % reg.id, {
                'inv_no': inv_no or '',
                'inv_date': inv_date,
                'description': (desc or '').replace('\n', ' ').strip() or 'AMC Invoice',
                'amount': amount,
                'lpo_no': reg.contract_lpo_no or '',
                'age_days': self._cafm_soa_age_days(inv_date, as_of),
                'source': 'amc_reg',
            })

        # 3) VAR work invoiced for same project
        Var = self.env['cpabooks.cafm.var.work']
        var_domain = [
            ('company_id', '=', self.company_id.id),
            ('status', '=', 'invoiced'),
        ]
        if project:
            var_domain.append(('l3_level_id', '=', project.id))
        elif partner:
            var_domain.append(('partner_id', 'child_of', partner.id))
        for var in Var.search(var_domain, order='invoice_date asc, id asc'):
            inv_date = var.invoice_date or var.work_date
            if inv_date and inv_date > as_of:
                continue
            inv_no = (var.invoice_no or (var.invoice_id.name if var.invoice_id else '') or '').strip()
            amount = var.invoice_amount or 0.0
            if var.invoice_id and var.invoice_id.state == 'posted':
                amount = var.invoice_id.amount_residual
                if var.invoice_id.move_type == 'out_refund':
                    amount = -abs(amount)
                inv_date = var.invoice_id.invoice_date or inv_date
            if abs(amount) < 0.00001:
                continue
            desc = (var.problem_description or '').replace('\n', ' ').strip()
            if not desc and var.work_type_id:
                desc = var.work_type_id.name
            if not desc:
                desc = 'VAR Work'
            self._cafm_soa_push_line(bucket, inv_no or 'var-%s' % var.id, {
                'inv_no': inv_no or '',
                'inv_date': inv_date,
                'description': desc,
                'amount': amount,
                'lpo_no': var.lpo_no or '',
                'age_days': self._cafm_soa_age_days(inv_date, as_of),
                'source': 'var',
            })

        lines = list(bucket.values())
        lines.sort(key=lambda r: (r.get('inv_date') or fields.Date.to_date('1900-01-01'), r.get('inv_no') or ''))
        running = 0.0
        for line in lines:
            running += line.get('amount') or 0.0
            line['balance'] = running
            line['amount_display'] = self._cafm_soa_fmt_amount(line.get('amount') or 0.0)
            line['balance_display'] = self._cafm_soa_fmt_amount(line['balance'])
            if line.get('inv_date'):
                line['inv_date_display'] = line['inv_date'].strftime('%d-%m-%Y')
            else:
                line['inv_date_display'] = ''
        return lines

    def _cafm_soa_bank_vals(self):
        company = self.company_id or self.env.company
        account_name = company.name or ''
        bank_name = getattr(company, 'bank_name', None) or ''
        branch = getattr(company, 'bank_branch', None) or getattr(company, 'bank_address', None) or ''
        acc_no = getattr(company, 'bank_account_number', None) or ''
        iban = getattr(company, 'bank_iban_number', None) or ''
        swift = ''
        # Prefer primary partner bank if company fields empty
        partner_banks = company.partner_id.bank_ids if company.partner_id else self.env['res.partner.bank']
        if partner_banks:
            pb = partner_banks[0]
            if not acc_no:
                acc_no = pb.acc_number or ''
            if not bank_name and pb.bank_id:
                bank_name = pb.bank_id.name or ''
            if not swift and pb.bank_id:
                swift = pb.bank_id.bic or ''
            if not iban and getattr(pb, 'sanitized_acc_number', None):
                # Some setups store IBAN as acc_number
                if (pb.acc_number or '').upper().startswith('AE'):
                    iban = pb.acc_number
        return {
            'account_name': account_name,
            'bank_name': bank_name,
            'branch': branch,
            'acc_no': acc_no,
            'iban': iban,
            'swift': swift,
        }

    def _cafm_soa_company_name_parts(self):
        """Split company name for Green City style header."""
        company = self.company_id or self.env.company
        full = (company.name or '').strip()
        # Prefer "Green City Line" / "Facilities Services L.L.C." style split
        markers = ['Facilities', 'Facility', 'Services', 'L.L.C', 'LLC', 'L.L.C.']
        for marker in markers:
            idx = full.find(marker)
            if idx > 0:
                return full[:idx].strip(), full[idx:].strip()
        parts = full.split(' ', 3)
        if len(parts) >= 3:
            return ' '.join(parts[:3]), ' '.join(parts[3:]) if len(parts) > 3 else ''
        return full, ''

    def get_cafm_client_soa_data(self):
        """Full payload for QWeb Client SOA report."""
        self.ensure_one()
        as_of = self._cafm_soa_as_of_date()
        lines = self._cafm_soa_collect_lines(as_of=as_of)
        total = lines[-1]['balance'] if lines else 0.0
        company = self.company_id or self.env.company
        name_main, name_sub = self._cafm_soa_company_name_parts()
        stamp = False
        if 'stamp' in company._fields and company.stamp:
            stamp = company.stamp
        elif 'cpabooks_company_stamp' in company._fields and company.cpabooks_company_stamp:
            stamp = company.cpabooks_company_stamp
        arabic_name = ''
        if 'arabic_name' in company._fields and company.arabic_name:
            arabic_name = company.arabic_name
        elif company.partner_id and 'arabic_name' in company.partner_id._fields:
            arabic_name = company.partner_id.arabic_name or ''
        currency = self.currency_id or company.currency_id
        # Sample print uses sparingly-padded dates like 3-8-2026
        statement_date_display = '%s-%s-%s' % (as_of.day, as_of.month, as_of.year)
        return {
            'contract': self,
            'company': company,
            'as_of': as_of,
            'as_of_display': statement_date_display,
            'statement_date_display': statement_date_display,
            'project_label': self._cafm_soa_project_label(),
            'customer_id_label': self._cafm_soa_customer_id_label(),
            'recipient_lines': self._cafm_soa_recipient_lines(),
            'lines': lines,
            'total': total,
            'total_display': self._cafm_soa_fmt_amount(total),
            'total_outstanding_label': 'Total Outstanding Balance : %s %s' % (
                currency.name or 'AED',
                formatLang(self.env, abs(total), currency_obj=currency),
            ),
            'amount_words': self._cafm_soa_amount_words(total),
            'bank': self._cafm_soa_bank_vals(),
            'company_name_main': name_main,
            'company_name_sub': name_sub,
            'arabic_name': arabic_name,
            'stamp': stamp,
            'logo': company.logo,
        }


class ReportCafmClientSoa(models.AbstractModel):
    _name = 'report.cpabooks_cafm.report_cafm_client_soa_template'
    _description = 'CAFM Client SOA Single Project Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['cpabooks.cafm.contract'].browse(docids)
        payloads = {doc.id: doc.get_cafm_client_soa_data() for doc in docs}
        return {
            'doc_ids': docids,
            'doc_model': 'cpabooks.cafm.contract',
            'docs': docs,
            'payloads': payloads,
        }
