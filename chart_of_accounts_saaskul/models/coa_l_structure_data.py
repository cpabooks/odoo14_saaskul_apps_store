# -*- coding: utf-8 -*-
"""L1 Type / L2 IFRS Group catalog for CPABooks COA structure."""

# Max branch companies shown as separate BC values.
MAX_BRANCH_COMPANIES = 9

L1_TYPE_CODES = {
    'asset': ('1', 'Assets'),
    'liability': ('2', 'Liabilities'),
    'equity': ('3', 'Equity'),
    'income': ('4', 'Income'),
    'expense': ('5', 'Expenses'),
}

L1_BY_INTERNAL_GROUP = {
    'asset': '1',
    'liability': '2',
    'equity': '3',
    'income': '4',
    'expense': '5',
    'off_balance': '1',
}

# (group_code, label, keyword_patterns)
L2_CATALOG = {
    '1': [
        ('11', 'Fixed Assets', (
            r'fixed asset', r'\bppe\b', r'furniture', r'vehicle', r'equipment',
            r'building', r'leasehold', r'computer hardware', r'motor',
        )),
        ('12', 'Current Assets', (r'current asset',)),
        ('13', 'Trade and Other Receivables', (
            r'receivable', r'debtor', r'trade receivable',
        )),
        ('14', 'Inventory', (r'inventory', r'stock',)),
        ('15', 'Cash and Bank', (
            r'\bbank\b', r'\bcash\b', r'cheque', r'petty', r'liquidity',
        )),
        ('16', 'Intercompany Assets', (r'intercompany', r'interco', r'\bic\b')),
        ('17', 'Deposits', (r'deposit',)),
        ('18', 'Prepaid Expenses', (r'prepaid', r'prepayment', r'advance')),
        ('19', 'Other Assets', (r'other asset', r'accum', r'deprec', r'suspense')),
    ],
    '2': [
        ('21', 'Trade and Other Payables', (r'payable', r'creditor', r'trade payable')),
        ('22', 'Accruals', (r'accrual', r'accrued',)),
        ('23', 'Loans and Borrowings', (r'loan', r'borrowing', r'note payable')),
        ('24', 'VAT / Tax Payable', (r'\bvat\b', r'tax payable', r'withholding')),
        ('25', 'Intercompany Liabilities', (r'intercompany', r'interco', r'\bic\b')),
        ('26', 'Provision', (r'provision',)),
        ('27', 'Other Liabilities', (r'other liabilit',)),
    ],
    '3': [
        ('31', 'Share Capital', (r'share capital', r'capital stock')),
        ('32', 'Retained Earnings', (r'retained earning', r'retained profit')),
        ('33', 'Current Year Profit / Loss', (
            r'current year', r'profit.?loss', r'p&l reserve',
        )),
        ('34', 'Owner / Partner Current Account', (
            r'owner', r'partner', r'drawing', r'current account',
        )),
    ],
    '4': [
        ('41', 'Sales Revenue', (r'sales', r'revenue', r'turnover')),
        ('42', 'Service Income', (r'service income', r'consulting income')),
        ('43', 'Other Income', (r'other income',)),
        ('44', 'Discount / Rebate Income', (r'discount income', r'rebate income')),
    ],
    '5': [
        ('51', 'Cost of Sales', (r'cost of sales', r'\bcogs\b', r'cost of goods')),
        ('52', 'Direct Expenses', (r'direct expense', r'direct cost')),
        ('53', 'Staff Cost', (r'salary', r'payroll', r'wage', r'staff', r'gratuity')),
        ('54', 'Rent and Utilities', (r'rent', r'utility', r'utilities',)),
        ('55', 'Admin Expenses', (r'admin', r'office expense', r'general expense')),
        ('56', 'Finance Cost', (r'finance cost', r'interest expense', r'bank charge')),
        ('57', 'Depreciation', (r'deprec', r'amort',)),
        ('58', 'Other Expenses', (r'other expense',)),
    ],
}

L2_DEFAULT_BY_TYPE = {
    '1': '19',
    '2': '27',
    '3': '34',
    '4': '43',
    '5': '58',
}

COA_STRUCTURE_HELP = (
    'L1 Type (1 digit): 1 Assets, 2 Liabilities, 3 Equity, 4 Income, 5 Expense\n'
    'L2 Group (2 digits): IFRS group, e.g. 11 Fixed Assets, 58 Other Expenses\n'
    'L3 Ledger (4 digits): Group code + sequence, e.g. 5801. BC is separate.'
)
