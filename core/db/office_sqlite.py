"""OfficeSQLite — Zero-dependency SQLite relational database manager for AIMAOS.

Manages transactional tables for:
- `cases`: Client files, case numbers, categories, status summary, paths.
- `tasks`: Office board active tasks, leases, priority queues.
- `templates`: Production template registry and variable mappings.

Includes auto-migration from legacy JSON sidecars (.client_index.json, office_board.json).
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(AIMAOS_ROOT, "comms/office_database.sqlite")
OLD_INDEX_PATH = os.path.join(AIMAOS_ROOT, "Alix-AI/workspace/output/.client_index.json")
OLD_BOARD_PATH = os.path.join(AIMAOS_ROOT, "comms/office_board.json")


class OfficeSQLite:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_tables()
        self._migrate_if_needed()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _init_tables(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Cases Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    client_slug TEXT PRIMARY KEY,
                    client_name TEXT NOT NULL,
                    matter_type TEXT,
                    category TEXT,
                    status TEXT DEFAULT 'open',
                    case_number TEXT,
                    opened_at TEXT,
                    updated_at TEXT,
                    path TEXT NOT NULL
                )
            """)

            # 2. Tasks Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    assigned_agent TEXT,
                    priority TEXT DEFAULT 'NORMAL',
                    priority_weight INTEGER DEFAULT 5,
                    status TEXT DEFAULT 'PENDING',
                    created_at TEXT,
                    updated_at TEXT,
                    lease_expires_at TEXT
                )
            """)

            # 3. Templates Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    template_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    category TEXT NOT NULL,
                    rel_path TEXT NOT NULL,
                    size_bytes INTEGER,
                    modified_at TEXT
                )
            """)

            # 4. Dashboard Jobs Table.  Model-backed work runs outside HTTP
            # request threads and reports honest progress through this table.
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
            conn.commit()

    def _migrate_if_needed(self):
        """Auto-migrates existing client index and office board JSON data into SQLite."""
        # Migrate Client Index
        if os.path.exists(OLD_INDEX_PATH):
            try:
                with open(OLD_INDEX_PATH, "r") as f:
                    data = json.load(f)
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    for slug, path in data.items():
                        cname = slug.replace("_", " ").title()
                        state_path = os.path.join(path, ".client_file_state.json")
                        matter_type = "Legal Matter"
                        category = ""
                        status = "open"
                        case_number = None
                        opened_at = datetime.now().isoformat()
                        updated_at = datetime.now().isoformat()

                        if os.path.exists(state_path):
                            try:
                                with open(state_path, "r") as sf:
                                    st = json.load(sf)
                                    cname = st.get("client_name", cname)
                                    matter_type = st.get("matter_type", matter_type)
                                    category = st.get("category", category)
                                    status = st.get("state", status)
                                    case_number = st.get("case_number", case_number)
                                    opened_at = st.get("opened", opened_at)
                                    updated_at = st.get("last_updated", updated_at)
                            except Exception:
                                pass

                        cursor.execute("""
                            INSERT OR REPLACE INTO cases 
                            (client_slug, client_name, matter_type, category, status, case_number, opened_at, updated_at, path)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (slug, cname, matter_type, category, status, case_number, opened_at, updated_at, path))
                    conn.commit()
            except Exception as e:
                logger.warning(f"Error migrating client index to SQLite: {e}")

        # Migrate Office Board Tasks
        if os.path.exists(OLD_BOARD_PATH):
            try:
                with open(OLD_BOARD_PATH, "r") as f:
                    board_data = json.load(f)
                # The JSON office board keeps live work in "active_tasks" and
                # finished work in "completed_tasks" ("tasks" never existed).
                tasks = (board_data.get("active_tasks", [])
                         + board_data.get("completed_tasks", []))
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    for t in tasks:
                        tid = t.get("task_id") or t.get("id")
                        if not tid:
                            continue
                        cursor.execute("""
                            INSERT OR REPLACE INTO tasks 
                            (task_id, title, description, assigned_agent, priority, priority_weight, status, created_at, updated_at, lease_expires_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            str(tid),
                            t.get("title", "Untitled Task"),
                            t.get("description", ""),
                            t.get("assigned_agent", "Unassigned"),
                            t.get("priority", "NORMAL"),
                            t.get("priority_weight", 5),
                            t.get("status", "PENDING"),
                            t.get("created_at", datetime.now().isoformat()),
                            t.get("updated_at", datetime.now().isoformat()),
                            t.get("lease_expires_at")
                        ))
                    conn.commit()
            except Exception as e:
                logger.warning(f"Error migrating office board to SQLite: {e}")

    # --- Cases Methods ---
    def upsert_case(self, client_slug, client_name, path, matter_type="Legal Matter", category="", status="open", case_number=None):
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO cases (client_slug, client_name, matter_type, category, status, case_number, opened_at, updated_at, path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_slug) DO UPDATE SET
                    client_name=excluded.client_name,
                    matter_type=COALESCE(excluded.matter_type, cases.matter_type),
                    category=COALESCE(excluded.category, cases.category),
                    status=COALESCE(excluded.status, cases.status),
                    case_number=COALESCE(excluded.case_number, cases.case_number),
                    updated_at=excluded.updated_at,
                    path=excluded.path
            """, (client_slug, client_name, matter_type, category, status, case_number, now, now, path))
            conn.commit()

    def get_case(self, client_slug):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cases WHERE client_slug = ?", (client_slug,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_all_cases(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cases ORDER BY client_name ASC")
            return [dict(r) for r in cursor.fetchall()]

    # --- Tasks Methods ---
    def upsert_task(self, task_id, title, description="", assigned_agent="Unassigned", priority="NORMAL", priority_weight=5, status="PENDING", lease_expires_at=None):
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tasks (task_id, title, description, assigned_agent, priority, priority_weight, status, created_at, updated_at, lease_expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    title=excluded.title,
                    description=excluded.description,
                    assigned_agent=excluded.assigned_agent,
                    priority=excluded.priority,
                    priority_weight=excluded.priority_weight,
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    lease_expires_at=excluded.lease_expires_at
            """, (task_id, title, description, assigned_agent, priority, priority_weight, status, now, now, lease_expires_at))
            conn.commit()

    def list_tasks(self, status=None, assigned_agent=None):
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if assigned_agent:
            query += " AND assigned_agent = ?"
            params.append(assigned_agent)
        query += " ORDER BY priority_weight DESC, created_at ASC"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    def update_task_status(self, task_id, status, result=None):
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, description = COALESCE(?, description), updated_at = ? WHERE task_id = ?",
                (status, result, now, task_id),
            )
            conn.commit()

    # --- Dashboard Jobs Methods ---
    def create_job(self, job_id, kind, title):
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, kind, title, status, created_at) VALUES (?, ?, ?, 'queued', ?)",
                (job_id, kind, title, datetime.now().isoformat()),
            )
            conn.commit()

    def update_job(self, job_id, *, status=None, result=None, error=None,
                   started_at=None, completed_at=None):
        updates = []
        values = []
        if status is not None:
            updates.append("status = ?")
            values.append(status)
        if result is not None:
            updates.append("result_json = ?")
            values.append(json.dumps(result, default=str))
        if error is not None:
            updates.append("error = ?")
            values.append(str(error)[:4000])
        if started_at is not None:
            updates.append("started_at = ?")
            values.append(started_at)
        if completed_at is not None:
            updates.append("completed_at = ?")
            values.append(completed_at)
        if not updates:
            return
        values.append(job_id)
        with self.get_connection() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(updates)} WHERE job_id = ?", values)
            conn.commit()

    @staticmethod
    def _decode_job(row):
        if not row:
            return None
        job = dict(row)
        raw_result = job.pop("result_json", None)
        if raw_result:
            try:
                job["result"] = json.loads(raw_result)
            except json.JSONDecodeError:
                job["result"] = raw_result
        else:
            job["result"] = None
        return job

    def get_job(self, job_id):
        with self.get_connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._decode_job(row)

    def list_jobs(self, limit=50):
        limit = max(1, min(int(limit), 200))
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._decode_job(row) for row in rows]

    def interrupt_unfinished_jobs(self):
        """Work closures cannot survive a process restart; report that fact."""
        with self.get_connection() as conn:
            conn.execute(
                """UPDATE jobs
                   SET status = 'interrupted',
                       error = COALESCE(error, 'Application restarted before this job completed.'),
                       completed_at = ?
                   WHERE status IN ('queued', 'running')""",
                (datetime.now().isoformat(),),
            )
            conn.commit()


if __name__ == "__main__":
    db = OfficeSQLite()
    print(f"OfficeSQLite initialized cleanly at {DB_PATH}.")
    print(f"Total Cases in SQLite: {len(db.list_all_cases())}")
    print(f"Total Tasks in SQLite: {len(db.list_tasks())}")
