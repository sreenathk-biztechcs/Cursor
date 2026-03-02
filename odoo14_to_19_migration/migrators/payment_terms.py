"""
Migrate account.payment.term and account.payment.term.line records.

Payment terms changed in Odoo 17+:
- Odoo 14 line fields: value ('balance'/'percent'/'fixed'), value_amount, days, option
- Odoo 17+ line fields: value_amount, nb_days, delay_type, value ('percent'/'fixed'/'balance')
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)


class PaymentTermMigrator(BaseMigrator):
    name = "payment_terms"

    def run(self):
        logger.info("=== Migrating Payment Terms (Multi-Company Merge) ===")
        for company_id in self.get_source_company_ids():
            cname = self.get_company_name(company_id)
            logger.info("--- Payment terms for company %d (%s) ---", company_id, cname)
            self._migrate_payment_terms(company_id)
        self.log_summary()

    def _migrate_payment_terms(self, company_id: int):
        src_terms = self.src.search_read(
            "account.payment.term",
            self._src_company_domain_with_false("account.payment.term", company_id),
            fields=["name", "note", "active", "line_ids", "company_id"],
            order="id asc",
        )
        for term in src_terms:
            sid = term["id"]
            if self.mapper.has("account.payment.term", sid):
                self.skipped += 1
                continue

            existing = self._find_target_by_name("account.payment.term", term["name"])
            if existing:
                self.mapper.set("account.payment.term", sid, existing)
                self.skipped += 1
                continue

            vals = {
                "name": term["name"],
                "note": term.get("note") or "",
                "active": term.get("active", True),
            }
            self._add_company_to_vals("account.payment.term", vals, config.TARGET_COMPANY_ID)

            # Build line_ids as one2many commands
            if term.get("line_ids"):
                line_commands = self._build_line_commands(term["line_ids"])
                if line_commands:
                    vals["line_ids"] = line_commands

            self._safe_create("account.payment.term", vals, sid)

        self.mapper.save()

    def _build_line_commands(self, src_line_ids: list) -> list:
        src_lines = self.src.read(
            "account.payment.term.line", src_line_ids,
            fields=["value", "value_amount", "days", "option", "sequence"],
        )
        commands = []
        for line in src_lines:
            value = line.get("value", "balance")
            value_amount = line.get("value_amount", 0)

            # Odoo 19 removed 'balance' from the selection.
            # 'balance' meant "the remaining amount" → convert to 'percent' 100%
            if value == "balance":
                value = "percent"
                value_amount = 100.0

            # Map Odoo 14 'option' → Odoo 19 'delay_type'
            delay_type = "days_after"
            option = line.get("option", "day_after_invoice_date")
            if option in ("day_following_month", "fix_day_following_month",
                          "day_current_month"):
                delay_type = "days_after_end_of_month"

            line_vals = {
                "value": value,
                "value_amount": value_amount,
                "nb_days": line.get("days", 0),
                "delay_type": delay_type,
            }
            commands.append((0, 0, line_vals))
        return commands
