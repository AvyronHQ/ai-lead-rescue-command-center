from __future__ import annotations

import json
import mimetypes
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ai_service import AIService
from automation import AutomationEngine
from db import LeadRepository, utc_now

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv(BASE_DIR / ".env")
DB_PATH = Path(os.getenv("DATABASE_PATH", DATA_DIR / "lead_rescue.db"))
repo = LeadRepository(DB_PATH)
repo.seed_demo()
ai = AIService()
automation = AutomationEngine(repo, ai)


class AppHandler(BaseHTTPRequestHandler):
    server_version = "LeadRescue/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")

    def _json(self, payload, status=HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message: str, status=HTTPStatus.BAD_REQUEST) -> None:
        self._json({"error": message}, status)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > 1_000_000:
            raise ValueError("Request body is too large.")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON body.") from exc

    def _serve_file(self, relative: str) -> None:
        target = (FRONTEND_DIR / relative).resolve()
        try:
            target.relative_to(FRONTEND_DIR.resolve())
        except ValueError:
            self._error("Not found", HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            self._error("Not found", HTTPStatus.NOT_FOUND)
            return
        content = target.read_bytes()
        mime, _ = mimetypes.guess_type(target.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", (mime or "application/octet-stream") + ("; charset=utf-8" if (mime or "").startswith("text/") else ""))
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    @staticmethod
    def _lead_id(path: str, suffix: str = "") -> int | None:
        pattern = rf"^/api/leads/(\d+){re.escape(suffix)}$"
        match = re.match(pattern, path)
        return int(match.group(1)) if match else None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            return self._serve_file("index.html")
        if path == "/intake":
            return self._serve_file("intake.html")
        if path.startswith("/assets/"):
            return self._serve_file(path.removeprefix("/assets/"))
        if path in {"/styles.css", "/app.js", "/intake.js"}:
            return self._serve_file(path.lstrip("/"))

        if path == "/api/health":
            return self._json({"status": "ok", "ai_mode": ai.mode, "model": ai.model if ai.mode == "openai" else "demo-fallback", "time": utc_now()})
        if path == "/api/dashboard":
            return self._json(repo.dashboard())
        if path == "/api/leads":
            status = query.get("status", [None])[0]
            search = query.get("search", [None])[0]
            return self._json({"leads": repo.list_leads(status=status, search=search)})
        lead_id = self._lead_id(path)
        if lead_id is not None:
            lead = repo.get_lead(lead_id)
            return self._json(lead) if lead else self._error("Lead not found", HTTPStatus.NOT_FOUND)
        if path == "/api/reminders":
            status = query.get("status", ["OPEN"])[0]
            if status.lower() == "all":
                status = None
            return self._json({"reminders": repo.list_reminders(status=status)})
        if path == "/api/activities":
            try:
                limit = min(max(int(query.get("limit", [12])[0]), 1), 50)
            except ValueError:
                limit = 12
            return self._json({"activities": repo.recent_activities(limit)})

        self._error("Not found", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            data = self._read_json()
        except ValueError as exc:
            return self._error(str(exc))

        if path == "/api/leads":
            name = str(data.get("name", "")).strip()
            email = str(data.get("email", "")).strip()
            if len(name) < 2:
                return self._error("Name is required.")
            if "@" not in email or len(email) < 5:
                return self._error("A valid email is required.")
            if data.get("budget") in ("", None):
                data["budget"] = None
            else:
                try:
                    data["budget"] = float(data["budget"])
                except (TypeError, ValueError):
                    return self._error("Budget must be a number.")
            return self._json(repo.create_lead(data), HTTPStatus.CREATED)

        for suffix, action in [
            ("/ai-summary", "summary"),
            ("/followup-draft", "draft"),
            ("/quote", "quote"),
            ("/activity", "activity"),
            ("/status", "status"),
        ]:
            lead_id = self._lead_id(path, suffix)
            if lead_id is None:
                continue
            lead = repo.get_lead(lead_id)
            if not lead:
                return self._error("Lead not found", HTTPStatus.NOT_FOUND)

            if action == "summary":
                try:
                    summary = ai.summarize_lead(lead)
                except Exception as exc:
                    return self._error(str(exc), HTTPStatus.BAD_GATEWAY)
                repo.update_lead(lead_id, {"ai_summary": summary})
                repo.add_activity(lead_id, "AI_SUMMARY", "AI summary generated for this lead.")
                return self._json({"summary": summary, "ai_mode": ai.mode})

            if action == "draft":
                try:
                    draft = ai.followup_draft(lead)
                except Exception as exc:
                    return self._error(str(exc), HTTPStatus.BAD_GATEWAY)
                repo.add_activity(lead_id, "AI_DRAFT", "AI follow-up draft prepared for review.")
                return self._json({"draft": draft, "ai_mode": ai.mode})

            if action == "quote":
                try:
                    amount = float(data.get("amount"))
                    followup_days = int(data.get("followup_days", 2))
                except (TypeError, ValueError):
                    return self._error("Quote amount and follow-up days must be valid numbers.")
                if amount <= 0:
                    return self._error("Quote amount must be greater than zero.")
                return self._json(repo.set_quote(lead_id, amount, followup_days))

            if action == "activity":
                note = str(data.get("note", "")).strip()
                if not note:
                    return self._error("Activity note is required.")
                activity = repo.add_activity(lead_id, str(data.get("type", "NOTE")).upper(), note)
                repo.update_lead(lead_id, {"last_contact_at": utc_now()})
                return self._json(activity, HTTPStatus.CREATED)

            if action == "status":
                status = str(data.get("status", "")).upper()
                updated = repo.update_lead(lead_id, {"status": status})
                if not updated:
                    return self._error("Lead not found", HTTPStatus.NOT_FOUND)
                if updated["status"] != status:
                    return self._error("Invalid status.")
                repo.add_activity(lead_id, "STATUS_CHANGED", f"Status changed to {status.replace('_', ' ').title()}.")
                return self._json(repo.get_lead(lead_id))

        reminder_match = re.match(r"^/api/reminders/(\d+)/complete$", path)
        if reminder_match:
            reminder_id = int(reminder_match.group(1))
            reminder = repo.complete_reminder(reminder_id)
            if not reminder:
                return self._error("Reminder not found", HTTPStatus.NOT_FOUND)
            repo.update_lead(reminder["lead_id"], {"last_contact_at": utc_now(), "next_followup_at": None})
            repo.add_activity(reminder["lead_id"], "FOLLOWUP_DONE", "Follow-up reminder completed.")
            return self._json(reminder)

        if path == "/api/automation/run":
            return self._json(automation.run_once())
        if path == "/api/demo/reset":
            repo.reset_demo()
            result = automation.run_once()
            return self._json({"message": "Demo data reset.", "automation": result})

        self._error("Not found", HTTPStatus.NOT_FOUND)

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        lead_id = self._lead_id(parsed.path)
        if lead_id is None:
            return self._error("Not found", HTTPStatus.NOT_FOUND)
        try:
            data = self._read_json()
        except ValueError as exc:
            return self._error(str(exc))
        updated = repo.update_lead(lead_id, data)
        return self._json(updated) if updated else self._error("Lead not found", HTTPStatus.NOT_FOUND)


def main() -> None:
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    automation.run_once()
    automation.start(interval_seconds=int(os.getenv("AUTOMATION_INTERVAL_SECONDS", "60")))
    server = ThreadingHTTPServer((host, port), AppHandler)
    print("\nLead Rescue & Quote Follow-Up Command Center")
    print(f"Dashboard: http://{host}:{port}")
    print(f"Public intake form: http://{host}:{port}/intake")
    print(f"AI mode: {ai.mode}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        automation.stop()
        server.server_close()


if __name__ == "__main__":
    main()
