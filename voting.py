"""Discordへの通信を行わず、投票の集計とカードの表示を組み立てる。"""
import copy

EMOJIS = ('1️⃣', '2️⃣', '3️⃣')
VOTE_GUIDE = '1️⃣ 第一志望　2️⃣ 第二志望　3️⃣ 第三志望'


def is_proposal(embed):
    """説明文の先頭に投票案内があるカードを処理対象にする。"""
    # 呼び出し側で対象のWebhook・チャンネルに限定している。
    description = embed.get('description', '')
    return description.split('\n')[0] == VOTE_GUIDE


def count_votes(voters_by_rank):
    """同じ人の票は、最も高い志望にだけ数える。"""
    seen = set()
    counts = []
    for voters in voters_by_rank:
        counts.append(len(set(voters) - seen))
        seen.update(voters)
    return counts


def render_embed(original, counts, threshold=3):
    """元のカードをコピーし、人数・募集状態・色を更新する。"""
    embed = copy.deepcopy(original)
    ready = counts[0] >= threshold
    embed['color'] = 0x57F287 if ready else 0xFF69B4
    embed['description'] = (VOTE_GUIDE + '\n'
                            'この班での希望順位を1つ押してください。変更時は元のリアクションを外してください。')
    status = '' if ready else f'募集中：第一志望あと{threshold - counts[0]}人で成立目安'
    footer = dict(embed.get('footer', {}))
    footer['text'] = (f'第一志望 {counts[0]}人 ｜ 第二志望 {counts[1]}人 ｜ 第三志望 {counts[2]}人' + ('\n' + status if status else ''))
    embed['footer'] = footer
    # Discordの応答専用項目は、編集データには含めない。
    for key in ('provider', 'video'):
        embed.pop(key, None)
    return embed
