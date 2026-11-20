function onSubmit(event) {
  if (!event || !event.response) {
    throw new Error('Googleフォームの送信トリガーから実行してください。');
  }
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const properties = PropertiesService.getScriptProperties();
    let webhook = properties.getProperty('DISCORD_WEBHOOK_URL');
    if (!webhook) throw new Error('DISCORD_WEBHOOK_URL が未設定です。');
    webhook = webhook.trim().replace(/\?.*$/, '').replace(/\/$/, '');
    if (properties.getProperty('DISCORD_USE_CANARY') !== 'false') {
      webhook = webhook.replace('https://discord.com/', 'https://canary.discord.com/');
    }
    const responseId = event.response.getId();
    const savedKey = 'CAMP_POSTED_' + responseId;
    if (properties.getProperty(savedKey)) return;

    const fields = [];
    for (const item of event.response.getItemResponses()) {
      const name = item.getItem().getTitle();
      const answer = item.getResponse();
      const value = (Array.isArray(answer) ? answer.join('、') : String(answer ?? '')).trim() || '記入なし';
      fields.push({ name, value });
    }
    // 最初の質問「名称」の回答をカードの見出しにする。
    const title = fields[0]?.value || '名称未記入';
    if (title.length > 256) {
      throw new Error('名称は256文字以内で入力してください。');
    }
    // 名称は見出しだけに表示し、本文は2番目の質問からにする。
    fields.shift();
    // 全質問をDiscordに公開するため、フォームには公開してよい項目だけを置く。
    const length = fields.reduce((sum, field) => sum + field.name.length + field.value.length, 0);
    if (fields.length > 25 || fields.some(f => !f.name || f.name.length > 256 || f.value.length > 1024) || length > 5500) {
      throw new Error('質問数または文字数がDiscordの上限を超えています。');
    }
    const payload = {
      allowed_mentions: { parse: [] },
      embeds: [{
        title,
        color: 0xFF69B4,
        description: '1️⃣ 第一志望　2️⃣ 第二志望　3️⃣ 第三志望',
        fields,
      }],
    };
    // Discordが指定した待機時間中は再送しない。
    const webhookId = webhook.match(/\/webhooks\/(\d+)\//)?.[1];
    const cooldownKey = 'CAMP_RETRY_AFTER_' + webhookId;
    const retryAt = Number(properties.getProperty(cooldownKey) || 0);
    if (Date.now() < retryAt) {
      throw new Error('Discord投稿待機中。あと' + Math.ceil((retryAt - Date.now()) / 1000) + '秒。回答はフォームに保存されています。');
    }
    let response;
    try {
      response = UrlFetchApp.fetch(webhook + '?wait=true', {
        method: 'post',
        contentType: 'application/json',
        payload: JSON.stringify(payload),
        muteHttpExceptions: true,
      });
    } catch (_) {
      throw new Error('Discordへの通信に失敗しました。再送前に投稿の有無を確認してください。');
    }
    const status = response.getResponseCode();
    if (status === 429) {
      const headers = response.getAllHeaders();
      const header = name => {
        const key = Object.keys(headers).find(key => key.toLowerCase() === name.toLowerCase());
        return key ? String(headers[key]) : '';
      };
      let body = {};
      try { body = JSON.parse(response.getContentText()); } catch (_) {}
      const retryHeader = header('Retry-After');
      const headerSeconds = retryHeader && !Number.isNaN(Number(retryHeader))
        ? Number(retryHeader)
        : (Date.parse(retryHeader) - Date.now()) / 1000;
      const seconds = Math.max(0, Number(body.retry_after) || 0, Number.isFinite(headerSeconds) ? headerSeconds : 0);
      if (seconds > 0) {
        properties.setProperty(cooldownKey, String(Date.now() + Math.ceil(seconds * 1000) + 3000));
      }
      console.error('Discord制限: 待ち秒数=' + (seconds || '不明') +
        ' / scope=' + (header('X-RateLimit-Scope') || '不明') +
        ' / CF-Ray=' + (header('CF-Ray') || 'なし'));
      throw new Error('Discord投稿失敗 HTTP 429。' +
        (seconds > 0 ? Math.ceil(seconds + 3) + '秒以上待ってください。' : '待ち時間の指定がありません。連続再送を停止してください。') +
        ' 自動再送はしません。回答はフォームに保存されています。');
    }
    if (status < 200 || status >= 300) {
      throw new Error('Discord投稿失敗 HTTP ' + status);
    }
    const message = JSON.parse(response.getContentText());
    properties.setProperty(savedKey, message.id);
    console.log('投稿成功 message=' + message.id);
  } finally {
    lock.releaseLock();
  }
}
