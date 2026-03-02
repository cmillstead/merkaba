# src/merkaba/init.py
"""Merkaba onboarding wizard — ``merkaba init``."""

import json
import os
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from merkaba.config.prompts import DEFAULT_SOUL, DEFAULT_USER

MERKABA_DIR = Path(os.path.expanduser("~/.merkaba"))

DEFAULT_CONFIG = {
    "models": {
        "simple": "qwen3:8b",
        "complex": "qwen3.5:122b",
    },
    "rate_limiting": {
        "max_concurrent": 2,
        "queue_depth_warning": 5,
    },
}

REQUIRED_MODELS = {
    "simple": "qwen3:8b",
    "complex": "qwen3.5:122b",
    "classifier": "qwen3:4b",
}

MODEL_DESCRIPTIONS = {
    "simple": "Fast responses, routing, classification",
    "complex": "Deep reasoning, tool use, long tasks",
    "classifier": "Safety checks, complexity routing",
}


@dataclass
class ModelStatus:
    """Result of Ollama availability and model check."""

    available: bool
    installed_models: list[str] = field(default_factory=list)
    missing_models: list[str] = field(default_factory=list)


def check_ollama() -> ModelStatus:
    """Check Ollama availability and installed models."""
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
    except Exception:
        return ModelStatus(
            available=False,
            missing_models=list(REQUIRED_MODELS.values()),
        )

    installed = [m["name"] for m in data.get("models", [])]
    installed_set = set(installed)
    missing = [m for m in REQUIRED_MODELS.values() if m not in installed_set]

    return ModelStatus(
        available=True,
        installed_models=installed,
        missing_models=missing,
    )


def pull_model(model: str) -> bool:
    """Pull an Ollama model. Returns True on success."""
    print(f"\n  Pulling {model}... (this may take a few minutes)\n")
    result = subprocess.run(
        ["ollama", "pull", model],
        # Let stdout/stderr pass through so the user sees progress
    )
    return result.returncode == 0


class FileAction(Enum):
    """Result of a file safety check."""

    WRITE = "write"
    SKIP = "skip"
    BACKUP = "backup"


def check_file_safety(
    path: Path,
    default_content: str,
    *,
    force: bool = False,
) -> FileAction:
    """Check if a file can be safely written.

    Returns:
        WRITE if the file is missing or matches the default.
        SKIP if user chose to skip.
        BACKUP if user chose to backup (or --force was used).
    """
    if not path.exists():
        return FileAction.WRITE

    existing = path.read_text(encoding="utf-8")
    if existing.strip() == default_content.strip():
        return FileAction.WRITE

    # File has been user-edited
    if force:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        return FileAction.BACKUP

    print(f"\n  {path.name} has been customized.")
    choice = input("  [o]verwrite / [s]kip / [b]ackup and overwrite? ").strip().lower()

    if choice == "b":
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        return FileAction.BACKUP
    elif choice == "o":
        return FileAction.WRITE
    else:
        return FileAction.SKIP


def run_preflight(*, force: bool = False) -> ModelStatus:
    """Phase 1: Check prerequisites, create dirs, seed defaults.

    Returns ModelStatus so the caller knows if the interview can run.
    """
    print("\n  Setting up Merkaba...\n")

    # 1. Create directories
    for subdir in ("logs", "conversations", "plugins"):
        (MERKABA_DIR / subdir).mkdir(parents=True, exist_ok=True)

    # 2. Seed config.json
    config_path = MERKABA_DIR / "config.json"
    action = check_file_safety(config_path, json.dumps(DEFAULT_CONFIG, indent=2), force=force)
    if action != FileAction.SKIP:
        config_path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        print(f"  Created {config_path}")

    # 3. Seed SOUL.md
    soul_path = MERKABA_DIR / "SOUL.md"
    action = check_file_safety(soul_path, DEFAULT_SOUL, force=force)
    if action != FileAction.SKIP:
        soul_path.write_text(DEFAULT_SOUL, encoding="utf-8")
        print(f"  Created {soul_path}")

    # 4. Seed USER.md
    user_path = MERKABA_DIR / "USER.md"
    action = check_file_safety(user_path, DEFAULT_USER, force=force)
    if action != FileAction.SKIP:
        user_path.write_text(DEFAULT_USER, encoding="utf-8")
        print(f"  Created {user_path}")

    # 5. Check Ollama and models
    status = check_ollama()
    if not status.available:
        print("\n  Ollama is not running.")
        print("  Start it with: ollama serve\n")
    else:
        print("\n  Ollama is running.")
        _print_model_inventory(status)

    return status


