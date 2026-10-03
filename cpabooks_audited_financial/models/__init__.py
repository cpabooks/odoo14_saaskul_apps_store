# -*- coding: utf-8 -*-

from . import audited_financial_menu
from . import audited_financials
from . import account_account
from . import audited_financial_ctf_group
from . import audited_financial_fta
from . import audited_financial_ledger_merge
from . import audited_financial_l1_print_wizard
from . import audited_financial_print_setup_wizard
from . import audited_financial_ct_master
from . import account_move_line

try:
    from . import audited_financial_report
except Exception:  # pragma: no cover - keep core AFG loadable if report extras fail
    import logging
    logging.getLogger(__name__).exception(
        "cpabooks_audited_financial: could not load audited_financial_report extension"
    )
