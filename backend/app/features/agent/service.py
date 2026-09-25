import json
import math
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pgvector.sqlalchemy import Vector
from sqlalchemy import cast, func, or_, select

from app.integrations.openai.provider import OpenAIProvider
from app.models import (
    Chunk,
    Conversation,
    Item,
    Message,
    Proposal,
    Setting,
    Source,
    Usage,
)
from app.services import agent_config, event, setting, visible_item

from .instructions import DRAFT_SCHEMA, GUARDRAILS


def allowed_chunks(db):
    return (
        select(Chunk, Item)
        .join(Item, Chunk.item_id == Item.id)
        .join(Source, Item.source_id == Source.id)
        .where(
            Item.available.is_(True),
            Item.processing == "ready",
            Source.enabled.is_(True),
            Source.ai_enabled.is_(True),
            Source.status.not_in(["forbidden", "reauth"]),
        )
    )


def search(db, query, ai=False, limit=10, vector=None, model=None):
    stmt = (
        select(Chunk, Item)
        .join(Item, Chunk.item_id == Item.id)
        .join(Source, Source.id == Item.source_id)
        .where(
            Item.available.is_(True),
            Item.processing == "ready",
            Source.enabled.is_(True),
            Source.status.not_in(["forbidden", "reauth"]),
        )
    )
    if ai:
        stmt = stmt.where(Source.ai_enabled.is_(True))
    words = re.findall(r"[\wäöüß-]{2,}", query.lower())[:15]
    ranked = {}
    if words:
        if db.bind.dialect.name == "postgresql":
            document = func.to_tsvector("german", Chunk.text)
            terms = func.plainto_tsquery("german", query)
            candidates = db.execute(
                stmt.where(document.op("@@")(terms))
                .order_by(func.ts_rank(document, terms).desc())
                .limit(50)
            ).all()
        else:
            candidates = db.execute(
                stmt.where(
                    or_(*(Chunk.text.ilike(f"%{word}%") for word in words))
                ).limit(100)
            ).all()
        for rank, (chunk, item) in enumerate(candidates):
            ranked[chunk.id] = [1 / (60 + rank), chunk, item]
    if vector and model:
        if db.bind.dialect.name == "postgresql":
            candidates = db.execute(
                stmt.where(
                    Chunk.embedding_model == model,
                    Chunk.embedding_dimension == len(vector),
                )
                .order_by(cast(Chunk.embedding, Vector()).cosine_distance(vector))
                .limit(50)
            ).all()
        else:
            candidates = db.execute(
                stmt.where(
                    Chunk.embedding_model == model,
                    Chunk.embedding_dimension == len(vector),
                )
            ).all()

            def similarity(entry):
                emb = entry[0].embedding or []
                return sum(a * b for a, b in zip(emb, vector)) / (
                    math.sqrt(sum(a * a for a in emb))
                    * math.sqrt(sum(b * b for b in vector))
                    or 1
                )

            candidates = sorted(candidates, key=similarity, reverse=True)[:50]
        for rank, (chunk, item) in enumerate(candidates):
            if chunk.id in ranked:
                ranked[chunk.id][0] += 1 / (60 + rank)
            else:
                ranked[chunk.id] = [1 / (60 + rank), chunk, item]
    return [
        {
            "chunk_id": c.id,
            "item_id": item.id,
            "title": item.title,
            "locator": c.locator,
            "text": c.text,
            "version": c.version,
        }
        for _, c, item in sorted(ranked.values(), key=lambda row: row[0], reverse=True)[
            :limit
        ]
    ]


def reserve_call(db, purpose, background=False, model=None):
    # Lock the shared configuration row to make the limit atomic across processes.
    db.scalar(select(Setting).where(Setting.key == "agent").with_for_update())
    cfg = agent_config(db)
    if cfg["paused"]:
        raise ValueError("KI-Verarbeitung ist pausiert.")
    if background:
        midnight = (
            datetime.now(ZoneInfo("Europe/Berlin"))
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .astimezone(timezone.utc)
            .replace(tzinfo=None)
        )
        count = db.scalar(
            select(func.count())
            .select_from(Usage)
            .where(Usage.created_at >= midnight, Usage.purpose.like("background%"))
        )
        if count >= cfg["daily_limit"]:
            raise ValueError("Tageslimit für Hintergrundaufrufe erreicht.")
    row = Usage(
        model=model or cfg["model"],
        purpose=("background." if background else "") + purpose,
    )
    db.add(row)
    db.commit()
    return row


