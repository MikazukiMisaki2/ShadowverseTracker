#!/usr/bin/env python3
"""
从 card_effects_chs.json 自动提取斩杀可信子集并生成 card_rules.json
支持：直伤、疾驰/突进、超进化技能、连击/唤灵/觉醒/协作条件、Token生成与循环调用
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# 正则清理 HTML 标签
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(text: str) -> str:
    """去除富文本标签并规范化标点"""
    text = TAG_RE.sub("", text)
    return text.replace(" ", "").replace("\n", " ")


class CardRuleExtractor:
    def __init__(self, raw_cards: Dict[str, Any]):
        self.raw_cards = raw_cards
        # 建立 卡牌名 -> card_id 的映射，用于关联 Token
        self.name_to_id = {c["name"]: cid for cid, c in raw_cards.items()}

    def extract_conditions(self, text: str) -> Dict[str, Any]:
        """提取触发条件"""
        conds = {}
        # 唤灵 (Necromancy)
        if m := re.search(r"【唤灵】_(\d+)", text):
            conds["cemetery_gte"] = int(m.group(1))
        # 连击 (Combo)
        if m := re.search(r"【连击】_(\d+)", text):
            conds["combo_gte"] = int(m.group(1))
        # 协作 (Rally)
        if m := re.search(r"【协作】_(\d+)", text):
            conds["rally_gte"] = int(m.group(1))
        # 爆能强化 (Enhance)
        if m := re.search(r"【爆能强化】_(\d+)", text):
            conds["enhance_cost"] = int(m.group(1))
        # 觉醒 (Overflow)
        if "【觉醒】" in text or "若为【觉醒】" in text:
            conds["overflow"] = True
        # 超进化解禁
        if "超进化已解禁" in text:
            conds["super_evolve_unlocked"] = True
        # 选择己方护符条件 (针对天书深渊等)
        if "若选择了自己的护符" in text:
            conds["target_is_ally_amulet"] = True
        return conds

    def extract_actions(self, text: str, related_ids: List[int]) -> List[Dict[str, Any]]:
        """提取动作效果列表"""
        actions = []

        # 1. 直伤类
        if m := re.search(r"对对手的主战者造成(\d+)点伤害", text):
            actions.append({"op": "deal_damage", "target": "enemy_leader", "amount": int(m.group(1))})
        elif m := re.search(r"对所有主战者造成(\d+)点伤害", text):
            actions.append({"op": "deal_damage", "target": "all_leaders", "amount": int(m.group(1))})
        elif m := re.search(r"选择对手的战场上的1个随从或对手的主战者，对其造成(\d+)点伤害", text):
            actions.append({"op": "deal_damage", "target_choice": ["enemy_leader", "enemy_follower"], "amount": int(m.group(1))})
        
        # 2. 回费类
        if m := re.search(r"回复自己(\d+)点能量点", text):
            actions.append({"op": "recover_pp", "amount": int(m.group(1))})

        # 3. 随从攻击力增益
        if m := re.search(r"本随从\+(\d+)/\+(\d+)", text):
            actions.append({"op": "buff_attack", "amount": int(m.group(1))})
        elif m := re.search(r"本随从\+(\d+)/\+?0", text):
            actions.append({"op": "buff_attack", "amount": int(m.group(1))})
        elif "本随从+X/+0。X为自己的【连击】" in text:
            actions.append({"op": "buff_attack", "scale_by": "combo_count"})

        # 4. 自身获得疾驰 / 给队友赋予疾驰
        if "本随从获得【疾驰】" in text or "使其获得【疾驰】" in text:
            if "选择自己的战场上的1个其他随从" in text:
                actions.append({"op": "grant_status", "target": "other_ally_follower", "status": "storm"})
            else:
                actions.append({"op": "gain_status", "status": "storm"})

        # 5. 多刀 (1回合攻击2次)
        if "1回合可以攻击2次" in text:
            actions.append({"op": "set_max_attacks", "amount": 2})

        # 6. Token 生成与递归手牌添加
        if m := re.findall(r"将(?:\d+张)?『(.*?)』加入手牌", text):
            token_ids = []
            for name in m:
                if name in self.name_to_id:
                    token_ids.append(int(self.name_to_id[name]))
            if token_ids:
                actions.append({"op": "add_to_hand", "card_ids": token_ids})

        return actions

    def parse_card(self, card_id: str, card_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """解析单张卡牌，若与斩杀无关则返回 None"""
        raw_skill = card_data.get("skill_text", "")
        raw_evo = card_data.get("evo_skill_text", "")
        related_ids = card_data.get("related_card_ids", [])
        card_type = card_data.get("type", 1)  # 1: 随从, 2/3: 护符, 4: 法术

        # 分离超进化技能 (<sev>...</sev>) 与普通技能
        sev_match = re.search(r"<sev>(.*?)</sev>", raw_skill + raw_evo)
        sev_text = clean_text(sev_match.group(1)) if sev_match else ""

        # 分离进化技能 (<ev>...</ev>)
        ev_match = re.search(r"<ev>(.*?)</ev>", raw_skill + raw_evo)
        ev_text = clean_text(ev_match.group(1)) if ev_match else ""

        base_text = clean_text(raw_skill)

        # 静态词条检测
        has_storm = "【疾驰】" in base_text and "获得【疾驰】" not in base_text
        has_rush = "【突进】" in base_text and "获得【突进】" not in base_text
        ignore_ward = "可以无视【守护】" in base_text

        # 效果解析
        on_play_effects = []
        on_evolve_effects = []
        on_super_evolve_effects = []

        # 1. 解析入场曲 / 法术基础效果
        play_actions = self.extract_actions(base_text, related_ids)
        if play_actions:
            conds = self.extract_conditions(base_text)
            on_play_effects.append({"if": conds, "do": play_actions} if conds else {"do": play_actions})

        # 2. 解析进化效果
        if ev_text:
            ev_actions = self.extract_actions(ev_text, related_ids)
            if ev_actions:
                on_evolve_effects.append({"do": ev_actions})

        # 3. 解析超进化效果
        if sev_text:
            sev_actions = self.extract_actions(sev_text, related_ids)
            if sev_actions:
                on_super_evolve_effects.append({"do": sev_actions})

        # 斩杀相关性过滤：如果既无直伤、疾驰、增攻、回费、多刀，也无超进化赋能，则排除
        is_lethal_relevant = (
            has_storm
            or bool(on_play_effects)
            or bool(on_evolve_effects)
            or bool(on_super_evolve_effects)
        )

        if not is_lethal_relevant:
            return None

        rule = {
            "name": card_data.get("name", ""),
            "cost": card_data.get("cost", 0),
            "type": card_type,
        }

        static_flags = {}
        if has_storm: static_flags["has_storm"] = True
        if has_rush: static_flags["has_rush"] = True
        if ignore_ward: static_flags["ignore_ward"] = True
        if static_flags: rule["static"] = static_flags

        if on_play_effects: rule["on_play"] = on_play_effects
        if on_evolve_effects: rule["on_evolve"] = on_evolve_effects
        if on_super_evolve_effects: rule["on_super_evolve"] = on_super_evolve_effects

        return rule


def main():
    source_path = Path("card_effects_chs.json")
    target_path = Path("card_rules.json")

    if not source_path.exists():
        print(f"错误: 找不到输入文件 {source_path}")
        return

    with open(source_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cards = data.get("cards", {})
    extractor = CardRuleExtractor(cards)

    rules = {}
    for cid, cdata in cards.items():
        parsed = extractor.parse_card(cid, cdata)
        if parsed:
            rules[cid] = parsed

    # 手动补丁注入：处理极少数含有深层逻辑/特殊目标连锁的 Token 机制
    # 例如：天书深渊 (选择己方护符打 2 脸并回收自身)
    rules["90064320"] = {
        "name": "天书深渊",
        "cost": 0,
        "type": 4,
        "on_play": [
            {
                "if": {"target_is_ally_amulet": True},
                "do": [
                    {"op": "destroy_target", "target": "selected_ally_amulet"},
                    {"op": "deal_damage", "target": "enemy_leader", "amount": 2},
                    {"op": "add_to_hand", "card_ids": [90064320]}  # 递归自循环
                ]
            }
        ]
    }

    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)

    print(f"成功转换！共扫描 {len(cards)} 张卡牌，提取出 {len(rules)} 张斩杀相关卡牌规则 -> {target_path}")


if __name__ == "__main__":
    main()