import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from bot import CampBot
from storage import Store
from voting import count_votes, render_embed, is_proposal


class RulesTest(unittest.TestCase):
    def test_named_card_and_legacy_recognition(self):
        named = {'title': '線形代数', 'fields': [{'name': '名称', 'value': '線形代数'}]}
        self.assertTrue(is_proposal(named, '春合宿のゼミ提案'))
        self.assertTrue(is_proposal({'title': '春合宿のゼミ提案'}, '春合宿のゼミ提案'))
        self.assertFalse(is_proposal({'title': '別のお知らせ'}, '春合宿のゼミ提案'))
        self.assertEqual(render_embed(named, [3, 0, 0])['title'], '線形代数')

    def test_priority_and_withdrawal(self):
        self.assertEqual(count_votes([{1, 2, 3}, {2, 4}, {1, 4, 5}]), [3, 1, 1])
        card = {'title': '春合宿のゼミ提案', 'fields': [{'name': '概要', 'value': '内容'}], 'image': {'url': 'https://example.com/a.png'}}
        green = render_embed(card, [3, 1, 1])
        pink = render_embed(green, [2, 1, 1])
        self.assertEqual(green['color'], 0x57F287)
        self.assertEqual(pink['color'], 0xFF69B4)
        self.assertEqual(pink['fields'], card['fields'])
        self.assertEqual(pink['image'], card['image'])
        self.assertNotIn('color', card)

    def test_restart_and_webhook_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'state.db')
            store = Store(path, 123)
            store.add(456)
            store.set('cursor', 789)
            store.close()
            store = Store(path, 123)
            self.assertEqual(store.ids(), [456])
            self.assertEqual(store.get('cursor'), '789')
            store.remove(456)
            self.assertFalse(store.contains(456))
            store.close()
            with self.assertRaises(ValueError):
                Store(path, 999)


class FakeReaction:
    def __init__(self, emoji, ids, bot_id=99):
        self.emoji, self.ids, self.me = emoji, ids, False
        self.bot_id = bot_id

    async def users(self, **kwargs):
        for user_id in self.ids:
            yield SimpleNamespace(id=user_id, bot=user_id == self.bot_id)


class IntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_webhook_reaction_parsing_uses_client_state(self):
        import aiohttp
        from discord.webhook.async_ import _WebhookState
        client = CampBot('https://discord.com/api/webhooks/123456789012345678/' + 'x' * 60)
        data = {'emoji': {'id': None, 'name': '1️⃣'}, 'count': 1, 'me': True}
        async with aiohttp.ClientSession() as session:
            standalone = discord.Webhook.from_url(client.webhook_url, session=session)
            message = SimpleNamespace(_state=_WebhookState(standalone, None))
            with self.assertRaises(AttributeError):
                discord.Reaction(message=message, data=data)
            attached = discord.Webhook.from_url(client.webhook_url, session=session, client=client)
            message = SimpleNamespace(_state=_WebhookState(attached, attached._state))
            reaction = discord.Reaction(message=message, data=data)
            self.assertEqual(reaction.emoji, '1️⃣')

    async def test_sync_excludes_bot_and_burst_duplicates_preserves_fields(self):
        client = CampBot('https://discord.com/api/webhooks/123456789012345678/' + 'x' * 60)
        original = discord.Embed(title='春合宿のゼミ提案')
        original.add_field(name='概要', value='本文')
        source = SimpleNamespace(embeds=[original])
        client.webhook = SimpleNamespace(fetch_message=AsyncMock(return_value=source), edit_message=AsyncMock())
        reactions = [FakeReaction('1️⃣', [1, 2, 3, 99]), FakeReaction('2️⃣', [2, 4]), FakeReaction('3️⃣', [4, 5])]
        message = SimpleNamespace(reactions=reactions, add_reaction=AsyncMock())
        client.channel = SimpleNamespace(fetch_message=AsyncMock(return_value=message))
        await client.sync_message(456)
        self.assertEqual(message.add_reaction.await_count, 3)
        edited = client.webhook.edit_message.call_args.kwargs['embeds'][0]
        self.assertEqual(edited.colour.value, 0x57F287)
        self.assertIn('第一志望 3人 ｜ 第二志望 1人 ｜ 第三志望 1人', edited.footer.text)
        self.assertEqual(edited.fields[0].value, '本文')
        # Unchanged card is not edited again.
        source.embeds = [edited]
        client.webhook.edit_message.reset_mock()
        await client.sync_message(456)
        client.webhook.edit_message.assert_not_awaited()
        # Withdrawal changes green back to pink.
        reactions[0].ids = [1, 2, 99]
        await client.sync_message(456)
        self.assertEqual(client.webhook.edit_message.call_args.kwargs['embeds'][0].colour.value, 0xFF69B4)

    async def test_event_filters_and_deduplication(self):
        client = CampBot('https://discord.com/api/webhooks/123456789012345678/' + 'x' * 60)
        client.channel_id = 10
        client._connection.user = SimpleNamespace(id=99)
        with tempfile.TemporaryDirectory() as directory:
            client.store = Store(str(Path(directory) / 'state.db'), 123)
            client.store.add(456)
            for channel, user, emoji, message in [(11, 1, '1️⃣', 456), (10, 99, '1️⃣', 456), (10, 1, '👍', 456), (10, 1, '1️⃣', 777)]:
                await client.reaction_event(SimpleNamespace(channel_id=channel, user_id=user, emoji=emoji, message_id=message))
            self.assertTrue(client.queue.empty())
            payload = SimpleNamespace(channel_id=10, user_id=1, emoji='1️⃣', message_id=456)
            await client.reaction_event(payload)
            await client.reaction_event(payload)
            self.assertEqual(client.queue.qsize(), 1)
            client.store.close()


if __name__ == '__main__':
    unittest.main()
