"""
建置教育部臺灣閩南語常用詞辭典之押韻索引 SQLite 資料庫
從 ../台語/kautian.ods 讀取詞目、義項、近義詞並計算 13 大韻部
"""

import os
import re
import sys
import time
import zipfile
import sqlite3
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from rhyme_helper import TaiwaneseRhymeMatcher

sys.stdout.reconfigure(encoding='utf-8')

matcher = TaiwaneseRhymeMatcher()

# 補充擴充通押規則 (若 un, ut, ng, m 在預設 13 部未明定，給予合理歸納)
EXTRA_RHYME_MAP = {
    'un': ('NASAL_EN', 'UN通押入IN/ENG類陽聲'),
    'ut': ('STOP_ET', 'UT通押入IT/EK類塞音'),
    'ng': ('NASAL_ON', '聲化韻NG通押入ONG類陽聲'),
    'm': ('NASAL_ON', '聲化韻M通押入OM類陽聲')
}

def extract_last_syllable_info(tailo_str: str):
    """
    從台羅拼音字串萃取末字音節與韻部資訊
    """
    if not tailo_str:
        return '', '', '', '', None
    
    # 取第一種發音（排除 / 之後的又讀）
    main_pron = tailo_str.split('/')[0].strip()
    
    # 拆分為音節
    sylls = [s for s in re.split(r'[\s\-]+', main_pron) if s and s != '--']
    if not sylls:
        return '', '', '', '', None
        
    last_syll = sylls[-1]
    init, rhyme, tone = matcher.split_syllable(last_syll)
    
    # 查詢 13 大韻部
    res = matcher.get_rhyme_group(last_syll)
    group_id = ''
    if res:
        group_id = res['group_id']
    elif rhyme in EXTRA_RHYME_MAP:
        group_id = EXTRA_RHYME_MAP[rhyme][0]
        
    return last_syll, init, rhyme, group_id, tone


