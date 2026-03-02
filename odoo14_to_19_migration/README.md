# Odoo 14 → 19 Community Edition — Accounting Data Migration

Python migration tool that consolidates **complete accounting data** from
multiple companies in Odoo 14 CE into a **single company** in Odoo 19 CE
via XML-RPC.

## Multi-Company → Single-Company Consolidation

```
Odoo 14  (12 Companies)                    Odoo 19  (1 Company)
┌────────────────────────┐                ┌──────────────────────────────┐
│ Company A  [ALP]       │──┐             │                              │
│   SAJ, PUR, BNK, CSH   │  │  journals  │  ALP-SAJ, ALP-PUR, ALP-BNK  │
│   INV/0001 … INV/0500  │  ├──────────→ │  BET-SAJ, BET-PUR, BET-BNK  │
│ Company B  [BET]       │  │            │  …                            │
│   SAJ, PUR, BNK, CSH   │  │  ref field │  ref: [ALP] INV/2024/0001   │
│   INV/0001 … INV/0300  │  │  ────────→ │  ref: [BET] INV/2024/0001   │
│ …12 companies…         │──┘            │                              │
│                        │    analytics  │  Analytic Plan "Legacy Co."  │
│                        │    ────────→  │    [ALP] Alpha Trading Corp  │
│                        │               │    [BET] Beta Services Ltd    │
└────────────────────────┘                └──────────────────────────────┘
```

### How Sequences / Document Numbers Are Handled

| Concern | Solution |
|---------|----------|
| 12 companies each have `INV/0001` | Odoo 19 generates **new** unified numbers; originals stored in `ref` |
| Need to trace back to source company | `ref` is prefixed: `[ALP] INV/2024/0001` |
| Reports need per-company filtering | Each journal is prefixed (`ALP-SAJ`) AND an analytic account per company is auto-created |
| Chart of accounts overlap | Accounts with same code across companies → **merged** into one target account |
| Same partner in multiple companies | **Deduplicated** by VAT → ref → email → name |

## What Gets Migrated

| Step | Model(s) | Multi-Company Handling |
|------|----------|----------------------|
| `currencies` | `res.currency`, `res.currency.rate` | Merged by ISO code, rates from all companies |
| `accounts` | `account.group`, `account.account` | Same code → same account (merged) |
| `taxes` | `account.tax.group`, `account.tax` | Same name+type → same tax (merged) |
| `journals` | `account.journal` | **Prefixed per company**: `ALP-SAJ`, `BET-SAJ` |
| `fiscal` | `account.fiscal.position` | Merged by name |
| `payment_terms` | `account.payment.term` | Merged by name |
| `partners` | `res.partner`, `res.partner.bank` | **Deduplicated** across companies |
| `moves` | `account.move`, `account.move.line` | Ref prefixed, analytic tracking applied |
| `payments` | `account.payment` | Ref prefixed with company |
| `bank_statements` | `account.bank.statement` | Name prefixed with company |
| `verify` | — | Cross-company trial balance comparison |

## Quick Start

```bash
# 1. Set connection details
export SOURCE_URL=http://odoo14-server:8069
export SOURCE_DB=odoo14_production
export SOURCE_USER=admin
export SOURCE_PASSWORD=admin

export TARGET_URL=http://odoo19-server:8069
export TARGET_DB=odoo19_production
export TARGET_USER=admin
export TARGET_PASSWORD=admin

# 2. Configure multi-company (optional — defaults to "all")
export SOURCE_COMPANY_IDS=all          # or "1,2,3,5,8,12"
export TARGET_COMPANY_ID=1

# 3. Set company short names for clean prefixes (optional — auto-detected)
export COMPANY_SHORT_NAMES="1:ALP,2:BET,3:GAM,4:DEL,5:EPS"

# 4. Dry run
python -m odoo14_to_19_migration --dry-run --verbose

# 5. Run full migration
python -m odoo14_to_19_migration

# 6. Run specific steps
python -m odoo14_to_19_migration --step accounts
python -m odoo14_to_19_migration --step "currencies,accounts,taxes"

# 7. Verify
python -m odoo14_to_19_migration --step verify
```

## Configuration

All settings in `config.py`, overridable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SOURCE_URL` | `http://localhost:8014` | Odoo 14 base URL |
| `SOURCE_DB` | `odoo14_db` | Source database name |
| `TARGET_URL` | `http://localhost:8069` | Odoo 19 base URL |
| `TARGET_DB` | `odoo19_db` | Target database name |
| `SOURCE_COMPANY_IDS` | `all` | Source companies: `"all"` or `"1,2,3"` |
| `TARGET_COMPANY_ID` | `1` | Single target company |
| `COMPANY_SHORT_NAMES` | (auto) | `"1:ALP,2:BET"` for clean prefixes |
| `JOURNAL_PREFIX_BY_COMPANY` | `True` | Prefix journal codes per company |
| `ANALYTIC_TRACKING` | `True` | Create analytic accounts per legacy company |
| `REF_PREFIX_BY_COMPANY` | `True` | Prefix refs with `[ALP]` etc. |
| `BATCH_SIZE` | `100` | Records per RPC batch |
| `DRY_RUN` | `false` | Simulate without writes |
| `MAPPING_FILE` | `id_mapping.json` | Persistent ID map file |

## Resumability

`id_mapping.json` tracks `(model, source_id) → target_id`. Re-running any
step skips already-migrated records automatically.

## Migration Order

```
currencies → accounts → taxes → journals → fiscal → payment_terms
→ partners → moves → payments → bank_statements → verify
```

## Key Schema Changes Handled (v14 → v19)

| Change | Handling |
|--------|----------|
| `user_type_id` (M2o) → `account_type` (Selection) | Full 18-type mapping |
| `analytic_account_id` (M2o) → `analytic_distribution` (JSON) | Converted to `{id: 100.0}` |
| `payment_method_id` → `payment_method_line_id` | Journal-based lookup |
| Payment term `days`+`option` → `nb_days`+`delay_type` | Value mapping |
| `type_tax_use='none'` removed | Mapped to `'sale'` |

## Post-Migration Checklist

1. Run `--step verify` to compare trial balances
2. Review logs for `WARNING` and `ERROR` entries
3. Spot-check invoices/payments in Odoo 19 (search by `ref` field)
4. Run tax reports for the same period in both systems
5. Check partner receivable/payable balances
6. Use Odoo 19 reconciliation wizard if needed

## Limitations

- **Products** are not migrated (only referenced if they exist on target)
- **Attachments** (invoice PDFs, etc.) are not migrated
- **Reconciliation** data is not replayed automatically
- **Sequences** are fresh in Odoo 19; originals preserved in `ref`
- **Inter-company transactions** may need manual review after consolidation
