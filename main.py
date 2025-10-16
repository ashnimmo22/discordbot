import discord
from discord.ext import commands, tasks
import aiohttp, asyncio, json
from datetime import datetime, timezone

EVENT_API = "https://wilderness.spegal.dev/api/events"
CONFIG_FILE = "guild_config.json"

# ---- Helper functions --------------------------------------------------------

def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

async def fetch_event():
    async with aiohttp.ClientSession() as s:
        async with s.get(EVENT_API) as r:
            if r.status == 200:
                return await r.json()
    return None

def make_embed(data):
    cur = data.get("current_event", "Unknown")
    nxt = data.get("next_event", "Unknown")
    nxt_time = data.get("next_event_time", "")
    try:
        t = datetime.fromisoformat(nxt_time.replace("Z", "+00:00"))
        formatted = t.strftime("%H:%M UTC")
    except Exception:
        formatted = "Unknown"
    e = discord.Embed(title="🌋 Wilderness Flash Events", color=0xFF6600)
    e.add_field(name="Current", value=cur, inline=False)
    e.add_field(name="Next", value=f"{nxt} — {formatted}", inline=False)
    e.set_footer(text="Data: wilderness.spegal.dev | Auto update at :55 UTC")
    return e

# ---- Bot setup ---------------------------------------------------------------

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

guilds_cfg = load_config()

# ---- Slash commands ----------------------------------------------------------

@bot.tree.command(description="Enable Wildy event notifications in this channel")
async def enable(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    guilds_cfg[guild_id] = {
        "channel_id": interaction.channel_id,
        "enabled": True
    }
    save_config(guilds_cfg)
    await interaction.response.send_message("✅ Notifications enabled in this channel.", ephemeral=True)

@bot.tree.command(description="Stop Wildy event notifications for this server")
async def stop(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    if guild_id in guilds_cfg:
        guilds_cfg[guild_id]["enabled"] = False
        save_config(guilds_cfg)
    await interaction.response.send_message("🛑 Notifications disabled.", ephemeral=True)

@bot.tree.command(description="Send an immediate Wildy event update")
async def notify(interaction: discord.Interaction):
    data = await fetch_event()
    if not data:
        await interaction.response.send_message("⚠️ Could not fetch event data.", ephemeral=True)
        return
    embed = make_embed(data)
    await interaction.response.send_message(embed=embed)

# ---- Scheduled hourly updater ------------------------------------------------

@tasks.loop(minutes=1)
async def hourly_update():
    """Runs every minute; posts updates at HH:55 UTC."""
    now = datetime.now(timezone.utc)
    if now.minute == 55:          # 55th minute
        data = await fetch_event()
        if not data:
            return
        embed = make_embed(data)
        for g_id, cfg in guilds_cfg.items():
            if cfg.get("enabled"):
                ch = bot.get_channel(cfg["channel_id"])
                if ch:
                    try:
                        await ch.send(embed=embed)
                    except Exception as e:
                        print(f"Failed to send to guild {g_id}: {e}")

@hourly_update.before_loop
async def before_loop():
    await bot.wait_until_ready()

# ---- Run ---------------------------------------------------------------------

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} — tracking {len(guilds_cfg)} servers.")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print("Command sync error:", e)
    hourly_update.start()

import os
TOKEN = os.getenv("DISCORD_TOKEN")  # use Render/Replit secret
bot.run(TOKEN)
