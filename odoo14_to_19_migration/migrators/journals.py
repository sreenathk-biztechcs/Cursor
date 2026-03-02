"""
Migrate account.journal records — multi-company aware.

When consolidating 12 companies → 1, each company's journals get a
unique code prefix to prevent collisions and enable per-company reporting.

Example:
    Company "Alpha" (short=ALP), journal "Sales" (code=SAJ)
    → Target journal code: "ALP-SAJ", name: "Sales - Alpha Trading Corp"
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)


class JournalMigrator(BaseMigrator):
    name = "journals"

    def run(self):
        logger.info("=== Migrating Journals (Multi-Company → Single) ===")
        for company_id in self.get_source_company_ids():
            short = self.get_company_short(company_id)
            cname = self.get_company_name(company_id)
            logger.info(
                "--- Journals for company %d [%s] %s ---", company_id, short, cname,
            )
            self._migrate_journals_for_company(company_id)
        self.log_summary()

    def _migrate_journals_for_company(self, company_id: int):
        fields = [
            "name", "code", "type", "currency_id",
            "default_account_id",
            "payment_debit_account_id", "payment_credit_account_id",
            "company_id", "sequence",
        ]
        src_journals = self.src.search_read(
            "account.journal",
            self._src_company_domain("account.journal", company_id),
            fields=fields,
            order="id asc",
        )
        for jrn in src_journals:
            sid = jrn["id"]
            if self.mapper.has("account.journal", sid):
                self.skipped += 1
                continue

            short = self.get_company_short(company_id)
            cname = self.get_company_name(company_id)

            # Build target journal code — prefix with company short name
            src_code = jrn["code"]
            if config.JOURNAL_PREFIX_BY_COMPANY and short:
                target_code = f"{short}-{src_code}"
                # Journal code max 5 chars in some Odoo versions, relax in v19 (max ~10)
                if len(target_code) > 10:
                    target_code = target_code[:10]
                target_name = f"{jrn['name']} - {cname}"
            else:
                target_code = src_code
                target_name = jrn["name"]

            currency_tid = self._resolve_id("res.currency", jrn.get("currency_id"))
            default_account_tid = self._resolve_id(
                "account.account", jrn.get("default_account_id"),
            )

            vals = {
                "name": target_name,
                "code": target_code,
                "type": jrn["type"],
            }
            self._add_company_to_vals("account.journal", vals, config.TARGET_COMPANY_ID)
            if currency_tid:
                vals["currency_id"] = currency_tid
            if default_account_tid:
                vals["default_account_id"] = default_account_tid

            pay_debit = self._resolve_id(
                "account.account", jrn.get("payment_debit_account_id"),
            )
            pay_credit = self._resolve_id(
                "account.account", jrn.get("payment_credit_account_id"),
            )
            if pay_debit:
                vals["payment_debit_account_id"] = pay_debit
            if pay_credit:
                vals["payment_credit_account_id"] = pay_credit

            # ── Reuse existing journals instead of creating duplicates ──
            # 1) Prefer match by NAME + TYPE (e.g. localization journals already present).
            existing_by_name = self.tgt.search(
                "account.journal",
                [
                    ("name", "=", target_name),
                    ("type", "=", jrn["type"]),
                    ("company_id", "=", config.TARGET_COMPANY_ID),
                ],
                limit=1,
            )
            if existing_by_name:
                target_id = existing_by_name[0]
                try:
                    self.tgt.write("account.journal", [target_id], vals)
                except Exception as exc:
                    logger.warning(
                        "[journals] Failed to update existing journal %s (id=%s): %s",
                        target_name, target_id, exc,
                    )
                self.mapper.set("account.journal", sid, target_id)
                self.skipped += 1
                continue

            # 2) Fallback: merge by CODE when a journal with the same code
            # already exists on target (from another source company).
            existing_by_code = self._find_target_by_code(
                "account.journal", target_code, config.TARGET_COMPANY_ID,
            )
            if existing_by_code:
                self.mapper.set("account.journal", sid, existing_by_code)
                self.skipped += 1
                continue

            # 3) Otherwise create a brand-new journal on the target.
            self._safe_create("account.journal", vals, sid)

        self.mapper.save()
