"""
Migrate res.partner records with accounting-related properties.
Multi-company aware — deduplicates partners that exist across multiple
source companies (same customer in Company A and Company B → one partner).

Partners are matched by VAT number first, then ref, then email, then name.
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)


class PartnerMigrator(BaseMigrator):
    name = "partners"

    def run(self):
        logger.info("=== Migrating Partners (Multi-Company, Deduplicated) ===")
        # Process companies → deduplicate across all of them
        for company_id in self.get_source_company_ids():
            cname = self.get_company_name(company_id)
            logger.info("--- Partners for company %d (%s) ---", company_id, cname)
            self._migrate_partners(company_id)
        self.log_summary()

    def _migrate_partners(self, company_id: int):
        fields = [
            "name", "display_name", "is_company", "parent_id",
            "street", "street2", "city", "state_id", "zip", "country_id",
            "vat", "email", "phone", "mobile", "website",
            "lang", "ref", "company_type",
            "property_account_receivable_id",
            "property_account_payable_id",
            "property_payment_term_id",
            "property_supplier_payment_term_id",
            "property_account_position_id",
            "customer_rank", "supplier_rank",
            "bank_ids", "active", "company_id",
        ]

        has_company = self._source_has_field("res.partner", "company_id")

        # Companies/top-level first, then contacts
        for is_company_filter in [True, False]:
            if has_company:
                company_part = ["|", ("company_id", "=", company_id),
                                ("company_id", "=", False)]
            else:
                company_part = []

            if is_company_filter:
                domain = company_part + [("is_company", "=", True)]
            else:
                # Include non-company partners that are customers/suppliers OR have a parent
                domain = company_part + [
                    ("is_company", "=", False),
                    "|",
                    ("parent_id", "!=", False),
                    "|",
                    ("customer_rank", ">", 0),
                    ("supplier_rank", ">", 0),
                    ]
            for batch in self._iter_batches(
                "res.partner", domain, fields=fields, order="id asc",
            ):
                for partner in batch:
                    self._migrate_single_partner(partner)

            self.mapper.save()

    def _migrate_single_partner(self, partner: dict):
        sid = partner["id"]
        if self.mapper.has("res.partner", sid):
            self.skipped += 1
            return

        # Deduplicate: check if this partner already exists on target
        existing_tid = self._find_existing_partner(partner)
        if existing_tid:
            self.mapper.set("res.partner", sid, existing_tid)
            self.skipped += 1
            return

        parent_tid = self._resolve_id("res.partner", partner.get("parent_id"))

        vals = {
            "name": partner["name"],
            "is_company": partner.get("is_company", False),
            "active": partner.get("active", True),
        }

        for f in ("street", "street2", "city", "zip", "email",
                   "phone", "mobile", "website", "lang", "ref", "vat"):
            if partner.get(f):
                vals[f] = partner[f]

        if partner.get("company_type"):
            vals["company_type"] = partner["company_type"]
        if partner.get("state_id"):
            vals["state_id"] = self._m2o(partner["state_id"])
        if partner.get("country_id"):
            vals["country_id"] = self._m2o(partner["country_id"])
        if parent_tid:
            vals["parent_id"] = parent_tid

        # Accounting properties
        recv_acc = self._resolve_id(
            "account.account", partner.get("property_account_receivable_id"),
        )
        pay_acc = self._resolve_id(
            "account.account", partner.get("property_account_payable_id"),
        )
        pay_term = self._resolve_id(
            "account.payment.term", partner.get("property_payment_term_id"),
        )
        sup_pay_term = self._resolve_id(
            "account.payment.term", partner.get("property_supplier_payment_term_id"),
        )
        fiscal_pos = self._resolve_id(
            "account.fiscal.position", partner.get("property_account_position_id"),
        )
        if recv_acc:
            vals["property_account_receivable_id"] = recv_acc
        if pay_acc:
            vals["property_account_payable_id"] = pay_acc
        if pay_term:
            vals["property_payment_term_id"] = pay_term
        if sup_pay_term:
            vals["property_supplier_payment_term_id"] = sup_pay_term
        if fiscal_pos:
            vals["property_account_position_id"] = fiscal_pos

        if partner.get("customer_rank"):
            vals["customer_rank"] = partner["customer_rank"]
        if partner.get("supplier_rank"):
            vals["supplier_rank"] = partner["supplier_rank"]

        tid = self._safe_create("res.partner", vals, sid)

        if tid and partner.get("bank_ids"):
            self._migrate_bank_accounts(partner["bank_ids"], tid)

    def _find_existing_partner(self, partner: dict):
        """
        Find an existing partner on target. This handles deduplication when the
        same partner exists in multiple source companies.
        """
        # 1. Already migrated from another source company (check mapper for all IDs)
        #    This is handled by the mapper.has() check in the caller.

        # 2. Match by VAT
        if partner.get("vat"):
            result = self.tgt.search(
                "res.partner",
                [("vat", "=", partner["vat"]), ("active", "in", [True, False])],
                limit=1,
            )
            if result:
                return result[0]

        # 3. Match by ref
        if partner.get("ref"):
            result = self.tgt.search(
                "res.partner",
                [("ref", "=", partner["ref"]), ("active", "in", [True, False])],
                limit=1,
            )
            if result:
                return result[0]

        # 4. Match by email for companies
        if partner.get("email") and partner.get("is_company"):
            result = self.tgt.search(
                "res.partner",
                [("email", "=", partner["email"]),
                 ("is_company", "=", True),
                 ("active", "in", [True, False])],
                limit=1,
            )
            if result:
                return result[0]

        # 5. Match by exact name for companies
        if partner.get("is_company") and partner.get("name"):
            result = self.tgt.search(
                "res.partner",
                [("name", "=", partner["name"]),
                 ("is_company", "=", True),
                 ("active", "in", [True, False])],
                limit=1,
            )
            if result:
                return result[0]

        return None

    def _migrate_bank_accounts(self, bank_ids: list, target_partner_id: int):
        src_banks = self.src.read(
            "res.partner.bank", bank_ids,
            fields=["acc_number", "bank_id", "currency_id"],
        )
        for bank in src_banks:
            existing = self.tgt.search(
                "res.partner.bank",
                [("acc_number", "=", bank["acc_number"]),
                 ("partner_id", "=", target_partner_id)],
                limit=1,
            )
            if existing:
                continue
            vals = {
                "acc_number": bank["acc_number"],
                "partner_id": target_partner_id,
            }
            if bank.get("currency_id"):
                cur_tid = self._resolve_id("res.currency", bank["currency_id"])
                if cur_tid:
                    vals["currency_id"] = cur_tid
            try:
                self.tgt.create("res.partner.bank", vals)
            except Exception as exc:
                logger.warning(
                    "Failed to create bank account %s: %s",
                    bank["acc_number"], exc,
                )
