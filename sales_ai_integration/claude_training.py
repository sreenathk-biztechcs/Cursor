"""
claude_training.py

This module is a placeholder for any one-off initialization logic
you want to run when the Sales AI module is installed or upgraded.

In practice, Claude is not "trained" from Odoo – prompts and examples
are provided at call time. Here we simply log that the Sales AI
integration has been initialized successfully.
"""

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


@api.model
def _run_training(env):
    _logger.info("Sales AI: post-init hook executed. Prompts and settings are ready.")


def run(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _run_training(env)

