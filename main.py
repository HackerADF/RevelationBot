# === Standard Library Imports ===
import asyncio
import base64
import datetime
import json
import logging
import os
import io
import random
import re
import sys
import subprocess
from datetime import datetime, timedelta
from io import BytesIO

# === Third-Party Imports ===
import aiohttp
import aiosqlite
import discord
from openai import OpenAI
import requests
from charset_normalizer.md import getLogger
from discord import app_commands, ButtonStyle, Webhook
from discord.ext import commands, tasks
from discord.ui import Button, View
from discord.utils import get
from discord import FFmpegPCMAudio
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from sympy import false
from termcolor import colored

# == Local Imports ===
from cogs.kos import KOSGroup

# === Runtime Cleanup & Signal Handling ===
import atexit
import signal

TICKET_DATABASE = "tickets.db"
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
_log = logging.getLogger("discord")

intents = discord.Intents.all()
bot = commands.AutoShardedBot(command_prefix="!", intents=intents,
                              activity=discord.Streaming(name='ADF coding me!', url="https://nauticalhosting.org"))
class VerificationChallengeView(discord.ui.View):
    def __init__(self, user: discord.Member, code: int):
        super().__init__(timeout=300)
        self.user = user
        self.code = code
    @discord.ui.button(label="Enter Code", style=discord.ButtonStyle.red, custom_id="verify_code")
    async def verify_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            return await interaction.response.send_message("This challenge isn't for you.", ephemeral=True)
        modal = VerificationModal(self.code)
        await interaction.response.send_modal(modal)
class VerificationModal(discord.ui.Modal, title="Enter Verification Code"):
    def __init__(self, code: int):
        super().__init__()
        self.code = code
        self.username_input = discord.ui.TextInput(
            label="Minecraft Username",
            placeholder="Enter your Minecraft username here...",
            required=True,
            max_length=18
        )
        self.add_item(self.username_input)
        self.code_input = discord.ui.TextInput(
            label="Verification Code",
            placeholder="Enter the 6-digit code...",
            required=True,
            max_length=6
        )
        self.add_item(self.code_input)
    async def on_submit(self, interaction: discord.Interaction):
        guild_id = 1414363675552252048
        if self.code_input.value == str(self.code):
            guild = await interaction.client.fetch_guild(guild_id)
            if guild:
                role = guild.get_role(int("1414392497383149639"))
                if role:
                    server = bot.get_guild(guild_id)
                    role = discord.utils.get(server.roles, name="verified")
                    member = server.get_member(interaction.user.id)
                    await member.add_roles(role)
                    await edit_verification_embed(member, "Verified", self.username_input)
                    await interaction.response.send_message("✅ Verification successful! You are now awaiting approval.\nBe sure to checkout <#1414381158740922568> and <#1414384922113867826>!",
                                                            ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Role not found.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Couldn't find the server. Please try again later.",
                                                        ephemeral=True)
        else:
            await interaction.response.send_message("❌ Incorrect code. Please try again.", ephemeral=True)
