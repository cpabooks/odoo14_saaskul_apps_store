import datetime
from decimal import Decimal

from odoo import models, fields, api,_
from odoo.exceptions import ValidationError


class AccountMoveInheritance(models.Model):
    _inherit = 'account.move'

    # name = fields.Char(string='Number', copy=False, compute='_compute_name_get', readonly=True, store=True, index=True,
    #                    tracking=True)

    name = fields.Char(string='Number', copy=False, index=True,
                       tracking=True)

    invoice_date = fields.Date(string='Invoice/Bill Date', readonly=True, index=True, copy=False,
                               states={'draft': [('readonly', False)]},
                               default=lambda self:datetime.datetime.now().date())

    system_admin=fields.Boolean(compute="_get_system_admin")

    data_from_excel=fields.Boolean()

    def _is_sequence_placeholder_name(self, name):
        return not name or name in ('/', 'DRAFT', 'draft', 'Draft', 'NEW', 'new', 'New')

    def _constrains_date_sequence(self):
        payment_moves = self.filtered('payment_id')
        super(AccountMoveInheritance, self - payment_moves)._constrains_date_sequence()

    def _get_sequence_component_index(self, sequence_obj, split_seq, component):
        placeholder_map = {
            'year': '%(year)s',
            'month': '%(month)s',
            'day': '%(day)s',
        }
        placeholder = placeholder_map.get(component, component)
        prefix_parts = [part for part in (sequence_obj.prefix or '').split('/') if part]
        try:
            idx = prefix_parts.index(placeholder)
        except ValueError:
            return False
        if idx >= len(split_seq):
            return False
        return idx

    def _set_sequence_component(self, sequence_obj, split_seq, component, value):
        idx = self._get_sequence_component_index(sequence_obj, split_seq, component)
        if idx is False:
            return False
        split_seq[idx] = value
        return True

    def _sequence_matches_date(self, split_name_parts, date_obj, year_index, month_index=None):
        if not split_name_parts or year_index is False or year_index >= len(split_name_parts):
            return False
        if str(date_obj.year) != split_name_parts[year_index]:
            return False
        if month_index is None:
            return True
        if month_index >= len(split_name_parts):
            return False
        try:
            return int(split_name_parts[month_index]) == date_obj.month
        except (TypeError, ValueError):
            return False

    def _cpabooks_sale_invoice_sequence_prefix(self, sequence_obj, invoice_date):
        common = self.env['common.method']
        ref = common._cpabooks_ref_datetime(invoice_date)
        base = (sequence_obj.prefix or '').split('%')[0]
        year = common._cpabooks_stored_document_year(ref)
        if sequence_obj._cpabooks_is_monthly_pattern(sequence_obj.sequence_pattern):
            return '%s%s/%s/' % (base, year, ref.strftime('%m'))
        return '%s%s/' % (base, year)

    def _cpabooks_posted_name_conflict(self):
        self.ensure_one()
        if not self.name or self.name == '/':
            return self.env['account.move']
        return self.search([
            ('id', '!=', self.id),
            ('name', '=', self.name),
            ('journal_id', '=', self.journal_id.id),
            ('move_type', '=', self.move_type),
            ('state', '=', 'posted'),
        ], limit=1)

    def _cpabooks_next_available_move_name(self):
        """Next free name using the same client prefix and digit padding as self.name."""
        self.ensure_one()
        if self._is_sequence_placeholder_name(self.name) or '/' not in self.name:
            return False
        parts = self.name.split('/')
        suffix = parts[-1]
        if not suffix.isdigit():
            return False
        prefix = '/'.join(parts[:-1]) + '/'
        padding = len(suffix)
        next_num = int(suffix)
        Move = self.env['account.move'].sudo()
        while True:
            candidate = '%s%s' % (prefix, str(next_num).zfill(padding))
            if not Move.search_count([
                ('id', '!=', self.id),
                ('name', '=', candidate),
                ('journal_id', '=', self.journal_id.id),
                ('move_type', '=', self.move_type),
                ('state', '=', 'posted'),
            ]):
                return candidate
            next_num += 1

    def _cpabooks_resolve_posted_name_conflict(self):
        """Assign the next unused sequence number without changing prefix/padding."""
        self.ensure_one()
        if not self._cpabooks_posted_name_conflict():
            return False
        next_name = self._cpabooks_next_available_move_name()
        if not next_name:
            return False
        parts = next_name.split('/')
        self.with_context(skip_duplicate_source_name_restore=True).write({
            'name': next_name,
            'sequence_number': parts[-1],
            'sequence_prefix': '/'.join(parts[:-1]) + '/',
        })
        return True

    def _cpabooks_next_sale_invoice_name(self, invoice_date=None):
        self.ensure_one()
        if self.move_type != 'out_invoice':
            return False
        invoice_date = invoice_date or self.invoice_date or fields.Date.context_today(self)
        company_id = self.company_id.id or self.env.company.id
        sequence_obj = self.env['ir.sequence'].sudo().search(
            [('sequence_for', '=', 'sale_invoice'), ('company_id', 'in', [company_id, False])],
            limit=1,
        )
        if not sequence_obj:
            return False
        common = self.env['common.method']
        ref = common._cpabooks_ref_datetime(invoice_date)
        prefix = self._cpabooks_sale_invoice_sequence_prefix(sequence_obj, invoice_date)
        if sequence_obj._cpabooks_is_monthly_pattern(sequence_obj.sequence_pattern):
            highest = common.get_highest_seq_no_for_current_pattern(
                sequence_obj, ref, 'account.move',
                extra_domain=[('move_type', 'in', ('out_invoice', 'out_receipt'))],
            )
        else:
            highest = common.get_highest_seq_no_for_current_pattern(
                sequence_obj, ref, 'account.move',
                extra_domain=[('move_type', 'in', ('out_invoice', 'out_receipt'))],
            )
        next_number = int(highest or 0) + 1
        while True:
            candidate = '%s%s' % (prefix, str(next_number).zfill(sequence_obj.padding))
            if not self.search_count([
                ('id', '!=', self.id),
                ('name', '=', candidate),
                ('journal_id', '=', self.journal_id.id),
                ('move_type', '=', self.move_type),
                ('state', '=', 'posted'),
            ]):
                return candidate
            next_number += 1

    def _get_sale_invoice_backdated_sequence_name(self, invoice_date):
        self.ensure_one()
        if self.move_type != 'out_invoice':
            return False
        if not invoice_date:
            return False
        if not self.name or self.name in ('/', 'DRAFT', 'draft', 'Draft', 'NEW', 'new', 'New'):
            return False

        company_id = self.company_id.id or self.env.company.id
        get_sequence_object = self.env['ir.sequence'].sudo().search(
            [('sequence_for', '=', 'sale_invoice'), ('company_id', 'in', [company_id, False])],
            limit=1,
        )
        if not get_sequence_object:
            return False

        sequence_prefix = self._cpabooks_sale_invoice_sequence_prefix(get_sequence_object, invoice_date)
        current_prefix = False
        if self.name and '/' in self.name:
            current_prefix = '/'.join(self.name.split('/')[:-1]) + '/'
        if current_prefix == sequence_prefix:
            return self.name

        return self._cpabooks_next_sale_invoice_name(invoice_date)

    def _get_journal_voucher_backdated_sequence_name(self, move_date):
        self.ensure_one()
        if self.move_type != 'entry' or self.payment_id:
            return False
        if not move_date:
            return False
        if not self.name or self.name in ('/', 'DRAFT', 'draft', 'Draft', 'NEW', 'new', 'New'):
            return False

        company_id = self.company_id.id or self.env.company.id
        get_sequence_object = self.env['ir.sequence'].sudo().search(
            [('sequence_for', '=', 'journal_voucher'), ('company_id', 'in', [company_id, False])],
            limit=1,
        )
        if not get_sequence_object:
            return False

        get_sequence = self.env['ir.sequence'].next_by_sequence_for(
            'journal_voucher', sequence_date=move_date
        )
        if not get_sequence:
            return False
        split_sequence = get_sequence.split('/')
        if len(split_sequence) < 2:
            return get_sequence

        sequence_prefix = '/'.join(split_sequence[:-1]) + '/'
        current_prefix = '/'.join(self.name.split('/')[:-1]) + '/' if '/' in self.name else False
        if current_prefix == sequence_prefix:
            return self.name

        highest_move = self.env['account.move'].with_context(
            cpabooks_jv_view_mode=False,
            cpabooks_odoo_fix_jv_view_mode=False,
        ).search(
            [
                ('move_type', '=', 'entry'),
                ('payment_id', '=', False),
                ('company_id', '=', company_id),
                ('id', '!=', self.id),
                ('sequence_prefix', '=', sequence_prefix),
            ],
            limit=1,
            order='sequence_number desc, id desc',
        )[:1]
        next_number = (highest_move.sequence_number or 0) + 1
        split_sequence[-1] = str(next_number).zfill(get_sequence_object.padding)
        return '/'.join(split_sequence)

    # @api.depends('state')
    # def _get_system_admin(self):
    #     for rec in self:
    #         get_admin_power_group=self.env['res.groups'].sudo().search([('name','=ilike','Sequence Editor')])
    #         if get_admin_power_group:
    #             if self.env.user.has_group('base.group_system') or self.env.user.id in get_admin_power_group.users.ids:
    #                 rec.system_admin=True
    #             else:
    #                 rec.system_admin=False
    #         else:
    #             if self.env.user.has_group('base.group_system'):
    #                 rec.system_admin=True
    #             else:
    #                 rec.system_admin=False
    @api.depends('state')
    def _get_system_admin(self):
        for rec in self:
            rec.system_admin = False
            get_admin_power_group = self.env['res.groups'].sudo().search([('name', '=ilike', 'Sequence Editor')])
            if get_admin_power_group:
                if self.env.user.id in get_admin_power_group.users.ids:
                    rec.system_admin = True
                else:
                    rec.system_admin = False
            # else:
            #     if self.env.user.has_group('base.group_system'):
            #         rec.system_admin = True
            #     else:
            #         rec.system_admin = False

    # def get_system_admin(self):
    #     for rec in self:
    #         if not isinstance(rec.name,bool):
    #             if self.env.user.

    # @api.depends('journal_id')
    # def _compute_name_get(self):
    #     for rec in self:
    #         if not isinstance(rec.name,bool):
    #             if rec.name=='/' or rec.name.upper()=='DRAFT' or rec.name.upper()=='NEW':
    #                 rec.name='/'
    #             else:
    #                 rec.name=rec.name
    #         else:
    #             rec.name = '/'


    def _cpabooks_finalize_sequence_dates_only(self, sequence_obj, sequence, inv_name, vals_list):
        """Apply year/month segments only; keep the counter-based suffix."""
        if inv_name:
            inv_parts = inv_name.split('/')
            seq_parts = sequence.split('/')
            if inv_parts and seq_parts:
                seq_parts[-1] = inv_parts[-1]
                sequence = '/'.join(seq_parts)
        split_seq = sequence.split('/')
        date_val = vals_list.get('invoice_date') or vals_list.get('date')
        if not date_val and self.invoice_date:
            date_val = self.invoice_date
        if date_val and not isinstance(date_val, bool):
            date_obj = self.env['common.method'].parse_sequence_datetime(date_val)
            if '/%(year)s/' in (sequence_obj.prefix or ''):
                self._set_sequence_component(
                    sequence_obj, split_seq, 'year', str(date_obj.year),
                )
            if '/%(month)s/' in (sequence_obj.prefix or ''):
                self._set_sequence_component(
                    sequence_obj, split_seq, 'month', date_obj.strftime('%m'),
                )
            sequence = '/'.join(split_seq)
        return sequence

    def _get_sequence(self,get_sequence_object,get_sequence,inv_name,vals_list,get_highest_inv):
        if get_sequence_object.cpabooks_start_new_sequence:
            return self._cpabooks_finalize_sequence_dates_only(
                get_sequence_object, get_sequence, inv_name, vals_list,
            )
        if (
            get_sequence_object._cpabooks_is_monthly_pattern(get_sequence_object.sequence_pattern)
            and '/%(year)s/%(month)s/' not in (get_sequence_object.prefix or '')
        ):
            fixed_prefix = get_sequence_object._cpabooks_prefix_for_pattern(
                get_sequence_object.sequence_pattern,
                get_sequence_object.prefix or '',
            )
            if fixed_prefix and fixed_prefix != get_sequence_object.prefix:
                get_sequence_object.sudo().with_context(
                    cpabooks_sequence_force_write=True,
                ).write({'prefix': fixed_prefix})
        common_method = self.env['common.method']
        model = 'account.move'
        if '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='month_year':
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_inv and get_highest_inv.name!='/':
                    split_highest_inv=get_highest_inv.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                # split_highest_inv = get_highest_inv.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            if 'invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'],
                                                                     bool):
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(vals_list['invoice_date']).split('-')[0]):
                    get_sequence = "/".join(split_seq)
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(vals_list['invoice_date']).split('-')[1]):
                    get_sequence = "/".join(split_seq)
            if 'invoice_date' not in vals_list.keys() and not isinstance(self.invoice_date,
                                                                     bool):
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(self.invoice_date).split('-')[0]):
                    get_sequence = "/".join(split_seq)
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(self.invoice_date).split('-')[1]):
                    get_sequence = "/".join(split_seq)
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool) and self.move_type=='entry':
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(vals_list['date']).split('-')[0]):
                    get_sequence = "/".join(split_seq)
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(vals_list['date']).split('-')[1]):
                    get_sequence = "/".join(split_seq)
            return get_sequence
        #1st change
        elif '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='month_year_monthly':
            split_seq_obj = get_sequence_object.prefix.split('/')
            get_year_index = split_seq_obj.index('%(year)s')
            get_month_index = split_seq_obj.index('%(month)s')
            split_inv_name = []
            for i in range(get_year_index + 3):
                split_inv_name.append('')
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_inv and get_highest_inv.name!='/':
                #     split_highest_inv=get_highest_inv.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])-2
                    get_sequence_object.number_next_actual =get_sequence_object.number_next_actual-1

            else:
                split_seq = get_sequence.split('/')
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual-1


                # split_highest_inv = get_highest_inv.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            if 'invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'],
                                                                     bool):
                date_obj = datetime.datetime.strptime(str(vals_list['invoice_date']), '%Y-%m-%d') + datetime.timedelta(
                    hours=6)
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(date_obj).split('-')[0]):
                    get_sequence = "/".join(split_seq)
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(date_obj).split('-')[1]):
                    get_sequence = "/".join(split_seq)

                    # region Month wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if self._sequence_matches_date(split_inv_name, date_obj, get_year_index, get_month_index):
                        orginal_sequence = inv_name.split('/')
                    else:
                        get_highest_sequence_no = common_method.get_highest_seq_no_month_year_monthly(get_sequence_object,
                                                                                                    date_obj, model)
                        # get_highest_sequence_no = self.env['account.move'].search(
                        #     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="sequence_number desc",
                        #     limit=1).sequence_number

                        sequence_padding = get_sequence_object.padding
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            divide_by=100000
                            if sequence_padding==4:
                                divide_by=10000
                            if sequence_padding==3:
                                divide_by=1000
                            if sequence_padding==2:
                                divide_by=100
                            if sequence_padding==1:
                                divide_by=10
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert
                    get_sequence = "/".join(orginal_sequence)
                    # endregion
            if 'invoice_date' not in vals_list.keys() and not isinstance(self.invoice_date,
                                                                     bool):
                date_obj = self.invoice_date + datetime.timedelta(hours=6)
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(date_obj).split('-')[0]):
                    get_sequence = "/".join(split_seq)
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(date_obj).split('-')[1]):
                    get_sequence = "/".join(split_seq)
                    #region Month wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"
                    # date_obj = datetime.strptime(str(vals_list['invoice_date']), '%Y-%m-%d')

                    if self._sequence_matches_date(split_inv_name, date_obj, get_year_index, get_month_index):
                        orginal_sequence = inv_name.split('/')
                    else:
                        get_highest_sequence_no = common_method.get_highest_seq_no_month_year_monthly(get_sequence_object,
                                                                                                    date_obj, model)
                        # get_highest_sequence_no = self.env['account.move'].search(
                        #     [('sequence_prefix', '=', without_last_index_sequence),('id','!=',self.id)], order="sequence_number desc",
                        #     limit=1).sequence_number

                        sequence_padding = get_sequence_object.padding
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            common='1'
                            divide_by=int(common.ljust(sequence_padding+1,'0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert
                    get_sequence = "/".join(orginal_sequence)
                    #endregion
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool) and self.move_type=='entry':
                date_obj = datetime.datetime.strptime(str(vals_list['date']), '%Y-%m-%d') + datetime.timedelta(hours=6)
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(date_obj).split('-')[0]):
                    get_sequence = "/".join(split_seq)
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(date_obj).split('-')[1]):
                    get_sequence = "/".join(split_seq)

                    # region Month wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if self._sequence_matches_date(split_inv_name, date_obj, get_year_index, get_month_index):
                        orginal_sequence = inv_name.split('/')
                    else:
                        get_highest_sequence_no = common_method.get_highest_seq_no_month_year_monthly(get_sequence_object,date_obj, model)
                        # get_highest_sequence_no = self.env['account.move'].search(
                        #     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="sequence_number desc",
                        #     limit=1).sequence_number

                        sequence_padding = get_sequence_object.padding
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            divide_by=100000
                            if sequence_padding==4:
                                divide_by=10000
                            if sequence_padding==3:
                                divide_by=1000
                            if sequence_padding==2:
                                divide_by=100
                            if sequence_padding==1:
                                divide_by=10
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert
                    get_sequence = "/".join(orginal_sequence)
            
            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='year' :
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_inv and get_highest_inv.name!='/':
                    split_highest_inv=get_highest_inv.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
            if 'invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'],
                                                                     bool):
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(vals_list['invoice_date']).split('-')[0]):
                    get_sequence = "/".join(split_seq)

            if 'invoice_date' not in vals_list.keys() and not isinstance(self.invoice_date,
                                                                     bool):
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(self.invoice_date).split('-')[0]):
                    get_sequence = "/".join(split_seq)

            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool) and self.move_type=='entry':
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(vals_list['date']).split('-')[0]):
                    get_sequence = "/".join(split_seq)

            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='year_yearly':
            split_seq_obj = get_sequence_object.prefix.split('/')
            get_year_index = split_seq_obj.index('%(year)s')
            split_inv_name = []
            for i in range(get_year_index + 1):
                split_inv_name.append('')
            split_inv_name.append('')
            # split_inv_name = ['', '', '', ''] if inv_name == '' else inv_name.split('/')
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_inv and get_highest_inv.name != '/':
                    split_highest_inv = get_highest_inv.name.split('/')
                    # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) -2
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual-1
            else:
                split_seq = get_sequence.split('/')
                # get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            if 'invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'],
                                                                     bool):
                date_obj = datetime.datetime.strptime(str(vals_list['invoice_date']), '%Y-%m-%d') + datetime.timedelta(
                    hours=6)
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(date_obj).split('-')[0]):
                    get_sequence = "/".join(split_seq)

                    # region year wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if self._sequence_matches_date(split_inv_name, date_obj, get_year_index): #and not inv_name.startswith(without_last_index_sequence):
                        orginal_sequence = inv_name.split('/')
                    else:
                        get_highest_sequence_no = common_method.get_highest_seq_no(
                            get_sequence_object,
                            date_obj, model)
                        # get_highest_sequence_no = self.env['account.move'].search(
                        #     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="sequence_number desc",
                        #     limit=1).sequence_number
                        if len(str(get_highest_sequence_no))>5:
                            number=get_highest_sequence_no+1
                            string_convert=str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            number = (get_highest_sequence_no + 1) / 100000
                            dec_string = str(round(Decimal(number), 5))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert

                    get_sequence = "/".join(orginal_sequence)
                    # endregion

            if 'invoice_date' not in vals_list.keys() and not isinstance(self.invoice_date,
                                                                         bool):
                date_obj = self.invoice_date + datetime.timedelta(hours=6)
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(date_obj).split('-')[0]):
                    get_sequence = "/".join(split_seq)

                    # region year wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    #if str(date_obj.year) == split_inv_name[get_year_index]: #and not inv_name.startswith(without_last_index_sequence):
                    #    orginal_sequence = inv_name.split('/')
                    if (split_inv_name and isinstance(get_year_index, int) and get_year_index < len(split_inv_name) and str(date_obj.year) == split_inv_name[get_year_index]):
                        orginal_sequence = inv_name.split('/')
                    else:
                        get_highest_sequence_no = common_method.get_highest_seq_no(
                            get_sequence_object,
                            date_obj, model)
                        # get_highest_sequence_no = self.env['account.move'].search(
                        #     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="sequence_number desc",
                        #     limit=1).sequence_number
                        sequence_padding = get_sequence_object.padding
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            common='1'
                            divide_by=int(common.ljust(sequence_padding+1,'0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert
                    get_sequence = "/".join(orginal_sequence)
                    # endregion

            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool) and self.move_type=='entry':
                date_obj = datetime.datetime.strptime(str(vals_list['date']), '%Y-%m-%d') + datetime.timedelta(hours=6)
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(date_obj).split('-')[0]):
                    get_sequence = "/".join(split_seq)

                    # region year wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if self._sequence_matches_date(split_inv_name, date_obj, get_year_index): #and not inv_name.startswith(without_last_index_sequence):
                        orginal_sequence = inv_name.split('/')
                    else:
                        get_highest_sequence_no = common_method.get_highest_seq_no(get_sequence_object,date_obj, model)
                        # get_highest_sequence_no = self.env['account.move'].search(
                        #     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="sequence_number desc",
                        #     limit=1).sequence_number
                        if len(str(get_highest_sequence_no))>5:
                            number=get_highest_sequence_no+1
                            string_convert=str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            number = (get_highest_sequence_no + 1) / 100000
                            dec_string = str(round(Decimal(number), 5))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert

                    get_sequence = "/".join(orginal_sequence)
                    # endregion
            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(month)s/' in get_sequence_object.prefix:
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_inv and get_highest_inv.name!='/':
                    split_highest_inv=get_highest_inv.name.split('/')
                    get_sequence_object.number_next_actual=int(split_highest_inv[-1])
            else:
                split_seq = get_sequence.split('/')
            if 'invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'],
                                                                     bool):
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(vals_list['invoice_date']).split('-')[1]):
                    get_sequence = "/".join(split_seq)
            if 'invoice_date' not in vals_list.keys() and not isinstance(self.invoice_date,
                                                                     bool):

                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(self.invoice_date).split('-')[1]):
                    get_sequence = "/".join(split_seq)

            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool) and self.move_type=="entry":
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(vals_list['date']).split('-')[1]):
                    get_sequence = "/".join(split_seq)
            return get_sequence


        else:
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                get_sequence = "/".join(split_seq)
                if get_highest_inv and get_highest_inv.name!='/':
                    split_highest_inv=get_highest_inv.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                get_sequence = "/".join(split_seq)
            return get_sequence


    def _get_sequence_for_date(self,get_sequence_object,get_sequence,inv_name,vals_list,get_highest_inv):
        common_method = self.env['common.method']
        model = 'account.move'
        if '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='month_year':
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_inv and get_highest_inv.name!='/':
                    split_highest_inv=get_highest_inv.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                # split_highest_inv = get_highest_inv.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool):
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(vals_list['date']).split('-')[0]):
                    get_sequence = "/".join(split_seq)
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(vals_list['date']).split('-')[1]):
                    get_sequence = "/".join(split_seq)
            if 'date' not in vals_list.keys() and not isinstance(self.date,
                                                                     bool):
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(self.date).split('-')[0]):
                    get_sequence = "/".join(split_seq)
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(self.date).split('-')[1]):
                    get_sequence = "/".join(split_seq)
            return get_sequence

        elif '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='month_year_monthly':
            split_seq_obj = get_sequence_object.prefix.split('/')
            get_year_index = split_seq_obj.index('%(year)s')
            get_month_index = split_seq_obj.index('%(month)s')
            split_inv_name = []
            for i in range(get_year_index + 3):
                split_inv_name.append('')
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_inv and get_highest_inv.name!='/':
                    split_highest_inv=get_highest_inv.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
                # split_highest_inv = get_highest_inv.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool):
                date_obj = datetime.datetime.strptime(str(vals_list['date']), '%Y-%m-%d') + datetime.timedelta(hours=6)
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(date_obj).split('-')[0]):
                    get_sequence = "/".join(split_seq)
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(date_obj).split('-')[1]):
                    get_sequence = "/".join(split_seq)

                    # region Month wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if self._sequence_matches_date(split_inv_name, date_obj, get_year_index, get_month_index):
                        orginal_sequence = inv_name.split('/')
                    else:
                        get_highest_sequence_no = common_method.get_highest_seq_no_month_year_monthly(get_sequence_object,
                                                                                   date_obj, model)
                        # get_highest_sequence_no = self.env['account.move'].search(
                        #     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="sequence_number desc",
                        #     limit=1).sequence_number

                        sequence_padding = get_sequence_object.padding
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            common='1'
                            divide_by=int(common.ljust(sequence_padding+1,'0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert
                    get_sequence = "/".join(orginal_sequence)
                    # endregion
            if 'date' not in vals_list.keys() and not isinstance(self.date,
                                                                     bool):
                date_obj = self.date + datetime.timedelta(hours=6)
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(date_obj).split('-')[0]):
                    get_sequence = "/".join(split_seq)
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(date_obj).split('-')[1]):
                    get_sequence = "/".join(split_seq)

                    # region Month wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if self._sequence_matches_date(split_inv_name, date_obj, get_year_index, get_month_index):
                        orginal_sequence = inv_name.split('/')
                    else:
                        get_highest_sequence_no = common_method.get_highest_seq_no_month_year_monthly(get_sequence_object,
                                                                                   date_obj, model)
                        # get_highest_sequence_no = self.env['account.move'].search(
                        #     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="sequence_number desc",
                        #     limit=1).sequence_number

                        sequence_padding = get_sequence_object.padding
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            common='1'
                            divide_by=int(common.ljust(sequence_padding+1,'0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert
                    get_sequence = "/".join(orginal_sequence)
                    # endregion
            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='year':
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_inv and get_highest_inv.name!='/':
                    split_highest_inv=get_highest_inv.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool):
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(vals_list['date']).split('-')[0]):
                    get_sequence = "/".join(split_seq)
            if 'date' not in vals_list.keys() and not isinstance(self.date,
                                                                     bool):
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(self.date).split('-')[0]):
                    get_sequence = "/".join(split_seq)
            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='year_yearly':
            # split_inv_name = ['', '', '', ''] if inv_name == '' else inv_name.split('/')
            split_seq_obj = get_sequence_object.prefix.split('/')
            get_year_index = split_seq_obj.index('%(year)s')
            split_inv_name = []
            for i in range(get_year_index + 1):
                split_inv_name.append('')
            split_inv_name.append('')
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_inv and get_highest_inv.name!='/':
                    split_highest_inv=get_highest_inv.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool):
                date_obj = datetime.datetime.strptime(str(vals_list['date']), '%Y-%m-%d') + datetime.timedelta(hours=6)
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(date_obj).split('-')[0]):
                    get_sequence = "/".join(split_seq)

                    # region year wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if self._sequence_matches_date(split_inv_name, date_obj, get_year_index):
                        orginal_sequence = inv_name.split('/')

                    else:
                        get_highest_sequence_no = common_method.get_highest_seq_no(
                            get_sequence_object,
                            date_obj, model)
                        # get_highest_sequence_no = self.env['account.move'].search(
                        #     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="sequence_number desc",
                        #     limit=1).sequence_number
                        sequence_padding = get_sequence_object.padding
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            common='1'
                            divide_by=int(common.ljust(sequence_padding+1,'0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert
                    get_sequence = "/".join(orginal_sequence)
                    # endregion
            # if 'date' not in vals_list.keys() and not isinstance(self.date,
            #                                                          bool):
            #     if get_sequence.find(str(datetime.datetime.now().year)) > -1:
            #         idx = split_seq.index(str(datetime.datetime.now().year))
            #         split_seq[idx] = str(self.date).split('-')[0]
            #         get_sequence = "/".join(split_seq)
            if 'date' not in vals_list.keys() and not isinstance(self.date,
                                                                         bool):
                date_obj = self.date + datetime.timedelta(hours=6)
                if self._set_sequence_component(get_sequence_object, split_seq, 'year', str(date_obj).split('-')[0]):
                    get_sequence = "/".join(split_seq)

                    # region year wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if self._sequence_matches_date(split_inv_name, date_obj, get_year_index):
                        orginal_sequence = inv_name.split('/')
                    else:
                        get_highest_sequence_no = common_method.get_highest_seq_no(
                            get_sequence_object,
                            date_obj, model)
                        # get_highest_sequence_no = self.env['account.move'].search(
                        #     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="sequence_number desc",
                        #     limit=1).sequence_number
                        sequence_padding = get_sequence_object.padding
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            common='1'
                            divide_by=int(common.ljust(sequence_padding+1,'0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert
                    get_sequence = "/".join(orginal_sequence)
            return get_sequence


        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(month)s/' in get_sequence_object.prefix:
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_inv and get_highest_inv.name!='/':
                    split_highest_inv=get_highest_inv.name.split('/')
                    get_sequence_object.number_next_actual=int(split_highest_inv[-1])-1
            else:
                split_seq = get_sequence.split('/')
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool):
                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(vals_list['date']).split('-')[1]):
                    get_sequence = "/".join(split_seq)
            if 'date' not in vals_list.keys() and not isinstance(self.date,
                                                                     bool):

                if self._set_sequence_component(get_sequence_object, split_seq, 'month', str(self.date).split('-')[1]):
                    get_sequence = "/".join(split_seq)
            return get_sequence

        else:
            if inv_name != '':
                split_inv_name = inv_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                get_sequence = "/".join(split_seq)
                if get_highest_inv and get_highest_inv.name!='/':
                    split_highest_inv=get_highest_inv.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                get_sequence = "/".join(split_seq)
            return get_sequence

    @api.model
    def create(self, vals_list):
        if 'name' in vals_list.keys() and vals_list.get('name') not in ('/','DRAFT','draft','Draft','NEW','new','New'):
            return super(AccountMoveInheritance, self).create(vals_list)
        res=super(AccountMoveInheritance, self).create(vals_list)
        company_id = self.env.company.id
        inv_name=''        
        if res.move_type=='out_invoice':
            get_sequence_object = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'sale_invoice'), ('company_id', 'in', [company_id, False])],
                limit=1, )
            if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                inv_name = res.name
            if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                inv_name = ''


            get_sequence = self.env['ir.sequence'].next_by_sequence_for('sale_invoice')

            if get_sequence:
                get_highest_inv=self.env['account.move'].search([('move_type','=','out_invoice'),('company_id','=',self.env.company.id)],limit=1,order='id desc')
                get_sequence=res._get_sequence(get_sequence_object,get_sequence,inv_name,vals_list,get_highest_inv)
            if not get_sequence:
                raise ValidationError(_("Sequence is not set for Invoice"))
            res.name = get_sequence or _('/')
            if res._cpabooks_posted_name_conflict():
                next_name = res._cpabooks_next_sale_invoice_name(res.invoice_date)
                if next_name:
                    parts = next_name.split('/')
                    res.write({
                        'name': next_name,
                        'sequence_number': parts[-1],
                        'sequence_prefix': '/'.join(parts[:-1]) + '/',
                    })

        if res.move_type=='out_refund':
            # get_sequence = self.env['ir.sequence'].next_by_sequence_for('credit_note')
            # split_seq=get_sequence.split('/')
            # if 'invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'],bool) and get_sequence.find(str(datetime.datetime.now().year))>-1:
            #     idx=split_seq.index(str(datetime.datetime.now().year))
            #     split_seq[idx]=str(vals_list['invoice_date']).split('-')[0]
            #     get_sequence="/".join(split_seq)
            get_sequence_object = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'credit_note'), ('company_id', 'in', [company_id, False])],
                limit=1, )
            if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                inv_name = res.name
            if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                inv_name = ''
            get_sequence = self.env['ir.sequence'].next_by_sequence_for('credit_note')

            if get_sequence:
                get_highest_inv = self.env['account.move'].search([('move_type', '=', 'out_refund'),('company_id','=',self.env.company.id)], limit=1,
                                                                         order='id desc')
                get_sequence = res._get_sequence(get_sequence_object, get_sequence, inv_name, vals_list,
                                                 get_highest_inv)


            if not get_sequence:
                raise ValidationError(_("Sequence is not set for credit note"))
            res.name=get_sequence or _('/')

        if res.move_type=='in_invoice':
            get_sequence_object = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'purchase_bill'), ('company_id', 'in', [company_id, False])],
                limit=1, )
            if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                inv_name = res.name
            if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                inv_name = ''
            get_sequence = self.env['ir.sequence'].next_by_sequence_for('purchase_bill')
            if get_sequence:
                get_highest_inv = self.env['account.move'].search([('move_type', '=', 'in_invoice'),('company_id','=',self.env.company.id)], limit=1,
                                                                         order='id desc')
                get_sequence = res._get_sequence(get_sequence_object,get_sequence,inv_name,vals_list,get_highest_inv)
            # split_seq = get_sequence.split('/')
            # if 'invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'],bool) and get_sequence.find(str(datetime.datetime.now().year)) > -1:
            #     idx = split_seq.index(str(datetime.datetime.now().year))
            #     split_seq[idx] = str(vals_list['invoice_date']).split('-')[0]
            #     get_sequence = "/".join(split_seq)
            if not get_sequence:
                raise ValidationError(_("Sequence is not set for Bill"))
            res.name=get_sequence or _('/')

        if res.move_type=='in_refund':
            # get_sequence = self.env['ir.sequence'].next_by_sequence_for('debit_note')
            # split_seq = get_sequence.split('/')
            # if 'invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'],bool) and get_sequence.find(str(datetime.datetime.now().year)) > -1:
            #     idx = split_seq.index(str(datetime.datetime.now().year))
            #     split_seq[idx] = str(vals_list['invoice_date']).split('-')[0]
            #     get_sequence = "/".join(split_seq)
            get_sequence_object = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'debit_note'), ('company_id', 'in', [company_id, False])],
                limit=1, )
            if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                inv_name = res.name
            if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                inv_name = ''
            get_sequence = self.env['ir.sequence'].next_by_sequence_for('debit_note')

            if get_sequence:
                get_highest_inv = self.env['account.move'].search([('move_type', '=', 'in_refund'),('company_id','=',self.env.company.id)], limit=1,
                                                                         order='id desc')
                get_sequence = res._get_sequence(get_sequence_object, get_sequence, inv_name, vals_list,
                                                 get_highest_inv)


            if not get_sequence:
                raise ValidationError(_("Sequence is not set for debit note"))
            res.name=get_sequence or _('/')

        if res.move_type=='entry' and not res.payment_id and not self._context.get('skip_payment_move_sequence'):
            get_sequence_object = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'journal_voucher'), ('company_id', 'in', [company_id, False])],
                limit=1, )
            if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                inv_name = res.name
            if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                inv_name = ''
            # next_number = self.get_next_number(res.date)
            get_sequence = self.env['ir.sequence'].next_by_sequence_for(sequence_for='journal_voucher', sequence_date=res.date)

            if get_sequence:
                get_highest_inv = self.env['account.move'].search([('move_type', '=', 'entry'),('company_id','=',self.env.company.id)], limit=1,
                                                                         order='id desc')
                get_sequence = res._get_sequence(get_sequence_object, get_sequence, inv_name, vals_list,
                                                 get_highest_inv)
            # get_sequence = self.env['ir.sequence'].next_by_sequence_for('journal_voucher')
            # split_seq = get_sequence.split('/')
            # if 'invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'],bool) and get_sequence.find(str(datetime.datetime.now().year)) > -1:
            #     idx = split_seq.index(str(datetime.datetime.now().year))
            #     split_seq[idx] = str(vals_list['invoice_date']).split('-')[0]
            #     get_sequence = "/".join(split_seq)
            if not get_sequence and res.journal_id.type not in ('bank','cash'):
                raise ValidationError(_("Sequence is not set for Journal Voucher Entry"))
            res.name=get_sequence or _('/')
            if res._cpabooks_posted_name_conflict():
                res._cpabooks_resolve_posted_name_conflict()

        return res


    # @api.model
    def write(self, vals_list):
        vals_list = dict(vals_list)
        preserve_posted_entry_name = bool(
            len(self) == 1
            and self.state == 'posted'
            and self.move_type == 'entry'
            and not self._is_sequence_placeholder_name(self.name)
            and 'name' not in vals_list
        )
        if (
            self.env.context.get('skip_duplicate_source_name_restore')
            and len(self) == 1
            and set(vals_list.keys()) <= {'name', 'sequence_number', 'sequence_prefix'}
            and self.state == 'draft'
            and self.move_type in (
                'out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'entry',
            )
            and not self._is_sequence_placeholder_name(self.name)
            and vals_list.get('name', self.name) != self.name
        ):
            return super(AccountMoveInheritance, self).write(vals_list)
        sale_invoice_name_prepared = False
        journal_voucher_name_prepared = False
        payment_move_name_prepared = False

        if (
            len(self) == 1
            and self.move_type == 'out_invoice'
            and 'invoice_date' in vals_list
            and not isinstance(vals_list.get('invoice_date'), bool)
            and 'name' not in vals_list
        ):
            prepared_name = self._get_sale_invoice_backdated_sequence_name(vals_list.get('invoice_date'))
            if prepared_name:
                vals_list['name'] = prepared_name
                sale_invoice_name_prepared = True

        if (
            len(self) == 1
            and not preserve_posted_entry_name
            and self.move_type == 'entry'
            and not self.payment_id
            and 'date' in vals_list
            and not isinstance(vals_list.get('date'), bool)
            and 'name' not in vals_list
        ):
            prepared_name = self._get_journal_voucher_backdated_sequence_name(vals_list.get('date'))
            if prepared_name:
                vals_list['name'] = prepared_name
                journal_voucher_name_prepared = True

        if (
            len(self) == 1
            and not preserve_posted_entry_name
            and 'date' in vals_list
            and not isinstance(vals_list.get('date'), bool)
            and 'name' not in vals_list
            and self.payment_id
        ):
            payment = self.payment_id
            sequence_date = vals_list.get('date') or self.date
            sequence_for = payment._get_payment_sequence_code()
            prepared_name = payment._get_backdated_sequence_name(sequence_for, sequence_date) if sequence_for else False
            if prepared_name:
                vals_list = dict(vals_list, name=prepared_name)
                payment_move_name_prepared = True

        rec = super(AccountMoveInheritance, self).write(vals_list)
        if preserve_posted_entry_name:
            return rec
        # ESD / billing-scope writes must not assign document numbers.
        if set(vals_list) <= {'esd_payment_date', 'esd_amount', 'cpabooks_billing_scope_id'}:
            return rec
        # if 'name' in vals_list.keys():
        # self_name = self.name.split('/')
        # vals_name = vals_list['name'].split('/')
        # if self_name[0]!=vals_name[0] and self_name[1]!=vals_name[1] and self_name[2]!=vals_name[2]:
        company_id = self.env.company.id
        for res in self:
            name_val = vals_list.get('name')
            if name_val and isinstance(name_val, str):
                get_number=name_val.split('/')
                res.sequence_number=get_number[-1]
                res.sequence_prefix='/'.join(get_number[:-1]) + '/'
            inv_name=''
            move_name = res.name if isinstance(res.name, str) else ''

            # or (res.name == '/' and not isinstance(res.invoice_date, bool))
            if ('invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'], bool) and res.move_type in ('out_invoice','out_refund','in_invoice','in_refund')) or (move_name == '/' or move_name.upper() == 'DRAFT' or move_name.upper() == 'NEW'):
                    if res.move_type=='out_invoice':
                        if sale_invoice_name_prepared:
                            continue
                        get_sequence_object = self.env['ir.sequence'].sudo().search(
                            [('sequence_for', '=', 'sale_invoice'), ('company_id', 'in', [company_id, False])],
                            limit=1, )
                        if (res.name!='/' or (res.name or '').upper()!='DRAFT' or (res.name or '').upper()!='NEW') or ((res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW') and res.data_from_excel==False):
                            inv_name=res.name
                        elif res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                            # inv_name = ''
                            inv_name = ''


                        if inv_name!='':
                            get_sequence = self.env['ir.sequence'].next_by_sequence_for('sale_invoice','no')

                            if get_sequence:
                                get_highest_inv = self.env['account.move'].search([('move_type', '=', 'out_invoice'),('company_id','=',self.env.company.id)],
                                                                                         limit=1,
                                                                                         order='id desc')
                                get_sequence = res._get_sequence(get_sequence_object, get_sequence, inv_name, vals_list,
                                                                 get_highest_inv)



                            if not get_sequence:
                                raise ValidationError(_("Sequence is not set for Invoice"))
                            res.name=get_sequence or _('/')

                    if res.move_type == 'out_refund':
                        get_sequence_object = self.env['ir.sequence'].sudo().search(
                            [('sequence_for', '=', 'credit_note'), ('company_id', 'in', [company_id, False])],
                            limit=1, )
                        if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                            inv_name = res.name
                        if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                            inv_name = ''

                        if inv_name != '':
                            get_sequence = self.env['ir.sequence'].next_by_sequence_for('credit_note')

                            if get_sequence:
                                get_highest_inv = self.env['account.move'].search([('move_type', '=', 'out_refund'),('company_id','=',self.env.company.id)],
                                                                                         limit=1,
                                                                                         order='id desc')
                                get_sequence = res._get_sequence(get_sequence_object, get_sequence, inv_name, vals_list,
                                                                 get_highest_inv)


                            if not get_sequence:
                                raise ValidationError(_("Sequence is not set for credit note"))
                            res.name = get_sequence or _('/')

                    if res.move_type=='in_invoice':
                        get_sequence_object = self.env['ir.sequence'].sudo().search(
                            [('sequence_for', '=', 'purchase_bill'), ('company_id', 'in', [company_id, False])],
                            limit=1, )
                        if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                            inv_name = res.name
                        if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                            inv_name = ''

                        if inv_name != '':
                            get_sequence = self.env['ir.sequence'].next_by_sequence_for('purchase_bill')
                            if get_sequence:
                                get_highest_inv = self.env['account.move'].search([('move_type', '=', 'in_invoice'),('company_id','=',self.env.company.id)],
                                                                                         limit=1,
                                                                                         order='id desc')
                                get_sequence = res._get_sequence(get_sequence_object, get_sequence, inv_name, vals_list,
                                                                 get_highest_inv)
                            if not get_sequence:
                                raise ValidationError(_("Sequence is not set for Bill"))
                            res.name = get_sequence or _('/')

                    if res.move_type == 'in_refund':
                        get_sequence_object = self.env['ir.sequence'].sudo().search(
                            [('sequence_for', '=', 'debit_note'), ('company_id', 'in', [company_id, False])],
                            limit=1, )
                        if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                            inv_name = res.name
                        if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                            inv_name = ''

                        if inv_name != '':
                            get_sequence = self.env['ir.sequence'].next_by_sequence_for('debit_note')

                            if get_sequence:
                                get_highest_inv = self.env['account.move'].search([('move_type', '=', 'in_refund'),('company_id','=',self.env.company.id)], limit=1,
                                                                                         order='id desc')
                                get_sequence = res._get_sequence(get_sequence_object, get_sequence, inv_name, vals_list,
                                                                 get_highest_inv)


                            if not get_sequence:
                                raise ValidationError(_("Sequence is not set for debit note"))
                            res.name = get_sequence or _('/')

                    if res.move_type=='entry' and not res.payment_id:
                        if journal_voucher_name_prepared:
                            continue
                        get_sequence_object = self.env['ir.sequence'].sudo().search(
                            [('sequence_for', '=', 'journal_voucher'), ('company_id', 'in', [company_id, False])],
                            limit=1, )
                        if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                            inv_name = res.name
                        if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                            inv_name = ''

                        if inv_name != '':
                            field_date = vals_list.get('date')
                            # next_number = self.get_next_number(field_date)
                            get_sequence = self.env['ir.sequence'].next_by_sequence_for(sequence_for='journal_voucher', sequence_date=field_date)

                            if get_sequence:
                                get_highest_inv = self.env['account.move'].search(
                                    [('move_type', '=', 'entry'),('company_id','=',self.env.company.id)], limit=1,
                                    order='id desc')
                                get_sequence = res._get_sequence(get_sequence_object, get_sequence, inv_name, vals_list,
                                                                 get_highest_inv)

                            if not get_sequence and res.journal_id.type not in ('bank', 'cash'):
                                raise ValidationError(_("Sequence is not set for Journal Voucher Entry"))
                            res.name = get_sequence or _('/')


                    return rec
            # or (res.name == '/' and not isinstance(res.date, bool))
            elif 'date' in vals_list.keys() and not isinstance(vals_list['date'], bool) and  res.move_type=='entry':
                if payment_move_name_prepared and res.payment_id:
                    continue
                # if ('date' in vals_list.keys() and not str(vals_list['date']).find(str(datetime.datetime.now().year))>-1) or res.name.find(str(datetime.datetime.now().year))==-1:
                if res.move_type == 'out_invoice':
                    get_sequence_object = self.env['ir.sequence'].sudo().search(
                        [('sequence_for', '=', 'sale_invoice'), ('company_id', 'in', [company_id, False])],
                        limit=1, )
                    if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                        inv_name = res.name
                    if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                        inv_name = ''

                    if inv_name != '':
                        if get_sequence_object.sequence_pattern=='month_year_monthly':
                            get_sequence = self.env['ir.sequence'].next_by_sequence_for('sale_invoice')
                            get_sequence_object.number_next_actual= get_sequence_object.number_next_actual-1
                        else:
                            get_sequence = self.env['ir.sequence'].next_by_sequence_for('sale_invoice')
                            get_sequence_object.number_next_actual = get_sequence_object.number_next_actual + 1
                        if get_sequence:
                            get_highest_inv = self.env['account.move'].search(
                                [('move_type', '=', 'out_invoice'),('company_id','=',self.env.company.id)],
                                limit=1,
                                order='id desc')
                            get_sequence = res._get_sequence_for_date(get_sequence_object, get_sequence, inv_name, vals_list,
                                                             get_highest_inv)

                        if not get_sequence:
                            raise ValidationError(_("Sequence is not set for Invoice"))
                        res.name = get_sequence or _('/')

                if res.move_type == 'out_refund':
                    get_sequence_object = self.env['ir.sequence'].sudo().search(
                        [('sequence_for', '=', 'credit_note'), ('company_id', 'in', [company_id, False])],
                        limit=1, )
                    if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                        inv_name = res.name
                    if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                        inv_name = ''

                    if inv_name != '':
                        get_sequence = self.env['ir.sequence'].next_by_sequence_for('credit_note')

                        if get_sequence:
                            get_highest_inv = self.env['account.move'].search([('move_type', '=', 'out_refund'),('company_id','=',self.env.company.id)],
                                                                                     limit=1,
                                                                                     order='id desc')
                            get_sequence = res._get_sequence_for_date(get_sequence_object, get_sequence, inv_name, vals_list,
                                                             get_highest_inv)

                        if not get_sequence:
                            raise ValidationError(_("Sequence is not set for credit note"))
                        res.name = get_sequence or _('/')

                if res.move_type == 'in_invoice':
                    get_sequence_object = self.env['ir.sequence'].sudo().search(
                        [('sequence_for', '=', 'purchase_bill'), ('company_id', 'in', [company_id, False])],
                        limit=1, )
                    if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                        inv_name = res.name
                    if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                        inv_name = ''

                    if inv_name != '':
                        get_sequence = self.env['ir.sequence'].next_by_sequence_for('purchase_bill')
                        if get_sequence:
                            get_highest_inv = self.env['account.move'].search([('move_type', '=', 'in_invoice'),('company_id','=',self.env.company.id)],
                                                                                     limit=1,
                                                                                     order='id desc')
                            get_sequence = res._get_sequence_for_date(get_sequence_object, get_sequence, inv_name, vals_list,
                                                             get_highest_inv)
                        if not get_sequence:
                            raise ValidationError(_("Sequence is not set for Bill"))
                        res.name = get_sequence or _('/')

                if res.move_type == 'in_refund':
                    # get_sequence = self.env['ir.sequence'].next_by_sequence_for('debit_note')
                    # split_seq = get_sequence.split('/')
                    # if 'invoice_date' in vals_list.keys() and not isinstance(vals_list['invoice_date'],bool) and get_sequence.find(str(datetime.datetime.now().year)) > -1:
                    #     idx = split_seq.index(str(datetime.datetime.now().year))
                    #     split_seq[idx] = str(vals_list['invoice_date']).split('-')[0]
                    #     get_sequence = "/".join(split_seq)
                    get_sequence_object = self.env['ir.sequence'].sudo().search(
                        [('sequence_for', '=', 'debit_note'), ('company_id', 'in', [company_id, False])],
                        limit=1, )
                    if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                        inv_name = res.name
                    if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                        inv_name = ''

                    if inv_name != '':
                        get_sequence = self.env['ir.sequence'].next_by_sequence_for('debit_note')

                        if get_sequence:
                            get_highest_inv = self.env['account.move'].search([('move_type', '=', 'in_refund'),('company_id','=',self.env.company.id)],
                                                                                     limit=1,
                                                                                     order='id desc')
                            get_sequence = res._get_sequence_for_date(get_sequence_object, get_sequence, inv_name, vals_list,
                                                             get_highest_inv)

                        if not get_sequence:
                            raise ValidationError(_("Sequence is not set for debit note"))
                        res.name = get_sequence or _('/')

                if res.move_type == 'entry' and not res.payment_id:
                    get_sequence_object = self.env['ir.sequence'].sudo().search(
                        [('sequence_for', '=', 'journal_voucher'), ('company_id', 'in', [company_id, False])],
                        limit=1, )
                    if res.name != '/' or (res.name or '').upper() != 'DRAFT' or (res.name or '').upper() != 'NEW':
                        inv_name = res.name
                    if res.name == '/' or (res.name or '').upper() == 'DRAFT' or (res.name or '').upper() == 'NEW':
                        inv_name = ''

                    if inv_name != '':
                        get_sequence = self.env['ir.sequence'].next_by_sequence_for('journal_voucher')

                        if get_sequence:
                            get_highest_inv = self.env['account.move'].search(
                                [('move_type', '=', 'entry'),('company_id','=',self.env.company.id)], limit=1,
                                order='id desc')
                            get_sequence = res._get_sequence_for_date(get_sequence_object, get_sequence, inv_name, vals_list,
                                                             get_highest_inv)

                        if not get_sequence and res.journal_id.type not in ('bank', 'cash'):
                            raise ValidationError(_("Sequence is not set for Journal Voucher Entry"))
                        res.name = get_sequence or _('/')
                return rec
        return rec
    
    def action_post(self):
        for rec in self:
            if rec.data_from_excel:
                rec.data_from_excel = False
            if rec.move_type == 'out_invoice' and rec._cpabooks_posted_name_conflict():
                next_name = rec._cpabooks_next_available_move_name()
                if not next_name:
                    next_name = rec._cpabooks_next_sale_invoice_name()
                if next_name:
                    parts = next_name.split('/')
                    rec.with_context(skip_duplicate_source_name_restore=True).write({
                        'name': next_name,
                        'sequence_number': parts[-1],
                        'sequence_prefix': '/'.join(parts[:-1]) + '/',
                    })
            elif (
                rec.move_type == 'entry'
                and not rec.payment_id
                and rec._cpabooks_posted_name_conflict()
            ):
                while rec._cpabooks_posted_name_conflict():
                    if not rec._cpabooks_resolve_posted_name_conflict():
                        break
        return super(AccountMoveInheritance, self).action_post()

    # @api.constrains('name')
    # def _check_unique_name(self):
    #     for rec in self:
    #         existing = self.search([('name', '=ilike', rec.name), ('id', '!=', rec.id)])
    #         if existing:
    #             raise ValidationError("The name must be unique!")


    # def get_next_number(self, field_date=False, sequence_for=False):
    #     if not sequence_for:
    #         sequence_for = 'journal_voucher'
    #     sequence_id = self.env['ir.sequence'].search([
    #         ('company_id', '=', self.env.company.id),
    #         ('sequence_for', '=', sequence_for)
    #     ], limit=1)
    #     prefix = sequence_id.prefix
    #     print(prefix)
    #     if not field_date:
    #         field_date = datetime.date.today()
    #     if isinstance(field_date, str):
    #         try:
    #             # Handle both formats: YYYY-MM-DD and DD/MM/YYYY
    #             if "-" in field_date:
    #                 date_obj = datetime.datetime.strptime(field_date, "%Y-%m-%d")
    #             else:
    #                 date_obj = datetime.datetime.strptime(field_date, "%d/%m/%Y")
    #         except ValueError:
    #             raise ValueError(f"Invalid date format: {field_date}. Expected formats: 'YYYY-MM-DD' or 'DD/MM/YYYY'.")
    #     else:
    #         # If already a `date` object, no need to parse
    #         date_obj = field_date
    #
    #     # Extract day, month, and year
    #     day = date_obj.day
    #     month = date_obj.month
    #     year = date_obj.year
    #     vals = ''
    #     if '%(year)s/' in prefix:
    #         vals = self.search([
    #             ('company_id', '=', self.env.company.id),
    #             ('name', 'ilike', f'{year}/')
    #         ])
    #     if '%(year)s' and '%(month)s' in prefix:
    #         vals = self.search([
    #             ('company_id', '=', self.env.company.id),
    #             ('name', 'ilike', f'{year}/{month:02d}')
    #         ])
    #     numbers =[val.name.split('/')[-1] for val in vals]
    #     names =[val.name for val in vals]
    #     print(numbers)
    #     print(names)
    #     int_num = [int(num) for num in numbers]
    #     print(f'int num jounral_voucher')
    #     largest_number = 0
    #     if int_num:
    #         largest_number = max(int_num)
    #     print(largest_number)
    #     return largest_number + 1