def build_database(ods_path: str, db_path: str):
    t0 = time.time()
    print(f"開始從 {ods_path} 讀取辭典資料...")
    
    ns = {
        'table': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
        'text': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0',
        'office': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0'
    }

    def get_cell_value(cell):
        txt = ''.join(p.text or '' for p in cell.findall('.//text:p', ns)).strip()
        if not txt:
            val = cell.attrib.get('{urn:oasis:names:tc:opendocument:xmlns:office:1.0}value')
            if val is not None:
                return str(int(float(val))) if val.replace('.', '', 1).isdigit() else str(val)
        return txt

    with zipfile.ZipFile(ods_path, 'r') as z:
        with z.open('content.xml') as f:
            tree = ET.parse(f)
            root = tree.getroot()
            
    print(f"XML 解析完成，耗時 {time.time() - t0:.2f} 秒")
    
    tables = root.findall('.//table:table', ns)
    t_map = {t.attrib.get('{urn:oasis:names:tc:opendocument:xmlns:table:1.0}name'): t for t in tables}
    
    # 1. 讀取 義項 (釋義與詞性)
    print("解析義項資料...")
    definitions = {} # entry_id -> list of {"pos": ..., "def": ...}
    y_table = t_map.get('義項')
    if y_table is not None:
        for r in y_table.findall('.//table:table-row', ns)[1:]:
            cells = r.findall('.//table:table-cell', ns)
            vals = [get_cell_value(c) for c in cells]
            if len(vals) >= 4 and vals[0]:
                try:
                    eid = int(vals[0])
                    pos = vals[2].strip() if len(vals) > 2 else ''
                    definition = vals[3].strip() if len(vals) > 3 else ''
                    if eid not in definitions:
                        definitions[eid] = []
                    definitions[eid].append({'pos': pos, 'def': definition})
                except ValueError:
                    pass

    # 2. 讀取 近義詞 (詞目tuì詞目近義)
    print("解析近義詞關聯...")
    synonyms_map = {} # entry_id -> list of target_id
    syn_table = t_map.get('詞目tuì詞目近義')
    if syn_table is not None:
        for r in syn_table.findall('.//table:table-row', ns)[1:]:
            cells = r.findall('.//table:table-cell', ns)
            vals = [get_cell_value(c) for c in cells]
            if len(vals) >= 3 and vals[0] and vals[2]:
                try:
                    src_id = int(vals[0])
                    dst_id = int(vals[2])
                    if src_id not in synonyms_map:
                        synonyms_map[src_id] = []
                    synonyms_map[src_id].append(dst_id)
                except ValueError:
                    pass

    # 3. 讀取 詞目 並建立資料庫
    if os.path.exists(db_path):
        os.remove(db_path)
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE words (
        id INTEGER PRIMARY KEY,
        word_type TEXT,
        hanji TEXT,
        tailo TEXT,
        category TEXT,
        pos TEXT,
        definition TEXT,
        char_count INTEGER,
        last_char TEXT,
        last_syllable TEXT,
        last_rhyme TEXT,
        rhyme_group TEXT,
        tone INTEGER,
        is_rhyme_matched INTEGER
    )
    """)
    
    cursor.execute("""
    CREATE TABLE synonyms (
        word_id INTEGER,
        synonym_id INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE char_readings (
        hanji TEXT,
        tailo TEXT,
        last_syllable TEXT,
        last_rhyme TEXT,
        rhyme_group TEXT,
        tone INTEGER
    )
    """)
    
    # 建立索引加快查詢
    cursor.execute("CREATE INDEX idx_rhyme_group ON words(rhyme_group)")
    cursor.execute("CREATE INDEX idx_char_count ON words(char_count)")
    cursor.execute("CREATE INDEX idx_tone ON words(tone)")
    cursor.execute("CREATE INDEX idx_hanji ON words(hanji)")
    cursor.execute("CREATE INDEX idx_last_char ON words(last_char)")
    cursor.execute("CREATE INDEX idx_syn_src ON synonyms(word_id)")
    cursor.execute("CREATE INDEX idx_char_h ON char_readings(hanji)")
    cursor.execute("CREATE INDEX idx_char_grp ON char_readings(rhyme_group)")


    words_table = t_map.get('詞目')
    rows = words_table.findall('.//table:table-row', ns)
    
    batch = []
    total_parsed = 0
    
    for idx, r in enumerate(rows[1:]):
        cells = r.findall('.//table:table-cell', ns)
        vals = [get_cell_value(c) for c in cells]
            
        if len(vals) >= 4 and vals[0] and vals[2] and vals[3]:
            try:
                entry_id = int(vals[0])
                w_type = vals[1].strip()
                hanji = vals[2].strip()
                tailo = vals[3].strip()
                category = vals[4].strip() if len(vals) > 4 else ''
                
                # 清除漢字中標註的 【替】等附註
                clean_hanji = re.sub(r'【.*?】', '', hanji).strip()
                char_count = len(clean_hanji)
                last_char = clean_hanji[-1] if clean_hanji else ''
                
                # 萃取韻部資訊
                last_s, init, rhyme, grp, tone = extract_last_syllable_info(tailo)
                is_matched = 1 if grp else 0
                
                # 義項與詞性合併
                y_list = definitions.get(entry_id, [])
                pos_list = list(dict.fromkeys(y['pos'] for y in y_list if y['pos']))
                def_list = [f"({y['pos']}) {y['def']}" if y['pos'] else y['def'] for y in y_list if y['def']]
                
                pos_str = "/".join(pos_list)
                def_str = "；".join(def_list)
                
                batch.append((
                    entry_id, w_type, clean_hanji, tailo, category,
                    pos_str, def_str, char_count, last_char,
                    last_s, rhyme, grp, tone if tone else 0, is_matched
                ))
                total_parsed += 1
                
                if len(batch) >= 2000:
                    cursor.executemany("""
                    INSERT INTO words VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, batch)
                    batch = []
            except Exception as e:
                continue

    if batch:
        cursor.executemany("""
        INSERT INTO words VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, batch)
        
    # 寫入近義詞表
    syn_batch = []
    for sid, dids in synonyms_map.items():
        for did in dids:
            syn_batch.append((sid, did))
    if syn_batch:
        cursor.executemany("INSERT INTO synonyms VALUES (?,?)", syn_batch)

    # 4. 讀取 漢字羅馬字對應 並寫入 char_readings
    print("解析漢字羅馬字對應表...")
    char_table = t_map.get('漢字羅馬字對應')
    char_batch = []
    seen_char_readings = set()
    if char_table is not None:
        for r in char_table.findall('.//table:table-row', ns)[1:]:
            cells = r.findall('.//table:table-cell', ns)
            vals = [get_cell_value(c) for c in cells]
            if len(vals) >= 2 and vals[0] and vals[1]:
                h = vals[0].strip().lstrip('-')
                t = vals[1].strip().lstrip('-')
                if h and t and (h, t) not in seen_char_readings:
                    seen_char_readings.add((h, t))
                    last_s, init, rhyme, grp, tone = extract_last_syllable_info(t)
                    char_batch.append((h, t, last_s, rhyme, grp, tone if tone else 0))
                    if len(char_batch) >= 2000:
                        cursor.executemany("INSERT INTO char_readings VALUES (?,?,?,?,?,?)", char_batch)
                        char_batch = []
        if char_batch:
            cursor.executemany("INSERT INTO char_readings VALUES (?,?,?,?,?,?)", char_batch)
        print(f"寫入字音對應 {len(seen_char_readings)} 筆！")

    conn.commit()
    conn.close()

    
    print(f"成功建置資料庫！共收錄 {total_parsed} 筆詞目，輸出檔案大小: {os.path.getsize(db_path)/(1024*1024):.2f} MB")
    print(f"近義詞關係數: {len(syn_batch)} 條")
    print(f"總耗時: {time.time() - t0:.2f} 秒")

if __name__ == '__main__':
    ods_file = '../台語/kautian.ods'
    db_file = 'taigi_dict.db'
    build_database(ods_file, db_file)
