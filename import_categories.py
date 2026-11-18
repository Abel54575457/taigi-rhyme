"""
台語常用詞辭典 28,695 條全方位主題分類、近反義詞釋義補全與多對多標籤庫重建腳本
1. 從 ../台語/kautian.ods 讀取《義項tuì詞目近義》、《詞目tuì詞目近義》、《義項tuì詞目反義》、《義項tuì義項近義》，
   自動補全「近反義詞不單列詞目者」與「臺華共同詞」之釋義、詞性、原始分類與雙向近義詞關聯表 (synonyms)。
2. 完整涵蓋 22 大主題領域：天氣、植物、動物、菜餚、魚類、昆蟲、心情、飲食、地理、天文、人生、身體、器物、服飾、建築、社會、民俗、文藝、動作、狀態、言語、時空。
"""

import os
import sys
import re
import time
import zipfile
import sqlite3
import xml.etree.ElementTree as ET
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 主題分類優先級（當決定 words.category_main 單一主分類時使用）
CATEGORY_PRIMARY_PRIORITY = [
    "昆蟲", "魚類", "菜餚", "天氣", "天文", "服飾", "建築", "地理", 
    "民俗", "植物", "動物", "心情", "飲食", "人生", "身體", 
    "文藝", "器物", "社會", "動作", "狀態", "時空", "言語", "其他"
]


