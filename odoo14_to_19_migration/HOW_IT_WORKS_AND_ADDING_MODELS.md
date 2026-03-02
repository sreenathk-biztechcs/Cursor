# How the Odoo 14 → 19 Migration Script Works (Step by Step)

## 1. High-Level Architecture

The migration tool:

1. **Connects** to two Odoo instances via **XML-RPC** (source = Odoo 14, target = Odoo 19).
2. **Runs a fixed sequence of steps** (currencies → accounts → taxes → … → verify).
3. **Maps source record IDs to target IDs** in a JSON file (`id_mapping.json`) so:
   - Re-runs skip already-migrated records (resumability).
   - Later steps can resolve Many2one references (e.g. move → partner, journal).
4. **Supports multi-company → single-company**: many companies on source are consolidated into one company on target, with prefixes (e.g. `[ALP] INV/0001`) and optional analytic tracking.

---

## 2. Step-by-Step: What Happens When You Run the Script

### 2.1 Entry Point and Configuration

- **Run**: `python -m odoo14_to_19_migration [--step STEP] [--dry-run] [--verbose]`
- **Entry**: `__main__.py` calls `main()` from `main.py`.
- **Config**: `config.py` holds URLs, DB names, credentials, company IDs, batch size, etc. Values can be overridden by environment variables (e.g. `SOURCE_URL`, `SOURCE_DB`).

### 2.2 Main Flow (main.py)

1. **Parse arguments**: `--step` (default `all`), `--dry-run`, `--verbose`, `--full-refresh`.
2. **Load ID mapper**: `IDMapper(config.MAPPING_FILE)` loads `id_mapping.json`. If `--full-refresh`, the mapper is cleared (use only with an empty target DB).
3. **Connect to source and target**: Two `OdooRPC` instances (see `rpc_client.py`) authenticate and store `uid` and server version.
4. **Validate connections**: Ensures source has `account` module, target is v17+, and URLs are not swapped.
5. **Build company map**: `company_setup.build_company_map(source, target, mapper)`:
   - Resolves which source companies to migrate (`SOURCE_COMPANY_IDS`: `all` or `"1,2,3"`).
   - For each company: id, name, short prefix (e.g. ALP), and optionally creates an analytic account on target for tracking (`analytic_id`).
6. **Determine steps**: If `--step all`, use `STEP_ORDER`; else split `--step` by comma and validate step names.
7. **Run migration**: For each step:
   - If step is `verify`: call `verify_balances(...)` (compare trial balance), then continue.
   - Else: get the migrator class from `STEP_CLASSES`, instantiate it with `(source, target, mapper, company_map)`, call `migrator.run()`, then `mapper.save()`.

### 2.3 RPC Layer (rpc_client.py)

- **OdooRPC**: Wraps XML-RPC `common` and `object` endpoints.
- **connect()**: Authenticates, stores `uid`, reads server version (and major version for checks).
- **Methods**: `search`, `read`, `search_read`, `search_count`, `create`, `write`, `execute`, `fields_get`, `get_xml_id`, `resolve_xml_id`, `model_exists`.
- Retries on transient RPC/connection errors.

### 2.4 ID Mapper (id_mapper.py)

- **Structure**: `_map[model][str(source_id)] = target_id` (e.g. `_map["res.partner"]["5"] = 12`).
- **Operations**: `set(model, source_id, target_id)`, `get(model, source_id)`, `get_all(model)`, `has(model, source_id)`, `resolve(model, many2one_value)`, `clear()`, `save()`.
- **Role**: Every migrator that creates a record must call `mapper.set(model, source_id, tid)` so later steps can resolve FKs. Resumability: if `mapper.has(model, sid)` then skip or reuse existing target id.

### 2.5 Company Setup (company_setup.py)

- **resolve_source_company_ids()**: From `SOURCE_COMPANY_IDS` returns list of company IDs (or all companies from source).
- **build_company_map()**: For each source company, builds `{ id, name, short, analytic_id }`. Short names come from `COMPANY_SHORT_NAMES` or are auto-generated. If `ANALYTIC_TRACKING`, creates an analytic plan and one analytic account per company on target and fills `analytic_id`.

