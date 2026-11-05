"""Owner: Sunil. Uses getUpdates long-polling, so no public URL is needed.
Only ONE process may poll a given bot token at a time (otherwise Telegram returns 409 Conflict)."""


def send_message(chat_id: str, text: str) -> str:
    """Send a message and return the Telegram message_id as a str."""
    raise NotImplementedError


def get_replies(since_update_id: int) -> list[dict]:
    """Return [{update_id, chat_id, text, t}] for updates newer than since_update_id."""
    raise NotImplementedError
