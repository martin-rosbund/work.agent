"""Operational messages without credentials, request bodies or provider responses."""

import logging

logger = logging.getLogger("workagent")


def worker_failure(exc):
    logger.error("Worker interrupted (%s); retrying in 5s", type(exc).__name__)
