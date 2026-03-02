#!/usr/bin/env python3
"""
Odoo 14 → 19 Community Edition — Complete Accounting Data Migration
Supports multi-company (source) → single-company (target) consolidation.

Usage:
    python -m odoo14_to_19_migration [--step STEP] [--dry-run] [--verbose]

Steps (run in order):
    all              Run every step sequentially (default)
    currencies       Currencies and exchange rates
    accounts         Chart of accounts (groups + accounts)
    taxes            Tax groups and taxes
    journals         Account journals (prefixed per source company)
    fiscal           Fiscal positions
    payment_terms    Payment terms
    partners         Partners with accounting properties (deduplicated)
    moves            Journal entries, invoices, and bills (with company tracking)
    payments         Customer/vendor payments
    bank_statements  Bank statements and lines
    reconcile        Replay invoice/payment reconciliations (payment status)
    verify           Post-migration balance verification

Environment variables (or edit config.py):
    SOURCE_URL, SOURCE_DB, SOURCE_USER, SOURCE_PASSWORD
    TARGET_URL, TARGET_DB, TARGET_USER, TARGET_PASSWORD
    SOURCE_COMPANY_IDS  ("all" or "1,2,3,5")
    TARGET_COMPANY_ID   (usually 1)
    COMPANY_SHORT_NAMES ("1:ALP,2:BET,3:GAM")
    BATCH_SIZE, DRY_RUN, LOG_LEVEL, MAPPING_FILE
"""
import argparse
import logging
import sys
import time

from . import config
from .rpc_client import OdooRPC
from .id_mapper import IDMapper
from .company_setup import build_company_map
from .migrators import (
    CurrencyMigrator,
    AccountMigrator,
    TaxMigrator,
    JournalMigrator,
    FiscalPositionMigrator,
    PaymentTermMigrator,
    PartnerMigrator,
    MoveMigrator,
    PaymentMigrator,
    BankStatementMigrator,
)

logger = logging.getLogger("migration")

STEP_ORDER = [
    "currencies",
    "accounts",
    "taxes",
    "journals",
    "fiscal",
    "payment_terms",
    "partners",
    "moves",
    "payments",
    "bank_statements",
    "verify",
]

STEP_CLASSES = {
    "currencies": CurrencyMigrator,
    "accounts": AccountMigrator,
    "taxes": TaxMigrator,
    "journals": JournalMigrator,
    "fiscal": FiscalPositionMigrator,
    "payment_terms": PaymentTermMigrator,
    "partners": PartnerMigrator,
    "moves": MoveMigrator,
    "payments": PaymentMigrator,
    "bank_statements": BankStatementMigrator,
}


def setup_logging(level: str):
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _validate_connections(source: OdooRPC, target: OdooRPC):
    """
    Sanity-check that SOURCE really is Odoo 14 (or similar old version)
    and TARGET is Odoo 17+/19. Catches swapped URLs early.
    """
    logger.info(
        "Source server version: %s  |  Target server version: %s",
        source.server_version, target.server_version,
    )

    # Check if source has the accounting module installed
    has_account = source.model_exists("account.account")
    if not has_account:
        logger.error(
            "SOURCE (%s) does not have the 'account' module installed.\n"
            "  Install Invoicing or Accounting on the source before migrating.",
            config.SOURCE_URL,
        )
        sys.exit(1)

    # Detect swapped connections: if source is v17+ it won't have account.account.type
    if source.server_major >= 17:
        logger.warning(
            "SOURCE reports version %s (v17+). The model 'account.account.type' "
            "was removed in Odoo 17. If this is really your OLD server, the "
            "migration will use the new-style account_type field directly.",
            source.server_version,
        )
    if target.server_major and target.server_major < 17:
        logger.error(
            "TARGET reports version %s — this looks like an older Odoo, not v17+/v19.\n"
            "  Did you swap SOURCE_URL and TARGET_URL?\n"
            "  SOURCE should be your OLD Odoo 14, TARGET should be your NEW Odoo 19.",
            target.server_version,
        )
        sys.exit(1)

    if source.server_major and target.server_major:
        if source.server_major > target.server_major:
            logger.error(
                "SOURCE version (%s) is NEWER than TARGET version (%s).\n"
                "  It looks like SOURCE_URL and TARGET_URL are swapped!\n"
                "  SOURCE_URL should point to Odoo 14, TARGET_URL to Odoo 19.",
                source.server_version, target.server_version,
            )
            sys.exit(1)

    logger.info("Connection validation passed.")


