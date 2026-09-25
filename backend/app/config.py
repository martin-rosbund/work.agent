"""Compatibility import; implementation lives in app.core.config."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("app.core.config")
