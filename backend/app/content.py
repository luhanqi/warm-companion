from __future__ import annotations

from typing import Any, Dict, List, Optional

SONGS: List[Dict[str, Any]] = [
    {
        "id": "molihua",
        "title": "茉莉花",
        "artist": "江苏民歌",
        "year": 1950,
        "decade": "50后",
        "lyrics": "好一朵美丽的茉莉花，好一朵美丽的茉莉花，芬芳美丽满枝桠，又香又白人人夸。",
        "story": "这是一首江苏民歌，后来唱遍全国。许多人第一次听到，是在收音机里，或是学校的合唱里。",
        "chapter": "youth",
        "notes": [392, 440, 523, 523, 440, 392, 349, 392, 440, 392],
    },
    {
        "id": "dongfanghong",
        "title": "东方红",
        "artist": "陕北民歌改编",
        "year": 1964,
        "decade": "60后",
        "lyrics": "东方红，太阳升，中国出了个毛泽东。",
        "story": "一九六四年前后，这首歌常在广播里响起。许多人记得天刚亮、巷子里的喇叭声。",
        "chapter": "youth",
        "notes": [392, 392, 440, 392, 349, 330, 294, 330, 349, 392],
    },
    {
        "id": "wodezuguo",
        "title": "我的祖国",
        "artist": "刘炽 / 郭兰英",
        "year": 1956,
        "decade": "50后",
        "lyrics": "一条大河波浪宽，风吹稻花香两岸。",
        "story": "电影《上甘岭》里的插曲。有人想起河边洗衣，有人想起第一次进电影院。",
        "chapter": "youth",
        "notes": [330, 349, 392, 523, 440, 392, 349, 330, 294, 330],
    },
    {
        "id": "nanniwan",
        "title": "南泥湾",
        "artist": "马可 / 郭兰英",
        "year": 1943,
        "decade": "50后",
        "lyrics": "花篮的花儿香，听我来唱一唱。",
        "story": "唱的是开荒种地。许多从乡下出来的人，听到还是会想起自己种过的田。",
        "chapter": "childhood",
        "notes": [392, 440, 392, 349, 330, 294, 330, 349, 392, 330],
    },
    {
        "id": "honghu",
        "title": "洪湖水浪打浪",
        "artist": "王玉珍",
        "year": 1961,
        "decade": "60后",
        "lyrics": "洪湖水呀浪呀嘛浪打浪啊，洪湖岸边是呀嘛是家乡啊。",
        "story": "歌剧里的名段。水乡的人听着像回家，北方的人听着像看见了荷叶。",
        "chapter": "youth",
        "notes": [440, 523, 440, 392, 349, 392, 440, 349, 330, 294],
    },
    {
        "id": "tianye",
        "title": "在希望的田野上",
        "artist": "施光南 / 彭丽媛",
        "year": 1981,
        "decade": "80后",
        "lyrics": "我们的家乡，在希望的田野上。",
        "story": "改革开放以后常唱。有人想起分田到户，有人想起第一次听录音机。",
        "chapter": "work",
        "notes": [392, 440, 494, 523, 494, 440, 392, 349, 330, 392],
    },
    {
        "id": "shuangjiang",
        "title": "让我们荡起双桨",
        "artist": "刘炽 / 乔羽",
        "year": 1955,
        "decade": "50后",
        "lyrics": "让我们荡起双桨，小船儿推开波浪。",
        "story": "少年时的歌。北海、公园、学校春游，常和这首歌叠在一起。",
        "chapter": "childhood",
        "notes": [330, 349, 392, 440, 392, 349, 330, 294, 262, 330],
    },
    {
        "id": "liuyanghe",
        "title": "浏阳河",
        "artist": "湖南民歌",
        "year": 1951,
        "decade": "50后",
        "lyrics": "浏阳河，弯过了几道弯。",
        "story": "水路弯弯的歌。有人想起家乡的河，有人想起第一次出远门坐的船。",
        "chapter": "childhood",
        "notes": [349, 392, 440, 392, 349, 330, 294, 330, 349, 392],
    },
]

EVENTS: List[Dict[str, Any]] = [
    {
        "year": 1956,
        "title": "对私有制的社会主义改造基本完成",
        "desc": "城里的铺子、厂子陆续公私合营。许多人的青春，是从学徒变成工人开始的。",
        "chapter": "youth",
    },
    {
        "year": 1964,
        "title": "第一颗原子弹爆炸成功",
        "desc": "广播里反复播报。有人在车间里听，有人在田埂上听，都记得那天的喇叭声。",
        "chapter": "youth",
    },
    {
        "year": 1971,
        "title": "恢复联合国合法席位",
        "desc": "报纸头条、单位学习。世界忽然变大了，收音机里的国际新闻多了起来。",
        "chapter": "work",
    },
    {
        "year": 1978,
        "title": "十一届三中全会",
        "desc": "后来叫做改革开放。有人回城，有人考大学，有人第一次知道“搞活”。",
        "chapter": "work",
    },
    {
        "year": 1984,
        "title": "国庆三十五周年阅兵",
        "desc": "电视开始走进更多家庭。一家人围着小屏幕，看天安门前过车。",
        "chapter": "family",
    },
    {
        "year": 1990,
        "title": "第十一届亚运会在北京举行",
        "desc": "盼盼、开幕式、单位组织观看。那是许多人口中“国家真的不一样了”的一年。",
        "chapter": "family",
    },
]

CHAPTERS = [
    {"key": "childhood", "title": "童年", "prompt": "您小时候在哪里长大？院子里有什么？"},
    {"key": "youth", "title": "青年", "prompt": "年轻时您做过什么？最记得哪一首歌？"},
    {"key": "work", "title": "工作", "prompt": "在厂里或单位里，您最记得谁？"},
    {"key": "family", "title": "家庭", "prompt": "家里人都好着吗？第一次成家是什么时候？"},
    {"key": "retire", "title": "现在", "prompt": "退休以后，一天愿意怎么过？"},
]


def find_song(song_id: str) -> Optional[Dict[str, Any]]:
    for song in SONGS:
        if song["id"] == song_id:
            return song
    return None


def match_song(text: str) -> Optional[Dict[str, Any]]:
    for song in SONGS:
        if song["title"] in text or song["id"] in text:
            return song
    if any(word in text for word in ("放首歌", "听歌", "唱一首", "老歌")):
        return SONGS[0]
    return None
