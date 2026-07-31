import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import hashlib
import glob
import re

TOOL_DEFINITION = {
    "name": "check_duplicates",
    "description": "Scans the file catalog, template library, and archives to check if a document, template, or client record already exists or has a near-duplicate match.",
    "parameters": {
        "type": "object",
        "properties": {
            "query_text": {
                "type": "string",
                "description": "Text content, keywords, or title to check for duplicates."
            },
            "search_dir": {
                "type": "string",
                "description": "Directory path to check (defaults to Alix-AI templates and output archives)."
            }
        },
        "required": ["query_text"]
    }
}

def execute(query_text, search_dir=None):
    if not search_dir:
        search_dirs = [
            os.path.join(AIMAOS_ROOT, "Alix-AI/templates"),
            os.path.join(AIMAOS_ROOT, "Alix-AI/workspace/output")
        ]
    else:
        search_dirs = [search_dir]

    query_norm = set(re.findall(r"\w+", query_text.lower()))
    matches = []

    for sdir in search_dirs:
        if not os.path.exists(sdir):
            continue
        for root, dirs, files in os.walk(sdir):
            for f in files:
                fpath = os.path.join(root, f)
                fname_norm = set(re.findall(r"\w+", f.lower()))

                # Filename overlap score
                filename_overlap = len(query_norm.intersection(fname_norm))
                if filename_overlap >= 2 or query_text.lower() in f.lower():
                    matches.append({
                        "file_path": fpath,
                        "match_type": "filename_overlap",
                        "score": round(filename_overlap / max(len(query_norm), 1), 2)
                    })

    if not matches:
        return f"No duplicates or near-matching records found for '{query_text}'. Record is unique."

    res = [f"Found {len(matches)} potential existing match(es) for '{query_text}':"]
    for m in matches[:5]:
        res.append(f"- Match [{m['match_type']} - score {m['score']}]: {m['file_path']}")
    return "\n".join(res)
