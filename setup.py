import os
import sys
import yaml
import shutil
import subprocess
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

DEFAULT_MODEL_ASSIGNMENTS = {
    "Alix-AI": "gemma2:9b",
    "Kai-AI": "llama3.1:8b",
    "Marley-AI": "qwen2.5:7b",
    "Quinn-AI": "mistral:7b",
    "Zoe-AI": "llama3.1:8b",
    "Finn-AI": "llama3:latest",
    "Rae-AI": "llama3.1:8b"
}

def run_diagnostics():
    console.print("\n[bold cyan]1. Running AIMAOS Environment & Dependency Diagnostics...[/bold cyan]")
    
    deps = {
        "Python Version": sys.version.split()[0],
        "docxtpl (Jinja2 Word Renderer)": import_check("docxtpl"),
        "rich (Terminal UI Engine)": import_check("rich"),
        "pyyaml (Config Parser)": import_check("yaml"),
        "soffice / LibreOffice (PDF Converter)": shutil.which("soffice") is not None
    }

    table = Table(title="Dependency Diagnostics")
    table.add_column("Component", style="white")
    table.add_column("Status", style="green")

    for name, val in deps.items():
        st = "[bold green]INSTALLED[/bold green]" if val else "[bold red]MISSING[/bold red]"
        if isinstance(val, str) and not isinstance(val, bool):
            st = f"[bold green]{val}[/bold green]"
        table.add_row(name, st)

    console.print(table)

def import_check(mod_name):
    try:
        __import__(mod_name)
        return True
    except ImportError:
        return False

def configure_workspaces():
    console.print("\n[bold cyan]2. Configuring AIMAOS Agent Workspaces & Multi-Model Assignment Matrix...[/bold cyan]")
    base_dir = "/path/to/AIMAOS"
    
    table = Table(title="AIMAOS Mini-Agent Multi-Model Matrix")
    table.add_column("Agent Workspace", style="white")
    table.add_column("Assigned LLM Model", style="yellow")
    table.add_column("Status", style="green")

    for agent, model in DEFAULT_MODEL_ASSIGNMENTS.items():
        apath = os.path.join(base_dir, agent)
        os.makedirs(os.path.join(apath, "workspace", ".memory"), exist_ok=True)
        
        cfg_path = os.path.join(apath, "config.yaml")
        cfg_data = {}
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r") as f:
                    cfg_data = yaml.safe_load(f) or {}
            except Exception:
                pass

        if "agent" not in cfg_data:
            cfg_data["agent"] = {"name": agent.replace("-AI", "")}
        
        cfg_data["agent"]["model"] = model
        with open(cfg_path, "w") as f:
            yaml.dump(cfg_data, f, sort_keys=False)

        table.add_row(agent, model, "[bold green]CONFIGURED[/bold green]")

    console.print(table)

    comms_dir = os.path.join(base_dir, "comms")
    os.makedirs(comms_dir, exist_ok=True)
    console.print(f"  - Configured IPC Comms Bus: [bold yellow]{comms_dir}[/bold yellow]")

def main():
    console.print(Panel("[bold cyan]AIMAOS SETUP WIZARD[/bold cyan]\nHelix-Style Multi-Model & Minimal mRAG Configurator", border_style="cyan"))
    run_diagnostics()
    configure_workspaces()
    console.print("\n[bold green]SUCCESS: AIMAOS Multi-Model Setup Completed![/bold green]")
    console.print("Run [bold yellow]python3 /path/to/AIMAOS/aimaos_ui.py[/bold yellow] to launch the All-in-One Dashboard!")

if __name__ == "__main__":
    main()
