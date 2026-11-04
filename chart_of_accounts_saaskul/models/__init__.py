# -*- coding: utf-8 -*-
# Load legacy COA core (ported from deprecated cpabooks_chart_of_accounts) before v1 extensions.

from . import models
from . import function_call_coa
from . import coa_create
from . import account_account_identity
from . import account_account_coa_core
from . import product_product_coa
from . import product_with_analytic_acc_config
from . import visa_product
from . import product_template
from . import res_partner
from . import res_company
from . import account_group
from . import account_account
from . import account_move
from . import account_move_line
from . import coa_bulk_actions_wizard
from . import coa_reset_code_options_wizard
from . import coa_ifrs_coding
from . import coa_ifrs_coding_wizard
from . import coa_actions2

# account.report / account.coa.report live in account_reports (Enterprise)
from ..optional_deps import module_installed
if module_installed('account_reports'):
    from . import account_report_coa
    from . import account_coa_report_balance
else:
    import logging
    logging.getLogger(__name__).info(
        'chart_of_accounts_saaskul: skip account_report inherits '
        '(account_reports not installed)'
    )

from . import coa_setup_file
