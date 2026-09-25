"""Compatibility import; implementation lives in app.features.knowledge.extraction."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("app.features.knowledge.extraction")
