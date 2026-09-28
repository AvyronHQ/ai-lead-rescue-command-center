from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class AIService:
    """OpenAI-backed assistant with a deterministic demo fallback.

    The project remains fully usable without an API key. If OPENAI_API_KEY is
    present, the Responses API is used for summaries and follow-up drafts.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna"
        self.mode = "openai" if self.api_key else "demo"

    def _call_openai(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "input": prompt,
                "max_output_tokens": 350,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            raise RuntimeError(f"AI provider request failed: {exc}") from exc

        if isinstance(body.get("output_text"), str) and body["output_text"].strip():
            return body["output_text"].strip()
        for item in body.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
        raise RuntimeError("AI provider returned no text output.")

    def summarize_lead(self, lead: dict[str, Any]) -> str:
        if self.mode == "openai":
            prompt = f"""
You are a sales operations assistant. Summarize this inbound business lead in 2 short sentences.
State the need, urgency/budget signal, and the best next action. Do not invent facts.

Name: {lead.get('name')}
Company: {lead.get('company')}
Service: {lead.get('service')}
Budget: {lead.get('budget')}
Message: {lead.get('message')}
Status: {lead.get('status')}
""".strip()
            return self._call_openai(prompt)

        service = lead.get("service") or "business support"
        budget = lead.get("budget")
        budget_text = f" with an indicated budget around ${float(budget):,.0f}" if budget else ""
        message = (lead.get("message") or "").strip().rstrip(".")
        need = message if message else f"They are interested in {service}"
        action = "Clarify scope and timeline, then move the lead toward a quote."
        if lead.get("status") in {"QUOTE_SENT", "WAITING"}:
            action = "Follow up on the quote and ask whether any questions are blocking a decision."
        return f"{lead.get('name')} from {lead.get('company') or 'an inbound lead'} needs {service}{budget_text}. {need}. {action}"

    def followup_draft(self, lead: dict[str, Any]) -> str:
        if self.mode == "openai":
            prompt = f"""
Write a concise, warm follow-up email for a service-business lead after a quote was sent.
Use 70-110 words. No pressure tactics. Mention the requested service and quote amount only if provided.
Ask one clear question and offer to clarify scope. Do not invent discounts or deadlines.

Client name: {lead.get('name')}
Company: {lead.get('company')}
Service: {lead.get('service')}
Quote amount: {lead.get('quote_amount')}
Original message: {lead.get('message')}
""".strip()
            return self._call_openai(prompt)

        first_name = (lead.get("name") or "there").split()[0]
        service = lead.get("service") or "your project"
        quote = lead.get("quote_amount")
        quote_line = f" I wanted to check in on the ${float(quote):,.0f} quote I sent" if quote else " I wanted to follow up"
        return (
            f"Hi {first_name},\n\n"
            f"{quote_line} for {service}. I wanted to make sure you have everything you need to review it. "
            "If any part of the scope, timing, or deliverables is unclear, I’m happy to clarify it.\n\n"
            "Is there anything you’d like me to adjust or explain before you decide on the next step?\n\n"
            "Best,\nYour Team"
        )
