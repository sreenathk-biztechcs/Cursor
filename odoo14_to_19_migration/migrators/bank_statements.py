"""
Migrate account.bank.statement and account.bank.statement.line records.
Multi-company aware — processes all source companies.
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)


class BankStatementMigrator(BaseMigrator):
    name = "bank_statements"

    def run(self):
        logger.info("=== Migrating Bank Statements (Multi-Company) ===")
        for company_id in self.get_source_company_ids():
            cname = self.get_company_name(company_id)
            logger.info("--- Bank statements for company %d (%s) ---", company_id, cname)
            self._migrate_statements(company_id)
        self.log_summary()

    def _migrate_statements(self, company_id: int):
        fields = [
            "name", "date", "journal_id", "company_id",
            "balance_start", "balance_end_real",
            "state", "line_ids",
        ]
        domain = self._src_company_domain("account.bank.statement", company_id)
        total = self.src.search_count("account.bank.statement", domain)
        if total == 0:
            logger.info("[bank_statements] No bank statements for company %d", company_id)
            return

        logger.info("[bank_statements] Migrating %d bank statements", total)

        for batch in self._iter_batches(
            "account.bank.statement", domain, fields=fields, order="date asc, id asc",
        ):
            for stmt in batch:
                self._migrate_single_statement(stmt, company_id)
            self.mapper.save()

    def _migrate_single_statement(self, stmt: dict, company_id: int):
        sid = stmt["id"]
        if self.mapper.has("account.bank.statement", sid):
            self.skipped += 1
            return

        journal_tid = self._resolve_id("account.journal", stmt.get("journal_id"))
        if not journal_tid:
            logger.warning(
                "[bank_statements] Skipping statement %s: journal not mapped",
                stmt.get("name"),
            )
            self.errors += 1
            return

        # Prefix statement name with company short
        original_name = stmt.get("name") or "/"
        prefixed_name = self.prefix_ref(original_name, company_id)

        vals = {
            "name": prefixed_name,
            "date": stmt.get("date"),
            "journal_id": journal_tid,
            "balance_start": stmt.get("balance_start", 0.0),
            "balance_end_real": stmt.get("balance_end_real", 0.0),
        }
        self._add_company_to_vals("account.bank.statement", vals, config.TARGET_COMPANY_ID)

        tid = self._safe_create("account.bank.statement", vals, sid)
        if not tid:
            return

        if stmt.get("line_ids"):
            self._migrate_statement_lines(stmt["line_ids"], tid, journal_tid, company_id)

    def _migrate_statement_lines(
        self, line_ids: list, target_stmt_id: int, journal_tid: int,
        company_id: int,
    ):
        src_lines = self.src.read(
            "account.bank.statement.line", line_ids,
            fields=[
                "name", "date", "amount", "partner_id",
                "ref", "note", "sequence",
                "payment_ref", "account_number",
            ],
        )
        for line in src_lines:
            line_sid = line["id"]
            if self.mapper.has("account.bank.statement.line", line_sid):
                continue

            partner_tid = self._resolve_id("res.partner", line.get("partner_id"))

            payment_ref = (
                line.get("payment_ref")
                or line.get("name")
                or line.get("ref")
                or "/"
            )
            # Prefix with company short name
            payment_ref = self.prefix_ref(payment_ref, company_id)

            line_vals = {
                "statement_id": target_stmt_id,
                "date": line.get("date"),
                "payment_ref": payment_ref,
                "amount": line.get("amount", 0.0),
                "journal_id": journal_tid,
            }
            if partner_tid:
                line_vals["partner_id"] = partner_tid

            try:
                if not self.dry_run:
                    line_tid = self.tgt.create(
                        "account.bank.statement.line", line_vals,
                    )
                    self.mapper.set(
                        "account.bank.statement.line", line_sid, line_tid,
                    )
                self.created += 1
            except Exception as exc:
                logger.warning(
                    "[bank_statements] Failed to create statement line: %s", exc,
                )
                self.errors += 1
