from collections import defaultdict

from odoo import api, models, fields, _
class Account(models.AbstractModel):
    _inherit = 'account.report'

    @api.model
    def _create_hierarchy(self, lines, options):
        """Compute the hierarchy based on account groups when the option is activated.

        The option is available only when there are account.group for the company.
        It should be called when before returning the lines to the client/templater.
        The lines are the result of _get_lines(). If there is a hierarchy, it is left
        untouched, only the lines related to an account.account are put in a hierarchy
        according to the account.group's and their prefixes.
        """
        unfold_all = self.env.context.get('print_mode') and len(options.get('unfolded_lines')) == 0 or options.get(
            'unfold_all')

        def add_to_hierarchy(lines, key, level, parent_id, hierarchy_parent, hierarchy):
            val_dict = hierarchy[key]
            # add the group totals
            lines.append({
                'id': val_dict['id'],
                'name': val_dict['name'] if len(val_dict['name']) < 60 else val_dict['name'][:60] + '...',
                'title_hover': val_dict['name'],
                'unfoldable': True,
                'unfolded': (
                    bool(unfold_all)
                    or val_dict['id'] in (options.get('unfolded_lines') or [])
                    or hierarchy_parent in (options.get('unfolded_lines') or [])
                ),
                'level': level,
                'parent_id': parent_id,
                'columns': [{'name': self.format_value(c) if isinstance(c, (int, float)) else c, 'no_format_name': c}
                            for c in val_dict['totals']],
            })
            # add every direct child group recursively
            for child in val_dict['children_codes']:
                add_to_hierarchy(lines, child, level + 1, val_dict['id'], hierarchy_parent, hierarchy)
            # add all the lines that are in this group but not in one of this group's children groups
            for l in val_dict['lines']:
                l['level'] = level + 1
                l['parent_id'] = val_dict['id']
            lines.extend(val_dict['lines'])

        def compute_hierarchy(lines, level, parent_id, hierarchy_parent):
            # put every line in each of its parents (from less global to more global) and compute the totals
            hierarchy = defaultdict(
                lambda: {'totals': [None] * len(lines[0]['columns']), 'lines': [], 'children_codes': set(), 'name': '',
                         'parent_id': None, 'id': ''})
            for line in lines:
                account_id = line.get('account_id') or line.get('id')
                if not isinstance(account_id, int):
                    continue
                account = self.env['account.account'].browse(account_id)
                codes = self.get_account_codes(account)  # id, name
                for code in codes:
                    hierarchy[code[0]]['id'] = 'hierarchy_' + str(code[0])
                    hierarchy[code[0]]['name'] = code[1]
                    for i, column in enumerate(line['columns']):
                        if isinstance(column.get('no_format_name', 0), (int, float)):
                            if hierarchy[code[0]]['totals'][i] is None:
                                hierarchy[code[0]]['totals'][i] = 0
                            hierarchy[code[0]]['totals'][i] += column.get('no_format_name', 0) if 'no_format_name' in column else column.get('no_format', 0)
                for code, child in zip(codes[:-1], codes[1:]):
                    hierarchy[code[0]]['children_codes'].add(child[0])
                    hierarchy[child[0]]['parent_id'] = hierarchy[code[0]]['id']
                hierarchy[codes[-1][0]]['lines'] += [line]
            # compute the tree-like structure by starting at the roots (being groups without parents)
            hierarchy_lines = []
            for root in [k for k, v in hierarchy.items() if not v['parent_id']]:
                add_to_hierarchy(hierarchy_lines, root, level, parent_id, hierarchy_parent, hierarchy)
            return hierarchy_lines

        def is_account_line(line):
            account_id = line.get('account_id')
            if isinstance(account_id, int):
                return True
            return line.get('caret_options') == 'account.account' and isinstance(line.get('id'), int)

        new_lines = []
        account_lines = []
        current_level = 0
        parent_id = 'root'
        for line in lines:
            if not is_account_line(line):
                # make the hierarchy with the lines we gathered, append it to the new lines and restart the gathering
                if account_lines:
                    new_lines.extend(compute_hierarchy(account_lines, current_level + 1, parent_id, parent_id))
                account_lines = []
                new_lines.append(line)
                current_level = line['level']
                parent_id = line['id']
            else:
                # gather all the lines we can create a hierarchy on
                account_lines.append(line)
        # do it one last time for the gathered lines remaining
        if account_lines:
            new_lines.extend(compute_hierarchy(account_lines, current_level + 1, parent_id, parent_id))
        return new_lines
