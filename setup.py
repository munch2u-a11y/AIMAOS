import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import yaml
import shutil
import argparse
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

BASE_DIR = AIMAOS_ROOT
DEFAULT_PACK = "document_heavy"


def pack_agents(pack_name):
    """The initial minimal roster is whatever the chosen starter pack defines —
    a fresh checkout has no agent workspaces until setup materializes them."""
    pack_dir = os.path.join(BASE_DIR, "starter_packs", pack_name)
    if not os.path.isdir(pack_dir):
        return []
    return sorted(d for d in os.listdir(pack_dir)
                  if d.endswith("-AI") and os.path.isdir(os.path.join(pack_dir, d)))


def materialized_agents():
    return sorted(d for d in os.listdir(BASE_DIR)
                  if d.endswith("-AI") and os.path.isdir(os.path.join(BASE_DIR, d)))

def run_diagnostics():
    console.print("\n[bold cyan]1. Running AIMAOS Model-Agnostic Environment & Dependency Diagnostics...[/bold cyan]")
    
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

def get_installed_ollama_models():
    """Returns installed Ollama model tags, or None if Ollama is unreachable."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            import json
            return [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return None

def materialize_pack(pack_name=DEFAULT_PACK, force=False):
    """Copies each agent's profession-specific content from starter_packs/<pack_name>/ into live directories."""
    console.print(f"\n[bold cyan]2. Materializing starter pack '{pack_name}'...[/bold cyan]")
    pack_dir = os.path.join(BASE_DIR, "starter_packs", pack_name)
    if not os.path.isdir(pack_dir):
        console.print(f"[bold red]No such starter pack: {pack_dir}[/bold red]")
        return False

    table = Table(title=f"Starter Pack: {pack_name}")
    table.add_column("Agent Workspace", style="white")
    table.add_column("Status", style="green")

    for agent in pack_agents(pack_name):
        src_root = os.path.join(pack_dir, agent)
        dst_root = os.path.join(BASE_DIR, agent)
        if not os.path.isdir(src_root):
            table.add_row(agent, "[bold red]MISSING FROM PACK[/bold red]")
            continue
        if os.path.isdir(dst_root) and not force:
            table.add_row(agent, "[bold yellow]ALREADY EXISTS (use --force to reapply)[/bold yellow]")
            continue

        for entry in os.listdir(src_root):
            src = os.path.join(src_root, entry)
            dst = os.path.join(dst_root, entry)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.isdir(src):
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                                dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        os.makedirs(os.path.join(dst_root, "workspace", ".memory"), exist_ok=True)
        table.add_row(agent, "[bold green]MATERIALIZED[/bold green]")

    console.print(table)
    return True

def configure_workspaces():
    console.print("\n[bold cyan]3. Configuring AIMAOS Mini-Agent Workspaces from aimaos_config.yaml...[/bold cyan]")
    base_dir = BASE_DIR

    office_cfg = {}
    office_cfg_path = os.path.join(base_dir, "aimaos_config.yaml")
    if os.path.exists(office_cfg_path):
        try:
            with open(office_cfg_path, "r") as f:
                office_cfg = yaml.safe_load(f) or {}
        except Exception:
            pass
    agent_models = office_cfg.get("agents", {})
    default_model = office_cfg.get("llm", {}).get("default_model", "qwen3.5:2b")
    installed = get_installed_ollama_models()

    table = Table(title="AIMAOS Mini-Agent Roster Matrix")
    table.add_column("Agent Workspace", style="white")
    table.add_column("Assigned Model", style="yellow")
    table.add_column("Status", style="green")

    for agent in materialized_agents():
        apath = os.path.join(base_dir, agent)
        os.makedirs(os.path.join(apath, "workspace", ".memory"), exist_ok=True)

        agent_name = agent.replace("-AI", "")
        model = agent_models.get(agent_name, {}).get("model", default_model)

        cfg_path = os.path.join(apath, "config.yaml")
        cfg_data = {}
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r") as f:
                    cfg_data = yaml.safe_load(f) or {}
            except Exception:
                pass

        if "agent" not in cfg_data:
            cfg_data["agent"] = {"name": agent_name}
        cfg_data["agent"]["model"] = model
        # Shipped configs keep workspace-relative paths; stamp them absolute
        # for this machine so tools resolve them regardless of cwd.
        for key, val in list(cfg_data.get("paths", {}).items()):
            if isinstance(val, str) and not os.path.isabs(val):
                cfg_data["paths"][key] = os.path.join(apath, val)
        with open(cfg_path, "w") as f:
            yaml.dump(cfg_data, f, sort_keys=False)

        if installed is None:
            status = "[bold yellow]CONFIGURED (Ollama offline, tag unvalidated)[/bold yellow]"
        elif model in installed or any(m.startswith(model + ":") for m in installed):
            status = "[bold green]CONFIGURED & MODEL INSTALLED[/bold green]"
        else:
            status = f"[bold red]MODEL '{model}' NOT INSTALLED (ollama pull {model})[/bold red]"
        table.add_row(agent, model, status)

    console.print(table)

    comms_dir = os.path.join(base_dir, "comms")
    os.makedirs(comms_dir, exist_ok=True)
    console.print(f"  - Configured IPC Comms Bus: [bold yellow]{comms_dir}[/bold yellow]")