def enrich_from_ods(conn, ods_path="../台語/kautian.ods"):
    """
    從教育部 kautian.ods 補全近反義詞釋義、原始分類與 synonyms 關聯
    """
    if not os.path.exists(ods_path):
        print(f"ODS file {ods_path} not found, skipping ODS enrichment.")
        return

    t0 = time.time()
    print(f"Reading {ods_path} to enrich synonyms & missing definitions...")
    ns = {
        'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
        'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
        'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0'
    }

    def get_val(c):
        txt = ''.join(p.text or '' for p in c.findall('.//text:p', ns)).strip()
        if not txt:
            val = c.attrib.get('{urn:oasis:names:tc:opendocument:xmlns:office:1.0}value')
            if val is not None:
                return str(int(float(val))) if val.replace('.', '', 1).isdigit() else str(val)
        return txt

    with zipfile.ZipFile(ods_path, 'r') as z:
        with z.open('content.xml') as f:
            root = ET.parse(f).getroot()

    t_map = {t.attrib.get('{urn:oasis:names:tc:opendocument:xmlns:table:1.0}name'): t for t in root.findall('.//table:table', ns)}

    # 1. 讀取 義項id -> (詞目id, 詞性, 解說)
    y_to_entry = {}
    y_table = t_map.get('義項')
    if y_table is not None:
        for r in y_table.findall('.//table:table-row', ns)[1:]:
            vals = [get_val(c) for c in r.findall('.//table:table-cell', ns)]
            if len(vals) >= 4 and vals[0] and vals[1]:
                try:
                    eid = int(vals[0])
                    yid = int(vals[1])
                    pos = vals[2].strip()
                    defi = vals[3].strip()
                    y_to_entry[yid] = (eid, pos, defi)
                except ValueError:
                    pass

    c = conn.cursor()
    c.execute("SELECT id, word_type, hanji, category, pos, definition FROM words")
    words_by_id = {
        r[0]: {
            'id': r[0], 'word_type': r[1] or '', 'hanji': r[2] or '',
            'category': r[3] or '', 'pos': r[4] or '', 'definition': r[5] or ''
        }
        for r in c.fetchall()
    }

    syn_updates = {}
    new_syn_pairs = set()

    def add_update(dst_id, text_def, src_cat, src_pos):
        if dst_id not in words_by_id:
            return
        if dst_id not in syn_updates:
            syn_updates[dst_id] = {'defs': [], 'cats': set(), 'pos': set()}
        if text_def and text_def not in syn_updates[dst_id]['defs']:
            syn_updates[dst_id]['defs'].append(text_def)
        if src_cat:
            for sc in src_cat.split(','):
                if sc.strip():
                    syn_updates[dst_id]['cats'].add(sc.strip())
        if src_pos:
            for sp in src_pos.split('/'):
                if sp.strip():
                    syn_updates[dst_id]['pos'].add(sp.strip())

    # 2. 解析 義項tuì詞目近義
    t_y_syn = t_map.get('義項tuì詞目近義')
    if t_y_syn is not None:
        for r in t_y_syn.findall('.//table:table-row', ns)[1:]:
            vals = [get_val(c) for c in r.findall('.//table:table-cell', ns)]
            if len(vals) >= 5 and vals[0] and vals[3]:
                try:
                    yid = int(vals[0])
                    src_hanji = vals[1].strip()
                    defi = vals[2].strip()
                    dst_id = int(vals[3])
                    src_info = y_to_entry.get(yid)
                    src_eid = src_info[0] if src_info else None
                    src_pos = src_info[1] if src_info else ''
                    src_word = words_by_id.get(src_eid, {}) if src_eid else {}
                    src_cat = src_word.get('category', '')

                    if src_eid and dst_id and src_eid != dst_id:
                        new_syn_pairs.add((src_eid, dst_id))
                        new_syn_pairs.add((dst_id, src_eid))

                    pos_prefix = f"({src_pos}) " if src_pos else ""
                    add_update(dst_id, f"{pos_prefix}{defi}（同「{src_hanji}」）", src_cat, src_pos)
                except ValueError:
                    pass

    # 3. 解析 詞目tuì詞目近義
    t_w_syn = t_map.get('詞目tuì詞目近義')
    if t_w_syn is not None:
        for r in t_w_syn.findall('.//table:table-row', ns)[1:]:
            vals = [get_val(c) for c in r.findall('.//table:table-cell', ns)]
            if len(vals) >= 4 and vals[0] and vals[2]:
                try:
                    src_eid = int(vals[0])
                    src_hanji = vals[1].strip()
                    dst_id = int(vals[2])
                    if src_eid != dst_id:
                        new_syn_pairs.add((src_eid, dst_id))
                        new_syn_pairs.add((dst_id, src_eid))
                    src_word = words_by_id.get(src_eid)
                    if src_word:
                        src_def = src_word.get('definition', '')
                        text_def = f"{src_def}（同「{src_hanji}」）" if src_def else f"同「{src_hanji}」"
                        add_update(dst_id, text_def, src_word.get('category', ''), src_word.get('pos', ''))
                except ValueError:
                    pass

    # 4. 解析 義項tuì義項近義 (擴充 synonyms 表)
    t_yy_syn = t_map.get('義項tuì義項近義')
    if t_yy_syn is not None:
        for r in t_yy_syn.findall('.//table:table-row', ns)[1:]:
            vals = [get_val(c) for c in r.findall('.//table:table-cell', ns)]
            if len(vals) >= 5 and vals[0] and vals[3]:
                try:
                    yid1 = int(vals[0])
                    yid2 = int(vals[3])
                    info1 = y_to_entry.get(yid1)
                    info2 = y_to_entry.get(yid2)
                    if info1 and info2 and info1[0] != info2[0]:
                        new_syn_pairs.add((info1[0], info2[0]))
                        new_syn_pairs.add((info2[0], info1[0]))
                except ValueError:
                    pass

    # 5. 解析 義項tuì詞目反義 (補全僅出現在反義詞之不單列詞目)
    t_y_ant = t_map.get('義項tuì詞目反義')
    if t_y_ant is not None:
        for r in t_y_ant.findall('.//table:table-row', ns)[1:]:
            vals = [get_val(c) for c in r.findall('.//table:table-cell', ns)]
            if len(vals) >= 5 and vals[0] and vals[3]:
                try:
                    yid = int(vals[0])
                    src_hanji = vals[1].strip()
                    defi = vals[2].strip()
                    dst_id = int(vals[3])
                    src_info = y_to_entry.get(yid)
                    src_eid = src_info[0] if src_info else None
                    src_pos = src_info[1] if src_info else ''
                    src_word = words_by_id.get(src_eid, {}) if src_eid else {}
                    src_cat = src_word.get('category', '')

                    pos_prefix = f"({src_pos}) " if src_pos else ""
                    add_update(dst_id, f"{pos_prefix}「{src_hanji}」之反義詞（原義：{defi}）", src_cat, src_pos)
                except ValueError:
                    pass

    # 寫入 words 表補全空缺之 definition, category, pos
    word_enrich_rows = []
    for wid, u in syn_updates.items():
        w = words_by_id[wid]
        new_def = w['definition']
        # 若原本無定義，或原本僅為系統自動標註之（同... / 臺華共同詞），則更新為完整釋義
        if not new_def or new_def.startswith('【臺華共同詞】') or '（同「' in new_def or '之反義詞' in new_def:
            if u['defs']:
                new_def = '；'.join(u['defs'][:3])
        new_cat = w['category']
        if not new_cat and u['cats']:
            new_cat = ','.join(sorted(u['cats']))
        new_pos = w['pos']
        if not new_pos and u['pos']:
            new_pos = '/'.join(sorted(u['pos']))
        if new_def != w['definition'] or new_cat != w['category'] or new_pos != w['pos']:
            word_enrich_rows.append((new_def, new_cat, new_pos, wid))

    print(f"Updating {len(word_enrich_rows)} words with enriched definitions/categories/pos...")
    c.executemany("UPDATE words SET definition = ?, category = ?, pos = ? WHERE id = ?", word_enrich_rows)

    # 重建更完整的 synonyms 表
    c.execute("SELECT word_id, synonym_id FROM synonyms")
    for r in c.fetchall():
        new_syn_pairs.add((r[0], r[1]))

    c.execute("DELETE FROM synonyms")
    c.executemany("INSERT INTO synonyms (word_id, synonym_id) VALUES (?, ?)", list(new_syn_pairs))
    conn.commit()
    print(f"ODS enrichment done in {time.time() - t0:.2f}s (total synonym links: {len(new_syn_pairs)}).")


