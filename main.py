print("🚀 Deploying Wildy Bot version 2.0")
from flask import Flask
import threading

app = Flask('')

@app.route('/')
def home():
    return "Wildy Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run_web).start()

import discord
from discord.ext import commands, tasks
import aiohttp, asyncio, json
from datetime import datetime, timezone

EVENT_API = "https://wilderness.spegal.dev/api/"
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
        try:
            async with s.get(EVENT_API) as r:
                if r.status == 200:
                    # Try JSON parsing safely
                    try:
                        return await r.json(content_type=None)
                    except Exception:
                        text = await r.text()
                        print(f"[fetch_event] Non-JSON response: {text[:200]}...")
                        return None
                else:
                    print(f"[fetch_event] HTTP error {r.status}")
        except Exception as e:
            print(f"[fetch_event] Exception: {e}")
    return None

def make_embed(data):
    cur = data.get("current", "Unknown")
    nxt = data.get("next", "Unknown")
    nxt_time = data.get("next_time", "")
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

@bot.tree.command(name="wildy_enable", description="Enable Wildy event notifications in this channel")
async def wildy_enable(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    guilds_cfg[guild_id] = {
        "channel_id": interaction.channel_id,
        "enabled": True
    }
    save_config(guilds_cfg)
    await interaction.response.send_message("✅ Notifications enabled in this channel.", ephemeral=True)

@bot.tree.command(name="wildy_stop", description="Stop Wildy event notifications for this server")
async def wildy_stop(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    if guild_id in guilds_cfg:
        guilds_cfg[guild_id]["enabled"] = False
        save_config(guilds_cfg)
    await interaction.response.send_message("🛑 Notifications disabled.", ephemeral=True)

@bot.tree.command(name="wildy_notify", description="Send an immediate Wildy event update")
async def wildy_notify(interaction: discord.Interaction):
    print("DEBUG: wildy_notify command called")
    data = await fetch_event()
    if not data:
        print("DEBUG: fetch_event returned None or failed")
        await interaction.response.send_message("⚠️ Could not fetch event data.", ephemeral=True)
        return

    print("DEBUG: API Data =", data)
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
    await asyncio.sleep(5)  # wait a few seconds before syncing

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash commands with Discord.")
        for cmd in synced:
            print(f" → /{cmd.name} — {cmd.description}")
    except Exception as e:
        print(f"❌ Command sync error: {e}")

    hourly_update.start()

import os
TOKEN = os.getenv("DISCORD_TOKEN")  # use Render/Replit secret
bot.run(TOKEN)
