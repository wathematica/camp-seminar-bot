# Dockerでの運用

## 起動まで

Linuxサーバー、Docker EngineとCompose、設定用のPython 3を用意します。サーバーへSSH接続できる必要があります。Tailscaleは管理用の接続経路として利用できますが、Botの必須条件ではありません。

```sh
git clone https://github.com/wathematica/camp-seminar-bot.git
cd camp-seminar-bot
python3 configure.py
```

BotトークンとGASと同じWebhook URLを入力します。`configure.py` は非表示で入力し、`secrets/` 配下のファイルに保存します。このフォルダーはGitとDockerイメージから除外されます。Dockerは起動時にそのファイルを読み込みます。

設定変更が必要なら：

```sh
cp .env.example .env
```

| 設定 | 初期値・用途 |
|---|---|
| `FIRST_CHOICE_THRESHOLD` | `3`：緑色になる第一志望の人数 |
| `EXPECTED_BOT_ID` | 空欄：任意。設定するとBot IDの取り違えを検出 |

秘密情報は `.env` に書かず、`configure.py` で入力します。

```sh
docker compose up -d --build
docker compose ps
docker compose logs --tail=60 camp-bot
```

「接続完了」を確認し、フォーム投稿とリアクションを試します。初回は過去のチャンネル履歴を1分に最大200件ずつ確認するため、履歴が多い場合は時間がかかります。

## 常時稼働

Botは外向きのHTTPSとDiscord Gateway接続を使います。公開Webサーバーや受信ポートの開放は不要です。

コンテナは `restart: unless-stopped` で動きます。異常終了時やDocker再起動後に再起動しますが、手動で停止したものは自動再開しません。サーバー起動時にDockerサービス自体も起動する設定にしてください。

ヘルスチェックは定期確認が継続しているかを調べます。`unhealthy` になっても自動再起動はしません。ログとネットワーク・権限を確認します。

## 更新・停止・再開

```sh
# 更新（先に作業中の変更がないか確認）
git status
git pull --ff-only
docker compose up -d --build

# 状態・ログ
docker compose ps
docker compose logs --tail=100 camp-bot

# 停止・再開
docker compose stop
docker compose start
```

投稿IDと履歴の位置は `camp-data` ボリュームに保存します。`docker compose down -v` はこの記録も削除するため、通常の停止には使いません。ボリュームが失われた場合は履歴から再走査しますが、完了まで時間がかかります。

同じWebhookに複数のBotプロセスを同時に動かさないでください。Webhookを変更する場合は、新しい作業フォルダー・Composeプロジェクトで起動し、以前の保存データを混ぜないようにします。

## 困ったとき

| 症状 | 確認箇所 |
|---|---|
| カードが投稿されない | Apps Scriptの `onSubmit` 実行履歴、Webhook、フォーム側のトリガー |
| リアクションが付かない | Botの接続ログ、対象サーバーへの参加、チャンネル権限、GASとBotのWebhookの一致 |
| 第二・第三志望が0人 | 同じ人が上位の志望も押していないか。最上位だけを集計します |
| 起動後すぐ終了 | トークン、Webhook URL、任意の `EXPECTED_BOT_ID` の一致 |
| `40333` | Cloudflareによるブロック。通常の権限不足と決めつけず、実行環境・操作・エラーを記録して調査 |
| `unhealthy` | `docker compose logs` で履歴確認の失敗を調べる |

ログに秘密情報を追加しないでください。トークンやWebhook URLを誤って公開した場合は、Discord側で無効化・再発行して設定を差し替えます。
