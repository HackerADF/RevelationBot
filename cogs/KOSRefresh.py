import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import datetime
from datetime import datetime as dt
import pytz

from cogs.kos import KOS_CHANNEL_ID

# -------- CONFIG ---------
KOS_CHANNEL_ID = KOS_CHANNEL_ID
TIMEZONE = pytz.timezone("America/Boise")
# -------------------------

class KOSRefresher(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="refresh_kos")
    @commands.has_permissions(administrator=True)
    async def refresh_kos(self, ctx: commands.Context):
        """This refreshes the KOS perms"""
        channel = ctx.guild.get_channel(KOS_CHANNEL_ID)
        if not channel:
            await ctx.channel.send("ur code is cooked buddy")

        refreshed = 0
        failed = 0

        async with aiosqlite.connect("kos.db") as db:
            async with db.execute("SELECT username, timestamp, message_id, reason FROM kos") as cursor:
                rows = await cursor.fetchall()
            for username, timestamp, message_id, reason in rows:
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.delete()
                except Exception:
                    failed += 1
                    pass

                embed = discord.Embed(
                    title="⚔️ KOS Notice",
                    color=discord.Colour.red()
                )
                embed.add_field(name="Usernames", value=username, inline=True)
                embed.add_field(name="Reason", value=reason, inline=True)
                embed.add_field(name="Date", value=f"<f:{timestamp}:F>", inline=True)
                embed.set_thumbnail(url=f"https://mineskin.eu/helm/{username}/100.png")

                new_msg = await channel.send(embed=embed)
                await db.execute("UPDATE kos SET message_id = ? WHERE lower(username) = lower(?)", (new_msg.id, username,))
                refreshed += 1

            await db.commit()
        await ctx.send(f"✅ Refresh {refreshed} KOS entries. ❌ Failed to delete {failed}")

async def setup(bot: commands.Bot):
    await bot.add_cog(KOSRefresher(bot))