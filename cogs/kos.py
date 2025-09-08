import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import datetime
import pytz

# ---------- CONFIG ----------
KOS_CHANNEL_ID = 1414380691994447912
KOS_REQUEST_CHANNEL_ID = 1414435650790359160
MOD_LOG_CHANNEL_ID = 1414435845615910933
ROLE_KOS_ADD = 1414436081444847667
ROLE_KOS_REQUEST = 1414369081405997178
ROLE_KOS_REVIEW = 1414369811022086144
TIMEZONE = pytz.timezone("America/Boise")
# ----------------------------


# ---------- Database Helpers ----------
class KOSDB:
    @staticmethod
    async def add(username: str, reason: str, message_id: int):
        timestamp = int(datetime.datetime.now(tz=TIMEZONE).timestamp())
        async with aiosqlite.connect("kos.db") as db:
            await db.execute(
                "INSERT OR REPLACE INTO kos (username, timestamp, message_id, reason) VALUES (?, ?, ?, ?)",
                (username, timestamp, message_id, reason)
            )
            await db.commit()

    @staticmethod
    async def remove(username: str):
        async with aiosqlite.connect("kos.db") as db:
            await db.execute("DELETE FROM kos WHERE lower(username) = lower(?)", (username,))
            await db.commit()

    @staticmethod
    async def get(username: str):
        async with aiosqlite.connect("kos.db") as db:
            async with db.execute(
                "SELECT username, timestamp, message_id, reason FROM kos WHERE lower(username) = lower(?)",
                (username,)
            ) as cursor:
                return await cursor.fetchone()


