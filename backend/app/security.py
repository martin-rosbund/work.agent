"""Compatibility import; implementation lives in app.core.security."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("app.core.security")
