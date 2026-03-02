"""
Migrate account.move and account.move.line records — multi-company aware.

Handles: customer invoices, vendor bills, credit/debit notes,
and general journal entries from ALL source companies into one target.

Key consolidation logic:
- Document numbers (INV/0001) get a company prefix in `ref` for traceability
- Each move line is tagged with the source company's analytic account
- Journals are already company-prefixed from the journal migration step

Key changes Odoo 14 → 19:
- Analytic accounts: `analytic_account_id` (M2o) → `analytic_distribution` (JSON)
- Tax repartition line references changed
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)

MOVE_TYPES = [
    # "entry",           # Journal entry
    "out_invoice",     # Customer invoice
    # "out_refund",      # Customer credit note
    # "in_invoice",      # Vendor bill
    # "in_refund",       # Vendor credit note (debit note)
]


class MoveMigrator(BaseMigrator):
    name = "moves"

    def run(self):
        logger.info("=== Migrating Journal Entries & Invoices (Multi-Company) ===")
        for company_id in self.get_source_company_ids():
            cname = self.get_company_name(company_id)
            logger.info("--- Moves for company %d (%s) ---", company_id, cname)
            for move_type in MOVE_TYPES:
                for state in ("posted", "draft"):
                    self._migrate_moves(move_type, state, company_id)
        self.log_summary()

    def _migrate_moves(self, move_type: str, state: str, company_id: int):
        domain = self._src_company_domain("account.move", company_id) + [
            ("move_type", "=", move_type),
            ("state", "=", state),
        ]

        # For invoices/bills/credit notes, only migrate "Not Paid" and
        # "Partially Paid" POSTED invoices from Odoo 14.
        # Draft invoices are always unpaid, so we include ALL drafts.
        if move_type != "entry":
            if self._source_has_field("account.move", "payment_state"):
                if state == "posted":
                    domain.append(("payment_state", "in", ["not_paid", "partial"]))
            elif self._source_has_field("account.move", "amount_residual"):
                domain.append(("amount_residual", ">", 0.0))
        total = self.src.search_count("account.move", domain)
        if total == 0:
            return
        logger.info(
            "[moves] Migrating %d %s moves (state=%s, company=%d)",
            total, move_type, state, company_id,
        )

        fields = [
            "name", "ref", "date", "move_type", "state",
            "partner_id", "journal_id", "currency_id",
            "invoice_date", "invoice_date_due",
            "invoice_payment_term_id", "fiscal_position_id",
            "narration", "invoice_origin",
            "line_ids", "amount_total", "amount_untaxed",
            "amount_residual", "company_id",
        ]

        for batch in self._iter_batches("account.move", domain, fields=fields):
            for move in batch:
                self._migrate_single_move(move, state, company_id)
            self.mapper.save()

    def _migrate_single_move(self, move: dict, original_state: str, company_id: int):
        sid = move["id"]
        if self.mapper.has("account.move", sid):
            self.skipped += 1
            return
        is_invoice = move["move_type"] != "entry"

        journal_tid = self._resolve_id("account.journal", move.get("journal_id"))
        if not journal_tid:
            logger.warning(
                "[moves] Skipping move %s: journal not mapped (source=%s)",
                move.get("name"), move.get("journal_id"),
            )
            self.errors += 1
            return

        partner_tid = self._resolve_id("res.partner", move.get("partner_id"))

        # Guard against stale partner mappings: if mapper points to a target
        # partner that no longer exists (e.g. DB reset), treat as unmapped so
        # we can recreate or rematch the partner.
        if partner_tid and not self.dry_run:
            partner_exists = self.tgt.search(
                "res.partner", [("id", "=", partner_tid)], limit=1,
            )
            if not partner_exists:
                logger.warning(
                    "[moves] Partner mapping for source %s points to missing "
                    "target partner_id=%s. Will recreate/rematch partner.",
                    move.get("partner_id"), partner_tid,
                )
                partner_tid = None

        if move["move_type"] != "entry" and not partner_tid and move.get("partner_id"):
            # Fallback: create or find partner on the fly
            partner_sid = self._m2o(move["partner_id"])
            src_partner = self.src.read(
                "res.partner",
                [partner_sid],
                fields=[
                    "name", "is_company", "active",
                    "street", "street2", "city", "zip", "email",
                    "phone", "mobile", "website", "lang", "ref", "vat",
                    "company_type", "state_id", "country_id",
                    "property_account_receivable_id",
                    "property_account_payable_id",
                    "customer_rank", "supplier_rank",
                    ],
                )[0]

            # Try to find existing partner on target
            existing_ids = []
            if src_partner.get("vat"):
                existing_ids = self.tgt.search(
                    "res.partner",
                    [("vat", "=", src_partner["vat"]),
                     ("active", "in", [True, False])],
                    limit=1,
                    )
            if not existing_ids and src_partner.get("ref"):
                existing_ids = self.tgt.search(
                    "res.partner",
                    [("ref", "=", src_partner["ref"]),
                     ("active", "in", [True, False])],
                    limit=1,
                    )
            if not existing_ids and src_partner.get("name"):
                existing_ids = self.tgt.search(
                    "res.partner",
                    [("name", "=", src_partner["name"]),
                     ("active", "in", [True, False])],
                    limit=1,
                    )

            if existing_ids:
                partner_tid = existing_ids[0]
                self.mapper.set("res.partner", partner_sid, partner_tid)
            else:
                partner_vals = {
                    "name": src_partner["name"],
                    "is_company": src_partner.get("is_company", False),
                    "active": src_partner.get("active", True),
                    }

                for f in ("street", "street2", "city", "zip", "email",
                          "phone", "mobile", "website", "lang", "ref", "vat"):
                    if src_partner.get(f):
                        partner_vals[f] = src_partner[f]

                if src_partner.get("company_type"):
                    partner_vals["company_type"] = src_partner["company_type"]
                if src_partner.get("state_id"):
                    partner_vals["state_id"] = self._m2o(
                        src_partner["state_id"])
                if src_partner.get("country_id"):
                    partner_vals["country_id"] = self._m2o(
                        src_partner["country_id"])

                recv_acc = self._resolve_id(
                    "account.account",
                    src_partner.get("property_account_receivable_id"),
                    )
                pay_acc = self._resolve_id(
                    "account.account",
                    src_partner.get("property_account_payable_id"),
                    )
                if recv_acc:
                    partner_vals["property_account_receivable_id"] = recv_acc
                if pay_acc:
                    partner_vals["property_account_payable_id"] = pay_acc

                if src_partner.get("customer_rank"):
                    partner_vals["customer_rank"] = src_partner[
                        "customer_rank"]
                if src_partner.get("supplier_rank"):
                    partner_vals["supplier_rank"] = src_partner[
                        "supplier_rank"]

                partner_tid = self._safe_create("res.partner", partner_vals,
                                                partner_sid)
        currency_tid = self._resolve_id("res.currency", move.get("currency_id"))

        # Ensure currency is active on target (inactive currencies block posting)
        if currency_tid and not self.dry_run:
            try:
                self.tgt.write("res.currency", [currency_tid], {"active": True})
            except Exception:
                pass
        pay_term_tid = self._resolve_id(
            "account.payment.term", move.get("invoice_payment_term_id"),
        )
        fiscal_tid = self._resolve_id(
            "account.fiscal.position", move.get("fiscal_position_id"),
        )

        # Preserve original sequence/number from source and keep a prefixed ref
        original_name = move.get("name") or ""
        original_ref = move.get("ref") or ""
        # Use original ref for traceability; fall back to name if needed
        combined_ref = original_ref or original_name
        if original_ref and original_name and original_ref != original_name:
            combined_ref = f"{original_ref} | {original_name}"
        prefixed_ref = self.prefix_ref(combined_ref, company_id)

        vals = {
            "move_type": move["move_type"],
            "journal_id": journal_tid,
            "date": move["date"],
            "ref": prefixed_ref,
        }
        # Preserve original sequence/number ONLY for invoices/bills/credit notes.
        # For generic/bank journal entries (move_type='entry'), let Odoo 19 assign
        # a new unique sequence and keep the legacy number in `ref` to avoid
        # name collisions with existing data.
        if is_invoice and original_name:
            vals["name"] = original_name

        self._add_company_to_vals("account.move", vals, config.TARGET_COMPANY_ID)

        # ── Idempotency / de-duplication guard ─────────────────────────────
        # Only for POSTED moves. Draft invoices are allowed to be duplicated
        # (you requested to keep them even if a draft already exists).
        existing_tid = None
        if original_state == "posted":
            if is_invoice and original_name:
                # Match by (journal, move_type, name) which is unique for invoices.
                domain = [
                    ("journal_id", "=", journal_tid),
                    ("move_type", "=", move["move_type"]),
                    ("name", "=", original_name),
                ]
                self._add_company_to_domain("account.move", domain, config.TARGET_COMPANY_ID)
                found = self.tgt.search("account.move", domain, limit=1)
                if found:
                    existing_tid = found[0]
            else:
                # For non-invoice entries, try matching by legacy ref + journal + date.
                if combined_ref:
                    domain = [
                        ("journal_id", "=", journal_tid),
                        ("date", "=", move["date"]),
                        ("ref", "=", prefixed_ref),
                    ]
                    self._add_company_to_domain("account.move", domain, config.TARGET_COMPANY_ID)
                    found = self.tgt.search("account.move", domain, limit=1)
                    if found:
                        existing_tid = found[0]

        if existing_tid:
            self.mapper.set("account.move", sid, existing_tid)
            self.skipped += 1
            return

        if partner_tid:
            vals["partner_id"] = partner_tid
        if currency_tid:
            vals["currency_id"] = currency_tid
        if move.get("invoice_date"):
            vals["invoice_date"] = move["invoice_date"]
        if move.get("invoice_date_due"):
            vals["invoice_date_due"] = move["invoice_date_due"]
        if pay_term_tid:
            vals["invoice_payment_term_id"] = pay_term_tid
        if fiscal_tid:
            vals["fiscal_position_id"] = fiscal_tid
        if move.get("narration"):
            vals["narration"] = move["narration"]
        if move.get("invoice_origin"):
            vals["invoice_origin"] = move["invoice_origin"]

        if is_invoice:
            invoice_line_commands = self._build_invoice_line_commands(
                move.get("line_ids", []), move, company_id,
            )
            if invoice_line_commands:
                vals["invoice_line_ids"] = invoice_line_commands
            else:
                # Fallback: raw move lines if we couldn't build invoice lines
                line_commands = self._build_line_commands(
                    move.get("line_ids", []), move, company_id,
                )
                if not line_commands:
                    logger.warning(
                        "[moves] Skipping move %s: no valid lines", move.get("name"),
                    )
                    self.errors += 1
                    return
                vals["line_ids"] = line_commands
        else:
            line_commands = self._build_line_commands(
                move.get("line_ids", []), move, company_id,
            )
            if not line_commands:
                logger.warning(
                    "[moves] Skipping move %s: no valid lines", move.get("name"),
                )
                self.errors += 1
                return
            vals["line_ids"] = line_commands

        tid = self._safe_create("account.move", vals, sid)
        if not tid:
            return

        if original_state == "posted" and not self.dry_run:
            try:
                self.tgt.execute("account.move", "action_post", [tid])
            except Exception as exc:
                logger.warning(
                    "[moves] Failed to post move %s (target_id=%d): %s",
                    move.get("name"), tid, exc,
                )

    def _build_line_commands(self, line_ids: list, move: dict, company_id: int) -> list:
        if not line_ids:
            return []

        src_lines = self.src.read(
            "account.move.line", line_ids,
            fields=[
                "name", "account_id", "partner_id",
                "debit", "credit", "balance",
                "amount_currency", "currency_id",
                "quantity", "price_unit", "discount",
                "product_id", "product_uom_id",
                "tax_ids", "tax_line_id", "tax_repartition_line_id",
                "analytic_account_id", "analytic_tag_ids",
                "date_maturity", "exclude_from_invoice_tab",
                "sequence",
            ],
        )

        commands = []
        is_invoice = move["move_type"] != "entry"
        legacy_analytic_id = self.get_company_analytic_id(company_id)

        for line in src_lines:
            account_tid = self._resolve_id("account.account", line.get("account_id"))
            if not account_tid:
                logger.debug(
                    "[moves] Skipping line (no account mapping): %s", line.get("name"),
                )
                continue

            line_vals = {
                "account_id": account_tid,
                "name": line.get("name") or "/",
                "debit": line.get("debit", 0.0),
                "credit": line.get("credit", 0.0),
            }

            partner_tid = self._resolve_id("res.partner", line.get("partner_id"))
            if partner_tid and not self.dry_run:
                partner_exists = self.tgt.search(
                    "res.partner", [("id", "=", partner_tid)], limit=1,
                )
                if not partner_exists:
                    logger.debug(
                        "[moves] Line partner mapping points to missing target "
                        "partner_id=%s; dropping partner on line '%s'",
                        partner_tid, line.get("name"),
                    )
                    partner_tid = None
            if partner_tid:
                line_vals["partner_id"] = partner_tid

            currency_tid = self._resolve_id("res.currency", line.get("currency_id"))
            if currency_tid:
                line_vals["currency_id"] = currency_tid
                line_vals["amount_currency"] = line.get("amount_currency", 0.0)

            if is_invoice:
                if line.get("quantity"):
                    line_vals["quantity"] = line["quantity"]
                if line.get("price_unit"):
                    line_vals["price_unit"] = line["price_unit"]
                if line.get("discount"):
                    line_vals["discount"] = line["discount"]

            if line.get("product_id"):
                prod_id = self._m2o(line["product_id"])
                prod_exists = self.tgt.search(
                    "product.product", [("id", "=", prod_id)], limit=1,
                )
                if prod_exists:
                    line_vals["product_id"] = prod_id

            tax_tids = self._resolve_ids("account.tax", line.get("tax_ids") or [])
            if tax_tids:
                # Guard against stale/missing tax mappings: only keep taxes
                # that actually exist on the target DB.
                valid_tax_tids = []
                for tid in tax_tids:
                    exists = self.tgt.search(
                        "account.tax", [("id", "=", tid)], limit=1,
                    )
                    if exists:
                        valid_tax_tids.append(tid)
                    else:
                        logger.debug(
                            "[moves] Dropping missing target tax_id=%s on line '%s'",
                            tid, line.get("name"),
                        )
                if valid_tax_tids:
                    line_vals["tax_ids"] = [(6, 0, valid_tax_tids)]

            # Analytic distribution (Odoo 14 M2o → Odoo 19 JSON)
            analytic_dist = {}

            # Original analytic from source
            if line.get("analytic_account_id"):
                analytic_sid = self._m2o(line["analytic_account_id"])
                analytic_tid = self.mapper.get("account.analytic.account", analytic_sid)
                if analytic_tid:
                    analytic_dist[str(analytic_tid)] = 100.0

            # Add legacy company tracking analytic
            if legacy_analytic_id and config.ANALYTIC_TRACKING:
                analytic_dist[str(legacy_analytic_id)] = 100.0

            if analytic_dist:
                line_vals["analytic_distribution"] = analytic_dist

            if line.get("date_maturity"):
                line_vals["date_maturity"] = line["date_maturity"]

            commands.append((0, 0, line_vals))

        return commands

    def _build_invoice_line_commands(self, line_ids: list, move: dict, company_id: int) -> list:
        """Build invoice_line_ids commands for invoice/bill moves using ORM semantics.

        We only take lines that appear on the invoice tab (exclude_from_invoice_tab is False),
        and let Odoo compute tax and receivable lines from these.
        """
        if not line_ids:
            return []

        src_lines = self.src.read(
            "account.move.line", line_ids,
            fields=[
                "name", "account_id", "partner_id",
                "debit", "credit", "balance",
                "amount_currency", "currency_id",
                "quantity", "price_unit", "discount",
                "product_id", "product_uom_id",
                "tax_ids", "tax_line_id", "tax_repartition_line_id",
                "analytic_account_id", "analytic_tag_ids",
                "date_maturity", "exclude_from_invoice_tab",
                "sequence",
            ],
        )

        commands = []
        legacy_analytic_id = self.get_company_analytic_id(company_id)

        for line in src_lines:
            # Keep only user-facing invoice lines; skip tax & receivable lines
            if line.get("exclude_from_invoice_tab"):
                continue

            account_tid = self._resolve_id("account.account", line.get("account_id"))
            if not account_tid:
                logger.debug(
                    "[moves] Skipping invoice line (no account mapping): %s", line.get("name"),
                )
                continue

            line_vals = {
                "account_id": account_tid,
                "name": line.get("name") or "/",
            }

            qty = line.get("quantity") or 1.0
            line_vals["quantity"] = qty
            if line.get("price_unit") is not None:
                line_vals["price_unit"] = line["price_unit"]
            if line.get("discount"):
                line_vals["discount"] = line["discount"]

            if line.get("product_id"):
                prod_id = self._m2o(line["product_id"])
                prod_exists = self.tgt.search(
                    "product.product", [("id", "=", prod_id)], limit=1,
                )
                if prod_exists:
                    line_vals["product_id"] = prod_id

            tax_tids = self._resolve_ids("account.tax", line.get("tax_ids") or [])
            if tax_tids:
                valid_tax_tids = []
                for tid in tax_tids:
                    exists = self.tgt.search(
                        "account.tax", [("id", "=", tid)], limit=1,
                    )
                    if exists:
                        valid_tax_tids.append(tid)
                if valid_tax_tids:
                    line_vals["tax_ids"] = [(6, 0, valid_tax_tids)]

            analytic_dist = {}
            if line.get("analytic_account_id"):
                analytic_sid = self._m2o(line["analytic_account_id"])
                analytic_tid = self.mapper.get("account.analytic.account", analytic_sid)
                if analytic_tid:
                    analytic_dist[str(analytic_tid)] = 100.0
            if legacy_analytic_id and config.ANALYTIC_TRACKING:
                analytic_dist[str(legacy_analytic_id)] = 100.0
            if analytic_dist:
                line_vals["analytic_distribution"] = analytic_dist

            commands.append((0, 0, line_vals))

        return commands