### 2.6 Base Migrator (base_migrator.py)

All migrators inherit from **BaseMigrator**:

- **Constructor**: Receives `source`, `target`, `mapper`, and `company_map`; reads `DRY_RUN`, `BATCH_SIZE` from config.
- **Field detection**: `_get_fields(rpc, prefix, model)` (cached), `_target_has_field(model, field)`, `_source_has_field(model, field)` to handle schema differences (e.g. Odoo 14 vs 19).
- **Company helpers**: `_add_company_to_domain`, `_add_company_to_vals`, `_src_company_domain`, `_src_company_domain_with_false`, `get_source_company_ids()`, `get_company_short()`, `get_company_name()`, `get_company_analytic_id()`, `prefix_ref()`.
- **ID resolution**: `_resolve_id(model, many2one_value)`, `_resolve_ids(model, ids)`, `_m2o(val)`, `_m2o_company(val)`.
- **Batching**: `_iter_batches(model, domain, fields, order)` yields batches of records from source.
- **Lookups**: `_find_target_by_code(model, code, company_id)`, `_find_target_by_name(model, name, company_id)`.
- **Create**: `_safe_create(model, vals, source_id)` strips unknown target fields, and if not dry-run creates the record and calls `mapper.set(model, source_id, tid)`.

Each migrator implements **run()** and uses these helpers.

### 2.7 Migration Steps (Order and Purpose)

| Step             | Model(s)                    | Purpose |
|------------------|-----------------------------|--------|
| currencies       | res.currency, res.currency.rate | Merge by ISO code; needed for moves/partners |
| accounts         | account.group, account.account | Chart of accounts; merge by code; map user_type_id → account_type |
| taxes            | account.tax.group, account.tax | Merge by name+type |
| journals         | account.journal             | One journal set per company; optional prefix (ALP-SAJ) |
| fiscal           | account.fiscal.position     | Merge by name |
| payment_terms    | account.payment.term (+ lines) | Merge by name; map old line fields → nb_days, delay_type |
| partners         | res.partner, res.partner.bank | Deduplicate by VAT/ref/email/name; accounting properties |
| moves            | account.move, account.move.line | Invoices/bills/entries; ref prefix; analytic_distribution |
| payments         | account.payment             | Ref prefix; link to moves |
| bank_statements  | account.bank.statement      | Name prefix |
| verify           | —                           | Compare trial balance source vs target |

Dependencies: partners need accounts, payment_terms, fiscal; moves need journals, partners, accounts, taxes, payment_terms, fiscal; payments need moves, partners; etc. So the **order** is fixed.

---

## 3. How to Add New Models (Sale Order, Order Line, Pricelist, Any Module)

To add **sale.order**, **sale.order.line**, **discount pricelist** (product.pricelist, product.pricelist.item), or any other model, you follow the same pattern: **create a new migrator class, register it in the step order and step classes, and respect dependencies**.

### 3.1 Dependency Order

- **product.pricelist** (and **product.pricelist.item**): Can run after **currencies** and **partners** (if pricelist is partner-specific). No accounting required.
- **sale.order**: Depends on **partners**, **currencies**, **product.pricelist** (if you use pricelists on SO), and optionally **account** (fiscal position, etc.). So: after **partners** (and after a new **pricelist** step if you add it).
- **sale.order.line**: Migrated as part of **sale.order** (one2many: order + lines in one create, or create order then create lines with `order_id`). Depends on **product.product** / **product.template** if you reference them (products are often not migrated; you may only link if product exists on target).

So a possible new order:

```
currencies → accounts → taxes → journals → fiscal → payment_terms
→ partners → pricelists → sale_orders → moves → payments → bank_statements → verify
```

(You can place **pricelists** and **sale_orders** where they fit; e.g. after **partners** and before **moves**.)

### 3.2 Steps to Add a New Migrator (e.g. Sale Order)

#### Step 1: Create the migrator file

Create `migrators/sale_orders.py` (or `migrators/pricelists.py` for pricelists).

#### Step 2: Implement the migrator class

