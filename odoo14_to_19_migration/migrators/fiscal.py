"""
Migrate account.fiscal.position and its tax/account mapping lines.
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)


class FiscalPositionMigrator(BaseMigrator):
    name = "fiscal_positions"

    def run(self):
        logger.info("=== Migrating Fiscal Positions (Multi-Company Merge) ===")
        for company_id in self.get_source_company_ids():
            cname = self.get_company_name(company_id)
            logger.info("--- Fiscal positions for company %d (%s) ---", company_id, cname)
            self._migrate_fiscal_positions(company_id)
        self.log_summary()

    def _migrate_fiscal_positions(self, company_id: int):
        src_fps = self.src.search_read(
            "account.fiscal.position",
            self._src_company_domain("account.fiscal.position", company_id),
            fields=["name", "sequence", "auto_apply", "vat_required",
                     "country_id", "country_group_id", "zip_from", "zip_to",
                     "tax_ids", "account_ids", "note"],
            order="id asc",
        )
        for fp in src_fps:
            sid = fp["id"]
            if self.mapper.has("account.fiscal.position", sid):
                self.skipped += 1
                continue

            existing = self._find_target_by_name(
                "account.fiscal.position", fp["name"], config.TARGET_COMPANY_ID,
            )
            if existing:
                self.mapper.set("account.fiscal.position", sid, existing)
                self.skipped += 1
                continue

            vals = {
                "name": fp["name"],
                "sequence": fp.get("sequence", 1),
                "auto_apply": fp.get("auto_apply", False),
                "vat_required": fp.get("vat_required", False),
            }
            self._add_company_to_vals("account.fiscal.position", vals, config.TARGET_COMPANY_ID)
            if fp.get("note"):
                vals["note"] = fp["note"]
            if fp.get("country_id"):
                vals["country_id"] = self._m2o(fp["country_id"])
            if fp.get("country_group_id"):
                vals["country_group_id"] = self._m2o(fp["country_group_id"])
            if fp.get("zip_from"):
                vals["zip_from"] = fp["zip_from"]
            if fp.get("zip_to"):
                vals["zip_to"] = fp["zip_to"]

            tid = self._safe_create("account.fiscal.position", vals, sid)
            if not tid:
                continue

            # Tax mapping lines
            if fp.get("tax_ids"):
                self._migrate_tax_mappings(fp["tax_ids"], tid)

            # Account mapping lines
            if fp.get("account_ids"):
                self._migrate_account_mappings(fp["account_ids"], tid)

        self.mapper.save()

    def _migrate_tax_mappings(self, src_line_ids: list, target_fp_id: int):
        lines = self.src.read(
            "account.fiscal.position.tax", src_line_ids,
            fields=["tax_src_id", "tax_dest_id"],
        )
        for line in lines:
            src_tax = self._resolve_id("account.tax", line.get("tax_src_id"))
            dst_tax = self._resolve_id("account.tax", line.get("tax_dest_id"))
            if not src_tax:
                continue
            vals = {
                "position_id": target_fp_id,
                "tax_src_id": src_tax,
            }
            if dst_tax:
                vals["tax_dest_id"] = dst_tax
            try:
                self.tgt.create("account.fiscal.position.tax", vals)
            except Exception as exc:
                logger.warning("Failed to create FP tax mapping: %s", exc)

    def _migrate_account_mappings(self, src_line_ids: list, target_fp_id: int):
        lines = self.src.read(
            "account.fiscal.position.account", src_line_ids,
            fields=["account_src_id", "account_dest_id"],
        )
        for line in lines:
            src_acc = self._resolve_id("account.account", line.get("account_src_id"))
            dst_acc = self._resolve_id("account.account", line.get("account_dest_id"))
            if not src_acc:
                continue
            vals = {
                "position_id": target_fp_id,
                "account_src_id": src_acc,
            }
            if dst_acc:
                vals["account_dest_id"] = dst_acc
            try:
                self.tgt.create("account.fiscal.position.account", vals)
            except Exception as exc:
                logger.warning("Failed to create FP account mapping: %s", exc)
