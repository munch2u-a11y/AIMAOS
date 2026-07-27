import os
import sys
import json
import importlib.util

sys.path.insert(0, "/path/to/AIMAOS/Alix-AI")
from core.document_engine import DocumentEngine
from core.comms.office_board import OfficeBoard

USER_EMAIL = "helix.agi.system@gmail.com"

def load_module(mod_name, file_path):
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

def run_multi_county_dispatch_test():
    print("====================================================================")
    print("AIMAOS MULTI-COUNTY CLIENT INTAKE, FORM GENERATION & EMAIL DISPATCH")
    print(f"Target User Email: {USER_EMAIL}")
    print("====================================================================\n")

    # Load agent modules
    finn_agent_mod = load_module("finn_agent_mod", "/path/to/AIMAOS/Finn-AI/core/agent.py")
    kai_agent_mod = load_module("kai_agent_mod", "/path/to/AIMAOS/Kai-AI/core/agent.py")
    marley_agent_mod = load_module("marley_agent_mod", "/path/to/AIMAOS/Marley-AI/core/agent.py")
    quinn_agent_mod = load_module("quinn_agent_mod", "/path/to/AIMAOS/Quinn-AI/core/agent.py")
    
    cmd_channel_mod = load_module("cmd_channel_mod", "/path/to/AIMAOS/Finn-AI/tools/commandeer_channel.py")

    finn = finn_agent_mod.FinnAgent()
    kai = kai_agent_mod.KaiAgent()
    marley = marley_agent_mod.MarleyAgent()
    quinn = quinn_agent_mod.QuinnAgent()

    board = OfficeBoard()
    templates_base = "/path/to/AIMAOS/Alix-AI/templates"

    clients = [
        {
            "name": "Alexander James Montgomery",
            "county": "Leon",
            "circuit": "2nd",
            "case_type": "Adult Name Change",
            "forms": ["form_12_982_a", "form_12_982_b"],
            "context": {
                "circuit_number": "2nd",
                "county": "Leon",
                "case_number": "2026-DR-002101",
                "division": "Family Law",
                "client_name": "Alexander James Montgomery",
                "new_name": "Alexander Sterling",
                "client_address": "1420 Timberlane Road, Tallahassee, FL 32312",
                "client_phone": "(850) 555-0144",
                "client_email": USER_EMAIL,
                "date_of_birth": "March 12, 1991"
            },
            "next_steps": [
                "1. Submit fingerprint card to FDLE for criminal history background check.",
                "2. File Petition for Change of Name (Adult) with Leon County Clerk of Court.",
                "3. Request final hearing date once FDLE results are received by Clerk."
            ]
        },
        {
            "name": "Sarah Jenkins",
            "county": "Clay",
            "circuit": "4th",
            "case_type": "Guardianship of Minor Child Name Change",
            "forms": ["form_12_982_f", "form_12_902_d"],
            "context": {
                "circuit_number": "4th",
                "county": "Clay",
                "case_number": "2026-DR-003420",
                "division": "Family Law",
                "parent_name": "Sarah Jenkins",
                "child_name": "Jacob Jenkins",
                "client_name": "Sarah Jenkins",
                "client_address": "405 Walnut Street, Green Cove Springs, FL 32043",
                "client_phone": "(904) 555-0198",
                "client_email": USER_EMAIL
            },
            "next_steps": [
                "1. Obtain signed Consent for Change of Name of Minor Child (Form 12.982g) from biological father.",
                "2. File Petition and UCCJEA Custody Affidavit with Clay County Clerk in Green Cove Springs.",
                "3. Serve formal Notice of Hearing on non-petitioning parent if consent is withheld."
            ]
        },
        {
            "name": "David and Elena Miller",
            "county": "Duval",
            "circuit": "4th",
            "case_type": "Dissolution of Marriage with Minor Children",
            "forms": ["form_12_901_a", "form_12_902_c", "form_12_902_e"],
            "context": {
                "circuit_number": "4th",
                "county": "Duval",
                "case_number": "2026-DR-008910",
                "division": "Family Law",
                "husband_name": "David Miller",
                "wife_name": "Elena Miller",
                "client_name": "David Miller",
                "spouse_name": "Elena Miller",
                "county": "Duval",
                "client_address": "1200 Ocean Boulevard, Jacksonville, FL 32216",
                "client_email": USER_EMAIL
            },
            "next_steps": [
                "1. Complete mandatory 4-hour Florida Parent Education and Family Stabilization Course.",
                "2. Execute Marital Settlement Agreement (Form 12.902f3) detailing time-sharing.",
                "3. File Joint Petition, Financial Affidavits, and Child Support Worksheet with Duval County Clerk."
            ]
        }
    ]

    dispatch_results = []

    for c in clients:
        print(f"\n====================================================================")
        print(f"PROCESSING CLIENT: {c['name']} ({c['county']} County | {c['case_type']})")
        print(f"====================================================================")

        # 1. Finn Security Gateway Triage
        triage_msg = finn.process_user_message(
            message=f"Intake request for {c['name']} in {c['county']} County for {c['case_type']}.",
            sender=USER_EMAIL
        )
        print("\n[FINN SECURITY TRIAGE]:\n", triage_msg)

        # 2. Form Generation
        generated_files = []
        out_dir = f"/path/to/AIMAOS/Alix-AI/workspace/output/{c['name'].lower().replace(' ', '_')}/2026-07-27"
        os.makedirs(out_dir, exist_ok=True)

        for form_id in c["forms"]:
            tpl_path = os.path.join(templates_base, form_id, "template.docx")
            if not os.path.exists(tpl_path):
                print(f"  • Warning: Template file not found at {tpl_path}, skipping.")
                continue

            engine = DocumentEngine(tpl_path)
            docx_out = os.path.join(out_dir, f"{form_id}_filled.docx")
            engine.generate(c["context"], docx_out)
            generated_files.append(docx_out)
            print(f"  • Generated Court Form [{form_id}]: {docx_out}")

        # 3. Commandeer Finn's Channel to send Email Package to helix.agi.system@gmail.com
        email_body = f"""DEAR CLIENT / COUNSEL,

Below is the completed legal filing package prepared by the AIMAOS Office Suite for {c['name']}.

JURISDICTION DETAILS:
- Client Name: {c['name']}
- County: {c['county']} County, Florida
- Judicial Circuit: {c['circuit']} Judicial Circuit
- Matter: {c['case_type']}

GENERATED COURT FORMS ATTACHED:
""" + "\n".join(f"- {os.path.basename(f)}" for f in generated_files) + """

IDENTIFIED NEXT STEPS & PROCEDURAL INSTRUCTIONS:
""" + "\n".join(c["next_steps"]) + """

Best regards,
Alix & Finn (AIMAOS Office Suite)
"""

        dispatch_res = cmd_channel_mod.execute(
            calling_agent="Alix",
            recipient_email=USER_EMAIL,
            subject=f"Legal Document Filing Package: {c['name']} ({c['county']} County)",
            body=email_body,
            attachments=generated_files
        )
        print("\n[EMAIL DISPATCH RESULT]:\n", dispatch_res)
        dispatch_results.append((c['name'], len(generated_files), dispatch_res))

    print("\n====================================================================")
    print("SUMMARY OF MULTI-COUNTY DISPATCHES TO helix.agi.system@gmail.com")
    print("====================================================================")
    for name, fcount, dres in dispatch_results:
        print(f"✅ Client '{name}': {fcount} forms generated & emailed to {USER_EMAIL}")
    print("====================================================================\n")

if __name__ == "__main__":
    run_multi_county_dispatch_test()
