"""Interactive local launch; tokens stay in memory, safe logs stay on disk."""
import asyncio
import getpass
import logging
import os
from pathlib import Path
import re

from bot import CampBot

ROOT = Path(__file__).resolve().parent


async def run():
    print('春合宿Botの実機テストです。対象Webhookの既存カードも更新します。')
    print('GASの定期集計は停止したままにしてください。')
    print('秘密情報は非表示で入力し、ファイルには保存しません。')
    token = getpass.getpass('Botトークン: ').strip()
    webhook = getpass.getpass('テスト投稿と同じWebhook URL: ').strip()
    if not token or not re.fullmatch(r'https://(?:canary\.)?discord\.com/api/(?:v\d+/)?webhooks/\d+/[A-Za-z0-9._-]+', webhook):
        print('入力形式を確認してください。')
        return
    webhook = webhook.replace('https://canary.discord.com/', 'https://discord.com/')
    threshold = input('緑になる第一志望人数（通常3／一人で色を試すなら1、Enterで3）: ').strip() or '3'
    if not threshold.isdigit() or int(threshold) < 1:
        print('人数は1以上の整数を入力してください。')
        return
    os.environ['FIRST_CHOICE_THRESHOLD'] = threshold
    os.environ['DATABASE_PATH'] = str(ROOT / 'local-data' / 'camp.sqlite3')
    os.environ['HEARTBEAT_PATH'] = str(ROOT / 'local-data' / 'heartbeat')
    print(f'成立目安：第一志望{threshold}人。停止はControl+C。テスト中はこの画面を開いたままにしてください。')
    logger = logging.getLogger('camp')
    logger.setLevel(logging.INFO)
    for handler in (logging.StreamHandler(), logging.FileHandler(ROOT / 'local-test.log', mode='w')):
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
    try:
        async with CampBot(webhook) as client:
            await client.start(token)
    except Exception as error:
        logger.error('起動・接続失敗 kind=%s HTTP=%s code=%s', type(error).__name__, getattr(error, 'status', ''), getattr(error, 'code', ''))


if __name__ == '__main__':
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, EOFError):
        print('\nBotを停止しました。')
