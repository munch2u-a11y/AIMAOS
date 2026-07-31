import os
import yaml
from datetime import datetime

TOOL_DEFINITION = {
    "name": "list_files",
    "description": "Lists all files in a specified folder (inbox, templates, output, or skills) with file size and last modified date.",
    "parameters": {
        "type": "object",
        "properties": {
            "directory_type": {
                "type": "string",
                "enum": ["inbox", "templates", "output", "skills"],
                "description": "The category of files to list."
            }
        },
        "required": ["directory_type"]
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

def execute(directory_type):
    config = get_config()
    paths = config.get("paths", {})
    
    dir_path = paths.get(directory_type)
    if not dir_path:
        # Fallbacks
        fallback_paths = {
            "inbox": "./workspace/inbox",
            "output": "./workspace/output",
            "templates": "./templates",
            "skills": "./skills"
        }
        dir_path = fallback_paths.get(directory_type)

    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)

    try:
        files = os.listdir(dir_path)
    except Exception as e:
        return f"Error reading directory {directory_type}: {e}"

    if not files:
        return f"The {directory_type} directory is currently empty."

    lines = [f"Contents of {directory_type} ({dir_path}):"]
    
    # Sort files by name
    for name in sorted(files):
        # Skip hidden files
        if name.startswith("."):
            continue
            
        full_path = os.path.join(dir_path, name)
        
        # Check if directory or file
        if os.path.isdir(full_path):
            modified = datetime.fromtimestamp(os.path.getmtime(full_path)).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"  [DIR]  {name}/  (Modified: {modified})")
        else:
            size_bytes = os.path.getsize(full_path)
            # Format size nicely
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes/1024:.1f} KB"
            else:
                size_str = f"{size_bytes/(1024*1024):.1f} MB"
                
            modified = datetime.fromtimestamp(os.path.getmtime(full_path)).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"  [FILE] {name} ({size_str}, Modified: {modified})")
            
    return "\n".join(lines)