class InterviewDepth(Enum):
    """Interview depth level."""

    QUICK = "quick"        # 3-4 questions
    MEDIUM = "medium"      # 5-8 questions
    DEEP = "deep"          # 8-12 questions


INTERVIEW_TOPICS = {
    InterviewDepth.QUICK: [
        "name and who they are",
        "what they're building or working on",
        "what they want Merkaba to help with",
    ],
    InterviewDepth.MEDIUM: [
        "name and who they are",
        "what they're building or working on",
        "what they want Merkaba to help with",
        "communication style preferences",
        "work schedule and timezone",
        "how they want to be challenged or pushed back on",
    ],
    InterviewDepth.DEEP: [
        "name and who they are",
        "what they're building or working on",
        "what they want Merkaba to help with",
        "communication style preferences",
        "work schedule and timezone",
        "how they want to be challenged or pushed back on",
        "core values and principles",
        "decision-making style",
        "pet peeves and things to avoid",
        "long-term vision",
    ],
}

INTERVIEW_SYSTEM_PROMPT = """You are Merkaba, meeting your owner for the first time. You are conducting \
an onboarding interview to learn about them so you can be a better AI partner.

Rules:
- Ask ONE question at a time
- Be warm but concise — this is a conversation, not a form
- Adapt your follow-up questions based on their answers
- Cover these topics: {topics}
- When you've covered all topics, respond with exactly [DONE] and nothing else
- Do NOT generate the user's answers — wait for their real input"""

SYNTHESIS_PROMPT = """Based on this onboarding interview, generate two markdown documents.

Interview transcript:
{transcript}

Generate output in EXACTLY this format (including the SOUL: and USER: headers and the --- separator):

SOUL:
[A SOUL.md that defines Merkaba's personality tailored to this specific user. \
Include who Merkaba is, how to behave with this user, and any relevant style notes. \
Keep the core identity (autonomous AI agent, local-first, partner not servant) but \
personalize tone and priorities based on what you learned.]
---
USER:
[A USER.md that captures key facts about the owner: who they are, what they're building, \
their preferences, communication style, and goals. Be specific — use details from the interview.]"""


def run_interview(
    *,
    model: str,
    depth: InterviewDepth,
) -> tuple[str, str]:
    """Phase 2: Run LLM-driven onboarding interview.

    Returns (soul_content, user_content) for writing to SOUL.md and USER.md.
    """
    from merkaba.llm import LLMClient

    llm = LLMClient(model=model)
    topics = ", ".join(INTERVIEW_TOPICS[depth])
    system = INTERVIEW_SYSTEM_PROMPT.format(topics=topics)

    print("\n  Let's get to know each other.\n")

    transcript: list[str] = []
    conversation: list[dict] = []

    # Kick off: ask the LLM for its first question
    response = llm.chat("Begin the interview.", system_prompt=system)
    print(f"  Merkaba: {response.content}\n")
    conversation.append({"role": "assistant", "content": response.content})

    while True:
        answer = input("  You: ")
        if not answer.strip():
            continue

        transcript.append(f"Merkaba: {conversation[-1]['content']}")
        transcript.append(f"User: {answer}")

        # Send the full conversation context
        conversation.append({"role": "user", "content": answer})
        msg = "\n".join(f"{m['role']}: {m['content']}" for m in conversation)
        response = llm.chat(msg, system_prompt=system)

        if "[DONE]" in response.content:
            break

        print(f"\n  Merkaba: {response.content}\n")
        conversation.append({"role": "assistant", "content": response.content})

    # Synthesis
    print("\n  Generating your personalized configuration...\n")
    full_transcript = "\n".join(transcript)
    synthesis = llm.chat(
        SYNTHESIS_PROMPT.format(transcript=full_transcript),
    )

    # Parse SOUL: ... --- USER: ...
    content = synthesis.content
    if "SOUL:" in content and "USER:" in content:
        parts = content.split("---", 1)
        soul = parts[0].replace("SOUL:", "", 1).strip()
        user = parts[1].replace("USER:", "", 1).strip() if len(parts) > 1 else ""
    else:
        # Fallback: use entire response as soul, keep default user
        soul = content.strip()
        user = DEFAULT_USER.strip()

    return soul, user


def _print_model_inventory(status: ModelStatus) -> None:
    """Print model availability table."""
    print("\n  Merkaba uses three models:\n")
    for role, model in REQUIRED_MODELS.items():
        desc = MODEL_DESCRIPTIONS[role]
        installed = model in status.installed_models
        marker = "+" if installed else "-"
        print(f"    {marker} {role.capitalize():12s} ({model:20s})  {desc}")

    if status.missing_models:
        print("\n  To install missing models:")
        for model in status.missing_models:
            print(f"    ollama pull {model}")
    print()
