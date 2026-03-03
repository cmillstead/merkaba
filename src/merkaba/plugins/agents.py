# src/merkaba/plugins/agents.py
"""Agent configuration loading and management."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import frontmatter

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """An agent configuration loaded from a plugin."""

    name: str
    description: str
    model: str
    system_prompt: str
    max_iterations: int = 10
    plugin_name: str = ""

    @classmethod
    def from_markdown(cls, markdown: str, plugin_name: str = "") -> "AgentConfig":
        """Parse an agent config from markdown with frontmatter."""
        post = frontmatter.loads(markdown)
        return cls(
            name=post.get("name", "unnamed"),
            description=post.get("description", ""),
            model=post.get("model", "qwen3.5:122b"),
            system_prompt=post.content,
            max_iterations=post.get("max_iterations", 10),
            plugin_name=plugin_name,
        )

    @classmethod
    def from_file(cls, path: Path, plugin_name: str = "") -> "AgentConfig":
        """Load an agent config from a markdown file."""
        with open(path) as f:
            return cls.from_markdown(f.read(), plugin_name)


@dataclass
class AgentManager:
    """Manages agent configuration loading and retrieval."""

    agents: dict[str, AgentConfig] = field(default_factory=dict)

    def load_from_directory(self, plugins_dir: str):
        """Load all agent configs from a plugins directory."""
        plugins_path = Path(plugins_dir)
        if not plugins_path.exists():
            return

        for plugin_dir in plugins_path.iterdir():
            if not plugin_dir.is_dir():
                continue

            agents_dir = plugin_dir / "agents"
            if not agents_dir.exists():
                continue

            plugin_name = plugin_dir.name
            for agent_file in agents_dir.glob("*.md"):
                try:
                    agent = AgentConfig.from_file(agent_file, plugin_name)
                    self.agents[agent.name] = agent
                except Exception as e:
                    logger.warning("Failed to load agent %s: %s", agent_file, e)

    def get(self, name: str) -> AgentConfig | None:
        """Get an agent config by name."""
        return self.agents.get(name)

    def list_agents(self) -> list[str]:
        """List all loaded agent names."""
        return list(self.agents.keys())