class VerificationView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=None)
    @discord.ui.button(label="Verify & Send Application", style=discord.ButtonStyle.red, custom_id="verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild  # Get the guild from the interaction
        member = guild.get_member(interaction.user.id)
        verify_role_id = 1414392497383149639
        verify_role = guild.get_role(verify_role_id)
        if verify_role in member.roles:
            channel = discord.utils.get(guild.text_channels, id=1414393765350604800)
            if channel:
                await channel.send(f"🚫 {member.mention} tried to verify but already has the verified role.")
            await interaction.response.send_message(
                "⚠️ |  Sorry, a raid has been detected, and you were flagged. Please check the channel list for the alternate verification channel, or wait for this raid to be resolved.",
                ephemeral=True)
            return
        await interaction.response.send_message("📩 Check your DMs for the verification challenge!", ephemeral=True)
        verification_code = random.randint(100000, 999999)
        embed = discord.Embed(
            title="Verification Challenge",
            description=f"To verify your identity, please enter your Minecraft username and the following code in the challenge panel:\n\n`{verification_code}`",
            color=discord.Color.red()
        )
        embed.set_footer(text="This verification code expires in 5 minutes.")
        try:
            await interaction.user.send(embed=embed,
                                        view=VerificationChallengeView(interaction.user, verification_code))
        except discord.Forbidden:
            await interaction.followup.send("⚠ Unable to send DM. Please enable direct messages and try again.",
                                            ephemeral=True)
async def edit_verification_embed(member, status, username):
    joinLogChannel = discord.utils.get(member.guild.text_channels, id=1414393765350604800)
    welcomeChannel = discord.utils.get(member.guild.text_channels, name="〔➕〕joins")  # Adjust this as needed
    if joinLogChannel:
        verified_embed = discord.Embed(title=f"Member {member.name} has been verified.",
                                       description=f"» **Member**: {member.name} **[{member.id}]** ({member.mention})\n» **Account Created**: {member.created_at}\n\n**Verification**:\n> **Status**: Verified ✅",
                                       colour=discord.Color.green())  # Change the color to Green when verified
        verified_embed.set_author(name="Security")
        await joinLogChannel.send(content="<@&1414369811022086144> please review this user!", embed=verified_embed)
    if welcomeChannel:
        await welcomeChannel.send(f"👋 |  {member.mention} has successfully joined & verified! - Welcome!")
# ====================================================================================================
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    async def create_ticket(self, interaction: discord.Interaction, reason: str, answers: str):
        guild = interaction.guild
        user = interaction.user
        staff = discord.utils.get(guild.roles, name="|  Team Lead")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),  # Hide for everyone
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True),  # Allow user
            staff: discord.PermissionOverwrite(view_channel=True, send_messages=True)  # Allow user
        }
        channel = await guild.create_text_channel(
            name=f"ticket-{user.name.replace('.', '-')}-{reason.lower().replace(' ', '-')}",
            category=guild.get_channel(1414397759729172590),
            overwrites=overwrites
        )
        async with aiosqlite.connect(TICKET_DATABASE) as db:
            await db.execute("INSERT INTO tickets (channel_id, user_id, reason) VALUES (?, ?, ?)",
                             (channel.id, user.id, reason))
            await db.commit()
        embed = discord.Embed(title="Welcome to the support channel!",
                              colour=0xae00ff)
        embed.set_author(name="Tickets")
        await channel.send(content="<@&1414369253959663708> <@&1414369811022086144>")
        await channel.send(embed=embed)
        answers = answers
        if reason.lower() == "report a user":
            embed = discord.Embed(title="Please wait for someone to respond to your ticket",
                                  description=f"**What is your name**?\n{answers['name']}\n\n**Who are you reporting**?\n{answers['reportee']}\n\n**Where did this occur**?\n{answers['place']}\n\n**Why are you reporting them?**?:\n{answers['reason']}\n\n**Any additional info**?:\n{answers['additional']}",
                                  colour=0xae00ff)
            await channel.send(embed=embed)
        elif reason.lower() == "ask a question":
            embed = discord.Embed(title="Please answer the following questions:",
                                  description="**How can we assist you today?**",
                                  colour=0xae00ff)
            await channel.send(embed=embed)
        elif reason.lower() == "need support":
            embed = discord.Embed(title="Please answer the following questions:",
                                  description="**What is your Minecraft IGN**?\n\n**What product, service, or server do you require support within**?\nPlease describe your issue in detail.",
                                  colour=0xae00ff)
            await channel.send(embed=embed)
        elif reason.lower() == "report a bug":
            embed = discord.Embed(title="Please answer the following questions:",
                                  description="**What is your Minecraft IGN**?\n\n**What is the bug**?\nPlease be detailed to ensure we can provide the best support possible!\n\n**How can it be recreated**?\nSteps to recreate the bug.\n\n**Where did you find this bug**?",
                                  colour=0xae00ff)
            await channel.send(embed=embed)
        elif reason.lower() == "become a member":
            embed = discord.Embed(title="Please wait for someone to handle your ticket.",
                                  description=f"**What is your Minecraft IGN**?\n{answers['name']}\n\n**Why do you want to join Revelation?**?\n{answers['why']}\n\n**What tier are you?\n{answers['tier'] if answers['tier'] else "Not Tested."}\n\n**What servers do you play on?**?\n{answers['servers']}\n\n**Any additional info?\n{answers['additional']}",
                                  colour=0xae00ff)
            await channel.send(embed=embed)
        else:
            return
        await interaction.response.send_message(
            f"✅ Your ticket has been created: {channel.mention}", ephemeral=True
        )
    @discord.ui.button(label="Become a member", emoji="⭐", style=discord.ButtonStyle.green, custom_id="become_a_member")
    async def become_a_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            TicketMemberModal(reason="become a member", interaction=interaction, parent_view=self))
    @discord.ui.button(label="Ask a Question", emoji="❓", style=discord.ButtonStyle.primary, custom_id="ask_question")
    async def ask_question(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Ask a Question", "")
    @discord.ui.button(label="Need Support", emoji="🧩", style=discord.ButtonStyle.primary, custom_id="need_support")
    async def need_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Need Support", "")
    @discord.ui.button(label="Report a Bug", emoji="🐛", style=discord.ButtonStyle.blurple, custom_id="report_bug")
    async def report_bug(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Report a Bug", "")
    @discord.ui.button(label="Report a User", emoji="⛑️", style=discord.ButtonStyle.danger, custom_id="report_user")
    async def report_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            TicketReportModal(reason="report a user", interaction=interaction, parent_view=self))
    @discord.ui.button(label="Appeal Punishment", emoji="⚠️", style=discord.ButtonStyle.danger,
                       custom_id="appeal_punishment")
    async def appeal_punishment(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket(interaction, "Appeal Punishment", "")
class TicketCloseView(View):
    def __init__(self, interaction, channel_id, ticket_creator_id):
        super().__init__()
        self.interaction = interaction  # Store the interaction for later use
        self.channel_id = channel_id
        self.ticket_creator_id = ticket_creator_id
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle the 'Confirm' button click."""
        await self.close_ticket(interaction)
    @discord.ui.button(label="Leave Open/Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle the 'Cancel' button click."""
        await interaction.response.send_message("Ticket closure has been canceled.", ephemeral=True)
    async def close_ticket(self, interaction: discord.Interaction):
        """Function to close and archive the ticket."""
        async with aiosqlite.connect(TICKET_DATABASE) as db:
            cursor = await db.execute("SELECT user_id FROM tickets WHERE channel_id = ?", (self.channel_id,))
            result = await cursor.fetchone()
            if not result:
                await interaction.response.send_message("This channel is not a ticket.", ephemeral=True)
                return
            ticket_creator_id = result[0]
            await db.execute("DELETE FROM tickets WHERE channel_id = ?", (self.channel_id,))
            await db.commit()
            channel = interaction.channel
            user_to_remove = interaction.guild.get_member(self.ticket_creator_id)
            if user_to_remove:
                await channel.set_permissions(user_to_remove, view_channel=False)
            archive_category = discord.utils.get(interaction.guild.categories, id=1414429643003527339)
            if archive_category:
                await channel.edit(category=archive_category)
                await channel.send("🔒 This ticket has been archived and is now private.")
            else:
                await channel.send("⚠️ Archive category not found. Please check the category ID.")
            await interaction.response.send_message("Ticket has been closed and archived.", ephemeral=True)
class TicketReportModal(discord.ui.Modal, title="Player Report Form"):
    name = discord.ui.TextInput(
        label="What is your Minecraft username?",
        placeholder="Enter your Minecraft username here...",
        required=True,
        max_length=16
    )
    reportee_name = discord.ui.TextInput(
        label="Who are you reporting?",
        placeholder="Enter their Minecraft/Discord username...",
        required=True,
        max_length=18
    )
    place = discord.ui.TextInput(
        label="Where did this occur?",
        placeholder="Discord/Minecraft/Any server",
        required=True,
        max_length=20
    )
    report_reason = discord.ui.TextInput(
        label="What are you reporting them for?",
        placeholder="Please be very detailed in why you're reporting them.",
        required=True,
        max_length=1000
    )
    additional_info = discord.ui.TextInput(
        label="Any additional info?",
        placeholder="Optional",
        required=False,
        max_length=300
    )
    def __init__(self, reason: str, interaction: discord.Interaction, parent_view):
        super().__init__()
        self.reason = reason
        self.interaction = interaction
        self.parent_view = parent_view
    async def on_submit(self, interaction: discord.Interaction):
        answers = {
            "name": self.name.value,
            "reportee": self.reportee_name.value,
            "place": self.place.value,
            "reason": self.report_reason.value,
            "additional": self.additional_info.value
        }
        await self.parent_view.create_ticket(interaction, self.reason, answers)
class TicketMemberModal(discord.ui.Modal, title="Revelation Member Application"):
    name = discord.ui.TextInput(
        label="What is your Minecraft username?",
        placeholder="Enter your Minecraft username here...",
        required=True,
        max_length=16
    )
    why = discord.ui.TextInput(
        label="Why do you want to join?",
        placeholder="Explain why you wish to become a member of Revelation",
        required=True,
        max_length=1000
    )
    tier = discord.ui.TextInput(
        label="What tier are you?",
        placeholder="Please list each gamemode and tier, if you are untested, leave this blank.",
        required=False,
        max_length=200
    )
    servers = discord.ui.TextInput(
        label="What servers do you play?",
        placeholder="Enter the servers you mainly play on, and include IPs if possible.",
        required=True,
        max_length=300
    )
    additional_info = discord.ui.TextInput(
        label="Any additional info?",
        placeholder="Optional",
        required=False,
        max_length=300
    )
    def __init__(self, reason: str, interaction: discord.Interaction, parent_view):
        super().__init__()
        self.reason = reason
        self.interaction = interaction
        self.parent_view = parent_view
    async def on_submit(self, interaction: discord.Interaction):
        answers = {
            "name": self.name.value,
            "why": self.why.value,
            "tier": self.tier.value,
            "servers": self.servers.value,
            "additional": self.additional_info.value

        }
        await self.parent_view.create_ticket(interaction, self.reason, answers)
@bot.tree.command(name="master", description="Master command")
@app_commands.describe(
    action="Choose an action.",
)
@app_commands.choices(
    action=[
        app_commands.Choice(name="Verification Panel", value="vp"),
        app_commands.Choice(name="Informations Panel", value="ip"),
        app_commands.Choice(name="Tickets Panel", value="tp"),
        app_commands.Choice(name="Rules Panel", value="rp"),
        app_commands.Choice(name="Anti-Raid Panel", value="arp")
    ]
)
async def master(interaction: discord.Interaction, action: str):
    if interaction.user.id != 1248492933875765328:
        await interaction.response.send_message("You are not permitted to use this command", ephemeral=True)
        return
    if action == "vp":
        embed = discord.Embed(
            title="Welcome to Revelation",
            description=(
                "Please verify by pressing the button below to ensure you are not a bot!\n\n**⸻⸻⸻⸻⸻⸻⸻⸻⸻⸻**\n\n"
                "> **Welcome to Revelation!**  \n\n"
                "```\nPvP | Building | Training\n```\n\n"
                "**Revelations** is a multi-server PvP team created by **ADF**, dedicated to exploring and dominating"
                "Minecraft servers!  \n\n"
                "We're powerful and feared among many, home to some of EYserver's best PvP-ers.\n"
                "- ADF\n"
                "- 1111KING\n"
                "- NSH\n"
                "- Biga252\n"
                "- and more"
                "\n\nGet ready to experience the raw power of REVELATION"
            ),
            colour=discord.Color.red(),
            timestamp=datetime.now()
        )
        embed.set_author(name="Verification required")
        embed.set_image(url="https://cdn.discordapp.com/banners/1414399114816393246/573ed7d1738cb1327e0a3db5a117aa45.png?size=512")
        embed.set_thumbnail(url="https://dan.onl/images/emptysong.jpg")
        embed.set_footer(text="Powered by: ADF Industries, LLC", icon_url="https://slate.dan.onl/slate.png")
        view = VerificationView(bot, 1414363675552252048)
        await interaction.response.send_message("Sending Verification Panel...", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)
    elif action == "ip":
        embed = discord.Embed(title="Welcome to ADF Industries!",
                              description="Welcome to the ADF Industries official discord server! Whether you're here to chat or are seeking support for one of our products, we have something for everyone.\n\n**Who are we?**\n    ADF Industries began as a small organization in 2021 founded by Rylen Reis, with Jordan Kadi as the co-founder. The organization consisted of 6 people. Rylen, Jordan, Johnathan, Ayden, Emileo, and Kile, offering configurations or setup for common things. Minecraft servers, websites, or even game creation - We had you covered!\n    As we got more and more experience throughout the years, we decided that we should expand our services to a greater audience. In 2023, we migrated to discord. This allowed us to reach a greater audience when advertising, and gave us yet another service to offer; Discord server setup. \n    In October of 2023, Rylen, the founder of ADF Industries decided that he wanted to do more than to just set things up. He wanted to experiment with things; To make them rather than configure them. One of the very first projects he launched in ADF Industries was The Game Space. The Game Space was a collection of games and entertaining apps that we developed over the years all compiled into one page. \n    The project was later archived in November. Replaced with a new project: ADF Private Chat. ADF Private Chat was one of the most worked on apps of the time and was not later released until early December. ADF Private Chat was a simple yet appealing chat application that allowed users to chat with one another. Rylen's main motive for this was to be able to seamlessly communicate with classmates while in school, as they tend to block most forms of communication. Unfortunately, one of the websites that the app ran off of was shut down, and the project fell into dis-repair.\n    After ADF Private Chat went offline, the company shifted, into Minecraft. Creating servers and plugins, and since then, they've split into departments. Rylen; Head of operations, Jordan; Head of Departments, Johnathan; Head of website development, Ayden; Head of Backend programming, Kile; Head of Frontend programming, Emileo; Head of Minecraft Development. Since then, ADF Industries has created several plugins, apps, servers, websites, and Discord bots!",
                              colour=0x00ff9d,
                              timestamp=datetime.now())
        embed.set_author(name="Information!")
        embed.add_field(name="Additional information",
                        value="🛍️|  Interested in our products? Check out: <#1346597134153027675>!\n🗨️|  Wanna chat with ADF? Go to: <#1330798539239985203>\n🧩|  Need support? <#1346510921023094814> is the place to go!\n🐛|  Found a bug? Post it in <#1346511753516941333>!",
                        inline=False)
        embed.add_field(name="Links",
                        value="[Coming soon!](https://www.example.com)\n[Coming soon!](https://www.example.com)\n[Coming soon!](https://www.example.com)\n[Coming soon!](https://www.example.com)",
                        inline=False)
        embed.set_image(url="https://cubedhuang.com/images/alex-knight-unsplash.webp")
        embed.set_footer(text="ADF Industries, LLC",
                         icon_url="https://slate.dan.onl/slate.png")
        await interaction.response.send_message("Sending Informations Panel...", ephemeral=True)
        await interaction.channel.send(embed=embed)
    elif action == "tp":
        embed = discord.Embed(title="Need support?",
                              colour=0xffc800,
                              timestamp=datetime.now())
        embed.set_author(name="Tickets")
        embed.add_field(name="What to make a ticket for:",
                        value="⭐|  Looking to become a member?\n❓|  Have questions for us?\n🧩|  Reporting someone/Need support?\n🐛|  Found a bug?\n⚠️|  Punishment Appeals?",
                        inline=True)

        embed.set_image(url="https://cdn.discordapp.com/banners/1414399114816393246/573ed7d1738cb1327e0a3db5a117aa45.png?size=512")
        embed.set_footer(text="ADF Industries, LLC",
                         icon_url="https://slate.dan.onl/slate.png")
        view = TicketView()
        await interaction.response.send_message("Sending Informations Panel...", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)
    elif action == "rp":
        embed1 = discord.Embed(
            title="Server Rules - Part 1",
            description="Please follow the rules to ensure a great experience for everyone.",
            color=discord.Color.blue()
        )
        embed1.add_field(name="1. Be respectful", value="Treat everyone with kindness and respect.", inline=False)
        embed1.add_field(name="2. Abide by Discord ToS", value="Follow Discord's Terms of Service at all times.",
                         inline=False)
        embed1.add_field(name="3. Use family-friendly language",
                         value="Keep your language appropriate for all audiences.", inline=False)
        embed1.add_field(name="4. No advertising", value="No unsolicited advertising or self-promotion.", inline=False)
        embed2 = discord.Embed(
            title="Server Rules - Part 2",
            description="Please continue to follow the rules for a better experience.",
            color=discord.Color.green()
        )
        embed2.add_field(name="5. Abide by our ToS", value="Ensure you follow our Terms of Service.", inline=False)
        embed2.add_field(name="6. Do NOT ask for support in #﹝🌍﹞chat",
                         value="Support requests should be handled in the proper channels.", inline=False)
        embed2.add_field(name="7. Do not ping staff", value="Avoid unnecessarily pinging staff members.", inline=False)
        embed2.add_field(name="8. Keep channels respective to their purpose",
                         value="Each channel has a specific purpose. Stay on-topic.", inline=False)
        embed3 = discord.Embed(
            title="Server Rules - Part 3",
            description="Please be mindful of the community rules.",
            color=discord.Color.orange()
        )
        embed3.add_field(name="9. No spamming, chatwalling, flooding, or disruptions of chat",
                         value="Do not spam, flood, or disrupt the chat.", inline=False)
        embed3.add_field(name="10. Do NOT DM staff for support",
                         value="Contact support through the appropriate channels.", inline=False)

        embed4 = discord.Embed(
            title="Server Rules - Part 4",
            description="Please respect these rules, they're important!",
            color=discord.Color.red()
        )
        embed4.add_field(name="11. Do not ping Nicole/N1nsoka",
                         value="Do not ping them, including reply pings! You **will** be punished!", inline=False)
        embed4.add_field(name="12. Do NOT ask for support for other servers.",
                         value="Support requests should be directly related to this server. (**NOT EYSERVER**)",
                         inline=False)
        embed6 = discord.Embed(
            title="Server Rules - Part 5",
            description="Respect everyone's privacy.",
            color=discord.Color.teal()
        )
        embed6.add_field(
            name="13. Do not share or ask about personal information",
            value="Do not discuss or ask about someone's private information (e.g., age, real name, face) unless they explicitly allow it.",
            inline=False
        )
        embed7 = discord.Embed(
            title="Server Rules - Part 6",
            description="Ethical behavior is expected from all members.",
            color=discord.Color.gold()
        )
        embed7.add_field(
            name="14. Maintain ethical conduct",
            value="Treat others fairly and act with integrity. Toxic, manipulative, or unethical behavior will not be tolerated.",
            inline=False
        )
        embed7.add_field(
            name=" **14**.1 Dox, SWATs, DDoS",
            value="Attempting to or threatening to dox, SWAT, or DDoS will **not** be tolorated, and will result in a permanent ban.",
            inline=False
        )
        embed8 = discord.Embed(
            title="Server Rules - Part 7",
            description="Certain client modifications are not allowed.",
            color=discord.Color.dark_red()
        )
        embed8.add_field(
            name="15. Vencord plugin restrictions",
            value="Use of any Vencord plugins that display hidden channels or deleted/edited messages is strictly prohibited. "
                  "You will receive two warnings. After the third offense, a punishment will be issued.",
            inline=False
        )
        embed9 = discord.Embed(
            title="Server Rules - Part 8",
            description="Use your best judgment.",
            color=discord.Color.dark_purple()
        )
        embed9.add_field(
            name="16. Use common sense",
            value="Not every rule can cover every situation. Use common sense and act in a way that maintains a positive, safe community.",
            inline=False
        )
        tosEmbed = discord.Embed(
            title="Terms of Service",
            description="Please review our Terms of Service here.",
            color=discord.Color.purple()
        )
        tosEmbed.add_field(name="Terms of Service",
                         value="[Click here to read our Terms of Service](https://docs.google.com/document/d/1L3DsEAZ-ojuh1Fe7UmjCqgYajyv1mv3oyCWzkslv2JQ/edit?pli=1&tab=t.0#heading=h.xaiwsnsomrhf)",
                         inline=False)
        await interaction.response.send_message("Sending Rules Panel...", ephemeral=True)
        await interaction.channel.send(embeds=[embed1, embed2, embed3, embed4, embed6, embed7, embed8, embed9, tosEmbed])
    if action == "arp":
        embed = discord.Embed(
            title="🚨 A Raid Has Been Detected! 🚨",
            description=(
                "### Immediate Action Required!\n\n"
                "---\n\n"
                "> **A potential raid has been detected on ADF Industries!**\n\n"
                "```\nSecurity | Protection | Stability\n```\n\n"
                "Our automated security system has flagged **unusual activity** that may indicate a coordinated attack. "
                "To protect our community, additional **security measures** have been activated.\n\n"
                "**What does this mean?**\n"
                "🔹 Temporary restrictions may apply.\n"
                "🔹 New users will require manual verification.\n"
                "🔹 Staff intervention may be necessary.\n\n"
                "If you believe this is a false alarm, please contact an **Administrator** immediately.\n\n"
                "[🛡️ Learn More About Security](https://example.com)\n\n"
                "**Stay vigilant and keep our community safe!**\n\n"
                "||Our systems continuously monitor and improve to prevent threats.||"
            ),
            color=0xFF0000,
            timestamp=datetime.now()
        )
        embed.set_author(name="Security Alert", icon_url="https://example.com/security-icon.png")
        embed.set_image(url="https://cubedhuang.com/images/security-alert.webp")
        embed.set_thumbnail(url="https://dan.onl/images/warning-icon.jpg")
        embed.set_footer(text="ADF Industries Security", icon_url="https://slate.dan.onl/slate.png")
        view = None
        await interaction.response.send_message("Sending Anti-Raid Panel...", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)
    else:
        await interaction.followup.send("Invalid action!", ephemeral=True)
@bot.tree.command(name="close", guild=discord.Object(id=int(1414363675552252048)))
async def close(interaction: discord.Interaction):
    async with aiosqlite.connect(TICKET_DATABASE) as db:
        cursor = await db.execute("SELECT user_id FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
        result = await cursor.fetchone()
        if not result:
            await interaction.response.send_message("This channel is not a ticket.", ephemeral=True)
            return
        """Closes a ticket by making it private and moving it to an archive category."""
        embed = discord.Embed(title="Are you sure?", description="Do you want to close and archive this ticket?",
                              color=discord.Color.dark_red())
        view = TicketCloseView(interaction, interaction.channel.id, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

async def load_extensions(folder: str, package: str = "cogs"):
    """Recursively load all cogs inside the given folder."""
    for root, _, files in os.walk(folder):
        for file in files:
            if file.endswith(".py"):
                relative_path = os.path.relpath(os.path.join(root, file), folder)
                module = relative_path.replace(os.sep, ".")[:-3]  # strip .py
                ext = f"{package}.{module}"
                try:
                    await bot.load_extension(ext)
                    print(f"✅ Loaded {ext}")
                except Exception as e:
                    print(f"❌ Failed to load {ext}: {e}")
@bot.event
async def on_ready():
    _log.info(f"{bot.user} has connected to Discord!")
    await load_extensions("cogs")
    bot.tree.add_command(KOSGroup())
    synced_commands = await bot.tree.sync()
    _log.info(f"Synced {len(synced_commands)} global slash command(s).")
    guild = discord.Object(id=1414363675552252048)
    await bot.tree.sync(guild=guild)
    _log.info("REVELATIONS' specific commands have been registered & synced!\n")
    _log.info(f"Successfully loaded Revelation Bot (v1)!")
    for guild in bot.guilds:
        bot.add_view(VerificationView(bot, guild.id))
    bot.add_view(TicketView())
    activity = discord.Streaming(name="Looking for KOS players", url="https://nauticalhosting.com")
    await bot.change_presence(
        activity=discord.Streaming(name="Looking for KOS players", url="https://nauticalhosting.com"))

bot.run(DISCORD_TOKEN)