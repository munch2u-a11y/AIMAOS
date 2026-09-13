"""Kai's Drive Ingestion Tool — scans external drives/directories, classifies files,
organizes client case folders, copies templates to Alix's library, and instantiates
CaseAgent records for each client.
"""
import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import shutil
import json
import logging
from datetime import datetime

sys.path.insert(0, AIMAOS_ROOT)
sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Kai-AI"))

from business import client_file
from core.case_specialist_service import notify_case_changed

logger = logging.getLogger(__name__)

# Folder names that group clients rather than name one, so ingestion should
# descend through them instead of registering them as a case. Offices organize
# drives differently — override with office.grouping_folders in
# aimaos_config.yaml (matched case-insensitively).
_DEFAULT_GROUPING_FOLDERS = ("CLOSED", "ARCHIVE", "ARCHIVED", "CLIENTS",
                             "ACTIVE", "FAMILY", "MISC", "GENERAL")


def _load_grouping_folders():
    try:
        import yaml
        with open(os.path.join(AIMAOS_ROOT, "aimaos_config.yaml")) as f:
            cfg = yaml.safe_load(f) or {}
        configured = (cfg.get("office", {}) or {}).get("grouping_folders")
        if configured:
            return tuple(str(x).upper() for x in configured)
    except Exception:
        pass
    return _DEFAULT_GROUPING_FOLDERS


GROUPING_FOLDERS = _load_grouping_folders()

TOOL_DEFINITION = {
    "name": "drive_ingestion",
    "description": "Scans an external drive or folder, classifies files (Client Files vs Templates vs Reference Documents), "
                   "creates organized case folders with dedicated CaseAgent managers for all clients, and catalogs templates into Alix's library.",
    "parameters": {
        "type": "object",
        "properties": {
            "drive_path": {
                "type": "string",
                "description": "Path to the root of the drive or folder to ingest (no default — ask for the drive or folder path)."
            },
            "organize_clients": {
                "type": "boolean",
                "description": "If true, creates case records and copies client files into the office workspace archive (default: true)."
            },
            "catalog_templates": {
                "type": "boolean",
                "description": "If true, organizes legal templates and forms into Alix's template library (default: true)."
            }
        },
        "required": ["drive_path"]
    }
}


def scan_and_ingest(drive_path=os.path.expanduser("~/office_drive"), organize_clients=True, catalog_templates=True):
    if not os.path.exists(drive_path):
        return {"error": f"Drive path '{drive_path}' does not exist or is not mounted."}

    report = {
        "timestamp": datetime.now().isoformat(),
        "drive_path": drive_path,
        "clients_processed": [],
        "templates_cataloged": [],
        "reference_files": [],
        "errors": []
    }

    templates_target = os.path.join(AIMAOS_ROOT, "Alix-AI/templates")
    os.makedirs(templates_target, exist_ok=True)

    # 1. Inspect top-level items
    top_items = os.listdir(drive_path)
    
    # Identify Template & Form directories
    template_dirs = [
        "DOM FORMS", "ESTATE PLANNING", "Guardianship Forms", 
        "Intake forms", "Name Change forms", "Probate forms"
    ]
    
    # 2. Ingest Templates & Standalone Forms
    if catalog_templates:
        # Standalone root templates / forms
        for item in top_items:
            item_path = os.path.join(drive_path, item)
            if os.path.isfile(item_path):
                ext = os.path.splitext(item)[1].lower()
                if ext in (".docx", ".doc", ".rtf"):
                    category = "general_templates"
                    item_lower = item.lower()
                    if "notice" in item_lower or "eviction" in item_lower:
                        category = "housing_and_notices"
                    elif "heir" in item_lower or "probate" in item_lower:
                        category = "probate"
                    elif "dpoa" in item_lower or "authority" in item_lower:
                        category = "estate_planning"
                    elif "family" in item_lower or "fl law" in item_lower or "child" in item_lower:
                        category = "family_law"
                    
                    target_dir = os.path.join(templates_target, category)
                    os.makedirs(target_dir, exist_ok=True)
                    dest_file = os.path.join(target_dir, item)
                    try:
                        shutil.copy2(item_path, dest_file)
                        report["templates_cataloged"].append({
                            "source": item,
                            "category": category,
                            "destination": dest_file
                        })
                    except Exception as e:
                        report["errors"].append(f"Error copying template {item}: {e}")

                elif ext == ".pdf":
                    # Legal reference material
                    ref_dir = os.path.join(AIMAOS_ROOT, "workspace/reference_materials")
                    os.makedirs(ref_dir, exist_ok=True)
                    dest_file = os.path.join(ref_dir, item)
                    try:
                        shutil.copy2(item_path, dest_file)
                        report["reference_files"].append({
                            "file": item,
                            "destination": dest_file
                        })
                    except Exception as e:
                        report["errors"].append(f"Error copying reference {item}: {e}")

        # Template Directories
        for tdir in template_dirs:
            tdir_path = os.path.join(drive_path, tdir)
            if os.path.isdir(tdir_path):
                category_name = tdir.lower().replace(" ", "_")
                target_dir = os.path.join(templates_target, category_name)
                os.makedirs(target_dir, exist_ok=True)
                
                for root, _, files in os.walk(tdir_path):
                    for f in files:
                        if f.startswith(".") or f.startswith("~$"):
                            continue
                        f_path = os.path.join(root, f)
                        rel_path = os.path.relpath(f_path, tdir_path)
                        dest_f = os.path.join(target_dir, rel_path)
                        os.makedirs(os.path.dirname(dest_f), exist_ok=True)
                        try:
                            shutil.copy2(f_path, dest_f)
                            report["templates_cataloged"].append({
                                "source": f"{tdir}/{rel_path}",
                                "category": category_name,
                                "destination": dest_f
                            })
                        except Exception as e:
                            report["errors"].append(f"Error copying template {f}: {e}")

    # 3. Process Client Files
    client_files_root = os.path.join(drive_path, "CLIENT FILES")
    if organize_clients and os.path.isdir(client_files_root):
        _walk_client_files(client_files_root, report)

    return report