- Inherit from **BaseMigrator**.
- Set **name** (e.g. `"sale_orders"`); this is the step name used in `--step`.
- Implement **run()**:
  - Loop over `self.get_source_company_ids()` if the model is company-specific (e.g. sale.order).
  - For each record:
    - Skip if `self.mapper.has("sale.order", source_id)`.
    - Optionally check for existing target record (e.g. by name/ref) to avoid duplicates.
    - Build **vals** for target: resolve every Many2one (partner, pricelist, currency, company, etc.) with `_resolve_id("model", value)`.
    - For one2many lines (order lines): fetch source lines, build list of dicts or commands `(0, 0, line_vals)`, and set `vals["order_line"] = commands` (or the correct field name in Odoo 19).
    - Call `tid = self._safe_create("sale.order", vals, source_id)`.
    - If you create lines in a second pass instead of inline, create the order first, then create each line with `order_id = tid` and optionally `mapper.set("sale.order.line", line_source_id, line_target_id)` if you need to reference lines later.

Use **BaseMigrator** helpers:

- `_resolve_id("res.partner", record["partner_id"])` for partner.
- `_resolve_id("product.pricelist", record["pricelist_id"])` for pricelist.
- `_iter_batches("sale.order", domain, fields=...)` to read in batches.
- `_safe_create("sale.order", vals, sid)` to create and register mapping.
- `prefix_ref(record.get("client_order_ref"), company_id)` if you want company prefix on refs.

#### Step 3: Register the step in main.py

- Append the step name to **STEP_ORDER** in the correct position (e.g. after `partners`, before `moves`):

```python
STEP_ORDER = [
    "currencies",
    "accounts",
    "taxes",
    "journals",
    "fiscal",
    "payment_terms",
    "partners",
    "pricelists",    # new
    "sale_orders",   # new
    "moves",
    "payments",
    "bank_statements",
    "verify",
]
```

- Add the class to **STEP_CLASSES**:

```python
from .migrators import (
    ...
    PricelistMigrator,
    SaleOrderMigrator,
)

STEP_CLASSES = {
    ...
    "pricelists": PricelistMigrator,
    "sale_orders": SaleOrderMigrator,
}
```

#### Step 4: Export the new migrator in migrators/__init__.py

```python
from .pricelists import PricelistMigrator
from .sale_orders import SaleOrderMigrator

__all__ = [
    ...
    "PricelistMigrator",
    "SaleOrderMigrator",
]
```

### 3.3 Field and Schema Differences (Odoo 14 vs 19)

- Use **`_source_has_field`** and **`_target_has_field`** before using a field.
- If a field was renamed or changed (e.g. selection values), map in your migrator (see `payment_terms.py` for `days`/`option` → `nb_days`/`delay_type`).
- For **product.pricelist** and **product.pricelist.item**, check in Odoo 19 docs whether:
  - `discount_policy` (e.g. with_discount / without_discount) still exists.
  - Item fields (e.g. `compute_price`, `fixed_price`, `percent_price`, `base`) are the same or renamed.

### 3.4 Handling Dependencies (e.g. Products)

- **Products**: The README says products are not migrated; only referenced if they exist on target. In **sale.order.line** you can:
  - Resolve `product_id` with `_resolve_id("product.product", line["product_id"])` and only set it if the product exists on target; otherwise create the line with name/description only (no product link).
- **Pricelist**: If you add **PricelistMigrator**, run it before **sale_orders** and map `sale.order.pricelist_id` to the new pricelist target id.

### 3.5 Multi-Company and Deduplication

- **Company-specific models** (sale.order, pricelist): Loop over `get_source_company_ids()`, restrict domain with `_src_company_domain("sale.order", company_id)`, and set `company_id` on target to `config.TARGET_COMPANY_ID` (via `_add_company_to_vals`).
- **Merge/deduplicate**: Like partners (by VAT/ref) or payment terms (by name), you can search target for an existing record by a unique key and reuse it: `mapper.set(model, source_id, existing_tid)` and skip create.

### 3.6 Example Skeleton: sale_orders.py

