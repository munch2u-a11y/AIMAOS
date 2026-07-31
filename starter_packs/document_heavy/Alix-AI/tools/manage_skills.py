import os
import yaml

TOOL_DEFINITION = {
    "name": "manage_skills",
    "description": "Create, update, list, or retrieve custom skills (reusable Python scripts for specific tasks).",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "update", "list", "get"],
                "description": "The CRUD action to perform."
            },
            "skill_name": {
                "type": "string",
                "description": "The unique snake_case name of the skill (required for create, update, and get)."
            },
            "description_text": {
                "type": "string",
                "description": "A summary of what the skill does (required for create)."
            },
            "input_format": {
                "type": "string",
                "description": "Description of expected input (e.g. 'Raw email body text') (optional)."
            },
            "output_format": {
                "type": "string",
                "description": "Description of expected output format (e.g. 'JSON with client_name and address') (optional)."
            },
            "script_content": {
                "type": "string",
                "description": "The Python source code for run.py (required for create and update)."
            }
        },
        "required": ["action"]
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

def execute(action, skill_name=None, description_text=None, input_format=None, output_format=None, script_content=None):
    config = get_config()
    paths = config.get("paths", {})
    skills_dir = paths.get("skills", "./skills")
    
    if not os.path.exists(skills_dir):
        os.makedirs(skills_dir, exist_ok=True)

    if action == "list":
        skills = []
        for item in sorted(os.listdir(skills_dir)):
            item_path = os.path.join(skills_dir, item)
            if os.path.isdir(item_path):
                yaml_path = os.path.join(item_path, "skill.yaml")
                if os.path.exists(yaml_path):
                    try:
                        with open(yaml_path, "r") as f:
                            meta = yaml.safe_load(f)
                        skills.append(f"- {meta.get('name')}: {meta.get('description', 'No description')}")
                    except Exception:
                        skills.append(f"- {item} (yaml parsing failed)")
                else:
                    skills.append(f"- {item} (no skill.yaml metadata)")
                    
        if not skills:
            return "No skills currently registered."
        return "Registered Skills:\n" + "\n".join(skills)

    if not skill_name:
        return "Error: skill_name is required for actions create, update, and get."

    # Normalize skill name to safe folder name
    skill_name = skill_name.strip().replace(" ", "_").lower()
    skill_path = os.path.join(skills_dir, skill_name)

    if action == "get":
        yaml_path = os.path.join(skill_path, "skill.yaml")
        run_py_path = os.path.join(skill_path, "run.py")
        
        if not os.path.exists(skill_path):
            return f"Error: Skill '{skill_name}' does not exist."
            
        result = [f"Skill '{skill_name}' Details:"]
        if os.path.exists(yaml_path):
            try:
                with open(yaml_path, "r") as f:
                    result.append(f"\n--- skill.yaml ---\n{f.read()}")
            except Exception as e:
                result.append(f"Error reading skill.yaml: {e}")
                
        if os.path.exists(run_py_path):
            try:
                with open(run_py_path, "r") as f:
                    result.append(f"\n--- run.py ---\n{f.read()}")
            except Exception as e:
                result.append(f"Error reading run.py: {e}")
                
        return "\n".join(result)

    if action in ["create", "update"]:
        if not script_content:
            return f"Error: script_content is required to {action} a skill."

        os.makedirs(skill_path, exist_ok=True)
        yaml_path = os.path.join(skill_path, "skill.yaml")
        run_py_path = os.path.join(skill_path, "run.py")

        # Handle skill.yaml update or create
        meta = {}
        if os.path.exists(yaml_path) and action == "update":
            try:
                with open(yaml_path, "r") as f:
                    meta = yaml.safe_load(f) or {}
            except Exception:
                pass
        
        if description_text:
            meta["description"] = description_text
        elif action == "create" and not description_text:
            return "Error: description_text is required to create a skill."
            
        meta["name"] = skill_name
        if input_format:
            meta["input"] = input_format
        if output_format:
            meta["output"] = output_format
        if "created" not in meta:
            from datetime import datetime
            meta["created"] = datetime.now().strftime("%Y-%m-%d")

        try:
            with open(yaml_path, "w") as f:
                yaml.safe_dump(meta, f, default_flow_style=False)
        except Exception as e:
            return f"Error writing skill.yaml: {e}"

        try:
            with open(run_py_path, "w") as f:
                f.write(script_content)
            # Make the file executable if on unix
            if os.name == "posix":
                os.chmod(run_py_path, 0o755)
        except Exception as e:
            return f"Error writing run.py: {e}"

        return f"Success: Skill '{skill_name}' successfully {action}d at {skill_path}"

    return f"Error: Unsupported action '{action}'."
