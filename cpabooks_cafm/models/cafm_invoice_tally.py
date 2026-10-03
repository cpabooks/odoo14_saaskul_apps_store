# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.tools.misc import formatLang


class AccountMoveCafmTallyInvoice(models.Model):
    _inherit = 'account.move'

    def _cafm_tally_fmt_amount(self, amount, currency=False):
        currency = currency or self.currency_id or self.env.company.currency_id
        return formatLang(self.env, amount or 0.0, digits=2, grouping=True)

    def _cafm_tally_fmt_date(self, value, padded=True):
        value = fields.Date.to_date(value) if value else False
        if not value:
            return ''
        if padded:
            return value.strftime('%d-%m-%Y')
        return '%s-%s-%s' % (value.day, value.month, value.year)

    def _cafm_tally_company_name_parts(self, company):
        full = (company.name or '').strip()
        for marker in ('Facilities', 'Facility', 'Services', 'L.L.C', 'LLC'):
            idx = full.find(marker)
            if idx > 0:
                return full[:idx].strip(), full[idx:].strip()
        parts = full.split(' ', 3)
        if len(parts) >= 3:
            return ' '.join(parts[:3]), ' '.join(parts[3:]) if len(parts) > 3 else ''
        return full, ''

    def _cafm_tally_arabic_name(self, company):
        if 'arabic_name' in company._fields and company.arabic_name:
            return company.arabic_name
        partner = company.partner_id
        if partner and 'arabic_name' in partner._fields:
            return partner.arabic_name or ''
        return ''

    def _cafm_tally_bank_vals(self, company):
        account_name = (company.name or '').replace('L.L.C.', 'LLC').replace('L.L.C', 'LLC')
        bank_name = getattr(company, 'bank_name', None) or ''
        branch = getattr(company, 'bank_branch', None) or getattr(company, 'bank_address', None) or ''
        acc_no = getattr(company, 'bank_account_number', None) or ''
        iban = getattr(company, 'bank_iban_number', None) or ''
        swift = ''
        partner_banks = company.partner_id.bank_ids if company.partner_id else self.env['res.partner.bank']
        if partner_banks:
            pb = partner_banks[0]
            if not acc_no:
                acc_no = pb.acc_number or ''
            if not bank_name and pb.bank_id:
                bank_name = pb.bank_id.name or ''
            if not swift and pb.bank_id:
                swift = pb.bank_id.bic or ''
            if not iban and (pb.acc_number or '').upper().startswith('AE'):
                iban = pb.acc_number
        return {
            'account_name': account_name,
            'bank_name': bank_name,
            'branch': branch,
            'acc_no': acc_no,
            'iban': iban,
            'swift': swift,
        }

    def _cafm_tally_amount_words(self, amount, currency):
        words = ''
        if 'num_word' in self._fields and self.num_word:
            words = self.num_word
        else:
            try:
                words = currency.with_context(lang='en_US').amount_to_text(abs(amount or 0.0))
            except Exception:
                words = ''
        words = (words or '').replace('And', 'and').strip()
        if words.lower().startswith('uae dirham'):
            return 'Total Amount in words : %s' % words
        name = 'UAE Dirhams' if (currency.name or '') in ('AED', 'DH') else (currency.currency_unit_label or currency.name or '')
        if words:
            return 'Total Amount in words : %s %s' % (name, words)
        return 'Total Amount in words : %s %s' % (currency.name or '', self._cafm_tally_fmt_amount(amount, currency))

    def _cafm_tally_contact_person(self):
        partner = self.partner_id
        if not partner:
            return ''
        if partner.type == 'contact' and partner.parent_id:
            return partner.name or ''
        child = partner.child_ids.filtered(lambda p: p.type == 'contact' and p.name)[:1]
        return child.name if child else ''

    def _cafm_tally_bill_to_lines(self):
        partner = self.partner_id.commercial_partner_id or self.partner_id
        lines = []
        if partner:
            lines.append('M/s. %s' % (partner.name or ''))
        addr = self.partner_id
        for part in (addr.street, addr.street2):
            if part:
                lines.append(part)
        city_line = ', '.join([p for p in (
            addr.city,
            addr.state_id.name if addr.state_id else '',
            addr.country_id.name if addr.country_id else '',
        ) if p])
        if city_line:
            lines.append(city_line)
        phones = []
        if addr.phone:
            phones.append('Tel- %s' % addr.phone)
        if addr.mobile and addr.mobile != addr.phone:
            phones.append(addr.mobile)
        if phones:
            lines.append(', '.join(phones))
        return lines

    def _cafm_tally_ordinal(self, number):
        n = int(number or 0)
        if n <= 0:
            return ''
        if 10 <= (n % 100) <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return '%s%s' % (n, suffix)

    def _cafm_tally_period_title(self, order):
        freq = order.contract_id.invoice_frequency or ''
        names = {
            'monthly': 'Monthly Invoice for 1 Month',
            'quarterly': 'Quarterly Invoice for 3 Months',
            'half_yearly': 'Half Yearly Invoice for 6 Months',
            'annually': 'Yearly Invoice for 12 Months',
        }
        base = names.get(freq, 'Invoice')
        label = order.period_label or ''
        match = re.search(r'([HQYM])\s*(\d+)', label, re.I)
        if match:
            ordinal = self._cafm_tally_ordinal(match.group(2))
            if freq == 'half_yearly':
                return '%s Half Yearly Invoice for 6 Months' % ordinal
            if freq == 'quarterly':
                return '%s Quarterly Invoice for 3 Months' % ordinal
            if freq == 'monthly':
                return '%s Monthly Invoice for 1 Month' % ordinal
            if freq == 'annually':
                return '%s Yearly Invoice' % ordinal
            return '%s %s' % (ordinal, base)
        return base

    def _cafm_tally_amc_blocks(self, order):
        contract = order.contract_id
        project = contract.project_id.display_name if contract.project_id else ''
        location = contract.location or ''
        place = ' '.join([p for p in (project, location) if p]).strip()
        title = 'Invoice for Annual Maintenance Charges'
        if place:
            title = '%s For %s' % (title, place)
        blocks = [title]
        if contract.contract_date or contract.contract_expiry:
            blocks.append('Contract Period From %s to %s' % (
                self._cafm_tally_fmt_date(contract.contract_date),
                self._cafm_tally_fmt_date(contract.contract_expiry),
            ))
        if contract.total_contract_value:
            currency = contract.currency_id or self.currency_id
            blocks.append('Total Amount of the Contract----------------- %s %s' % (
                currency.name or 'AED',
                self._cafm_tally_fmt_amount(contract.total_contract_value, currency),
            ))
        blocks.append(self._cafm_tally_period_title(order))
        if order.date_from or order.date_to:
            blocks.append('Invoice Period From %s to %s' % (
                self._cafm_tally_fmt_date(order.date_from),
                self._cafm_tally_fmt_date(order.date_to),
            ))
        blocks.append('Encl: Copy of Service Contract & Reports Summary')
        return blocks

    def _cafm_tally_vat_label(self):
        taxes = self.invoice_line_ids.mapped('tax_ids')
        if taxes:
            amount = taxes[0].amount or 0.0
            if amount == int(amount):
                return 'VAT @ %s%%' % int(amount)
            return 'VAT @ %s%%' % amount
        return 'VAT @ 5%'

    def get_cafm_tally_invoice_data(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        currency = self.currency_id or company.currency_id
        name_main, name_sub = self._cafm_tally_company_name_parts(company)
        stamp = False
        if 'stamp' in company._fields and company.stamp:
            stamp = company.stamp
        elif 'cpabooks_company_stamp' in company._fields and company.cpabooks_company_stamp:
            stamp = company.cpabooks_company_stamp
        footer_image = False
        if 'report_footer_image' in company._fields and company.report_footer_image:
            footer_image = company.report_footer_image

        lines = []
        orders = self.cafm_contract_order_ids.filtered(lambda o: o.state != 'cancelled')
        if orders:
            serial = 1
            for order in orders:
                lines.append({
                    'serial': serial,
                    'blocks': self._cafm_tally_amc_blocks(order),
                    'amount': order.amount or 0.0,
                    'amount_display': self._cafm_tally_fmt_amount(order.amount or 0.0, currency),
                })
                serial += 1
        else:
            serial = 1
            for line in self.invoice_line_ids.filtered(lambda l: not l.display_type):
                lines.append({
                    'serial': serial,
                    'blocks': [line.name or line.product_id.display_name or ''],
                    'amount': line.price_subtotal or 0.0,
                    'amount_display': self._cafm_tally_fmt_amount(line.price_subtotal or 0.0, currency),
                })
                serial += 1

        lpo = getattr(self, 'lpo_no', False) or self.ref or ''
        terms = self.invoice_payment_term_id.name if self.invoice_payment_term_id else ''
        partner = self.partner_id.commercial_partner_id or self.partner_id
        cheque_name = (company.name or '').replace('L.L.C.', 'LLC').replace('L.L.C', 'LLC')
        return {
            'move': self,
            'company': company,
            'company_name_main': name_main,
            'company_name_sub': name_sub,
            'arabic_name': self._cafm_tally_arabic_name(company),
            'logo': company.logo,
            'stamp': stamp,
            'footer_image': footer_image,
            'trn': company.vat or '',
            'partner_trn': partner.vat or '',
            'bill_to_lines': self._cafm_tally_bill_to_lines(),
            'contact_person': self._cafm_tally_contact_person(),
            'inv_no': self.name or '',
            'inv_date': self._cafm_tally_fmt_date(self.invoice_date, padded=False),
            'lpo': lpo,
            'terms': terms,
            'lines': lines,
            'amount_untaxed_display': self._cafm_tally_fmt_amount(self.amount_untaxed, currency),
            'amount_tax_display': self._cafm_tally_fmt_amount(self.amount_tax, currency),
            'amount_total_display': self._cafm_tally_fmt_amount(self.amount_total, currency),
            'vat_label': self._cafm_tally_vat_label(),
            'amount_words': self._cafm_tally_amount_words(self.amount_total, currency),
            'bank': self._cafm_tally_bank_vals(company),
            'cheque_name': cheque_name,
            'email': company.email or '',
            'website': company.website or '',
            'phone': company.phone or '',
            'street': company.street or '',
            'street2': company.street2 or '',
            'city': company.city or '',
            'country': company.country_id.name if company.country_id else '',
        }


class ReportCafmInvoiceTally(models.AbstractModel):
    _name = 'report.cpabooks_cafm.report_cafm_invoice_tally_template'
    _description = 'Print Invoice (Tally Format)'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.move'].browse(docids)
        payloads = {doc.id: doc.get_cafm_tally_invoice_data() for doc in docs}
        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'docs': docs,
            'payloads': payloads,
        }
