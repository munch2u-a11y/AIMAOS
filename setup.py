import os
import re

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

from core.atomic_io import atomic_write_text
from core.platform_support import find_libreoffice, launch_command, user_config_path

console = Console()

BASE_DIR = AIMAOS_ROOT
DEFAULT_PACK = "document_heavy"
MODEL_TAG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$")


def _load_yaml(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Could not read valid YAML from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping in {path}.")
    return payload


def _write_yaml(path, payload):
    atomic_write_text(path, yaml.safe_dump(payload, sort_keys=False), mode=0o600)


def _validated_model_tag(value):
    value = (value or "").strip()
    if not MODEL_TAG_PATTERN.fullmatch(value) or ".." in value or value.endswith(("/", ":")):
        raise ValueError("Model tags may contain letters, numbers, '.', '_', '-', '/', and ':' only.")
    return value


def _validated_email(value):
    value = (value or "").strip()
    if not EMAIL_PATTERN.fullmatch(value) or "\r" in value or "\n" in value:
        raise ValueError(f"Invalid email address: {value!r}")
    return value


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
        "soffice / LibreOffice (PDF Converter)": find_libreoffice() is not None
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

def get_installed_ollama_models(host="http://localhost:11434"):
    """Returns installed Ollama model tags, or None if Ollama is unreachable."""
    try:
        import urllib.request
        with urllib.request.urlopen(host.rstrip("/") + "/api/tags", timeout=3) as r:
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

def configure_models_and_pull(selected_model=None, pull_permission=None, interactive=False):
    console.print("\n[bold cyan]3. Model Configuration & Selection...[/bold cyan]")
    office_cfg_path = os.path.join(BASE_DIR, "aimaos_config.yaml")
    office_cfg = _load_yaml(office_cfg_path)

    current_default = office_cfg.get("llm", {}).get("default_model", "qwen3.5:4b")

    if interactive and not selected_model:
        console.print(f"Current configured default model: [bold yellow]{current_default}[/bold yellow]")
        console.print("Select default Ollama model for AIMAOS agents:")
        console.print("  [1] qwen3.5:4b (Recommended - balanced 4B reasoning)")
        console.print("  [2] qwen3.5:2b (Lightweight 2B model)")
        console.print("  [3] qwen3.5:0.8b (Ultra-fast short-turn model)")
        console.print("  [4] Custom model tag...")

        try:
            choice = input("Enter choice [1-4] (default: 1): ").strip()
            if choice == "2":
                selected_model = "qwen3.5:2b"
            elif choice == "3":
                selected_model = "qwen3.5:0.8b"
            elif choice == "4":
                selected_model = input("Enter custom Ollama model tag (e.g. llama3.1:8b): ").strip() or current_default
            else:
                selected_model = "qwen3.5:4b"
        except (KeyboardInterrupt, EOFError):
            selected_model = current_default

    chosen_model = _validated_model_tag(selected_model or current_default)

    # Update entries that inherited the old default while preserving deliberately
    # specialized assignments such as Finn's smaller short-turn model.
    llm_cfg = office_cfg.get("llm", {})
    llm_cfg["default_model"] = chosen_model
    office_cfg["llm"] = llm_cfg
    for agent_cfg in office_cfg.get("agents", {}).values():
        if isinstance(agent_cfg, dict) and agent_cfg.get("model") == current_default:
            agent_cfg["model"] = chosen_model
    _write_yaml(office_cfg_path, office_cfg)

    console.print(f"  - Default Agent Model Set To: [bold green]{chosen_model}[/bold green]")

    installed = get_installed_ollama_models(
        llm_cfg.get("ollama_host", "http://localhost:11434")
    )
    is_installed = installed is not None and (chosen_model in installed or any(m.startswith(chosen_model + ":") for m in installed))

    if is_installed:
        console.print(f"  - Model status: [bold green]INSTALLED[/bold green]")
    else:
        console.print(f"  - Model status: [bold yellow]NOT INSTALLED[/bold yellow]")

        # Ask permission to pull model if not specified via CLI
        should_pull = False
        if pull_permission is True:
            should_pull = True
        elif pull_permission is False:
            should_pull = False
        elif interactive and sys.stdin.isatty():
            try:
                ans = input(f"\n[?] Download model '{chosen_model}' via Ollama now? [y/N]: ").strip().lower()
                should_pull = ans in ["y", "yes"]
            except (KeyboardInterrupt, EOFError):
                should_pull = False

        if should_pull:
            console.print(f"\n[bold cyan]Downloading '{chosen_model}' via Ollama...[/bold cyan]")
            import subprocess
            ollama_cli = shutil.which("ollama")
            if not ollama_cli:
                console.print("[bold red]Ollama is not installed or is not on PATH.[/bold red]")
            else:
                res = subprocess.run([ollama_cli, "pull", chosen_model], check=False)
            if ollama_cli and res.returncode == 0:
                console.print(f"[bold green]Successfully pulled '{chosen_model}'.[/bold green]")
            elif ollama_cli:
                console.print(f"[bold red]Failed to pull model '{chosen_model}'. You can run 'ollama pull {chosen_model}' manually.[/bold red]")
        else:
            console.print(f"\n[bold yellow]Notice: Model auto-pull skipped.[/bold yellow] To download manually later, run:\n  [bold white]ollama pull {chosen_model}[/bold white]")

    return chosen_model

def configure_workspaces():
    console.print("\n[bold cyan]4. Configuring AIMAOS Mini-Agent Workspaces from aimaos_config.yaml...[/bold cyan]")
    base_dir = BASE_DIR

    office_cfg_path = os.path.join(base_dir, "aimaos_config.yaml")
    office_cfg = _load_yaml(office_cfg_path)
    agent_models = office_cfg.get("agents", {})
    default_model = office_cfg.get("llm", {}).get("default_model", "qwen3.5:4b")
    installed = get_installed_ollama_models(
        office_cfg.get("llm", {}).get("ollama_host", "http://localhost:11434")
    )

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
        cfg_data = _load_yaml(cfg_path)

        if "agent" not in cfg_data:
            cfg_data["agent"] = {"name": agent_name}
        cfg_data["agent"]["model"] = model
        # Shipped configs keep workspace-relative paths; stamp them absolute
        # for this machine so tools resolve them regardless of cwd.
        for key, val in list(cfg_data.get("paths", {}).items()):
            if isinstance(val, str) and not os.path.isabs(val):
                cfg_data["paths"][key] = os.path.join(apath, val)
        _write_yaml(cfg_path, cfg_data)

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
    console.print("\n[bold cyan]5. Hardware-Enforced Email Security Policy Setup...[/bold cyan]")
    office_cfg_path = os.path.join(BASE_DIR, "aimaos_config.yaml")
    
    office_cfg = _load_yaml(office_cfg_path)

    email_cfg = office_cfg.get("email", {})
    email_cfg["security_mode"] = security_mode.upper()
    if approved_recipients:
        email_cfg["approved_recipients"] = [
            _validated_email(recipient)
            for recipient in approved_recipients.split(",")
            if recipient.strip()
        ]
    elif "approved_recipients" not in email_cfg:
        email_cfg["approved_recipients"] = []  # empty until the operator whitelists real recipients

    office_cfg["email"] = email_cfg
    _write_yaml(office_cfg_path, office_cfg)

    if email_user:
        email_user = _validated_email(email_user)
        cred_path = user_config_path("credentials.env")
        os.makedirs(os.path.dirname(cred_path), exist_ok=True)
        lines = []
        if os.path.exists(cred_path):
            with open(cred_path, "r") as f:
                lines = f.readlines()
        
        updated = False
        new_lines = []
        for line in lines:
            if line.startswith("HELIX_EMAIL_USER="):
                new_lines.append(f"HELIX_EMAIL_USER={email_user}\n")
                updated = True
            else:
                new_lines.append(line)
        if not updated:
            new_lines.append(f"HELIX_EMAIL_USER={email_user}\n")

        atomic_write_text(cred_path, "".join(new_lines), mode=0o600)
        console.print(f"  - Configured Email Credentials: [bold green]{email_user}[/bold green]")

    sec_color = "green" if security_mode.upper() == "READ_ONLY" else "yellow"
    console.print(f"  - Email Security Mode: [bold {sec_color}]{security_mode.upper()}[/bold {sec_color}]")
    console.print(f"  - Approved Outbound Whitelist: [bold white]{', '.join(email_cfg.get('approved_recipients', []))}[/bold white]")

def main():
    if os.name == "posix":
        os.umask(0o077)
    parser = argparse.ArgumentParser(description="AIMAOS setup wizard")
    parser.add_argument("--pack", default=DEFAULT_PACK,
                        help=f"Starter pack to materialize (default: {DEFAULT_PACK}).")
    parser.add_argument("--force", action="store_true",
                        help="Re-materialize an agent workspace even if it exists.")
    parser.add_argument("--model", default=None,
                        help="Default Ollama model to assign (e.g. qwen3.5:4b, qwen3.5:2b, llama3.1:8b).")
    parser.add_argument("--pull-models", action="store_true", default=None,
                        help="Automatically download missing Ollama models during setup.")
    parser.add_argument("--no-pull-models", action="store_false", dest="pull_models",
                        help="Do not download missing Ollama models during setup.")
    parser.add_argument("--email-security-mode", default="READ_ONLY", choices=["READ_ONLY", "WHITELIST_ONLY", "DISABLED"],
                        help="Hardware-enforced email security policy mode (default: READ_ONLY).")
    parser.add_argument("--approved-recipients", default=None,
                        help="Comma-separated whitelist of approved outbound email recipients.")
    parser.add_argument("--email-user", default=None,
                        help="Optional company email address.")
    args = parser.parse_args()

    is_interactive = sys.stdin.isatty()

    console.print(Panel("[bold cyan]AIMAOS SETUP WIZARD[/bold cyan]\nModel-Agnostic Multi-Agent Operating System Configurator", border_style="cyan"))
    run_diagnostics()
    try:
        # Validate CLI-provided values before materializing or changing anything.
        if args.model:
            _validated_model_tag(args.model)
        if args.email_user:
            _validated_email(args.email_user)
        if args.approved_recipients:
            for recipient in args.approved_recipients.split(","):
                if recipient.strip():
                    _validated_email(recipient)
        materialize_pack(args.pack, force=args.force)
        configure_models_and_pull(
            selected_model=args.model,
            pull_permission=args.pull_models,
            interactive=is_interactive,
        )
        configure_workspaces()
        configure_email_security(args.email_security_mode, args.approved_recipients, args.email_user)
    except ValueError as exc:
        parser.error(str(exc))
    console.print("\n[bold green]SUCCESS: AIMAOS Model-Agnostic Setup Completed![/bold green]")
    console.print(
        f"Run [bold yellow]{launch_command('aimaos_ui.py')}[/bold yellow] (dashboard) or "
        f"[bold yellow]{launch_command('run_office.py')}[/bold yellow] (autonomous daemon)."
    )

if __name__ == "__main__":
    main()
