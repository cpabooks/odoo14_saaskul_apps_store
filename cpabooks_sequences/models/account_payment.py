import re

from odoo import models, fields, api,_
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
from decimal import Decimal


class AccountPaymentInheritance(models.Model):
    _inherit = 'account.payment'

    def _get_payment_sequence_code(self, payment_type=None):
        payment_type = payment_type or self.payment_type
        if payment_type == 'inbound':
            return 'receipt_voucher'
        if payment_type == 'outbound':
            return 'payment_voucher'
        return False

    def _get_payment_sequence_company(self):
        self.ensure_one()
        return self.company_id or self.journal_id.company_id or self.env.company

    def _get_backdated_sequence_name(self, sequence_for, payment_date, current_name=None):
        self.ensure_one()
        if not payment_date:
            return False

        company = self._get_payment_sequence_company()
        company_id = company.id
        get_sequence_object = self.env['ir.sequence'].sudo().search(
            [('sequence_for', '=', sequence_for), ('company_id', '=', company_id)],
            limit=1,
        )
        if not get_sequence_object:
            get_sequence_object = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', sequence_for), ('company_id', '=', False)],
                limit=1,
            )
        if not get_sequence_object:
            return False

        payment_type = 'inbound' if sequence_for == 'receipt_voucher' else 'outbound'
        get_sequence = get_sequence_object.next_by_custom_seq(
            sequence_for=sequence_for,
            field_date=payment_date,
            next_number=1,
        )
        if not get_sequence or not get_sequence_object.padding:
            return False

        sequence_prefix = get_sequence[:-get_sequence_object.padding]
        current_name = current_name if current_name is not None else self.name
        if current_name and current_name not in ('/', 'DRAFT', 'draft', 'Draft', 'NEW', 'new', 'New'):
            current_prefix = current_name[:-get_sequence_object.padding]
            if current_prefix == sequence_prefix:
                return current_name

        highest_payment = self.env['account.payment'].sudo().with_context(
            cpabooks_jv_view_mode=False,
            cpabooks_odoo_fix_jv_view_mode=False,
        ).search(
            [
                ('payment_type', '=', payment_type),
                ('company_id', '=', company_id),
                ('id', '!=', self.id),
                ('sequence_prefix', '=', sequence_prefix),
            ],
            limit=1,
            order='sequence_number desc, id desc',
        )[:1]
        next_number = (highest_payment.sequence_number or 0) + 1
        return f"{sequence_prefix}{str(next_number).zfill(get_sequence_object.padding)}"

    # @api.model
    # def create(self, vals_list):
    #     res=super(AccountPaymentInheritance, self).create(vals_list)
    #     get_sequence = None
    #     field_date = vals_list.get('date')
    #     if res.payment_type=='inbound':
    #         next_number = self.get_next_number(res.date, sequence_for='receipt_voucher')
    #         get_sequence = self.env['ir.sequence'].next_by_custom_seq(sequence_for='receipt_voucher',field_date=field_date, next_number=next_number)
    #         # get_sequence = self.env['ir.sequence'].with_company(company_id).next_by_sequence_for(sequence_for='receipt_voucher')
    #     else:
    #         next_number = self.get_next_number(res.date, sequence_for='payment_voucher')
    #         get_sequence = self.env['ir.sequence'].next_by_custom_seq(sequence_for='payment_voucher',field_date=field_date, next_number=next_number)
    #         # get_sequence = self.env['ir.sequence'].with_company(company_id).next_by_sequence_for(sequence_for='payment_voucher')
    #
    #     if not get_sequence:
    #         if res.payment_type == 'inbound':
    #             raise ValidationError(_("Sequence is not set for receipt voucher"))
    #         else:
    #             raise ValidationError(_("Sequence is not set for payment voucher"))
    #     res.name = get_sequence or _('/')
    #     return res
    #
    # def write(self, vals):
    #     res = super(AccountPaymentInheritance, self).write(vals)
    #     get_sequence = None
    #     if 'date' in vals:
    #         field_date = vals.get('date')
    #         next_number = self.get_next_number(field_date)
    #         for record in self:  # Loop through updated records in self
    #             if record.payment_type == 'inbound':
    #                 get_sequence = self.env['ir.sequence'].next_by_custom_seq(
    #                     sequence_for='receipt_voucher',
    #                     field_date=field_date,  # Use field_date directly
    #                     next_number=next_number
    #                 )
    #             else:
    #                 get_sequence = self.env['ir.sequence'].next_by_custom_seq(
    #                     sequence_for='payment_voucher',
    #                     field_date=field_date,  # Use field_date directly
    #                     next_number=next_number
    #                 )
    #
    #             if not get_sequence:
    #                 if record.payment_type == 'inbound':
    #                     raise ValidationError(_("Sequence is not set for receipt voucher"))
    #                 else:
    #                     raise ValidationError(_("Sequence is not set for payment voucher"))
    #
    #             record.update({
    #                 'name': get_sequence or _('/')
    #             })
    #     return res
    #
    # def get_next_number(self, field_date=False, sequence_for=False):
    #     if not sequence_for:
    #         sequence_for = 'payment_voucher'
    #     sequence_id = self.env['ir.sequence'].search([
    #         ('company_id', '=', self.env.company.id),
    #         ('sequence_for', '=', sequence_for)
    #     ], limit=1)
    #     prefix = sequence_id.prefix
    #     print(prefix)
    #     if not field_date:
    #         field_date = date.today()
    #     if isinstance(field_date, str):
    #         try:
    #             # Handle both formats: YYYY-MM-DD and DD/MM/YYYY
    #             if "-" in field_date:
    #                 date_obj = datetime.strptime(field_date, "%Y-%m-%d")
    #             else:
    #                 date_obj = datetime.strptime(field_date, "%d/%m/%Y")
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
    #     largest_number = 0
    #     if int_num:
    #         largest_number = max(int_num)
    #     return largest_number + 1
    
    
    # NEW CODE
    def _get_sequence(self,get_sequence_object,get_sequence,vals_list,get_highest_purchase,purchase_name):
        common_method = self.env['common.method']
        model = 'account.payment'
        if '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='month_year':
            # split_seq_obj = get_sequence_object.prefix.split('/')
            # get_year_index = split_seq_obj.index('%(year)s')
            # split_payment_name = []
            # for i in range(get_year_index + 3):
            #     split_payment_name.append('')
            if purchase_name != '':
                split_payment_name = purchase_name.split('/')
                split_seq = get_sequence.split('/')
                split_payment_name_last_value = split_payment_name[-1]
                split_seq[-1] = split_payment_name_last_value
                if get_highest_purchase and get_highest_purchase.name!='/':
                    split_highest_inv=get_highest_purchase.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])-1
                    get_sequence_object.number_next_actual=get_sequence_object.number_next_actual-1
            else:
                split_seq = get_sequence.split('/')
                # split_highest_inv = get_highest_purchase.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(vals_list['date']).split('-')[0]
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['invoice_date']).split('-')[1]) > -1:
                    month=datetime.now().month
                    str_month=str(datetime.now().month)
                    if month<10:
                        str_month=str(0)+str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(vals_list['date']).split('-')[1]
                    get_sequence = "/".join(split_seq)
            if 'date' not in vals_list.keys() and not isinstance(self.date,
                                                                     bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(self.date).split('-')[0]
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['invoice_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(self.date).split('-')[1]
                    get_sequence = "/".join(split_seq)
            return get_sequence

        elif '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='month_year_monthly':
            split_seq_obj = get_sequence_object.prefix.split('/')
            get_year_index = split_seq_obj.index('%(year)s')
            get_month_index = split_seq_obj.index('%(month)s')
            split_payment_name = []
            for i in range(get_year_index + 3):
                split_payment_name.append('')
            # *****************************************************
            if purchase_name != '':
                split_payment_name = purchase_name.split('/')
                split_seq = get_sequence.split('/')
                split_payment_name_last_value = split_payment_name[-1]
                split_seq[-1] = split_payment_name_last_value
                if get_highest_purchase and get_highest_purchase.name!='/':
                    split_highest_inv=get_highest_purchase.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
                # split_highest_inv = get_highest_inv.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],bool):
                date_obj = datetime.strptime(str(vals_list['date']), '%Y-%m-%d') + timedelta(hours=6)
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(date_obj).split('-')[0]
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    month=datetime.now().month
                    str_month=str(datetime.now().month)
                    if month<10:
                        str_month=str(0)+str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(date_obj).split('-')[1]
                    get_sequence = "/".join(split_seq)

                    # region Month wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"
                    if str(date_obj.year) == split_payment_name[get_year_index] \
                            and date_obj.month == int(split_payment_name[get_month_index]):
                        orginal_sequence = purchase_name.split('/')
                    else:
                        get_highest_sequence=common_method.get_highest_seq_for_month_year_monthly(get_sequence_object,date_obj,model)
                        # get_highest_sequence = self.env['account.payment'].sudo().search(
                        #     [('name', 'like', without_last_index_sequence), ('id', '!=', self.id)],
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
                date_obj=self.date+timedelta(hours=6)
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(date_obj).split('-')[0]
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
                    #region Month wise sequence
                    orginal_sequence = get_sequence.split('/')
                    split_sequence_prefix = get_sequence.split('/')
                    without_last_index = split_sequence_prefix.pop()
                    without_last_index_sequence = "/".join(split_sequence_prefix)
                    without_last_index_sequence += "/"
                    if str(date_obj.year) == split_payment_name[get_year_index] \
                            and date_obj.month == int(split_payment_name[get_month_index]):
                        orginal_sequence = purchase_name.split('/')
                    else:
                        get_highest_sequence=common_method.get_highest_seq_for_month_year_monthly(get_sequence_object,date_obj,model)

                        # get_highest_sequence = self.env['account.payment'].sudo().search(
                        #     [('name', 'like', without_last_index_sequence), ('id', '!=', self.id)],
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
                            common='1'
                            divide_by=int(common.ljust(sequence_padding+1,'0'))
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert

                    get_sequence = "/".join(orginal_sequence)
                    #endregion
            return get_sequence
            # *****************************************************

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='year' :
            if purchase_name != '':
                split_payment_name = purchase_name.split('/')
                split_seq = get_sequence.split('/')
                split_payment_name_last_value = split_payment_name[-1]
                split_seq[-1] = split_payment_name_last_value
                if get_highest_purchase and get_highest_purchase.name!='/':
                    split_highest_inv=get_highest_purchase.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(vals_list['date']).split('-')[0]
                    get_sequence = "/".join(split_seq)

            if 'date' not in vals_list.keys() and not isinstance(self.date,
                                                                     bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(self.date).split('-')[0]
                    get_sequence = "/".join(split_seq)


            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='year_yearly':
            split_seq_obj=get_sequence_object.prefix.split('/')
            get_year_index=split_seq_obj.index('%(year)s')
            split_payment_name=[]
            for i in range(get_year_index+1):
                split_payment_name.append('')
            split_payment_name.append('')
            # split_payment_name=['','','',''] if purchase_name=='' else purchase_name.split('/')
            if purchase_name != '':
                split_payment_name = purchase_name.split('/')
                split_seq = get_sequence.split('/')
                split_payment_name_last_value = split_payment_name[-1]
                split_seq[-1] = split_payment_name_last_value
                if get_highest_purchase and get_highest_purchase.name != '/':
                    split_highest_inv = get_highest_purchase.name.split('/')
                    # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool):
                date_obj = datetime.strptime(str(vals_list['date']), '%Y-%m-%d') + timedelta(hours=6)
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

                    if str(date_obj.year) == split_payment_name[get_year_index]: #and not purchase_name.startswith(without_last_index_sequence):
                        orginal_sequence = purchase_name.split('/')

                    else:
                        get_highest_sequence=common_method.get_highest_seq_for_year_yearly(get_sequence_object,date_obj,model)
                        # get_highest_sequence = self.env['account.payment'].sudo().search(
                        #     [('name', 'like', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="name desc",
                        #     limit=1)
                        sequence_padding = get_sequence_object.padding
                        get_highest_sequence_no = 0
                        if get_highest_sequence:
                            highest_seq = get_highest_sequence.name.split('/')
                            get_highest_sequence_no = int(highest_seq[-1])
                        if len(str(get_highest_sequence_no))>sequence_padding:
                            number=get_highest_sequence_no+1
                            string_convert=str(number)
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
                date_obj = self.date + timedelta(hours=6)
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

                    if str(self.date.year)==split_payment_name[get_year_index]: #and purchase_name.startswith(without_last_index_sequence):
                        orginal_sequence = purchase_name.split('/')
                    else:
                        get_highest_sequence=common_method.get_highest_seq_for_year_yearly(get_sequence_object,date_obj,model)
                        # get_highest_sequence = self.env['account.payment'].sudo().search(
                        #     [('name', 'like', without_last_index_sequence), ('id', '!=', self.id)],
                        #     order="name desc",
                        #     limit=1)
                        sequence_padding = get_sequence_object.padding

                        get_highest_sequence_no=0
                        if get_highest_sequence:
                            highest_seq = get_highest_sequence.name.split('/')
                            get_highest_sequence_no = int(highest_seq[-1])
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

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(month)s/' in get_sequence_object.prefix:
            if purchase_name != '':
                split_payment_name = purchase_name.split('/')
                split_seq = get_sequence.split('/')
                split_payment_name_last_value = split_payment_name[-1]
                split_seq[-1] = split_payment_name_last_value
                if get_highest_purchase and get_highest_purchase.name != '/':
                    split_highest_inv = get_highest_purchase.name.split('/')
                    get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            else:
                split_seq = get_sequence.split('/')
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
                                                                     bool):
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['invoice_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(vals_list['date']).split('-')[1]
                    get_sequence = "/".join(split_seq)
            if 'date' not in vals_list.keys() and not isinstance(self.date,
                                                                         bool):

                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['invoice_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(self.date).split('-')[1]
                    get_sequence = "/".join(split_seq)
            return get_sequence


        else:
            if purchase_name != '':
                split_payment_name = purchase_name.split('/')
                split_seq = get_sequence.split('/')
                split_payment_name_last_value = split_payment_name[-1]
                split_seq[-1] = split_payment_name_last_value
                get_sequence = "/".join(split_seq)
                if get_highest_purchase and get_highest_purchase.name != '/':
                    split_highest_inv = get_highest_purchase.name.split('/')
                    # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
                    get_sequence_object.number_next_actual =get_sequence_object.number_next_actual-1
            else:
                split_seq = get_sequence.split('/')
                get_sequence = "/".join(split_seq)
            return get_sequence

    # def _get_sequence(self,get_sequence_object,get_sequence,payment_name,vals_list,get_highest_inv):
    #     if '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='month_year':
    #         if payment_name != '':
    #             split_payment_name = payment_name.split('/')
    #             split_seq = get_sequence.split('/')
    #             split_payment_name_last_value = split_payment_name[-1]
    #             split_seq[-1] = split_payment_name_last_value
    #             if get_highest_inv and get_highest_inv.name!='/':
    #                 split_highest_inv=get_highest_inv.name.split('/')
    #                 # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
    #                 get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
    #         else:
    #             split_seq = get_sequence.split('/')
    #             # split_highest_inv = get_highest_inv.split('/')
    #             # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
    #         if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
    #                                                                  bool):
    #             if get_sequence.find(str(datetime.datetime.now().year)) > -1:
    #                 idx = split_seq.index(str(datetime.datetime.now().year))
    #                 split_seq[idx] = str(vals_list['date']).split('-')[0]
    #                 get_sequence = "/".join(split_seq)
    #             if get_sequence.find(str(datetime.datetime.now().month)) > -1:
    #                 # if not get_sequence.find(str(vals_list['date']).split('-')[1]) > -1:
    #                 month=datetime.datetime.now().month
    #                 str_month=str(datetime.datetime.now().month)
    #                 if month<10:
    #                     str_month=str(0)+str_month
    #                 idx = split_seq.index(str_month)
    #                 split_seq[idx] = str(vals_list['date']).split('-')[1]
    #                 get_sequence = "/".join(split_seq)
    #         if 'date' not in vals_list.keys() and not isinstance(self.invoice_date,
    #                                                                  bool):
    #             if get_sequence.find(str(datetime.datetime.now().year)) > -1:
    #                 idx = split_seq.index(str(datetime.datetime.now().year))
    #                 split_seq[idx] = str(self.invoice_date).split('-')[0]
    #                 get_sequence = "/".join(split_seq)
    #             if get_sequence.find(str(datetime.datetime.now().month)) > -1:
    #                 # if not get_sequence.find(str(vals_list['date']).split('-')[1]) > -1:
    #                 month = datetime.datetime.now().month
    #                 str_month = str(datetime.datetime.now().month)
    #                 if month < 10:
    #                     str_month = str(0) + str_month
    #                 idx = split_seq.index(str_month)
    #                 split_seq[idx] = str(self.invoice_date).split('-')[1]
    #                 get_sequence = "/".join(split_seq)
    #         self._cr.commit()
    #         return get_sequence
    #     #1st change
    #     elif '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='month_year_monthly':
    #         if payment_name != '':
    #             split_payment_name = payment_name.split('/')
    #             split_seq = get_sequence.split('/')
    #             split_payment_name_last_value = split_payment_name[-1]
    #             split_seq[-1] = split_payment_name_last_value
    #             if get_highest_inv and get_highest_inv.name!='/':
    #             #     split_highest_inv=get_highest_inv.name.split('/')
    #                 # get_sequence_object.number_next_actual=int(split_highest_inv[-1])-2
    #                 get_sequence_object.number_next_actual =get_sequence_object.number_next_actual-1
    #                 # self._cr.commit()
    #         else:
    #             split_seq = get_sequence.split('/')
    #             get_sequence_object.number_next_actual = get_sequence_object.number_next_actual-1
    #             # self._cr.commit()
    # 
    #             # split_highest_inv = get_highest_inv.split('/')
    #             # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
    #         if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
    #                                                                  bool):
    #             if get_sequence.find(str(datetime.datetime.now().year)) > -1:
    #                 idx = split_seq.index(str(datetime.datetime.now().year))
    #                 split_seq[idx] = str(vals_list['date']).split('-')[0]
    #                 get_sequence = "/".join(split_seq)
    #             if get_sequence.find(str(datetime.datetime.now().month)) > -1:
    #                 # if not get_sequence.find(str(vals_list['date']).split('-')[1]) > -1:
    #                 month=datetime.datetime.now().month
    #                 str_month=str(datetime.datetime.now().month)
    #                 if month<10:
    #                     str_month=str(0)+str_month
    #                 idx = split_seq.index(str_month)
    #                 split_seq[idx] = str(vals_list['date']).split('-')[1]
    #                 get_sequence = "/".join(split_seq)
    # 
    #                 # region Month wise sequence
    #                 orginal_sequence = get_sequence.split('/')
    #                 split_sequence_prefix = get_sequence.split('/')
    #                 without_last_index = split_sequence_prefix.pop()
    #                 without_last_index_sequence = "/".join(split_sequence_prefix)
    #                 without_last_index_sequence += "/"
    #                 # get_highest_sequence_no = self.env['account.move'].search(
    #                 #     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
    #                 #     order="sequence_number desc",
    #                 #     limit=1).sequence_number
    #                 get_highest_sequence_no=self.env['account.payment'].sudo().search([('id','!=',self.id)],
    #                                                                              limit=1,
    #                                                                              order='id desc')
    # 
    #                 sequence_padding = get_sequence_object.padding
    #                 if len(str(get_highest_sequence_no)) > sequence_padding:
    #                     number = get_highest_sequence_no + 1
    #                     string_convert = str(number)
    #                     orginal_sequence[-1] = string_convert
    #                 else:
    #                     divide_by=100000
    #                     if sequence_padding==4:
    #                         divide_by=10000
    #                     if sequence_padding==3:
    #                         divide_by=1000
    #                     if sequence_padding==2:
    #                         divide_by=100
    #                     if sequence_padding==1:
    #                         divide_by=10
    #                     number = (get_highest_sequence_no + 1) / divide_by
    #                     dec_string = str(round(Decimal(number), sequence_padding))
    #                     string_convert = dec_string.split('.')[1]
    #                     orginal_sequence[-1] = string_convert
    #                 get_sequence = "/".join(orginal_sequence)
    #                 # endregion
    #         if 'date' not in vals_list.keys() and not isinstance(self.invoice_date,
    #                                                                  bool):
    #             if get_sequence.find(str(datetime.datetime.now().year)) > -1:
    #                 idx = split_seq.index(str(datetime.datetime.now().year))
    #                 split_seq[idx] = str(self.invoice_date).split('-')[0]
    #                 get_sequence = "/".join(split_seq)
    #             if get_sequence.find(str(datetime.datetime.now().month)) > -1:
    #                 # if not get_sequence.find(str(vals_list['date']).split('-')[1]) > -1:
    #                 month = datetime.datetime.now().month
    #                 str_month = str(datetime.datetime.now().month)
    #                 if month < 10:
    #                     str_month = str(0) + str_month
    #                 idx = split_seq.index(str_month)
    #                 split_seq[idx] = str(self.invoice_date).split('-')[1]
    #                 get_sequence = "/".join(split_seq)
    #                 #region Month wise sequence
    #                 orginal_sequence = get_sequence.split('/')
    #                 split_sequence_prefix = get_sequence.split('/')
    #                 without_last_index = split_sequence_prefix.pop()
    #                 without_last_index_sequence = "/".join(split_sequence_prefix)
    #                 without_last_index_sequence += "/"
    #                 get_highest_sequence_no = self.env['account.move'].search(
    #                     [('sequence_prefix', '=', without_last_index_sequence),('id','!=',self.id)], order="sequence_number desc",
    #                     limit=1).sequence_number
    # 
    #                 sequence_padding = get_sequence_object.padding
    #                 if len(str(get_highest_sequence_no)) > sequence_padding:
    #                     number = get_highest_sequence_no + 1
    #                     string_convert = str(number)
    #                     orginal_sequence[-1] = string_convert
    #                 else:
    #                     common='1'
    #                     divide_by=int(common.ljust(sequence_padding+1,'0'))
    #                     number = (get_highest_sequence_no + 1) / divide_by
    #                     dec_string = str(round(Decimal(number), sequence_padding))
    #                     string_convert = dec_string.split('.')[1]
    #                     orginal_sequence[-1] = string_convert
    #                 get_sequence = "/".join(orginal_sequence)
    #                 #endregion
    #         
    #         self._cr.commit()
    #         return get_sequence
    # 
    #     elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='year' :
    #         if payment_name != '':
    #             split_payment_name = payment_name.split('/')
    #             split_seq = get_sequence.split('/')
    #             split_payment_name_last_value = split_payment_name[-1]
    #             split_seq[-1] = split_payment_name_last_value
    #             if get_highest_inv and get_highest_inv.name!='/':
    #                 split_highest_inv=get_highest_inv.name.split('/')
    #                 # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
    #                 get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
    #         else:
    #             split_seq = get_sequence.split('/')
    #         if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
    #                                                                  bool):
    #             if get_sequence.find(str(datetime.datetime.now().year)) > -1:
    #                 idx = split_seq.index(str(datetime.datetime.now().year))
    #                 split_seq[idx] = str(vals_list['date']).split('-')[0]
    #                 get_sequence = "/".join(split_seq)
    # 
    #         if 'date' not in vals_list.keys() and not isinstance(self.invoice_date,
    #                                                                  bool):
    #             if get_sequence.find(str(datetime.datetime.now().year)) > -1:
    #                 idx = split_seq.index(str(datetime.datetime.now().year))
    #                 split_seq[idx] = str(self.invoice_date).split('-')[0]
    #                 get_sequence = "/".join(split_seq)
    # 
    #        
    # 
    #         self._cr.commit()
    #         return get_sequence
    # 
    #     elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern=='year_yearly':
    #         if payment_name != '':
    #             split_payment_name = payment_name.split('/')
    #             split_seq = get_sequence.split('/')
    #             split_payment_name_last_value = split_payment_name[-1]
    #             split_seq[-1] = split_payment_name_last_value
    #             if get_highest_inv and get_highest_inv.name != '/':
    #                 split_highest_inv = get_highest_inv.name.split('/')
    #                 # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) -2
    #                 get_sequence_object.number_next_actual = get_sequence_object.number_next_actual-1
    #         else:
    #             split_seq = get_sequence.split('/')
    #             # get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
    #         if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
    #                                                                  bool):
    #             if get_sequence.find(str(datetime.datetime.now().year)) > -1:
    #                 idx = split_seq.index(str(datetime.datetime.now().year))
    #                 split_seq[idx] = str(vals_list['date']).split('-')[0]
    #                 get_sequence = "/".join(split_seq)
    # 
    #                 # region year wise sequence
    #                 orginal_sequence = get_sequence.split('/')
    #                 split_sequence_prefix = get_sequence.split('/')
    #                 without_last_index = split_sequence_prefix.pop()
    #                 without_last_index_sequence = "/".join(split_sequence_prefix)
    #                 without_last_index_sequence += "/"
    #                 get_highest_sequence_no = self.env['account.move'].search(
    #                     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
    #                     order="sequence_number desc",
    #                     limit=1).sequence_number
    #                 if len(str(get_highest_sequence_no))>5:
    #                     number=get_highest_sequence_no+1
    #                     string_convert=str(number)
    #                     orginal_sequence[-1] = string_convert
    #                 else:
    #                     number = (get_highest_sequence_no + 1) / 100000
    #                     dec_string = str(round(Decimal(number), 5))
    #                     string_convert = dec_string.split('.')[1]
    #                     orginal_sequence[-1] = string_convert
    # 
    #                 get_sequence = "/".join(orginal_sequence)
    #                 # endregion
    # 
    #         if 'date' not in vals_list.keys() and not isinstance(self.invoice_date,
    #                                                                      bool):
    #             if get_sequence.find(str(datetime.datetime.now().year)) > -1:
    #                 idx = split_seq.index(str(datetime.datetime.now().year))
    #                 split_seq[idx] = str(self.invoice_date).split('-')[0]
    #                 get_sequence = "/".join(split_seq)
    # 
    #                 # region year wise sequence
    #                 orginal_sequence = get_sequence.split('/')
    #                 split_sequence_prefix = get_sequence.split('/')
    #                 without_last_index = split_sequence_prefix.pop()
    #                 without_last_index_sequence = "/".join(split_sequence_prefix)
    #                 without_last_index_sequence += "/"
    #                 get_highest_sequence_no = self.env['account.move'].search(
    #                     [('sequence_prefix', '=', without_last_index_sequence), ('id', '!=', self.id)],
    #                     order="sequence_number desc",
    #                     limit=1).sequence_number
    #                 sequence_padding = get_sequence_object.padding
    #                 if len(str(get_highest_sequence_no)) > sequence_padding:
    #                     number = get_highest_sequence_no + 1
    #                     string_convert = str(number)
    #                     orginal_sequence[-1] = string_convert
    #                 else:
    #                     common='1'
    #                     divide_by=int(common.ljust(sequence_padding+1,'0'))
    #                     number = (get_highest_sequence_no + 1) / divide_by
    #                     dec_string = str(round(Decimal(number), sequence_padding))
    #                     string_convert = dec_string.split('.')[1]
    #                     orginal_sequence[-1] = string_convert
    #                 get_sequence = "/".join(orginal_sequence)
    #                 # endregion
    # 
    #       
    #         self._cr.commit()
    #         return get_sequence
    # 
    #     elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(month)s/' in get_sequence_object.prefix:
    #         if payment_name != '':
    #             split_payment_name = payment_name.split('/')
    #             split_seq = get_sequence.split('/')
    #             split_payment_name_last_value = split_payment_name[-1]
    #             split_seq[-1] = split_payment_name_last_value
    #             if get_highest_inv and get_highest_inv.name!='/':
    #                 split_highest_inv=get_highest_inv.name.split('/')
    #                 get_sequence_object.number_next_actual=int(split_highest_inv[-1])
    #         else:
    #             split_seq = get_sequence.split('/')
    #         if 'date' in vals_list.keys() and not isinstance(vals_list['date'],
    #                                                                  bool):
    #             if get_sequence.find(str(datetime.datetime.now().month)) > -1:
    #                 # if not get_sequence.find(str(vals_list['date']).split('-')[1]) > -1:
    #                 month = datetime.datetime.now().month
    #                 str_month = str(datetime.datetime.now().month)
    #                 if month < 10:
    #                     str_month = str(0) + str_month
    #                 idx = split_seq.index(str_month)
    #                 split_seq[idx] = str(vals_list['date']).split('-')[1]
    #                 get_sequence = "/".join(split_seq)
    #         if 'date' not in vals_list.keys() and not isinstance(self.invoice_date,
    #                                                                  bool):
    # 
    #             if get_sequence.find(str(datetime.datetime.now().month)) > -1:
    #                 # if not get_sequence.find(str(vals_list['date']).split('-')[1]) > -1:
    #                 month = datetime.datetime.now().month
    #                 str_month = str(datetime.datetime.now().month)
    #                 if month < 10:
    #                     str_month = str(0) + str_month
    #                 idx = split_seq.index(str_month)
    #                 split_seq[idx] = str(self.invoice_date).split('-')[1]
    #                 get_sequence = "/".join(split_seq)
    # 
    #        
    #         self._cr.commit()
    #         return get_sequence
    # 
    # 
    #     else:
    #         if payment_name != '':
    #             split_payment_name = payment_name.split('/')
    #             split_seq = get_sequence.split('/')
    #             split_payment_name_last_value = split_payment_name[-1]
    #             split_seq[-1] = split_payment_name_last_value
    #             get_sequence = "/".join(split_seq)
    #             if get_highest_inv and get_highest_inv.name!='/':
    #                 split_highest_inv=get_highest_inv.name.split('/')
    #                 # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
    #                 get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
    #         else:
    #             split_seq = get_sequence.split('/')
    #             get_sequence = "/".join(split_seq)
    #         self._cr.commit()
    #         return get_sequence

    @api.model
    def create(self, vals_list):
        res = super(AccountPaymentInheritance, self.with_context(skip_payment_move_sequence=True)).create(vals_list)
        company_id = res.company_id.id or self.env.company.id
        sequence_date = vals_list.get('date') or res.date
        payment_name=''        
        if res.payment_type == 'inbound':
            get_sequence_object = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'receipt_voucher'), ('company_id', 'in', [company_id, False])],
                limit=1, )
            if res.name != '/' or res.name.upper() != 'DRAFT' or res.name.upper() != 'NEW':
                payment_name = ''
            if res.name == '/' or res.name.upper() == 'DRAFT' or res.name.upper() == 'NEW':
                payment_name = ''
            get_sequence = res._get_backdated_sequence_name('receipt_voucher', sequence_date, current_name=False)
            if not get_sequence:
                raise ValidationError(_("Sequence is not set for Receipt Voucher"))
            res.name=get_sequence or _('/')
        elif res.payment_type == 'outbound':
            get_sequence_object = self.env['ir.sequence'].sudo().search(
                [('sequence_for', '=', 'payment_voucher'), ('company_id', 'in', [company_id, False])],
                limit=1, )
            if res.name != '/' or res.name.upper() != 'DRAFT' or res.name.upper() != 'NEW':
                payment_name = ''
            if res.name == '/' or res.name.upper() == 'DRAFT' or res.name.upper() == 'NEW':
                payment_name = ''
            get_sequence = res._get_backdated_sequence_name('payment_voucher', sequence_date, current_name=False)
            if not get_sequence:
                raise ValidationError(_("Sequence is not set for Payment Voucher"))
            res.name = get_sequence or _('/')

        return res
    
    def write(self, vals_list):
        vals_list = dict(vals_list)
        payment_name_prepared = False

        if (
            len(self) == 1
            and 'date' in vals_list
            and not isinstance(vals_list.get('date'), bool)
            and 'name' not in vals_list
        ):
            payment_date = vals_list.get('date')
            sequence_for = self._get_payment_sequence_code()
            prepared_name = self._get_backdated_sequence_name(sequence_for, payment_date) if sequence_for else False
            if prepared_name:
                vals_list['name'] = prepared_name
                payment_name_prepared = True

        if (
            len(self) == 1
            and 'date' in vals_list
            and not isinstance(vals_list.get('date'), bool)
            and 'name' not in vals_list
            and not payment_name_prepared
        ):
            payment = self
            company_id = payment.company_id.id or self.env.company.id
            payment_name = ''
            sequence_date = vals_list.get('date') or payment.date

            if payment.name != '/' and payment.name.upper() not in ('DRAFT', 'NEW'):
                payment_name = payment.name

            if payment.payment_type == 'inbound' and payment_name:
                get_sequence_object = self.env['ir.sequence'].sudo().search(
                    [('sequence_for', '=', 'receipt_voucher'), ('company_id', 'in', [company_id, False])],
                    limit=1,
                )
                get_sequence = self.env['ir.sequence'].with_company(company_id).next_by_sequence_for(
                    'receipt_voucher',
                    'no',
                    sequence_date=sequence_date,
                )
                if get_sequence:
                    get_highest_inv = self.env['account.payment'].sudo().search(
                        [('payment_type', '=', 'inbound'), ('id', '!=', payment.id), ('company_id', '=', company_id)],
                        limit=1,
                        order='id desc',
                    )
                    get_sequence = payment._get_sequence(
                        get_sequence_object, get_sequence, vals_list, get_highest_inv, payment_name
                    )
                if get_sequence:
                    vals_list = dict(vals_list, name=get_sequence)

            elif payment.payment_type == 'outbound' and payment_name:
                get_sequence_object = self.env['ir.sequence'].sudo().search(
                    [('sequence_for', '=', 'payment_voucher'), ('company_id', 'in', [company_id, False])],
                    limit=1,
                )
                get_sequence = self.env['ir.sequence'].with_company(company_id).next_by_sequence_for(
                    'payment_voucher',
                    sequence_date=sequence_date,
                )
                if get_sequence:
                    get_highest_inv = self.env['account.payment'].sudo().search(
                        [('payment_type', '=', 'outbound'), ('id', '!=', payment.id), ('company_id', '=', company_id)],
                        limit=1,
                        order='id desc',
                    )
                    get_sequence = payment._get_sequence(
                        get_sequence_object, get_sequence, vals_list, get_highest_inv, payment_name
                    )
                if get_sequence:
                    vals_list = dict(vals_list, name=get_sequence)

        rec = super(AccountPaymentInheritance, self).write(vals_list)
        for res in self:
            company_id = res.company_id.id or self.env.company.id
            if 'name' in vals_list.keys():
                get_number=vals_list['name'].split('/')
                res.sequence_number=get_number[-1]
                res.sequence_prefix='/'.join(get_number[:-1]) + '/'
            payment_name=''

            # or (res.name == '/' and not isinstance(res.invoice_date, bool))
            if 'date' in vals_list.keys() and not isinstance(vals_list['date'], bool):
                    sequence_date = vals_list.get('date') or res.date
                    if res.payment_type == 'inbound':
                        if payment_name_prepared:
                            continue
                        get_sequence_object = self.env['ir.sequence'].sudo().search(
                            [('sequence_for', '=', 'receipt_voucher'), ('company_id', 'in', [company_id, False])],
                            limit=1, )
                        if res.name!='/' or res.name.upper()!='DRAFT' or res.name.upper()!='NEW':
                            payment_name=res.name
                        if res.name == '/' or res.name.upper() == 'DRAFT' or res.name.upper() == 'NEW':
                            payment_name = ''

                        if payment_name!='':
                            get_sequence = self.env['ir.sequence'].with_company(company_id).next_by_sequence_for(
                                'receipt_voucher',
                                'no',
                                sequence_date=sequence_date,
                            )

                            if get_sequence:
                                get_highest_inv = self.env['account.payment'].sudo().search([('payment_type', '=', 'inbound'),('id','!=',self.ids[0]), ('company_id', '=', company_id)],
                                                                                         limit=1,
                                                                                         order='id desc')
                                get_sequence = res._get_sequence(get_sequence_object, get_sequence, vals_list,get_highest_inv,payment_name)



                            if not get_sequence:
                                raise ValidationError(_("Sequence is not set for Receipt Voucher"))
                            res.name=get_sequence or _('/')

                    if res.payment_type == 'outbound':
                        if payment_name_prepared:
                            continue
                        get_sequence_object = self.env['ir.sequence'].sudo().search(
                            [('sequence_for', '=', 'payment_voucher'), ('company_id', 'in', [company_id, False])],
                            limit=1, )
                        if res.name != '/' or res.name.upper() != 'DRAFT' or res.name.upper() != 'NEW':
                            payment_name = res.name
                        if res.name == '/' or res.name.upper() == 'DRAFT' or res.name.upper() == 'NEW':
                            payment_name = ''

                        if payment_name != '':
                            get_sequence = self.env['ir.sequence'].with_company(company_id).next_by_sequence_for(
                                'payment_voucher',
                                sequence_date=sequence_date,
                            )

                            if get_sequence:
                                get_highest_inv = self.env['account.payment'].sudo().search([('payment_type', '=', 'outbound'),('id','!=',self.ids[0]), ('company_id', '=', company_id)],
                                                                                         limit=1,
                                                                                         order='id desc')
                                get_sequence = res._get_sequence(get_sequence_object, get_sequence, vals_list,get_highest_inv,payment_name)


                            if not get_sequence:
                                raise ValidationError(_("Sequence is not set for Payment Voucher"))
                            res.name = get_sequence or _('/')

                    


                    return rec



            
            
        return rec
