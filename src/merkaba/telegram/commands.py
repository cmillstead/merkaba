# src/friday/telegram/commands.py
"""Telegram command handlers for Friday."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from friday.research import ApifyClient, ResearchDatabase, analyze_listings
from friday.listing import ListingConfig, EtsyClient, EtsyClientError

logger = logging.getLogger(__name__)


async def handle_research(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /research command."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /research <query>\n"
            "Example: /research boho floral clipart"
        )
        return

    query = " ".join(context.args)
    await update.message.reply_text(f"Searching: {query}")

    try:
        client = ApifyClient()
        await update.message.reply_text("Fetching listings from Etsy...")

        listings = client.search_etsy(query, max_results=50)
        await update.message.reply_text(f"Found {len(listings)} listings, analyzing...")

        metrics = analyze_listings(listings, len(listings))

        # Save to database
        db = ResearchDatabase()
        try:
            run_id = db.save_run(
                query=query,
                listing_count=len(listings),
                opportunity_score=metrics["opportunity_score"],
            )
            db.save_listings(run_id, listings)
            db.save_metrics(run_id, metrics)
        finally:
            db.close()

        # Format response
        score = metrics["opportunity_score"]
        if score >= 60:
            verdict = "Good opportunity"
        elif score >= 40:
            verdict = "Moderate opportunity"
        else:
            verdict = "Low opportunity"

        response = (
            f"Research complete!\n\n"
            f"Score: {score:.1f} - {verdict}\n"
            f"Listings analyzed: {len(listings)}\n"
            f"Avg price: ${metrics['avg_price']:.2f}\n"
            f"Price range: ${metrics['price_min']:.2f} - ${metrics['price_max']:.2f}\n\n"
            f"Run ID: #{run_id}"
        )
        await update.message.reply_text(response)

    except Exception as e:
        logger.error(f"Research failed: {e}")
        await update.message.reply_text("Research failed. Please try again later.")


async def handle_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /generate command."""
    if not context.args:
        await update.message.reply_text(
            "Usage: /generate <prompt>\n"
            "Example: /generate boho flowers watercolor"
        )
        return

    prompt = " ".join(context.args)
    await update.message.reply_text(f"Generating: {prompt}\n(This may take a while...)")

    # TODO: Implement image generation with progress
    await update.message.reply_text("Image generation not yet implemented in Telegram")


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command."""
    # TODO: Implement task cancellation
    await update.message.reply_text("No active tasks to cancel")


async def handle_listing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /listing commands."""
    if not context.args:
        await update.message.reply_text(
            "Usage:\n"
            "/listing auth - Check auth status\n"
            "/listing list - Show shop listings\n"
            "/listing create - Create from latest bundle"
        )
        return

    subcommand = context.args[0].lower()
    config = ListingConfig()

    if subcommand == "auth":
        tokens = config.get_tokens()
        if not tokens:
            await update.message.reply_text(
                "Not authenticated with Etsy\n\n"
                "Run `friday listing auth` in terminal to authenticate"
            )
        elif config.is_token_expired():
            await update.message.reply_text("Etsy token expired. Re-authenticate in terminal.")
        else:
            shop_id = config.get_shop_id()
            await update.message.reply_text(f"Authenticated with Etsy\nShop ID: {shop_id}")

    elif subcommand == "list":
        tokens = config.get_tokens()
        if not tokens or config.is_token_expired():
            await update.message.reply_text("Not authenticated. Run /listing auth first.")
            return

        try:
            client = EtsyClient(access_token=tokens["access_token"])
            shop_id = config.get_shop_id()
            listings = client.list_listings(shop_id=shop_id, limit=10)

            if not listings:
                await update.message.reply_text("No listings found")
                return

            response = "Your Listings:\n\n"
            for l in listings:
                state_indicator = "[draft]" if l.get("state") == "draft" else ""
                response += f"- {l.get('title', 'Untitled')[:40]} {state_indicator}\n"

            await update.message.reply_text(response)

        except EtsyClientError as e:
            await update.message.reply_text(f"Error: {e}")

    elif subcommand == "create":
        await update.message.reply_text(
            "Listing creation via Telegram coming soon.\n"
            "Use `friday listing create <bundle>` in terminal for now."
        )

    else:
        await update.message.reply_text(f"Unknown subcommand: {subcommand}")
