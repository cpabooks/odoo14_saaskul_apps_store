import re
from datetime import datetime, timedelta
from decimal import Decimal

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.addons.cpabooks_sequences.models.sequence_format import replace_prefix_placeholders


class StockPickingInheritance(models.Model):
    _inherit = 'stock.picking'

    system_admin = fields.Boolean(compute="_get_system_admin")
    name = fields.Char(
        'Reference', default='Draft',
        copy=False, index=True, readonly=True)

    # @api.depends('state')
    # def _get_system_admin(self):
    #     for rec in self:
    #         get_admin_power_group = self.env['res.groups'].sudo().search([('name', '=ilike', 'Sequence Editor')])
    #         if get_admin_power_group:
    #             if self.env.user.has_group('base.group_system') or self.env.user.id in get_admin_power_group.users.ids:
    #                 rec.system_admin = True
    #             else:
    #                 rec.system_admin = False
    #         else:
    #             if self.env.user.has_group('base.group_system'):
    #                 rec.system_admin = True
    #             else:
    #                 rec.system_admin = False
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

    @api.model
    def create(self, vals_list):
        print(vals_list)
        res = super(StockPickingInheritance, self).create(vals_list)
        seq_vals = dict(vals_list) if isinstance(vals_list, dict) else {}
        if not seq_vals.get('scheduled_date'):
            seq_vals['scheduled_date'] = res.scheduled_date or fields.Datetime.now()
        requested_name = seq_vals.get('name')
        if not requested_name or res._cpabooks_is_sequence_placeholder(requested_name):
            res.name = res._cpabooks_next_picking_name(seq_vals.get('scheduled_date'))
        elif res._cpabooks_picking_name_exists(res.name):
            raise ValidationError(_("Reference must be unique per company!"))
        res.flush(['name'])
        return res

    def _cpabooks_is_sequence_placeholder(self, value):
        return not value or value in ('/', 'DRAFT', 'draft', 'Draft', 'NEW', 'new', 'New')

    def _cpabooks_sequence_for_picking(self):
        self.ensure_one()
        # Material Issue / Return Notes use dedicated MIN / MRN sequences.
        if getattr(self, 'is_stock_return_note', False) or getattr(self, 'stock_issue_picking_id', False):
            return 'stock_return_note'
        if getattr(self, 'is_stock_issue_note', False) or getattr(self, 'issue_project_task_id', False):
            return 'stock_issue_note'
        if self.picking_type_code == 'incoming':
            return 'incoming'
        if self.picking_type_code == 'outgoing':
            return 'outgoing'
        return 'internal'

    def _cpabooks_picking_sequence(self):
        self.ensure_one()
        company_id = self.company_id.id or self.env.company.id
        sequence_for = self._cpabooks_sequence_for_picking()
        sequence = self.env['ir.sequence'].sudo().search([
            ('sequence_for', '=', sequence_for),
            ('company_id', '=', company_id),
        ], limit=1)
        if not sequence:
            sequence = self.env['ir.sequence'].sudo().search([
                ('sequence_for', '=', sequence_for),
                ('company_id', '=', False),
            ], limit=1)
        if not sequence:
            labels = {
                'incoming': _("receive products"),
                'outgoing': _("delivered products"),
                'internal': _("transfer products"),
                'stock_issue_note': _("material issue notes (MIN)"),
                'stock_return_note': _("material return notes (MRN)"),
            }
            raise ValidationError(_("Sequence is not set for %s") % labels.get(sequence_for, sequence_for))
        return sequence

    def _cpabooks_sequence_datetime(self, value=None):
        self.ensure_one()
        value = value or self.scheduled_date or fields.Datetime.now()
        return self.env['common.method'].parse_sequence_datetime(value, offset_hours=0)

    def _cpabooks_picking_prefix(self, sequence, date_value=None):
        self.ensure_one()
        ref = self._cpabooks_sequence_datetime(date_value)
        return replace_prefix_placeholders(
            sequence.prefix or '',
            ref.date() if isinstance(ref, datetime) else ref,
            sequence._cpabooks_year_digits(),
        )

    def _cpabooks_picking_name_exists(self, name):
        self.ensure_one()
        return bool(self.sudo().search_count([
            ('id', '!=', self.id),
            ('name', '=', name),
            ('company_id', '=', self.company_id.id),
        ]))

    def _cpabooks_highest_picking_number(self, prefix):
        self.ensure_one()
        pickings = self.sudo().search([
            ('id', '!=', self.id),
            ('company_id', '=', self.company_id.id),
            ('name', '=like', prefix + '%'),
        ])
        pattern = re.compile(r'^%s(\d+)$' % re.escape(prefix))
        highest = 0
        for picking in pickings:
            match = pattern.match(picking.name or '')
            if match:
                highest = max(highest, int(match.group(1)))
        return highest

    def _cpabooks_next_picking_name(self, date_value=None):
        self.ensure_one()
        sequence = self._cpabooks_picking_sequence()
        prefix = self._cpabooks_picking_prefix(sequence, date_value)
        padding = int(sequence.padding or 0)
        next_number = self._cpabooks_highest_picking_number(prefix) + 1
        while True:
            number = str(next_number).zfill(padding) if padding else str(next_number)
            candidate = '%s%s' % (prefix, number)
            if not self._cpabooks_picking_name_exists(candidate):
                next_actual = max(int(sequence.number_next_actual or 1), next_number + 1)
                sequence.sudo().write({'number_next_actual': next_actual})
                return candidate
            next_number += 1

    def _cpabooks_picking_prefix_matches_date(self, name, sequence, date_value=None):
        self.ensure_one()
        return bool(name and name.startswith(self._cpabooks_picking_prefix(sequence, date_value)))

    def _get_sequence_picking(self, get_sequence_object, get_sequence, vals_list, get_highest_picking, picking_name):
        common_method = self.env['common.method']
        model = 'stock.picking'
        if '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern == 'month_year':
            if picking_name != '':
                split_picking_name = picking_name.split('/')
                split_seq = get_sequence.split('/')
                split_picking_name_last_value = split_picking_name[-1]
                split_seq[-1] = split_picking_name_last_value
                if get_highest_picking and get_highest_picking.name != '/':
                    split_highest_inv = get_highest_picking.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
                else:
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                # split_highest_inv = get_highest_picking.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            if 'scheduled_date' in vals_list.keys() and not isinstance(vals_list['scheduled_date'],
                                                                       bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(vals_list['scheduled_date']).split('-')[0]
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['scheduled_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(vals_list['scheduled_date']).split('-')[1]
                    get_sequence = "/".join(split_seq)
            if 'scheduled_date' not in vals_list.keys() and not isinstance(self.scheduled_date,
                                                                           bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(self.scheduled_date).split('-')[0]
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['scheduled_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(self.scheduled_date).split('-')[1]
                    get_sequence = "/".join(split_seq)
            return get_sequence

        elif '/%(year)s/%(month)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern == 'month_year_monthly':
            split_seq_obj = get_sequence_object.prefix.split('/')
            get_year_index = split_seq_obj.index('%(year)s')
            get_month_index = split_seq_obj.index('%(month)s')
            split_inv_name = []
            for i in range(get_year_index + 3):
                split_inv_name.append('')
            if picking_name != '':
                split_inv_name = picking_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                if get_highest_picking and get_highest_picking.name != '/':
                    split_highest_inv = get_highest_picking.name.split('/')
                    # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
                else:
                    get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
                # split_highest_inv = get_highest_picking.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
            if 'scheduled_date' in vals_list.keys() and not isinstance(vals_list['scheduled_date'],
                                                                       bool):
                date_obj = self.env['common.method'].parse_sequence_datetime(vals_list['scheduled_date'])

                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(date_obj).split('-')[0]
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['scheduled_date']).split('-')[1]) > -1:
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
                    if str(date_obj.date().year) == split_inv_name[get_year_index] and date_obj.date().month == int(split_inv_name[get_month_index]):
                        orginal_sequence = picking_name.split('/')
                    else:
                        get_highest_sequence = common_method.get_highest_seq_for_month_year_monthly(get_sequence_object,
                                                                                                    date_obj, model)

                        # get_highest_sequence = self.env['stock.picking'].search(
                        #     [('name', 'like', without_last_index_sequence + '%'), ('id', '!=', self.id)],
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
            if 'scheduled_date' not in vals_list.keys() and not isinstance(self.scheduled_date,
                                                                           bool):
                date_obj=self.scheduled_date+timedelta(hours=6)
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(date_obj).split('-')[0]
                    get_sequence = "/".join(split_seq)
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['scheduled_date']).split('-')[1]) > -1:
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
                    if str(date_obj.year) == split_inv_name[get_year_index] and date_obj.month == int(
                            split_inv_name[get_month_index]):
                        orginal_sequence = picking_name.split('/')
                    else:
                        get_highest_sequence = common_method.get_highest_seq_for_month_year_monthly(get_sequence_object,
                                                                                                    date_obj, model)

                        # get_highest_sequence = self.env['stock.picking'].search(
                        #     [('name', 'like', without_last_index_sequence + '%'), ('id', '!=', self.id)],
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
            if picking_name != '':
                split_inv_name = picking_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                # if get_highest_picking and get_highest_picking.name!='/':
                #     split_highest_inv=get_highest_picking.name.split('/')
                # get_sequence_object.number_next_actual=int(split_highest_inv[-1])+1
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
            if 'scheduled_date' in vals_list.keys() and not isinstance(vals_list['scheduled_date'],
                                                                       bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(vals_list['scheduled_date']).split('-')[0]
                    get_sequence = "/".join(split_seq)

            if 'scheduled_date' not in vals_list.keys() and not isinstance(self.scheduled_date,
                                                                           bool):
                if get_sequence.find(str(datetime.now().year)) > -1:
                    idx = split_seq.index(str(datetime.now().year))
                    split_seq[idx] = str(self.scheduled_date).split('-')[0]
                    get_sequence = "/".join(split_seq)

            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(year)s/' in get_sequence_object.prefix and get_sequence_object.sequence_pattern == 'year_yearly':
            split_seq_obj = get_sequence_object.prefix.split('/')
            get_year_index = split_seq_obj.index('%(year)s')
            split_inv_name = []
            for i in range(get_year_index + 1):
                split_inv_name.append('')
            split_inv_name.append('')
            if picking_name != '':
                split_inv_name = picking_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                # if get_highest_picking and get_highest_picking.name != '/':
                #     split_highest_inv = get_highest_picking.name.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            if 'scheduled_date' in vals_list.keys() and not isinstance(vals_list['scheduled_date'],
                                                                       bool):
                date_obj = self.env['common.method'].parse_sequence_datetime(vals_list['scheduled_date'])

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
                        orginal_sequence = picking_name.split('/')
                    else:
                        get_highest_sequence = common_method.get_highest_seq_for_year_yearly(get_sequence_object,
                                                                                             date_obj, model)

                        # get_highest_sequence = self.env['stock.picking'].search(
                        #     [('name', 'like', without_last_index_sequence + '%'), ('id', '!=', self.id)],
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

            if 'scheduled_date' not in vals_list.keys() and not isinstance(self.scheduled_date,
                                                                           bool):
                date_obj = self.scheduled_date + timedelta(hours=6)
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
                        orginal_sequence = picking_name.split('/')
                    else:
                        get_highest_sequence = common_method.get_highest_seq_for_year_yearly(get_sequence_object,
                                                                                             date_obj, model)
                        #
                        # get_highest_sequence = self.env['stock.picking'].search(
                        #     [('name', 'like', without_last_index_sequence + '%'), ('id', '!=', self.id)],
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
                            # divide_by = 100000
                            # if sequence_padding == 4:
                            #     divide_by = 10000
                            # if sequence_padding == 3:
                            #     divide_by = 1000
                            # if sequence_padding == 2:
                            #     divide_by = 100
                            # if sequence_padding == 1:
                            #     divide_by = 10
                            number = (get_highest_sequence_no + 1) / divide_by
                            dec_string = str(round(Decimal(number), sequence_padding))
                            string_convert = dec_string.split('.')[1]
                            orginal_sequence[-1] = string_convert

                    get_sequence = "/".join(orginal_sequence)
                    # endregion

            return get_sequence

        elif '/%(year)s/%(month)s/' not in get_sequence_object.prefix and '/%(month)s/' in get_sequence_object.prefix:
            if picking_name != '':
                split_inv_name = picking_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                # if get_highest_picking and get_highest_picking.name != '/':
                #     split_highest_inv = get_highest_picking.name.split('/')
                #     get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
            if 'scheduled_date' in vals_list.keys() and not isinstance(vals_list['scheduled_date'],
                                                                       bool):
                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['scheduled_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(vals_list['scheduled_date']).split('-')[1]
                    get_sequence = "/".join(split_seq)
            if 'scheduled_date' not in vals_list.keys() and not isinstance(self.scheduled_date,
                                                                           bool):

                if get_sequence.find(str(datetime.now().month)) > -1:
                    # if not get_sequence.find(str(vals_list['scheduled_date']).split('-')[1]) > -1:
                    month = datetime.now().month
                    str_month = str(datetime.now().month)
                    if month < 10:
                        str_month = str(0) + str_month
                    idx = split_seq.index(str_month)
                    split_seq[idx] = str(self.scheduled_date).split('-')[1]
                    get_sequence = "/".join(split_seq)
            return get_sequence


        else:
            if picking_name != '':
                split_inv_name = picking_name.split('/')
                split_seq = get_sequence.split('/')
                split_inv_name_last_value = split_inv_name[-1]
                split_seq[-1] = split_inv_name_last_value
                get_sequence = "/".join(split_seq)
                # if get_highest_picking and get_highest_picking.name != '/':
                #     split_highest_inv = get_highest_picking.name.split('/')
                # get_sequence_object.number_next_actual = int(split_highest_inv[-1]) + 1
                get_sequence_object.number_next_actual = get_sequence_object.number_next_actual - 1
            else:
                split_seq = get_sequence.split('/')
                get_sequence = "/".join(split_seq)
            return get_sequence

    def write(self, vals_list):
        print(vals_list)

        rec = super(StockPickingInheritance, self).write(vals_list)
        for res in self:
            if 'name' in vals_list and not res._cpabooks_is_sequence_placeholder(res.name):
                if res._cpabooks_picking_name_exists(res.name):
                    raise ValidationError(_("Reference must be unique per company!"))
            if res._cpabooks_is_sequence_placeholder(res.name):
                res.name = res._cpabooks_next_picking_name(vals_list.get('scheduled_date'))
                continue
            if 'scheduled_date' in vals_list and vals_list.get('scheduled_date'):
                sequence = res._cpabooks_picking_sequence()
                if not res._cpabooks_picking_prefix_matches_date(
                    res.name, sequence, vals_list.get('scheduled_date'),
                ):
                    res.name = res._cpabooks_next_picking_name(vals_list.get('scheduled_date'))
        return rec
