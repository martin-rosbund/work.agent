"""Compatibility facade for shared application services."""

from app.core.events import audit, event
from app.core.jobs import enqueue
from app.core.settings import DEFAULT_AGENT, agent_config, put_setting, setting
from app.core.utils import date, digest, serialize
from app.features.content.storage import item_dict, replace_chunks, visible_item
from app.features.knowledge.storage import export_knowledge, save_knowledge
