import discord
from discord import app_commands
import requests
import yaml
import time

# ---------- LOAD CONFIG ---------- #
with open("config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

TOKEN = cfg["discord"]["token"]
LOG_CHANNEL_ID = cfg["discord"]["log_channel_id"]
ALLOWED_CHANNEL_ID = cfg["discord"]["allowed_channel_id"]
GUILD_ID = cfg["discord"]["guild_id"]  # add your guild/server ID here

API_URL = cfg["api"]["url"]
API_KEY = cfg["api"]["key"]

SERVICES = cfg["services"]
ROLES = cfg["roles"]

# ---------- ROLE LIMITS ---------- #
ROLE_LIMITS = {
    "free":   {"views": 100,  "likes": 10,  "shares": 10,  "follows": 0},
    "bronze": {"views": 3000, "likes": 200, "shares": 200, "follows": 0},
    "silver": {"views": 7000, "likes": 500, "shares": 500, "follows": 0},
}

# ---------- COOLDOWN PER COMMAND ---------- #
COOLDOWNS = {
    "jviews": 300,      # 5 minutes
    "jlikes": 300,      # 5 minutes
    "jshares": 3600,    # 1 hour
    "jfollow": 86400    # 1 day
}
user_cooldowns = {cmd: {} for cmd in COOLDOWNS.keys()}

# ---------- DISCORD ---------- #
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# ---------- HELPERS ---------- #
def get_user_tier(member: discord.Member):
    role_names = [r.name for r in member.roles]
    if ROLES["silver"] in role_names:
        return "silver"
    if ROLES["bronze"] in role_names:
        return "bronze"
    if ROLES["free"] in role_names:
        return "free"
    return None

def place_order(service_id, link, quantity):
    payload = {
        "key": API_KEY,
        "action": "add",
        "service": service_id,
        "link": link,
        "quantity": quantity
    }
    r = requests.post(API_URL, data=payload, timeout=20)
    return r.json()

async def send_log(interaction, tier, service, quantity, link, order_id):
    channel = interaction.client.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return

    embed = discord.Embed(
        title="📦 JEET Order Logged",
        color=discord.Color.purple()
    )
    embed.add_field(name="User", value=f"{interaction.user} (`{interaction.user.id}`)", inline=False)
    embed.add_field(name="Role", value=tier.capitalize(), inline=True)
    embed.add_field(name="Service", value=service.capitalize(), inline=True)
    embed.add_field(name="Quantity", value=str(quantity), inline=True)
    embed.add_field(name="Link", value=link, inline=False)
    embed.add_field(name="Order ID", value=str(order_id), inline=False)
    embed.set_footer(text="JEET ")
    await channel.send(embed=embed)

def format_time(seconds):
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    parts = []
    if d > 0: parts.append(f"{d}d")
    if h > 0: parts.append(f"{h}h")
    if m > 0: parts.append(f"{m}m")
    if s > 0: parts.append(f"{s}s")
    return ' '.join(parts) if parts else "0s"

# ---------- CORE PROCESS ---------- #
async def process(interaction: discord.Interaction, service_key: str, command_name: str):
    # ----- CHANNEL CHECK ----- #
    if interaction.channel.id != ALLOWED_CHANNEL_ID:
        await interaction.response.send_message(
            f"❌ Commands can only be used in <#{ALLOWED_CHANNEL_ID}>",
            ephemeral=True
        )
        return

    tier = get_user_tier(interaction.user)
    if not tier:
        await interaction.response.send_message(
            "❌ You do not have access to JEET services.",
            ephemeral=True
        )
        return

    # ----- PER-COMMAND COOLDOWN ----- #
    user_id = interaction.user.id
    now = time.time()
    last_used = user_cooldowns[command_name].get(user_id, 0)
    cd_time = COOLDOWNS[command_name]
    if now - last_used < cd_time:
        await interaction.response.send_message(
            f"⏳ Cooldown Active for `{command_name}`",
            ephemeral=True
        )
        return
    user_cooldowns[command_name][user_id] = now

    qty = ROLE_LIMITS[tier][service_key]
    if qty == 0:
        await interaction.response.send_message(
            "❌ This service is not available for your tier.",
            ephemeral=True
        )
        return

    service_id = SERVICES[service_key]
    link = interaction.data["options"][0]["value"]

    # Public order message
    await interaction.response.send_message(
        f"⏳ **Placing Order...**\nService: `{service_key}`\nQuantity: `{qty}`"
    )

    result = place_order(service_id, link, qty)

    if "order" in result:
        order_id = result["order"]
        await interaction.edit_original_response(
            content=(
                f"✅ **Order Placed Successfully**\n"
                f"👤 User: {interaction.user.mention}\n"
                f"📌 Service: `{service_key}`\n"
                f"📦 Quantity: `{qty}`\n"
                f"🆔 Order ID: `{order_id}`"
            )
        )
        await send_log(interaction, tier, service_key, qty, link, order_id)
    else:
        await interaction.edit_original_response(
            content=f"❌ **Order Failed**\n```{result}```"
        )

# ---------- COMMANDS ---------- #
@tree.command(name="jviews", description="Send TikTok views")
async def jviews(interaction: discord.Interaction, link: str):
    await process(interaction, "views", "jviews")

@tree.command(name="jlikes", description="Send TikTok likes")
async def jlikes(interaction: discord.Interaction, link: str):
    await process(interaction, "likes", "jlikes")

@tree.command(name="jshares", description="Send TikTok shares")
async def jshares(interaction: discord.Interaction, link: str):
    await process(interaction, "shares", "jshares")

@tree.command(name="jfollow", description="Send TikTok followers")
async def jfollow(interaction: discord.Interaction, link: str):
    await process(interaction, "follows", "jfollow")

# ---------- NEW COMMANDS ---------- #
@tree.command(name="jhelp", description="Shows all JEET commands and usage")
async def jhelp(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 JEET Bot Commands", color=discord.Color.purple())
    embed.add_field(name="/jviews <link>", value="Send TikTok views", inline=False)
    embed.add_field(name="/jlikes <link>", value="Send TikTok likes", inline=False)
    embed.add_field(name="/jshares <link>", value="Send TikTok shares", inline=False)
    embed.add_field(name="/jfollow <link>", value="Send TikTok followers", inline=False)
    embed.add_field(name="/jstatus", value="Shows cooldown left for each command for you", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="jstatus", description="Shows your cooldowns for JEET commands")
async def jstatus(interaction: discord.Interaction):
    now = time.time()
    status_lines = []
    for cmd, cd_dict in user_cooldowns.items():
        last_used = cd_dict.get(interaction.user.id, 0)
        remaining = COOLDOWNS[cmd] - (now - last_used)
        if remaining > 0:
            status_lines.append(f"`{cmd}`: {format_time(int(remaining))}")
        else:
            status_lines.append(f"`{cmd}`: Ready")
    embed = discord.Embed(title=f"⏱ {interaction.user.display_name} Cooldowns", color=discord.Color.purple())
    embed.description = "\n".join(status_lines)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- READY ---------- #
GUILD_ID = 1451871483222823027  # Replace with your Discord server ID

@client.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await tree.sync(guild=guild)
    print(f"JEET Bot Online as {client.user}")

client.run(TOKEN)
