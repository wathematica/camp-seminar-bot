"""Camp seminar bot: one webhook/channel only, no public HTTP server required."""
import asyncio
import contextlib
import logging
import os
from pathlib import Path
import time

import aiohttp
import discord

from storage import Store
from voting import EMOJIS, count_votes, render_embed, is_proposal

LOG = logging.getLogger('camp')


def read_secret(name):
    file_path = os.environ.get(name + '_FILE')
    value = Path(file_path).read_text().strip() if file_path else os.environ.get(name, '').strip()
    if not value:
        raise ValueError(name + ' が未設定です。')
    return value


class CampBot(discord.Client):
    def __init__(self, webhook_url):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.guild_messages = True
        intents.guild_reactions = True
        # Embed contents are read through the owning webhook, not message-content intent.
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.webhook_url = webhook_url
        self.threshold = int(os.environ.get('FIRST_CHOICE_THRESHOLD', '3'))
        if self.threshold < 1:
            raise ValueError('成立目安人数は1以上にしてください。')
        self.queue = asyncio.Queue()
        self.pending = set()
        self.tasks = []
        self.channel = None
        self.last_reconcile = 0

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        # Share the client state so webhook messages containing reactions can
        # resolve emoji data (standalone webhook state lacks this in 2.7.1).
        self.webhook = discord.Webhook.from_url(self.webhook_url, session=self.session, client=self)
        info = await self.webhook.fetch()
        expected_bot = os.environ.get('EXPECTED_BOT_ID', '').strip()
        if expected_bot and self.user.id != int(expected_bot):
            raise ValueError('想定したBotのトークンではありません。')
        self.channel_id = info.channel_id
        self.guild_id = info.guild_id
        self.store = Store(os.environ.get('DATABASE_PATH', 'data/camp.sqlite3'), self.webhook.id)
        self.tasks = [asyncio.create_task(self.worker()), asyncio.create_task(self.reconcile())]

    async def on_ready(self):
        LOG.info('接続完了 Bot=%s channel=%s', self.user.id, self.channel_id)

    def schedule(self, message_id):
        if message_id not in self.pending:
            self.pending.add(message_id)
            self.queue.put_nowait(message_id)

    async def on_message(self, message):
        if message.channel.id == self.channel_id and message.webhook_id == self.webhook.id:
            self.store.add(message.id)
            self.schedule(message.id)

    async def reaction_event(self, payload):
        if payload.channel_id != self.channel_id:
            return
        if getattr(payload, 'user_id', None) == self.user.id:
            return
        emoji = getattr(payload, 'emoji', None)
        if emoji is not None and str(emoji) not in EMOJIS:
            return
        if self.store.contains(payload.message_id):
            self.schedule(payload.message_id)

    on_raw_reaction_add = reaction_event
    on_raw_reaction_remove = reaction_event
    on_raw_reaction_clear = reaction_event
    on_raw_reaction_clear_emoji = reaction_event

    async def on_raw_message_delete(self, payload):
        if payload.channel_id == self.channel_id:
            self.store.remove(payload.message_id)

    async def on_raw_bulk_message_delete(self, payload):
        if payload.channel_id == self.channel_id:
            for message_id in payload.message_ids:
                self.store.remove(message_id)

    async def get_target_channel(self):
        if self.channel is None:
            self.channel = await self.fetch_channel(self.channel_id)
            if not isinstance(self.channel, discord.TextChannel):
                raise ValueError('通常のテキストチャンネル用Webhookを指定してください。')
        return self.channel

    async def sync_message(self, message_id):
        # Ownership checked through the configured webhook before any mutation.
        source = await self.webhook.fetch_message(message_id)
        if not source.embeds or not is_proposal(source.embeds[0].to_dict()):
            self.store.remove(message_id)
            return
        channel = await self.get_target_channel()
        message = await channel.fetch_message(message_id)
        for emoji in EMOJIS:
            existing = next((r for r in message.reactions if str(r.emoji) == emoji), None)
            if existing is None or not existing.me:
                await message.add_reaction(emoji)

        voters = []
        for emoji in EMOJIS:
            ids = set()
            reaction = next((r for r in message.reactions if str(r.emoji) == emoji), None)
            if reaction:
                for reaction_type in (discord.ReactionType.normal, discord.ReactionType.burst):
                    async for user in reaction.users(limit=None, type=reaction_type):
                        if not user.bot:
                            ids.add(user.id)
            voters.append(ids)
        counts = count_votes(voters)
        original = source.embeds[0].to_dict()
        updated = render_embed(original, counts, self.threshold)
        changed = any(original.get(k) != updated.get(k) for k in ('color', 'description', 'footer', 'fields'))
        if changed:
            embeds = [discord.Embed.from_dict(updated)] + source.embeds[1:]
            await self.webhook.edit_message(message_id, embeds=embeds,
                                           allowed_mentions=discord.AllowedMentions.none())
            LOG.info('人数更新 message=%s votes=%s', message_id, counts)

    async def worker(self):
        await self.wait_until_ready()
        while not self.is_closed():
            message_id = await self.queue.get()
            # A brief delay coalesces bursts. Events during sync enqueue another pass.
            await asyncio.sleep(0.7)
            self.pending.discard(message_id)
            try:
                if self.store.contains(message_id):
                    await self.sync_message(message_id)
            except discord.NotFound as error:
                if error.code == 10008:
                    self.store.remove(message_id)
                else:
                    LOG.error('更新失敗 message=%s HTTP=%s code=%s', message_id, error.status, error.code)
                    await asyncio.sleep(30)
            except discord.HTTPException as error:
                LOG.error('更新失敗 message=%s HTTP=%s code=%s', message_id, error.status, error.code)
                # Do not hammer an endpoint after access/block errors.
                await asyncio.sleep(30)
            except Exception as error:
                LOG.error('更新失敗 message=%s kind=%s', message_id, type(error).__name__)
                await asyncio.sleep(5)
            finally:
                self.queue.task_done()

    async def scan_history(self):
        channel = await self.get_target_channel()
        cursor = int(self.store.get('cursor') or 0)
        # Full initial history in bounded batches; subsequent scans cover downtime.
        async for message in channel.history(limit=200, after=discord.Object(id=cursor), oldest_first=True):
            if message.webhook_id == self.webhook.id:
                self.store.add(message.id)
                self.schedule(message.id)
            self.store.set('cursor', message.id)

    async def reconcile(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await self.scan_history()
                for message_id in self.store.ids():
                    self.schedule(message_id)
                self.last_reconcile = time.time()
                Path(os.environ.get('HEARTBEAT_PATH', 'data/heartbeat')).write_text(str(self.last_reconcile))
            except discord.HTTPException as error:
                LOG.error('履歴確認失敗 HTTP=%s code=%s', error.status, error.code)
            except Exception as error:
                LOG.error('履歴確認失敗 kind=%s', type(error).__name__)
            await asyncio.sleep(60)

    async def close(self):
        for task in self.tasks:
            task.cancel()
        for task in self.tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if hasattr(self, 'session'):
            await self.session.close()
        if hasattr(self, 'store'):
            self.store.close()
        await super().close()


async def main():
    bot = CampBot(read_secret('DISCORD_WEBHOOK_URL'))
    async with bot:
        await bot.start(read_secret('DISCORD_BOT_TOKEN'))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as error:
        LOG.error('起動失敗 kind=%s（トークン・Webhook・権限を確認してください）', type(error).__name__)
        raise SystemExit(1)
