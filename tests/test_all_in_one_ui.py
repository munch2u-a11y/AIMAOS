import os
import sys
import time
import json
import threading
import urllib.request

sys.path.insert(0, "/path/to/AIMAOS")
from aimaos_ui import AIMAOSUIHandler
from http.server import HTTPServer

PORT = 8089

def run_server():
    server_address = ("", PORT)
    httpd = HTTPServer(server_address, AIMAOSUIHandler)
    httpd.serve_forever()

def run_all_in_one_ui_test():
    print("====================================================================")
    print("AIMAOS ALL-IN-ONE SELF-CONTAINED UI INTEGRATION TEST SUITE")
    print(f"Testing Server on Port {PORT}")
    print("====================================================================\n")

    # Start UI server in background thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1)

    base_url = f"http://localhost:{PORT}"

    # 1. Test GET /api/status
    print("--- 1. TESTING GET /api/status ---")
    req = urllib.request.Request(f"{base_url}/api/status")
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        data = json.loads(response.read().decode())
        print("  • Agent Statuses:", list(data.get("agent_statuses", {}).keys()))
        print("  • Recent Activity Count:", len(data.get("recent_activity", [])))

    # 2. Test POST /api/chat (Finn Security & Chatbot)
    print("\n--- 2. TESTING POST /api/chat (Finn Direct Messenger) ---")
    payload = json.dumps({"message": "What is the current status of the office?"}).encode('utf-8')
    req = urllib.request.Request(f"{base_url}/api/chat", data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        data = json.loads(response.read().decode())
        print("  • Finn Response:\n", data.get("response"))

    # 3. Test POST /api/generate_doc (Alix Document Studio)
    print("\n--- 3. TESTING POST /api/generate_doc (Alix Document Studio) ---")
    doc_payload = json.dumps({
        "template": "form_12_982_a",
        "client_name": "Test Client",
        "county": "Leon",
        "new_name": "Test Sterling"
    }).encode('utf-8')
    req = urllib.request.Request(f"{base_url}/api/generate_doc", data=doc_payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        data = json.loads(response.read().decode())
        print("  • Alix Document Result:", data.get("message"))

    # 4. Test GET /api/reports (System Improvement Reports)
    print("\n--- 4. TESTING GET /api/reports (System Improvement Reports) ---")
    req = urllib.request.Request(f"{base_url}/api/reports")
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        data = json.loads(response.read().decode())
        print("  • Reports Summary Length:", len(data.get("reports", "")))

    # 5. Test POST /api/clone_agent (Rae Agent Cloner)
    print("\n--- 5. TESTING POST /api/clone_agent (Rae Agent Cloner) ---")
    clone_payload = json.dumps({
        "agent_name": "Seth",
        "role": "Financial & Tax Audit Agent"
    }).encode('utf-8')
    req = urllib.request.Request(f"{base_url}/api/clone_agent", data=clone_payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        assert response.status == 200
        data = json.loads(response.read().decode())
        print("  • Rae Agent Cloner Result:\n", data.get("message"))

    print("\n====================================================================")
    print("SUCCESS: AIMAOS ALL-IN-ONE SELF-CONTAINED UI IS 100% OPERATIONAL!")
    print("====================================================================\n")

if __name__ == "__main__":
    run_all_in_one_ui_test()
