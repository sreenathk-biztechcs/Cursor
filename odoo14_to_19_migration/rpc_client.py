"""
XML-RPC client wrapper for connecting to Odoo instances.
Provides authenticated access to models via execute_kw.
"""
import logging
import time
import xmlrpc.client

logger = logging.getLogger(__name__)


class OdooRPC:
    """Thread-safe XML-RPC client for a single Odoo instance."""

    def __init__(self, url: str, db: str, user: str, password: str, label: str = ""):
        self.url = url.rstrip("/")
        self.db = db
        self.user = user
        self.password = password
        self.label = label or url
        self.uid = None
        self._common = None
        self._object = None

    def connect(self):
        """Authenticate and store the user ID."""
        self._common = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/common", allow_none=True
        )
        self._object = xmlrpc.client.ServerProxy(
            f"{self.url}/xmlrpc/2/object", allow_none=True
        )
        self.uid = self._common.authenticate(self.db, self.user, self.password, {})
        if not self.uid:
            raise ConnectionError(
                f"[{self.label}] Authentication failed for {self.user}@{self.db}"
            )
        version_info = self._common.version()
        self.server_version = version_info.get("server_version", "?")
        # Extract major version number (e.g. "14.0" → 14, "19.0+e" → 19)
        try:
            self.server_major = int(self.server_version.split(".")[0])
        except (ValueError, IndexError):
            self.server_major = 0
        logger.info(
            "[%s] Connected as uid=%s  server=%s (major=%d)",
            self.label, self.uid, self.server_version, self.server_major,
        )
        return self

    def model_exists(self, model_name: str) -> bool:
        """Check if a model exists on this Odoo instance."""
        try:
            result = self.search("ir.model", [("model", "=", model_name)], limit=1)
            return bool(result)
        except Exception:
            return False

    def execute(self, model: str, method: str, *args, **kwargs):
        """Call execute_kw with automatic retry on transient failures."""
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                return self._object.execute_kw(
                    self.db, self.uid, self.password, model, method, list(args), kwargs
                )
            except xmlrpc.client.Fault as exc:
                logger.error(
                    "[%s] RPC fault on %s.%s (attempt %d/%d): %s",
                    self.label, model, method, attempt, max_retries, exc.faultString,
                )
                if attempt == max_retries:
                    raise
            except (ConnectionError, OSError) as exc:
                logger.warning(
                    "[%s] Connection error on %s.%s (attempt %d/%d): %s",
                    self.label, model, method, attempt, max_retries, exc,
                )
                if attempt == max_retries:
                    raise
                time.sleep(2 ** attempt)

    # ── Convenience helpers ──────────────────────────────────────────────

    def search(self, model, domain, **kw):
        return self.execute(model, "search", domain, **kw)

    def read(self, model, ids, fields=None):
        if fields:
            return self.execute(model, "read", ids, fields=fields)
        return self.execute(model, "read", ids)

    def search_read(self, model, domain, fields=None, **kw):
        opts = dict(kw)
        if fields:
            opts["fields"] = fields
        return self.execute(model, "search_read", domain, **opts)

    def search_count(self, model, domain):
        return self.execute(model, "search_count", domain)

    def create(self, model, vals):
        return self.execute(model, "create", vals)

    def write(self, model, ids, vals):
        return self.execute(model, "write", ids, vals)

    def get_xml_id(self, model, res_id):
        """Return the first external ID for a record, or '' if none."""
        result = self.execute(
            "ir.model.data", "search_read",
            [("model", "=", model), ("res_id", "=", res_id)],
            fields=["module", "name"], limit=1,
        )
        if result:
            return f"{result[0]['module']}.{result[0]['name']}"
        return ""

    def resolve_xml_id(self, xml_id: str):
        """Return the res_id for an external ID, or None."""
        if not xml_id or "." not in xml_id:
            return None
        module, name = xml_id.split(".", 1)
        result = self.execute(
            "ir.model.data", "search_read",
            [("module", "=", module), ("name", "=", name)],
            fields=["res_id"], limit=1,
        )
        return result[0]["res_id"] if result else None

    def fields_get(self, model, attributes=None):
        attrs = attributes or ["string", "type", "required"]
        return self.execute(model, "fields_get", attributes=attrs)
