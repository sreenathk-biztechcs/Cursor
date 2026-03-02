"""
Migrate res.currency and res.currency.rate records.

Currencies are matched by ISO code (e.g. USD, EUR). Only missing currencies
and rates are created on the target.
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)


class CurrencyMigrator(BaseMigrator):
    name = "currency"

    def run(self):
        logger.info("=== Migrating Currencies & Rates ===")
        self._migrate_currencies()
        self._migrate_rates()
        self.log_summary()

    def _migrate_currencies(self):
        src_currencies = self.src.search_read(
            "res.currency", [("active", "in", [True, False])],
            fields=["name", "symbol", "rounding", "decimal_places", "active",
                     "position", "currency_unit_label", "currency_subunit_label"],
        )
        for cur in src_currencies:
            sid = cur["id"]
            if self.mapper.has("res.currency", sid):
                self.skipped += 1
                continue

            # Match by ISO name on target
            existing = self.tgt.search_read(
                "res.currency", [("name", "=", cur["name"]), ("active", "in", [True, False])],
                fields=["id"], limit=1,
            )
            if existing:
                self.mapper.set("res.currency", sid, existing[0]["id"])
                # Always activate on target — inactive currencies referenced
                # by old transactions will cause posting failures otherwise
                try:
                    self.tgt.write("res.currency", [existing[0]["id"]], {"active": True})
                except Exception:
                    pass
                self.skipped += 1
                continue

            vals = {
                "name": cur["name"],
                "symbol": cur["symbol"],
                "rounding": cur["rounding"],
                "active": cur["active"],
                "position": cur.get("position", "after"),
                "currency_unit_label": cur.get("currency_unit_label", ""),
                "currency_subunit_label": cur.get("currency_subunit_label", ""),
            }
            self._safe_create("res.currency", vals, sid)

        self.mapper.save()

    def _migrate_rates(self):
        company_ids = self.get_source_company_ids()
        if self._source_has_field("res.currency.rate", "company_id"):
            rate_domain = [("company_id", "in", company_ids)]
        else:
            rate_domain = []
        src_rates = self.src.search_read(
            "res.currency.rate", rate_domain,
            fields=["name", "rate", "currency_id"],
            order="name asc",
        )
        rates_created = 0
        for rate in src_rates:
            currency_tid = self._resolve_id("res.currency", rate["currency_id"])
            if not currency_tid:
                continue

            # Check if rate for this date already exists
            rate_domain = [
                ("currency_id", "=", currency_tid),
                ("name", "=", rate["name"]),
            ]
            self._add_company_to_domain("res.currency.rate", rate_domain, config.TARGET_COMPANY_ID)
            existing = self.tgt.search("res.currency.rate", rate_domain, limit=1)
            if existing:
                continue

            vals = {
                "name": rate["name"],
                "rate": rate["rate"],
                "currency_id": currency_tid,
            }
            self._add_company_to_vals("res.currency.rate", vals, config.TARGET_COMPANY_ID)
            if not self.dry_run:
                try:
                    self.tgt.create("res.currency.rate", vals)
                    rates_created += 1
                except Exception as exc:
                    logger.warning("Failed to create currency rate: %s", exc)

        logger.info("[currency] Migrated %d currency rates", rates_created)