def classify_word(hanji, tailo, raw_cat, pos, defi):
    raw_cat = raw_cat or ""
    defi = defi or ""
    hanji = hanji or ""
    pos = pos or ""
    
    cats = set()
    
    # 1. 昆蟲 (昆蟲、節肢動物如蜘蛛、蜈蚣、蠍子、蚯蚓等，嚴謹排除疾病、器具、玩具、哺乳動物)
    if not re.search(r'(病名|傳染病|耳鳴|竹蜻蜓|玩具|穿山甲|哺乳類|魚類|鳥類|禽鳥|香草|植物名|防蚊|驅蚊|蚊香|蒼蠅拍|蒼蠅紙|碟狀器具|桌罩|細齒梳|梳子|遊行隊伍)', defi):
        if "昆蟲類" in raw_cat:
            if hanji not in ("嗚", "拍摔", "無時閒"):
                cats.add("昆蟲")
        elif ("名詞" in pos or not pos) and re.search(r'(昆蟲名|昆蟲類|節肢動物|蜘蛛|蜈蚣|螳螂|蜻蜓|蝴蝶|螢火蟲|蟋蟀|螻蛄|螞蟻|白蟻|蜜蜂|虎頭蜂|黃蜂|蟑螂|蚊子|蒼蠅|果蠅|知了|蟬|毛毛蟲|毛蟲|菜蟲|蠶蛹|蠶繭|跳蚤|頭蝨|木蝨|壁蝨|椿象|金龜子|象鼻蟲|天牛|獨角仙|鍬形蟲|孑孓|水黽|龍蝨|衣魚|書蟲|蛀蟲|蚯蚓)', defi):
            if not re.search(r'(海中的節肢動物|甲殼類|蝦|蟹|蟳|鱟|比喻|形容)', defi):
                cats.add("昆蟲")

    # 2. 魚類 (魚類、海鮮、蝦蟹貝類、水產海洋生物，排除純動詞、魚塭、禽鳥)
    if ("名詞" in pos or not pos):
        if not re.search(r'(養殖魚池|池塘|禽鳥類|鳥類|器具|釣具|漁網|船隻|菜名|一道菜|湯品)', defi):
            if "魚蝦海獸" in raw_cat:
                if hanji not in ("八卦", "反肚"):
                    cats.add("魚類")
            elif re.search(r'(魚名|魚類|海水魚|淡水魚|水產|海產|蝦類|蟹類|貝類|軟體動物|頭足類|甲殼類|棘皮動物|腔腸動物|刺絲胞動物|鯨魚|海豚|海龜|鯊魚|水母|烏賊|章魚|花枝|小管|鎖管|魷魚|蚵仔|牡蠣|蛤蜊|文蛤|九孔|鮑魚|海膽|海參|石斑|虱目魚|土魠|白帶魚|鰻魚|鱸魚|鯽魚|鰱魚|鯉魚|鮪魚|鮭魚|鯧魚|竹筴魚|比目魚|彈塗魚|河豚|泥鰍|鱔魚|田螺)', defi):
                if not re.search(r'(器官|角質或骨質|鳥獸蟲魚|比喻|形容)', defi):
                    cats.add("魚類")

    # 3. 菜餚 (熟食料理、臺灣小吃、傳統小吃、佳餚羹湯、糕餅點心、飯麵菜餚)
    is_dish = False
    if not pos or "名詞" in pos:
        if not any(k in raw_cat for k in ['魚蝦海獸', '蔬果作物', '花草樹木', '禽類', '獸類', '昆蟲類', '飲食物具', '生活用品', '生理構造', '傷疾病痛']) or re.search(r'(菜餚|小吃|湯品|糕點|點心|做成的一道菜)', defi):
            if not re.search(r'^\s*\(名詞\)\s*(哺乳動物|禽鳥類|鳥類|昆蟲|節肢動物|瓜果類|根莖類|葉菜類|草本|木本|常綠|落葉|一年生|多年生|果樹|農作物|淡水魚|海水魚|貝類|魚類|魚名|植物名|蔬菜名|器官|廚具|餐具|容器|節日)', defi):
                if not re.search(r'(調味料|佐料|香料|菸草|香菸|酒類|茶葉|生米|澱粉|勾芡用|食用油|高梁酒|葡萄酒|啤酒|米酒|汽水|果汁|咖啡)', defi) or re.search(r'(菜餚|小吃|湯品|糕點|做成的一道)', defi):
                    if '食物、飲料、煙酒' in raw_cat:
                        if (re.search(r'(飯|糜|粥|麵|米粉|冬粉|粿|糕|餅|粽|圓|湯|羹|丸|包|餃|扁食|卷|捲|腸|脯|鬆|乾|酥|炸|煎|炒|滷|炕|封|燉|湯圓|麻糍|豆花|豆腐|豆乾|豆皮|油條|燒餅|刈包|割包|潤餅|春捲|碗粿|米粩|麻粩|寸棗|雙胞胎|甜甜圈|麵包|蛋糕|冰|枝仔冰|仙草|愛玉|布丁|壽司|便當|菜|點心|小吃|料理|菜餚|火腿|香腸|鹹肉|臘肉)', hanji)
                            or re.search(r'(菜餚|小吃|糕點|點心|湯品|米食|麵食|甜品|甜食|粥品|料理|做成的食品|製成的食品|蒸熟|煮熟|油炸|煎成|炒熟|烘烤|包餡|傳統食品)', defi)):
                            if not re.search(r'^(米|白米|糙米|粟|秫米|麵粉|太白粉|番薯粉|糖|白糖|烏糖|冰糖|赤砂|鹽|油|豬油|麻油|豆油|醬油|醋|味素|酒|燒酒|茶|茶米|薰|紙薰|水|滾水|冰塊|卵|雞卵|鴨卵|乳|牛乳|母乳|肉|白肉|赤肉|肥肉|三層肉|肉皮|肉骨|肉絲|豬菜|餅店)$', hanji):
                                is_dish = True
                    else:
                        if re.search(r'(菜餚|臺灣小吃|地方小吃|傳統小吃|傳統點心|糕餅點心|一道菜|名菜|湯品|羹湯|麵食|米食)', defi):
                            if not re.search(r'(器具|工具|桌罩|廚房|比喻)', defi):
                                is_dish = True
                        elif re.search(r'(滷肉飯|爌肉飯|炕肉飯|雞肉飯|米粉炒|炒米粉|蚵仔煎|蚵仔麵線|鼎邊蚖|鼎邊趖|肉圓|碗粿|草仔粿|紅龜粿|菜頭粿|油炸粿|筒仔米糕|潤餅|春捲|割包|刈包|四神湯|下水湯|豬血湯|肉羹|魷魚羹|土魠魚羹|扁食|水餃|肉包|菜包|肉粽|鹼粽|菜粽|薑母鴨|麻油雞|燒酒雞|羊肉爐|五柳居|菜脯卵|菜脯蛋|豆花|米篩目|米苔目)', hanji):
                            is_dish = True
    if is_dish:
        cats.add("菜餚")

    # 4. 天氣 (氣候、天候、氣溫、落雨、颳風、雷電、霜雪、雺霧、風颱、天陰、晴天、節氣)
    if "氣候溫度" in raw_cat or "節氣" in raw_cat:
        cats.add("天氣")
    elif "自然現象" in raw_cat and re.search(r'(風|雨|雷|電|雲|霜|雪|霧|露|雹|晴|陰|寒|熱|氣溫|天時|氣候|落雨|天光|日曝|乾旱|風颱)', defi + hanji):
        if not re.search(r'(沙石地|江河中)', defi):
            cats.add("天氣")
    elif re.search(r'(天氣|天候|氣候|氣溫|下雨|落雨|降雨|颳風|風吹|打雷|閃電|下雪|霜雪|大霧|濃霧|晨霧|晴天|陰天|好天|寒流|冷氣團|風颱|颱風|西北雨|乾旱|梅雨|天時|氣溫|天陰|雷陣雨)', defi):
        if not re.search(r'(衣服|遮蔽|阻擋|防風|心理|情緒|病名|器具|中暑)', defi):
            cats.add("天氣")
    elif re.search(r'^(風|雨|雷|電|霜|雪|霧|露|雺|霰|雹|晴|陰|落雨|出日頭|風颱|好天|歹天|天光|西北雨|寒天|熱天)', hanji) and re.search(r'(天氣|氣候|自然現象|降水|風力|溫度)', defi):
        cats.add("天氣")

    # 5. 動物 (哺乳、走獸、禽鳥、兩棲爬蟲，排除純昆蟲與純魚蝦)
    if any(k in raw_cat for k in ["禽類", "獸類", "爬蟲、兩棲類", "其他動物"]):
        if "昆蟲" not in cats and "魚類" not in cats:
            cats.add("動物")
    elif re.search(r'(哺乳動物|哺乳類|鳥類|鳥名|禽類|野獸|家畜|家禽|兩棲類|爬蟲類|爬蟲動物|獸名|蛇類|青蛙|蟾蜍|狗|貓|水牛|黃牛|乳牛|馬|羊|豬|鹿|猴|虎|獅|豹|象|狼|狐狸|兔|鼠|鴨|鵝|雞|鴿|雀|鵰|雁|鶴|老鷹|八哥|綠繡眼|白頭翁|穿山甲)', defi):
        if "昆蟲" not in cats and "魚類" not in cats:
            if not re.search(r'(菜餚|湯品|小吃|做成的食品|器具|工具|節日|星座)', defi):
                cats.add("動物")

    # 6. 植物 (花草樹木、蔬果、農作、林木、中藥植物)
    if any(k in raw_cat for k in ["花草樹木", "蔬果作物", "植物形體、狀態"]):
        cats.add("植物")
    elif re.search(r'(植物名|草本|木本|樹木|花卉|農作物|果樹|灌木|喬木|蔬菜名|蕨類|菌類|野草|花名|草名|樹名|種植物|落葉植物|多年生草本|一年生草本|常綠喬木|常綠灌木)', defi):
        cats.add("植物")

    # 7. 飲食 (食材原料、飲品、酒水、茶葉、米糧、調味料、滋味口感)
    if any(k in raw_cat for k in ["食物、飲料、煙酒", "飲食物具", "飲食行為"]):
        cats.add("飲食")
    elif re.search(r'(食品|食材|原料|米糧|穀物|調味|醬油|鹽|糖|醋|酒|茶|飲料|果汁|咖啡|吃喝|吞嚥|味道|酸甜苦辣|滋味|烹調法)', defi):
        cats.add("飲食")

    # 8. 心情 (情緒、心境、情感、喜怒哀樂憂思驚恐、意志膽量、相思恩愛)
    if any(k in raw_cat for k in ["心理活動", "心理狀態", "個性風格", "氣質態度", "反應、表情"]):
        cats.add("心情")
    elif re.search(r'(心情|心境|情緒|喜愛|歡喜|高興|憤怒|發脾氣|傷心|悲傷|思念|想念|擔憂|煩惱|害怕|驚嚇|驚恐|恐懼|勇敢|大膽|膽量|膽識|膽子|膽小|害羞|羞恥|慚愧|後悔|心酸|相思|留戀|著急|心急|得意|失望|絕望|放心|安心|激動|佩服|心痛|痛心|快活|痛苦|怨恨|吃醋|嫉妒|羨慕|牽掛|情深|恩愛|志氣)', defi):
        cats.add("心情")

    # 9. 身體 (器官、五官、肢體、骨骼、生理、健康、傷病)
    if any(k in raw_cat for k in ["生理構造", "傷疾病痛", "醫療保健"]):
        cats.add("身體")
    elif re.search(r'(人體|身體|器官|骨骼|肌肉|五官|頭部|面部|手部|腳部|胸部|腹部|內臟|心臟|肺|肝|胃|腸|血液|皮膚|毛髮|指甲|生病|疾病|傷口|疼痛|症狀|醫藥|診斷|針灸)', defi):
        cats.add("身體")

    # 10. 服飾 (衣冠鞋襪、布帛、首飾、梳妝打扮)
    if any(k in raw_cat for k in ["衣帽鞋襪", "珠寶飾品", "縫紉洗熨", "理容、化妝"]):
        cats.add("服飾")
    elif re.search(r'(衣服|服飾|衣著|上衣|褲子|裙子|鞋子|襪子|帽子|頭巾|圍巾|手套|鈕扣|布料|絲綢|刺繡|項鍊|耳環|戒指|手鐲|髮簪|梳妝|打扮|化妝|穿著|裁縫)', defi):
        cats.add("服飾")

    # 11. 建築 (房屋、屋舍、門窗、庭院、磚瓦、宮廟、亭臺)
    if any(k in raw_cat for k in ["建築物、結構", "居住環境", "房屋租賃、搬遷", "道路、橋梁"]):
        cats.add("建築")
    elif re.search(r'(房屋|建築|住宅|屋宇|樓房|廳堂|房間|門窗|門楣|屋頂|瓦片|階梯|樑柱|柱子|牆壁|庭院|圍牆|欄杆|走廊|古厝|宮廟|寺廟|祠堂|亭仔腳)', defi):
        cats.add("建築")

    # 12. 地理 (山川、河海、港灣、田莊、地形、島嶼)
    if any(k in raw_cat for k in ["地理", "山脈", "河川", "海港", "舊地名"]):
        cats.add("地理")
    elif re.search(r'(山嶺|山峰|山脈|山坡|河流|河川|海港|港口|海洋|海岸|海邊|湖泊|池塘|島嶼|平原|山谷|溪流|水圳|海灘|田野|田莊|鄉村|城鎮|地勢|地形)', defi):
        cats.add("地理")

    # 13. 天文 (日月星辰、宇宙天象、天頂，排除單純時間方位或疾病眼鏡)
    if "天文" in raw_cat:
        cats.add("天文")
    elif re.search(r'(太陽系|日頭|月亮|月娘|月球|星星|星宿|星群|銀河|天頂|天象|星座|彗星|日蝕|月蝕|晨曦|朝霞|夕陽|流星|北極星|北斗星)', defi):
        if not re.search(r'(眼鏡|墨鏡|中暑|病症|方位名)', defi):
            cats.add("天文")

    # 14. 人生 (家庭、宗族、父母兄弟、夫妻婚姻、生老病死、歲月光陰)
    if any(k in raw_cat for k in ["宗族、家庭", "稱謂輩分", "性別、婚姻", "生養老死", "地位、身世、背景"]):
        cats.add("人生")
    elif re.search(r'(祖先|祖父|祖母|父母|父親|母親|兄弟|姊妹|夫妻|丈夫|妻子|兒女|兒子|女兒|孫子|孫女|親戚|宗族|結婚|婚姻|嫁娶|懷孕|生產|生兒育女|壽命|養育|年老|去世|死亡|身世|光陰|一生|歲月)', defi):
        cats.add("人生")

    # 15. 民俗 (信仰、節慶、神明、祭拜、普渡、籤詩符咒、民間習俗)
    if any(k in raw_cat for k in ["神明、鬼怪、教派", "神職、神巫、信徒", "廟宇", "婚喪喜慶"]):
        cats.add("民俗")
    elif re.search(r'(神明|神祇|媽祖|土地公|王爺|關公|佛祖|觀音|鬼神|魂魄|神仙|拜拜|祭祀|祭拜|進香|香火|普渡|普度|中元|中秋|端午|過年|春節|作醮|抽籤|算命|卜卦|收驚|符咒|安太歲|民俗|信仰|道教|佛教|禁忌)', defi):
        cats.add("民俗")

    # 16. 文藝 (唸歌相褒、歌仔戲、布袋戲、南管北管、音樂樂器、詩詞戲曲、遊藝)
    if any(k in raw_cat for k in ["文學、藝術", "戲劇、音樂", "休閒、娛樂", "體育、運動"]):
        cats.add("文藝")
    elif re.search(r'(歌仔戲|唸歌|相褒|南管|北管|布袋戲|皮影戲|曲調|七字調|都馬調|音樂|樂器|二胡|月琴|琵琶|笛子|鑼鼓|戲曲|唱腔|歌曲|詩詞|文章|書法|繪畫|繪圖|下棋|遊藝|陣頭)', defi):
        cats.add("文藝")

    # 17. 器物 (日常器具、農具生產工具、家具器皿、車舟交通工具)
    if any(k in raw_cat for k in ["生活用品", "生產工具", "相關器具、活動", "交通、運輸"]):
        cats.add("器物")
    elif re.search(r'(器具|工具|農具|家具|器皿|容器|桌椅|刀剪|鍋碗|箱籠|車輛|船隻|繩索|籃子|扁擔|燈具|鐘錶|鏡子|鎖頭)', defi):
        cats.add("器物")

    # 18. 社會 (行業職業、政治官職、商業買賣、法律軍事、學校教育)
    if any(k in raw_cat for k in ["國家、社會、民眾", "政治", "法律", "軍事", "商業", "錢財資產", "教育、學術", "軍公教業", "服務業及其他", "組織團體"]):
        cats.add("社會")
    elif re.search(r'(職業|行業|工匠|商人|官員|軍人|教師|學生|警察|醫生|買賣|交易|金錢|價格|薪水|法院|法律|監獄|政府|國家|百姓|軍隊|戰鬥|學校|功課|考試)', defi):
        cats.add("社會")

    # 19. 動作 (動態行為、肢體活動、感官操作)
    if any(k in raw_cat for k in ["一般動詞-活動動詞", "一般動詞-行為動詞", "肢體動作", "感官動作", "生活勞動"]) or "動詞" in pos:
        cats.add("動作")
    elif re.search(r'(動作|移動|行走|奔跑|跳躍|攀爬|提拿|抓取|搬運|打擊|推拉|觸摸|觀看|聆聽|品嚐|嗅聞|說話|喊叫|操作|製作|修理|打掃|工作)', defi):
        cats.add("動作")

    # 20. 狀態 (性質、外貌、形容、色彩、大小、速度、特質)
    if any(k in raw_cat for k in ["性質、程度", "形貌、體積", "體態樣貌", "顏色、氣味", "境況、狀態-擬人", "境況、狀態-擬物", "一般動詞-靜態動詞"]) or "形容詞" in pos:
        cats.add("狀態")
    elif re.search(r'(外貌|形態|大小|形狀|長短|高矮|肥瘦|粗細|顏色|氣味|滋味|溫度|速度|明暗|硬軟|深淺|乾濕|整齊|混亂|貧富|好壞|美醜)', defi):
        cats.add("狀態")

    # 21. 言語 (講話、口語、相褒、俗諺、應對、語氣詞)
    if any(k in raw_cat for k in ["語言、文字、符號", "交際應酬", "詈語", "待人處事"]) or "副詞" in pos or "助詞" in pos or "嘆詞" in pos:
        cats.add("言語")
    elif re.search(r'(說話|交談|言語|對話|聊天|商量|回答|質問|吩咐|交代|叮嚀|責罵|稱讚|嘲笑|俗語|諺語|歇後語|成語|口頭禪|招呼|客套|招呼用語)', defi):
        cats.add("言語")

    # 22. 時空 (時間節氣、早晚、季節、年歲、方位、方向)
    if any(k in raw_cat for k in ["時間節令", "空間方位"]):
        cats.add("時空")
    elif re.search(r'(時間|年代|年份|月份|日期|時刻|早晨|早起|中午|下晡|傍晚|夜晚|暗暝|半夜|過去|現在|未來|從前|方才|剛才|春季|夏季|秋季|冬季|春天|夏天|秋天|冬天|東方|西方|南方|北方|上面|下面|前面|後面|左邊|右邊|內部|外部)', defi):
        cats.add("時空")

    # 23. 針對無定義之詞目（如臺華共同詞或近反義詞）以漢字詞素精準歸類
    if not cats and len(hanji) >= 2:
        if re.search(r'(蜻蜓|蝴蝶|蜜蜂|虎頭蜂|黃蜂|螞蟻|白蟻|蟑螂|虼蚻|蟋蟀|螳螂|螢火蟲|火金蛄|草蜢|蚊仔|蠓仔|胡蠅|蒼蠅|果蠅|毛毛蟲|刺毛蟲|菜蟲|蛀蟲|米蟲|金龜|水龜|筍龜|杜伯|杜猴|杜蚓|蚯蚓|蜈蚣|蜘蛛|蟧蜈|田嬰|尾蝶|木蝨|狗蝨|跳蚤|虼蚤)', hanji):
            cats.add("昆蟲")
        elif re.search(r'(魚|蝦|蟳|蟹|鰻|鯖|鮭|鮫|鰱|鯽|鯧|魠|魩|蚵|蜆|蛤|蚌|螺|魷|鱟|鱘|花枝|小管|鎖管|烏賊|章魚|海參|海膽|水母|九孔|海豚)', hanji) and not re.search(r'(魚丸|魚脯|魚乾|魚翅|釣|塭)', hanji):
            cats.add("魚類")
        elif re.search(r'(飯|糜|粥|麵|米粉|冬粉|粿|糕|餅|粽|湯|羹|丸仔|肉丸|魚丸|貢丸|包仔|肉包|菜包|割包|刈包|水餃|煎餃|扁食|餛飩|春捲|潤餅|雞卷|蝦捲|香腸|米腸|粉腸|肉燥|肉圓|碗粿|米苔目|米篩目|鼎邊趖|蚵仔煎|豆花|豆腐|豆乾|油條|燒餅|麻糍|麻粩|米粩|枝仔冰|剉冰|四神湯|下水湯|排骨酥|肉乾|肉脯|肉酥|肉鬆|火腿|便當|壽司|點心|包餡)', hanji):
            cats.add("菜餚")
        elif re.search(r'(天氣|天時|好天|歹天|陰天|烏陰|落雨|西北雨|陣雨|風雨|三八雨|風颱|颱風|透風|大風|春風|東風|北風|海風|冷風|寒流|大寒|大熱|寒天|熱天|大旱|霜雪|落雪|雺霧|大霧|拍雷|雷公|爍爁|閃電|出日頭|日曝|回南)', hanji):
            cats.add("天氣")
        elif re.search(r'(日頭|月娘|月球|月眉|星|銀河|天文|太空|日蝕|月蝕|流星)', hanji):
            cats.add("天文")
        elif re.search(r'(花|草|樹|木|竹|葉|藤|林|果|豆|瓜|菜|筍|菇|蘭|菊|梅|蓮|荷|桃|李|柑|柚|檨|蕉|梨|棗|蔗|稻|粟|麥|麻|蒜|蔥|薑|椒|芋|番薯|土豆|九芎)', hanji):
            cats.add("植物")
        elif re.search(r'(牛|馬|羊|豬|狗|貓|雞|鴨|鵝|鳥|雀|鴿|鷹|鶴|燕|鴉|虎|獅|豹|象|狼|狐|猴|鹿|兔|鼠|蛇|蛙|水雞|田雞|蟾蜍|肚胿|蝌蚪|龜|鱉)', hanji):
            cats.add("動物")
        elif re.search(r'(心|情|愛|恨|怒|喜|樂|悲|哀|愁|思|念|驚|恐|怕|膽|羞|見笑|鬱|悶|煩|惱|怨|妒|欣羨|孤單|寂寞|快活|艱苦|痛苦|心酸|心痛|毋甘|爽快|歡喜|得意|失望|絕望|後悔|安心|放心)', hanji):
            cats.add("心情")
        elif re.search(r'(衫|褲|裙|鞋|襪|帽|巾|襖|袍|領|袖|布|絲|綢|緞|梳|妝)', hanji):
            cats.add("服飾")
        elif re.search(r'(厝|屋|房|廳|門|窗|壁|牆|柱|樑|瓦|磚|樓|亭|廟|宮|寺|堂|院|埕|橋)', hanji):
            cats.add("建築")
        elif re.search(r'(山|海|河|溪|江|湖|池|潭|港|灣|島|嶼|田|園|埔|崙|嶺|谷|洞|坡|岸)', hanji):
            cats.add("地理")
        elif re.search(r'(頭|目|耳|鼻|喙|口|舌|齒|面|臉|頷|頸|肩|手|掌|指|胸|腹|肚|腰|尻川|跤|腿|骨|血|皮|毛|肝|肺|胃|腸|腎|病|痛|傷|醫|藥)', hanji):
            cats.add("身體")
        elif re.search(r'(父|母|爸|媽|公|嬤|祖|兄|弟|姊|妹|夫|妻|某|翁|囝|兒|女|孫|親|戚|家|族|婚|嫁|娶|生|老|死|壽|命)', hanji):
            cats.add("人生")
        elif re.search(r'(神|佛|菩薩|媽祖|王爺|土地公|天公|鬼|仙|拜|祭|香|醮|普渡|籤|卦|符|咒|過年|端午|中秋|清明|重陽)', hanji):
            cats.add("民俗")
        elif re.search(r'(歌|曲|調|戲|詩|詞|文|書|畫|琴|鼓|鑼|吹|笛|弦|棋|牌|骰)', hanji):
            cats.add("文藝")
        elif re.search(r'(刀|劍|斧|鋸|錘|釘|針|線|車|船|轎|桌|椅|床|櫥|箱|籠|籃|桶|盆|碗|盤|杯|壺|鼎|鍋|灶|燈|扇|傘|鎖|鐘|錶)', hanji):
            cats.add("器物")
        elif re.search(r'(春|夏|秋|冬|年|月|日|工|暝|暗|早|晡|時|陣|今|昨|明|古|昔|東|西|南|北)', hanji):
            cats.add("時空")

    if not cats:
        cats.add("其他")
        
    return list(cats)


