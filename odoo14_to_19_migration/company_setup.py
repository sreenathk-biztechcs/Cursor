"""
Discover source companies and prepare the multi-company → single-company
consolidation: short-name prefixes, analytic plan/accounts for tracking.
"""
import logging
import re
from .rpc_client import OdooRPC
from .id_mapper import IDMapper
from . import config

logger = logging.getLogger(__name__)


def _make_short_name(name: str, max_len: int = 3) -> str:
    """
    Generate a short prefix from a company name.
    "Alpha Trading Corp" → "ALP"
    "Beta Services Pvt Ltd" → "BET"
    """
    name = re.sub(r"[^A-Za-z0-9 ]", "", name).strip()
    words = name.split()
    if len(words) == 1:
        return words[0][:max_len].upper()
    return "".join(w[0] for w in words[:max_len]).upper()


def discover_source_companies(source: OdooRPC) -> list[dict]:
    """Fetch all companies from the source Odoo 14 instance."""
    # Note: res.company has no 'active' field in Odoo 14, so we use an empty domain
    companies = source.search_read(
        "res.company", [],
        fields=["id", "name", "currency_id"],
        order="id asc",
    )
    logger.info("Discovered %d companies in source:", len(companies))
    for c in companies:
        logger.info("  [%d] %s", c["id"], c["name"])
    return companies


def resolve_source_company_ids(source: OdooRPC) -> list[int]:
    """
    Return the list of company IDs to migrate based on config.SOURCE_COMPANY_IDS.
    """
    raw = config.SOURCE_COMPANY_IDS.strip()
    if raw.lower() == "all":
        companies = discover_source_companies(source)
        return [c["id"] for c in companies]
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def build_company_map(source: OdooRPC, target: OdooRPC, mapper: IDMapper) -> dict:
    """
    Build the master company_map dict used by all migrators:
    {
        source_company_id: {
            "id": source_company_id,
            "name": "Alpha Trading Corp",
            "short": "ALP",
            "analytic_id": 42  (target analytic account ID, if tracking enabled)
        }
    }
    """
    company_ids = resolve_source_company_ids(source)
    companies = source.search_read(
        "res.company", [("id", "in", company_ids)],
        fields=["id", "name"],
        order="id asc",
    )

    company_map = {}
    used_shorts = set()

    for comp in companies:
        cid = comp["id"]
        name = comp["name"]

        # Determine short name
        if cid in config.COMPANY_SHORT_NAMES:
            short = config.COMPANY_SHORT_NAMES[cid]
        else:
            short = _make_short_name(name)
            # Ensure uniqueness
            base_short = short
            counter = 1
            while short in used_shorts:
                short = f"{base_short}{counter}"
                counter += 1

        used_shorts.add(short)
        company_map[cid] = {
            "id": cid,
            "name": name,
            "short": short,
            "analytic_id": None,
        }
        logger.info("Company %d [%s] → prefix '%s'", cid, name, short)

    # Create analytic tracking on target if enabled
    if config.ANALYTIC_TRACKING:
        _setup_analytic_tracking(target, mapper, company_map)

    return company_map


def _has_field(target: OdooRPC, model: str, field_name: str) -> bool:
    """Check if a field exists on a target model."""
    try:
        fields_info = target.fields_get(model, attributes=["type"])
        return field_name in fields_info
    except Exception:
        return False


def _setup_analytic_tracking(target: OdooRPC, mapper: IDMapper, company_map: dict):
    """
    Create an analytic plan 'Legacy Company' and one analytic account per
    source company on the target Odoo 19 instance.
    """
    logger.info("Setting up analytic tracking for legacy companies...")

    # Check if analytic plan model exists (Odoo 17+)
    if not target.model_exists("account.analytic.plan"):
        logger.warning(
            "account.analytic.plan model not found on target — "
            "skipping analytic tracking. Install the Analytic module."
        )
        return

    plan_name = "Legacy Company"
    # Search without company_id first (it may not exist on this model)
    existing_plan = target.search(
        "account.analytic.plan",
        [("name", "=", plan_name)],
        limit=1,
    )
    if existing_plan:
        plan_id = existing_plan[0]
        logger.info("Analytic plan '%s' already exists (id=%d)", plan_name, plan_id)
    else:
        plan_vals = {"name": plan_name}
        if _has_field(target, "account.analytic.plan", "company_id"):
            plan_vals["company_id"] = config.TARGET_COMPANY_ID
        plan_id = target.create("account.analytic.plan", plan_vals)
        logger.info("Created analytic plan '%s' (id=%d)", plan_name, plan_id)

    # Create one analytic account per source company
    has_company = _has_field(target, "account.analytic.account", "company_id")

    for cid, info in company_map.items():
        acct_name = f"[{info['short']}] {info['name']}"

        existing = target.search(
            "account.analytic.account",
            [("name", "=", acct_name), ("plan_id", "=", plan_id)],
            limit=1,
        )
        if existing:
            analytic_id = existing[0]
            logger.info("  Analytic account '%s' exists (id=%d)", acct_name, analytic_id)
        else:
            acct_vals = {
                "name": acct_name,
                "plan_id": plan_id,
            }
            if has_company:
                acct_vals["company_id"] = config.TARGET_COMPANY_ID
            analytic_id = target.create("account.analytic.account", acct_vals)
            logger.info("  Created analytic account '%s' (id=%d)", acct_name, analytic_id)

        info["analytic_id"] = analytic_id
        mapper.set("analytic.legacy_company", cid, analytic_id)

    mapper.save()
