"""Discord integration adapter.

Uses discord.py (optional dependency) to send/read messages and list channels.
Bot token stored via CredentialManager. Message handling routes through
SessionPool for per-session serialization.
"""

import asyncio
import logging
from dataclasses import dataclass, field

from merkaba.integrations.base import IntegrationAdapter, register_adapter
from merkaba.integrations.credentials import CredentialManager

logger = logging.getLogger(__name__)

REQUIRED_CREDENTIALS = ["bot_token"]


@dataclass
class DiscordAdapter(IntegrationAdapter):
    """Adapter for Discord via discord.py.

    Actions:
        send_message  -- params: channel_id (int), text (str)
        read_messages -- params: channel_id (int), limit (int, default 10)
        list_channels -- params: guild_id (int, optional)
    """

    _creds: CredentialManager = field(
        default_factory=CredentialManager, init=False, repr=False
    )
    _bot: object = field(default=None, init=False, repr=False)
    _loop: object = field(default=None, init=False, repr=False)
    _pool: object = field(default=None, init=False, repr=False)

    def connect(self) -> bool:
        """Validate credentials and create the discord.py Bot instance.

        Does NOT start the event loop -- call run() or use connect() as a
        readiness check before execute().
        """
        ok, missing = self._creds.has_required("discord", REQUIRED_CREDENTIALS)
        if not ok:
            logger.warning("Discord adapter missing credentials: %s", missing)
            self._connected = False
            return False

        try:
            import discord
            from discord.ext import commands
        except ImportError:
            logger.error("discord.py not installed -- run: pip install discord.py")
            self._connected = False
            return False

        token = self._creds.get("discord", "bot_token")
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True

        self._bot = commands.Bot(command_prefix="!", intents=intents)
        self._bot._token = token  # stored for run() / health_check
        self._connected = True
        return True

    def disconnect(self) -> None:
        """Close the bot connection if active."""
        if self._bot is not None:
            try:
                loop = self._bot.loop
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(self._bot.close(), loop)
            except Exception as e:
                logger.debug("Error during disconnect: %s", e)
        self._connected = False

    def execute(self, action: str, params: dict | None = None) -> dict:
        params = params or {}
        actions = {
            "send_message": self._send_message,
            "read_messages": self._read_messages,
            "list_channels": self._list_channels,
        }
        handler = actions.get(action)
        if not handler:
            return {"ok": False, "error": f"Unknown action: {action}"}
        return handler(params)

    def health_check(self) -> dict:
        if not self._connected or not self._bot:
            return {"ok": False, "adapter": "discord", "error": "Not connected"}
        try:
            # If the bot has logged in, user will be set
            user = self._bot.user
            if user:
                return {
                    "ok": True,
                    "adapter": "discord",
                    "user": str(user),
                    "guilds": len(self._bot.guilds),
                }
            # Connected but not yet logged in
            return {"ok": True, "adapter": "discord", "status": "initialized"}
        except Exception as e:
            return {"ok": False, "adapter": "discord", "error": str(e)}

    # -- Session helpers --------------------------------------------------

    @staticmethod
    def build_session_id(
        user_id: str | int,
        channel_id: str | int | None = None,
        business_id: str | int | None = None,
    ) -> str:
        """Build a session ID following the Merkaba convention.

        Format: discord:<user_id>[:topic:<channel_id>][:biz:<business_id>]
        """
        from merkaba.orchestration.session import build_session_id

        return build_session_id(
            "discord",
            str(user_id),
            topic_id=str(channel_id) if channel_id else None,
            business_id=str(business_id) if business_id else None,
        )

    def setup_message_handler(self, pool=None):
        """Wire the on_message event to route through SessionPool.

        Call after connect() to enable inbound message routing. If no pool
        is provided, a new SessionPool is created.

        This installs the handler on self._bot. Start the bot with
        self._bot.run(token) or self.run().
        """
        if self._bot is None:
            raise RuntimeError("Call connect() before setup_message_handler()")

        if pool is None:
            from merkaba.orchestration.session_pool import SessionPool

            pool = SessionPool()
        self._pool = pool

        @self._bot.event
        async def on_message(message):
            # Ignore own messages
            if message.author == self._bot.user:
                return

            # Process commands first (if any registered with the bot)
            await self._bot.process_commands(message)

            # Skip command messages
            ctx = await self._bot.get_context(message)
            if ctx.valid:
                return

            user_id = str(message.author.id)
            channel_id = str(message.channel.id)
            session_id = self.build_session_id(user_id, channel_id)

            try:
                response = await pool.submit(session_id, message.content)
                await message.channel.send(response)
            except Exception as e:
                logger.error("Error processing Discord message: %s", e)
                await message.channel.send(
                    "Sorry, something went wrong processing your message."
                )

    def run(self):
        """Start the bot (blocking). Call after connect() + setup_message_handler()."""
        if not self._connected or not self._bot:
            raise RuntimeError("Call connect() before run()")
        token = self._creds.get("discord", "bot_token")
        self._bot.run(token)

    # -- Private action handlers ------------------------------------------

    def _send_message(self, params: dict) -> dict:
        try:
            channel_id = params["channel_id"]
            text = params["text"]
        except KeyError as e:
            return {"ok": False, "error": f"Missing required parameter: {e}"}

        try:
            channel = self._bot.get_channel(int(channel_id))
            if channel is None:
                return {"ok": False, "error": f"Channel {channel_id} not found"}

            # Run coroutine in the bot's event loop
            loop = self._bot.loop
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    channel.send(text), loop
                )
                msg = future.result(timeout=10)
                return {"ok": True, "message_id": str(msg.id)}
            else:
                return {"ok": False, "error": "Bot event loop not running"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _read_messages(self, params: dict) -> dict:
        try:
            channel_id = params["channel_id"]
        except KeyError as e:
            return {"ok": False, "error": f"Missing required parameter: {e}"}

        limit = params.get("limit", 10)

        try:
            channel = self._bot.get_channel(int(channel_id))
            if channel is None:
                return {"ok": False, "error": f"Channel {channel_id} not found"}

            loop = self._bot.loop
            if loop and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._fetch_messages(channel, limit), loop
                )
                messages = future.result(timeout=10)
                return {"ok": True, "messages": messages}
            else:
                return {"ok": False, "error": "Bot event loop not running"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @staticmethod
    async def _fetch_messages(channel, limit: int) -> list[dict]:
        """Fetch message history from a channel."""
        messages = []
        async for msg in channel.history(limit=limit):
            messages.append(
                {
                    "id": str(msg.id),
                    "author": str(msg.author),
                    "content": msg.content,
                    "timestamp": msg.created_at.isoformat(),
                }
            )
        return messages

    def _list_channels(self, params: dict) -> dict:
        try:
            guild_id = params.get("guild_id")
            if guild_id:
                guild = self._bot.get_guild(int(guild_id))
                if guild is None:
                    return {"ok": False, "error": f"Guild {guild_id} not found"}
                guilds = [guild]
            else:
                guilds = self._bot.guilds

            channels = []
            for guild in guilds:
                for ch in guild.text_channels:
                    channels.append(
                        {
                            "id": str(ch.id),
                            "name": ch.name,
                            "guild": guild.name,
                            "guild_id": str(guild.id),
                        }
                    )
            return {"ok": True, "channels": channels}
        except Exception as e:
            return {"ok": False, "error": str(e)}


register_adapter("discord", DiscordAdapter)
