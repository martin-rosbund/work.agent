"""Compatibility import for agent orchestration."""

import sys

from app.features.agent import service

sys.modules[__name__] = service
