# src/merkaba/cli.py
import json
import logging
import os
import platform
import sys
from datetime import datetime

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from merkaba import __version__

logger = logging.getLogger(__name__)

# Heavy modules imported lazily inside commands to avoid import-time failures
# (e.g., ollama SOCKS proxy error) and speed up CLI startup.

CLAUDE_PLUGIN_DIR = os.path.expanduser("~/.claude/plugins/cache")
MERKABA_DIR = os.path.expanduser("~/.merkaba")

# Exit code constants
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG = 2
EXIT_NOT_FOUND = 3

# Module-level verbose flag; set True when --verbose / -V is passed
verbose: bool = False


def format_date(value: str | None) -> str:
    """Format an ISO timestamp to a short date string (YYYY-MM-DD).

    Returns the original string unchanged if it cannot be parsed, and an
    empty string for None.
    """
    if value is None:
        return ""
    if "T" in value:
        return value.split("T")[0]
    return value


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


# Load CLI extensions from installed packages
def _load_cli_extensions():
    from merkaba.extensions import discover_cli_apps
    for name, ext_app in discover_cli_apps().items():
        try:
            app.add_typer(ext_app, name=name)
        except Exception as e:
            logger.warning("Failed to load CLI extension %s: %s", name, e)

_load_cli_extensions()


def _atomic_write_json(path: str, data: dict, **kwargs) -> None:
    """Write JSON to a file atomically via tmp+rename."""
    import tempfile
    dir_ = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, **kwargs)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def version_callback(value: bool):
    if value:
        py = sys.version_info
        console.print(
            f"merkaba {__version__} "
            f"(Python {py.major}.{py.minor}.{py.micro}, "
            f"{platform.system()} {platform.machine()})"
        )
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
    verbose_flag: bool = typer.Option(
        False, "--verbose", "-V", help="Enable verbose (DEBUG) output"
    ),
):
    """Merkaba - Local AI Agent Framework"""
    global verbose
    verbose = verbose_flag
    try:
        from merkaba.observability.tracing import setup_logging
        if verbose_flag:
            setup_logging(level=logging.DEBUG)
            # Also attach a Rich console handler to the root logger so DEBUG
            # messages appear on the terminal during verbose runs.
            from rich.logging import RichHandler
            root = logging.getLogger()
            root.setLevel(logging.DEBUG)
            if not any(isinstance(h, RichHandler) for h in root.handlers):
                root.addHandler(RichHandler(console=console, show_time=False))
        else:
            setup_logging()
    except Exception:
        pass


