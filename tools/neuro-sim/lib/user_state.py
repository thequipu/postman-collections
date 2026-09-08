"""Per-user state machine for Neuro simulation."""

import random


class UserState:
    """Tracks everything a simulated user owns: space, namespaces, facts, pins."""

    def __init__(self, user_id: str, user_index: int, space_prefix: str = "neurosim",
                 existing_space: str = "", existing_namespace: str = ""):
        self.user_id = user_id
        self.user_index = user_index
        # Use existing space/namespace if provided, else generate new ones
        self.space = existing_space or f"{space_prefix}-{user_id}"
        self.ns = existing_namespace or f"{self.space}-self"
        self.using_existing = bool(existing_space)

        # Owned resources
        self.graph_namespaces: list[str] = []
        self.ingested_ids: list[str] = []
        self.fact_uris: list[str] = []
        self.pinned_uris: list[str] = []
        self.invalidated_uris: list[str] = []
        self.deleted_uris: list[str] = []
        self.threads: set[str] = set()

        # Data pool slice
        self.data_items: list[dict] = []
        self.message_cursor: int = 0

        # Lifecycle flags
        self.space_created: bool = False
        self.profile_set: bool = False

    def next_message(self) -> dict | None:
        """Get next content to ingest, cycling through assigned data."""
        if not self.data_items:
            return None
        item = self.data_items[self.message_cursor % len(self.data_items)]
        self.message_cursor += 1
        domain = item.get("domain", "general")
        thread = f"thread-{self.user_id}-{domain}"
        self.threads.add(thread)
        return {
            "content": item["content"],
            "thread_id": thread,
            "speaker": f"{self.user_id}@sim.quipu.test",
            "source": item.get("source", "unknown"),
        }

    def has_facts(self) -> bool:
        return len(self.fact_uris) > 0

    def random_fact(self) -> str | None:
        return random.choice(self.fact_uris) if self.fact_uris else None

    def can_attach_namespace(self) -> bool:
        return len(self.graph_namespaces) < 3

    def can_detach_namespace(self) -> bool:
        return len(self.graph_namespaces) > 0

    def summary(self) -> dict:
        return {
            "ingested": len(self.ingested_ids),
            "facts_seen": len(self.fact_uris),
            "pinned": len(self.pinned_uris),
            "invalidated": len(self.invalidated_uris),
            "deleted": len(self.deleted_uris),
            "namespaces": len(self.graph_namespaces),
            "threads": len(self.threads),
            "messages_sent": self.message_cursor,
        }
