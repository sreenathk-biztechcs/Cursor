"""
Migrate the Chart of Accounts: account.group and account.account.
Multi-company aware — merges accounts with the same code from different
source companies into one target account.

Key change: Odoo 14 uses `user_type_id` (Many2one → account.account.type).
Odoo 17+ replaced this with a Selection field `account_type` on account.account.
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)


class AccountMigrator(BaseMigrator):
    name = "accounts"

    def run(self):
        logger.info("=== Migrating Chart of Accounts (Multi-Company Merge) ===")
        self._build_account_type_map()
        # Process all companies — accounts with the same code are merged
        for company_id in self.get_source_company_ids():
            cname = self.get_company_name(company_id)
            logger.info("--- Accounts for company %d (%s) ---", company_id, cname)
            self._migrate_account_groups(company_id)
            self._migrate_accounts(company_id)
        self.log_summary()

    # ── Account type resolution ──────────────────────────────────────────

    def _build_account_type_map(self):
        """Build mapping: Odoo14 account.account.type ID → Odoo19 account_type string."""
        self._type_id_to_selection = {}

        src_types = self.src.search_read(
            "account.account.type", [],
            fields=["id", "name", "type", "internal_group"],
        )
        for at in src_types:
            xml_id = self.src.get_xml_id("account.account.type", at["id"])
            mapped = None
            if xml_id and xml_id in config.ACCOUNT_TYPE_XMLID_MAP:
                mapped = config.ACCOUNT_TYPE_XMLID_MAP[xml_id]
            if not mapped:
                mapped = config.ACCOUNT_TYPE_NAME_MAP.get(at["name"].strip().lower())
            if not mapped:
                mapped = config.ACCOUNT_INTERNAL_TYPE_MAP.get(
                    at.get("type", "other"), "asset_current",
                )
            self._type_id_to_selection[at["id"]] = mapped
            logger.debug("Account type %d (%s) → %s", at["id"], at["name"], mapped)

    def _resolve_account_type(self, user_type_id) -> str:
        if not user_type_id:
            return "asset_current"
        type_id = user_type_id[0] if isinstance(user_type_id, (list, tuple)) else user_type_id
        return self._type_id_to_selection.get(type_id, "asset_current")

    # ── Account Groups ───────────────────────────────────────────────────

    def _migrate_account_groups(self, company_id: int):
        src_groups = self.src.search_read(
            "account.group",
            [("company_id", "=", company_id)],
            fields=["name", "code_prefix_start", "code_prefix_end", "parent_id"],
            order="id asc",
        )
        for grp in src_groups:
            sid = grp["id"]
            if self.mapper.has("account.group", sid):
                self.skipped += 1
                continue

            prefix_start = grp.get("code_prefix_start") or grp.get("code_prefix", "")
            prefix_end = grp.get("code_prefix_end") or prefix_start

            # Merge: check if this group already exists on target
            existing = self.tgt.search(
                "account.group",
                [("code_prefix_start", "=", prefix_start),
                 ("company_id", "=", config.TARGET_COMPANY_ID)],
                limit=1,
            )
            if existing:
                self.mapper.set("account.group", sid, existing[0])
                self.skipped += 1
                continue

            parent_tid = self._resolve_id("account.group", grp.get("parent_id"))
            vals = {
                "name": grp["name"],
                "code_prefix_start": prefix_start,
                "code_prefix_end": prefix_end,
                "company_id": config.TARGET_COMPANY_ID,
            }
            if parent_tid:
                vals["parent_id"] = parent_tid
            self._safe_create("account.group", vals, sid)

        self.mapper.save()

    # ── Accounts ─────────────────────────────────────────────────────────

    def _migrate_accounts(self, company_id: int):
        fields = [
            "name", "code", "user_type_id", "reconcile",
            "deprecated", "currency_id", "tax_ids", "group_id",
            "note", "company_id",
        ]
        for batch in self._iter_batches(
            "account.account",
            [("company_id", "=", company_id)],
            fields=fields,
        ):
            for acc in batch:
                sid = acc["id"]
                if self.mapper.has("account.account", sid):
                    self.skipped += 1
                    continue

                account_type = self._resolve_account_type(acc["user_type_id"])
                currency_tid = self._resolve_id("res.currency", acc.get("currency_id"))
                group_tid = self._resolve_id("account.group", acc.get("group_id"))
                tax_tids = self._resolve_ids("account.tax", acc.get("tax_ids") or [])

                vals = {
                    "name": acc["name"],
                    "code": acc["code"],
                    "account_type": account_type,
                    "reconcile": acc.get("reconcile", False),
                    "deprecated": acc.get("deprecated", False),
                    "company_id": config.TARGET_COMPANY_ID,
                }
                if currency_tid:
                    vals["currency_id"] = currency_tid
                if group_tid:
                    vals["group_id"] = group_tid
                if tax_tids:
                    vals["tax_ids"] = [(6, 0, tax_tids)]

                # ── Reuse existing accounts instead of creating duplicates ──
                # 1) Prefer match by NAME (e.g. localization accounts already present).
                existing_by_name = self.tgt.search(
                    "account.account",
                    [
                        ("name", "=", acc["name"]),
                        ("company_id", "=", config.TARGET_COMPANY_ID),
                    ],
                    limit=1,
                )
                if existing_by_name:
                    target_id = existing_by_name[0]
                    try:
                        # Update the existing account with the legacy code/type so
                        # reports use the same structure as the old system.
                        self.tgt.write("account.account", [target_id], vals)
                    except Exception as exc:
                        logger.warning(
                            "[accounts] Failed to update existing account %s (id=%s): %s",
                            acc["name"], target_id, exc,
                        )
                    self.mapper.set("account.account", sid, target_id)
                    self.skipped += 1
                    continue

                # 2) Fallback: merge by CODE when an account with the same code
                # already exists on target (from another source company).
                existing_by_code = self._find_target_by_code(
                    "account.account", acc["code"], config.TARGET_COMPANY_ID,
                )
                if existing_by_code:
                    self.mapper.set("account.account", sid, existing_by_code)
                    self.skipped += 1
                    continue

                # 3) Otherwise create a brand-new account on the target.
                self._safe_create("account.account", vals, sid)

            self.mapper.save()
