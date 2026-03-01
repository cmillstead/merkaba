# src/merkaba/cli.py
import json
import os
from datetime import datetime

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from merkaba import __version__

# Heavy modules imported lazily inside commands to avoid import-time failures
# (e.g., ollama SOCKS proxy error) and speed up CLI startup.

CLAUDE_PLUGIN_DIR = os.path.expanduser("~/.claude/plugins/cache")
MERKABA_DIR = os.path.expanduser("~/.merkaba")


def _load_adapters():
    """Import adapter modules to trigger registration."""
    import merkaba.integrations.email_adapter  # noqa: F401
    import merkaba.integrations.stripe_adapter  # noqa: F401


app = typer.Typer(
    name="merkaba",
    help="Local AI agent framework -- build autonomous agents with persistent memory",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"merkaba version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """Merkaba - Local AI Agent Framework"""
    try:
        from merkaba.observability.tracing import setup_logging
        setup_logging()
    except Exception:
        pass


@app.command()
def chat(
    message: str = typer.Argument(None, help="Message to send to Merkaba"),
    model: str = typer.Option("qwen3.5:122b", "--model", "-m", help="LLM model to use"),
):
    """Start a conversation with Merkaba."""
    from merkaba.agent import Agent
    agent = Agent(model=model)

    if message:
        console.print(f"[bold blue]You:[/] {message}")
        try:
            with console.status("[bold green]Merkaba is thinking..."):
                response = agent.run(message)
            console.print(f"[bold green]Merkaba:[/]")
            console.print(Markdown(response))
        except Exception as e:
            console.print(f"[bold red]Error:[/] {e}")
    else:
        # Interactive mode
        console.print("[bold green]Merkaba[/] at your service. Type 'exit' to quit.\n")
        while True:
            try:
                user_input = console.input("[bold blue]You:[/] ")
                if user_input.lower() in ("exit", "quit", "bye"):
                    console.print("[bold green]Merkaba:[/] Goodbye!")
                    break
                try:
                    with console.status("[bold green]Merkaba is thinking..."):
                        response = agent.run(user_input)
                    console.print(f"[bold green]Merkaba:[/]")
                    console.print(Markdown(response))
                    console.print()
                except Exception as e:
                    console.print(f"[bold red]Error:[/] {e}")
                    console.print()  # continue the loop
            except KeyboardInterrupt:
                console.print("\n[bold green]Merkaba:[/] Goodbye!")
                break


# --- Telegram Command Group ---

telegram_app = typer.Typer(help="Telegram bot commands")
app.add_typer(telegram_app, name="telegram")


@telegram_app.command("setup")
def telegram_setup():
    """Configure Telegram bot integration."""
    from merkaba.telegram import TelegramConfig
    config = TelegramConfig()

    console.print("[bold]Telegram Bot Setup[/bold]\n")
    console.print("1. Create a bot via @BotFather on Telegram")
    console.print("2. Copy the bot token")
    console.print("3. Get your user ID via @userinfobot\n")

    bot_token = typer.prompt("Enter your bot token")
    config.save_bot_token(bot_token)

    user_id_str = typer.prompt("Enter your Telegram user ID")
    try:
        user_id = int(user_id_str)
        config.save_allowed_user_ids([user_id])
    except ValueError:
        console.print("[red]Invalid user ID - must be a number[/red]")
        raise typer.Exit(1)

    console.print("\n[green]Telegram configured![/green]")
    console.print("Start the bot with: [bold]merkaba serve[/bold]")


@telegram_app.command("status")
def telegram_status():
    """Check Telegram bot configuration status."""
    from merkaba.telegram import TelegramConfig
    config = TelegramConfig()

    if not config.is_configured():
        console.print("[yellow]Telegram not configured[/yellow]")
        console.print("Run [bold]merkaba telegram setup[/bold] to configure")
        return

    console.print("[green]Telegram configured[/green]")
    user_ids = config.get_allowed_user_ids()
    console.print(f"Allowed users: {user_ids}")


@app.command("web")
def web(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(5173, "--port", "-p", help="Port to listen on"),
):
    """Start Mission Control web interface."""
    import uvicorn
    from merkaba.web.app import create_app
    console.print(f"[bold green]Starting Mission Control...[/bold green]")
    console.print(f"Open [bold]http://{host}:{port}[/bold] in your browser")
    console.print("Press Ctrl+C to stop\n")
    uvicorn.run(create_app(), host=host, port=port)


@app.command("serve")
def serve():
    """Start Merkaba with Telegram bot integration."""
    from merkaba.telegram import TelegramConfig, MerkabaBot
    config = TelegramConfig()

    if not config.is_configured():
        console.print("[red]Telegram not configured[/red]")
        console.print("Run [bold]merkaba telegram setup[/bold] first")
        raise typer.Exit(1)

    token = config.get_bot_token()
    allowed_users = config.get_allowed_user_ids()

    console.print("[bold green]Starting Merkaba...[/bold green]")
    console.print(f"Allowed users: {allowed_users}")
    console.print("Press Ctrl+C to stop\n")

    bot = MerkabaBot(token=token, allowed_user_ids=allowed_users)

    try:
        bot.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")


# --- Plugin Command Group ---

plugins_app = typer.Typer(help="Plugin management commands")
app.add_typer(plugins_app, name="plugins")


@plugins_app.command("list")
def plugins_list():
    """List installed plugins and their components."""
    from merkaba.plugins import PluginRegistry
    registry = PluginRegistry.default()

    skills = registry.skills.list_skills()
    commands = registry.commands.list_commands()
    agents = registry.agents.list_agents()
    hooks = registry.hooks.hooks

    console.print("[bold]Installed Plugin Components[/bold]\n")

    if skills:
        console.print("[cyan]Skills:[/cyan]")
        for name in skills:
            skill = registry.skills.get(name)
            if skill and skill.manifest:
                m = skill.manifest
                tools_str = ", ".join(m.required_tools) if m.required_tools else "none"
                console.print(f"  - {name} [dim](sandboxed: tools=[{tools_str}], tier={m.permission_tier})[/dim]")
            else:
                console.print(f"  - {name} [dim](unrestricted)[/dim]")
    else:
        console.print("[dim]No skills loaded[/dim]")

    console.print()

    if commands:
        console.print("[cyan]Commands:[/cyan]")
        for name in commands:
            console.print(f"  - /{name}")
    else:
        console.print("[dim]No commands loaded[/dim]")

    console.print()

    if agents:
        console.print("[cyan]Agents:[/cyan]")
        for name in agents:
            console.print(f"  - {name}")
    else:
        console.print("[dim]No agents loaded[/dim]")

    console.print()

    if hooks:
        console.print("[cyan]Hooks:[/cyan]")
        for hook in hooks:
            console.print(f"  - {hook.name} ({hook.event.value})")
    else:
        console.print("[dim]No hooks loaded[/dim]")


@plugins_app.command("inspect")
def plugins_inspect(
    name: str = typer.Argument(..., help="Skill name to inspect"),
):
    """Show detailed manifest and metadata for a skill."""
    from merkaba.plugins import PluginRegistry

    registry = PluginRegistry.default()
    skill = registry.skills.get(name)
    if not skill:
        console.print(f"[red]Skill '{name}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]{skill.name}[/bold]")
    console.print(f"  Plugin: {skill.plugin_name or '(none)'}")
    console.print(f"  Description: {skill.description or '(none)'}")

    if skill.warnings:
        console.print(f"  [yellow]Warnings: {len(skill.warnings)}[/yellow]")
        for w in skill.warnings:
            console.print(f"    - {w}")

    if skill.manifest:
        m = skill.manifest
        console.print()
        console.print("[cyan]Manifest (sandboxed):[/cyan]")
        console.print(f"  Version: {m.version}")
        console.print(f"  Permission tier: {m.permission_tier}")
        console.print(f"  Max context tokens: {m.max_context_tokens}")
        console.print(f"  Required tools: {m.required_tools or '(none)'}")
        console.print(f"  Required integrations: {m.required_integrations or '(none)'}")
        console.print(f"  File access patterns: {m.file_access or '(none)'}")
    else:
        console.print()
        console.print("[dim]No manifest -- unrestricted tool access[/dim]")


@plugins_app.command("import")
def plugins_import(
    skill_ref: str = typer.Argument(..., help="Skill to import (plugin:skill or plugin)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force import low-compatibility skills"),
):
    """Import a Claude Code plugin skill."""
    from merkaba.plugins.importer import PluginImporter
    source_dirs = [
        os.path.expanduser("~/.claude/plugins/cache"),
    ]
    dest_dir = os.path.expanduser("~/.merkaba/plugins")

    importer = PluginImporter(source_dirs=source_dirs, dest_dir=dest_dir)

    # Parse skill reference
    if ":" in skill_ref:
        plugin_name, skill_name = skill_ref.split(":", 1)
    else:
        plugin_name = skill_ref
        skill_name = None

    if skill_name:
        # Import single skill
        result = importer.import_skill(plugin_name, skill_name, force=force)
        _print_import_result(result)
    else:
        # Import all skills from plugin
        console.print(f"[yellow]Importing all skills from {plugin_name}...[/yellow]")
        console.print("[dim]TODO: Implement bulk import[/dim]")


def _print_import_result(result):
    """Print import result to console."""
    if result.success:
        console.print(f"[green]v[/green] {result.skill_name} ({result.compatibility}% compatible, {result.conversion})")
    elif result.skipped:
        console.print(f"[yellow]o[/yellow] {result.skill_name} skipped ({result.compatibility}% compatible)")
        if result.missing_tools:
            console.print(f"  Missing: {', '.join(result.missing_tools)}")
    else:
        console.print(f"[red]x[/red] {result.skill_name}: {result.error}")


@plugins_app.command("available")
def plugins_available():
    """List available Claude Code plugins that can be imported."""
    from pathlib import Path

    plugin_dir = Path(CLAUDE_PLUGIN_DIR)

    if not plugin_dir.exists():
        console.print("[yellow]No Claude Code plugins found.[/yellow]")
        return

    console.print("[bold]Available Claude Code plugins:[/bold]\n")

    # Structure: cache/org/plugin/version/skills/skill-name/
    for org_path in sorted(plugin_dir.iterdir()):
        if not org_path.is_dir():
            continue

        for plugin_path in sorted(org_path.iterdir()):
            if not plugin_path.is_dir():
                continue

            # Find version directories and look for skills
            for version_path in sorted(plugin_path.iterdir(), reverse=True):
                if not version_path.is_dir():
                    continue

                skills_dir = version_path / "skills"
                if not skills_dir.exists():
                    continue

                plugin_name = plugin_path.name
                skills = [s.name for s in skills_dir.iterdir() if s.is_dir()]

                if skills:
                    console.print(f"[cyan]{plugin_name}[/cyan] ({version_path.name})")
                    for skill in sorted(skills):
                        console.print(f"  - {skill}")
                    console.print()
                break  # Only show latest version


@plugins_app.command("uninstall")
def plugins_uninstall(
    name: str = typer.Argument(..., help="Plugin/skill name to uninstall"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Uninstall a plugin by removing all its files from Claude Code and Merkaba."""
    from merkaba.plugins.uninstaller import PluginUninstaller

    uninstaller = PluginUninstaller()
    targets = uninstaller.scan(name)

    if not targets:
        console.print(f"[yellow]No files found for '{name}'.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Found {len(targets)} item(s) for '{name}':[/bold]\n")

    table = Table()
    table.add_column("Category", style="cyan")
    table.add_column("Description")
    table.add_column("Path", style="dim")

    for t in targets:
        table.add_row(t.category, t.description, t.path)

    console.print(table)
    console.print()

    if not yes:
        confirm = typer.confirm("Remove all of the above?")
        if not confirm:
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    result = uninstaller.uninstall(name, targets)

    console.print(f"\n[green]Removed {len(result.targets_removed)} item(s).[/green]")
    if result.settings_cleaned:
        console.print("[green]Cleaned settings.json enabledPlugins.[/green]")
    console.print("\n[dim]Restart Claude Code for changes to take effect.[/dim]")


# --- Commands Command Group ---

commands_app = typer.Typer(help="Plugin command management")
app.add_typer(commands_app, name="commands")


@commands_app.command("list")
def commands_list():
    """List available plugin commands."""
    from merkaba.plugins import PluginRegistry
    registry = PluginRegistry.default()
    commands = registry.commands.list_commands()

    if not commands:
        console.print("[dim]No commands available[/dim]")
        return

    console.print("[bold]Available Commands[/bold]\n")
    for name in commands:
        cmd = registry.commands.get(name)
        console.print(f"  /{name} - {cmd.description}")


# --- Memory Command Group ---

memory_app = typer.Typer(help="Memory management commands")
app.add_typer(memory_app, name="memory")


@memory_app.command("status")
def memory_status():
    """Show memory statistics."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        counts = store.stats()
    finally:
        store.close()

    console.print("[bold]Memory Status[/bold]\n")

    table = Table()
    table.add_column("Category", style="cyan")
    table.add_column("Count", justify="right")

    for name, count in counts.items():
        table.add_row(name.capitalize(), str(count))

    console.print(table)


@memory_app.command("businesses")
def memory_businesses():
    """List registered businesses."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        businesses = store.list_businesses()
    finally:
        store.close()

    if not businesses:
        console.print("[dim]No businesses registered yet.[/dim]")
        return

    table = Table(title="Registered Businesses")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("Autonomy", justify="right")
    table.add_column("Created", style="dim")

    for biz in businesses:
        created = biz["created_at"]
        if "T" in created:
            created = created.split("T")[0]
        table.add_row(
            str(biz["id"]),
            biz["name"],
            biz["type"],
            str(biz["autonomy_level"]),
            created,
        )

    console.print(table)


@memory_app.command("recall")
def memory_recall(
    query: str = typer.Argument(..., help="What to search for"),
    business_id: int = typer.Option(None, "--business", "-b", help="Filter by business ID"),
    limit: int = typer.Option(5, "--limit", "-l", help="Max results"),
):
    """Semantic search: what does Merkaba know about a topic?"""
    from merkaba.memory.store import MemoryStore
    from merkaba.memory.retrieval import MemoryRetrieval

    store = MemoryStore()
    vectors = None
    try:
        from merkaba.memory.vectors import VectorMemory
        vectors = VectorMemory()
    except (ImportError, Exception):
        pass

    retrieval = MemoryRetrieval(store=store, vectors=vectors)
    try:
        summary = retrieval.what_do_i_know(query, business_id)
        console.print(summary)
    finally:
        retrieval.close()


@memory_app.command("decay")
def memory_decay():
    """Run memory decay: reduce relevance of stale memories and archive low-score items."""
    from merkaba.memory.store import MemoryStore
    from merkaba.memory.lifecycle import MemoryDecayJob

    store = MemoryStore()
    try:
        job = MemoryDecayJob(store=store)
        stats = job.run()
        console.print(f"[bold]Decay complete:[/bold] {stats['decayed']} decayed, {stats['archived']} archived")
    finally:
        store.close()


@memory_app.command("archived")
def memory_archived(
    table: str = typer.Argument("facts", help="Table to list (facts, decisions, learnings)"),
    business_id: int = typer.Option(None, "--business", "-b", help="Filter by business ID"),
):
    """List archived memory items."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        items = store.list_archived(table, business_id=business_id)
    finally:
        store.close()

    if not items:
        console.print(f"[dim]No archived {table}.[/dim]")
        return

    tbl = Table(title=f"Archived {table.capitalize()}")
    tbl.add_column("ID", style="cyan", justify="right")
    tbl.add_column("Score", justify="right")
    if table == "facts":
        tbl.add_column("Category")
        tbl.add_column("Key")
        tbl.add_column("Value")
        for item in items:
            tbl.add_row(str(item["id"]), f"{item.get('relevance_score', 0):.2f}",
                        item.get("category", ""), item.get("key", ""), item.get("value", "")[:60])
    elif table == "decisions":
        tbl.add_column("Action")
        tbl.add_column("Decision")
        for item in items:
            tbl.add_row(str(item["id"]), f"{item.get('relevance_score', 0):.2f}",
                        item.get("action_type", ""), item.get("decision", "")[:60])
    elif table == "learnings":
        tbl.add_column("Category")
        tbl.add_column("Insight")
        for item in items:
            tbl.add_row(str(item["id"]), f"{item.get('relevance_score', 0):.2f}",
                        item.get("category", ""), item.get("insight", "")[:60])

    console.print(tbl)


@memory_app.command("unarchive")
def memory_unarchive(
    table: str = typer.Argument(..., help="Table (facts, decisions, learnings)"),
    item_id: int = typer.Argument(..., help="ID of the item to unarchive"),
):
    """Restore an archived memory item."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        store.unarchive(table, item_id)
    finally:
        store.close()
    console.print(f"[green]Unarchived {table} #{item_id}[/green]")


@memory_app.command("episodes")
def memory_episodes(
    episode_id: int = typer.Argument(None, help="Show detail for a specific episode"),
    business: int = typer.Option(None, "--business", "-b", help="Filter by business ID"),
    task_type: str = typer.Option(None, "--type", "-t", help="Filter by task type"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results"),
):
    """List recent episodes or show episode detail."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        if episode_id is not None:
            ep = store.get_episode(episode_id)
            if not ep:
                console.print(f"[red]Episode #{episode_id} not found.[/red]")
                return
            console.print(f"[bold]Episode #{ep['id']}[/bold]\n")
            console.print(f"  Business ID: {ep['business_id']}")
            console.print(f"  Task Type:   {ep['task_type']}")
            console.print(f"  Task ID:     {ep['task_id']}")
            console.print(f"  Outcome:     {ep['outcome']}")
            console.print(f"  Created:     {ep['created_at']}")
            if ep.get("duration_seconds"):
                console.print(f"  Duration:    {ep['duration_seconds']}s")
            console.print(f"\n[bold]Summary:[/bold] {ep['summary']}")
            if ep.get("outcome_details"):
                console.print(f"\n[bold]Details:[/bold] {ep['outcome_details']}")
            if ep.get("key_decisions"):
                console.print("\n[bold]Key Decisions:[/bold]")
                for d in ep["key_decisions"]:
                    console.print(f"  - {d}")
            if ep.get("tags"):
                console.print(f"\n[bold]Tags:[/bold] {', '.join(ep['tags'])}")
            return

        episodes = store.get_episodes(business_id=business, task_type=task_type, limit=limit)
    finally:
        store.close()

    if not episodes:
        console.print("[dim]No episodes recorded yet.[/dim]")
        return

    table = Table(title="Recent Episodes")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Business", justify="right")
    table.add_column("Type", style="yellow")
    table.add_column("Outcome", style="green")
    table.add_column("Summary")
    table.add_column("Created", style="dim")

    for ep in episodes:
        summary = (ep.get("summary") or "")[:60]
        created = (ep.get("created_at") or "").split("T")[0] if "T" in (ep.get("created_at") or "") else ep.get("created_at", "")
        outcome_style = "green" if ep["outcome"] == "success" else "red"
        table.add_row(
            str(ep["id"]),
            str(ep.get("business_id", "")),
            ep.get("task_type", ""),
            f"[{outcome_style}]{ep['outcome']}[/{outcome_style}]",
            summary,
            created,
        )

    console.print(table)


@memory_app.command("consolidate")
def memory_consolidate():
    """Consolidate related facts into summaries using LLM."""
    from merkaba.memory.store import MemoryStore
    from merkaba.memory.lifecycle import MemoryConsolidationJob
    from merkaba.llm import LLMClient

    store = MemoryStore()
    llm = LLMClient()
    try:
        job = MemoryConsolidationJob(store=store, llm=llm)
        stats = job.run()
        console.print(
            f"[bold]Consolidation complete:[/bold] "
            f"{stats['groups']} groups, {stats['summaries']} summaries, {stats['archived']} archived"
        )
    finally:
        store.close()


# --- Scheduler Command Group ---

scheduler_app = typer.Typer(help="Task scheduler commands")
app.add_typer(scheduler_app, name="scheduler")


@scheduler_app.command("run")
def scheduler_run():
    """Run one scheduler tick (check and execute due tasks)."""
    from merkaba.orchestration.queue import TaskQueue
    from merkaba.orchestration.scheduler import Scheduler
    from merkaba.orchestration.supervisor import Supervisor
    from merkaba.memory.store import MemoryStore
    from merkaba.approval.queue import ActionQueue

    queue = TaskQueue()
    memory = MemoryStore()
    action_queue = ActionQueue()

    def handle_approval(action: dict):
        action_queue.add_action(
            business_id=action.get("business_id") or 0,
            action_type=action.get("action", "unknown"),
            description=action.get("description", str(action)),
            params=action,
            autonomy_level=action.get("autonomy_level", 1),
        )

    supervisor = Supervisor(memory_store=memory, on_needs_approval=handle_approval)
    scheduler = Scheduler(queue=queue, on_task_due=supervisor.handle_task)
    try:
        due = scheduler.tick()
        if due:
            console.print(f"[green]Processed {len(due)} due tasks[/green]")
            for task in due:
                console.print(f"  - {task['name']} (id={task['id']})")
        else:
            console.print("[dim]No due tasks[/dim]")
    finally:
        queue.close()
        action_queue.close()
        supervisor.close()


@scheduler_app.command("start")
def scheduler_start(
    interval: int = typer.Option(60, "--interval", "-i", help="Seconds between ticks"),
):
    """Run the scheduler loop (foreground)."""
    from merkaba.orchestration.queue import TaskQueue
    from merkaba.orchestration.scheduler import Scheduler
    from merkaba.orchestration.supervisor import Supervisor
    from merkaba.memory.store import MemoryStore
    from merkaba.approval.queue import ActionQueue

    queue = TaskQueue()
    memory = MemoryStore()
    action_queue = ActionQueue()

    def handle_approval(action: dict):
        action_queue.add_action(
            business_id=action.get("business_id") or 0,
            action_type=action.get("action", "unknown"),
            description=action.get("description", str(action)),
            params=action,
            autonomy_level=action.get("autonomy_level", 1),
        )

    supervisor = Supervisor(memory_store=memory, on_needs_approval=handle_approval)
    scheduler = Scheduler(queue=queue, on_task_due=supervisor.handle_task)

    console.print(f"[bold green]Scheduler starting[/bold green] (interval={interval}s)")
    console.print("Press Ctrl+C to stop\n")

    try:
        scheduler.run_loop(interval=interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler stopped[/yellow]")
    finally:
        queue.close()
        action_queue.close()
        supervisor.close()


@scheduler_app.command("workers")
def scheduler_workers():
    """List registered task workers."""
    from merkaba.orchestration.workers import WORKER_REGISTRY

    if not WORKER_REGISTRY:
        console.print("[dim]No workers registered[/dim]")
        return

    table = Table(title="Registered Workers")
    table.add_column("Task Type", style="cyan")
    table.add_column("Worker Class", style="green")
    for task_type, worker_class in sorted(WORKER_REGISTRY.items()):
        table.add_row(task_type, worker_class.__name__)
    console.print(table)


@scheduler_app.command("install")
def scheduler_install():
    """Install launchd plist for automatic scheduling."""
    import shutil
    import subprocess
    import sys

    # Resolve through pyenv shims to get the real binary path (launchd lacks shell env)
    merkaba_path = shutil.which("merkaba") or sys.executable
    if ".pyenv/shims" in merkaba_path:
        real = subprocess.run(
            ["pyenv", "which", "merkaba"], capture_output=True, text=True
        )
        if real.returncode == 0 and real.stdout.strip():
            merkaba_path = real.stdout.strip()
    log_dir = os.path.expanduser("~/.merkaba/logs")
    os.makedirs(log_dir, exist_ok=True)

    plist_content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        "    <string>com.merkaba.scheduler</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"        <string>{merkaba_path}</string>\n"
        "        <string>scheduler</string>\n"
        "        <string>run</string>\n"
        "    </array>\n"
        "    <key>StartInterval</key>\n"
        "    <integer>60</integer>\n"
        "    <key>StandardOutPath</key>\n"
        f"    <string>{log_dir}/scheduler.log</string>\n"
        "    <key>StandardErrorPath</key>\n"
        f"    <string>{log_dir}/scheduler-error.log</string>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "</dict>\n"
        "</plist>"
    )

    plist_path = os.path.expanduser(
        "~/Library/LaunchAgents/com.merkaba.scheduler.plist"
    )
    os.makedirs(os.path.dirname(plist_path), exist_ok=True)

    with open(plist_path, "w") as f:
        f.write(plist_content)

    subprocess.run(["launchctl", "load", plist_path], check=True)
    console.print(f"[green]Installed and loaded:[/green] {plist_path}")
    console.print(f"Logs: {log_dir}/scheduler.log")


@scheduler_app.command("remove")
def scheduler_remove():
    """Remove launchd plist."""
    import subprocess

    plist_path = os.path.expanduser(
        "~/Library/LaunchAgents/com.merkaba.scheduler.plist"
    )

    if not os.path.exists(plist_path):
        console.print("[yellow]Plist not installed[/yellow]")
        return

    subprocess.run(["launchctl", "unload", plist_path], check=False)
    os.remove(plist_path)
    console.print(f"[green]Removed:[/green] {plist_path}")


# --- Approval Command Group ---

approval_app = typer.Typer(help="Approval workflow commands")
app.add_typer(approval_app, name="approval")


@approval_app.command("list")
def approval_list(
    status: str = typer.Option(None, "--status", "-s", help="Filter by status"),
    business_id: int = typer.Option(None, "--business", "-b", help="Filter by business"),
):
    """List pending and recent actions."""
    from merkaba.approval.queue import ActionQueue

    queue = ActionQueue()
    try:
        actions = queue.list_actions(status=status, business_id=business_id)
    finally:
        queue.close()

    if not actions:
        console.print("[dim]No actions found[/dim]")
        return

    table = Table(title="Actions")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Type", style="white")
    table.add_column("Description")
    table.add_column("Level", justify="right")
    table.add_column("Status", style="yellow")
    table.add_column("Created", style="dim")

    for a in actions:
        created = a["created_at"]
        if "T" in created:
            created = created.split("T")[0]
        table.add_row(
            str(a["id"]),
            a["action_type"],
            a["description"][:50],
            str(a["autonomy_level"]),
            a["status"],
            created,
        )

    console.print(table)


@approval_app.command("approve")
def approval_approve(
    action_id: int = typer.Argument(..., help="Action ID to approve"),
):
    """Approve a pending action."""
    from merkaba.approval.queue import ActionQueue
    from merkaba.approval.graduation import GraduationChecker

    queue = ActionQueue()
    try:
        result = queue.decide(action_id, approved=True, decided_by="cli")
        if result:
            console.print(f"[green]Approved action #{action_id}[/green]: {result['action_type']}")
            checker = GraduationChecker(action_queue=queue)
            suggestion = checker.check(result["business_id"], result["action_type"])
            if suggestion:
                console.print(f"[bold magenta]Graduation suggestion:[/bold magenta] {suggestion['suggestion']}")
        else:
            console.print(f"[red]Cannot approve action #{action_id}[/red] (not found or not pending)")
    finally:
        queue.close()


@approval_app.command("deny")
def approval_deny(
    action_id: int = typer.Argument(..., help="Action ID to deny"),
):
    """Deny a pending action."""
    from merkaba.approval.queue import ActionQueue

    queue = ActionQueue()
    try:
        result = queue.decide(action_id, approved=False, decided_by="cli")
        if result:
            console.print(f"[yellow]Denied action #{action_id}[/yellow]: {result['action_type']}")
        else:
            console.print(f"[red]Cannot deny action #{action_id}[/red] (not found or not pending)")
    finally:
        queue.close()


@approval_app.command("stats")
def approval_stats():
    """Show approval queue statistics."""
    from merkaba.approval.queue import ActionQueue

    queue = ActionQueue()
    try:
        counts = queue.stats()
    finally:
        queue.close()

    table = Table(title="Approval Queue")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")
    for name, count in counts.items():
        table.add_row(name.replace("_", " ").title(), str(count))
    console.print(table)


@approval_app.command("graduation")
def approval_graduation(
    business_id: int = typer.Argument(..., help="Business ID to check"),
):
    """Check which action types are ready for autonomy promotion."""
    from merkaba.approval.queue import ActionQueue
    from merkaba.approval.graduation import GraduationChecker

    queue = ActionQueue()
    try:
        checker = GraduationChecker(action_queue=queue)
        suggestions = checker.check_all(business_id)
    finally:
        queue.close()

    if not suggestions:
        console.print("[dim]No action types ready for promotion[/dim]")
        return

    for s in suggestions:
        console.print(f"[magenta]{s['suggestion']}[/magenta]")


# --- Tasks Command Group ---

tasks_app = typer.Typer(help="Task management commands")
app.add_typer(tasks_app, name="tasks")


@tasks_app.command("list")
def tasks_list(
    status_filter: str = typer.Option(None, "--status", "-s", help="Filter by status"),
    business_id: int = typer.Option(None, "--business", "-b", help="Filter by business ID"),
):
    """List all tasks."""
    from merkaba.orchestration.queue import TaskQueue

    queue = TaskQueue()
    try:
        tasks = queue.list_tasks(status=status_filter, business_id=business_id)
    finally:
        queue.close()

    if not tasks:
        console.print("[dim]No tasks found[/dim]")
        return

    table = Table(title="Tasks")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run", style="dim")

    for task in tasks:
        status = task["status"]
        status_colors = {
            "pending": "green",
            "running": "blue",
            "paused": "yellow",
            "failed": "red",
        }
        status_style = status_colors.get(status, "white")

        table.add_row(
            str(task["id"]),
            task["name"],
            task["task_type"],
            task["schedule"] or "-",
            f"[{status_style}]{status}[/{status_style}]",
            (task["next_run"] or "-")[:19],
        )

    console.print(table)


@tasks_app.command("add")
def tasks_add(
    name: str = typer.Option(..., "--name", "-n", help="Task name"),
    task_type: str = typer.Option(..., "--type", "-t", help="Task type"),
    schedule: str = typer.Option(None, "--schedule", "-s", help="Cron schedule"),
    business_id: int = typer.Option(None, "--business", "-b", help="Business ID"),
    autonomy_level: int = typer.Option(1, "--autonomy", "-a", help="Autonomy level (1-5)"),
):
    """Add a new task."""
    from merkaba.orchestration.queue import TaskQueue

    queue = TaskQueue()
    try:
        task_id = queue.add_task(
            name=name,
            task_type=task_type,
            schedule=schedule,
            business_id=business_id,
            autonomy_level=autonomy_level,
        )
    finally:
        queue.close()

    console.print(f"[green]Task created:[/green] id={task_id}, name={name}")
    if schedule:
        console.print(f"[dim]Schedule: {schedule}[/dim]")


@tasks_app.command("pause")
def tasks_pause(
    task_id: int = typer.Argument(..., help="Task ID to pause"),
):
    """Pause a task."""
    from merkaba.orchestration.queue import TaskQueue

    queue = TaskQueue()
    try:
        task = queue.get_task(task_id)
        if not task:
            console.print(f"[red]Task {task_id} not found[/red]")
            raise typer.Exit(1)
        queue.pause_task(task_id)
    finally:
        queue.close()

    console.print(f"[yellow]Paused:[/yellow] {task['name']} (id={task_id})")


@tasks_app.command("resume")
def tasks_resume(
    task_id: int = typer.Argument(..., help="Task ID to resume"),
):
    """Resume a paused task."""
    from merkaba.orchestration.queue import TaskQueue

    queue = TaskQueue()
    try:
        task = queue.get_task(task_id)
        if not task:
            console.print(f"[red]Task {task_id} not found[/red]")
            raise typer.Exit(1)
        queue.resume_task(task_id)
    finally:
        queue.close()

    console.print(f"[green]Resumed:[/green] {task['name']} (id={task_id})")


@tasks_app.command("runs")
def tasks_runs(
    task_id: int = typer.Argument(..., help="Task ID"),
):
    """Show run history for a task."""
    from merkaba.orchestration.queue import TaskQueue

    queue = TaskQueue()
    try:
        task = queue.get_task(task_id)
        if not task:
            console.print(f"[red]Task {task_id} not found[/red]")
            raise typer.Exit(1)
        runs = queue.get_runs(task_id)
    finally:
        queue.close()

    console.print(f"[bold]Run history for:[/bold] {task['name']} (id={task_id})\n")

    if not runs:
        console.print("[dim]No runs yet[/dim]")
        return

    table = Table()
    table.add_column("Run ID", style="cyan", justify="right")
    table.add_column("Started", style="dim")
    table.add_column("Finished", style="dim")
    table.add_column("Status")
    table.add_column("Error")

    for run in runs:
        run_status = run["status"]
        run_status_colors = {
            "success": "green",
            "failed": "red",
            "running": "blue",
            "timeout": "yellow",
        }
        run_style = run_status_colors.get(run_status, "white")

        table.add_row(
            str(run["id"]),
            run["started_at"][:19],
            (run["finished_at"] or "-")[:19],
            f"[{run_style}]{run_status}[/{run_style}]",
            (run["error"] or "-")[:50],
        )

    console.print(table)


# --- Integrations commands ---

integrations_app = typer.Typer(help="Manage external integrations")
app.add_typer(integrations_app, name="integrations")


@integrations_app.command("list")
def integrations_list():
    """List registered integration adapters."""
    _load_adapters()
    from merkaba.integrations import list_adapters, get_adapter_class

    adapters = list_adapters()
    if not adapters:
        console.print("No adapters registered.")
        return

    table = Table(title="Integration Adapters")
    table.add_column("Name", style="cyan")
    table.add_column("Class", style="green")

    for name in sorted(adapters):
        cls = get_adapter_class(name)
        table.add_row(name, cls.__name__ if cls else "?")

    console.print(table)


@integrations_app.command("test")
def integrations_test(name: str = typer.Argument(help="Adapter name to test")):
    """Run health check on an integration adapter."""
    _load_adapters()
    from merkaba.integrations import get_adapter_class

    cls = get_adapter_class(name)
    if cls is None:
        console.print(f"[red]Adapter not found: {name}[/red]")
        return

    adapter = cls(name=name)
    if not adapter.connect():
        console.print(f"[red]Failed to connect {name} -- check credentials with: merkaba integrations setup {name}[/red]")
        return

    result = adapter.health_check()
    if result.get("ok"):
        console.print(f"[green]{name} health check passed[/green]")
    else:
        console.print(f"[red]{name} health check failed: {result.get('error', 'unknown')}[/red]")


@integrations_app.command("setup")
def integrations_setup(name: str = typer.Argument(help="Adapter name to configure")):
    """Interactive credential setup for an integration adapter."""
    _load_adapters()
    from merkaba.integrations import get_adapter_class
    from merkaba.integrations.credentials import CredentialManager

    cls = get_adapter_class(name)
    if cls is None:
        console.print(f"[red]Adapter not found: {name}[/red]")
        return

    import importlib
    mod = importlib.import_module(f"merkaba.integrations.{name}_adapter")
    required = getattr(mod, "REQUIRED_CREDENTIALS", [])

    if not required:
        console.print(f"[yellow]No credentials required for {name}[/yellow]")
        return

    creds = CredentialManager()
    ok, missing = creds.has_required(name, required)

    if ok:
        console.print(f"[green]All credentials for {name} are already set.[/green]")
        if not typer.confirm("Overwrite?"):
            return
        missing = required

    for key in missing:
        value = typer.prompt(f"  {name}.{key}", hide_input="password" in key or "secret" in key or "token" in key)
        creds.store(name, key, value)

    console.print(f"[green]Credentials saved for {name}[/green]")


# --- Business Command Group ---

business_app = typer.Typer(help="Business management commands")
app.add_typer(business_app, name="business")


@business_app.command("add")
def business_add(
    name: str = typer.Option(..., "--name", "-n", help="Business name"),
    biz_type: str = typer.Option(..., "--type", "-t", help="Business type"),
    autonomy: int = typer.Option(1, "--autonomy", "-a", help="Starting autonomy level (0-5)"),
):
    """Register a new business."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        biz_id = store.add_business(name=name, type=biz_type, autonomy_level=autonomy)
        store.set_state(biz_id, "business", str(biz_id), "status", "active")
    finally:
        store.close()

    console.print(f"[green]Business created:[/green] id={biz_id}, name={name}, type={biz_type}")


@business_app.command("list")
def business_list():
    """List all registered businesses."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        businesses = store.list_businesses()
    finally:
        store.close()

    if not businesses:
        console.print("[dim]No businesses registered yet.[/dim]")
        return

    table = Table(title="Businesses")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("Autonomy", justify="right")
    table.add_column("Created", style="dim")

    for biz in businesses:
        created = biz["created_at"]
        if "T" in created:
            created = created.split("T")[0]
        table.add_row(
            str(biz["id"]),
            biz["name"],
            biz["type"],
            str(biz["autonomy_level"]),
            created,
        )

    console.print(table)


@business_app.command("show")
def business_show(
    business_id: int = typer.Argument(..., help="Business ID"),
):
    """Show detailed information about a business."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        biz = store.get_business(business_id)
        if not biz:
            console.print(f"[red]Business {business_id} not found[/red]")
            raise typer.Exit(1)

        facts = store.get_facts(business_id)
        decisions = store.get_decisions(business_id)
        state = store.get_state(business_id)
    finally:
        store.close()

    console.print(f"\n[bold]{biz['name']}[/bold] (id={biz['id']})")
    console.print(f"  Type: {biz['type']}")
    console.print(f"  Autonomy: {biz['autonomy_level']}")
    console.print(f"  Created: {biz['created_at']}")

    console.print(f"\n  Facts: {len(facts)}")
    console.print(f"  Decisions: {len(decisions)}")

    if state:
        console.print("\n[bold]State:[/bold]")
        state_table = Table(show_header=True)
        state_table.add_column("Entity", style="cyan")
        state_table.add_column("Key")
        state_table.add_column("Value", style="green")
        for s in state[:10]:
            state_table.add_row(
                f"{s['entity_type']}:{s['entity_id']}",
                s["key"],
                s["value"],
            )
        console.print(state_table)


@business_app.command("update")
def business_update(
    business_id: int = typer.Argument(..., help="Business ID"),
    name: str = typer.Option(None, "--name", "-n", help="New name"),
    biz_type: str = typer.Option(None, "--type", "-t", help="New type"),
    autonomy: int = typer.Option(None, "--autonomy", "-a", help="New autonomy level"),
):
    """Update a business's settings."""
    from merkaba.memory.store import MemoryStore

    kwargs = {}
    if name is not None:
        kwargs["name"] = name
    if biz_type is not None:
        kwargs["type"] = biz_type
    if autonomy is not None:
        kwargs["autonomy_level"] = autonomy

    if not kwargs:
        console.print("[yellow]Nothing to update. Use --name, --type, or --autonomy.[/yellow]")
        return

    store = MemoryStore()
    try:
        biz = store.get_business(business_id)
        if not biz:
            console.print(f"[red]Business {business_id} not found[/red]")
            raise typer.Exit(1)
        store.update_business(business_id, **kwargs)
    finally:
        store.close()

    console.print(f"[green]Updated business {business_id}:[/green] {kwargs}")


@business_app.command("dashboard")
def business_dashboard(
    business_id: int = typer.Argument(..., help="Business ID"),
):
    """Rich dashboard overview of a business."""
    from merkaba.memory.store import MemoryStore
    from merkaba.orchestration.queue import TaskQueue
    from merkaba.approval.queue import ActionQueue

    store = MemoryStore()
    task_queue = TaskQueue()
    action_queue = ActionQueue()
    try:
        biz = store.get_business(business_id)
        if not biz:
            console.print(f"[red]Business {business_id} not found[/red]")
            raise typer.Exit(1)

        facts = store.get_facts(business_id)
        decisions = store.get_decisions(business_id)
        state = store.get_state(business_id)
        tasks = task_queue.list_tasks(business_id=business_id)
        pending_actions = action_queue.list_actions(status="pending", business_id=business_id)
    finally:
        store.close()
        task_queue.close()
        action_queue.close()

    # Header
    console.print(f"\n[bold cyan]{'=' * 50}[/bold cyan]")
    console.print(f"[bold]  {biz['name']}[/bold]  ({biz['type']})  autonomy={biz['autonomy_level']}")
    console.print(f"[bold cyan]{'=' * 50}[/bold cyan]\n")

    # State
    if state:
        console.print("[bold]Current State[/bold]")
        state_table = Table(show_header=True, show_edge=False, pad_edge=False)
        state_table.add_column("Entity", style="cyan")
        state_table.add_column("Key")
        state_table.add_column("Value", style="green")
        for s in state:
            state_table.add_row(f"{s['entity_type']}:{s['entity_id']}", s["key"], s["value"])
        console.print(state_table)
        console.print()

    # Recent facts
    console.print(f"[bold]Recent Facts[/bold] ({len(facts)} total)")
    if facts:
        fact_table = Table(show_header=True, show_edge=False, pad_edge=False)
        fact_table.add_column("Category", style="yellow")
        fact_table.add_column("Key")
        fact_table.add_column("Value", max_width=50)
        for f in facts[:5]:
            fact_table.add_row(f["category"], f["key"], f["value"][:50])
        console.print(fact_table)
    else:
        console.print("  [dim]No facts yet[/dim]")
    console.print()

    # Recent decisions
    console.print(f"[bold]Recent Decisions[/bold] ({len(decisions)} total)")
    if decisions:
        dec_table = Table(show_header=True, show_edge=False, pad_edge=False)
        dec_table.add_column("Type", style="magenta")
        dec_table.add_column("Decision")
        dec_table.add_column("Outcome", style="dim")
        for d in decisions[:5]:
            dec_table.add_row(d["action_type"], d["decision"][:40], d.get("outcome") or "-")
        console.print(dec_table)
    else:
        console.print("  [dim]No decisions yet[/dim]")
    console.print()

    # Tasks
    console.print(f"[bold]Tasks[/bold] ({len(tasks)} total)")
    if tasks:
        task_table = Table(show_header=True, show_edge=False, pad_edge=False)
        task_table.add_column("ID", style="cyan", justify="right")
        task_table.add_column("Name")
        task_table.add_column("Status")
        task_table.add_column("Next Run", style="dim")
        for t in tasks[:5]:
            status_colors = {"pending": "green", "running": "blue", "paused": "yellow", "failed": "red"}
            sc = status_colors.get(t["status"], "white")
            task_table.add_row(
                str(t["id"]), t["name"],
                f"[{sc}]{t['status']}[/{sc}]",
                (t["next_run"] or "-")[:19],
            )
        console.print(task_table)
    else:
        console.print("  [dim]No tasks[/dim]")
    console.print()

    # Pending approvals
    console.print(f"[bold]Pending Approvals[/bold] ({len(pending_actions)} waiting)")
    if pending_actions:
        for a in pending_actions[:5]:
            console.print(f"  [{a['id']}] {a['action_type']}: {a['description'][:60]}")
    else:
        console.print("  [dim]No pending approvals[/dim]")
    console.print()


models_app = typer.Typer(help="Model routing commands")
app.add_typer(models_app, name="models")


@models_app.command("list")
def models_list():
    """Show current task_type to model mapping."""
    from merkaba.orchestration.supervisor import (
        MODEL_DEFAULTS, DEFAULT_MODEL, load_model_config, CONFIG_PATH,
    )

    mapping = load_model_config()

    table = Table(title="Model Routing", show_header=True)
    table.add_column("Task Type", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Source", style="dim")

    # Load overrides to show source
    overrides: dict[str, str] = {}
    try:
        with open(CONFIG_PATH) as f:
            overrides = json.load(f).get("models", {}).get("task_types", {})
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    for task_type in sorted(mapping):
        source = "config" if task_type in overrides else "default"
        table.add_row(task_type, mapping[task_type], source)

    table.add_row("(other)", DEFAULT_MODEL, "fallback")
    console.print(table)


@models_app.command("check")
def models_check():
    """Check which models are loaded and show fallback chain coverage."""
    from merkaba.llm import LLMClient, load_fallback_chains

    llm = LLMClient()
    available = llm.get_available_models()

    if not available:
        console.print("[red]Could not reach Ollama -- is it running?[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Loaded models ({len(available)}):[/bold]")
    for m in sorted(available):
        console.print(f"  [green]{m}[/green]")
    console.print()

    chains = load_fallback_chains()
    table = Table(title="Fallback Chain Coverage", show_header=True)
    table.add_column("Tier", style="cyan")
    table.add_column("Primary", style="green")
    table.add_column("Fallbacks", style="yellow")
    table.add_column("Status", style="bold")

    for tier_name, tier in sorted(chains.items()):
        primary_ok = tier.primary in available
        all_models = [tier.primary] + tier.fallbacks
        any_ok = any(m in available for m in all_models)

        fallback_strs = []
        for fb in tier.fallbacks:
            mark = "[green]v[/green]" if fb in available else "[red]x[/red]"
            fallback_strs.append(f"{mark} {fb}")

        primary_mark = "[green]v[/green]" if primary_ok else "[red]x[/red]"
        status = "[green]OK[/green]" if primary_ok else ("[yellow]DEGRADED[/yellow]" if any_ok else "[red]UNAVAILABLE[/red]")

        table.add_row(
            tier_name,
            f"{primary_mark} {tier.primary}",
            ", ".join(fallback_strs) if fallback_strs else "-",
            status,
        )

    console.print(table)


@models_app.command("set")
def models_set(
    task_type: str = typer.Argument(..., help="Task type to configure"),
    model: str = typer.Argument(..., help="Model name to use"),
):
    """Set a model override for a task type."""
    from merkaba.orchestration.supervisor import CONFIG_PATH

    config_path = CONFIG_PATH
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    data: dict = {}
    try:
        with open(config_path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    if "models" not in data:
        data["models"] = {}
    if "task_types" not in data["models"]:
        data["models"]["task_types"] = {}

    data["models"]["task_types"][task_type] = model
    with open(config_path, "w") as f:
        json.dump(data, f, indent=2)

    console.print(f"[green]Set {task_type} -> {model}[/green]")


@models_app.command("providers")
def models_providers():
    """Show cloud provider status."""
    from merkaba.llm_providers.registry import get_configured_providers, _load_cloud_config

    cloud_config = _load_cloud_config()
    providers = get_configured_providers()

    if not cloud_config and not providers:
        console.print("[dim]No cloud providers configured.[/dim]")
        console.print("\nTo add cloud providers, edit ~/.merkaba/config.json:")
        console.print('  {"cloud_providers": {"anthropic": {"api_key": "sk-ant-..."}}}')
        console.print("\nOr set environment variables: ANTHROPIC_API_KEY, OPENAI_API_KEY")
        return

    table = Table(title="Cloud Providers", show_header=True)
    table.add_column("Provider", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Source", style="dim")

    for name in sorted(set(list(cloud_config.keys()) + list(providers.keys()))):
        available = providers.get(name, False)
        status = "[green]Available[/green]" if available else "[red]Unavailable[/red]"
        has_config = name in cloud_config and cloud_config[name].get("api_key")
        has_env = os.environ.get(f"{name.upper()}_API_KEY") is not None
        source = "config" if has_config else ("env" if has_env else "none")
        table.add_row(name, status, source)

    console.print(table)
    console.print("\n[dim]Use cloud models with prefix: anthropic:claude-sonnet-4-20250514, openai:gpt-4o[/dim]")


# --- Backup commands ---

backup_app = typer.Typer(help="Database backup and restore")
app.add_typer(backup_app, name="backup")


@backup_app.command("run")
def backup_run():
    """Create a backup of all databases and config."""
    from merkaba.orchestration.backup import BackupManager

    mgr = BackupManager()
    path = mgr.run_backup()
    console.print(f"[green]Backup created:[/green] {path}")
    files = [f.name for f in path.iterdir() if f.is_file()]
    for f in files:
        console.print(f"  - {f}")
    convos = path / "conversations"
    if convos.is_dir():
        count = len(list(convos.iterdir()))
        console.print(f"  - conversations/ ({count} files)")


@backup_app.command("list")
def backup_list():
    """List available backups."""
    from merkaba.orchestration.backup import BackupManager

    mgr = BackupManager()
    backups = mgr.list_backups()
    if not backups:
        console.print("[dim]No backups found[/dim]")
        return
    table = Table(title="Backups", show_header=True)
    table.add_column("Timestamp", style="cyan")
    table.add_column("Files", style="green")
    for b in backups:
        table.add_row(b["timestamp"], ", ".join(b["files"]))
    console.print(table)


@backup_app.command("restore")
def backup_restore(
    timestamp: str = typer.Argument(..., help="Backup timestamp to restore from"),
    db_name: str = typer.Argument(..., help="Database file to restore (e.g. memory.db)"),
):
    """Restore a database from a backup."""
    from merkaba.orchestration.backup import BackupManager

    mgr = BackupManager()
    try:
        mgr.restore(timestamp, db_name)
        console.print(f"[green]Restored {db_name} from {timestamp}[/green]")
        console.print(f"[dim]Safety copy at {db_name}.pre-restore[/dim]")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


# --- Code agent commands ---

code_app = typer.Typer(help="Coding agent commands")
app.add_typer(code_app, name="code")


@code_app.command("run")
def code_run(
    spec: str = typer.Argument(..., help="Task description / spec for code generation"),
    target: list[str] = typer.Option([], "--target", "-t", help="Target files to modify"),
    explore: list[str] = typer.Option([], "--explore", "-e", help="Paths to explore first"),
    high_stakes: bool = typer.Option(False, "--high-stakes", help="Enable review after generation"),
):
    """Generate code from a spec with verification."""
    from merkaba.orchestration.code_worker import CodeWorker
    from merkaba.tools.registry import ToolRegistry
    from merkaba.tools.builtin import file_read, file_write, file_list, grep, glob, bash

    registry = ToolRegistry()
    for tool in [file_read, file_write, file_list, grep, glob, bash]:
        registry.register(tool)

    worker = CodeWorker(tools=registry)

    task = {
        "id": 0,
        "name": spec[:100],
        "task_type": "code",
        "payload": {
            "spec": spec,
            "target_files": target,
            "stakes": "high" if high_stakes else "normal",
        },
    }
    if explore:
        task["payload"]["complexity"] = "high"
        task["payload"]["explore_paths"] = explore

    console.print(f"[bold blue]Generating code...[/bold blue]")
    result = worker.execute(task)

    if result.success:
        console.print(f"[green]Success![/green] Verification: {result.output.get('verification', 'n/a')}")
        for f in result.output.get("files_written", []):
            console.print(f"  [cyan]{f}[/cyan]")
    else:
        console.print(f"[red]Failed:[/red] {result.error}")
        if result.output.get("files_rolled_back"):
            console.print("[dim]Rolled back files:[/dim]")
            for f in result.output["files_rolled_back"]:
                console.print(f"  [dim]{f}[/dim]")
        raise typer.Exit(1)


@code_app.command("explore")
def code_explore(
    path: str = typer.Argument(..., help="File or directory to explore"),
):
    """Explore a file or directory structure."""
    from merkaba.orchestration.explorer import ExplorationAgent

    agent = ExplorationAgent()

    if os.path.isdir(path):
        console.print(f"[bold blue]Mapping directory: {path}[/bold blue]")
        summary = agent.map_directory(path)
    elif os.path.isfile(path):
        console.print(f"[bold blue]Tracing file: {path}[/bold blue]")
        summary = agent.trace_functionality(path)
    else:
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)

    console.print(Markdown(summary))


# -- Observe command group --

observe_app = typer.Typer(help="Observability tools: token usage, audit trail, tracing")
app.add_typer(observe_app, name="observe")


@observe_app.command("tokens")
def observe_tokens(
    group_by: str = typer.Option("model", "--group-by", "-g", help="Group by: model or worker_type"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to look back"),
):
    """Show token usage summary."""
    from merkaba.observability.tokens import TokenUsageStore

    store = TokenUsageStore()
    summary = store.get_summary(group_by=group_by, days=days)
    store.close()

    if not summary:
        console.print("[dim]No token usage recorded yet.[/dim]")
        return

    table = Table(title=f"Token Usage (last {days} days, by {group_by})")
    table.add_column(group_by, style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Input", justify="right")
    table.add_column("Output", justify="right")
    table.add_column("Total", justify="right", style="bold")
    table.add_column("Duration (s)", justify="right")

    for row in summary:
        table.add_row(
            str(row.get(group_by) or "-"),
            str(row["call_count"]),
            str(row["total_input"]),
            str(row["total_output"]),
            str(row["total_tokens"]),
            f"{(row['total_duration_ms'] or 0) / 1000:.1f}",
        )
    console.print(table)


@observe_app.command("audit")
def observe_audit(
    type_filter: str = typer.Option(None, "--type", "-t", help="Filter by decision type"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max rows"),
):
    """Show recent decisions from the audit trail."""
    from merkaba.observability.audit import DecisionAuditStore

    store = DecisionAuditStore()
    decisions = store.get_recent(decision_type=type_filter, limit=limit)
    store.close()

    if not decisions:
        console.print("[dim]No decisions recorded yet.[/dim]")
        return

    table = Table(title="Decision Audit Trail")
    table.add_column("Trace", style="cyan", max_width=16)
    table.add_column("Type", style="yellow")
    table.add_column("Decision")
    table.add_column("Model", style="dim")
    table.add_column("Time", style="dim")

    for d in decisions:
        table.add_row(
            d["trace_id"],
            d["decision_type"],
            d["decision"],
            d.get("model") or "-",
            d["timestamp"][:19],
        )
    console.print(table)


@observe_app.command("trace")
def observe_trace(
    trace_id: str = typer.Argument(..., help="Trace ID to look up"),
):
    """Show all events for a specific trace ID."""
    from merkaba.observability.tokens import TokenUsageStore
    from merkaba.observability.audit import DecisionAuditStore

    token_store = TokenUsageStore()
    audit_store = DecisionAuditStore()

    tokens = token_store.get_by_trace(trace_id)
    decisions = audit_store.get_by_trace(trace_id)

    token_store.close()
    audit_store.close()

    if not tokens and not decisions:
        console.print(f"[dim]No events found for trace: {trace_id}[/dim]")
        return

    if decisions:
        table = Table(title=f"Decisions - {trace_id}")
        table.add_column("Type", style="yellow")
        table.add_column("Decision")
        table.add_column("Alternatives", style="dim")
        table.add_column("Time", style="dim")

        for d in decisions:
            alts = ", ".join(d["alternatives"]) if d.get("alternatives") else "-"
            table.add_row(d["decision_type"], d["decision"], alts, d["timestamp"][:19])
        console.print(table)

    if tokens:
        table = Table(title=f"Token Usage - {trace_id}")
        table.add_column("Model", style="cyan")
        table.add_column("Input", justify="right")
        table.add_column("Output", justify="right")
        table.add_column("Total", justify="right", style="bold")
        table.add_column("Duration (ms)", justify="right")
        table.add_column("Time", style="dim")

        for t in tokens:
            table.add_row(
                t["model"],
                str(t["input_tokens"]),
                str(t["output_tokens"]),
                str(t["total_tokens"]),
                str(t["duration_ms"]),
                t["timestamp"][:19],
            )
        console.print(table)


# -- Security command group --

security_app = typer.Typer(help="Security settings: 2FA, rate limits")
app.add_typer(security_app, name="security")


@security_app.command("setup-2fa")
def security_setup_2fa():
    """Generate and store a TOTP secret for approval 2FA."""
    import pyotp
    from merkaba.security.secrets import store_secret, get_secret

    existing = get_secret("totp_secret")
    if existing:
        console.print("[yellow]2FA is already configured.[/yellow]")
        console.print("Run 'merkaba security disable-2fa' first to reconfigure.")
        raise typer.Exit(1)

    secret = pyotp.random_base32()
    store_secret("totp_secret", secret)

    uri = pyotp.TOTP(secret).provisioning_uri(name="merkaba", issuer_name="Merkaba AI")

    console.print("[green]2FA configured successfully![/green]\n")
    console.print(f"Secret key: [bold]{secret}[/bold]")
    console.print(f"\nProvisioning URI:\n{uri}")
    console.print("\nAdd this to your authenticator app (Google Authenticator, Authy, etc.)")


@security_app.command("disable-2fa")
def security_disable_2fa(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove the TOTP secret from the keychain."""
    from merkaba.security.secrets import get_secret, delete_secret

    if not get_secret("totp_secret"):
        console.print("[dim]2FA is not configured.[/dim]")
        return

    if not confirm:
        typer.confirm("Are you sure you want to disable 2FA?", abort=True)

    delete_secret("totp_secret")
    console.print("[green]2FA has been disabled.[/green]")


@security_app.command("enable-encryption")
def security_enable_encryption():
    """Enable Fernet encryption for conversation files."""
    import base64
    from merkaba.security.secrets import store_secret, get_secret
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    existing = get_secret("conversation_encryption_key")
    if existing:
        console.print("[yellow]Encryption is already configured.[/yellow]")
        console.print("Run 'merkaba security disable-encryption' first to reconfigure.")
        raise typer.Exit(1)

    passphrase = typer.prompt("Enter encryption passphrase", hide_input=True)
    confirm = typer.prompt("Confirm passphrase", hide_input=True)
    if passphrase != confirm:
        console.print("[red]Passphrases do not match.[/red]")
        raise typer.Exit(1)

    # Derive Fernet key from passphrase
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"merkaba-conversation-salt",
        iterations=480_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode())).decode()
    store_secret("conversation_encryption_key", key)

    console.print("[green]Conversation encryption enabled.[/green]")
    console.print("New conversations will be encrypted. Existing files remain as-is.")


@security_app.command("disable-encryption")
def security_disable_encryption(
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Remove the conversation encryption key from the keychain."""
    from merkaba.security.secrets import get_secret, delete_secret

    if not get_secret("conversation_encryption_key"):
        console.print("[dim]Encryption is not configured.[/dim]")
        return

    if not confirm:
        typer.confirm(
            "Are you sure? Encrypted conversations will become unreadable.",
            abort=True,
        )

    delete_secret("conversation_encryption_key")
    console.print("[green]Conversation encryption disabled.[/green]")


@security_app.command("status")
def security_status():
    """Show current security configuration."""
    from merkaba.security.secrets import get_secret

    # 2FA status
    has_totp = get_secret("totp_secret") is not None
    status = "[green]Enabled[/green]" if has_totp else "[dim]Disabled[/dim]"
    console.print(f"2FA: {status}")

    # Encryption status
    has_encryption = get_secret("conversation_encryption_key") is not None
    enc_status = "[green]Enabled[/green]" if has_encryption else "[dim]Disabled[/dim]"
    console.print(f"Encryption: {enc_status}")

    # Load config for rate limit and threshold
    config_path = os.path.expanduser("~/.merkaba/config.json")
    totp_threshold = 3
    max_approvals = 5
    window_seconds = 60
    try:
        with open(config_path) as f:
            config = json.load(f)
        security = config.get("security", {})
        totp_threshold = security.get("totp_threshold", 3)
        rl = security.get("approval_rate_limit", {})
        max_approvals = rl.get("max_approvals", 5)
        window_seconds = rl.get("window_seconds", 60)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    console.print(f"TOTP threshold: autonomy_level >= {totp_threshold}")
    console.print(f"Rate limit: {max_approvals} approvals per {window_seconds}s")


# -- Config commands --
config_app = typer.Typer(help="Prompt and configuration management")
app.add_typer(config_app, name="config")


@config_app.command("show-prompt")
def config_show_prompt(business: int = typer.Option(None, help="Business ID")):
    """Show the resolved system prompt and which files are used."""
    from merkaba.config.prompts import PromptLoader
    loader = PromptLoader(base_dir=MERKABA_DIR)
    soul, user = loader.load(business_id=business)
    info = loader.resolve(business_id=business)
    console.print(f"[bold]=== SOUL (source: {info['soul_source']}) ===[/bold]")
    console.print(soul)
    console.print(f"\n[bold]=== USER (source: {info['user_source']}) ===[/bold]")
    console.print(user)


@config_app.command("edit-soul")
def config_edit_soul(business: int = typer.Option(None, help="Business ID")):
    """Open SOUL.md in $EDITOR."""
    import subprocess
    from merkaba.config.prompts import PromptLoader, DEFAULT_SOUL
    loader = PromptLoader(base_dir=MERKABA_DIR)
    loader.seed()
    if business:
        path = os.path.join(MERKABA_DIR, "businesses", str(business), "SOUL.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(DEFAULT_SOUL)
    else:
        path = os.path.join(MERKABA_DIR, "SOUL.md")
    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, path], check=False)


@config_app.command("edit-user")
def config_edit_user(business: int = typer.Option(None, help="Business ID")):
    """Open USER.md in $EDITOR."""
    import subprocess
    from merkaba.config.prompts import PromptLoader, DEFAULT_USER
    loader = PromptLoader(base_dir=MERKABA_DIR)
    loader.seed()
    if business:
        path = os.path.join(MERKABA_DIR, "businesses", str(business), "USER.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(DEFAULT_USER)
    else:
        path = os.path.join(MERKABA_DIR, "USER.md")
    editor = os.environ.get("EDITOR", "nano")
    subprocess.run([editor, path], check=False)


if __name__ == "__main__":
    app()
