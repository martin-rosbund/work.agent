import json
from typing import Protocol

from openai import OpenAI

from app.features.agent.instructions import DRAFT_TOOL
from app.security import decrypt
from app.services import agent_config, setting


class TextProvider(Protocol):
    def generate(
        self, instructions: str, messages: list, on_delta=None, on_proposals=None
    ): ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]): ...


class OpenAIProvider:
    def __init__(self, db):
        cfg = setting(db, "openai")
        if not cfg.get("key"):
            raise ValueError("Bitte zuerst einen OpenAI-API-Schlüssel einrichten.")
        self.client = OpenAI(api_key=decrypt(cfg["key"]), timeout=90, max_retries=1)
        self.config = agent_config(db)

    def generate(self, instructions, messages, on_delta=None, on_proposals=None):
        if not self.config["model"]:
            raise ValueError("Bitte ein Responses-fähiges Modell auswählen.")
        tools = [DRAFT_TOOL] if on_proposals else []
        response = self.client.responses.create(
            model=self.config["model"],
            instructions=instructions,
            input=messages,
            store=False,
            stream=True,
            max_output_tokens=5000,
            tools=tools,
        )
        parts, usage = [], {"input_tokens": 0, "output_tokens": 0}
        drafts = []
        completed = False
        for update in response:
            if update.type == "response.output_text.delta":
                parts.append(update.delta)
                if on_delta:
                    on_delta(update.delta)
            elif update.type == "response.completed":
                completed = True
                if update.response.usage:
                    usage = {
                        "input_tokens": update.response.usage.input_tokens,
                        "output_tokens": update.response.usage.output_tokens,
                    }
            elif (
                update.type == "response.output_item.done"
                and update.item.type == "function_call"
                and update.item.name == "draft_actions"
            ):
                drafts.append(json.loads(update.item.arguments))
            elif update.type in {"response.failed", "response.incomplete", "error"}:
                raise ValueError(
                    "Die Modellantwort wurde abgebrochen. Bitte erneut versuchen."
                )
        if not completed:
            raise ValueError(
                "Die Modellantwort wurde unterbrochen. Bitte erneut versuchen."
            )
        if on_proposals:
            for draft in drafts:
                on_proposals(draft)
        if drafts and not parts:
            parts.append(
                "Ich habe Vorschläge zur Prüfung vorbereitet. Du kannst sie bearbeiten und anschließend einzeln freigeben."
            )
        return "".join(parts), usage

    def embed(self, texts):
        result = self.client.embeddings.create(
            model=self.config["embedding_model"], input=texts
        )
        return [r.embedding for r in result.data], result.usage.total_tokens
