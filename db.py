from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

STATUSES = ["NEW", "CONTACTED", "QUALIFIED", "QUOTE_SENT", "WAITING", "WON", "LOST"]
PRIORITIES = ["LOW", "MEDIUM", "HIGH"]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def iso_after(days: int = 0, hours: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).replace(microsecond=0).isoformat()


class LeadRepository:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    phone TEXT DEFAULT '',
                    company TEXT DEFAULT '',
                    source TEXT DEFAULT 'Website',
                    service TEXT DEFAULT '',
                    message TEXT DEFAULT '',
                    budget REAL,
                    status TEXT NOT NULL DEFAULT 'NEW',
                    priority TEXT NOT NULL DEFAULT 'MEDIUM',
                    ai_summary TEXT DEFAULT '',
                    quote_amount REAL,
                    quote_sent_at TEXT,
                    next_followup_at TEXT,
                    last_contact_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    note TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    generated_draft TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
                CREATE INDEX IF NOT EXISTS idx_leads_followup ON leads(next_followup_at);
                CREATE INDEX IF NOT EXISTS idx_reminders_status_due ON reminders(status, due_at);
                """
            )

    def count_leads(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]

    def create_lead(self, data: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        status = str(data.get("status", "NEW")).upper()
        priority = str(data.get("priority", "MEDIUM")).upper()
        if status not in STATUSES:
            status = "NEW"
        if priority not in PRIORITIES:
            priority = "MEDIUM"

        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO leads
                (name, email, phone, company, source, service, message, budget, status, priority,
                 ai_summary, quote_amount, quote_sent_at, next_followup_at, last_contact_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["name"].strip(),
                    data["email"].strip(),
                    str(data.get("phone", "")).strip(),
                    str(data.get("company", "")).strip(),
                    str(data.get("source", "Website")).strip() or "Website",
                    str(data.get("service", "")).strip(),
                    str(data.get("message", "")).strip(),
                    data.get("budget"),
                    status,
                    priority,
                    str(data.get("ai_summary", "")).strip(),
                    data.get("quote_amount"),
                    data.get("quote_sent_at"),
                    data.get("next_followup_at"),
                    data.get("last_contact_at"),
                    data.get("created_at", now),
                    now,
                ),
            )
            lead_id = cur.lastrowid
            conn.execute(
                "INSERT INTO activities (lead_id, type, note, created_at) VALUES (?, ?, ?, ?)",
                (lead_id, "LEAD_CREATED", f"Lead captured from {data.get('source', 'Website')}", now),
            )
        return self.get_lead(int(lead_id))

    def get_lead(self, lead_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if not row:
                return None
            lead = dict(row)
            lead["activities"] = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM activities WHERE lead_id = ? ORDER BY created_at DESC, id DESC LIMIT 30",
                    (lead_id,),
                ).fetchall()
            ]
            return lead

    def list_leads(self, status: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM leads WHERE 1=1"
        params: list[Any] = []
        if status and status.upper() in STATUSES:
            sql += " AND status = ?"
            params.append(status.upper())
        if search:
            sql += " AND (name LIKE ? OR email LIKE ? OR company LIKE ? OR service LIKE ?)"
            needle = f"%{search.strip()}%"
            params.extend([needle, needle, needle, needle])
        sql += " ORDER BY CASE priority WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END, created_at DESC"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def update_lead(self, lead_id: int, changes: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {
            "name", "email", "phone", "company", "source", "service", "message", "budget",
            "status", "priority", "ai_summary", "quote_amount", "quote_sent_at", "next_followup_at",
            "last_contact_at"
        }
        clean = {k: v for k, v in changes.items() if k in allowed}
        if "status" in clean:
            clean["status"] = str(clean["status"]).upper()
            if clean["status"] not in STATUSES:
                del clean["status"]
        if "priority" in clean:
            clean["priority"] = str(clean["priority"]).upper()
            if clean["priority"] not in PRIORITIES:
                del clean["priority"]
        if not clean:
            return self.get_lead(lead_id)
        clean["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = ?" for key in clean)
        values = list(clean.values()) + [lead_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE leads SET {assignments} WHERE id = ?", values)
        return self.get_lead(lead_id)

    def set_quote(self, lead_id: int, amount: float, followup_days: int = 2) -> dict[str, Any] | None:
        now = utc_now()
        followup_at = iso_after(days=max(1, followup_days))
        updated = self.update_lead(
            lead_id,
            {
                "status": "QUOTE_SENT",
                "quote_amount": amount,
                "quote_sent_at": now,
                "last_contact_at": now,
                "next_followup_at": followup_at,
            },
        )
        if updated:
            self.add_activity(lead_id, "QUOTE_SENT", f"Quote sent: ${amount:,.2f}. Follow-up scheduled.")
        return updated

    def add_activity(self, lead_id: int, activity_type: str, note: str) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO activities (lead_id, type, note, created_at) VALUES (?, ?, ?, ?)",
                (lead_id, activity_type, note.strip(), now),
            )
            row = conn.execute("SELECT * FROM activities WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def recent_activities(self, limit: int = 12) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT a.*, l.name AS lead_name, l.company AS lead_company
                FROM activities a
                JOIN leads l ON l.id = a.lead_id
                ORDER BY a.created_at DESC, a.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def has_open_reminder(self, lead_id: int) -> bool:
        with self._connect() as conn:
            return bool(
                conn.execute(
                    "SELECT 1 FROM reminders WHERE lead_id = ? AND status = 'OPEN' LIMIT 1",
                    (lead_id,),
                ).fetchone()
            )

    def create_reminder(self, lead_id: int, title: str, due_at: str, generated_draft: str = "") -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO reminders (lead_id, title, due_at, status, generated_draft, created_at)
                VALUES (?, ?, ?, 'OPEN', ?, ?)
                """,
                (lead_id, title.strip(), due_at, generated_draft, now),
            )
            row = conn.execute("SELECT * FROM reminders WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def list_reminders(self, status: str | None = "OPEN") -> list[dict[str, Any]]:
        sql = """
            SELECT r.*, l.name AS lead_name, l.email AS lead_email, l.company AS lead_company,
                   l.service AS lead_service, l.quote_amount AS quote_amount
            FROM reminders r JOIN leads l ON l.id = r.lead_id
        """
        params: list[Any] = []
        if status:
            sql += " WHERE r.status = ?"
            params.append(status.upper())
        sql += " ORDER BY r.due_at ASC, r.id DESC"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def complete_reminder(self, reminder_id: int) -> dict[str, Any] | None:
        now = utc_now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE reminders SET status = 'DONE', completed_at = ? WHERE id = ?",
                (now, reminder_id),
            )
            row = conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,)).fetchone()
        return dict(row) if row else None

    def overdue_followup_candidates(self) -> list[dict[str, Any]]:
        now = utc_now()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM leads
                WHERE status IN ('QUOTE_SENT', 'WAITING')
                  AND next_followup_at IS NOT NULL
                  AND next_followup_at <= ?
                ORDER BY next_followup_at ASC
                """,
                (now,),
            ).fetchall()
            return [dict(r) for r in rows]

    def dashboard(self) -> dict[str, Any]:
        now = utc_now()
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            active_quotes = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE status IN ('QUOTE_SENT', 'WAITING')"
            ).fetchone()[0]
            overdue = conn.execute(
                "SELECT COUNT(*) FROM reminders WHERE status = 'OPEN' AND due_at <= ?", (now,)
            ).fetchone()[0]
            won_value = conn.execute(
                "SELECT COALESCE(SUM(quote_amount), 0) FROM leads WHERE status = 'WON'"
            ).fetchone()[0]
            pipeline_rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM leads GROUP BY status"
            ).fetchall()
            source_rows = conn.execute(
                "SELECT source, COUNT(*) AS count FROM leads GROUP BY source ORDER BY count DESC"
            ).fetchall()
            pipeline = {status: 0 for status in STATUSES}
            for r in pipeline_rows:
                pipeline[r["status"]] = r["count"]
            return {
                "total_leads": total,
                "active_quotes": active_quotes,
                "overdue_followups": overdue,
                "won_value": float(won_value or 0),
                "pipeline": pipeline,
                "sources": [dict(r) for r in source_rows],
                "recent_activities": self.recent_activities(10),
            }

    def reset_demo(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM reminders")
            conn.execute("DELETE FROM activities")
            conn.execute("DELETE FROM leads")
        self.seed_demo()

    def seed_demo(self) -> None:
        if self.count_leads() > 0:
            return

        demo = [
            {
                "name": "Maya Brooks", "email": "maya@northstar.example", "company": "Northstar Studio",
                "source": "Website", "service": "Website redesign", "message": "Need a modern site and a quote this week.",
                "budget": 1800, "status": "NEW", "priority": "HIGH", "created_at": iso_after(hours=-3)
            },
            {
                "name": "Ethan Cole", "email": "ethan@harborfix.example", "company": "HarborFix Repairs",
                "source": "Google Ads", "service": "Lead automation", "message": "We lose leads after sending estimates. Need follow-up automation.",
                "budget": 1200, "status": "QUALIFIED", "priority": "HIGH", "created_at": iso_after(days=-1)
            },
            {
                "name": "Sofia Patel", "email": "sofia@lumenlegal.example", "company": "Lumen Legal",
                "source": "Referral", "service": "Client intake system", "message": "Looking for a safer way to organize inquiries and reminders.",
                "budget": 2500, "status": "CONTACTED", "priority": "MEDIUM", "created_at": iso_after(days=-2),
                "last_contact_at": iso_after(days=-1)
            },
            {
                "name": "Noah Bennett", "email": "noah@evergreen.example", "company": "Evergreen Landscaping",
                "source": "Website", "service": "Quote workflow", "message": "Need quote tracking and follow-up so estimates do not go cold.",
                "budget": 950, "status": "QUOTE_SENT", "priority": "HIGH", "quote_amount": 900,
                "quote_sent_at": iso_after(days=-4), "next_followup_at": iso_after(days=-1), "created_at": iso_after(days=-5)
            },
            {
                "name": "Ava Morgan", "email": "ava@brightdesk.example", "company": "BrightDesk Consulting",
                "source": "LinkedIn", "service": "AI email assistant", "message": "Want AI-assisted drafting for routine sales follow-ups.",
                "budget": 1400, "status": "WAITING", "priority": "MEDIUM", "quote_amount": 1250,
                "quote_sent_at": iso_after(days=-5), "next_followup_at": iso_after(hours=-5), "created_at": iso_after(days=-7)
            },
            {
                "name": "Liam Foster", "email": "liam@forgeworks.example", "company": "ForgeWorks",
                "source": "Upwork", "service": "CRM dashboard", "message": "Need a simple lead pipeline for our service team.",
                "budget": 2000, "status": "WON", "priority": "MEDIUM", "quote_amount": 1750,
                "created_at": iso_after(days=-12), "last_contact_at": iso_after(days=-1)
            },
            {
                "name": "Chloe Reed", "email": "chloe@sunline.example", "company": "Sunline Cleaning",
                "source": "Website", "service": "Booking automation", "message": "Need web leads organized before staff call them.",
                "budget": 700, "status": "NEW", "priority": "LOW", "created_at": iso_after(hours=-8)
            },
            {
                "name": "Oliver Grant", "email": "oliver@blueoak.example", "company": "BlueOak Renovations",
                "source": "Facebook", "service": "Quote follow-up", "message": "Customers ask for quotes but often disappear. Need reminders.",
                "budget": 1100, "status": "QUOTE_SENT", "priority": "HIGH", "quote_amount": 980,
                "quote_sent_at": iso_after(days=-2), "next_followup_at": iso_after(days=1), "created_at": iso_after(days=-3)
            },
            {
                "name": "Isla Turner", "email": "isla@mintwell.example", "company": "Mintwell Wellness",
                "source": "Referral", "service": "Intake dashboard", "message": "Need non-medical inquiry tracking and team follow-up.",
                "budget": 1300, "status": "LOST", "priority": "MEDIUM", "quote_amount": 1200,
                "created_at": iso_after(days=-18)
            },
            {
                "name": "Lucas Kim", "email": "lucas@pixelbay.example", "company": "PixelBay Media",
                "source": "LinkedIn", "service": "Automation audit", "message": "Looking to reduce manual lead routing and response delays.",
                "budget": 1600, "status": "QUALIFIED", "priority": "MEDIUM", "created_at": iso_after(days=-1, hours=-4)
            },
        ]
        for item in demo:
            lead = self.create_lead(item)
            if lead["status"] == "WON":
                self.add_activity(lead["id"], "DEAL_WON", f"Deal won at ${lead['quote_amount']:,.2f}.")
            elif lead["status"] == "LOST":
                self.add_activity(lead["id"], "DEAL_LOST", "Lead closed as lost after final follow-up.")