```python
"""
Migrate sale.order and sale.order.line — multi-company aware.
Depends on: partners, currencies; optional: product.pricelist, product.product.
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)


class SaleOrderMigrator(BaseMigrator):
    name = "sale_orders"

    def run(self):
        logger.info("=== Migrating Sale Orders ===")
        for company_id in self.get_source_company_ids():
            self._migrate_orders(company_id)
        self.log_summary()

    def _migrate_orders(self, company_id: int):
        domain = self._src_company_domain("sale.order", company_id)
        fields = [
            "name", "partner_id", "date_order", "state", "pricelist_id",
            "currency_id", "order_line", "company_id", "client_order_ref",
            "fiscal_position_id", "payment_term_id", ...
        ]
        for batch in self._iter_batches("sale.order", domain, fields=fields):
            for order in batch:
                self._migrate_single_order(order, company_id)
            self.mapper.save()

    def _migrate_single_order(self, order: dict, company_id: int):
        sid = order["id"]
        if self.mapper.has("sale.order", sid):
            self.skipped += 1
            return
        partner_tid = self._resolve_id("res.partner", order.get("partner_id"))
        if not partner_tid:
            logger.warning("[sale_orders] Skipping order %s: no partner", order.get("name"))
            self.errors += 1
            return
        pricelist_tid = self._resolve_id("product.pricelist", order.get("pricelist_id"))
        currency_tid = self._resolve_id("res.currency", order.get("currency_id"))
        vals = {
            "partner_id": partner_tid,
            "date_order": order.get("date_order"),
            # ... other scalar fields; resolve M2o with _resolve_id
        }
        self._add_company_to_vals("sale.order", vals, config.TARGET_COMPANY_ID)
        if pricelist_tid:
            vals["pricelist_id"] = pricelist_tid
        if currency_tid:
            vals["currency_id"] = currency_tid
        # Build order_line commands from order["order_line"] (read lines, resolve product_id, etc.)
        line_commands = self._build_order_line_commands(order.get("order_line", []))
        if line_commands:
            vals["order_line"] = line_commands
        self._safe_create("sale.order", vals, sid)
```

You would implement `_build_order_line_commands` to read `sale.order.line` from source, resolve product/uom/tax, and return `[(0, 0, {...}), ...]`.

---

## 4. Summary Checklist for Adding a New Module/Model

1. **Decide dependency order**: Which existing steps must run first (partners, currencies, pricelists, etc.)?
2. **Create `migrators/<name>.py`**: Class inheriting **BaseMigrator**, implement **run()** and any helper methods.
3. **Resolve all Many2one fields** with `_resolve_id` / `_resolve_ids` and only set them if the target record exists (or you created it in an earlier step).
4. **Handle one2many** by building command list `(0, 0, line_vals)` and setting the relation field on the parent vals; or create child records after parent and map IDs if needed.
5. **Resumability**: Always check `mapper.has(model, source_id)` and skip or reuse existing target id.
6. **Schema differences**: Use `_source_has_field` / `_target_has_field` and map old field names/values to new (e.g. payment term lines, account types).
7. **Register step**: Add to **STEP_ORDER** and **STEP_CLASSES** in `main.py`, and export in `migrators/__init__.py`.
8. **Run**: `python -m odoo14_to_19_migration --step pricelists,sale_orders` or include in full run.

This is the same pattern used for sale order, order line, discount pricelist, and any other dependent module: one migrator per logical “step”, correct order, and consistent use of the ID mapper and base helpers.



MIGRATION SCRIPT – HOW TO RUN

1) Dry Run First (Recommended)
--------------------------------

    python -m odoo14_to_19_migration --dry-run --verbose

Options:
    --dry-run
        • No writes to target database
        • Only logs what would be created

    --verbose
        • Sets log level to DEBUG
        • Shows detailed execution output

Use this first to:
    • Confirm source/target connections
    • Validate configuration
    • Preview what will be migrated


2) Full Migration with Full Refresh
-------------------------------------

    python -m odoo14_to_19_migration --full-refresh

What it does:
    • Clears id_mapping.json
    • Runs all migration steps from scratch

IMPORTANT:
    • Use only when target DB is empty
    • Or when you accept possible duplicates
    • Script will show a warning before proceeding

If resuming a migration:
    • Run without --full-refresh
    • Existing id_mapping.json will be reused


3) Run Individual Steps
-------------------------

Single step:

    python -m odoo14_to_19_migration --step accounts

