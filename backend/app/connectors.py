"""Compatibility import; implementation lives in app.integrations.registry."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("app.integrations.registry")