def configure_email_security(security_mode="READ_ONLY", approved_recipients=None, email_user=None):
    console.print("\n[bold cyan]4. Hardware-Enforced Email Security Policy Setup...[/bold cyan]")
    office_cfg_path = os.path.join(BASE_DIR, "aimaos_config.yaml")
    
    office_cfg = {}
    if os.path.exists(office_cfg_path):
        try:
            with open(office_cfg_path, "r") as f:
                office_cfg = yaml.safe_load(f) or {}
        except Exception:
            pass

    email_cfg = office_cfg.get("email", {})
    email_cfg["security_mode"] = security_mode.upper()
    if approved_recipients:
        email_cfg["approved_recipients"] = [r.strip() for r in approved_recipients.split(",") if r.strip()]
    elif "approved_recipients" not in email_cfg:
        email_cfg["approved_recipients"] = []  # empty until the operator whitelists real recipients

    office_cfg["email"] = email_cfg
    with open(office_cfg_path, "w") as f:
        yaml.dump(office_cfg, f, sort_keys=False)

    if email_user:
        cred_path = os.path.expanduser("~/.config/aimaos/credentials.env")
        os.makedirs(os.path.dirname(cred_path), exist_ok=True)
        lines = []
        if os.path.exists(cred_path):
            with open(cred_path, "r") as f:
                lines = f.readlines()
        
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith("HELIX_EMAIL_USER="):
                new_lines.append(f'HELIX_EMAIL_USER="{email_user}"\n')
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f'HELIX_EMAIL_USER="{email_user}"\n')

        with open(cred_path, "w") as f:
            f.writelines(new_lines)
        console.print(f"  - Configured Email Credentials: [bold green]{email_user}[/bold green]")

    sec_color = "green" if security_mode.upper() == "READ_ONLY" else "yellow"
    console.print(f"  - Email Security Mode: [bold {sec_color}]{security_mode.upper()}[/bold {sec_color}]")
    console.print(f"  - Approved Outbound Whitelist: [bold white]{', '.join(email_cfg.get('approved_recipients', []))}[/bold white]")

def main():
    parser = argparse.ArgumentParser(description="AIMAOS setup wizard")
    parser.add_argument("--pack", default=DEFAULT_PACK,
                        help=f"Starter pack to materialize (default: {DEFAULT_PACK}).")
    parser.add_argument("--force", action="store_true",
                        help="Re-materialize an agent workspace even if it exists.")
    parser.add_argument("--email-security-mode", default="READ_ONLY", choices=["READ_ONLY", "WHITELIST_ONLY", "DISABLED"],
                        help="Hardware-enforced email security policy mode (default: READ_ONLY).")
    parser.add_argument("--approved-recipients", default=None,
                        help="Comma-separated whitelist of approved outbound email recipients.")
    parser.add_argument("--email-user", default=None,
                        help="Optional company email address.")
    args = parser.parse_args()

    console.print(Panel("[bold cyan]AIMAOS SETUP WIZARD[/bold cyan]\nModel-Agnostic Multi-Agent Operating System Configurator", border_style="cyan"))
    run_diagnostics()
    materialize_pack(args.pack, force=args.force)
    configure_workspaces()
    configure_email_security(args.email_security_mode, args.approved_recipients, args.email_user)
    console.print("\n[bold green]SUCCESS: AIMAOS Model-Agnostic Setup Completed![/bold green]")
    console.print("Run [bold yellow]python3 aimaos_ui.py[/bold yellow] (dashboard) or [bold yellow]python3 run_office.py[/bold yellow] (autonomous daemon).")

if __name__ == "__main__":
    main()
