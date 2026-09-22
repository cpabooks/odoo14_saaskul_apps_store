from datetime import datetime, timedelta, date
from decimal import Decimal

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class SaleOrderInheritance(models.Model):
    _inherit = 'sale.order'

    def _cpabooks_sequence_year_str(self, date_val, company=None):
        """Year segment for document names (2- or 4-digit per company setting)."""
        from odoo.addons.cpabooks_sequences.models.sequence_format import format_year
        company = company or self.env.company
        digits = getattr(company, 'cpabooks_sequence_year_digits', None) or '4'
        if isinstance(date_val, datetime):
            year = date_val.year
        elif isinstance(date_val, date):
            year = date_val.year
        elif isinstance(date_val, str):
            parsed = fields.Datetime.to_datetime(date_val)
            year = parsed.year
        else:
            year = datetime.now().year
        return format_year(year, digits)

    # name = fields.Char(string='Order Reference', required=True, copy=False, readonly=True,
    #                    states={'draft': [('readonly', False)]}, index=True, default=lambda self: _('New'))
    name = fields.Char(string='Order Reference', required=True, copy=False, readonly=True,
                       states={'draft': [('readonly', False)]}, index=True, default=lambda self: _('Draft'))
    system_admin = fields.Boolean(compute="_get_system_admin")

    def _cpabooks_is_placeholder_sale_name(self, name):
        return not name or name == '/' or str(name).upper() in ('DRAFT', 'NEW')

    def _cpabooks_sale_name_exists(self, name, company, exclude_order=False):
        if self._cpabooks_is_placeholder_sale_name(name):
            return False
        domain = [('name', '=', name)]
        if company:
            domain.append(('company_id', '=', company.id))
        if exclude_order:
            domain.append(('id', '!=', exclude_order.id))
        return bool(self.sudo().search(domain, limit=1))

    def _cpabooks_make_unique_sale_name(self, name, company, exclude_order=False):
        if not self._cpabooks_sale_name_exists(name, company, exclude_order=exclude_order):
            return name

        parts = name.rsplit('/', 1)
        if len(parts) == 2 and parts[1].isdigit():
            prefix, serial = parts
            max_serial = int(serial)
            domain = [
                ('name', '=like', prefix + '/%'),
                ('name', 'not like', '%-R%'),
            ]
            if company:
                domain.append(('company_id', '=', company.id))
            existing_orders = self.sudo().search(domain)
            for order in existing_orders:
                current_serial = order.name.rsplit('/', 1)[-1]
                if current_serial.isdigit():
                    max_serial = max(max_serial, int(current_serial))
            return '%s/%s' % (prefix, str(max_serial + 1).zfill(len(serial)))

        suffix = 2
        while self._cpabooks_sale_name_exists('%s-%s' % (name, suffix), company, exclude_order=exclude_order):
            suffix += 1
        return '%s-%s' % (name, suffix)

    @api.constrains('name', 'company_id')
    def _check_order_name_company_id(self):
        for order in self:
            if order._cpabooks_is_placeholder_sale_name(order.name):
                continue
            company_id = order.company_id
            get_name_existency = self.env['sale.order'].sudo().search(
                [('name', '=', order.name), ('company_id', '=', company_id.id), ('id', '!=', order.id)])
            if get_name_existency:
                raise ValidationError(_("Duplicate serial is not acceptable, Please change the serial"))

    def _prepare_confirmation_values(self):
        return {
            'state': 'sale'
        }

    # @api.depends('state')
    # def _get_system_admin(self):
    #     for rec in self:
    #         # get_admin_power_group = self.env['res.groups'].sudo().search([('name', '=ilike', 'Admin Power')])
    #         # if get_admin_power_group:
    #         #     if self.env.user.has_group('base.group_system') or self.env.user.id in get_admin_power_group.users.ids:
    #         #         rec.system_admin = True
    #         #     else:
    #         #         rec.system_admin = False
    #         # else:
    #         #     if self.env.user.has_group('base.group_system'):
    #         #         rec.system_admin = True
    #         #     else:
    #         #         rec.system_admin = False
    #         if self.env.user.has_group('base.group_system'):
    #             rec.system_admin = True
    #         else:
    #             rec.system_admin = False

    # @api.constrains('name')
    # def _check_unique_name(self):
    #     for rec in self:
    #         existing = self.search([('name', '=ilike', rec.name), ('id', '!=', rec.id)])
    #         if existing:
    #             raise ValidationError("The name must be unique!")

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

    def _prepare_invoice(self):
        res = super(SaleOrderInheritance, self)._prepare_invoice()
        res['invoice_date'] = datetime.now().date()
        return res

    @api.model
    def create(self, vals_list):
        revise = False
        if vals_list.get('revise') == True:
            revise = True
            vals_list.pop('revise')
        res = super(SaleOrderInheritance, self).create(vals_list)
        company_id = self.env.company.id
        sale_name = ''
        if revise == True:
            get_name_from_db = self.env['sale.order'].sudo().search([('name', 'ilike', self.name + '%')], limit=1,
                                                                    order='id desc')
            name_chk = get_name_from_db.name.split('-R')
            if len(name_chk) > 1 and name_chk[1]:
                res.name = name_chk[0] + '-R' + str(int(name_chk[1]) + 1)
            else:
                res.name = self.name + '-R1'

        else:
            get_sequence_object = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'sale'), ('company_id', 'in', [company_id, False])],
                limit=1, )
            if res.name != '/' or res.name.upper() != 'DRAFT' or res.name.upper() != 'NEW':
                sale_name = ''
            if res.name == '/' or res.name.upper() == 'DRAFT' or res.name.upper() == 'NEW':
                sale_name = ''
            seq_date = vals_list.get('date_order') or fields.Date.context_today(self)
            get_sequence = self.env['ir.sequence'].next_by_sequence_for(
                'sale', sequence_date=seq_date,
            )
            if get_sequence:
                get_highest_sale = self.env['sale.order'].sudo().search(
                    [('id', '!=', res.id), ('name', 'not like', '%-R%')], limit=1, order='id desc')
                get_sequence = res._get_sequence(get_sequence_object, get_sequence, vals_list, get_highest_sale,
                                                 sale_name)
                get_sequence = res._cpabooks_make_unique_sale_name(
                    get_sequence, res.company_id, exclude_order=res)

            if not get_sequence:
                raise ValidationError(_("Sequence is not set for sale quotation"))
            res.name = get_sequence or _('/')
        res.flush(['name'])
        return res

    def _get_sequence(self, get_sequence_object, get_sequence, vals_list, get_highest_sale, sale_name):
        common_method = self.env['common.method']
        model = 'sale.order'
        if '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern == 'month_year':
            if sale_name != '':
                split_sale_name = sale_name.split('/')
                split_seq = get_sequence.split('/')
                split_sale_name_last_value = split_sale_name[-1]
                split_seq[-1] = split_sale_name_last_value
                if get_highest_sale and get_highest_sale.name != '/':
                    split_highest_inv = get_highest_sale.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = max(1, get_sequence_object.number_next_actual - 1)
            else:
                split_seq = get_sequence.split('/')
                # split_highest_inv = get_highest_sale.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            if 'date_order' in vals_list.keys() and not isinstance(vals_list['date_order'],
                                                                   bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(vals_list['date_order']).split('-')[0]
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['invoice_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(vals_list['date_order']).split('-')[1]
                    get_sequence = "/".join(split_seq)
            if 'date_order' not in vals_list.keys() and not isinstance(self.date_order,
                                                                       bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(self.date_order).split('-')[0]
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['invoice_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(self.date_order).split('-')[1]
                    get_sequence = "/".join(split_seq)
            return get_sequence

        elif '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern == 'month_year_monthly':
            split_seq_obj = get_sequence_object.prefix.split('/')
            get_year_index = split_seq_obj.index('%(year)s')
            get_month_index = split_seq_obj.index('%(month)s')
            split_inv_name = []
            for i in range(get_year_index + 3):
                split_inv_name.append('')
            if sale_name != '':
                split_inv_name = sale_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_sale and get_highest_sale.name != '/':
                    split_highest_inv = get_highest_sale.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = max(1, get_sequence_object.number_next_actual - 1)
            else:
                split_seq = get_sequence.split('/')
                get_sequence_object.number_next_actual = max(1, get_sequence_object.number_next_actual - 1)
                # split_highest_inv = get_highest_inv.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            if 'date_order' in vals_list.keys() and not isinstance(vals_list['date_order'],
                                                                   bool):
                date_obj = common_method.parse_sequence_datetime(vals_list['date_order'])
                year_str = self._cpabooks_sequence_year_str(date_obj)
                if len(split_seq) > get_year_index:
                    split_seq[get_year_index] = year_str
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['invoice_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(date_obj).split('-')[1]
                    get_sequence = "/".join(split_seq)

                    # region Month wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if year_str == split_inv_name[get_year_index] and date_obj.date().month == int(
                            split_inv_name[get_month_index]):
                        orginal_sequence = sale_name.split('/')
                    else:
                        extra_condition = ('name', 'not like', '%-R%')
                        get_highest_sequence = common_method.get_highest_seq_for_month_year_monthly(get_sequence_object,
                                                                                                    date_obj, model,
                                                                                                    extra_condition)
                        # get_highest_sequence = self.env['sale.order'].sudo().search(
                        #     [('name', 'like', without_last_index_sequence),('name','not like','%-R%'), ('id', '!=', self.id)],
                        #     order="name desc",
                        #     limit=1)
                        sequence_padding = get_sequence_object.padding
                        get_highest_sequence_no = 0
                        if get_highest_sequence:
                            highest_seq = get_highest_sequence.name.split('/')
                            get_highest_sequence_no = int(highest_seq[-1])
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            common = '1'
                            divide_by = int(common.ljust(sequence_padding + 1, '0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert

                    get_sequence = "/".join(orginal_sequence)
                    # endregion
            if 'date_order' not in vals_list.keys() and not isinstance(self.date_order,
                                                                       bool):
                date_obj = self.date_order + timedelta(hours=6)
                year_str = self._cpabooks_sequence_year_str(date_obj)
                if len(split_seq) > get_year_index:
                    split_seq[get_year_index] = year_str
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['invoice_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(date_obj).split('-')[1]
                    get_sequence = "/".join(split_seq)
                    # region Month wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if year_str == split_inv_name[get_year_index] and date_obj.month == int(
                            split_inv_name[get_month_index]):
                        orginal_sequence = sale_name.split('/')
                    else:
                        extra_condition = ('name', 'not like', '%-R%')
                        get_highest_sequence = common_method.get_highest_seq_for_month_year_monthly(get_sequence_object,
                                                                                                    date_obj, model,
                                                                                                    extra_condition)
                        # get_highest_sequence = self.env['sale.order'].sudo().search(
                        #     [('name', 'like', without_last_index_sequence),('name','not like','%-R%'), ('id', '!=', self.id)],
                        #     order="name desc",
                        #     limit=1)
                        sequence_padding = get_sequence_object.padding
                        get_highest_sequence_no = 0
                        if get_highest_sequence:
                            highest_seq = get_highest_sequence.name.split('/')
                            get_highest_sequence_no = int(highest_seq[-1])
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            common = '1'
                            divide_by = int(common.ljust(sequence_padding + 1, '0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert

                    get_sequence = "/".join(orginal_sequence)
                    # endregion
            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern == 'year':
            if sale_name != '':
                split_inv_name = sale_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_sale and get_highest_sale.name != '/':
                    split_highest_inv = get_highest_sale.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = max(1, get_sequence_object.number_next_actual - 1)
            else:
                split_seq = get_sequence.split('/')
            if 'date_order' in vals_list.keys() and not isinstance(vals_list['date_order'],
                                                                   bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(vals_list['date_order']).split('-')[0]
                    get_sequence = "/".join(split_seq)

            if 'date_order' not in vals_list.keys() and not isinstance(self.date_order,
                                                                       bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(self.date_order).split('-')[0]
                    get_sequence = "/".join(split_seq)

            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern == 'year_yearly':
            # split_inv_name = ['', '', '', ''] if sale_name == '' else sale_name.split('/')
            split_seq_obj = get_sequence_object.prefix.split('/')
            get_year_index = split_seq_obj.index('%(year)s')
            split_inv_name = []
            for i in range(get_year_index + 1):
                split_inv_name.append('')
            split_inv_name.append('')
            if sale_name != '':
                split_inv_name = sale_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_sale and get_highest_sale.name != '/':
                    split_highest_inv = get_highest_sale.name.split('/')
                    # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
                    get_sequence_object.number_next_actual = max(1, get_sequence_object.number_next_actual - 1)
            else:
                split_seq = get_sequence.split('/')
                get_sequence_object.number_next_actual = max(1, get_sequence_object.number_next_actual - 1)
            if 'date_order' in vals_list and not isinstance(vals_list['date_order'], bool):
                date_val = vals_list['date_order']

                if isinstance(date_val, datetime):
                    date_obj = date_val + timedelta(hours=6)
                if isinstance(date_val, date):
                    date_obj = datetime.combine(date_val, datetime.min.time()) + timedelta(hours=6)
                else:
                    date_obj = common_method.parse_sequence_datetime(vals_list['date_order'])

                # if isinstance(vals_list['date_order'], datetime):
                #     date_obj = vals_list['date_order'] + timedelta(hours=6)
                # else:
                #     date_obj = datetime.strptime(vals_list['date_order'], '%Y-%m-%d %H:%M:%S') + timedelta(hours=6)
                # date_obj = datetime.strptime(vals_list['date_order'], '%Y-%m-%d %H:%M:%S') + timedelta(hours=6)
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(date_obj).split('-')[0]
                    get_sequence = "/".join(split_seq)

                    # region year wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"

                    if str(date_obj.date().year) == split_inv_name[get_year_index]:
                        orginal_sequence = sale_name.split('/')
                    else:
                        extra_condition = ('name', 'not like', '%-R%')
                        get_highest_sequence = common_method.get_highest_seq_for_year_yearly(get_sequence_object,
                                                                                             date_obj, model,
                                                                                             extra_condition)
                        # get_highest_sequence = self.env['sale.order'].sudo().search(
                        #     [('name', 'like', without_last_index_sequence),('name','not like','%-R%'), ('id', '!=', self.id)],
                        #     order="name desc",
                        #     limit=1)
                        sequence_padding = get_sequence_object.padding
                        get_highest_sequence_no = 0
                        if get_highest_sequence:
                            highest_seq = get_highest_sequence.name.split('/')
                            get_highest_sequence_no = int(highest_seq[-1])
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            common = '1'
                            divide_by = int(common.ljust(sequence_padding + 1, '0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert

                    get_sequence = "/".join(orginal_sequence)
                    # endregion

            if 'date_order' not in vals_list.keys() and not isinstance(self.date_order,
                                                                       bool):
                date_obj = self.date_order + timedelta(hours=6)
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(date_obj).split('-')[0]
                    get_sequence = "/".join(split_seq)

                    # region year wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"
                    if str(date_obj.year) == split_inv_name[get_year_index]:
                        orginal_sequence = sale_name.split('/')
                    else:
                        extra_condition = ('name', 'not like', '%-R%')
                        get_highest_sequence = common_method.get_highest_seq_for_year_yearly(get_sequence_object,
                                                                                             date_obj, model,
                                                                                             extra_condition)
                        # get_highest_sequence = self.env['sale.order'].sudo().search(
                        #     [('name', 'like', without_last_index_sequence),('name','not like','%-R%'), ('id', '!=', self.id)],
                        #     order="name desc",
                        #     limit=1)
                        sequence_padding = get_sequence_object.padding
                        get_highest_sequence_no = 0
                        if get_highest_sequence:
                            highest_seq = get_highest_sequence.name.split('/')
                            get_highest_sequence_no = int(highest_seq[-1])
                        if len(str(get_highest_sequence_no)) > sequence_padding:
                            number = get_highest_sequence_no + 1
                            string_convert = str(number)
                            orginal_sequence[-1] = string_convert
                        else:
                            common = '1'
                            divide_by = int(common.ljust(sequence_padding + 1, '0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert

                    get_sequence = "/".join(orginal_sequence)
                    # endregion

            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(month)s/' in get_sequence_object.prefix:
            if sale_name != '':
                split_inv_name = sale_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_sale and get_highest_sale.name != '/':
                    split_highest_inv = get_highest_sale.name.split('/')
                    get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            else:
                split_seq = get_sequence.split('/')
            if 'date_order' in vals_list.keys() and not isinstance(vals_list['date_order'],
                                                                   bool):
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['invoice_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(vals_list['date_order']).split('-')[1]
                    get_sequence = "/".join(split_seq)
            if 'date_order' not in vals_list.keys() and not isinstance(self.date_order,
                                                                       bool):

                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['invoice_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(self.date_order).split('-')[1]
                    get_sequence = "/".join(split_seq)
            return get_sequence


        else:
            if sale_name != '':
                split_inv_name = sale_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                get_sequence = "/".join(split_seq)
                if get_highest_sale and get_highest_sale.name != '/':
                    split_highest_inv = get_highest_sale.name.split('/')
                    # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
                    get_sequence_object.number_next_actual = max(1, get_sequence_object.number_next_actual - 1)
            else:
                split_seq = get_sequence.split('/')
                get_sequence = "/".join(split_seq)
            return get_sequence

    def write(self, vals_list):
        rec = super(SaleOrderInheritance, self).write(vals_list)
        company_id = self.env.company.id
        for res in self:
            if not res.name.__contains__('-R'):

                sale_name = ''
                if ('date_order' in vals_list.keys() and not isinstance(vals_list['date_order'], bool)) or (
                        res.name == '/' and not isinstance(res.date_order, bool)):
                    get_sequence_object = self.env['ir.sequence'].sudo().search(
                        [('sequence_for', '=', 'sale'), ('company_id', 'in', [company_id, False])],
                        limit=1, )
                    if res.name != '/' or res.name.upper() != 'DRAFT' or res.name.upper() != 'NEW':
                        sale_name = res.name
                    if res.name == '/' or res.name.upper() == 'DRAFT' or res.name.upper() == 'NEW':
                        sale_name = ''
                    if sale_name != '':
                        get_sequence = self.env['ir.sequence'].next_by_sequence_for('sale')
                        if get_sequence:
                            get_highest_sale = self.env['sale.order'].sudo().search(
                                [('id', '!=', res.id), ('name', 'not like', '%-R%')],
                                limit=1,
                                order='id desc')
                            get_sequence = res._get_sequence(get_sequence_object, get_sequence, vals_list,
                                                             get_highest_sale, sale_name)
                            get_sequence = res._cpabooks_make_unique_sale_name(
                                get_sequence, res.company_id, exclude_order=res)

                        if not get_sequence:
                            raise ValidationError(_("Sequence is not set for Sale"))
                        res.name = get_sequence or _('/')

        return rec

    def action_revise_sale_order(self, default=None):
        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_orders")
        if default is None:
            default = {}
        if 'order_line' not in default:
            default['order_line'] = [(0, 0, line.copy_data()[0]) for line in
                                     self.order_line.filtered(lambda l: not l.is_downpayment)]
            default['revise'] = True
        data = super(SaleOrderInheritance, self).copy(default)
        action['context'] = dict(self.env.context)
        action['context']['form_view_initial_mode'] = 'edit'
        action['context']['view_no_maturity'] = False
        action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
        action['res_id'] = data.id

        return action
        # return {
        #     # 'name': self.display_name,
        #     'type': 'ir.actions.act_window',
        #     'view_type': 'form',
        #     'view_mode': 'form',
        #     'res_model': 'sale.order',
        #     'res_id': data.id,
        # }
