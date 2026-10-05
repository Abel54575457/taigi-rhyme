"""
台語押韻比對工具 (Taiwanese Rhyme Helper)
支援台羅拼音 (Tai-lo) / 白話字 (POJ) 音節解析與十三部押韻歸類
"""

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

# 避免 Windows cp950 終端機編碼錯誤
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


# 聲調符號對照表 (Unicode 組合或預組字符轉換成無調符號)
TONE_DIACRITICS_MAP = {
    'á': 'a', 'à': 'a', 'â': 'a', 'ā': 'a', 'a̍': 'a', 'a̋': 'a', 'ă': 'a',
    'é': 'e', 'è': 'e', 'ê': 'e', 'ē': 'e', 'e̍': 'e', 'e̋': 'e', 'ĕ': 'e',
    'í': 'i', 'ì': 'i', 'î': 'i', 'ī': 'i', 'i̍': 'i', 'i̋': 'i', 'ĭ': 'i',
    'ó': 'o', 'ò': 'o', 'ô': 'o', 'ō': 'o', 'o̍': 'o', 'ő': 'o', 'ŏ': 'o',
    'ú': 'u', 'ù': 'u', 'û': 'u', 'ū': 'u', 'u̍': 'u', 'ű': 'u', 'ŭ': 'u',
    'ḿ': 'm', 'm̀': 'm', 'm̂': 'm', 'm̄': 'm', 'm̍': 'm',
    'ń': 'n', 'ǹ': 'n', 'n̂': 'n', 'n̄': 'n', 'n̍': 'n',
}

# Unicode Combining Diacritics 聲調對應 (台羅/白話字)
DIACRITIC_TO_TONE = {
    '\u0301': 2,  # acute (2聲 陰上)
    '\u0300': 3,  # grave (3聲 陰去)
    '\u0302': 5,  # circumflex (5聲 陽平)
    '\u030c': 6,  # caron (6聲 陽上)
    '\u0306': 6,  # breve
    '\u0304': 7,  # macron (7聲 陽去)
    '\u030d': 8,  # vertical line above (8聲 陽入)
    '\u030b': 9,  # double acute (9聲)
}

# 台語聲母列表 (由長到短排序以優先匹配複合聲母)
INITIALS = [
    'tsh', 'chh',  # ㄘ
    'ts', 'ch',    # ㄗ
    'ph',          # ㄆ
    'th',          # ㄊ
    'kh',          # ㄎ
    'ng',          # ㄫ
    'p', 'b', 'm',
    't', 'd', 'n', 'l',
    'k', 'g', 'h',
    's', 'j'
]


