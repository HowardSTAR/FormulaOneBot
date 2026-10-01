"""Legacy loader entry point backed by deletable, cancellable loading messages."""
from app.utils.activity_status import ActivityStatus


class Loader(ActivityStatus):
    def __init__(self, message, text="Загружаю данные…"):
        super().__init__(message, text, parse_mode="HTML")

    @property
    def msg(self):
        return self.status
