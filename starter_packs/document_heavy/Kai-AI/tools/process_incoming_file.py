"""Kai's incoming-correspondence workflow: something arrived for a client
who already has a case (the running example: an emailed attachment like a
birth certificate). Real IMAP fetching isn't built -- this takes a file
already saved locally (whatever fetched it, or a manual drop) and runs the
rest of the sequence for real:

  1. Confirm the client's case already exists (never silently create one
     here -- an unrecognized name goes through the normal intake path instead).
  2. File the attachment into the right folder, renaming if asked.
  3. Hand off to case_review.run_review_and_apply -- the same shared review
     step manage_case_records' review action uses, so a review triggered by
     a new arrival gets exactly the same follow-through (tasks posted,
     deadlines scheduled, a client notification queued) as one triggered by
     routine housekeeping.
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

sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Kai-AI"))
from business import client_file
from business import case_review

TOOL_DEFINITION = {
    "name": "process_incoming_file",
    "description": "Handles a file that arrived for a client who should already have a case (e.g. an "
                   "emailed attachment): confirms the case exists, files the attachment (renaming if "
                   "asked), then runs the case's review agent, which posts follow-up tasks, calendar "
                   "deadlines, and a client-notification task for Finn wherever it identifies them. "
                   "Refuses (rather than guessing) if no case exists yet for the given name.",
    "parameters": {
        "type": "object",
        "properties": {
            "client_name": {
                "type": "string",
                "description": "The client this file is for — must already have a case record."
            },
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to file (already downloaded/saved locally)."
            },
            "rename_to": {
                "type": "string",
                "description": "Optional clearer filename to use instead of the original (extension "
                               "kept from the original if omitted from this)."
            }
        },
        "required": ["client_name", "file_path"]
    }
}


def execute(client_name, file_path, rename_to=None):
    if not os.path.isfile(file_path):
        return f"Error: file not found: {file_path}"

    if not client_file.client_exists(client_name):
        return (f"No existing case found for '{client_name}' — not filing anything under a guess. "
                f"If this is actually a new client, use the standard intake process (manage_case_records "
                f"action=create) to open a case first.")

    case_dir = client_file.resolve_client_dir(client_name)

    if rename_to:
        ext = os.path.splitext(file_path)[1]
        final_name = rename_to if os.path.splitext(rename_to)[1] else rename_to + ext
    else:
        final_name = os.path.basename(file_path)
    dest_path = os.path.join(case_dir, final_name)
    shutil.copy2(file_path, dest_path)
    client_file.mark_document_dispatched(client_name, final_name, dest_path)

    report, _update = case_review.run_review_and_apply(client_name)
    return f"Filed {final_name} for {client_name} at {dest_path}.\n" + "\n".join(report)
