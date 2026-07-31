import os
import yaml

TOOL_DEFINITION = {
    "name": "search_files",
    "description": "Searches for a text query across all files (filenames and contents) in templates, skills, inbox, or output directories.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search term or pattern to look for."
            },
            "directory_type": {
                "type": "string",
                "enum": ["all", "inbox", "templates", "output", "skills"],
                "description": "Restrict the search to this directory type, or search all (default).",
                "default": "all"
            }
        },
        "required": ["query"]
    }
}

def get_config():
    tools_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(tools_dir)
    config_path = os.path.join(project_dir, "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            try:
                return yaml.safe_load(f)
            except Exception:
                pass
    return {}

def execute(query, directory_type="all"):
    config = get_config()
    paths = config.get("paths", {})
    
    fallback_paths = {
        "inbox": "./workspace/inbox",
        "output": "./workspace/output",
        "templates": "./templates",
        "skills": "./skills"
    }
    
    dirs_to_search = {}
    if directory_type == "all":
        for k in fallback_paths:
            dirs_to_search[k] = paths.get(k, fallback_paths[k])
    else:
        dirs_to_search[directory_type] = paths.get(directory_type, fallback_paths[directory_type])

    results = []
    query_lower = query.lower()

    for dir_type, dir_path in dirs_to_search.items():
        if not os.path.exists(dir_path):
            continue
            
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                # Skip hidden files
                if file.startswith("."):
                    continue
                    
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, dir_path)
                
                # Check filename match
                filename_match = query_lower in file.lower()
                content_matches = []
                
                # Check file content if it is a text-based file
                is_text = False
                ext = os.path.splitext(file)[1].lower()
                if ext in [".txt", ".py", ".yaml", ".yml", ".json", ".md", ".csv"]:
                    is_text = True
                    
                if is_text:
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            for idx, line in enumerate(f, 1):
                                if query_lower in line.lower():
                                    content_matches.append((idx, line.strip()))
                    except Exception:
                        pass
                
                if filename_match or content_matches:
                    results.append({
                        "directory": dir_type,
                        "filename": file,
                        "rel_path": rel_path,
                        "filename_match": filename_match,
                        "content_matches": content_matches[:5] # Limit matches per file to 5
                    })

    if not results:
        return f"No matches found for '{query}' in directory '{directory_type}'."

    output_lines = [f"Search results for '{query}' (found {len(results)} matching files):"]
    for r in results:
        match_type = []
        if r["filename_match"]:
            match_type.append("filename")
        if r["content_matches"]:
            match_type.append("contents")
            
        header = f"  [{r['directory'].upper()}] {r['rel_path']} (Match in {', '.join(match_type)})"
        output_lines.append(header)
        
        if r["content_matches"]:
            for line_no, content in r["content_matches"]:
                # Truncate content line if too long
                if len(content) > 100:
                    content = content[:97] + "..."
                output_lines.append(f"    Line {line_no}: {content}")
                
    return "\n".join(output_lines)
