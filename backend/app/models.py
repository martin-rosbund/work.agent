"""Compatibility import; implementation lives in app.core.models."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("app.core.models")
