from datetime import timedelta

from sqlalchemy import select

from app.config import DATA_DIR, MAX_FILE_BYTES, SUPPORTED_EXTENSIONS
from app.features.content.ingestion import remove_item, upsert
from app.models import Item, now, uid
from app.services import audit, date

from .client import Graph, GraphError, plain, q, source_scopes


def sync_source(db, source):
    graph = Graph(db, source_scopes(source))
    try:
        if source.kind == "chat" and source.config.get("mode") == "all_direct_incoming":
            from .direct_messages import sync_direct_messages

            return sync_direct_messages(db, source, graph)
        return _sync(db, source, graph)
    finally:
        graph.close()


def _sync(db, source, graph):
    cfg, cursor = source.config, dict(source.cursor)
    initial = source.last_sync is None
    cutoff = now() - timedelta(days=int(cfg.get("days", 90)))
    cutoff_s = cutoff.isoformat(timespec="seconds") + "Z"
    full = (
        initial
        or not cursor.get("reconciled")
        or date(cursor["reconciled"]) < now() - timedelta(days=1)
    )
    seen = set()
    if source.kind == "mail":
        snapshot = not cursor.get("delta")
        path = (
            cursor.get("delta")
            or f"/me/mailFolders/{q(cfg.get('folder_id', 'inbox'))}/messages/delta?$filter=receivedDateTime ge {cutoff_s}"
        )
        rows, delta = graph.pages(path)
        for msg in rows:
            if "@removed" in msg:
                remove_item(db, source.id, msg["id"])
                continue
            # Delta may contain only changed properties, including read state for
            # messages outside the requested time window. Fetch before indexing.
            if "body" not in msg or "receivedDateTime" not in msg:
                try:
                    msg = graph.request("GET", f"/me/messages/{q(msg['id'])}")
                except GraphError as exc:
                    if exc.status == 404:
                        remove_item(db, source.id, msg["id"])
                        continue
                    raise
            seen.add(msg["id"])
            if date(msg.get("receivedDateTime")) < cutoff and not db.scalar(
                select(Item.id).where(
                    Item.source_id == source.id, Item.external_id == msg["id"]
                )
            ):
                continue
            body = plain(msg.get("body", {}).get("content", ""))
            sender = msg.get("from", {}).get("emailAddress", {})
            upsert(
                db,
                source,
                msg["id"],
                "mail",
                msg.get("subject") or "(Ohne Betreff)",
                body,
                sender.get("name") or sender.get("address", ""),
                date(msg.get("receivedDateTime")),
                msg.get("conversationId", msg["id"]),
                msg.get("webLink", ""),
                {
                    "email": sender.get("address", ""),
                    "to": msg.get("toRecipients", []),
                    "cc": msg.get("ccRecipients", []),
                    "is_read": msg.get("isRead", False),
                },
                initial=initial,
            )
        if snapshot:
            reconcile(db, source, seen, cutoff)
        if delta:
            cursor["delta"] = delta
    elif source.kind in {"chat", "channel"}:
        if source.kind == "chat":
            since = cutoff if full else source.last_sync - timedelta(minutes=5)
            path = f"/chats/{q(cfg['chat_id'])}/messages?$top=50&$orderby=lastModifiedDateTime desc&$filter=lastModifiedDateTime gt {since.isoformat()}Z"
        else:
            path = f"/teams/{q(cfg['team_id'])}/channels/{q(cfg['channel_id'])}/messages?$top=50"
        rows, _ = graph.pages(path)
        for msg in rows:
            thread = (
                msg.get("replyToId") or msg["id"]
                if source.kind == "channel"
                else cfg["chat_id"]
            )
            entries = [msg]
            if source.kind == "channel":
                replies, _ = graph.pages(
                    f"/teams/{q(cfg['team_id'])}/channels/{q(cfg['channel_id'])}/messages/{q(msg['id'])}/replies?$top=50"
                )
                entries += replies
            for entry in entries:
                seen.add(entry["id"])
                if entry.get("deletedDateTime"):
                    remove_item(db, source.id, entry["id"])
                    continue
                if date(entry.get("createdDateTime")) < cutoff:
                    continue
                body = plain(entry.get("body", {}).get("content", ""))
                upsert(
                    db,
                    source,
                    entry["id"],
                    source.kind,
                    entry.get("subject") or body[:100] or "Teams-Nachricht",
                    body,
                    ((entry.get("from") or {}).get("user") or {}).get(
                        "displayName", ""
                    ),
                    date(entry.get("createdDateTime")),
                    thread,
                    entry.get("webUrl", ""),
                    {
                        "root_id": msg["id"],
                        "chat_id": cfg.get("chat_id"),
                        "team_id": cfg.get("team_id"),
                        "channel_id": cfg.get("channel_id"),
                    },
                    initial=initial,
                )
        if full or source.kind == "channel":
            reconcile(db, source, seen, cutoff)
            cursor["reconciled"] = now().isoformat()
    elif source.kind == "calendar":
        calendar = graph.request(
            "GET", f"/me/calendars/{q(cfg['calendar_id'])}?$select=id,isDefaultCalendar"
        )
        primary = calendar.get("isDefaultCalendar", False)
        if full or not primary:
            cursor.pop("delta", None)
        view = (
            "/me/calendarView/delta"
            if primary
            else f"/me/calendars/{q(cfg['calendar_id'])}/calendarView"
        )
        path = (
            cursor.get("delta")
            or f"{view}?startDateTime={cutoff_s}&endDateTime={(now() + timedelta(days=180)).isoformat()}Z"
        )
        rows, delta = graph.pages(path)
        for msg in rows:
            if "@removed" in msg or msg.get("isCancelled"):
                remove_item(db, source.id, msg["id"])
                continue
            seen.add(msg["id"])
            upsert(
                db,
                source,
                msg["id"],
                "calendar",
                msg.get("subject") or "Termin",
                plain(msg.get("body", {}).get("content", "")),
                msg.get("organizer", {}).get("emailAddress", {}).get("name", ""),
                date(msg.get("start", {}).get("dateTime")),
                web_url=msg.get("webLink", ""),
                meta={
                    "start": msg.get("start"),
                    "end": msg.get("end"),
                    "location": msg.get("location"),
                    "attendees": msg.get("attendees", []),
                    "etag": msg.get("@odata.etag"),
                },
                initial=True,
            )
        if full or not primary:
            reconcile(db, source, seen)
            cursor["reconciled"] = now().isoformat()
        if delta:
            cursor["delta"] = delta
    elif source.kind == "todo":
        rows, _ = graph.pages(f"/me/todo/lists/{q(cfg['list_id'])}/tasks")
        for task in rows:
            seen.add(task["id"])
            row, _ = upsert(
                db,
                source,
                task["id"],
                "task",
                task["title"],
                task.get("body", {}).get("content", ""),
                occurred_at=date(task.get("lastModifiedDateTime")),
                meta={
                    "list_id": cfg["list_id"],
                    "due": task.get("dueDateTime"),
                    "task_status": task.get("status"),
                    "etag": task.get("@odata.etag"),
                },
                initial=True,
            )
            row.status = "done" if task.get("status") == "completed" else "new"
        reconcile(db, source, seen)
    elif source.kind == "drive":
        drive, root = cfg["drive_id"], cfg["folder_id"]
        # Check access to the selected root even when a delta token remains valid.
        graph.request("GET", f"/drives/{q(drive)}/items/{q(root)}")
        folders = set(cursor.get("folders", [root]))
        rows, delta = ([], None)
        if cursor.get("delta") and not full:
            rows, delta = graph.pages(cursor["delta"])
            if any("folder" in entry or "deleted" in entry for entry in rows):
                full = True
        if full:
            # Capture the token BEFORE enumeration to avoid dropping changes during enumeration.
            _, delta = graph.pages(f"/drives/{q(drive)}/root/delta?token=latest")
            folders, rows, queue = {root}, [], [root]
            while queue:
                folder = queue.pop()
                children, _ = graph.pages(
                    f"/drives/{q(drive)}/items/{q(folder)}/children"
                )
                for child in children:
                    if "folder" in child:
                        if child["id"] not in folders:
                            folders.add(child["id"])
                            queue.append(child["id"])
                    elif "file" in child:
                        rows.append(child)
            cursor["reconciled"] = now().isoformat()
        for entry in rows:
            if (
                entry.get("deleted")
                or entry.get("parentReference", {}).get("id") not in folders
            ):
                remove_item(db, source.id, entry["id"])
                continue
            if "file" not in entry:
                continue
            seen.add(entry["id"])
            existing = db.scalar(
                select(Item).where(
                    Item.source_id == source.id, Item.external_id == entry["id"]
                )
            )
            etag = entry.get("cTag") or entry.get("eTag")
            if existing and existing.meta.get("etag") == etag and existing.available:
                continue
            suffix = __import__("pathlib").Path(entry["name"]).suffix.lower()
            meta = {"etag": etag, "drive_id": drive, "name": entry["name"]}
            if (
                suffix not in SUPPORTED_EXTENSIONS
                or entry.get("size", 0) > MAX_FILE_BYTES
            ):
                row, _ = upsert(
                    db,
                    source,
                    entry["id"],
                    "document",
                    entry["name"],
                    web_url=entry.get("webUrl", ""),
                    meta=meta,
                    initial=True,
                )
                row.processing, row.processing_error = (
                    "unsupported",
                    "Nicht unterstütztes Format oder größer als 25 MB.",
                )
                continue
            content = graph.download(drive, entry["id"])
            target = DATA_DIR / "originals" / f"{uid()}{suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            upsert(
                db,
                source,
                entry["id"],
                "document",
                entry["name"],
                web_url=entry.get("webUrl", ""),
                meta=meta,
                file_path=str(target),
                initial=True,
            )
        if full:
            reconcile(db, source, seen)
        cursor.update({"delta": delta, "folders": list(folders)})
    source.cursor, source.last_sync, source.status, source.error = (
        cursor,
        now(),
        "ok",
        None,
    )
    source.next_sync = now() + timedelta(
        minutes=2 if source.kind in {"mail", "chat", "channel"} else 5
    )
    audit(db, "source.synced", source_id=source.id)


def reconcile(db, source, seen, cutoff=None):
    query = select(Item).where(Item.source_id == source.id, Item.available.is_(True))
    if cutoff:
        query = query.where(Item.occurred_at >= cutoff)
    for item in db.scalars(query):
        if item.external_id not in seen:
            item.available = False
