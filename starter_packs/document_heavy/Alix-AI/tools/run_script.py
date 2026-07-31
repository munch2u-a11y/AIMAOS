import os
import sys
import subprocess
import yaml
from core.security import resolve_within, validate_tool_name

TOOL_DEFINITION = {
    "name": "run_script",
    "description": "Executes a custom Python skill script by passing input data via stdin and capturing the output from stdout.",
    "parameters": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "The name of the skill to execute (e.g. 'extract_tax_fields')."
            },
            "input_data": {
                "type": "string",
                "description": "The input data to pass to the script via stdin. Can be plain text or a JSON string."
            }
        },
        "required": ["skill_name", "input_data"]
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

def execute(skill_name, input_data):
    config = get_config()
    paths = config.get("paths", {})
    skills_dir = paths.get("skills", "./skills")
    
    # Normalize skill name
    try:
        skill_name = validate_tool_name(skill_name, label="skill name")
        run_py_path = resolve_within(skills_dir, skill_name, "run.py")
    except ValueError as exc:
        return f"Error: {exc}"

    if not os.path.exists(run_py_path):
        return f"Error: Skill '{skill_name}' does not exist or has no 'run.py' at: {run_py_path}"

    try:
        # Run subprocess using the same python interpreter
        result = subprocess.run(
            [sys.executable, run_py_path],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.join(skills_dir, skill_name) # Run within its own directory for file isolation
        )
        
        output = []
        if result.returncode == 0:
            output.append(f"Skill '{skill_name}' executed successfully.")
            if result.stdout.strip():
                output.append(f"Output:\n{result.stdout}")
            else:
                output.append("Output was empty.")
        else:
            output.append(f"Error: Skill '{skill_name}' exited with non-zero code {result.returncode}.")
            if result.stderr.strip():
                output.append(f"Error Details (stderr):\n{result.stderr}")
            if result.stdout.strip():
                output.append(f"Partial Output (stdout):\n{result.stdout}")
                
        return "\n".join(output)
    except subprocess.TimeoutExpired:
        return f"Error: Skill '{skill_name}' execution timed out after 30 seconds."
    except Exception as e:
        return f"Error running skill '{skill_name}': {e}"