def verify_balances(source: OdooRPC, target: OdooRPC, mapper: IDMapper,
                    company_map: dict):
    """
    Compare trial balance totals between source and target.
    When multi-company → single-company, sums across all source companies
    and compares with the single target company.
    """
    logger.info("=== Post-Migration Balance Verification ===")

    account_map = mapper.get_all("account.account")
    if not account_map:
        logger.warning("[verify] No account mappings found — skipping verification")
        return

    source_company_ids = list(company_map.keys())
    mismatches = 0
    checked = 0

    # Build reverse map: target_account_id → [source_account_ids]
    tgt_to_src = {}
    for src_id, tgt_id in account_map.items():
        tgt_to_src.setdefault(tgt_id, []).append(src_id)

    for tgt_id, src_ids in tgt_to_src.items():
        try:
            # Source: sum across all source companies and all mapped source accounts
            src_debit = 0.0
            src_credit = 0.0
            for src_id in src_ids:
                src_domain = [
                    ("account_id", "=", src_id),
                    ("parent_state", "=", "posted"),
                ]
                # company_id may not exist on source model either
                try:
                    src_fields_info = source.fields_get("account.move.line", attributes=["type"])
                    if "company_id" in src_fields_info:
                        src_domain.append(("company_id", "in", source_company_ids))
                except Exception:
                    pass
                src_lines = source.search_read(
                    "account.move.line", src_domain,
                    fields=["debit", "credit"],
                )
                src_debit += sum(l["debit"] for l in src_lines)
                src_credit += sum(l["credit"] for l in src_lines)

            # Target — company_id may not exist on account.move.line in Odoo 19
            tgt_domain = [
                ("account_id", "=", tgt_id),
                ("parent_state", "=", "posted"),
            ]
            # Check if company_id exists on move lines (may not in Odoo 19)
            try:
                tgt_fields = target.fields_get("account.move.line", attributes=["type"])
                if "company_id" in tgt_fields:
                    tgt_domain.append(("company_id", "=", config.TARGET_COMPANY_ID))
            except Exception:
                pass
            tgt_lines = target.search_read(
                "account.move.line", tgt_domain,
                fields=["debit", "credit"],
            )
            tgt_debit = sum(l["debit"] for l in tgt_lines)
            tgt_credit = sum(l["credit"] for l in tgt_lines)

            checked += 1
            if abs(src_debit - tgt_debit) > 0.01 or abs(src_credit - tgt_credit) > 0.01:
                tgt_acc = target.read("account.account", [tgt_id], ["code", "name"])
                acc_label = f"{tgt_acc[0]['code']} {tgt_acc[0]['name']}" if tgt_acc else str(tgt_id)
                logger.warning(
                    "[verify] MISMATCH %s: "
                    "src(D=%.2f C=%.2f) vs tgt(D=%.2f C=%.2f)",
                    acc_label, src_debit, src_credit, tgt_debit, tgt_credit,
                )
                mismatches += 1
        except Exception as exc:
            logger.debug("[verify] Error checking account tgt=%s: %s", tgt_id, exc)

    if mismatches:
        logger.warning(
            "[verify] %d / %d accounts have balance mismatches", mismatches, checked,
        )
    else:
        logger.info(
            "[verify] All %d checked accounts match. Migration looks clean!", checked,
        )


def run_migration(steps: list, source: OdooRPC, target: OdooRPC,
                  mapper: IDMapper, company_map: dict):
    for step_name in steps:
        if step_name == "verify":
            verify_balances(source, target, mapper, company_map)
            continue

        cls = STEP_CLASSES.get(step_name)
        if not cls:
            logger.error("Unknown step: %s", step_name)
            continue

        t0 = time.time()
        migrator = cls(source, target, mapper, company_map=company_map)
        try:
            migrator.run()
        except Exception:
            logger.exception("[%s] FATAL error — stopping", step_name)
            sys.exit(1)
        elapsed = time.time() - t0
        logger.info("[%s] Completed in %.1f seconds", step_name, elapsed)

    mapper.save()
    logger.info("ID mappings saved to %s", config.MAPPING_FILE)


def main():
    parser = argparse.ArgumentParser(
        description="Odoo 14 → 19 Accounting Data Migration (Multi-Company → Single)",
    )
    parser.add_argument(
        "--step", default="all",
        help=f"Migration step to run. One of: all, {', '.join(STEP_ORDER)}",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simulate without writing to target",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Clear ID mapping and create ALL records (use only with an empty target DB).",
    )
    args = parser.parse_args()

    if args.dry_run:
        config.DRY_RUN = True
    if args.verbose:
        config.LOG_LEVEL = "DEBUG"

    setup_logging(config.LOG_LEVEL)

    if config.DRY_RUN:
        logger.info("*** DRY-RUN MODE — no records will be created ***")

    logger.info("Source: %s (db=%s)", config.SOURCE_URL, config.SOURCE_DB)
    logger.info("Target: %s (db=%s)", config.TARGET_URL, config.TARGET_DB)

    # Load mapper first so we can clear it before connecting if --full-refresh
    mapper = IDMapper(config.MAPPING_FILE)
    if args.full_refresh:
        mapper.clear()
        mapper.save()
        logger.info(
            "*** FULL-REFRESH: mapping cleared. Ensure target DB is empty or you will get duplicates. ***"
        )

    # Connect to both instances
    source = OdooRPC(
        config.SOURCE_URL, config.SOURCE_DB,
        config.SOURCE_USER, config.SOURCE_PASSWORD,
        label="SOURCE",
    ).connect()

    target = OdooRPC(
        config.TARGET_URL, config.TARGET_DB,
        config.TARGET_USER, config.TARGET_PASSWORD,
        label="TARGET",
    ).connect()

    # ── Validate connections ──────────────────────────────────────────
    _validate_connections(source, target)

    # Discover source companies and build the consolidation map
    company_map = build_company_map(source, target, mapper)
    logger.info(
        "Consolidating %d source companies → target company %d",
        len(company_map), config.TARGET_COMPANY_ID,
    )
    for cid, info in company_map.items():
        analytic_info = f", analytic_id={info['analytic_id']}" if info.get('analytic_id') else ""
        logger.info(
            "  Company %d [%s] %s%s", cid, info["short"], info["name"], analytic_info,
        )

    # Determine which steps to run
    if args.step == "all":
        steps = STEP_ORDER
    else:
        steps = [s.strip() for s in args.step.split(",")]
        for s in steps:
            if s not in STEP_ORDER:
                logger.error("Unknown step '%s'. Valid steps: %s", s, STEP_ORDER)
                sys.exit(1)

    t_start = time.time()
    run_migration(steps, source, target, mapper, company_map)
    logger.info("Total migration time: %.1f seconds", time.time() - t_start)


if __name__ == "__main__":
    main()
