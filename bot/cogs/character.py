"""캐릭터 CRUD.

캐릭터에 연결된 디스코드 계정이 곧 알림에서 멘션할 대상이다.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from ..models import Character
from .common import (
    EMBED_COLOR,
    ConfirmView,
    character_autocomplete,
    find_character,
    get_or_create_character,
    open_session,
    schedules_of_character,
)

log = logging.getLogger("maple.character")


def can_manage(interaction: discord.Interaction, character: Character) -> bool:
    """본인 캐릭터이거나, 미연결 캐릭터이거나, 서버 관리자면 손댈 수 있다."""
    if character.discord_user_id in (None, interaction.user.id):
        return True
    permissions = getattr(interaction.user, "guild_permissions", None)
    return bool(permissions and permissions.manage_guild)


@app_commands.guild_only()
class Characters(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="캐릭터등록",
        description="캐릭터를 계정에 연결합니다. 유저를 비우면 내 캐릭터로 등록합니다.",
    )
    @app_commands.describe(
        이름="캐릭터명",
        유저="이 캐릭터의 주인. 비우면 나로 등록합니다",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        이름: str,
        유저: discord.Member | None = None,
    ) -> None:
        name = 이름.strip()
        if not name:
            await interaction.response.send_message("❓ 캐릭터명을 적어주세요.", ephemeral=True)
            return
        if len(name) > 32:
            await interaction.response.send_message(
                "❓ 캐릭터명은 32자 이하로 적어주세요.", ephemeral=True
            )
            return

        owner = 유저 or interaction.user
        본인 = owner.id == interaction.user.id
        if owner.bot:
            await interaction.response.send_message(
                "❓ 봇 계정에는 캐릭터를 연결할 수 없습니다.", ephemeral=True
            )
            return

        with open_session(interaction) as session:
            existing = find_character(session, interaction.guild_id, name)
            if existing is not None and existing.discord_user_id not in (None, owner.id):
                await interaction.response.send_message(
                    f"⛔ `{name}` 은 이미 <@{existing.discord_user_id}> 님의 캐릭터입니다.",
                    ephemeral=True,
                )
                return

            was_unlinked = existing is not None and existing.discord_user_id is None
            get_or_create_character(session, interaction.guild_id, name, owner.id)
            session.flush()

        머리말 = (
            "🔗 미연결 캐릭터를 계정에 연결했습니다" if was_unlinked else "✅ 캐릭터를 등록했습니다"
        )
        주인 = "" if 본인 else f" → {owner.mention}"
        # 남을 등록했으면 당사자가 알 수 있게 채널에 공개한다.
        await interaction.response.send_message(f"{머리말}: **{name}**{주인}", ephemeral=본인)

    @app_commands.command(
        name="캐릭터목록",
        description="등록된 캐릭터를 봅니다. 유저를 비우면 서버 전체를 보여줍니다.",
    )
    @app_commands.describe(유저="비우면 서버 전체 캐릭터")
    async def listing(
        self, interaction: discord.Interaction, 유저: discord.Member | None = None
    ) -> None:
        with open_session(interaction) as session:
            statement = select(Character).where(Character.guild_id == interaction.guild_id)
            if 유저 is not None:
                statement = statement.where(Character.discord_user_id == 유저.id)
            rows = session.scalars(
                statement.order_by(Character.discord_user_id.is_(None), Character.name)
            ).all()

            if not rows:
                대상 = f"{유저.display_name} 님의 " if 유저 else ""
                await interaction.response.send_message(
                    f"{대상}등록된 캐릭터가 없습니다. `/캐릭터등록` 으로 만들어보세요.",
                    ephemeral=True,
                )
                return

            줄 = []
            for row in rows:
                주인 = f"<@{row.discord_user_id}>" if row.is_linked else "미연결"
                일정수 = len(schedules_of_character(session, interaction.guild_id, row.id))
                줄.append(f"・**{row.name}** — {주인} · 파티 {일정수}개")

        embed = discord.Embed(
            title="🧙 캐릭터 목록" + (f" · {유저.display_name}" if 유저 else ""),
            description="\n".join(줄)[:4000],
            color=EMBED_COLOR,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="캐릭터수정", description="캐릭터 이름을 바꿉니다.")
    @app_commands.describe(캐릭터="이름을 바꿀 캐릭터", 새이름="새 캐릭터명")
    @app_commands.autocomplete(캐릭터=character_autocomplete)
    async def update(
        self,
        interaction: discord.Interaction,
        캐릭터: str,
        새이름: str,
    ) -> None:

        with open_session(interaction) as session:
            character = find_character(session, interaction.guild_id, 캐릭터)
            if character is None:
                await interaction.response.send_message(
                    f"❓ `{캐릭터}` 캐릭터를 찾을 수 없습니다.", ephemeral=True
                )
                return
            if not can_manage(interaction, character):
                await interaction.response.send_message(
                    "⛔ 다른 사람의 캐릭터는 고칠 수 없습니다.", ephemeral=True
                )
                return

            new_name = 새이름.strip()
            if not new_name or len(new_name) > 32:
                await interaction.response.send_message(
                    "❓ 이름은 1~32자로 적어주세요.", ephemeral=True
                )
                return
            겹침 = find_character(session, interaction.guild_id, new_name)
            if 겹침 is not None and 겹침.id != character.id:
                await interaction.response.send_message(
                    f"⛔ `{new_name}` 은 이미 등록된 캐릭터명입니다.", ephemeral=True
                )
                return
            변경 = f"`{character.name}` → `{new_name}`"
            character.name = new_name

            session.flush()

        await interaction.response.send_message(f"✏️ 이름을 바꿨습니다: {변경}", ephemeral=True)

    @app_commands.command(
        name="캐릭터삭제",
        description="캐릭터를 지웁니다. 참여 중인 파티에서도 함께 빠집니다.",
    )
    @app_commands.describe(캐릭터="지울 캐릭터")
    @app_commands.autocomplete(캐릭터=character_autocomplete)
    async def delete(self, interaction: discord.Interaction, 캐릭터: str) -> None:
        with open_session(interaction) as session:
            character = find_character(session, interaction.guild_id, 캐릭터)
            if character is None:
                await interaction.response.send_message(
                    f"❓ `{캐릭터}` 캐릭터를 찾을 수 없습니다.", ephemeral=True
                )
                return
            if not can_manage(interaction, character):
                await interaction.response.send_message(
                    "⛔ 다른 사람의 캐릭터는 지울 수 없습니다.", ephemeral=True
                )
                return

            character_id = character.id
            이름 = character.name
            파티수 = len(schedules_of_character(session, interaction.guild_id, character_id))

        view = ConfirmView(interaction.user.id)
        경고 = f"\n참여 중인 파티 {파티수}개에서도 빠집니다." if 파티수 else ""
        await interaction.response.send_message(
            f"🗑️ **{이름}** 캐릭터를 지울까요?{경고}", view=view, ephemeral=True
        )
        await view.wait()

        if not view.confirmed:
            await interaction.edit_original_response(content="취소했습니다.", view=None)
            return

        with open_session(interaction) as session:
            character = session.get(Character, character_id)
            if character is None or character.guild_id != interaction.guild_id:
                await interaction.edit_original_response(
                    content="❓ 이미 삭제된 캐릭터입니다.", view=None
                )
                return
            session.delete(character)

        await interaction.edit_original_response(
            content=f"🗑️ **{이름}** 캐릭터를 지웠습니다.", view=None
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Characters(bot))
