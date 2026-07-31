import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys

sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Kai-AI"))
from business import client_file
from business import case_review

TOOL_DEFINITION = {
    "name": "manage_case_records",
    "description": "Creates and organizes a client/case record: a directory (placed under whatever "
                   "category makes sense for this office's work — by matter type, by branch, whatever "
                   "fits), plus a persistent case file in it (status summary, next-steps list, "
                   "required-document checklist, activity log). Other agents' document dispatches log "
                   "themselves here automatically. Each case also has its own small review agent "
                   "(action=review) with its own private memory of past reviews, independent of the "
                   "shared case file -- a review also posts any follow-up work it identifies to the "
                   "Office Board, any deadlines to Marley's calendar, and a client-notification task to "
                   "Finn if the client needs to do or review something. Use action=list_stale to find which cases actually need a review "
                   "instead of reviewing everything blind. close/reopen actually relocate the case's "
                   "directory (not just a status label) to wherever it belongs in the archive once "
                   "concluded/reactivated. action=audit reports any indexed record whose real location "
                   "has drifted from where it should be; action=recategorize is how you actually fix "
                   "what it flags.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "log_entry", "update_status", "get", "review", "list_stale",
                         "close", "reopen", "audit", "recategorize"],
                "description": "create: start a new case record (no-op if one already exists, "
                               "regardless of category given); log_entry: append one dated note; "
                               "update_status: replace the summary and/or next-steps and/or "
                               "required-document statuses (only fields given are changed); "
                               "get: return the current case file as markdown; review: have the case's "
                               "own review agent look over the directory and the current record and "
                               "propose updates (a real reasoning pass, not instant — use when "
                               "something has actually changed, not on every dispatch); list_stale: "
                               "report every case whose files have changed since it was last reviewed "
                               "(or that's never been reviewed) — no client_name needed; close: mark "
                               "the case closed and physically move its folder under a 'closed' branch "
                               "of its current category (or wherever `category` says); reopen: mark it "
                               "open again and move it back out of 'closed' (or wherever `category` "
                               "says); audit: report indexed records whose real location doesn't match "
                               "where it should be — no client_name needed; recategorize: move a case "
                               "to a different category without touching its open/closed state — how "
                               "you actually fix what audit flags (a case that drifted to the wrong "
                               "spot, not one that needs closing). Don't close/reopen/recategorize a "
                               "case while a review of it may be in flight."
            },
            "client_name": {
                "type": "string",
                "description": "Client's name — must match what other agents use (populate_template, "
                               "dispatch_document) so everything lands in the same record. Not needed "
                               "for list_stale."
            },
            "matter_type": {
                "type": "string",
                "description": "create only: what kind of matter this is, e.g. 'Minor name change'."
            },
            "category": {
                "type": "string",
                "description": "create: the organizational folder this record should live under — "
                               "your judgment call on how this office's records are best grouped (by "
                               "case/matter type, by branch, etc). Omit to place it at the archive "
                               "root. On create, only matters at first creation — a record keeps its "
                               "location afterward until moved. close/reopen: optional explicit "
                               "destination category, overriding the default of appending/removing a "
                               "'closed' branch under wherever the case already lives. recategorize: "
                               "required — the new category to move it to."
            },
            "case_number": {
                "type": "string",
                "description": "create only: court/matter case number, if assigned yet."
            },
            "entry": {
                "type": "string",
                "description": "log_entry only: the note to append."
            },
            "summary": {
                "type": "string",
                "description": "update_status only: replaces the status summary paragraph."
            },
            "next_steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "update_status only: replaces the next-steps list entirely — give the "
                               "full current list, not just additions."
            },
            "required_documents": {
                "type": "object",
                "description": "update_status only: document name -> status string (e.g. "
                               "'not_started', 'drafted', 'needs_review'). Merges into the existing "
                               "checklist rather than replacing it."
            },
            "preferred_channel": {
                "type": "string",
                "description": "update_status only: how this client prefers to be contacted (e.g. "
                               "'email'), if they've said so. Only email actually delivers today; this "
                               "records the preference for when more channels are wired."
            }
        },
        "required": ["action"]
    }
}


def execute(action, client_name=None, matter_type=None, category=None, case_number=None, entry=None,
            summary=None, next_steps=None, required_documents=None, preferred_channel=None):
    if action == "list_stale":
        stale = client_file.list_stale_clients()
        if not stale:
            return "No cases need review — every case's files are unchanged since its last review."
        lines = [f"- {c['client_name']}: {c['reason']}" for c in stale]
        return f"{len(stale)} case(s) need review:\n" + "\n".join(lines)

    if action == "audit":
        findings = client_file.audit_records()
        if not findings:
            return "Audit clean: every indexed record resolves to a real, valid path under the archive root."
        lines = [f"- {f['client_name']} ({f['issue']}): {f['path']}" for f in findings]
        return f"{len(findings)} record(s) need attention:\n" + "\n".join(lines)

    if not client_name:
        return f"Error: action '{action}' requires client_name."

    if action == "create":
        if not matter_type:
            return "Error: create requires matter_type."
        state, created = client_file.create_case_file(client_name, matter_type, category, case_number)
        verb = "Created" if created else "Case record already existed for"
        loc = client_file.resolve_client_dir(client_name)
        return f"{verb} {client_name} -> {loc}"

    if action == "log_entry":
        if not entry:
            return "Error: log_entry requires entry."
        state = client_file.log_entry(client_name, entry)
        if state is None:
            return f"Error: no case record exists yet for {client_name}; use action=create first."
        return f"Logged entry for {client_name}."

    if action == "update_status":
        state = client_file.update_status(client_name, summary=summary, next_steps=next_steps,
                                          required_documents=required_documents,
                                          preferred_channel=preferred_channel)
        if state is None:
            return f"Error: no case record exists yet for {client_name}; use action=create first."
        return f"Updated case record for {client_name}."

    if action == "get":
        md = client_file.get_markdown(client_name)
        if md is None:
            return f"No case record exists yet for {client_name}."
        return md

    if action == "review":
        report, _update = case_review.run_review_and_apply(client_name)
        return "\n".join(report)

    if action in ("close", "reopen"):
        target_state = "closed" if action == "close" else "open"
        state = client_file.update_status(client_name, state_label=target_state)
        if state is None:
            return f"Error: no case record exists yet for {client_name}; use action=create first."
        current_category = state.get("category") or ""
        if category:
            dest_category = category
        elif action == "close":
            dest_category = f"{current_category}/closed" if current_category else "closed"
        elif current_category.endswith("/closed"):
            dest_category = current_category[:-len("/closed")]
        else:
            dest_category = None

        if not dest_category:
            return f"Marked {client_name} {target_state} (record stayed at its current location)."
        new_path = client_file.move_client_dir(client_name, dest_category)
        if new_path is None:
            return f"Marked {client_name} {target_state}, but could not locate its directory to move (index missing?)."
        return f"Marked {client_name} {target_state} and moved its record to {new_path}."

    if action == "recategorize":
        if not category:
            return "Error: recategorize requires category (the destination to move it to)."
        new_path = client_file.move_client_dir(client_name, category)
        if new_path is None:
            return f"Error: no indexed record found for {client_name} to move."
        return f"Moved {client_name} to {new_path}."

    return (f"Unknown action '{action}'. Use create, log_entry, update_status, get, review, "
            f"list_stale, close, reopen, audit, or recategorize.")
