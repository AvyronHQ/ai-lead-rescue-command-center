from __future__ import annotations

import threading
import time
from typing import Any

from ai_service import AIService
from db import LeadRepository, utc_now


class AutomationEngine:
    def __init__(self, repo: LeadRepository, ai: AIService):
        self.repo = repo
        self.ai = ai
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> dict[str, Any]:
        created: list[dict[str, Any]] = []
        skipped = 0
        for lead in self.repo.overdue_followup_candidates():
            if self.repo.has_open_reminder(lead["id"]):
                skipped += 1
                continue
            try:
                draft = self.ai.followup_draft(lead)
            except Exception:
                draft = AIService().followup_draft(lead) if self.ai.mode == "openai" else self.ai.followup_draft(lead)
            reminder = self.repo.create_reminder(
                lead_id=lead["id"],
                title=f"Follow up with {lead['name']}",
                due_at=lead.get("next_followup_at") or utc_now(),
                generated_draft=draft,
            )
            self.repo.update_lead(lead["id"], {"status": "WAITING"})
            self.repo.add_activity(
                lead["id"],
                "FOLLOWUP_CREATED",
                "Automation detected an overdue quote and prepared a follow-up draft.",
            )
            created.append(reminder)
        return {"created": len(created), "skipped_existing": skipped, "reminders": created}

    def start(self, interval_seconds: int = 60) -> None:
        if self._thread and self._thread.is_alive():
            return

        def loop() -> None:
            while not self._stop_event.is_set():
                try:
                    self.run_once()
                except Exception as exc:
                    print(f"[automation] {exc}")
                self._stop_event.wait(interval_seconds)

        self._thread = threading.Thread(target=loop, daemon=True, name="lead-followup-automation")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
