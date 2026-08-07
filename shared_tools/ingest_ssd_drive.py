#!/usr/bin/env python3
"""Master SSD Drive Ingestion & Multi-Agent Case Manager Setup Script.

Performs drive scanning, template cataloging, client case folder setup,
and CaseAgent review initialization for external drives mounted by the user (pass the mount path).
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
import logging
from datetime import datetime

sys.path.insert(0, AIMAOS_ROOT)
for rel in ["Kai-AI/tools", "Alix-AI/tools", "starter_packs/document_heavy/Kai-AI/tools", "starter_packs/document_heavy/Alix-AI/tools"]:
    p = os.path.join(AIMAOS_ROOT, rel)
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

import drive_ingestion
import catalog_templates
from core.comms.office_board import OfficeBoard

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ingest_ssd_drive")


def run_full_drive_ingestion(drive_path=os.path.expanduser("~/office_drive")):
    logger.info(f"=== Starting AIMAOS Drive Ingestion: {drive_path} ===")

    if not os.path.exists(drive_path):
        logger.error(f"Target drive path '{drive_path}' does not exist.")
        return {"error": f"Drive path '{drive_path}' non-existent."}

    # Step 1: Execute Kai's Drive Ingestion Scanner
    logger.info("Step 1: Running Kai's Drive Ingestion Scanner...")
    ingest_report = drive_ingestion.scan_and_ingest(drive_path=drive_path)
    logger.info(f"Processed {len(ingest_report['clients_processed'])} client folders, "
                f"cataloged {len(ingest_report['templates_cataloged'])} templates.")

    # Step 2: Catalog Legal Templates with Alix
    logger.info("Step 2: Cataloging Legal Templates in Alix's Library...")
    template_registry = catalog_templates.scan_and_index_templates()
    logger.info(f"Template registry updated with {len(template_registry['templates'])} indexed templates.")

    # Step 3: Register Tasks on Central Office Board
    logger.info("Step 3: Registering processing tasks on Central Office Board...")
    board = OfficeBoard()
    
    # Task for Kai to maintain archive index
    board.post_task(
        title="Drive Ingestion Indexing Audit",
        requester="System",
        target_agent="Kai",
        priority="NORMAL",
        details={"info": f"Verify client index integrity for {len(ingest_report['clients_processed'])} ingested cases from {drive_path}."}
    )

    # Task for Alix to verify template variables
    board.post_task(
        title="Template Variable Audit & Extraction",
        requester="System",
        target_agent="Alix",
        priority="NORMAL",
        details={"info": f"Inspect {len(template_registry['templates'])} new legal templates in Alix's library for Jinja2 variable mapping."}
    )

    # Summary manifest
    summary = {
        "timestamp": datetime.now().isoformat(),
        "drive_path": drive_path,
        "clients_count": len(ingest_report["clients_processed"]),
        "clients": ingest_report["clients_processed"],
        "templates_count": len(template_registry["templates"]),
        "template_categories": template_registry.get("categories", {}),
        "reference_files_count": len(ingest_report["reference_files"]),
        "errors": ingest_report["errors"]
    }

    manifest_path = os.path.join(AIMAOS_ROOT, "workspace/ssd_ingestion_manifest.json")
    with open(manifest_path, "w") as mf:
        json.dump(summary, mf, indent=2)
    
    logger.info(f"=== Drive Ingestion Complete! Manifest saved to: {manifest_path} ===")
    return summary


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/office_drive")
    res = run_full_drive_ingestion(target)
    print("\n--- INGESTION SUMMARY ---")
    print(f"Clients Ingested & Assigned Case Managers: {res.get('clients_count', 0)}")
    for c in res.get("clients", []):
        print(f"  - Client: {c['client_name']} | Category: {c['category']} | Target: {c['target_dir']}")
    print(f"Templates Cataloged: {res.get('templates_count', 0)}")
    for cat, count in res.get("template_categories", {}).items():
        print(f"  - Category '{cat}': {count} template(s)")
    if res.get("errors"):
        print(f"Warnings/Errors: {len(res['errors'])}")
