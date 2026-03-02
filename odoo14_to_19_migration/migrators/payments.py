"""
Migrate account.payment records — multi-company aware.

Key changes Odoo 14 → 19:
- payment_method_id → payment_method_line_id
- Payments from all source companies go to the single target company
- Ref is prefixed with source company short name for traceability
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)


class PaymentMigrator(BaseMigrator):
    name = "payments"

    def run(self):
        logger.info("=== Migrating Payments (Multi-Company) ===")
        self._cache_payment_method_lines()
        for company_id in self.get_source_company_ids():
            cname = self.get_company_name(company_id)
            logger.info("--- Payments for company %d (%s) ---", company_id, cname)
            self._migrate_payments(company_id)
        self.log_summary()

    def _cache_payment_method_lines(self):
        self._pml_cache = {}
        lines = self.tgt.search_read(
            "account.payment.method.line", [],
            fields=["journal_id", "payment_method_id", "name", "payment_type"],
        )
        for ln in lines:
            journal_id = self._m2o(ln["journal_id"])
            ptype = ln.get("payment_type", "inbound")
            key = (journal_id, ptype)
            self._pml_cache.setdefault(key, ln["id"])

    def _get_payment_method_line(self, journal_tid: int, payment_type: str) -> int:
        key = (journal_tid, payment_type)
        if key in self._pml_cache:
            return self._pml_cache[key]
        result = self.tgt.search(
            "account.payment.method.line",
            [("journal_id", "=", journal_tid)],
            limit=1,
        )
        if result:
            self._pml_cache[key] = result[0]
            return result[0]
        return None

    def _migrate_payments(self, company_id: int):
        # Only request fields that actually exist on the SOURCE model.
        base_fields = [
            "name", "payment_type", "partner_type",
            "partner_id", "amount", "date", "ref",
            "journal_id", "currency_id",
            "payment_method_id", "state",
            "move_id",
        ]
        fields = list(base_fields)
        # `communication` exists in many Odoo 14 setups but not all;
        # guard it to avoid "Invalid field" errors.
        if self._source_has_field("account.payment", "communication"):
            fields.append("communication")
        for state in ("posted", "draft"):
            domain = self._src_company_domain("account.payment", company_id) + [
                ("state", "=", state),
            ]
            total = self.src.search_count("account.payment", domain)
            if total == 0:
                continue
            logger.info(
                "[payments] Migrating %d payments (state=%s, company=%d)",
                total, state, company_id,
            )

            for batch in self._iter_batches("account.payment", domain, fields=fields):
                for payment in batch:
                    self._migrate_single_payment(payment, state, company_id)
                self.mapper.save()

    def _migrate_single_payment(self, payment: dict, original_state: str,
                                company_id: int):
        sid = payment["id"]
        if self.mapper.has("account.payment", sid):
            self.skipped += 1
            return

        # Only migrate payments that are actually linked (via reconciliations)
        # to invoices/bills that we migrated (i.e. not fully paid in source).
        # This avoids importing orphan or fully-settled payments.
        if not self._payment_links_migrated_invoice(payment):
            self.skipped += 1
            return

        journal_tid = self._resolve_id("account.journal", payment.get("journal_id"))
        if not journal_tid:
            logger.warning(
                "[payments] Skipping payment %s: journal not mapped", payment.get("name"),
            )
            self.errors += 1
            return

        partner_tid = self._resolve_id("res.partner", payment.get("partner_id"))
        currency_tid = self._resolve_id("res.currency", payment.get("currency_id"))
        payment_type = payment.get("payment_type", "inbound")
        pml_id = self._get_payment_method_line(journal_tid, payment_type)

        vals = {
            "payment_type": payment_type,
            "partner_type": payment.get("partner_type", "customer"),
            "amount": payment.get("amount", 0),
            "date": payment.get("date"),
            "journal_id": journal_tid,
        }
        self._add_company_to_vals("account.payment", vals, config.TARGET_COMPANY_ID)
        if partner_tid:
            vals["partner_id"] = partner_tid
        if currency_tid:
            vals["currency_id"] = currency_tid
        if pml_id:
            vals["payment_method_line_id"] = pml_id

        # Prefix ref with company name + original payment name
        original_name = payment.get("name") or ""
        ref = payment.get("ref") or payment.get("communication") or ""
        combined = original_name
        if ref and ref != original_name:
            combined = f"{original_name} | {ref}"
        vals["ref"] = self.prefix_ref(combined, company_id)

        tid = self._safe_create("account.payment", vals, sid)
        if not tid:
            return

        if original_state == "posted" and not self.dry_run:
            try:
                self.tgt.execute("account.payment", "action_post", [tid])
            except TypeError as exc:
                # Some Odoo 19 servers return None from action_post, which breaks
                # XML-RPC marshalling when allow_none=False. Treat this as success.
                msg = str(exc).lower()
                if "marshal" in msg and "none" in msg:
                    logger.debug(
                        "[payments] action_post returned None for payment %d; "
                        "treating as success.",
                        tid,
                    )
                else:
                    logger.warning("[payments] Failed to post payment %d: %s", tid, exc)
            except Exception as exc:
                logger.warning("[payments] Failed to post payment %d: %s", tid, exc)

    def _payment_links_migrated_invoice(self, payment: dict) -> bool:
        """
        Return True if this payment is reconciled (via account.partial.reconcile)
        to at least one invoice/bill that we migrated (i.e. whose account.move
        has a mapping in the ID mapper).

        This ensures we only migrate payments that are relevant to the open /
        partially-paid invoices we brought over, and skip payments tied solely
        to invoices we did NOT migrate (e.g. fully paid legacy invoices).
        """
        if not payment.get("move_id"):
            return False

        pay_move_sid = self._m2o(payment["move_id"])
        if not pay_move_sid:
            return False

        # Fetch all move lines on the payment's journal entry
        try:
            pay_move_data = self.src.read("account.move", [pay_move_sid], ["line_ids"])
        except Exception:
            return False
        if not pay_move_data or not pay_move_data[0].get("line_ids"):
            return False

        pay_line_ids = pay_move_data[0]["line_ids"]

        # Find partial reconciliations involving any of these lines
        pr_domain = [
            "|",
            ("debit_move_id", "in", pay_line_ids),
            ("credit_move_id", "in", pay_line_ids),
        ]
        pr_recs = self.src.search_read(
            "account.partial.reconcile",
            pr_domain,
            fields=["debit_move_id", "credit_move_id"],
        )
        if not pr_recs:
            return False

        # Collect the "other side" move line IDs (the invoice side)
        other_line_ids = set()
        for rec in pr_recs:
            debit_sid = self._m2o(rec.get("debit_move_id"))
            credit_sid = self._m2o(rec.get("credit_move_id"))
            if debit_sid in pay_line_ids and credit_sid:
                other_line_ids.add(credit_sid)
            elif credit_sid in pay_line_ids and debit_sid:
                other_line_ids.add(debit_sid)

        if not other_line_ids:
            return False

        # Read those lines to get their parent moves
        other_lines = self.src.read(
            "account.move.line",
            list(other_line_ids),
            fields=["move_id"],
        )
        inv_move_ids = set()
        for line in other_lines:
            inv_sid = self._m2o(line.get("move_id"))
            if inv_sid:
                inv_move_ids.add(inv_sid)

        if not inv_move_ids:
            return False

        # Check if any of those invoice moves were migrated (have an ID mapping)
        for inv_sid in inv_move_ids:
            if self.mapper.get("account.move", inv_sid):
                return True

        return False