Multiple steps (comma-separated):

    python -m odoo14_to_19_migration --step currencies,accounts,taxes

Notes:
    • Spaces after commas are allowed
    • The script strips extra spaces automatically

Valid step names:

    currencies
    accounts
    taxes
    journals
    fiscal
    payment_terms
    partners
    moves
    payments
    bank_statements
    verify


4) Verify Post-Migration
--------------------------

    python -m odoo14_to_19_migration --step verify

What it does:
    • Compares trial balance
    • Checks posted move lines
    • Validates debit/credit totals
    • Compares source vs target

Run this after the main migration completes.


---------------------------------------
SUGGESTED ORDER OF USAGE
---------------------------------------

Step 1 – Dry Run

    python -m odoo14_to_19_migration --dry-run --verbose

Purpose:
    Check configuration and preview migration


Step 2 – Full Migration

    python -m odoo14_to_19_migration --full-refresh

Purpose:
    Full migration on empty target
    (or omit --full-refresh to resume)


Step 3 – Verification

    python -m odoo14_to_19_migration --step verify

Purpose:
    Validate balances after migration


---------------------------------------
IMPORTANT RECOMMENDATIONS
---------------------------------------

• Run from project root directory
      (so id_mapping.json path resolves correctly)

• Ensure configuration is set before running:
      Either in config.py
      OR via environment variables:

          SOURCE_*
          TARGET_*

• Always start with --dry-run before any real migration


---------------------------------------

Conclusion:

Yes — the commands you listed are correct
and represent a proper workflow for running the migration script safely.



Here’s a compact “cheat sheet” for all the scripts you have now, plus how you’ll run delta sync once we wire it in.
1) Where to run from
cd /home/sreenath.k/PycharmProjects/odoo19# (activate venv if needed)# source .venv/bin/activate
2) Control which companies to migrate
# All companies (default)export SOURCE_COMPANY_IDS="all"# Only a specific company (e.g. 3 = AppJetty)export SOURCE_COMPANY_IDS="3"# Or a subsetexport SOURCE_COMPANY_IDS="1,3,5"
3) Full migration (all steps, once)
python -m odoo14_to_19_migration --step all
Optional flags:
# Dry run (no writes)python -m odoo14_to_19_migration --step all --dry-run# More loggingpython -m odoo14_to_19_migration --step all -v
4) Run individual steps
# Single steppython -m odoo14_to_19_migration --step partnerspython -m odoo14_to_19_migration --step productspython -m odoo14_to_19_migration --step sale_orderspython -m odoo14_to_19_migration --step moves# Multiple steps in one runpython -m odoo14_to_19_migration --step "partners,products,sale_orders,moves"
(Any step name from STEP_ORDER is valid: currencies, accounts, taxes, journals, fiscal, payment_terms, partners, moves, payments, bank_statements, uom, product_attributes, product_categories, products, pricelists, delivery, loyalty_programs, sale_orders, verify plus the two below.)
5) Report what’s missing (no writes)
python -m odoo14_to_19_migration --step check_missing
This will log missing/unmapped:
res.partner
product.template + product.product
sale.order
account.move (customer invoices)
6) Fill missing data (create only, no duplicates)
python -m odoo14_to_19_migration --step fill_missing
This internally runs:
PartnerMigrator
ProductMigrator (templates + variants)
SaleOrderMigrator
MoveMigrator
and will:
Create any contacts/products/variants/SOs/invoices that are missing.
Reuse existing records when they match (no duplicates).
You can chain both:
python -m odoo14_to_19_migration --step "check_missing,fill_missing"
7) Delta sync (after we implement it)
Once we add DELTA_START + delta logic:
# Example: sync changes from 2026-03-05 00:00:00 onwardsexport DELTA_START="2026-03-05 00:00:00"export SOURCE_COMPANY_IDS="1,3"# Only update/create changed records for these models:python -m odoo14_to_19_migration --step "partners,products,sale_orders,moves,fill_missing"
That run will:
Read only records with create_date or write_date >= DELTA_START.
Create new records since that time.
Update existing records (without duplicating) where something changed.
Right now steps 1–6 are fully implemented; step 7 is the pattern we’ll use once we wire the delta filtering into the migrators.
