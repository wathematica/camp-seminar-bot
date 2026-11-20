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
