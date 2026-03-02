"""
Base class for all migrators.

Provides common utilities: batch iteration, progress logging,
ID resolution helpers, multi-company support, field detection for
both source and target, and the dry-run guard.
"""
import logging
from typing import Optional

from .rpc_client import OdooRPC
from .id_mapper import IDMapper
from . import config

logger = logging.getLogger(__name__)

# Cache: {"src:model" or "tgt:model": set of field names or None if fetch failed}
_field_cache: dict[str, set[str] | None] = {}


class BaseMigrator:
    """Subclasses override `run()` to implement their migration logic."""

    name: str = "base"

    def __init__(self, source: OdooRPC, target: OdooRPC, mapper: IDMapper,
                 company_map: dict = None):
        self.src = source
        self.tgt = target
        self.mapper = mapper
        self.dry_run = config.DRY_RUN
        self.batch_size = config.BATCH_SIZE
        self.created = 0
        self.skipped = 0
        self.errors = 0
        # {source_company_id: {"id": int, "name": str, "short": str, "analytic_id": int}}
        self.company_map = company_map or {}

    def run(self):
        raise NotImplementedError

    # ── Field detection (source & target) ───────────────────────────────

    def _get_fields(self, rpc: OdooRPC, prefix: str, model: str) -> set[str] | None:
        """Return field names for a model on a given instance (cached).
        Returns None if the fetch failed (so callers can distinguish from empty)."""
        key = f"{prefix}:{model}"
        if key not in _field_cache:
            try:
                fields_info = rpc.fields_get(model, attributes=["type"])
                _field_cache[key] = set(fields_info.keys())
                logger.debug("[fields] %s:%s has %d fields", prefix, model, len(_field_cache[key]))
            except Exception as exc:
                logger.warning("[fields] Failed to get fields for %s:%s: %s", prefix, model, exc)
                _field_cache[key] = None
        return _field_cache[key]

    def _target_has_field(self, model: str, field_name: str) -> bool:
        fields = self._get_fields(self.tgt, "tgt", model)
        if fields is None:
            return True  # assume field exists if we can't check
        return field_name in fields

    def _source_has_field(self, model: str, field_name: str) -> bool:
        fields = self._get_fields(self.src, "src", model)
        if fields is None:
            return True  # assume field exists if we can't check
        return field_name in fields

    def _add_company_to_domain(self, model: str, domain: list, company_id: int):
        """Append company_id filter ONLY if the TARGET model has that field."""
        if company_id and self._target_has_field(model, "company_id"):
            domain.append(("company_id", "=", company_id))

    def _add_company_to_vals(self, model: str, vals: dict, company_id: int):
        """Set company_id in vals ONLY if the TARGET model has that field."""
        if company_id and self._target_has_field(model, "company_id"):
            vals["company_id"] = company_id

    def _src_company_domain(self, model: str, company_id: int) -> list:
        """Build a SOURCE company_id domain, or empty if field doesn't exist."""
        if self._source_has_field(model, "company_id"):
            return [("company_id", "=", company_id)]
        return []

    def _src_company_domain_with_false(self, model: str, company_id: int) -> list:
        """Build domain matching company_id OR False (shared records) on SOURCE."""
        if self._source_has_field(model, "company_id"):
            return [("company_id", "in", [company_id, False])]
        return []

    # ── Multi-company helpers ────────────────────────────────────────────

    def get_source_company_ids(self) -> list[int]:
        """Return list of source company IDs being migrated."""
        return list(self.company_map.keys())

    def get_company_short(self, company_id: int) -> str:
        """Return the short prefix for a source company."""
        info = self.company_map.get(company_id, {})
        return info.get("short", "")

    def get_company_name(self, company_id: int) -> str:
        info = self.company_map.get(company_id, {})
        return info.get("name", f"Company-{company_id}")

    def get_company_analytic_id(self, company_id: int) -> Optional[int]:
        """Return the target analytic account ID for a source company."""
        info = self.company_map.get(company_id, {})
        return info.get("analytic_id")

    def prefix_ref(self, ref: str, company_id: int) -> str:
        """Prefix a ref/document number with the company short name."""
        if not config.REF_PREFIX_BY_COMPANY:
            return ref or ""
        short = self.get_company_short(company_id)
        ref = ref or ""
        if short:
            return f"[{short}] {ref}"
        return ref

    # ── Standard helpers ─────────────────────────────────────────────────

    def log_summary(self):
        logger.info(
            "[%s] Done — created=%d  skipped=%d  errors=%d",
            self.name, self.created, self.skipped, self.errors,
        )

    def _resolve_id(self, model: str, source_val) -> Optional[int]:
        """Resolve a Many2one value (int or [id, name]) to the mapped target id."""
        return self.mapper.resolve(model, source_val)

    def _resolve_ids(self, model: str, source_ids: list) -> list:
        """Resolve a list of source IDs to target IDs, dropping unmapped ones."""
        result = []
        for sid in (source_ids or []):
            tid = self.mapper.get(model, sid)
            if tid:
                result.append(tid)
        return result

    def _m2o(self, val):
        """Extract raw ID from a Many2one XML-RPC value (int or [id, name])."""
        if not val:
            return None
        return val[0] if isinstance(val, (list, tuple)) else val

    def _m2o_company(self, val) -> Optional[int]:
        """Extract company_id from a Many2one value, return int or None."""
        return self._m2o(val)

    def _iter_batches(self, model: str, domain: list, fields: list, order: str = "id asc"):
        """Yield records from source in batches."""
        total = self.src.search_count(model, domain)
        logger.info("[%s] Fetching %d records from %s", self.name, total, model)
        offset = 0
        while offset < total:
            records = self.src.search_read(
                model, domain, fields=fields,
                limit=self.batch_size, offset=offset, order=order,
            )
            if not records:
                break
            yield records
            offset += len(records)

    def _find_target_by_code(self, model: str, code: str, company_id: int = None):
        """Find a record on target by its 'code' field (company-aware)."""
        domain = [("code", "=", code)]
        self._add_company_to_domain(model, domain, company_id)
        result = self.tgt.search(model, domain, limit=1)
        return result[0] if result else None

    def _find_target_by_name(self, model: str, name: str, company_id: int = None):
        """Find a record on target by its 'name' field (company-aware)."""
        domain = [("name", "=", name)]
        self._add_company_to_domain(model, domain, company_id)
        result = self.tgt.search(model, domain, limit=1)
        return result[0] if result else None

    def _safe_create(self, model: str, vals: dict, source_id: int) -> Optional[int]:
        """Create a record on target; auto-strips unknown fields, logs errors."""
        # Remove fields that don't exist on the target model
        target_fields = self._get_fields(self.tgt, "tgt", model)
        if target_fields is not None:
            unknown = [k for k in vals if k not in target_fields]
            for k in unknown:
                logger.debug(
                    "[%s] Stripping unknown field '%s' from %s create vals",
                    self.name, k, model,
                )
                del vals[k]

        if self.dry_run:
            logger.info("[%s][DRY-RUN] Would create %s: %s", self.name, model, vals)
            self.created += 1
            return None
        try:
            tid = self.tgt.create(model, vals)
            self.mapper.set(model, source_id, tid)
            self.created += 1
            return tid
        except Exception as exc:
            logger.error(
                "[%s] Failed to create %s (source_id=%s): %s\n  vals=%s",
                self.name, model, source_id, exc, vals,
            )
            self.errors += 1
            return None