def _walk_client_files(client_files_root, report):
    """Recursively traverses CLIENT FILES directory to discover client folders and create case records."""
    for root, dirs, files in os.walk(client_files_root):
        # Ignore system folders
        if "$RECYCLE.BIN" in root or "System Volume Information" in root:
            continue
        
        # Determine if current root contains actual case documents
        valid_doc_files = [f for f in files if not f.startswith(".") and not f.startswith("~$")]
        
        if valid_doc_files:
            rel_dir = os.path.relpath(root, client_files_root)
            parts = [p for p in rel_dir.split(os.sep) if p != "."]
            
            if not parts:
                continue

            # Determine client name and category path
            client_folder_name = parts[-1]
            category_parts = parts[:-1]
            category = "/".join(category_parts) if category_parts else "general_cases"

            # Skip grouping folders that organize clients rather than name one.
            # Offices bucket their drives differently, so this is configurable:
            # set office.grouping_folders in aimaos_config.yaml to match yours.
            if client_folder_name.upper() in GROUPING_FOLDERS:
                continue

            # Normalize "Last, First" folder names into "First Last"
            client_name = client_folder_name
            if "," in client_folder_name:
                last, first = [x.strip() for x in client_folder_name.split(",", 1)]
                client_name = f"{first} {last}"

            # Create or resolve client case file
            matter_type = "Legal Matter"
            if "CLOSED" in parts:
                matter_type = "Closed Matter"
            
            try:
                state, created = client_file.create_case_file(client_name, matter_type, category)
                target_dir = client_file.resolve_client_dir(client_name)

                # Copy files into client's official case folder
                copied_files = []
                for f in valid_doc_files:
                    src_f = os.path.join(root, f)
                    dest_f = os.path.join(target_dir, f)
                    if not os.path.exists(dest_f):
                        shutil.copy2(src_f, dest_f)
                        copied_files.append(f)

                # Log entry in case file
                client_file.log_entry(
                    client_name, 
                    f"Ingested {len(copied_files)} document(s) from external drive location: {rel_dir}"
                )

                # Run one digest-scoped review after the complete folder batch
                # is durable, rather than one review per copied document.
                review_res = notify_case_changed(
                    target_dir,
                    client_name=client_name,
                    reason=f"Drive ingestion batch: {rel_dir}",
                )

                report["clients_processed"].append({
                    "client_name": client_name,
                    "folder": client_folder_name,
                    "category": category,
                    "target_dir": target_dir,
                    "files_copied": len(copied_files),
                    "review_status": "success" if review_res.get("status") == "applied" else review_res.get("status")
                })

            except Exception as e:
                report["errors"].append(f"Error processing client '{client_name}': {e}")


def execute(drive_path=os.path.expanduser("~/office_drive"), organize_clients=True, catalog_templates=True):
    res = scan_and_ingest(drive_path=drive_path, organize_clients=organize_clients, catalog_templates=catalog_templates)
    return json.dumps(res, indent=2)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/office_drive")
    print(f"Executing drive ingestion on: {path}")
    result = scan_and_ingest(drive_path=path)
    print(f"Ingested {len(result['clients_processed'])} clients and {len(result['templates_cataloged'])} templates.")
    if result["errors"]:
        print(f"Encountered {len(result['errors'])} errors.")
