"""Drafts a clear, professional message asking a client to confirm or
provide specific information in writing, shared by every AIMAOS agent. For
the exact situation this office just hit: a handwritten/scanned document
couldn't be reliably read, so ask the client to type the answer instead of
guessing from an unreliable read.

Deliberately template-based, not model-generated — right after finding that
local vision extraction can fabricate plausible-looking wrong answers, a
second unreviewed model call drafting the client-facing message would be
exactly the wrong place to introduce another point of unreliability. This
returns the draft text only; hand it to Finn's email tool to actually send.
"""
TOOL_DEFINITION = {
    "name": "draft_client_request",
    "description": "Drafts a professional message asking a client to confirm or provide specific "
                   "information in writing (typed), e.g. when a scanned or handwritten document "
                   "couldn't be reliably read. Returns draft text only — does not send anything.",
    "parameters": {
        "type": "object",
        "properties": {
            "client_name": {
                "type": "string",
                "description": "Client's name, for the greeting."
            },
            "case_context": {
                "type": "string",
                "description": "One short phrase naming the matter, e.g. 'your name change petition'."
            },
            "needed_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Plain-language descriptions of what's needed, e.g. ['the exact legal "
                               "spelling of the requested new name', 'your current county of residence']."
            },
            "reason": {
                "type": "string",
                "description": "Why it's needed, e.g. 'the handwritten intake form couldn't be reliably "
                               "read'. Optional — a generic reason is used if omitted."
            }
        },
        "required": ["client_name", "case_context", "needed_fields"]
    }
}


def execute(client_name, case_context, needed_fields, reason=None):
    if not needed_fields:
        return "Error: needed_fields must not be empty."

    reason_line = reason or "a few details need to be confirmed before we can proceed"
    fields_list = "\n".join(f"  - {f}" for f in needed_fields)

    return f"""Dear {client_name},

Thank you for submitting your intake materials for {case_context}.

Before we can prepare your documents, {reason_line}. Could you reply with the following, typed rather than handwritten where possible, so we can be certain it's recorded accurately:

{fields_list}

Once we have this confirmed, we'll move forward with preparing everything for filing.

Thank you,
The Office"""
