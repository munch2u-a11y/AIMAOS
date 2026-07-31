import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import json
import logging
import webbrowser
import importlib.util
from http.server import HTTPServer, SimpleHTTPRequestHandler

sys.path.insert(0, AIMAOS_ROOT)
sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))

from business.document_engine import DocumentEngine
from core.comms.office_board import OfficeBoard

def load_agent(agent_folder, agent_class):
    file_path = os.path.join(AIMAOS_ROOT, agent_folder, "core", "agent.py")
    spec = importlib.util.spec_from_file_location(f"{agent_folder}_mod", file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, agent_class)()

class AIMAOSUIHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        static_dir = os.path.join(AIMAOS_ROOT, "ui")
        super().__init__(*args, directory=static_dir, **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.path = "/aimaos_ui.html"
            return super().do_GET()
        elif self.path == "/api/status":
            board = OfficeBoard()
            active = board.board.get("active_tasks", [])
            completed = board.board.get("completed_tasks", [])
            statuses = board.board.get("agent_statuses", {})
            stream = board.board.get("activity_stream", [])[-5:]

            payload = {
                "active_tasks": active,
                "completed_task_count": len(completed),
                "agent_statuses": statuses,
                "recent_activity": stream
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        elif self.path == "/api/cases":
            from core.db.office_sqlite import OfficeSQLite
            db = OfficeSQLite()
            cases = db.list_all_cases()
            self._send_json({"status": "success", "cases": cases})

        elif self.path.startswith("/api/case_file"):
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            slug = query.get("slug", [""])[0]

            from core.db.office_sqlite import OfficeSQLite
            db = OfficeSQLite()
            cinfo = db.get_case(slug) if slug else None
            
            if not cinfo:
                # Fallback search by slug directory in output
                out_base = os.path.join(AIMAOS_ROOT, "Alix-AI", "workspace", "output")
                target_dir = os.path.join(out_base, slug) if slug else ""
            else:
                target_dir = cinfo.get("path", "")

            content = "No case summary found."
            file_list = []
            if target_dir and os.path.exists(target_dir):
                client_md = os.path.join(target_dir, "CLIENT_FILE.md")
                if os.path.exists(client_md):
                    with open(client_md, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                for root, dirs, files in os.walk(target_dir):
                    for fname in files:
                        if fname.startswith("."):
                            continue
                        fpath = os.path.join(root, fname)
                        rel = os.path.relpath(fpath, target_dir)
                        file_list.append({"name": fname, "rel_path": rel, "abs_path": fpath, "size": os.path.getsize(fpath)})

            self._send_json({"status": "success", "slug": slug, "summary_md": content, "files": file_list})
        else:
            super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        data = json.loads(body) if body else {}

        if self.path == "/api/chat":
            user_msg = data.get("message", "")
            finn = load_agent("Finn-AI", "FinnAgent")
            resp = finn.process_user_message(user_msg)
            self._send_json({"status": "success", "response": resp})

        elif self.path == "/api/open_file":
            filepath = data.get("path")
            if filepath and os.path.exists(filepath):
                import subprocess
                try:
                    subprocess.Popen(["xdg-open", filepath])
                    msg = f"Opened file natively: {os.path.basename(filepath)}"
                except Exception as ex:
                    msg = f"Could not launch native app: {ex}"
            else:
                msg = "File does not exist on local disk."
            self._send_json({"status": "success", "message": msg})

        elif self.path == "/api/upload":
            client_name = data.get("client_name", "New Client Ingest").strip()
            slug = client_name.lower().replace(" ", "_")
            file_name = data.get("file_name", "intake_note.txt")
            file_content = data.get("content", "")

            out_dir = os.path.join(AIMAOS_ROOT, "Alix-AI", "workspace", "output", slug)
            os.makedirs(out_dir, exist_ok=True)
            saved_file = os.path.join(out_dir, file_name)
            with open(saved_file, "w", encoding="utf-8") as f:
                f.write(file_content)

            # Register in SQLite and trigger CaseAgent
            from core.db.office_sqlite import OfficeSQLite
            from core.case_agent import CaseAgent
            db = OfficeSQLite()
            db.upsert_case(slug, client_name, out_dir, matter_type="Document Ingest", category="general")

            ca = CaseAgent(out_dir, client_name, category="general")
            ca.process_client_file(saved_file)

            board = OfficeBoard()
            board.post_task(f"Ingest File Review for {client_name}", "User", "Kai", "HIGH")

            self._send_json({"status": "success", "message": f"Successfully ingested file and initialized dedicated CaseManager for '{client_name}'.", "slug": slug})

        elif self.path == "/api/quick_action":
            action = data.get("action", "")
            board = OfficeBoard()

            if action == "audit_all":
                board.post_task("Comprehensive Office & Case File Security Audit", "User", "Finn", "HIGH")
                msg = "Posted Security Audit task to Finn."
            elif action == "synthesize_skills":
                board.post_task("Background Reflexive Skill Formation Cycle", "User", "Zoe", "NORMAL")
                msg = "Posted Skill Formation reflection task to Zoe."
            elif action == "scan_drives":
                board.post_task("External Drive & Workspace Archival Scan", "User", "Kai", "NORMAL")
                msg = "Posted Archival Scan task to Kai."
            else:
                board.post_task(f"Quick Action Request: {action}", "User", "Marley", "HIGH")
                msg = f"Posted Quick Action '{action}' to Marley."

            self._send_json({"status": "success", "message": msg})

        elif self.path == "/api/generate_doc":
            template_id = data.get("template", "form_12_982_a")
            client_name = data.get("client_name", "Valued Client")
            county = data.get("county", "Leon")
            new_name = data.get("new_name", "")

            template_path = os.path.join(AIMAOS_ROOT, "Alix-AI", "templates", template_id, "template.docx")
            out_dir = os.path.join(AIMAOS_ROOT, "Alix-AI", "workspace", "output", client_name.lower().replace(" ", "_"))
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, f"{template_id}_filled.docx")

            engine = DocumentEngine(template_path)
            ctx = {
                "client_name": client_name,
                "county": county,
                "new_name": new_name,
                "circuit_number": "2nd",
                "case_number": "2026-DR-9999"
            }
            engine.generate(ctx, out_path)

            board = OfficeBoard()
            board.post_task(f"Document Studio Request ({template_id})", "User", "Alix", "HIGH")

            self._send_json({"status": "success", "message": f"Generated court form at {out_path}"})

        elif self.path == "/api/clone_agent":
            agent_name = data.get("agent_name")
            role = data.get("role", "Specialized Agent")
            if not agent_name:
                self._send_json({"status": "error", "message": "agent_name is required to clone a new specialist."})
                return
            
            tool_path = os.path.join(AIMAOS_ROOT, "Rae-AI", "tools", "clone_agent.py")
            spec = importlib.util.spec_from_file_location("rae_clone", tool_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            msg = mod.execute(agent_name, role)

            self._send_json({"status": "success", "message": msg})

        elif self.path == "/api/voice_scribe":
            client_name = data.get("client_name")
            audio_path = data.get("audio_path")
            note_text = data.get("text", "")

            if audio_path and os.path.exists(audio_path):
                tool_path = os.path.join(AIMAOS_ROOT, "Finn-AI", "tools", "transcribe_audio_note.py")
                spec = importlib.util.spec_from_file_location("finn_scribe", tool_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                res_msg = mod.execute(audio_path, client_name=client_name)
            else:
                # Direct voice text scribe note
                from core.db.office_sqlite import OfficeSQLite
                from core.case_agent import CaseAgent
                db = OfficeSQLite()
                all_cases = db.list_all_cases()
                target_case = None
                if client_name:
                    for c in all_cases:
                        if client_name.lower() in c.get("client_name", "").lower() or client_name.lower() in c.get("client_slug", "").lower():
                            target_case = c
                            break
                if target_case:
                    case_dir = target_case.get("path")
                    c_name = target_case.get("client_name")
                    c_cat = target_case.get("category", "general")
                    if case_dir and os.path.exists(case_dir):
                        ca = CaseAgent(case_dir, c_name, category=c_cat)
                        ca.record_experience(f"Voice Scribe Note: {note_text}", category="memory", confidence=0.9)
                        res_msg = f"🎙️ Voice Scribe Note attached to [{c_name}]'s case record."
                    else:
                        res_msg = f"Logged voice note: {note_text}"
                else:
                    res_msg = f"Logged general office voice note: {note_text}"

            self._send_json({"status": "success", "message": res_msg})
        else:
            self.send_error(404, "Not Found")

    def _send_json(self, payload):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

def launch_aimaos_ui(port=8080, open_browser=True):
    server_address = ("", port)
    httpd = HTTPServer(server_address, AIMAOSUIHandler)
    url = f"http://localhost:{port}"

    print("====================================================================")
    print("AIMAOS ALL-IN-ONE SELF-CONTAINED OPERATING SYSTEM UI")
    print(f"Server Running at: {url}")
    print("Roster: Alix, Kai, Marley, Quinn, Zoe, Finn, Rae")
    print("====================================================================\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    httpd.serve_forever()

if __name__ == "__main__":
    launch_aimaos_ui(8080, open_browser=True)