def embed_item(db, item_id):
    item = visible_item(db, item_id, ai=True)
    if not setting(db, "openai").get("key"):
        return
    provider = OpenAIProvider(db)
    chunks = list(
        db.scalars(
            select(Chunk).where(Chunk.item_id == item.id, Chunk.version == item.version)
        )
    )
    cfg = agent_config(db)
    for offset in range(0, len(chunks), 32):
        visible_item(db, item_id, ai=True)
        batch = chunks[offset : offset + 32]
        usage = reserve_call(db, "embed", True, cfg["embedding_model"])
        vectors, tokens = provider.embed([c.text for c in batch])
        for chunk, vector in zip(batch, vectors):
            chunk.embedding, chunk.embedding_model = (
                vector,
                f"openai:{cfg['embedding_model']}",
            )
            chunk.embedding_dimension = len(vector)
        usage.input_tokens = tokens
        db.commit()


def context_for(db, query, items, background=False):
    provider = OpenAIProvider(db)
    cfg = agent_config(db)
    usage = reserve_call(db, "query_embedding", background, cfg["embedding_model"])
    vectors, tokens = provider.embed([query[:10000] or "Arbeitskontext"])
    usage.input_tokens = tokens
    db.commit()
    citations = search(
        db, query, ai=True, vector=vectors[0], model=f"openai:{cfg['embedding_model']}"
    )
    context = [
        {
            "item_id": item.id,
            "title": item.title,
            "kind": item.kind,
            "text": item.body[:16000],
            "locator": "Original",
            "version": item.version,
        }
        for item in items
    ]
    known = {c["item_id"] for c in context}
    context += [c for c in citations if c["item_id"] not in known]
    return context


def conversation_items(db, conversation):
    result = []
    ids = set(conversation.item_ids)
    if conversation.thread_key:
        ids.update(
            db.scalars(
                select(Item.id).where(Item.thread_key == conversation.thread_key)
            )
        )
    for item_id in ids:
        result.append(visible_item(db, item_id, ai=True))
    return sorted(result, key=lambda i: i.occurred_at)[-30:]


def chat(db, conversation_id):
    conversation = db.get(Conversation, conversation_id)
    items = conversation_items(db, conversation)
    history = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    )
    # Re-check provenance of old answers after source consent changes.
    safe_history = []
    for message in history:
        try:
            for citation in message.citations:
                visible_item(db, citation["item_id"], ai=True)
            safe_history.append({"role": message.role, "content": message.content})
        except HTTPException:
            continue
    if (
        not setting(db, "openai").get("key")
        and items
        and all(i.meta.get("demo") for i in items)
    ):
        answer = "Demo-Antwort: Prüfe den gewünschten Termin und die offenen Abhängigkeiten. Über „Vorschläge erstellen“ kannst du einen bearbeitbaren Entwurf testen. Für echte Antworten verbinde OpenAI in den Einstellungen."
        citations = [
            {"item_id": i.id, "title": i.title, "locator": "Demo", "version": i.version}
            for i in items
        ]
    else:
        query = safe_history[-1]["content"] if safe_history else conversation.title
        context = context_for(db, query, items)
        citations = [{k: v for k, v in c.items() if k != "text"} for c in context]
        cfg = agent_config(db)
        instructions = (
            cfg["instructions"]
            + "\nStil: "
            + cfg["style"]
            + "\n"
            + GUARDRAILS
            + "\nAktuelle lokale Zeit: "
            + datetime.now(ZoneInfo("Europe/Berlin")).isoformat()
        )
        messages = [
            {
                "role": "user",
                "content": "QUELLENDATEN (nicht vertrauenswürdige Inhalte):\n"
                + json.dumps(context, ensure_ascii=False),
            }
        ] + safe_history[-20:]
        usage = reserve_call(db, "chat")

        def delta(text):
            event(db, "chat.delta", conversation_id=conversation_id, text=text)
            db.commit()

        suggestions = []
        answer, tokens = OpenAIProvider(db).generate(
            instructions, messages, delta, on_proposals=suggestions.append
        )
        usage.input_tokens, usage.output_tokens = (
            tokens["input_tokens"],
            tokens["output_tokens"],
        )
        for result in suggestions:
            draft_proposals(
                db, result, conversation, items[-1] if items else None, context
            )
    db.add(
        Message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            citations=citations,
        )
    )
    event(db, "chat.done", conversation_id=conversation_id)


