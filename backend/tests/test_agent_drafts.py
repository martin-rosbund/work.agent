from sqlalchemy import select
from app import ai
from app.models import Conversation, Proposal, KnowledgeVersion
from app.services import save_knowledge
from types import SimpleNamespace
import pytest


def test_agent_only_proposes_memory_update_and_keeps_expected_version(db, mail):
    source, item = mail
    note = save_knowledge(db, "Known rule", "Old content")
    db.get(
        __import__("app.models", fromlist=["Source"]).Source, note.source_id
    ).ai_enabled = True
    conversation = Conversation(title="Review", item_ids=[item.id])
    db.add(conversation)
    db.flush()
    context = [{"item_id": note.id, "version": note.version, "title": note.title}]
    ai.draft_proposals(
        db,
        {
            "knowledge": [
                {"item_id": note.id, "title": "Known rule", "content": "New content"}
            ]
        },
        conversation,
        item,
        context,
    )
    db.commit()
    proposal = db.scalar(select(Proposal))
    assert proposal.status == "draft" and proposal.payload["expected_version"] == 1
    assert note.body == "Old content"
    assert len(list(db.scalars(select(KnowledgeVersion)))) == 1


def test_unknown_model_supplied_target_is_ignored(db, mail):
    source, item = mail
    conversation = Conversation(title="Review", item_ids=[item.id])
    db.add(conversation)
    db.flush()
    ai.draft_proposals(
        db,
        {
            "knowledge": [{"item_id": "arbitrary", "title": "x", "content": "y"}],
            "task_updates": [{"item_id": "arbitrary", "completed": True}],
        },
        conversation,
        item,
        [],
    )
    db.commit()
    assert list(db.scalars(select(Proposal))) == []


def test_chat_can_propose_local_task_without_external_execution(db):
    conversation = Conversation(title="Planning", item_ids=[])
    db.add(conversation)
    db.flush()
    ai.draft_proposals(
        db,
        {"tasks": [{"title": "Review proposal", "body": "Read the document"}]},
        conversation,
        None,
        [],
    )
    db.commit()
    p = db.scalar(select(Proposal))
    assert (
        p.kind == "create_task"
        and p.status == "draft"
        and not p.payload.get("source_id")
    )


@pytest.mark.parametrize("completed", [True, False])
def test_responses_stream_creates_only_complete_drafts(completed):
    events = [
        SimpleNamespace(
            type="response.output_item.done",
            item=SimpleNamespace(
                type="function_call",
                name="draft_actions",
                arguments='{"tasks":[{"title":"Review"}]}',
            ),
        )
    ]
    if completed:
        events.append(
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    usage=SimpleNamespace(input_tokens=20, output_tokens=10)
                ),
            )
        )
    calls, proposals = [], []

    def create(**kwargs):
        calls.append(kwargs)
        return iter(events)

    provider = object.__new__(ai.OpenAIProvider)
    provider.config = {"model": "test-model"}
    provider.client = SimpleNamespace(responses=SimpleNamespace(create=create))
    if completed:
        text, usage = provider.generate(
            "instructions", [], on_proposals=proposals.append
        )
        assert proposals[0]["tasks"][0]["title"] == "Review"
        assert "Vorschläge" in text and usage["input_tokens"] == 20
    else:
        with pytest.raises(ValueError, match="unterbrochen"):
            provider.generate("instructions", [], on_proposals=proposals.append)
        assert proposals == []
    assert calls[0]["store"] is False and calls[0]["stream"] is True
    assert calls[0]["tools"][0]["name"] == "draft_actions"


def test_demo_contains_calendar_and_task_without_cloud_jobs(db):
    from app.demo import seed
    from app.models import Item, Job

    seed(db)
    db.commit()
    calendar = db.scalar(select(Item).where(Item.kind == "calendar"))
    task = db.scalar(select(Item).where(Item.kind == "task"))
    assert calendar.title == "Produkt-Abstimmung"
    assert task.title == "Release-Checkliste aktualisieren"
    assert not list(db.scalars(select(Job).where(Job.kind == "analyze")))
