"""Run on the destination server. Do not pass secrets as command arguments."""
import getpass
import os
from pathlib import Path
import re


def main():
    os.umask(0o077)
    directory = Path(__file__).resolve().parent / 'secrets'
    directory.mkdir(exist_ok=True, mode=0o700)
    if any((directory / name).exists() for name in ('bot_token', 'webhook_url')):
        if input('既存の接続情報を上書きしますか？ yes の場合のみ続行: ') != 'yes':
            return
    token = getpass.getpass('Botトークン（非表示）: ').strip()
    webhook = getpass.getpass('GASと同じWebhook URL（非表示）: ').strip()
    if not token or token.startswith('Bot ') or any(c.isspace() for c in token):
        raise ValueError('トークン本体だけを入力してください。')
    if not re.fullmatch(r'https://(?:canary\.)?discord\.com/api/(?:v\d+/)?webhooks/\d+/[A-Za-z0-9._-]+', webhook):
        raise ValueError('通常のテキストチャンネル用Webhook URLを入力してください。')
    webhook = webhook.replace('https://canary.discord.com/', 'https://discord.com/')
    for name, value in [('bot_token', token), ('webhook_url', webhook)]:
        path = directory / name
        path.write_text(value, encoding='utf-8')
        path.chmod(0o600)
    print('接続情報を保存しました。docker compose up -d --build で起動できます。')


if __name__ == '__main__':
    main()
