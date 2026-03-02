"""
Configuration for Odoo 14 → 19 accounting data migration.
Supports multi-company (source) → single-company (target) consolidation.
Update the connection settings below for your source and target instances.
"""
import os

# ─── Source: Odoo 14 (your OLD system with existing data) ─────────────────────
SOURCE_URL = os.getenv("SOURCE_URL", "https://prelive-orbit.biztechcs.com/")
SOURCE_DB = os.getenv("SOURCE_DB", "prelive_feb_25_2026")
SOURCE_USER = os.getenv("SOURCE_USER", "admin")
SOURCE_PASSWORD = os.getenv("SOURCE_PASSWORD", "admin")

# ─── Target: Odoo 19 (your NEW system where data will be migrated to) ────────
TARGET_URL = os.getenv("TARGET_URL", "https://prelive-migration-orbit-03.biztechcs.com")
TARGET_DB = os.getenv("TARGET_DB", "26_feb_migration_prelive-orbit_03")
TARGET_USER = os.getenv("TARGET_USER", "admin")
TARGET_PASSWORD = os.getenv("TARGET_PASSWORD", "admin")

# ─── Migration Settings ──────────────────────────────────────────────────────
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MAPPING_FILE = os.getenv("MAPPING_FILE", "id_mapping.json")

# ─── Company Configuration ───────────────────────────────────────────────────
# Target: The single company in Odoo 19 where ALL data is consolidated
TARGET_COMPANY_ID = int(os.getenv("TARGET_COMPANY_ID", "1"))

# Source: Set to a comma-separated list of company IDs to migrate,
# or "all" to auto-discover every company in Odoo 14.
# Examples: "1,2,3,5,8" or "all"
SOURCE_COMPANY_IDS = os.getenv("SOURCE_COMPANY_IDS", "all")

# LEGACY — kept for backward compatibility; ignored when SOURCE_COMPANY_IDS is set
SOURCE_COMPANY_ID = int(os.getenv("SOURCE_COMPANY_ID", "1"))

# ─── Multi-Company → Single-Company Strategy ────────────────────────────────
# JOURNAL_PREFIX: Prefix each company's journals with a short code so they
#   stay separate in the single target company.
#   e.g. Company "Alpha Corp" with journal "SAJ" → journal code "ALP-SAJ"
# Set to False to merge journals with the same code into one.
JOURNAL_PREFIX_BY_COMPANY = False

# ANALYTIC_TRACKING: Create an analytic plan "Legacy Company" and an analytic
#   account per source company. Every migrated move line is tagged so you can
#   still run reports filtered by original company.
ANALYTIC_TRACKING = False

# REF_PREFIX: Prefix the `ref` field on moves/payments with the source company
#   short name so you can trace "[Alpha] INV/2024/0001" back to its origin.
REF_PREFIX_BY_COMPANY = True

# ─── Company Short Names ─────────────────────────────────────────────────────
# Map source company IDs to short prefixes (max 3-4 chars) used in journal
# codes, refs, etc.  Auto-detected if not provided — set manually here for
# cleaner prefixes.  Format: "1:ALP,2:BET,3:GAM"
COMPANY_SHORT_NAMES_RAW = os.getenv("COMPANY_SHORT_NAMES", "")
COMPANY_SHORT_NAMES: dict[int, str] = {}
if COMPANY_SHORT_NAMES_RAW:
    for pair in COMPANY_SHORT_NAMES_RAW.split(","):
        cid, prefix = pair.strip().split(":")
        COMPANY_SHORT_NAMES[int(cid)] = prefix.strip().upper()

# ─── Account Type Mapping ────────────────────────────────────────────────────
# Odoo 14 uses account.account.type (model) referenced via user_type_id.
# Odoo 17+ replaced this with a selection field `account_type` on account.account.
# This maps Odoo 14 account type XML-IDs → Odoo 19 account_type selection values.
ACCOUNT_TYPE_XMLID_MAP = {
    "account.data_account_type_receivable": "asset_receivable",
    "account.data_account_type_payable": "liability_payable",
    "account.data_account_type_liquidity": "asset_cash",
    "account.data_account_type_credit_card": "liability_credit_card",
    "account.data_account_type_current_assets": "asset_current",
    "account.data_account_type_non_current_assets": "asset_non_current",
    "account.data_account_type_prepayments": "asset_prepayments",
    "account.data_account_type_fixed_assets": "asset_fixed",
    "account.data_account_type_current_liabilities": "liability_current",
    "account.data_account_type_non_current_liabilities": "liability_non_current",
    "account.data_account_type_equity": "equity",
    "account.data_unaffected_earnings": "equity_unaffected",
    "account.data_account_type_revenue": "income",
    "account.data_account_type_other_income": "income_other",
    "account.data_account_type_expenses": "expense",
    "account.data_account_type_depreciation": "expense_depreciation",
    "account.data_account_type_direct_costs": "expense_direct_cost",
    "account.data_account_off_balance": "off_balance",
}

# Fallback: map by Odoo 14 account type name (case-insensitive) when XML-ID is unavailable
ACCOUNT_TYPE_NAME_MAP = {
    "receivable": "asset_receivable",
    "payable": "liability_payable",
    "bank and cash": "asset_cash",
    "credit card": "liability_credit_card",
    "current assets": "asset_current",
    "non-current assets": "asset_non_current",
    "prepayments": "asset_prepayments",
    "fixed assets": "asset_fixed",
    "current liabilities": "liability_current",
    "non-current liabilities": "liability_non_current",
    "equity": "equity",
    "current year earnings": "equity_unaffected",
    "income": "income",
    "other income": "income_other",
    "expenses": "expense",
    "depreciation": "expense_depreciation",
    "cost of revenue": "expense_direct_cost",
    "off-balance sheet": "off_balance",
}

# Internal type fallback (from account.account.type.type field in Odoo 14)
ACCOUNT_INTERNAL_TYPE_MAP = {
    "receivable": "asset_receivable",
    "payable": "liability_payable",
    "liquidity": "asset_cash",
    "other": "asset_current",  # generic fallback
}