@app.command(rich_help_panel="Core")
def chat(
    message: str = typer.Argument(None, help="Message to send to Merkaba"),
    model: str = typer.Option("qwen3.5:122b", "--model", "-m", help="LLM model to use"),
):
    """Start a conversation with Merkaba."""
    from pathlib import Path as _Path
    from merkaba.config.validation import validate_config, print_startup_report, Severity

    config_path = os.path.expanduser("~/.merkaba/config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        config = {}
    base_dir = _Path(os.path.expanduser("~/.merkaba"))
    issues = validate_config(config, base_dir)
    if issues:
        print_startup_report(issues)
        if any(i.severity == Severity.ERROR for i in issues):
            console.print("[bold red]Startup blocked due to configuration errors.[/bold red]")
            raise typer.Exit(EXIT_CONFIG)

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


@app.command("init", rich_help_panel="Core")
def init_cmd(
    force: bool = typer.Option(False, "--force", "-f", help="Re-create config even if already initialized"),
):
    """Initialize Merkaba: create directories, config, templates, and databases."""
    from pathlib import Path as _Path
    from merkaba.init import run_init

    merkaba_home = _Path(os.path.expanduser("~/.merkaba"))
    result = run_init(merkaba_home, force=force)

    if result.already_initialized and not force:
        console.print("[yellow]Merkaba is already initialized.[/yellow]")
        console.print(f"  Home: {result.home_dir}")
        console.print("  Use [bold]--force[/bold] to re-create config and templates.")
        return

    console.print("[bold green]Merkaba initialized![/bold green]\n")

    if result.created_dirs:
        console.print(f"  Directories created: {', '.join(result.created_dirs)}")
    if result.config_written:
        console.print(f"  Config written: {result.home_dir / 'config.json'}")
    if result.soul_copied:
        console.print(f"  SOUL.md created from template")
    if result.user_copied:
        console.print(f"  USER.md created from template")
    if result.databases_initialized:
        console.print(f"  Databases initialized: {', '.join(result.databases_initialized)}")

    if result.ollama_available:
        console.print("\n  [green]Ollama is running[/green] -- ready to chat!")
    else:
        console.print("\n  [yellow]Ollama not detected[/yellow] -- start it with: ollama serve")

    console.print(f"\n  Run [bold]merkaba chat[/bold] to get started.")


# --- Telegram Command Group ---

telegram_app = typer.Typer(help="Telegram bot commands")
app.add_typer(telegram_app, name="telegram", rich_help_panel="Operations")


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


@app.command("web", rich_help_panel="Core")
def web(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind to"),
    port: int = typer.Option(5173, "--port", "-p", help="Port to listen on"),
):
    """Start Mission Control web interface."""
    import uvicorn
    from merkaba.web.app import create_app
    if host not in ("127.0.0.1", "localhost", "0.0.0.0"):
        console.print(
            "[yellow]Warning:[/yellow] Binding to non-localhost without TLS. "
            "Consider using a reverse proxy with TLS."
        )
    console.print(f"[bold green]Starting Mission Control...[/bold green]")
    console.print(f"Open [bold]http://{host}:{port}[/bold] in your browser")
    console.print("Press Ctrl+C to stop\n")
    uvicorn.run(create_app(), host=host, port=port)


@app.command("serve", rich_help_panel="Core")
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


@app.command("status", rich_help_panel="Core")
def status():
    """One-command health check: Ollama, databases, pending approvals, workers."""
    import sqlite3 as _sqlite3

    table = Table(title="Merkaba Status", show_header=True)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("Detail", style="dim")

    # --- Ollama ---
    try:
        import urllib.request as _req
        with _req.urlopen("http://localhost:11434/api/tags", timeout=2):
            ollama_status = "[green]OK[/green]"
            ollama_detail = "reachable at localhost:11434"
    except Exception as exc:
        ollama_status = "[red]FAIL[/red]"
        ollama_detail = f"not reachable: {exc.__class__.__name__}"
    table.add_row("Ollama", ollama_status, ollama_detail)

    # --- Databases ---
    for db_name in ("memory.db", "tasks.db", "actions.db"):
        db_path = os.path.join(MERKABA_DIR, db_name)
        if os.path.exists(db_path):
            try:
                conn = _sqlite3.connect(db_path)
                conn.execute("PRAGMA integrity_check")
                conn.close()
                db_status = "[green]OK[/green]"
                db_detail = db_path
            except Exception as exc:
                db_status = "[red]FAIL[/red]"
                db_detail = str(exc)
        else:
            db_status = "[yellow]MISSING[/yellow]"
            db_detail = db_path
        table.add_row(db_name, db_status, db_detail)

    # --- Pending approvals ---
    try:
        from merkaba.approval.queue import ActionQueue
        aq = ActionQueue()
        count = aq.get_pending_count()
        aq.close()
        approval_status = "[green]OK[/green]" if count == 0 else "[yellow]PENDING[/yellow]"
        approval_detail = f"{count} pending approval(s)"
    except Exception as exc:
        approval_status = "[dim]N/A[/dim]"
        approval_detail = str(exc)
    table.add_row("Approvals", approval_status, approval_detail)

    # --- Workers ---
    try:
        from merkaba.orchestration.workers import WORKER_REGISTRY
        worker_count = len(WORKER_REGISTRY)
        workers_status = "[green]OK[/green]"
        workers_detail = f"{worker_count} worker(s) registered"
    except Exception as exc:
        workers_status = "[dim]N/A[/dim]"
        workers_detail = str(exc)
    table.add_row("Workers", workers_status, workers_detail)

    console.print(table)


# --- Plugin Command Group ---

plugins_app = typer.Typer(help="Plugin management commands")
app.add_typer(plugins_app, name="plugins", rich_help_panel="Extensions")


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
        results = importer.import_all(plugin_name, force=force)
        for result in results:
            _print_import_result(result)


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


# --- Skills Command Group ---

skills_app = typer.Typer(help="Skill management commands")
app.add_typer(skills_app, name="skills", rich_help_panel="Extensions")


@skills_app.command("forge")
def skills_forge(
    from_url: str = typer.Option(..., "--from", help="ClawHub or GitHub URL to forge from"),
    name: str = typer.Option(None, "--name", help="Override the generated plugin name"),
    force: bool = typer.Option(False, "--force", "-f", help="Proceed even if flagged as dangerous"),
):
    """Generate a merkaba plugin from a ClawHub or GitHub skill."""
    from merkaba.plugins.forge import forge, check_security_gate, scrape_url

    console.print(f"[cyan]Forging plugin from:[/cyan] {from_url}\n")

    # Scrape first to show security gate before LLM call
    try:
        skill = scrape_url(from_url)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Failed to fetch URL:[/red] {e}")
        raise typer.Exit(1)

    # Security gate
    gate = check_security_gate(skill)
    if gate == "warn":
        console.print("[yellow]WARNING: ClawHub rates this skill as Suspicious.[/yellow]")
        if not force:
            confirm = typer.confirm("Continue anyway?")
            if not confirm:
                raise typer.Exit(0)
    elif gate == "double_warn":
        console.print("[red bold]DANGER: ClawHub rates this skill as MALICIOUS.[/red bold]")
        console.print("[red]This skill was flagged for dangerous patterns.[/red]")
        if not force:
            confirm = typer.confirm("Are you SURE you want to proceed?")
            if not confirm:
                raise typer.Exit(0)

    console.print(f"[cyan]Scraped:[/cyan] {skill.name} -- {skill.description}")
    console.print("[cyan]Generating plugin...[/cyan]")

    result = forge(
        url=from_url,
        name=name,
        confirm_dangerous=force,
    )

    if result.success:
        console.print(f"\n[green]Plugin forged successfully![/green]")
        console.print(f"  Name: {result.name}")
        console.print(f"  Path: {result.path}")
        if result.warnings:
            console.print(f"\n[yellow]Warnings ({len(result.warnings)}):[/yellow]")
            for w in result.warnings:
                console.print(f"  - {w}")
    else:
        console.print(f"\n[red]Forge failed:[/red] {result.error}")
        if result.warnings:
            console.print(f"\n[yellow]Security scan warnings:[/yellow]")
            for w in result.warnings:
                console.print(f"  - {w}")
            console.print("\n[dim]Use --force to write anyway.[/dim]")
        raise typer.Exit(1)


# --- Commands Command Group ---

commands_app = typer.Typer(help="Plugin command management")
app.add_typer(commands_app, name="commands", rich_help_panel="Extensions")


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
app.add_typer(memory_app, name="memory", rich_help_panel="Data")


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
    """List registered businesses. (Alias for 'merkaba business list'.)"""
    console.print("[dim]Tip: use [bold]merkaba business list[/bold] for the full business command group.[/dim]\n")
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        businesses = store.list_businesses()
    finally:
        store.close()

    if not businesses:
        console.print("[dim]No businesses found.[/dim]")
        return

    table = Table(title="Registered Businesses")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("Autonomy", justify="right")
    table.add_column("Created", style="dim")

    for biz in businesses:
        table.add_row(
            str(biz["id"]),
            biz["name"],
            biz["type"],
            str(biz["autonomy_level"]),
            format_date(biz["created_at"]),
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
def memory_decay(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Run memory decay: reduce relevance of stale memories and archive low-score items."""
    from merkaba.memory.store import MemoryStore
    from merkaba.memory.lifecycle import MemoryDecayJob

    if not yes:
        typer.confirm(
            "This will reduce relevance scores and archive low-score memories. Continue?",
            abort=True,
        )

    store = MemoryStore()
    try:
        with console.status("[bold]Running memory decay...[/bold]"):
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
def memory_consolidate(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Consolidate related facts into summaries using LLM."""
    from merkaba.memory.store import MemoryStore
    from merkaba.memory.lifecycle import MemoryConsolidationJob
    from merkaba.llm import LLMClient

    if not yes:
        typer.confirm(
            "This will group and summarize related facts via LLM, archiving the originals. Continue?",
            abort=True,
        )

    store = MemoryStore()
    llm = LLMClient()
    try:
        with console.status("[bold]Running memory consolidation...[/bold]"):
            job = MemoryConsolidationJob(store=store, llm=llm)
            stats = job.run()
        console.print(
            f"[bold]Consolidation complete:[/bold] "
            f"{stats['groups']} groups, {stats['summaries']} summaries, {stats['archived']} archived"
        )
    finally:
        store.close()


@memory_app.command("rebuild-vectors")
def memory_rebuild_vectors(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Rebuild vector store from non-archived SQLite data."""
    from merkaba.memory.store import MemoryStore
    from merkaba.memory.vectors import VectorMemory

    if not yes:
        typer.confirm(
            "This will delete and rebuild the entire vector store from SQLite data. Continue?",
            abort=True,
        )

    store = MemoryStore()
    try:
        with console.status("[bold]Rebuilding vector store...[/bold]"):
            vectors = VectorMemory()
            stats = vectors.rebuild_from_store(store)
            vectors.close()
        console.print(f"[green]Vector rebuild complete:[/green] {stats}")
    except ImportError:
        console.print("[red]ChromaDB not installed. Run: pip install chromadb[/red]")
    except Exception as e:
        console.print(f"[red]Rebuild failed: {e}[/red]")
    finally:
        store.close()


# --- Memory: Conversations Sub-Group ---

conversations_app = typer.Typer(help="Conversation history management")
memory_app.add_typer(conversations_app, name="conversations")


@conversations_app.command("list")
def conversations_list(
    limit: int = typer.Option(20, "--limit", "-l", help="Max conversations to show"),
):
    """List conversation files by date."""
    import glob as _glob
    convos_dir = os.path.expanduser("~/.merkaba/conversations")
    if not os.path.isdir(convos_dir):
        console.print("[dim]No conversations found.[/dim]")
        return

    files = sorted(
        _glob.glob(os.path.join(convos_dir, "*.json")),
        key=os.path.getmtime,
        reverse=True,
    )[:limit]

    if not files:
        console.print("[dim]No conversations found.[/dim]")
        return

    table = Table(title="Conversations")
    table.add_column("ID", style="cyan")
    table.add_column("Messages", justify="right")
    table.add_column("Modified", style="dim")

    for fpath in files:
        conv_id = os.path.splitext(os.path.basename(fpath))[0]
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
        msg_count = "-"
        try:
            with open(fpath) as f:
                raw = f.read()
            if not raw.startswith("MERKABA_ENC:"):
                data = json.loads(raw)
                msg_count = str(len(data.get("messages", [])))
        except (json.JSONDecodeError, OSError):
            pass
        table.add_row(conv_id, msg_count, mtime)

    console.print(table)


@conversations_app.command("show")
def conversations_show(
    conversation_id: str = typer.Argument(..., help="Conversation ID (session filename without .json)"),
):
    """Display a conversation."""
    convos_dir = os.path.expanduser("~/.merkaba/conversations")
    fpath = os.path.join(convos_dir, f"{conversation_id}.json")

    if not os.path.exists(fpath):
        console.print(f"[red]Conversation '{conversation_id}' not found.[/red]")
        raise typer.Exit(EXIT_NOT_FOUND)

    try:
        with open(fpath) as f:
            raw = f.read()
        if raw.startswith("MERKABA_ENC:"):
            console.print("[yellow]Conversation is encrypted -- use 'merkaba security enable-encryption' to configure decryption.[/yellow]")
            raise typer.Exit(EXIT_ERROR)
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]Failed to read conversation:[/red] {e}")
        raise typer.Exit(EXIT_ERROR)

    messages = data.get("messages", [])
    console.print(f"[bold]Conversation:[/bold] {conversation_id}")
    console.print(f"[dim]{len(messages)} message(s)[/dim]\n")

    role_styles = {"user": "bold blue", "assistant": "bold green", "system": "dim", "tool": "yellow"}
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        timestamp = format_date(msg.get("timestamp", ""))
        style = role_styles.get(role, "white")
        label = f"[{style}]{role.upper()}[/{style}]"
        if timestamp:
            label += f" [dim]({timestamp})[/dim]"
        console.print(f"{label}: {content}\n")


@conversations_app.command("delete")
def conversations_delete(
    conversation_id: str = typer.Argument(..., help="Conversation ID to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a conversation file."""
    convos_dir = os.path.expanduser("~/.merkaba/conversations")
    fpath = os.path.join(convos_dir, f"{conversation_id}.json")

    if not os.path.exists(fpath):
        console.print(f"[red]Conversation '{conversation_id}' not found.[/red]")
        raise typer.Exit(EXIT_NOT_FOUND)

    if not yes:
        typer.confirm(f"Delete conversation '{conversation_id}'?", abort=True)

    os.remove(fpath)
    console.print(f"[green]Deleted:[/green] {conversation_id}")


@conversations_app.command("export")
def conversations_export(
    conversation_id: str = typer.Argument(..., help="Conversation ID to export"),
    output: str = typer.Option(..., "--output", "-o", help="Output JSON file path"),
):
    """Export a conversation as JSON."""
    convos_dir = os.path.expanduser("~/.merkaba/conversations")
    fpath = os.path.join(convos_dir, f"{conversation_id}.json")

    if not os.path.exists(fpath):
        console.print(f"[red]Conversation '{conversation_id}' not found.[/red]")
        raise typer.Exit(EXIT_NOT_FOUND)

    try:
        with open(fpath) as f:
            raw = f.read()
        if raw.startswith("MERKABA_ENC:"):
            console.print("[yellow]Conversation is encrypted -- cannot export without decryption key.[/yellow]")
            raise typer.Exit(EXIT_ERROR)
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        console.print(f"[red]Failed to read conversation:[/red] {e}")
        raise typer.Exit(EXIT_ERROR)

    with open(output, "w") as f:
        json.dump(data, f, indent=2)

    msg_count = len(data.get("messages", []))
    console.print(f"[green]Exported[/green] {msg_count} message(s) to [bold]{output}[/bold]")


# --- Memory: Relationships Command ---

@memory_app.command("relationships")
def memory_relationships(
    entity: str = typer.Option(None, "--entity", "-e", help="Filter by entity name"),
    business_id: int = typer.Option(None, "--business", "-b", help="Filter by business ID"),
):
    """Show entity relationships from the memory store."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        businesses = store.list_businesses()
        if not businesses:
            console.print("[dim]No relationships found.[/dim]")
            return

        rows: list[dict] = []
        target_ids = (
            [b["id"] for b in businesses if b["id"] == business_id]
            if business_id is not None
            else [b["id"] for b in businesses]
        )
        for biz_id in target_ids:
            rels = store.get_relationships(biz_id)
            rows.extend(rels)
    finally:
        store.close()

    if entity:
        entity_lower = entity.lower()
        rows = [r for r in rows if entity_lower in r["entity_id"].lower() or entity_lower in r["related_entity"].lower()]

    if not rows:
        console.print("[dim]No relationships found.[/dim]")
        return

    table = Table(title="Entity Relationships")
    table.add_column("Entity", style="cyan")
    table.add_column("Related Entity", style="green")
    table.add_column("Relationship", style="yellow")
    table.add_column("Type", style="dim")
    table.add_column("Updated", style="dim")

    for r in rows:
        table.add_row(
            r["entity_id"],
            r["related_entity"],
            r["relation"],
            r.get("entity_type", ""),
            format_date(r.get("updated_at", "")),
        )

    console.print(table)


# --- Scheduler Command Group ---

scheduler_app = typer.Typer(help="Task scheduler commands")
app.add_typer(scheduler_app, name="scheduler", rich_help_panel="Operations")


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
def scheduler_remove(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Remove launchd plist."""
    import subprocess

    plist_path = os.path.expanduser(
        "~/Library/LaunchAgents/com.merkaba.scheduler.plist"
    )

    if not os.path.exists(plist_path):
        console.print("[yellow]Plist not installed[/yellow]")
        return

    if not yes:
        typer.confirm(
            "This will unload and remove the scheduler launchd plist. Continue?",
            abort=True,
        )

    subprocess.run(["launchctl", "unload", plist_path], check=False)
    os.remove(plist_path)
    console.print(f"[green]Removed:[/green] {plist_path}")


# --- Approval Command Group ---

approval_app = typer.Typer(help="Approval workflow commands")
app.add_typer(approval_app, name="approval", rich_help_panel="Operations")


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
        table.add_row(
            str(a["id"]),
            a["action_type"],
            a["description"][:50],
            str(a["autonomy_level"]),
            a["status"],
            format_date(a["created_at"]),
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
    reason: str = typer.Option(None, "--reason", "-r", help="Reason for denial"),
):
    """Deny a pending action."""
    from merkaba.approval.queue import ActionQueue

    queue = ActionQueue()
    try:
        result = queue.decide(action_id, approved=False, decided_by="cli", reason=reason)
        if result:
            msg = f"[yellow]Denied action #{action_id}[/yellow]: {result['action_type']}"
            if reason:
                msg += f" (reason: {reason})"
            console.print(msg)
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
app.add_typer(tasks_app, name="tasks", rich_help_panel="Data")


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
app.add_typer(integrations_app, name="integrations", rich_help_panel="Extensions")


@integrations_app.command("list")
def integrations_list():
    """List available integrations and their configuration status."""
    _load_adapters()
    from merkaba.integrations import list_adapters, get_adapter_class
    from merkaba.integrations.credentials import CredentialManager

    adapters = list_adapters()
    if not adapters:
        console.print("[dim]No integrations found.[/dim]")
        return

    creds = CredentialManager()

    # Map known adapters to their required credential keys
    _known_creds: dict[str, list[str]] = {
        "email": ["host", "port", "user", "password"],
        "stripe": ["api_key"],
        "slack": ["bot_token"],
        "github": ["token"],
        "discord": ["bot_token"],
        "signal": ["account"],
        "calendar": [],
        "qmd": [],
    }

    table = Table(title="Integrations")
    table.add_column("Name", style="cyan")
    table.add_column("Class", style="green")
    table.add_column("Status", style="bold")

    for name in sorted(adapters):
        cls = get_adapter_class(name)
        class_name = cls.__name__ if cls else "?"
        required = _known_creds.get(name, [])
        if not required:
            status = "[dim]no credentials needed[/dim]"
        else:
            ok, missing = creds.has_required(name, required)
            if ok:
                status = "[green]configured[/green]"
            else:
                status = f"[yellow]missing: {', '.join(missing)}[/yellow]"
        table.add_row(name, class_name, status)

    console.print(table)
    console.print("\n[dim]Configure with: merkaba integrations setup <name>[/dim]")


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
app.add_typer(business_app, name="business", rich_help_panel="Data")


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
        console.print("[dim]No businesses found.[/dim]")
        return

    table = Table(title="Businesses")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Name", style="white")
    table.add_column("Type", style="yellow")
    table.add_column("Autonomy", justify="right")
    table.add_column("Created", style="dim")

    for biz in businesses:
        table.add_row(
            str(biz["id"]),
            biz["name"],
            biz["type"],
            str(biz["autonomy_level"]),
            format_date(biz["created_at"]),
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
app.add_typer(models_app, name="models", rich_help_panel="System")


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
    _atomic_write_json(config_path, data)

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
app.add_typer(backup_app, name="backup", rich_help_panel="System")


@backup_app.command("run")
def backup_run(
    encrypt: bool = typer.Option(False, "--encrypt", "-e", help="Encrypt backup files using keychain key"),
):
    """Create a backup of all databases and config."""
    from merkaba.orchestration.backup import BackupManager

    mgr = BackupManager()
    with console.status("[bold]Creating backup...[/bold]"):
        path = mgr.run_backup(encrypt=encrypt)
    if encrypt:
        console.print(f"[green]Backup created:[/green] {path} [dim]\[encrypted][/dim]")
    else:
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
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Restore a database from a backup."""
    from merkaba.orchestration.backup import BackupManager

    if not yes:
        typer.confirm(
            f"This will overwrite {db_name} with the backup from {timestamp}. Continue?",
            abort=True,
        )

    mgr = BackupManager()
    try:
        with console.status(f"[bold]Restoring {db_name}...[/bold]"):
            mgr.restore(timestamp, db_name)
        console.print(f"[green]Restored {db_name} from {timestamp}[/green]")
        console.print(f"[dim]Safety copy at {db_name}.pre-restore[/dim]")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


# --- Data Command Group ---

data_app = typer.Typer(help="Data management (export, delete)")
app.add_typer(data_app, name="data", rich_help_panel="Data")


@data_app.command("export")
def data_export(
    output: str = typer.Option(..., "--output", "-o", help="Output JSON file path"),
    business_id: int = typer.Option(None, "--business-id", "-b", help="Filter to a specific business"),
):
    """Export memory data (facts, decisions, learnings, episodes, relationships, state) to JSON."""
    from merkaba.memory.store import MemoryStore

    store = MemoryStore()
    try:
        if business_id is not None:
            biz = store.get_business(business_id)
            if not biz:
                console.print(f"[red]Business {business_id} not found[/red]")
                raise typer.Exit(1)
            facts = store.get_facts(business_id, include_archived=True)
            decisions = store.get_decisions(business_id, include_archived=True)
            relationships = store.get_relationships(business_id)
            episodes = store.get_episodes(business_id=business_id, limit=100_000)
            learnings = [
                l for l in store.get_learnings(include_archived=True)
                if l.get("source_business_id") == business_id
            ]
            state = store.get_all_state(business_id)
        else:
            # Export all data across all businesses
            businesses = store.list_businesses()
            facts: list = []
            decisions: list = []
            relationships: list = []
            episodes: list = []
            state: list = []
            for biz in businesses:
                biz_id = biz["id"]
                facts.extend(store.get_facts(biz_id, include_archived=True))
                decisions.extend(store.get_decisions(biz_id, include_archived=True))
                relationships.extend(store.get_relationships(biz_id))
                episodes.extend(store.get_episodes(business_id=biz_id, limit=100_000))
                state.extend(store.get_all_state(biz_id))
            learnings = store.get_learnings(include_archived=True)
    finally:
        store.close()

    exported_at = datetime.utcnow().isoformat() + "Z"
    payload = {
        "exported_at": exported_at,
        "business_id": business_id,
        "facts": facts,
        "decisions": decisions,
        "learnings": learnings,
        "episodes": episodes,
        "relationships": relationships,
        "state": state,
    }

    with open(output, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    console.print(
        f"[green]Exported[/green] "
        f"{len(facts)} facts, {len(decisions)} decisions, "
        f"{len(learnings)} learnings, {len(episodes)} episodes, "
        f"{len(relationships)} relationships, {len(state)} state entries "
        f"to [bold]{output}[/bold]"
    )


@data_app.command("delete-all")
def data_delete_all(
    business_id: int = typer.Option(..., "--business-id", "-b", help="Business ID whose data to delete"),
    confirm: bool = typer.Option(False, "--confirm", help="Skip interactive confirmation prompt"),
):
    """Permanently delete all data for a business (facts, decisions, episodes, etc.)."""
    from merkaba.memory.store import MemoryStore

    if not confirm:
        confirmed = typer.confirm(
            f"This will permanently delete all data for business {business_id}. Continue?"
        )
        if not confirmed:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    store = MemoryStore()
    try:
        biz = store.get_business(business_id)
        if not biz:
            console.print(f"[red]Business {business_id} not found[/red]")
            raise typer.Exit(1)
        counts = store.hard_delete_business(business_id, cascade=True)
    finally:
        store.close()

    # Also remove conversation and upload files
    import shutil as _shutil
    convos_dir = os.path.join(MERKABA_DIR, "conversations")
    uploads_dir = os.path.join(MERKABA_DIR, "uploads")
    for dir_path, label in [(convos_dir, "conversations"), (uploads_dir, "uploads")]:
        if os.path.isdir(dir_path):
            count = len(os.listdir(dir_path))
            _shutil.rmtree(dir_path)
            counts[label] = count

    console.print(f"[green]Deleted all data for business {business_id}:[/green]")
    for table, count in counts.items():
        console.print(f"  {table}: {count} row(s) deleted")


# --- Code agent commands ---

code_app = typer.Typer(help="Coding agent commands")
app.add_typer(code_app, name="code", rich_help_panel="Core")


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


@code_app.command("review")
def code_review(
    path: str = typer.Argument(..., help="File or directory to review"),
    criteria: str = typer.Option(
        "Check for correctness, best practices, and potential issues.",
        "--criteria", "-c",
        help="Review criteria",
    ),
):
    """Review code in a file or directory."""
    from merkaba.orchestration.review_worker import ReviewWorker

    # Collect file contents
    file_contents: list[str] = []
    if os.path.isdir(path):
        for root, _dirs, files in os.walk(path):
            for fname in sorted(files):
                if fname.endswith(".py"):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath) as f:
                            content = f.read()
                        file_contents.append(f"### {fpath}\n```python\n{content}\n```")
                    except (OSError, UnicodeDecodeError):
                        continue
    elif os.path.isfile(path):
        try:
            with open(path) as f:
                content = f.read()
            file_contents.append(f"### {path}\n```\n{content}\n```")
        except (OSError, UnicodeDecodeError):
            console.print(f"[red]Cannot read: {path}[/red]")
            raise typer.Exit(1)
    else:
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(1)

    if not file_contents:
        console.print("[yellow]No files to review.[/yellow]")
        return

    output_text = "\n\n".join(file_contents)

    task = {
        "id": 0,
        "name": f"Review: {path}",
        "task_type": "review",
        "payload": {
            "output_text": output_text,
            "review_criteria": criteria,
        },
    }

    console.print(f"[bold blue]Reviewing {len(file_contents)} file(s)...[/bold blue]")
    worker = ReviewWorker()
    result = worker.execute(task)

    if result.success:
        console.print(Markdown(result.output.get("review", "")))
    else:
        console.print(f"[red]Review failed:[/red] {result.error}")
        raise typer.Exit(1)


# -- Observe command group --

observe_app = typer.Typer(help="Observability tools: token usage, audit trail, tracing")
app.add_typer(observe_app, name="observe", rich_help_panel="System")


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
app.add_typer(security_app, name="security", rich_help_panel="System")


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


@security_app.command("scan")
def security_scan(
    full: bool = typer.Option(False, "--full", help="Run full scan (integrity + CVE + code patterns)"),
    regenerate_baseline: bool = typer.Option(False, "--regenerate-baseline", help="Regenerate integrity baseline and exit"),
):
    """Run a security scan."""
    from merkaba.security.scanner import SecurityScanner

    scanner = SecurityScanner()

    if regenerate_baseline:
        hashes = scanner.regenerate_baseline()
        console.print(f"[green]Baseline regenerated:[/green] {len(hashes)} file(s) hashed")
        return

    console.print(f"[bold blue]Running {'full' if full else 'quick'} security scan...[/bold blue]")
    report = scanner.full_scan() if full else scanner.quick_scan()

    if not report.has_issues:
        console.print("[green]No issues found.[/green]")
        return

    if report.integrity_issues:
        table = Table(title=f"Integrity Issues ({len(report.integrity_issues)})")
        table.add_column("Issue", style="yellow")
        for issue in report.integrity_issues:
            table.add_row(issue)
        console.print(table)

    if report.cve_issues:
        table = Table(title=f"CVE Issues ({len(report.cve_issues)})")
        table.add_column("Package", style="cyan")
        table.add_column("Version")
        table.add_column("CVE", style="red")
        table.add_column("Fix Version", style="green")
        for cve in report.cve_issues:
            table.add_row(cve.package, cve.version, cve.cve_id, cve.fix_version or "-")
        console.print(table)

    if report.code_warnings:
        table = Table(title=f"Code Warnings ({len(report.code_warnings)})")
        table.add_column("Warning", style="yellow")
        for warning in report.code_warnings:
            table.add_row(warning)
        console.print(table)

    raise typer.Exit(1)


@security_app.command("migrate-keys")
def security_migrate_keys():
    """Migrate API keys from config.json to the OS keychain."""
    try:
        import keyring as _keyring
    except ImportError:
        console.print("[red]Error:[/red] keyring package is not installed.")
        console.print("Install it with: pip install keyring")
        raise typer.Exit(1)

    config_path = os.path.expanduser("~/.merkaba/config.json")

    try:
        with open(config_path) as f:
            config = json.load(f)
    except FileNotFoundError:
        console.print("[dim]No config.json found at ~/.merkaba/config.json[/dim]")
        return
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error:[/red] Could not parse config.json: {exc}")
        raise typer.Exit(1)

    cloud_providers = config.get("cloud_providers", {})
    if not cloud_providers:
        console.print("[dim]No cloud_providers section in config.json.[/dim]")
        return

    migrated = []
    for name, provider_cfg in cloud_providers.items():
        key = provider_cfg.get("api_key")
        if not key:
            continue

        _keyring.set_password("merkaba", f"{name}_api_key", key)
        console.print(f"[green]Stored[/green] {name} API key in keychain.")
        migrated.append(name)

    if not migrated:
        console.print("[dim]No API keys found in config.json to migrate.[/dim]")
        return

    remove = typer.confirm("Remove keys from config.json?", default=False)
    if remove:
        for name in migrated:
            config["cloud_providers"][name].pop("api_key", None)
        _atomic_write_json(config_path, config)
        console.print("[green]API keys removed from config.json.[/green]")
    else:
        console.print("[dim]Keys left in config.json. Run 'merkaba security migrate-keys' again to remove them later.[/dim]")


# -- Pair commands --
# TODO: GatewayPairing state is in-memory only. Each CLI invocation creates a
# new instance, so initiate + confirm must happen in the same process (useful
# for testing). Persistent pairing state (e.g., SQLite) is needed for real
# multi-process usage where a channel initiates and the CLI confirms.
pair_app = typer.Typer(help="Gateway pairing commands")
app.add_typer(pair_app, name="pair", rich_help_panel="System")


@pair_app.command("list")
def pair_list():
    """Show all paired channel identities."""
    from merkaba.security.pairing import GatewayPairing

    gp = GatewayPairing()
    paired = gp.list_paired()

    if not paired:
        console.print("[dim]No paired identities.[/dim]")
        return

    table = Table(title="Paired Identities")
    table.add_column("Identity", style="cyan")
    for identity in paired:
        table.add_row(identity)
    console.print(table)


@pair_app.command("initiate")
def pair_initiate(
    channel: str = typer.Argument(help="Channel type (e.g., telegram, discord, slack)"),
    identity: str = typer.Argument(help="Channel identity (e.g., telegram:user123)"),
):
    """Generate a pairing code for testing. In production, channels initiate pairing themselves."""
    from merkaba.security.pairing import GatewayPairing

    gp = GatewayPairing()
    code = gp.initiate(channel, identity)
    console.print(f"Pairing code for [cyan]{identity}[/cyan] on [yellow]{channel}[/yellow]: [bold green]{code}[/bold green]")
    console.print(f"Confirm with: [bold]merkaba pair confirm {identity} {code}[/bold]")
    console.print("[dim]Code expires in 5 minutes.[/dim]")


@pair_app.command("confirm")
def pair_confirm(
    identity: str = typer.Argument(help="Channel identity to confirm"),
    code: str = typer.Argument(help="6-character pairing code"),
):
    """Confirm a pairing code to authorize a channel identity."""
    from merkaba.security.pairing import GatewayPairing

    gp = GatewayPairing()
    if gp.confirm(identity, code):
        console.print(f"[green]Identity paired successfully:[/green] {identity}")
    else:
        console.print("[red]Pairing failed.[/red] Code may be invalid or expired.")
        raise typer.Exit(1)


@pair_app.command("revoke")
def pair_revoke(
    identity: str = typer.Argument(help="Channel identity to revoke"),
):
    """Revoke a paired channel identity."""
    from merkaba.security.pairing import GatewayPairing

    gp = GatewayPairing()
    if gp.is_paired(identity):
        gp.revoke(identity)
        console.print(f"[green]Identity revoked:[/green] {identity}")
    else:
        console.print(f"[yellow]Identity not found:[/yellow] {identity}")


# -- Config commands --
config_app = typer.Typer(help="Prompt and configuration management")
app.add_typer(config_app, name="config", rich_help_panel="System")


@config_app.command("show")
def config_show():
    """Pretty-print ~/.merkaba/config.json with API keys redacted."""
    import re

    from rich.syntax import Syntax

    config_path = os.path.join(MERKABA_DIR, "config.json")
    try:
        with open(config_path) as f:
            raw = f.read()
        config = json.loads(raw)
    except FileNotFoundError:
        console.print(f"[dim]No config.json found at {config_path}[/dim]")
        return
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error:[/red] Could not parse config.json: {exc}")
        raise typer.Exit(1)

    def _redact(obj):
        if isinstance(obj, dict):
            return {
                k: "***redacted***" if re.search(r"api[_-]?key|secret", k, re.IGNORECASE) else _redact(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_redact(v) for v in obj]
        return obj

    redacted = _redact(config)
    formatted = json.dumps(redacted, indent=2)
    syntax = Syntax(formatted, "json", theme="monokai", line_numbers=False)
    console.print(syntax)


@config_app.command("validate")
def config_validate():
    """Validate ~/.merkaba/config.json and report issues."""
    from pathlib import Path as _Path

    from merkaba.config.validation import validate_config, Severity

    config_path = os.path.join(MERKABA_DIR, "config.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
    except FileNotFoundError:
        console.print(f"[dim]No config.json found at {config_path} — using empty config.[/dim]")
        config = {}
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error:[/red] Could not parse config.json: {exc}")
        raise typer.Exit(1)

    base_dir = _Path(MERKABA_DIR)
    issues = validate_config(config, base_dir, _skip_runtime_checks=True)

    if not issues:
        console.print("[green]Config is valid — no issues found.[/green]")
        return

    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]
    infos = [i for i in issues if i.severity == Severity.INFO]

    if errors:
        table = Table(title=f"Errors ({len(errors)})", style="red")
        table.add_column("Component", style="cyan")
        table.add_column("Message")
        table.add_column("Hint", style="dim")
        for issue in errors:
            table.add_row(issue.component, issue.message, issue.hint or "")
        console.print(table)

    if warnings:
        table = Table(title=f"Warnings ({len(warnings)})", style="yellow")
        table.add_column("Component", style="cyan")
        table.add_column("Message")
        table.add_column("Hint", style="dim")
        for issue in warnings:
            table.add_row(issue.component, issue.message, issue.hint or "")
        console.print(table)

    if infos:
        table = Table(title=f"Info ({len(infos)})")
        table.add_column("Component", style="cyan")
        table.add_column("Message")
        for issue in infos:
            table.add_row(issue.component, issue.message)
        console.print(table)

    if errors:
        raise typer.Exit(1)


KNOWN_CONFIG_KEYS = frozenset({
    "model", "models", "business_id", "auto_approve_level",
    "security", "api_key", "cors_origins", "log_level",
    "permissions", "permission_tiers", "path_restrictions",
    "shell_allowlist", "encryption_key", "classifier_fail_mode",
    "host", "port", "debug", "telegram", "slack", "plugins",
    "tools", "workers", "memory", "scheduler", "backup",
    "cloud_providers",
})


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Dotted config key (e.g. security.classifier_fail_mode)"),
    value: str = typer.Argument(help="Value to set"),
):
    """Set a config value at a dotted path in ~/.merkaba/config.json."""
    config_path = os.path.join(MERKABA_DIR, "config.json")

    # Load existing config or start fresh
    try:
        with open(config_path) as f:
            config = json.load(f)
    except FileNotFoundError:
        config = {}
    except json.JSONDecodeError as exc:
        console.print(f"[red]Error:[/red] Could not parse config.json: {exc}")
        raise typer.Exit(1)

    # Auto-detect type
    def _coerce(v: str):
        if v.lower() == "true":
            return True
        if v.lower() == "false":
            return False
        try:
            return int(v)
        except ValueError:
            pass
        try:
            return float(v)
        except ValueError:
            pass
        return v

    coerced = _coerce(value)

    # Navigate and set via dotted path
    parts = key.split(".")
    d = config
    for part in parts[:-1]:
        if part not in d or not isinstance(d[part], dict):
            d[part] = {}
        d = d[part]
    d[parts[-1]] = coerced

    top_key = parts[0]
    if top_key not in KNOWN_CONFIG_KEYS:
        console.print(f"[yellow]Warning:[/yellow] '{top_key}' is not a recognized config key. Check for typos.")

    os.makedirs(MERKABA_DIR, exist_ok=True)
    _atomic_write_json(config_path, config)

    console.print(f"[green]Set[/green] [cyan]{key}[/cyan] = [yellow]{coerced!r}[/yellow]")


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


# -- Migrate commands --
migrate_app = typer.Typer(help="Migrate workspaces from other agent frameworks")
app.add_typer(migrate_app, name="migrate", rich_help_panel="Extensions")


@migrate_app.command("openclaw")
def migrate_openclaw(
    path: str = typer.Argument(help="Path to the OpenClaw workspace directory"),
    business: str = typer.Option(..., "--business", "-b", help="Target business name"),
):
    """Migrate an OpenClaw workspace into a Merkaba business directory."""
    from pathlib import Path as _Path

    from merkaba.plugins.importer_openclaw import OpenClawMigrator

    workspace = _Path(path).expanduser().resolve()
    if not workspace.is_dir():
        console.print(f"[red]Error:[/red] Not a directory: {workspace}")
        raise typer.Exit(1)

    migrator = OpenClawMigrator()
    if not migrator.detect(workspace):
        console.print(f"[red]Error:[/red] Not an OpenClaw workspace: {workspace}")
        raise typer.Exit(1)

    result = migrator.migrate(workspace, business)

    if result.migrated:
        console.print(f"[bold green]Migrated {len(result.migrated)} file(s):[/bold green]")
        for f in result.migrated:
            console.print(f"  {f}")

    if result.skipped:
        console.print(f"[yellow]Skipped {len(result.skipped)} file(s):[/yellow]")
        for f in result.skipped:
            console.print(f"  {f}")

    if result.errors:
        console.print(f"[red]Errors ({len(result.errors)}):[/red]")
        for e in result.errors:
            console.print(f"  {e}")
        raise typer.Exit(1)

    if not result.migrated and not result.skipped:
        console.print("[dim]No files found in workspace.[/dim]")
    else:
        console.print(f"\n[green]Migration complete.[/green] Business: [cyan]{business}[/cyan]")


# -- Identity commands --
identity_app = typer.Typer(help="Import and export agent identity (AIEOS format)")
app.add_typer(identity_app, name="identity", rich_help_panel="Extensions")


@identity_app.command("import")
def identity_import(
    path: str = typer.Argument(help="Path to AIEOS v1.1 JSON file"),
    business: str = typer.Option(..., "--business", "-b", help="Target business name"),
):
    """Import an AIEOS v1.1 identity file into a Merkaba business."""
    from pathlib import Path as _Path

    from merkaba.identity.aieos import import_aieos

    aieos_path = _Path(path).expanduser().resolve()
    if not aieos_path.is_file():
        console.print(f"[red]Error:[/red] File not found: {aieos_path}")
        raise typer.Exit(1)

    result = import_aieos(aieos_path, business)

    if result.success:
        console.print(f"[green]Identity imported successfully.[/green]")
        console.print(f"  SOUL.md: [cyan]{result.soul_md_path}[/cyan]")
        console.print(f"  Business: [cyan]{business}[/cyan]")
    else:
        console.print("[red]Import failed:[/red]")
        for e in result.errors:
            console.print(f"  {e}")
        raise typer.Exit(1)


@identity_app.command("export")
def identity_export(
    business: str = typer.Option(..., "--business", "-b", help="Business name to export"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path (default: ./<business>.aieos.json)"),
):
    """Export a Merkaba business identity as AIEOS v1.1 JSON."""
    from pathlib import Path as _Path

    from merkaba.identity.aieos import export_aieos

    output_path = _Path(output).expanduser().resolve() if output else _Path(f"{business}.aieos.json").resolve()

    result = export_aieos(business, output_path=output_path)

    if result.success:
        console.print(f"[green]Identity exported successfully.[/green]")
        console.print(f"  Output: [cyan]{result.output_path}[/cyan]")
        console.print(f"  Business: [cyan]{business}[/cyan]")
    else:
        console.print("[red]Export failed:[/red]")
        for e in result.errors:
            console.print(f"  {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
