"""Microsoft adapter compatibility facade."""

from .core.utils import date
from .integrations.microsoft.client import *
from .integrations.microsoft.sync import (
    _sync,
    reconcile,
    remove_item,
    sync_source,
    upsert,
)
