"""
Migrate account.tax.group, account.tax, and tax repartition lines.

Tax structure is largely consistent between Odoo 14 and 19, but repartition
lines replaced the older children-based tax distribution model.
Odoo 14 already has repartition lines (invoice/refund_repartition_line_ids).
"""
import logging
from ..base_migrator import BaseMigrator
from .. import config

logger = logging.getLogger(__name__)


class TaxMigrator(BaseMigrator):
    name = "taxes"

    def run(self):
        logger.info("=== Migrating Taxes (Multi-Company Merge) ===")
        for company_id in self.get_source_company_ids():
            cname = self.get_company_name(company_id)
            logger.info("--- Taxes for company %d (%s) ---", company_id, cname)
            self._migrate_tax_groups(company_id)
            self._migrate_taxes(company_id)
        self.log_summary()

    def _migrate_tax_groups(self, company_id: int):
        src_groups = self.src.search_read(
            "account.tax.group",
            self._src_company_domain_with_false("account.tax.group", company_id),
            fields=["name", "sequence"],
            order="id asc",
        )
        for grp in src_groups:
            sid = grp["id"]
            if self.mapper.has("account.tax.group", sid):
                self.skipped += 1
                continue

            existing = self._find_target_by_name(
                "account.tax.group", grp["name"], config.TARGET_COMPANY_ID,
            )
            # Also try without company filter
            if not existing:
                existing = self._find_target_by_name("account.tax.group", grp["name"])
            if existing:
                self.mapper.set("account.tax.group", sid, existing)
                self.skipped += 1
                continue

            vals = {
                "name": grp["name"],
                "sequence": grp.get("sequence", 10),
            }
            self._add_company_to_vals("account.tax.group", vals, config.TARGET_COMPANY_ID)
            self._safe_create("account.tax.group", vals, sid)

        self.mapper.save()

    def _migrate_taxes(self, company_id: int):
        fields = [
            "name", "type_tax_use", "amount_type", "amount", "description",
            "active", "sequence", "price_include", "include_base_amount",
            "tax_group_id", "company_id", "tax_exigibility",
            "cash_basis_transition_account_id",
            "invoice_repartition_line_ids", "refund_repartition_line_ids",
            "children_tax_ids",
        ]
        # Python-code taxes in Odoo 14 store their logic in python_compute /
        # python_applicable. Only add these fields if they exist on source.
        if self._source_has_field("account.tax", "python_compute"):
            fields.append("python_compute")
        if self._source_has_field("account.tax", "python_applicable"):
            fields.append("python_applicable")

        # Detect whether the TARGET supports Custom Formula taxes. In your Odoo 19,
        # the account_python_tax module extends amount_type with 'code' (Custom
        # Formula) and adds a text field 'formula'. We detect that dynamically.
        supports_formula = False
        formula_field = None
        try:
            tgt_fields = self.tgt.fields_get("account.tax", attributes=["selection"])
            sel = tgt_fields.get("amount_type", {}).get("selection") or []
            sel_values = [v for v, _ in sel]
            # In Odoo 19 with Custom Formula, the selection value is 'code'
            # (labelled "Custom Formula").
            if "code" in sel_values:
                supports_formula = True
            tgt_fields2 = self.tgt.fields_get("account.tax", attributes=["type"])
            if "formula" in tgt_fields2:
                formula_field = "formula"
            elif "python_compute" in tgt_fields2:
                formula_field = "python_compute"
        except Exception:
            pass
        src_taxes = self.src.search_read(
            "account.tax",
            self._src_company_domain("account.tax", company_id),
            fields=fields,
            order="sequence, id asc",
        )
        for tax in src_taxes:
            sid = tax["id"]
            if self.mapper.has("account.tax", sid):
                self.skipped += 1
                continue

            # Match by name + type on target
            type_tax_use = tax["type_tax_use"]
            # Odoo 17 removed 'none' type_tax_use; map to 'sale' as fallback
            if type_tax_use == "none":
                type_tax_use = "sale"

            amount_type = tax["amount_type"]

            # ── Python-code taxes (amount_type='code') ─────────────────────
            if amount_type == "code":
                if formula_field:
                    # Target has a text field (usually 'formula'); keep amount_type
                    # as 'code' (Custom Formula) and just copy the Python code
                    # into that field. This matches your Odoo 19 model:
                    #   amount_type = 'code'  (Custom Formula)
                    #   formula = <python expression>
                    pass
                else:
                    # No place to store the code and no formula engine. Try to link
                    # to an existing tax with same name/type instead of inventing.
                    domain = [
                        ("name", "=", tax["name"]),
                        ("type_tax_use", "=", type_tax_use),
                    ]
                    self._add_company_to_domain("account.tax", domain, config.TARGET_COMPANY_ID)
                    existing = self.tgt.search("account.tax", domain, limit=1)
                    if existing:
                        self.mapper.set("account.tax", sid, existing[0])
                        self.skipped += 1
                        continue
                    logger.warning(
                        "[taxes] Tax %s (id=%s) uses Python code (amount_type='code'), "
                        "but target has no formula field and no matching tax exists. "
                        "It will NOT be migrated.",
                        tax["name"], sid,
                    )
                    self.errors += 1
                    continue

            # Check if a dedicated "[Migrated]" tax already exists on target.
            # This keeps the script idempotent when it was previously run with
            # the old behavior that created "<name> [Migrated]" copies.
            migrated_name = f"{tax['name']} [Migrated]"
            migr_domain = [
                ("name", "=", migrated_name),
                ("type_tax_use", "=", type_tax_use),
            ]
            self._add_company_to_domain(
                "account.tax", migr_domain, config.TARGET_COMPANY_ID
            )
            existing_migr = self.tgt.search("account.tax", migr_domain, limit=1)
            if existing_migr:
                self.mapper.set("account.tax", sid, existing_migr[0])
                self.skipped += 1
                continue

            # Check if a base tax with same name/type already exists on target.
            base_domain = [
                ("name", "=", tax["name"]),
                ("type_tax_use", "=", type_tax_use),
            ]
            self._add_company_to_domain("account.tax", base_domain, config.TARGET_COMPANY_ID)
            existing_base = self.tgt.search("account.tax", base_domain, limit=1)

            tax_group_tid = self._resolve_id("account.tax.group", tax.get("tax_group_id"))

            vals = {
                # Always use the original tax name from Odoo 14. If a base tax
                # already exists on the target, we will UPDATE that tax instead
                # of creating a new "<name> [Migrated]" copy.
                "name": tax["name"],
                "type_tax_use": type_tax_use,
                "amount_type": amount_type,
                "amount": tax["amount"],
                "description": tax.get("description") or "",
                "active": tax.get("active", True),
                "sequence": tax.get("sequence", 1),
                "price_include": tax.get("price_include", False),
                "include_base_amount": tax.get("include_base_amount", False),
            }

            # When mapping legacy Python-code taxes, copy the python_compute
            # content into the target 'formula' text field. Odoo 19 expects a
            # pure expression there, so we strip the "result =" part if present.
            if amount_type == "code" and formula_field:
                src_code = (tax.get("python_compute") or "").strip()
                formula_expr = src_code
                if "result" in src_code:
                    for line in src_code.splitlines():
                        if "result" in line and "=" in line:
                            rhs = line.split("=", 1)[1].strip()
                            if rhs:
                                formula_expr = rhs
                            break
                vals[formula_field] = formula_expr
            self._add_company_to_vals("account.tax", vals, config.TARGET_COMPANY_ID)
            if tax_group_tid:
                vals["tax_group_id"] = tax_group_tid

            # Tax exigibility (on_invoice / on_payment)
            if tax.get("tax_exigibility"):
                vals["tax_exigibility"] = tax["tax_exigibility"]
                if tax.get("cash_basis_transition_account_id"):
                    trans_acct = self._resolve_id(
                        "account.account", tax["cash_basis_transition_account_id"]
                    )
                    if trans_acct:
                        vals["cash_basis_transition_account_id"] = trans_acct

            # If a base tax already exists with the same name/type on the target,
            # reuse it instead of creating a separate "<name> [Migrated]" record.
            if existing_base:
                base_tid = existing_base[0]
                try:
                    self.tgt.write("account.tax", [base_tid], vals)
                except Exception as exc:
                    logger.warning(
                        "[taxes] Failed to update existing tax %s (id=%s): %s",
                        tax["name"], base_tid, exc,
                    )
                self.mapper.set("account.tax", sid, base_tid)
                # Ensure repartition lines on the reused tax match the source.
                try:
                    self._migrate_repartition_lines(tax, base_tid)
                except Exception as exc:
                    logger.warning(
                        "[taxes] Failed to update repartition lines for tax %s (id=%s): %s",
                        tax["name"], base_tid, exc,
                    )
                self.skipped += 1
                continue

            tid = self._safe_create("account.tax", vals, sid)
            if tid:
                self._migrate_repartition_lines(tax, tid)

        # Second pass: set children on group taxes (taxes of type "group")
        # after all individual taxes have been created and mapped.
        for tax in src_taxes:
            if tax.get("amount_type") != "group":
                continue
            children = tax.get("children_tax_ids") or []
            if not children:
                continue
            group_sid = tax["id"]
            group_tid = self.mapper.get("account.tax", group_sid)
            if not group_tid:
                continue

            # Ensure the mapped target tax still exists on the target DB
            try:
                chk = self.tgt.read("account.tax", [group_tid], ["id"])
            except Exception:
                chk = []
            if not chk:
                continue

            child_tids = []
            for child_sid in children:
                ct = self.mapper.get("account.tax", child_sid)
                if ct:
                    child_tids.append(ct)
            if not child_tids:
                continue

            try:
                self.tgt.write(
                    "account.tax",
                    [group_tid],
                    {"children_tax_ids": [(6, 0, child_tids)]},
                )
            except Exception as exc:
                logger.warning(
                    "[taxes] Failed to set children for group tax %s (id=%s): %s",
                    tax["name"], group_tid, exc,
                )

        self.mapper.save()

    def _migrate_repartition_lines(self, src_tax: dict, target_tax_id: int):
        """Recreate invoice and refund repartition lines on the target tax."""
        for line_type in ("invoice", "refund"):
            field_name = f"{line_type}_repartition_line_ids"
            src_line_ids = src_tax.get(field_name, [])
            if not src_line_ids:
                continue

            src_lines = self.src.read(
                "account.tax.repartition.line", src_line_ids,
                fields=["factor_percent", "repartition_type", "account_id",
                         "tag_ids", "sequence"],
            )

            # Delete auto-created repartition lines on target
            existing_lines = self.tgt.search_read(
                "account.tax.repartition.line",
                [("tax_id", "=", target_tax_id),
                 ("document_type", "=", line_type)],
                fields=["id"],
            )
            if existing_lines:
                try:
                    self.tgt.execute(
                        "account.tax.repartition.line", "unlink",
                        [l["id"] for l in existing_lines],
                    )
                except Exception:
                    pass  # Some lines may be protected

            for line in src_lines:
                account_tid = self._resolve_id("account.account", line.get("account_id"))
                line_vals = {
                    "tax_id": target_tax_id,
                    "factor_percent": line.get("factor_percent", 100.0),
                    "repartition_type": line["repartition_type"],
                    "document_type": line_type,
                }
                if account_tid:
                    line_vals["account_id"] = account_tid

                try:
                    self.tgt.create("account.tax.repartition.line", line_vals)
                except Exception as exc:
                    logger.warning(
                        "Failed to create repartition line for tax %d: %s",
                        target_tax_id, exc,
                    )
