"""Persist known messages and the history cursor across restarts."""
import sqlite3
from pathlib import Path


class Store:
    def __init__(self, path, webhook_id):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY)')
        self.db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)')
        old = self.get('webhook')
        if old and old != str(webhook_id):
            raise ValueError('別Webhook用の保存データです。新しいデータ領域を使用してください。')
        self.set('webhook', str(webhook_id))

    def get(self, key):
        row = self.db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return row[0] if row else None

    def set(self, key, value):
        self.db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, str(value)))
        self.db.commit()

    def add(self, message_id):
        self.db.execute('INSERT OR IGNORE INTO messages VALUES (?)', (str(message_id),))
        self.db.commit()

    def remove(self, message_id):
        self.db.execute('DELETE FROM messages WHERE id=?', (str(message_id),))
        self.db.commit()

    def contains(self, message_id):
        return self.db.execute('SELECT 1 FROM messages WHERE id=?', (str(message_id),)).fetchone() is not None

    def ids(self):
        return [int(row[0]) for row in self.db.execute('SELECT id FROM messages')]

    def close(self):
        self.db.close()