# ---------- Group ----------
class KOSGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="kos", description="Kill On Sight commands")

    async def log_action(self, guild: discord.Guild, title: str, description: str, color=discord.Color.blurple()):
        channel = guild.get_channel(MOD_LOG_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title=title, description=description,
                color=color, timestamp=datetime.datetime.utcnow()
            )
            await channel.send(embed=embed)

    @app_commands.command(name="add", description="Add someone to the KOS list.")
    async def kos_add(self, interaction: discord.Interaction, username: str, reason: str):
        if ROLE_KOS_ADD not in [r.id for r in interaction.user.roles]:
            return await interaction.response.send_message(embed=discord.Embed(
                title="Permission Denied",
                description="You don't have permission to add KOS entries.",
                color=discord.Color.red()
            ), ephemeral=True)

        if await KOSDB.get(username):
            return await interaction.response.send_message(embed=discord.Embed(
                title="Already on KOS",
                description=f"**{username}** is already on the KOS list.",
                color=discord.Color.orange()
            ), ephemeral=True)

        channel = interaction.guild.get_channel(KOS_CHANNEL_ID)
        if not channel:
            return await interaction.response.send_message(embed=discord.Embed(
                title="Error",
                description="KOS channel not found.",
                color=discord.Color.red()
            ), ephemeral=True)

        now_ts = int(datetime.datetime.now(tz=TIMEZONE).timestamp())
        embed = discord.Embed(title="⚔️ KOS Notice", color=discord.Color.red())
        embed.add_field(name="Username", value=username)
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Date", value=f"<t:{now_ts}:F>")

        msg = await channel.send(embed=embed)
        await KOSDB.add(username, reason, msg.id)

        await self.log_action(interaction.guild, "KOS Added", f"{interaction.user.mention} added **{username}** for: {reason}", discord.Color.red())
        await interaction.response.send_message(embed=discord.Embed(
            title="KOS Added",
            description=f"**{username}** has been added to the KOS list.",
            color=discord.Color.green()
        ), ephemeral=True)

    @app_commands.command(name="remove", description="Remove someone from the KOS list.")
    async def kos_remove(self, interaction: discord.Interaction, username: str):
        entry = await KOSDB.get(username)
        if not entry:
            return await interaction.response.send_message(embed=discord.Embed(
                title="Not Found",
                description=f"**{username}** is not on the KOS list.",
                color=discord.Color.red()
            ), ephemeral=True)

        message_id = entry[2]
        channel = interaction.guild.get_channel(KOS_CHANNEL_ID)
        if channel:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
            except:
                pass

        await KOSDB.remove(username)
        await self.log_action(interaction.guild, "KOS Removed", f"{interaction.user.mention} removed **{username}**", discord.Color.green())
        await interaction.response.send_message(embed=discord.Embed(
            title="KOS Removed",
            description=f"**{username}** has been removed from the KOS list.",
            color=discord.Color.green()
        ), ephemeral=True)

    @app_commands.command(name="request", description="Request to add someone to KOS.")
    async def kos_request(self, interaction: discord.Interaction, username: str, reason: str, attachment: discord.Attachment = None):
        if ROLE_KOS_REQUEST not in [r.id for r in interaction.user.roles]:
            return await interaction.response.send_message(embed=discord.Embed(
                title="Permission Denied",
                description="You don't have permission to request KOS.",
                color=discord.Color.red()
            ), ephemeral=True)

        channel = interaction.guild.get_channel(KOS_REQUEST_CHANNEL_ID)
        if not channel:
            return await interaction.response.send_message(embed=discord.Embed(
                title="Error",
                description="KOS request channel not found.",
                color=discord.Color.red()
            ), ephemeral=True)

        embed = discord.Embed(title="📝 KOS Request", color=discord.Color.orange())
        embed.add_field(name="Requested By", value=interaction.user.mention, inline=True)
        embed.add_field(name="Username", value=username, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        if attachment:
            embed.set_image(url=attachment.url)

        view = KOSApprovalView(username, reason, self, requester=interaction.user)
        request_msg = await channel.send(embed=embed, view=view)
        view.message = request_msg

        await self.log_action(interaction.guild, "KOS Request Submitted", f"{interaction.user.mention} requested KOS for **{username}**", discord.Color.orange())
        await interaction.response.send_message(embed=discord.Embed(
            title="Request Sent",
            description="Your KOS request has been submitted for review.",
            color=discord.Color.orange()
        ))

    @app_commands.command(name="status", description="Check if someone is on the KOS list.")
    async def kos_status(self, interaction: discord.Interaction, username: str):
        entry = await KOSDB.get(username)
        if not entry:
            return await interaction.response.send_message(embed=discord.Embed(
                title="Not on KOS",
                description=f"**{username}** is not on the KOS list.",
                color=discord.Color.green()
            ), ephemeral=True)

        _, timestamp, _, reason = entry
        embed = discord.Embed(title="KOS Status", color=discord.Color.red())
        embed.add_field(name="Username", value=username, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Date", value=f"<t:{timestamp}:F>\n<t:{timestamp}:R>", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------- View ----------
class KOSApprovalView(discord.ui.View):
    def __init__(self, username: str, reason: str, group: KOSGroup, requester: discord.User):
        super().__init__(timeout=None)
        self.username = username
        self.reason = reason
        self.group = group
        self.requester = requester
        self.message = None  # will be assigned after sending

    @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if ROLE_KOS_REVIEW not in [r.id for r in interaction.user.roles]:
            return await interaction.response.send_message(embed=discord.Embed(
                title="Permission Denied",
                description="You don't have permission to approve requests.",
                color=discord.Color.red()
            ), ephemeral=True)

        channel = interaction.guild.get_channel(KOS_CHANNEL_ID)
        now_ts = int(datetime.datetime.now(tz=TIMEZONE).timestamp())
        embed = discord.Embed(title="⚔️ KOS Approved", color=discord.Color.red())
        embed.add_field(name="Username", value=self.username)
        embed.add_field(name="Reason", value=self.reason)
        embed.add_field(name="Approved By", value=interaction.user.mention)
        embed.add_field(name="Date", value=f"<t:{now_ts}:F>")

        msg = await channel.send(embed=embed)
        await KOSDB.add(self.username, self.reason, msg.id)

        await self.group.log_action(
            interaction.guild,
            "KOS Approved",
            f"{interaction.user.mention} approved **{self.username}** (requested by {self.requester.mention})",
            discord.Color.red()
        )

        # Edit original request message to reflect approval
        if self.message:
            approved_embed = self.message.embeds[0]
            approved_embed.title = "✅ KOS Request Approved"
            approved_embed.color = discord.Color.green()
            approved_embed.add_field(name="Reviewed By", value=interaction.user.mention, inline=False)
            await self.message.edit(embed=approved_embed, view=None)

        await interaction.response.send_message(f"{self.username} has been approved and added to the KOS list.",
                                                ephemeral=True)
        self.stop()

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if ROLE_KOS_REVIEW not in [r.id for r in interaction.user.roles]:
            return await interaction.response.send_message(embed=discord.Embed(
                title="Permission Denied",
                description="You don't have permission to deny requests.",
                color=discord.Color.red()
            ), ephemeral=True)

        await self.group.log_action(
            interaction.guild,
            "KOS Denied",
            f"{interaction.user.mention} denied KOS for **{self.username}**",
            discord.Color.dark_grey()
        )

        if self.message:
            denied_embed = self.message.embeds[0]
            denied_embed.title = "❌ KOS Request Denied"
            denied_embed.color = discord.Color.dark_grey()
            denied_embed.add_field(name="Reviewed By", value=interaction.user.mention, inline=False)
            await self.message.edit(embed=denied_embed, view=None)

        await interaction.response.send_message(f"KOS request for {self.username} has been denied.", ephemeral=True)
        self.stop()


# ---------- Cog ----------
class KOSCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        if not hasattr(self.bot, "kos_synced"):
            self.bot.tree.add_command(KOSGroup())
            await self.bot.tree.sync()
            self.bot.kos_synced = True


async def setup(bot: commands.Bot):
    await bot.add_cog(KOSCog(bot))
