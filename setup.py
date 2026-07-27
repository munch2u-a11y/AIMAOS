import os
import sys
import shutil
import subprocess
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

def run_diagnostics():
    console.print("\n[bold cyan]1. Running AIMAOS Environment & Dependency Checks...[/bold cyan]")
    
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
    console.print("\n[bold cyan]2. Verifying AIMAOS Agent Workspaces & IPC Directories...[/bold cyan]")
    base_dir = "/path/to/AIMAOS"
    agents = ["Alix-AI", "Kai-AI", "Marley-AI", "Quinn-AI", "Zoe-AI", "Echo-AI", "Nova-AI"]
    
    for agent in agents:
        apath = os.path.join(base_dir, agent)
        os.makedirs(os.path.join(apath, "workspace", ".memory"), exist_ok=True)
        console.print(f"  - Configured workspace: [bold yellow]{apath}[/bold yellow]")

    comms_dir = os.path.join(base_dir, "comms")
    os.makedirs(comms_dir, exist_ok=True)
    console.print(f"  - Configured IPC Comms Bus: [bold yellow]{comms_dir}[/bold yellow]")

def main():
    console.print(Panel("[bold cyan]AIMAOS SETUP WIZARD[/bold cyan]\nConfiguring AI Multi-Agent Office Suite Operating System", border_style="cyan"))
    run_diagnostics()
    configure_workspaces()
    console.print("\n[bold green]SUCCESS: AIMAOS Environment Setup Completed![/bold green]")
    console.print("Run [bold yellow]python3 /path/to/AIMAOS/ui/web_ui.py[/bold yellow] to launch the Web Interface!")

if __name__ == "__main__":
    main()
