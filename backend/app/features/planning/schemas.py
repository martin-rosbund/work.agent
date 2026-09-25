from app.api.schemas import ItemView


class TaskView(ItemView):
    """Task metadata includes due date and source status."""


class CalendarView(ItemView):
    """Calendar metadata includes start/end with source timezone."""