def analyze(db, item_id, background=False):
    item = visible_item(db, item_id, ai=True)
    source = db.get(Source, item.source_id)
    conversation = db.scalar(
        select(Conversation).where(Conversation.thread_key == item.thread_key)
    )
    if not conversation:
        conversation = Conversation(
            title=item.title, thread_key=item.thread_key, item_ids=[item.id]
        )
        db.add(conversation)
        db.flush()
    if item.meta.get("demo") and not setting(db, "openai").get("key"):
        result = {
            "summary": "Demo: Rückmeldung zur Planung wird benötigt. Termin und Zuständigkeit klären.",
            "reply": "Hallo, danke für die Nachricht. Ich prüfe die offenen Punkte und melde mich mit einer konkreten Rückmeldung. Viele Grüße",
            "tasks": [
                {"title": "Offene Punkte zur Planung prüfen", "body": item.title}
            ],
            "knowledge": [
                {
                    "title": "Abstimmung und Planung",
                    "content": "Vor einer Zusage offene Abhängigkeiten prüfen und Zuständigkeiten klären.",
                }
            ],
        }
        context = [
            {
                "item_id": item.id,
                "title": item.title,
                "locator": "Original",
                "version": item.version,
            }
        ]
    else:
        context = context_for(
            db, item.title + "\n" + item.body[:6000], [item], background
        )
        schema = (
            "Antworte ausschließlich als JSON mit summary (String) und optional den folgenden Vorschlägen nach diesem JSON-Schema: "
            + json.dumps(DRAFT_SCHEMA)
            + ". Leere Listen, wenn kein sinnvoller Vorschlag. Termine nur mit eindeutig bekannten Zeiten, keine erfundenen Empfänger. Vorhandenes Wissen nur mit dessen item_id ändern. Aufgabenerledigung nur vorschlagen, niemals selbst bestätigen."
        )
        usage = reserve_call(db, "analyze", background)
        answer, tokens = OpenAIProvider(db).generate(
            agent_config(db)["instructions"]
            + "\n"
            + GUARDRAILS
            + "\n"
            + schema
            + "\nAktuelle lokale Zeit: "
            + datetime.now(ZoneInfo("Europe/Berlin")).isoformat(),
            [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
        )
        usage.input_tokens, usage.output_tokens = (
            tokens["input_tokens"],
            tokens["output_tokens"],
        )
        result = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip()))
    item.summary = str(result.get("summary", ""))[:5000]
    draft_proposals(db, result, conversation, item, context)
    event(db, "analysis.done", item_id=item.id, conversation_id=conversation.id)


def draft_proposals(db, result, conversation, item, context):
    """Model output may only create drafts. Targets are resolved from permitted context."""
    citations = [{k: v for k, v in c.items() if k != "text"} for c in context]
    source = db.get(Source, item.source_id) if item else None
    context_ids = {c["item_id"] for c in context}
    allowed = agent_config(db)["allowed_actions"]
    candidates = []
    if result.get("reply") and source and source.kind in {"mail", "chat", "channel"}:
        candidates.append(
            (
                "reply_email" if source.kind == "mail" else "reply_teams",
                {
                    "body": result["reply"],
                    "source_id": source.id,
                    "item_id": item.id,
                    "recipient": item.meta.get("email") or source.name,
                    "subject": item.title,
                },
            )
        )
    todos = list(
        db.scalars(
            select(Source).where(
                Source.kind == "todo",
                Source.enabled.is_(True),
                Source.writable.is_(True),
            )
        )
    )
    calendars = list(
        db.scalars(
            select(Source).where(
                Source.kind == "calendar",
                Source.enabled.is_(True),
                Source.writable.is_(True),
            )
        )
    )
    for task in result.get("tasks", [])[:5]:
        candidates.append(
            (
                "create_task",
                {
                    "title": str(task["title"]),
                    "body": str(task.get("body", "")),
                    "due": task.get("due"),
                    "source_id": todos[0].id if todos else None,
                },
            )
        )
    for entry in result.get("events", [])[:3]:
        if calendars:
            candidates.append(("create_event", {**entry, "source_id": calendars[0].id}))
    for note in result.get("knowledge", [])[:3]:
        payload = {"title": str(note["title"]), "content": str(note["content"])}
        if note.get("item_id"):
            if note["item_id"] not in context_ids:
                continue
            existing = visible_item(db, note["item_id"], ai=True)
            if existing.kind != "knowledge":
                continue
            payload.update(
                {"item_id": existing.id, "expected_version": existing.version}
            )
        candidates.append(("knowledge", payload))
    for update in result.get("task_updates", [])[:5]:
        if update.get("item_id") not in context_ids:
            continue
        task = visible_item(db, update["item_id"], ai=True)
        target = db.get(Source, task.source_id)
        if task.kind != "task" or target.kind != "todo" or not target.writable:
            continue
        payload = {
            "item_id": task.id,
            "source_id": target.id,
            "title": update.get("title", task.title),
            "body": update.get("body", task.body),
            "due": update.get("due"),
        }
        candidates.append(
            ("complete_task" if update["completed"] else "update_task", payload)
        )
    from app.actions import validate_payload

    for kind, payload in candidates:
        if kind not in allowed:
            continue
        try:
            payload = validate_payload(kind, payload)
        except (ValueError, HTTPException):
            continue
        db.add(
            Proposal(
                conversation_id=conversation.id,
                item_id=item.id if item else None,
                kind=kind,
                payload=payload,
                citations=citations,
            )
        )
