from __future__ import annotations

import re
from typing import Dict, List, Tuple

PersonWrite = Dict[str, str]
FactWrite = Dict[str, str]


def extract_memory(text: str) -> Tuple[List[PersonWrite], List[FactWrite]]:
    """规则抽取，没有大模型时也能把家人、爱好写进黑板。"""
    people: List[PersonWrite] = []
    facts: List[FactWrite] = []
    seen_people = set()

    patterns = [
        (r"(?:我的?)?儿子叫([\u4e00-\u9fffA-Za-z]{1,12})", "儿子"),
        (r"(?:我的?)?女儿叫([\u4e00-\u9fffA-Za-z]{1,12})", "女儿"),
        (r"(?:我的?)?孙子叫([\u4e00-\u9fffA-Za-z]{1,12})", "孙子"),
        (r"(?:我的?)?孙女叫([\u4e00-\u9fffA-Za-z]{1,12})", "孙女"),
        (r"(?:我的?)?老伴(?:叫|是)([\u4e00-\u9fffA-Za-z]{1,12})", "老伴"),
        (r"(?:我的?)?丈夫叫([\u4e00-\u9fffA-Za-z]{1,12})", "丈夫"),
        (r"(?:我的?)?妻子叫([\u4e00-\u9fffA-Za-z]{1,12})", "妻子"),
    ]
    for pattern, relation in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip("的了啊呀呢吗")
            key = (relation, name)
            if name and key not in seen_people:
                seen_people.add(key)
                people.append({"relation": relation, "name": name, "note": ""})

    like = re.search(r"我喜欢(.{1,20}?)(?:[，。！？\s]|$)", text)
    if like:
        facts.append({"key": "爱好", "value": "喜欢" + like.group(1).strip(), "source": "user"})

    work = re.search(r"(?:以前|曾经|年轻时)?在(.{2,20}?)(?:工作|上班|做工)", text)
    if work:
        facts.append({"key": "工作", "value": "曾在%s工作" % work.group(1).strip(), "source": "user"})

    home = re.search(r"(?:老家在|我是)([\u4e00-\u9fff]{2,12})(?:人|的)", text)
    if home:
        facts.append({"key": "籍贯", "value": home.group(1).strip(), "source": "user"})

    song = re.search(r"(?:喜欢听|想听|爱听)[《「]?([^》」，。！？]{1,16})", text)
    if song:
        facts.append({"key": "爱好", "value": "喜欢听%s" % song.group(1).strip(), "source": "user"})

    return people, facts