def main():
    db_path = "taigi_dict.db"
    print(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Step 1: 先從 kautian.ods 補全近反義詞釋義、分類與 synonyms 表
    enrich_from_ods(conn)
    
    # 確保 words 表有 category_main 欄位
    c.execute("PRAGMA table_info(words)")
    columns = [col[1] for col in c.fetchall()]
    if "category_main" not in columns:
        print("Adding category_main column to words table...")
        c.execute("ALTER TABLE words ADD COLUMN category_main TEXT DEFAULT ''")
        
    # 重建 word_categories 表
    print("Recreating word_categories table...")
    c.execute("DROP TABLE IF EXISTS word_categories")
    c.execute("""
        CREATE TABLE word_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word_id INTEGER NOT NULL,
            category_main TEXT NOT NULL,
            category_raw TEXT DEFAULT ''
        )
    """)
    
    # 讀取全部詞條
    print("Fetching all words...")
    c.execute("SELECT id, word_type, hanji, tailo, category, pos, definition FROM words")
    words = c.fetchall()
    print(f"Loaded {len(words)} words.")
    
    batch_cat_inserts = []
    batch_word_updates = []
    batch_def_fallbacks = []
    
    cat_counts = defaultdict(int)
    
    t0 = time.time()
    for row in words:
        w_id, word_type, hanji, tailo, raw_cat, pos, defi = row
        assigned_cats = classify_word(hanji, tailo, raw_cat, pos, defi)
        
        # 決定 words.category_main 單一主分類（依照優先順序）
        primary_cat = "其他"
        for p in CATEGORY_PRIMARY_PRIORITY:
            if p in assigned_cats:
                primary_cat = p
                break
                
        batch_word_updates.append((primary_cat, w_id))

        # 若臺華共同詞或近反義詞仍無釋義，補上簡明標註讓前端與推薦引擎皆可使用
        if not defi and word_type in ("臺華共同詞", "近反義詞不單列詞目者"):
            cat_label = "、".join([ac for ac in assigned_cats if ac != "其他"]) or primary_cat
            fallback_def = f"【{word_type}】{hanji}（領域：{cat_label}）"
            batch_def_fallbacks.append((fallback_def, w_id))
        
        for cat in assigned_cats:
            cat_counts[cat] += 1
            batch_cat_inserts.append((w_id, cat, raw_cat or ''))
            
    print(f"Classification completed in {time.time() - t0:.2f}s.")
    print("Inserting into word_categories...")
    c.executemany("INSERT INTO word_categories (word_id, category_main, category_raw) VALUES (?, ?, ?)", batch_cat_inserts)
    
    print("Updating words.category_main...")
    c.executemany("UPDATE words SET category_main = ? WHERE id = ?", batch_word_updates)

    if batch_def_fallbacks:
        print(f"Updating {len(batch_def_fallbacks)} fallback definitions for 臺華共同詞/近反義詞...")
        c.executemany("UPDATE words SET definition = ? WHERE id = ?", batch_def_fallbacks)
    
    # 建立索引以確保雙向查詢效能
    print("Creating indexes...")
    c.execute("CREATE INDEX IF NOT EXISTS idx_wc_main ON word_categories(category_main)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_wc_word ON word_categories(word_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_words_cat_main ON words(category_main)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_words_last_rhyme ON words(last_rhyme)")
    
    conn.commit()
    conn.close()
    
    print("\n=== All Categories Rebuilt Successfully ===")
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {cnt} 條")
    print("Done!")

if __name__ == "__main__":
    main()
