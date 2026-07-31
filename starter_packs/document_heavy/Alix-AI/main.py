import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

sys.path.insert(0, AIMAOS_ROOT)
sys.path.insert(0, os.path.join(AIMAOS_ROOT, "Alix-AI"))
from core.llm import LLMClient
from core.tools import ToolRegistry
from business.agent import Agent

console = Console()

def load_config():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(project_dir, "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            try:
                return yaml.safe_load(f)
            except Exception as e:
                console.print(f"[bold red]Error parsing config.yaml:[/bold red] {e}")
                sys.exit(1)
    else:
        # Default configuration
        return {
            "llm": {
                "backend": "ollama",
                "model": "gemma3:2b",
                "ollama_host": "http://localhost:11434",
                "llamacpp_host": "http://localhost:8080",
                "temperature": 0.1,
                "max_tokens": 4096
            },
            "paths": {
                "templates": "./templates",
                "skills": "./skills",
                "inbox": "./workspace/inbox",
                "output": "./workspace/output",
                "sessions": "./workspace/.sessions"
            },
            "default_output_format": "docx"
        }

def show_welcome(config, agent):
    templates_str, skills_str = agent._get_dynamic_context()
    
    # Count templates and skills
    t_count = len(templates_str.split("\n")) if templates_str != "None available yet." else 0
    s_count = len(skills_str.split("\n")) if skills_str != "None available yet." else 0
    p_count = len(agent.prod_memory.get_preferences())
    h_count = len(agent.prod_memory.get_production_history(limit=100))
    
    llm_conf = config.get("llm", {})
    backend = llm_conf.get("backend", "ollama")
    model = llm_conf.get("model", "gemma3:2b")
    
    panel_content = (
        f"[bold blue]LLM Backend:[/bold blue] {backend.upper()} | [bold blue]Model:[/bold blue] {model}\n"
        f"[bold blue]Active Workspace Paths:[/bold blue]\n"
        f"  • Inbox:     {agent.inbox_dir}\n"
        f"  • Output:    {agent.output_dir}\n"
        f"  • Templates: {agent.templates_dir} ({t_count} active)\n"
        f"  • Skills:    {agent.skills_dir} ({s_count} active)\n"
        f"  • Memory:    {agent.memory_dir} ({p_count} rules, {h_count} logged productions)\n\n"
        f"Type your request (e.g. 'can you make a will form for Bob Client...') or use one of the slash commands:\n"
        f"  [bold cyan]/templates[/bold cyan] - List all available templates\n"
        f"  [bold cyan]/skills[/bold cyan]    - List all custom skills\n"
        f"  [bold cyan]/memory[/bold cyan]    - View persistent preferences, mRAG facts & audit logs\n"
        f"  [bold cyan]/clear[/bold cyan]     - Clear conversation session history\n"
        f"  [bold cyan]/exit[/bold cyan]      - Quit Alix-AI"
    )
    
    console.print(Panel(panel_content, title="🔷 Alix-AI Document Maker & Keeper Agent (mRAG Enhanced)", border_style="blue"))

def console_callback(event_type, data):
    if event_type == "agent_start_thinking":
        console.print(f"\n[bold yellow]🤔 Agent Thinking (Turn {data['turn']})...[/bold yellow]")
    elif event_type == "tool_start":
        args_formatted = ", ".join(f"{k}={repr(v)}" for k, v in data["arguments"].items())
        console.print(f"⚙️  [bold cyan]Running tool:[/bold cyan] [underline]{data['name']}[/underline]({args_formatted})")
    elif event_type == "tool_end":
        res = str(data["result"])
        if len(res) > 200:
            display_res = res[:200] + "\n... [truncated]"
        else:
            display_res = res
        console.print(f"✅ [bold green]Tool Result:[/bold green]\n{display_res}")
    elif event_type == "agent_error":
        console.print(f"[bold red]❌ Error:[/bold red] {data['message']}")

def main():
    config = load_config()
    
    paths = config.get("paths", {})
    tools_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
    registry = ToolRegistry(tools_dir)
    
    llm_client = LLMClient(config)
    
    console.print("[bold yellow]Connecting to local LLM backend...[/bold yellow]")
    ok, msg = llm_client.check_availability()
    if not ok:
        console.print(Panel(
            f"[bold red]Connection Failed![/bold red]\n\n"
            f"{msg}\n\n"
            f"[bold yellow]Troubleshooting Checklist:[/bold yellow]\n"
            f"1. Is Ollama running? (Try running `ollama serve` in a terminal)\n"
            f"2. Has the model been downloaded? (Run `ollama pull {llm_client.model}`)\n"
            f"3. If using llama.cpp, is the server running on port 8080?",
            title="System Alert",
            border_style="red"
        ))
        sys.exit(1)
        
    console.print(f"[bold green]✔[/bold green] {msg}")
    
    agent = Agent(config, llm_client, registry)
    
    show_welcome(config, agent)
    
    while True:
        try:
            user_input = console.input("\n[bold blue]You:[/bold blue] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold yellow]Goodbye![/bold yellow]")
            if hasattr(agent, "watcher") and agent.watcher:
                agent.watcher.stop()
            break
            
        if not user_input:
            continue
            
        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]
            if cmd in ["/exit", "/quit"]:
                console.print("[bold yellow]Goodbye![/bold yellow]")
                if hasattr(agent, "watcher") and agent.watcher:
                    agent.watcher.stop()
                break
            elif cmd == "/templates":
                templates_str, _ = agent._get_dynamic_context()
                console.print(Panel(templates_str, title="Available Templates", border_style="cyan"))
            elif cmd == "/skills":
                _, skills_str = agent._get_dynamic_context()
                console.print(Panel(skills_str, title="Available Skills", border_style="cyan"))
            elif cmd == "/memory":
                memory_summary = agent.prod_memory.get_system_prompt_summary()
                console.print(Panel(memory_summary, title="Persistent Document Production Memory", border_style="magenta"))
            elif cmd == "/clear":
                agent.memory.clear()
                console.print("[bold green]Conversation history cleared.[/bold green]")
            elif cmd == "/review":
                console.print("[bold yellow]Invoking Template Reviewer Subagent...[/bold yellow]")
                res = agent.tools.execute_tool("review_templates", {"action": "process_pending"})
                console.print(Panel(res, title="Template Reviewer Subagent Output", border_style="cyan"))
            elif cmd in ["/help", "/h"]:
                console.print(
                    "[bold cyan]Available Commands:[/bold cyan]\n"
                    "  /templates - List all templates\n"
                    "  /skills    - List all skills\n"
                    "  /review    - Run background Template Reviewer subagent\n"
                    "  /memory    - View persistent preferences, mRAG facts & audit logs\n"
                    "  /clear     - Clear session history\n"
                    "  /exit      - Quit the program"
                )
            else:
                console.print(f"[bold red]Unknown command:[/bold red] {cmd}")
            continue
            
        response = agent.process_input(user_input, console_callback=console_callback)
        console.print(Panel(response, title="Alix-AI Response", border_style="green"))

if __name__ == "__main__":
    main()
