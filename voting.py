"""Voting rules independent of Discord/network access."""
import copy

EMOJIS = ('1️⃣', '2️⃣', '3️⃣')
VOTE_GUIDE = '1️⃣ 第一志望　2️⃣ 第二志望　3️⃣ 第三志望'


def is_proposal(embed, legacy_title):
    """Accept legacy cards and cards headed by the first 名称 answer."""
    fields = embed.get('fields', [])
    # Caller already restricts messages to the configured webhook/channel.
    return embed.get('description', '').split('\n')[0] == VOTE_GUIDE or embed.get('title') == legacy_title or bool(
        fields and fields[0].get('name') == '名称'
        and fields[0].get('value') == embed.get('title')
    )


def count_votes(voters_by_rank):
    seen = set()
    counts = []
    for voters in voters_by_rank:
        counts.append(len(set(voters) - seen))
        seen.update(voters)
    return counts


def render_embed(original, counts, threshold=3):
    embed = copy.deepcopy(original)
    fields = embed.get('fields', [])
    if fields and fields[0].get('name') == '名称' and fields[0].get('value') == embed.get('title'):
        embed['fields'] = fields[1:]
    ready = counts[0] >= threshold
    embed['color'] = 0x57F287 if ready else 0xFF69B4
    embed['description'] = (VOTE_GUIDE + '\n'
                            'この班での希望順位を1つ押してください。変更時は元のリアクションを外してください。')
    status = '' if ready else f'募集中：第一志望あと{threshold - counts[0]}人で成立目安'
    footer = dict(embed.get('footer', {}))
    footer['text'] = (f'第一志望 {counts[0]}人 ｜ 第二志望 {counts[1]}人 ｜ 第三志望 {counts[2]}人' + ('\n' + status if status else ''))
    embed['footer'] = footer
    # Response-only fields are not needed when editing an embed.
    for key in ('provider', 'video'):
        embed.pop(key, None)
    return embed