class TaiwaneseRhymeMatcher:
    def __init__(self, json_path: Optional[str] = None):
        if json_path is None:
            json_path = Path(__file__).parent / "rhyme_groups.json"
        
        with open(json_path, "r", encoding="utf-8") as f:
            self.rhyme_groups: Dict[str, Dict[str, Any]] = json.load(f)
        
        # 建立 韻母 variant -> group_id 的快速反查索引
        self.variant_to_group: Dict[str, str] = {}
        for group_id, info in self.rhyme_groups.items():
            for v in info.get("variants", []):
                self.variant_to_group[v.lower()] = group_id

    @staticmethod
    def strip_tone(syllable: str) -> Tuple[str, Optional[int]]:
        """
        移除音節中的聲調符號或數字聲調，回傳 (無調拼音, 聲調數字 1~8)
        例如: 'tshiâng' -> ('tshiang', 5), 'hue1' -> ('hue', 1), 'kok' -> ('kok', 4)
        """
        s = syllable.strip().lower()
        if not s:
            return "", None
            
        is_neutral = False
        if s.startswith('--'):
            is_neutral = True
            s = s[2:]
        
        # 檢查結尾數字調號
        tone_num = None
        if s and s[-1].isdigit():
            tone_num = int(s[-1])
            s = s[:-1]
        
        # 處理 POJ 鼻化符號 ⁿ -> nn，以及 o͘ -> oo
        s = s.replace('ⁿ', 'nn')
        s = s.replace('o͘', 'oo').replace('o\u0358', 'oo')
        
        # 處理 Unicode 分解調號 (檢測 combining mark 判斷聲調)
        decomposed = unicodedata.normalize('NFD', s)
        filtered = []
        for ch in decomposed:
            if ch in DIACRITIC_TO_TONE and tone_num is None:
                tone_num = DIACRITIC_TO_TONE[ch]
            # 排除非字母重音組合符
            if unicodedata.category(ch) != 'Mn':
                filtered.append(ch)
        s = "".join(filtered)
        
        # 替換殘留的特殊預組字母
        for k, v in TONE_DIACRITICS_MAP.items():
            s = s.replace(k, v)
            
        clean_s = re.sub(r'[^a-z]', '', s)
        
        # 若仍無聲調，依舒聲/入聲規則判定本調
        if is_neutral:
            tone_num = 0
        elif tone_num is None and clean_s:
            if clean_s[-1] in ('p', 't', 'k', 'h'):
                tone_num = 4  # 陰入聲 (無調符塞音/喉塞音尾)
            else:
                tone_num = 1  # 陰平聲 (舒聲預設為1聲)
                
        return clean_s, tone_num

    def split_syllable(self, syllable: str) -> Tuple[str, str, Optional[int]]:
        """
        將音節拆分為 (聲母, 韻母, 聲調)
        例如: 'tshiâng' -> ('tsh', 'iang', 5)
        """
        clean_s, tone = self.strip_tone(syllable)
        
        # 移除可能的多餘符號（如連字號）
        clean_s = re.sub(r'[^a-z]', '', clean_s)
        
        # 匹配聲母
        matched_initial = ""
        remainder = clean_s
        for init in INITIALS:
            if clean_s.startswith(init):
                # 排除單獨的 m/ng 韻化音節 (例如 ng5 黃，此時 ng 是韻母不是聲母)
                if clean_s == init:
                    break
                matched_initial = init
                remainder = clean_s[len(init):]
                break
                
        return matched_initial, remainder, tone

    def get_rhyme_group(self, syllable: str) -> Optional[Dict[str, Any]]:
        """
        查詢特定音節屬於哪一個韻部
        """
        _, rhyme, _ = self.split_syllable(syllable)
        
        group_id = self.variant_to_group.get(rhyme)
        if group_id:
            group_info = self.rhyme_groups[group_id]
            return {
                "input": syllable,
                "rhyme": rhyme,
                "group_id": group_id,
                "description": group_info["description"],
                "type": group_info["type"],
                "all_variants": group_info["variants"]
            }
        return None

    def can_rhyme(self, syllable1: str, syllable2: str) -> Tuple[bool, Optional[str]]:
        """
        判斷兩個音節是否押韻 (屬於同一韻部)
        """
        info1 = self.get_rhyme_group(syllable1)
        info2 = self.get_rhyme_group(syllable2)
        
        if not info1 or not info2:
            return False, None
            
        if info1["group_id"] == info2["group_id"]:
            return True, info1["group_id"]
        return False, None


if __name__ == "__main__":
    matcher = TaiwaneseRhymeMatcher()
    
    test_cases = [
        "kha", "hua", "huann", "tshiâng", "bāng", "suann", "kuan", 
        "ue", "teh", "tshiat", "kok", "hó", "tshùi"
    ]
    
    print("=== 音節歸納測試 ===")
    for word in test_cases:
        res = matcher.get_rhyme_group(word)
        if res:
            print(f"[{word:8s}] -> 韻母: {res['rhyme']:6s} | 韻部: {res['group_id']:12s} ({res['description']})")
        else:
            print(f"[{word:8s}] -> 未能匹配韻部")
            
    print("\n=== 押韻判定測試 ===")
    pairs = [
        ("kha", "hua"),
        ("tshiâng", "bāng"),
        ("suann", "kuan"),
        ("kok", "tshiat")
    ]
    for s1, s2 in pairs:
        rhymes, grp = matcher.can_rhyme(s1, s2)
        print(f"'{s1}' 與 '{s2}' 是否押韻？ {'✓ 是' if rhymes else '✗ 否'} ({grp})")
