import os
import sys
import json
import logging
import webbrowser
import importlib.util
from http.server import HTTPServer, SimpleHTTPRequestHandler

AIMAOS_ROOT = "/path/to/AIMAOS"
sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))

from core.document_engine import DocumentEngine
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

        elif self.path == "/api/reports":
            reports_dir = os.path.join(AIMAOS_ROOT, "Zoe-AI", "workspace", "diagnostics")
            report_text = ""
            if os.path.exists(reports_dir):
                for f in sorted(os.listdir(reports_dir), reverse=True):
                    if f.endswith(".md"):
                        with open(os.path.join(reports_dir, f), "r") as rfile:
                            report_text += f"=== {f} ===\n" + rfile.read() + "\n\n"
            if not report_text:
                report_text = "No system improvement diagnostic reports generated yet."

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"reports": report_text}).encode("utf-8"))
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
            agent_name = data.get("agent_name", "Echo")
            role = data.get("role", "Specialized Agent")
            
            tool_path = os.path.join(AIMAOS_ROOT, "Rae-AI", "tools", "clone_agent.py")
            spec = importlib.util.spec_from_file_location("rae_clone", tool_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            msg = mod.execute(agent_name, role)

            self._send_json({"status": "success", "message": msg})
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
