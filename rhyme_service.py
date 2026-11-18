"""
台語押韻核心服務 (Rhyme Service)
提供歌詞押韻分析、辭典反查、詞尾智慧替換、前後句換句建議、Gemini AI 連網擴寫
"""

import os
import re
import sys
import json
import sqlite3
import unicodedata
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union
import asyncio
import httpx
from dotenv import load_dotenv
from rhyme_helper import TaiwaneseRhymeMatcher

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')


# 常見歌詞段落標題過濾正則
SECTION_HEADER_RE = re.compile(r'^\s*((\[|【|\(|（).*?(\]|】|\)|）)|#+.*|第\s*[0-9一二三四五六七八九十]+\s*[段節首葩].*|(前奏|主歌|副歌|尾奏|橋段|間奏|A段|B段|C段|Chorus|Verse|Bridge|Intro|Outro|[0-9]+)\s*(\]|】|\)|）|:)?)\s*$', re.IGNORECASE)

# 主題分類對應圖示
CATEGORY_ICONS = {
    "天氣": "⛅",
    "植物": "🌸",
    "動物": "🐾",
    "菜餚": "🍲",
    "魚類": "🐟",
    "昆蟲": "🦋",
    "心情": "💖",
    "飲食": "🍵",
    "地理": "🏔️",
    "天文": "✨",
    "人生": "⏳",
    "身體": "💪",
    "器物": "🏡",
    "服飾": "👘",
    "建築": "🏛️",
    "社會": "👥",
    "民俗": "🏮",
    "文藝": "📜",
    "動作": "🏃",
    "狀態": "🎨",
    "言語": "💬",
    "時空": "🌌",
    "其他": "📦"
}

# 主題分類預設排列順序（天氣、植物、動物、菜餚、魚類、昆蟲、心情 置頂優先）
CATEGORY_ORDER = [
    "天氣", "植物", "動物", "菜餚", "魚類", "昆蟲", "心情",
    "飲食", "地理", "天文", "人生", "身體", "器物", "服飾",
    "建築", "社會", "民俗", "文藝", "動作", "狀態", "言語",
    "時空", "其他"
]

# 寫歌常用詩意詞彙情境庫 (用於本地智慧推薦評分與題材歸類)
THEMATIC_KEYWORDS = {
    "思念情感": ["愛", "情", "心", "夢", "想", "戀", "念", "恨", "痛", "悲", "望", "淚", "相思", "等待", "難忘", "情深", "溫柔", "牽掛"],
    "人生歲月": ["年", "月", "日", "世間", "運命", "青春", "無奈", "歲月", "一生", "過去", "未來", "流浪", "繁華", "回頭", "前途", "夢醒"],
    "自然景色": ["風", "雨", "海", "天", "雲", "星", "月娘", "花", "山", "水", "路", "夜", "日頭", "春風", "暗暝", "黃昏", "波浪"],
    "江湖志向": ["兄弟", "行", "拚", "膽", "義理", "乾杯", "酒", "路途", "志氣", "擔當", "成功", "英雄", "漂泊", "孤單", "不驚"]
}

# 經典歌仔冊精選種子文本（提供寫作時之對偶押韻與句型參考）
DEFAULT_KUA_A_TSHEH_SEEDS = [
    {
        "title": "雪梅思君七字調",
        "theme": "思念情感",
        "author": "民間傳統歌仔冊",
        "description": "流傳最廣的七字仔四句聯敘事悲歌，敘述商雪梅思念良人，全篇格律嚴謹，為七字仔之代表作。",
        "raw_content": """正月算來迎春風
二人相愛在花房
天生姻緣成雙對
美滿恩愛久長長

二月算來春草青
想起往事痛心肝
為君一人流珠淚
滿腹悲傷無人聽

三月算來是清明
手提紙錢去祭靈
啼啼哭哭墳前拜
哭一聲來嘆一聲

四月算來日頭長
繡房孤單守空房
千思萬想心煩惱
何時重見我情郎"""
    },
    {
        "title": "勸世歌・人生浮浪",
        "theme": "勸世醒世",
        "author": "傳統唸歌相褒",
        "description": "台灣民間著名勸世唸歌，詞句生動，教人修身積德、珍惜光陰，合律順唱。",
        "raw_content": """我來唸歌囉各位聽
無欲借錢免著驚
勸人做好莫做歹
好歹到頭天知影

人生在世幾十年
何必逐日貪金錢
富貴榮華如浮雲
臨老換來一縷煙

天地生人皆有命
修心向善保平安
若有真心待朋友
到處春風好為伴

作人處世著端正
行路莫行歪斜嶺
世間是非分明在
留得芳名傳萬名"""
    },
    {
        "title": "周成過台灣・渡海別妻",
        "theme": "離別悲歡",
        "author": "清末民初歌仔冊",
        "description": "台灣四大奇案之首，刻劃渡海移民離鄉背井、渡過黑水溝之艱難情境。",
        "raw_content": """離鄉背井過台灣
茫茫黑水難過關
夫妻恩愛今分離
何時回鄉見容顏

海湧滔滔接青天
心酸淚滴濕衣邊
若非生活這般苦
誰人願意走天邊

一葉扁舟渡汪洋
回頭遙望舊家鄉
叮嚀賢妻好照顧
莫為夫婿心頭傷

過海台灣求前途
不怕風霜受辛勞
若得功成名就日
同享榮華同樂陶"""
    },
    {
        "title": "傳統男女相褒四句聯",
        "theme": "男女相褒",
        "author": "台灣鄉土民間相褒",
        "description": "台灣早期採茶、做田時男女對唱之相褒歌，情意詼諧、比喻生動，為即興鬥句之精粹。",
        "raw_content": """手提甘蔗入花園
看見甘蔗青又純
阿妹生做水如花
何時與哥訂乾坤

行過小橋又過嶺
看見阿妹手提傘
有心作伴行一路
日頭落山不知冷

採茶來到茶山邊
滿山茶香透天池
茶葉青翠人清秀
心心相印正當時

天頂天星萬萬粒
不如月娘一輪圓
世間美人雖然多
只愛阿妹萬萬年"""
    },
    {
        "title": "台南運河殉情記七字調",
        "theme": "人生歲月",
        "author": "台灣近代歌仔冊",
        "description": "描寫日治時期台南運河淒美哀怨的愛情故事，唱詞典雅，聲情動人。",
        "raw_content": """運河水深流無歇
哀怨歌聲伴秋月
兩人立誓心同在
不通隨風吹落葉

深情相許難分離
滿腹冤屈無人知
願隨流水歸大海
生生死死伴相隨

夜半冷風吹孤影
安平港口月明定
若非世途多坎坷
怎會投身運河行"""
    },
    {
        "title": "最新十二碗菜歌",
        "theme": "飲食風俗",
        "author": "傳統歌仔冊唱本（許嘉勇考訂校釋）",
        "description": "20世紀初葉流傳於廈門與台灣之經典歌仔冊，全書56葩、1,568字，描述煙花女於酒樓張羅十二道宴席工夫菜（正燕、咖哩雞、冬菜鴨、炒蝦仁、蘑菇肚、炒肚尖、燒豬紅燒魚、拼盤、鮑魚肚、封雞水餃、洋旺梨、千層糕）款待賓客，席間男女對唱借景抒情，飲食起興。",
        "raw_content": """一塊圓桌排出去
各位酒杯佮牙箸
全桌拼盤佮燒豬
欲請人客佮紳士

圓桌閣罩白桌巾
去罩桌巾較斯文
雞鴨僫爛著先𤉙
雞湯提來配魚唇

桌今排好緊夯椅
交椅逐塊是宣芝
椅杆閣有刻花字
也刻仙女送孩兒

緊叫菜館排桌面
閣排生花真巧神
拼盤四碟件件新
各位瓜子佮杏仁

也排桔汁共烏醋
甘蔗削皮佮切箍
皮蛋過糋才袂烏
洋豆雞肉配豬肚

湯匙著掛湯匙座
瓜子加買才袂無
一桌排到好好好
下昏小娘欲請哥

吩咐總舖湯著清
芋泥阮欲換杏仁
碗盤共阮攢較新
人客看了會出神

半桌點心用芋棗
一半包麻一半無
尾碗點心千重糕
毋通傷甜才有好

各項有共恁交帶
你有聽見就會知
人客小停就齊來
毋通予人食嫌歹

燒豬著燒較大隻
大隻才較有通食
肉皮著燒較到赤
到赤磅皮才有額

魚刺醋著會記倒
食了才袂嫌臭臊
逐碗共阮煮伊好
下日欲閣辦一桌

湯頭照顧拄好鹹
才免食去予人嫌
若是予人嫌漚先
你就共我提無仙

房間趕緊來整理
差人去買勿蘭池
麥酒加買廿四枝
一打小銀四箍二

所在格到真是派
緊買芳薰長城牌
長城的薰猶袂歹
會曉食薰伊就知

人客未來緊去請
請伊較緊勉強行
阮無跤手伊知影
毋通予阮閣再行

人客相招眾弟兄
欲到阮兜來開廳
厝邊的人盡知影
通人呵咾好所行

人客規陣行欲到
行到倚佇阮門口
知影這間是阮兜
一个一个爬上樓

阮今趕緊請伊坐
緊緊雙手請食茶
才共眾人叫失禮
念阮跤手無濟个

跤手無濟阮都知
才有冗早家己來
禮數遮到欲啥代
毋是生份免鋪排

知你做人好所行
若無毋敢欲請兄
大家都是相知影
知你袂嫌才毋驚

同行一陣十外人
薰盤捀予阮邊弄
鴉片紲買一錢重
毋知通燒抑毋通

薰盤阮今緊來捀
捀來予恁通邊弄
磚棚來燒較無蠓
咱有報牌無啥空

咱有去報特別牌
我今來學燒看覓
就予看見無啥代
獻光毋免驚人知

我叫總舖發落便
喝聲欲食才免延
另外加煮一碗燕
予兄食看有新嫣

桌今叫伊乘紲開
招呼朋友來坐位
阮著佮你坐相對
才袂大家積規堆

所在傷細較歹勢
望恁帶念阮一个
麥酒袂醉那食茶
實在對恁真失禮

甲遮客氣啥何因
阮也無咧毋知恁
隨隨便便無要緊
毋通想到遮認真

手攑米酒有一枝
請恁列位眾兄弟
粗菜騙喙一點意
大家毋通欲客氣

阮無客氣才有來
我的人款你所知
你我都是相意愛
朋友才有遮濟來

頭碗出來是正燕
正燕燒燒敢無煙
阿君面前看現現
這碗食了結姻緣

正燕大盞配杏仁
甜甜食了真正清
娘你有念相好情
阮有趁錢分你用

二碗出來咖哩雞
無物請兄較失陪
阿君欲食食伊濟
這碗食了結夫妻

咖哩雞肉𤉙真爛
便宜好食真有盤
知娘佮阮同心肝
刁來共娘恁做伴

三碗出來冬菜鴨
這碗氣味有較差
阿君欲食食伊飽
才袂予人看五跤

冬菜煮鴨氣味嬌
專專是骨真嘐潲
娘你賢慧有守竅
到尾大家無相僥

四碗出來炒蝦仁
佮兄食了較有親
若無棄嫌欲做陣
生理頭路著認真

蝦仁炒來真正芳
透底蝦仁無別項
你兄毋是侗戇人
生理我是做會動

五碗出來蘑菰肚
蘑菰煮到爛糊糊
這碗教人按怎哺
菜館總舖這糊塗

蘑菰罐頭本然爛
三八總舖袂曉看
干干無食了一碗
問𪜶頭家欲按怎

六碗出來炒肚尖
這碗煮來拄好鹹
菜館總舖有懸點
這碗食來無犯嫌

肚尖食了猶是喙
專專閣是無灌水
可惜這陣無芫荽
欲有食了猶較對

七碗出來是燒豬
中央一盤紅燒魚
列位朋友請起箸
燒豬食了通食魚

燒豬燒了猶久赤
磅皮大塊甲好食
這隻豬仔猶大隻
若無哪有這有額

八碗出來是拼盤
中央一碗燒豬肝
喙今咧食目咧看
阿君毋通僥心肝

豬肝有人叫肝花
一碗滿滿真正濟
阿娘的人真賢慧
啥人僥心著連回

九碗出來鮑魚肚
鮑魚切到遮大箍
遮粗叫人按怎哺
總舖實在真無譜

鮑魚本港是袂歹
切傷大箍才有呆
好鱟刣到煞滲屎
煮到這範真不該

十碗出來是封雞
封雞火𤉙到爛膎膎
欲食著用湯匙貯
菜館總舖袂曉衰

雞肉無味咱莫按
食湯猶較有字眼
今日好命拄著咱
若無提錢就為難

十一出來是水餃
一碗予兄食袂枵
阿君欲食食伊了
才袂予人笑衰潲

水餃做了猶袂歹
我看免食代先知
毋信你來共食覓
若是無好你才汰

十二出來洋王梨
這碗清甜敢袂歹
若無嫌阮歹所在
大家著閣相招來

王梨食了罐頭味
四邊的目刻無離
阿娘佮阮若有意
阮欲踮遮毋轉去

尾碗包仔千重糕
這碗出來完全無
欲拆一塊八仙桌
欲留一个貼心哥

列位朋友代先行
阿娘下昏欲留兄
拍算恁看嘛知影
失陪予恁家己行

共恁兩人說多謝
阮今來去你踮遮
差人共阮叫拖車
阮欲來去九龍崎"""
    }
]

class RhymeService:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = Path(__file__).parent / "taigi_dict.db"
        self.db_path = str(db_path)
        self.matcher = TaiwaneseRhymeMatcher()
        self.init_kua_a_tsheh_tables()

    def get_db_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_kua_a_tsheh_tables(self):
        """
        初始化歌仔冊文庫資料表與預設經典文庫
        """
        try:
            conn = self.get_db_connection()
            c = conn.cursor()
            c.execute("""
            CREATE TABLE IF NOT EXISTS kua_a_tsheh_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                theme TEXT NOT NULL,
                author TEXT DEFAULT '',
                description TEXT DEFAULT '',
                raw_content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS kua_a_tsheh_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL REFERENCES kua_a_tsheh_docs(id) ON DELETE CASCADE,
                stanza_index INTEGER NOT NULL,
                line_no INTEGER NOT NULL,
                line_in_stanza INTEGER NOT NULL,
                line_text TEXT NOT NULL,
                end_char TEXT DEFAULT '',
                end_tailo TEXT DEFAULT '',
                tone INTEGER DEFAULT NULL,
                rhyme_group TEXT DEFAULT '',
                theme TEXT DEFAULT ''
            )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_kua_doc ON kua_a_tsheh_lines(doc_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_kua_rhyme ON kua_a_tsheh_lines(rhyme_group)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_kua_theme ON kua_a_tsheh_lines(theme)")
            conn.commit()

            # 自動注入經典種子文章（若種子尚未存在）
            self._seed_default_kua_a_tsheh(conn)
            conn.close()
        except Exception as e:
            print(f"初始化歌仔冊文庫失敗: {e}")

    def _parse_and_insert_lines(self, conn, doc_id: int, theme: str, raw_content: str) -> Tuple[int, int]:
        """
        將歌仔冊內文切割為四句聯與逐行音律特徵並寫入資料庫
        """
        raw_lines = [l.strip() for l in raw_content.splitlines()]
        valid_lines = [l for l in raw_lines if l and not SECTION_HEADER_RE.match(l)]
        
        c = conn.cursor()
        line_count = 0
        stanza_idx = 1
        
        for idx, line_text in enumerate(valid_lines):
            line_no = idx + 1
            line_in_stanza = ((line_no - 1) % 4) + 1
            if line_in_stanza == 1 and idx > 0:
                stanza_idx += 1
                
            analysis = self.analyze_single_line(line_text, line_no=line_no)
            end_char = analysis.get("end_char", "")
            end_tailo = analysis.get("end_tailo", "")
            tone = analysis.get("tone")
            rhyme_group = analysis.get("rhyme_group", "")
            
            c.execute("""
            INSERT INTO kua_a_tsheh_lines 
            (doc_id, stanza_index, line_no, line_in_stanza, line_text, end_char, end_tailo, tone, rhyme_group, theme)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, stanza_idx, line_no, line_in_stanza, line_text, end_char, end_tailo, tone, rhyme_group, theme))
            line_count += 1
            
        total_stanzas = stanza_idx if line_count > 0 else 0
        return total_stanzas, line_count

    def _seed_default_kua_a_tsheh(self, conn):
        """注入經典預設歌仔冊文本（已存在者略過）"""
        for seed in DEFAULT_KUA_A_TSHEH_SEEDS:
            c = conn.cursor()
            c.execute("SELECT id FROM kua_a_tsheh_docs WHERE title = ?", (seed["title"],))
            if c.fetchone():
                continue
            c.execute("""
            INSERT INTO kua_a_tsheh_docs (title, theme, author, description, raw_content)
            VALUES (?, ?, ?, ?, ?)
            """, (seed["title"], seed["theme"], seed.get("author", ""), seed.get("description", ""), seed["raw_content"]))
            doc_id = c.lastrowid
            self._parse_and_insert_lines(conn, doc_id, seed["theme"], seed["raw_content"])
        conn.commit()

    def import_kua_a_tsheh(self, title: str, theme: str, author: str = '', description: str = '', raw_content: str = '') -> Dict[str, Any]:
        """
        匯入新的歌仔冊文章
        """
        clean_title = title.strip()
        clean_theme = theme.strip() or "未分類"
        clean_content = raw_content.strip()
        if not clean_title:
            raise ValueError("歌仔冊標題不可為空")
        if not clean_content:
            raise ValueError("歌仔冊內容不可為空")

        conn = self.get_db_connection()
        c = conn.cursor()
        c.execute("""
        INSERT INTO kua_a_tsheh_docs (title, theme, author, description, raw_content)
        VALUES (?, ?, ?, ?, ?)
        """, (clean_title, clean_theme, author.strip(), description.strip(), clean_content))
        doc_id = c.lastrowid
        
        stanzas, lines = self._parse_and_insert_lines(conn, doc_id, clean_theme, clean_content)
        conn.commit()
        conn.close()
        
        return {
            "id": doc_id,
            "title": clean_title,
            "theme": clean_theme,
            "author": author.strip(),
            "description": description.strip(),
            "stanzas_count": stanzas,
            "lines_count": lines
        }

    def get_kua_a_tsheh_list(self, theme: Optional[str] = None, keyword: Optional[str] = None, rhyme_group: Optional[str] = None, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """
        檢索歌仔冊文庫列表
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        
        where_clauses = ["1=1"]
        params = []
        
        if theme and theme != "全部主題":
            where_clauses.append("d.theme LIKE ?")
            params.append(f"%{theme}%")
        if keyword:
            where_clauses.append("(d.title LIKE ? OR d.description LIKE ? OR d.raw_content LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
        if rhyme_group:
            where_clauses.append("d.id IN (SELECT DISTINCT doc_id FROM kua_a_tsheh_lines WHERE rhyme_group = ?)")
            params.append(rhyme_group)
            
        where_sql = " AND ".join(where_clauses)
        
        count_query = f"SELECT COUNT(*) FROM kua_a_tsheh_docs d WHERE {where_sql}"
        c.execute(count_query, params)
        total_count = c.fetchone()[0]
        
        query = f"""
        SELECT d.id, d.title, d.theme, d.author, d.description, d.created_at,
               COUNT(DISTINCT l.stanza_index) AS stanzas_count,
               COUNT(l.id) AS lines_count,
               substr(d.raw_content, 1, 90) AS snippet
        FROM kua_a_tsheh_docs d
        LEFT JOIN kua_a_tsheh_lines l ON d.id = l.doc_id
        WHERE {where_sql}
        GROUP BY d.id
        ORDER BY d.id DESC
        LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        c.execute(query, params)
        rows = c.fetchall()
        
        c.execute("SELECT DISTINCT theme FROM kua_a_tsheh_docs WHERE theme != '' ORDER BY theme ASC")
        themes = [r[0] for r in c.fetchall()]
        conn.close()
        
        docs = []
        for r in rows:
            docs.append({
                "id": r["id"],
                "title": r["title"],
                "theme": r["theme"],
                "author": r["author"],
                "description": r["description"],
                "created_at": r["created_at"],
                "stanzas_count": r["stanzas_count"],
                "lines_count": r["lines_count"],
                "snippet": r["snippet"].replace('\n', ' ') + "..."
            })
            
        return {
            "total": total_count,
            "total_docs": total_count,
            "themes": themes,
            "docs": docs,
            "limit": limit,
            "offset": offset
        }

    def get_kua_a_tsheh_detail(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """
        取得單篇歌仔冊完整四句聯結構與音律細節
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, title, theme, author, description, raw_content, created_at FROM kua_a_tsheh_docs WHERE id = ?", (doc_id,))
        doc_row = c.fetchone()
        if not doc_row:
            conn.close()
            return None
            
        c.execute("""
        SELECT id, stanza_index, line_no, line_in_stanza, line_text, end_char, end_tailo, tone, rhyme_group
        FROM kua_a_tsheh_lines
        WHERE doc_id = ?
        ORDER BY line_no ASC
        """, (doc_id,))
        line_rows = c.fetchall()
        conn.close()
        
        stanzas_map = {}
        for lr in line_rows:
            s_idx = lr["stanza_index"]
            if s_idx not in stanzas_map:
                stanzas_map[s_idx] = []
            stanzas_map[s_idx].append({
                "line_no": lr["line_no"],
                "line_in_stanza": lr["line_in_stanza"],
                "line_text": lr["line_text"],
                "end_char": lr["end_char"],
                "end_tailo": lr["end_tailo"],
                "tone": lr["tone"],
                "rhyme_group": lr["rhyme_group"]
            })
            
        stanzas = []
        for s_idx in sorted(stanzas_map.keys()):
            stanzas.append({
                "stanza_index": s_idx,
                "lines": stanzas_map[s_idx]
            })
            
        return {
            "id": doc_row["id"],
            "title": doc_row["title"],
            "theme": doc_row["theme"],
            "author": doc_row["author"],
            "description": doc_row["description"],
            "raw_content": doc_row["raw_content"],
            "created_at": doc_row["created_at"],
            "total_stanzas": len(stanzas),
            "stanzas": stanzas
        }

    def delete_kua_a_tsheh(self, doc_id: int) -> bool:
        """
        刪除歌仔冊文章
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM kua_a_tsheh_lines WHERE doc_id = ?", (doc_id,))
        c.execute("DELETE FROM kua_a_tsheh_docs WHERE id = ?", (doc_id,))
        rows = c.rowcount
        conn.commit()
        conn.close()
        return rows > 0

    def find_kua_a_tsheh_references(self, rhyme_group: Optional[str] = None, theme: Optional[str] = None, keyword: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        在歌仔冊文庫中尋找同韻、同主題或關聯關鍵字的四句聯經典句
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        
        where_clauses = []
        params = []
        
        if rhyme_group:
            where_clauses.append("l.rhyme_group = ?")
            params.append(rhyme_group)
        if theme and theme != "全部主題":
            where_clauses.append("l.theme LIKE ?")
            params.append(f"%{theme}%")
        if keyword:
            where_clauses.append("l.line_text LIKE ?")
            params.append(f"%{keyword}%")
            
        if not where_clauses:
            where_clauses.append("1=1")
            
        where_sql = " AND ".join(where_clauses)
        
        c.execute(f"""
        SELECT DISTINCT l.doc_id, l.stanza_index, d.title, d.theme
        FROM kua_a_tsheh_lines l
        JOIN kua_a_tsheh_docs d ON l.doc_id = d.id
        WHERE {where_sql}
        ORDER BY (l.line_in_stanza IN (2, 4)) DESC, l.id ASC
        LIMIT ?
        """, (*params, limit))
        candidate_stanzas = c.fetchall()
        
        results = []
        for cs in candidate_stanzas:
            doc_id = cs["doc_id"]
            s_idx = cs["stanza_index"]
            c.execute("""
            SELECT line_no, line_in_stanza, line_text, end_char, end_tailo, tone, rhyme_group
            FROM kua_a_tsheh_lines
            WHERE doc_id = ? AND stanza_index = ?
            ORDER BY line_no ASC
            """, (doc_id, s_idx))
            lines = c.fetchall()
            
            stanza_lines = []
            for ln in lines:
                is_match = False
                if rhyme_group and ln["rhyme_group"] == rhyme_group:
                    is_match = True
                if keyword and keyword in ln["line_text"]:
                    is_match = True
                    
                stanza_lines.append({
                    "line_no": ln["line_no"],
                    "line_in_stanza": ln["line_in_stanza"],
                    "line_text": ln["line_text"],
                    "end_char": ln["end_char"],
                    "end_tailo": ln["end_tailo"],
                    "tone": ln["tone"],
                    "rhyme_group": ln["rhyme_group"],
                    "is_match": is_match
                })
                
            results.append({
                "doc_id": doc_id,
                "doc_title": cs["title"],
                "theme": cs["theme"],
                "stanza_index": s_idx,
                "lines": stanza_lines
            })
            
        conn.close()
        return results

    def lookup_char(self, char: str) -> List[Dict[str, Any]]:
        """
        查詢單一漢字在台語中的所有可能讀音與押韻歸屬
        """
        if not char:
            return []
        conn = self.get_db_connection()
        c = conn.cursor()
        c.execute("""
        SELECT hanji, tailo, rhyme_group, tone FROM char_readings WHERE hanji = ?
        """, (char,))
        rows = c.fetchall()
        
        # 若在 char_readings 沒找到，再從 words 單字查找
        if not rows:
            c.execute("""
            SELECT hanji, tailo, rhyme_group, tone FROM words WHERE hanji = ? AND char_count = 1
            """, (char,))
            rows = c.fetchall()
            
        conn.close()
        
        results = []
        seen = set()
        for r in rows:
            key = (r["hanji"], r["tailo"], r["rhyme_group"])
            if key not in seen:
                seen.add(key)
                group_id = r["rhyme_group"]
                group_info = self.matcher.rhyme_groups.get(group_id, {})
                results.append({
                    "hanji": r["hanji"],
                    "tailo": r["tailo"],
                    "rhyme_group": group_id,
                    "group_desc": group_info.get("description", "未分類"),
                    "group_type": group_info.get("type", ""),
                    "tone": r["tone"]
                })
        return results

    def lookup_word(self, word: str) -> List[Dict[str, Any]]:
        """
        查詢特定詞彙（單字或多字詞）
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        c.execute("""
        SELECT id, word_type, hanji, tailo, pos, definition, rhyme_group, tone, char_count
        FROM words WHERE hanji = ?
        """, (word,))
        rows = c.fetchall()
        conn.close()
        
        results = []
        for r in rows:
            group_id = r["rhyme_group"]
            group_info = self.matcher.rhyme_groups.get(group_id, {})
            results.append({
                "id": r["id"],
                "hanji": r["hanji"],
                "tailo": r["tailo"],
                "pos": r["pos"],
                "definition": r["definition"],
                "rhyme_group": group_id,
                "group_desc": group_info.get("description", "未分類"),
                "group_type": group_info.get("type", ""),
                "tone": r["tone"]
            })
        return results

    def analyze_single_line(self, line: str, line_no: int = 1, target_rhyme_group: Optional[str] = None) -> Dict[str, Any]:
        """
        分析單行歌詞尾字的韻母與韻部
        """
        raw_text = line.strip()
        if not raw_text or SECTION_HEADER_RE.match(raw_text):
            return {
                "line_no": line_no,
                "text": raw_text,
                "is_section_header": bool(SECTION_HEADER_RE.match(raw_text)),
                "is_valid": False,
                "end_char": "",
                "end_tailo": "",
                "rhyme_group": "",
                "group_desc": "",
                "tone": None,
                "tone_type": ""
            }

        # 清除句末標點符號
        clean_text = re.sub(r'[\s\.,\?!，。？！…—~～、]+$', '', raw_text)
        if not clean_text:
            return {"line_no": line_no, "text": raw_text, "is_valid": False}

        # 判斷是否為純拼音（台羅）
        is_pure_tailo = bool(re.match(r'^[a-zA-Z0-9\-\s\u0300-\u036f]+$', clean_text))
        
        end_word = ""
        tailo = ""
        rhyme = ""
        rhyme_group = ""
        tone = None
        
        if is_pure_tailo:
            # 純台羅：取最後一個音節
            tokens = [t for t in re.split(r'[\s\-]+', clean_text) if t]
            if tokens:
                end_word = tokens[-1]
                tailo = end_word
                init, rhyme, tone = self.matcher.split_syllable(end_word)
                grp_res = self.matcher.get_rhyme_group(end_word)
                if grp_res:
                    rhyme_group = grp_res["group_id"]
        else:
            # 漢字或漢羅混合：嘗試取最後2字看是否為辭典詞彙
            last_two = clean_text[-2:] if len(clean_text) >= 2 else ""
            two_word_matches = self.lookup_word(last_two) if last_two else []
            
            if two_word_matches and two_word_matches[0]["rhyme_group"]:
                if target_rhyme_group:
                    m_cands = [w for w in two_word_matches if w.get("rhyme_group") == target_rhyme_group]
                    m = m_cands[0] if m_cands else two_word_matches[0]
                else:
                    m = two_word_matches[0]
                end_word = last_two
                tailo = m["tailo"]
                rhyme_group = m["rhyme_group"]
                tone = m["tone"]
            else:
                # 取最後一個漢字查詢讀音
                last_char = clean_text[-1]
                end_word = last_char
                char_matches = self.lookup_char(last_char)
                if char_matches:
                    if target_rhyme_group:
                        m_cands = [c for c in char_matches if c.get("rhyme_group") == target_rhyme_group]
                        m = m_cands[0] if m_cands else char_matches[0]
                    else:
                        m = char_matches[0]
                    tailo = m["tailo"]
                    rhyme_group = m["rhyme_group"]
                    tone = m["tone"]
                else:
                    # 若漢字查不到，檢查末尾是否為拼音音節
                    tailo_match = re.search(r'([a-zA-Z\u0300-\u036f]+[0-9]?)$', clean_text)
                    if tailo_match:
                        syl = tailo_match.group(1)
                        end_word = syl
                        tailo = syl
                        grp_res = self.matcher.get_rhyme_group(syl)
                        if grp_res:
                            rhyme_group = grp_res["group_id"]

        # 萃取末字韻母
        rhyme = ""
        if tailo:
            parts = [s for s in re.split(r'[\s\-]+', tailo.split('/')[0]) if s and s != '--']
            if parts:
                _, rhyme, _ = self.matcher.split_syllable(parts[-1])

        # 計算聲調類型 (平聲 1, 5; 仄聲 2, 3, 4, 7, 8)
        tone_type = ""
        if tone in (1, 5):
            tone_type = "平聲"
        elif tone in (2, 3, 7):
            tone_type = "仄聲"
        elif tone in (4, 8):
            tone_type = "入聲(仄)"
            
        group_info = self.matcher.rhyme_groups.get(rhyme_group, {})

        return {
            "line_no": line_no,
            "text": raw_text,
            "is_section_header": False,
            "is_valid": bool(end_word),
            "end_char": end_word,
            "end_tailo": tailo,
            "rhyme": rhyme,
            "rhyme_group": rhyme_group,
            "group_desc": group_info.get("description", "未分類/未知"),
            "group_type": group_info.get("type", ""),
            "tone": tone,
            "tone_type": tone_type
        }

    @staticmethod
    def check_rhyme_relationship(rhyme1: str, rhyme2: str, grp1: str, grp2: str) -> str:
        """
        判定兩個韻母的押韻關係：
        - 'exact': 完全正押 (同一韻母)
        - 'borrow_nasal_coda': 陽聲韻 -m/-n/-ng 互借 (如 an/ang, am/an) 或塞音入聲 -p/-t/-k 互借
        - 'borrow_oral_nasal': 口鼻通押 (如 a/ann, e/enn, ua/uann)
        - 'borrow_other': 同通押部之其他通押變體
        - 'mismatch': 核心元音不相容 / 完全失韻
        """
        if not grp1 or not grp2 or grp1 != grp2:
            return 'mismatch'
            
        r1 = (rhyme1 or '').lower()
        r2 = (rhyme2 or '').lower()
        if r1 == r2:
            return 'exact'
            
        # 口鼻通押檢查 (一個有 nn 一個沒有)
        has_nn1 = 'nn' in r1
        has_nn2 = 'nn' in r2
        if has_nn1 != has_nn2:
            return 'borrow_oral_nasal'
            
        # 鼻音韻尾互借 (-m, -n, -ng)
        def get_coda(r):
            if r.endswith('ng'):
                return 'ng'
            if r and r[-1] in 'mnptk':
                return r[-1]
            return ''
            
        coda1 = get_coda(r1)
        coda2 = get_coda(r2)
        if coda1 and coda2 and coda1 != coda2:
            return 'borrow_nasal_coda'
            
        return 'borrow_other'

    @staticmethod
    def is_checked_rhyme(line_item: Dict[str, Any]) -> bool:
        """判斷音節是否為入聲韻尾 (-p, -t, -k, -h) 或入聲調 (4, 8 聲)"""
        if not line_item:
            return False
        grp = line_item.get("rhyme_group", "")
        if grp.startswith("STOP_"):
            return True
        r = line_item.get("rhyme", "")
        if r and r[-1] in ('p', 't', 'k', 'h'):
            return True
        t = line_item.get("tone")
        if t in (4, 8):
            return True
        return False

    def evaluate_stanza(self, stanza_lines: List[Dict[str, Any]], stanza_idx: int = 1) -> Dict[str, Any]:
        """
        四句聯/段落台語唸歌鬥句（Tàu-kù）檢查模組：全面採納周定邦老師實務格律
        
        【核心格律規範】
        1. 一般舒聲／陽聲韻：
           - 第 1、3 句：自由發揮，不強制檢查聲調，不限制平仄，入韻視為加分。
           - 第 2、4 句（韻跤）：
             - 押韻：必須同部押韻。
             - ❌ 阻擋（紅燈）：尾字聲調為第 2、3、4 聲（禁用降調/促音）。唱腔易下墜。
             - ⚠️ 寬容／提示（黃燈）：尾字聲調為第 7 聲或第 8 聲。實務演唱以 1、5 聲最圓順。
             - ✅ 完全合律（綠燈）：第 2、4 句尾字皆為第 1 聲或第 5 聲（1、5 最好原則）。
        2. 入聲句專屬判定（尾字帶 -p / -t / -k / -h 且押入聲韻）：
           - 啟用入聲四句公式「4 8 4 8」檢查：
             第 1 句 4 聲、第 2 句 8 聲、第 3 句 4 聲、第 4 句 8 聲。
        """
        line_count = len(stanza_lines)
        if line_count == 0:
            return {
                "stanza_idx": stanza_idx,
                "traffic_light": "neutral",
                "title": "無內容",
                "summary": "",
                "messages": []
            }

        l1 = stanza_lines[0] if line_count >= 1 else None
        l2 = stanza_lines[1] if line_count >= 2 else None
        l3 = stanza_lines[2] if line_count >= 3 else None
        l4 = stanza_lines[3] if line_count >= 4 else None

        messages = []

        # 雙句對聯檢查
        if l2 and not l4:
            t2 = l2.get("tone")
            if t2 in (1, 5):
                return {
                    "stanza_idx": stanza_idx,
                    "traffic_light": "green",
                    "title": "綠燈（完美合律・1、5最好）",
                    "summary": f"第 2 句尾字「{l2.get('end_char')}」為第 {t2} 聲（1、5最好最圓順）。",
                    "messages": [f"第 2 句尾字聲調合律（第 {t2} 聲）。"]
                }
            elif t2 in (7, 8):
                return {
                    "stanza_idx": stanza_idx,
                    "traffic_light": "yellow",
                    "title": "黃燈（合格・使用7/8聲）",
                    "summary": f"第 2 句尾字為第 {t2} 聲，合律；實務演唱以第 1、5 聲最為圓順。",
                    "messages": [f"合律（使用第 {t2} 聲）。提示：實務演唱以第 1、5 聲最為圓順（1、5 最好）。"]
                }
            else:
                return {
                    "stanza_idx": stanza_idx,
                    "traffic_light": "red",
                    "title": "紅燈（韻跤禁用降調）",
                    "summary": f"第 2 句尾字「{l2.get('end_char')}」為第 {t2} 聲（降調/促音），唱腔易下墜。",
                    "messages": ["第 2 句尾字不可使用降調/促音（第 2、3、4 聲），唱腔易下墜。"]
                }

        # 完整四句檢測 (依周定邦老師格律)
        if l2 and l4:
            r_rel = self.check_rhyme_relationship(
                l2.get("rhyme", ""), l4.get("rhyme", ""),
                l2.get("rhyme_group", ""), l4.get("rhyme_group", "")
            )
            t1 = l1.get("tone") if l1 else None
            t2 = l2.get("tone")
            t3 = l3.get("tone") if l3 else None
            t4 = l4.get("tone")

            # 1. 核心失韻檢查 (紅燈)
            if r_rel == 'mismatch':
                return {
                    "stanza_idx": stanza_idx,
                    "traffic_light": "red",
                    "title": "紅燈（完全失韻）",
                    "summary": f"第 2 句尾字「{l2.get('end_char')}」與第 4 句尾字「{l4.get('end_char')}」韻腹不相容，建議更換。",
                    "messages": [
                        f"第 2 句韻部為 {l2.get('rhyme_group')}，第 4 句韻部為 {l4.get('rhyme_group')}，核心元音完全不同，無法通押。"
                    ],
                    "line_indices": [l["line_no"] for l in stanza_lines if "line_no" in l]
                }

            # 判定是否為入聲句專門格律 (第 2、4 句皆為入聲韻尾或入聲調)
            is_l2_checked = self.is_checked_rhyme(l2)
            is_l4_checked = self.is_checked_rhyme(l4)
            is_checked_stanza = is_l2_checked and is_l4_checked

            # ==========================================
            # 模式 1：入聲句專屬判定（4 8 4 8 格律）
            # ==========================================
            if is_checked_stanza:
                l1_ok = (t1 == 4)
                l2_ok = (t2 == 8)
                l3_ok = (t3 == 4)
                l4_ok = (t4 == 8)
                all_4848 = l1_ok and l2_ok and l3_ok and l4_ok

                if all_4848:
                    return {
                        "stanza_idx": stanza_idx,
                        "traffic_light": "green",
                        "title": "綠燈（完全合律・入聲 4 8 4 8 格律）",
                        "summary": "完美合律入聲句！四句尾字聲調嚴格遵循周定邦老師『4 8 4 8』唸歌入聲專門格律。",
                        "messages": [
                            f"✅ 第 1 句尾字「{l1.get('end_char')}」為第 4 聲（陰入）。",
                            f"✅ 第 2 句尾字「{l2.get('end_char')}」為第 8 聲（陽入）。",
                            f"✅ 第 3 句尾字「{l3.get('end_char')}」為第 4 聲（陰入）。",
                            f"✅ 第 4 句尾字「{l4.get('end_char')}」為第 8 聲（陽入）。"
                        ],
                        "line_indices": [l["line_no"] for l in stanza_lines if "line_no" in l]
                    }
                else:
                    dev_messages = ["入聲句四句聲調須依序為：第 1 句 4 聲、第 2 句 8 聲、第 3 句 4 聲、第 4 句 8 聲（4 8 4 8 格律）。"]
                    if not l1_ok and l1:
                        dev_messages.append(f"第 1 句尾字「{l1.get('end_char')}」為第 {t1} 聲（依 4 8 4 8 格律須為第 4 聲陰入）。")
                    if not l2_ok:
                        dev_messages.append(f"第 2 句尾字「{l2.get('end_char')}」為第 {t2} 聲（依 4 8 4 8 格律須為第 8 聲陽入）。")
                    if not l3_ok and l3:
                        dev_messages.append(f"第 3 句尾字「{l3.get('end_char')}」為第 {t3} 聲（依 4 8 4 8 格律須為第 4 聲陰入）。")
                    if not l4_ok:
                        dev_messages.append(f"第 4 句尾字「{l4.get('end_char')}」為第 {t4} 聲（依 4 8 4 8 格律須為第 8 聲陽入）。")

                    has_falling = (t2 in (2, 3)) or (t4 in (2, 3))
                    traffic_light = "red" if has_falling else "yellow"
                    title = "紅燈（入聲格律未合）" if has_falling else "黃燈（入聲格律偏差提示）"
                    summary = "入聲句四句聲調須依序為：第 1 句 4 聲、第 2 句 8 聲、第 3 句 4 聲、第 4 句 8 聲（4 8 4 8 格律）。"

                    return {
                        "stanza_idx": stanza_idx,
                        "traffic_light": traffic_light,
                        "title": title,
                        "summary": summary,
                        "messages": dev_messages,
                        "line_indices": [l["line_no"] for l in stanza_lines if "line_no" in l]
                    }

            # ==========================================
            # 模式 2：一般舒聲／陽聲韻判定（非入聲閉尾）
            # ==========================================
            # 借韻檢查
            is_borrowing = False
            if r_rel == 'borrow_nasal_coda':
                is_borrowing = True
                messages.append("此處採用民間借韻（-m/-n/-ng 互借，如 an/ang 通押），演唱時注意順音拖腔即可。")
            elif r_rel == 'borrow_oral_nasal':
                is_borrowing = True
                messages.append("此處採用民間借韻（口鼻通押，如 a/ann 互押），演唱時注意順音拖腔即可。")
            elif r_rel == 'borrow_other':
                is_borrowing = True
                messages.append("此處採用民間通押寬韻（同部介音或變體通押），演唱時注意順音拖腔即可。")

            # 聲調檢查：禁用降調 (2, 3, 4 聲)
            has_falling_tone = (t2 in (2, 3, 4)) or (t4 in (2, 3, 4))
            if has_falling_tone:
                falling_reasons = []
                if t2 in (2, 3, 4):
                    falling_reasons.append(f"❌ 禁用降調：第 2 句尾字「{l2.get('end_char')}」為第 {t2} 聲（降調/促音），唱腔易下墜，依周定邦老師格律嚴禁使用。")
                if t4 in (2, 3, 4):
                    falling_reasons.append(f"❌ 禁用降調：第 4 句尾字「{l4.get('end_char')}」為第 {t4} 聲（降調/促音），唱腔易下墜，依周定邦老師格律嚴禁使用。")
                
                messages = falling_reasons + messages
                return {
                    "stanza_idx": stanza_idx,
                    "traffic_light": "red",
                    "title": "紅燈（韻跤禁用降調）",
                    "summary": "第 2 句或第 4 句尾字不可使用降調/促音（第 2、3、4 聲），唱腔易下墜。",
                    "messages": messages,
                    "line_indices": [l["line_no"] for l in stanza_lines if "line_no" in l]
                }

            # 第 1 句與第 3 句：自由發揮，若有入韻視為加分
            if l1:
                r_rel_1 = self.check_rhyme_relationship(
                    l1.get("rhyme", ""), l2.get("rhyme", ""),
                    l1.get("rhyme_group", ""), l2.get("rhyme_group", "")
                )
                if r_rel_1 != 'mismatch':
                    messages.append(f"✨ 首句入韻：第 1 句尾字「{l1.get('end_char')}」同入韻部，更添詩意綿密。")

            if l3:
                r_rel_3 = self.check_rhyme_relationship(
                    l3.get("rhyme", ""), l2.get("rhyme", ""),
                    l3.get("rhyme_group", ""), l2.get("rhyme_group", "")
                )
                if r_rel_3 != 'mismatch':
                    messages.append(f"✨ 轉句入韻：第 3 句尾字「{l3.get('end_char')}」同入韻部，四句通押，歌調一氣呵成。")

            # 聲調：是否使用了 7、8 聲 (黃燈寬容提示) 或完全為 1、5 聲 (綠燈最優)
            has_7_or_8 = (t2 in (7, 8)) or (t4 in (7, 8))
            if has_7_or_8 or is_borrowing:
                if t2 in (7, 8):
                    messages.insert(0, f"第 2 句尾字「{l2.get('end_char')}」為第 {t2} 聲，合律；提示：實務演唱以第 1、5 聲最為圓順（1、5 最好）。")
                else:
                    messages.insert(0, f"✅ 第 2 句尾字「{l2.get('end_char')}」為第 {t2} 聲（1、5最優圓順）。")

                if t4 in (7, 8):
                    messages.insert(1, f"第 4 句尾字「{l4.get('end_char')}」為第 {t4} 聲，合律；提示：實務演唱以第 1、5 聲最為圓順（1、5 最好）。")
                else:
                    messages.insert(1, f"✅ 第 4 句尾字「{l4.get('end_char')}」為第 {t4} 聲（1、5最優圓順）。")

                return {
                    "stanza_idx": stanza_idx,
                    "traffic_light": "yellow",
                    "title": "黃燈（合格・使用7/8聲或借韻）",
                    "summary": "合律（使用第 7/8 聲）。提示：實務演唱以第 1、5 聲最為圓順（1、5 最好）。",
                    "messages": messages,
                    "line_indices": [l["line_no"] for l in stanza_lines if "line_no" in l]
                }
            else:
                # 第 2、4 句皆為 1 或 5 聲，且非借韻 -> 綠燈完美合律！
                messages.insert(0, f"✅ 第 2 句尾字「{l2.get('end_char')}」為第 {t2} 聲（完美圓順）。")
                messages.insert(1, f"✅ 第 4 句尾字「{l4.get('end_char')}」為第 {t4} 聲（完美圓順）。")
                return {
                    "stanza_idx": stanza_idx,
                    "traffic_light": "green",
                    "title": "綠燈（完美合律・1、5最好）",
                    "summary": "完美合律！符合 1、5 最好原則。第 2、4 句尾字皆為第 1 聲或第 5 聲最優聲調。",
                    "messages": messages,
                    "line_indices": [l["line_no"] for l in stanza_lines if "line_no" in l]
                }

        return {
            "stanza_idx": stanza_idx,
            "traffic_light": "neutral",
            "title": "行數未滿四句",
            "summary": "尚未形成完整四句聯結構",
            "messages": []
        }

    def analyze_lyrics(self, lyrics_text: str) -> Dict[str, Any]:
        """
        完整歌詞押韻檢測：逐行分析、段落四句聯周定邦老師格律三級判定、計算主韻、押韻率與違押標記
        """
        raw_lines = lyrics_text.splitlines()
        analyzed_lines = []
        valid_lines = []
        group_counts = {}

        for idx, line in enumerate(raw_lines, 1):
            item = self.analyze_single_line(line, line_no=idx)
            analyzed_lines.append(item)
            if item.get("is_valid") and item.get("rhyme_group"):
                grp = item["rhyme_group"]
                group_counts[grp] = group_counts.get(grp, 0) + 1
                valid_lines.append(item)

        # 找出整篇歌詞的最優主押韻部 (Primary Rhyme Group)
        primary_group = ""
        if group_counts:
            sorted_groups = sorted(group_counts.items(), key=lambda x: x[1], reverse=True)
            primary_group = sorted_groups[0][0]

        # 為有效行賦予四句聯結構角色與聲調評定 (依周定邦老師格律)
        stanza_count = (len(valid_lines) + 3) // 4
        for k, vline in enumerate(valid_lines):
            s_idx = (k // 4) + 1
            pos_idx = (k % 4) + 1 # 1: 首句, 2: 韻跤, 3: 轉折, 4: 韻跤
            vline["stanza_idx"] = s_idx
            vline["role_index"] = pos_idx
            
            # 檢查所屬四句聯是否以入聲押韻
            s_valid = valid_lines[(s_idx - 1) * 4 : s_idx * 4]
            is_stanza_checked = False
            if len(s_valid) >= 2:
                sl2 = s_valid[1] if len(s_valid) >= 2 else None
                sl4 = s_valid[3] if len(s_valid) >= 4 else None
                if sl2 and sl4:
                    is_stanza_checked = self.is_checked_rhyme(sl2) and self.is_checked_rhyme(sl4)
                elif sl2:
                    is_stanza_checked = self.is_checked_rhyme(sl2)

            t = vline.get("tone")
            if is_stanza_checked:
                # 入聲句 4 8 4 8 格律
                if pos_idx in (1, 3):
                    vline["role_name"] = "起句" if pos_idx == 1 else "轉折句"
                    vline["role_rule"] = "入聲句專屬格律：尾字須為第 4 聲（陰入）"
                    if t == 4:
                        vline["tone_grade"] = "optimal"
                        vline["tone_feedback"] = "入聲專門格律最優（第 4 聲 陰入）"
                    else:
                        vline["tone_grade"] = "warning"
                        vline["tone_feedback"] = f"提示：入聲句第 {pos_idx} 句宜為第 4 聲（4 8 4 8 格律）"
                else:
                    vline["role_name"] = "韻跤句"
                    vline["role_rule"] = "入聲句專屬格律：尾字須為第 8 聲（陽入）"
                    if t == 8:
                        vline["tone_grade"] = "optimal"
                        vline["tone_feedback"] = "入聲專門格律最優（第 8 聲 陽入）"
                    elif t == 4:
                        vline["tone_grade"] = "warning"
                        vline["tone_feedback"] = "提示：入聲句第 2、4 句韻跤宜為第 8 聲（4 8 4 8 格律）"
                    else:
                        vline["tone_grade"] = "danger"
                        vline["tone_feedback"] = "❌ 違規：入聲句韻跤須為第 8 聲"
            else:
                # 舒聲/陽聲句：第 1、3 句自由發揮；第 2、4 句「降的不用，1、5最好」
                if pos_idx in (1, 3):
                    vline["role_name"] = "首句 (起句)" if pos_idx == 1 else "轉句 (轉折)"
                    vline["role_rule"] = "自由發揮，不限制聲調與平仄，入韻加分"
                    vline["tone_grade"] = "neutral"
                    vline["tone_feedback"] = "自由發揮（不限平仄）"
                elif pos_idx in (2, 4):
                    vline["role_name"] = "韻跤句"
                    vline["role_rule"] = "禁用降調(2,3,4聲)；合格1,5,7,8聲；最優1,5聲"
                    if t in (1, 5):
                        vline["tone_grade"] = "optimal"
                        vline["tone_feedback"] = "🌟 最優聲調（1、5最好，圓順合律）"
                    elif t in (7, 8):
                        vline["tone_grade"] = "acceptable"
                        vline["tone_feedback"] = "合格聲調（第 7/8 聲；提示：演唱以 1、5 聲最圓順）"
                    elif t in (2, 3, 4):
                        vline["tone_grade"] = "danger"
                        vline["tone_feedback"] = "❌ 禁用降調/促音（第 2、3、4 聲），唱腔易下墜"
                    else:
                        vline["tone_grade"] = "neutral"
                        vline["tone_feedback"] = f"第 {t} 聲"

        # 標記每行是否押韻（與主韻相同或與前句同韻）
        rhyme_line_count = 0
        for i, item in enumerate(analyzed_lines):
            if not item.get("is_valid"):
                item["rhyme_status"] = "無"
                continue
                
            grp = item.get("rhyme_group")
            if not grp:
                item["rhyme_status"] = "未識別"
                continue
                
            if grp == primary_group:
                item["rhyme_status"] = "押主韻"
                item["is_rhyme"] = True
                rhyme_line_count += 1
            else:
                prev_grp = None
                for prev_idx in range(i - 1, -1, -1):
                    if analyzed_lines[prev_idx].get("is_valid"):
                        prev_grp = analyzed_lines[prev_idx].get("rhyme_group")
                        break
                if prev_grp and grp == prev_grp:
                    item["rhyme_status"] = "偶句通押"
                    item["is_rhyme"] = True
                    rhyme_line_count += 1
                else:
                    item["rhyme_status"] = "出韻"
                    item["is_rhyme"] = False

        # 分段進行四句聯三級燈號評定 (周定邦老師格律)
        stanzas = []
        for s_i in range(1, stanza_count + 1):
            s_lines = [l for l in valid_lines if l.get("stanza_idx") == s_i]
            if s_lines:
                eval_res = self.evaluate_stanza(s_lines, stanza_idx=s_i)
                stanzas.append(eval_res)

        total_valid = len(valid_lines)
        rhyme_rate = round((rhyme_line_count / total_valid * 100), 1) if total_valid > 0 else 0.0
        primary_desc = self.matcher.rhyme_groups.get(primary_group, {}).get("description", "無")

        return {
            "total_lines": len(raw_lines),
            "valid_lines_count": total_valid,
            "rhyme_lines_count": rhyme_line_count,
            "rhyme_rate": rhyme_rate,
            "primary_group": primary_group,
            "primary_desc": primary_desc,
            "group_distribution": group_counts,
            "lines": analyzed_lines,
            "stanzas": stanzas
        }


    def search_dictionary(self, rhyme_group: Optional[str] = None, 
                          tone: Optional[Union[int, List[int], str]] = None, 
                          char_count: Optional[int] = None,
                          pos: Optional[str] = None,
                          keyword: Optional[str] = None,
                          category: Optional[str] = None,
                          rhyme: Optional[str] = None,
                          limit: int = 50,
                          offset: int = 0) -> Dict[str, Any]:
        """
        多條件檢索教育部辭典押韻詞彙，支援：
        - 主題分類篩選（如 天氣、植物、動物、菜餚、魚類、昆蟲、心情 等）
        - 13 大通押韻部（如 OPEN_A）或精確韻母/韻腳（如 ann, a, i, ang）
        - 單一聲調或多聲調組合（如 [1, 5, 7, 8]）
        - 詞性、字數與關鍵字檢索
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        
        # 決定資料來源表（若有指定主題分類，JOIN word_categories）
        if category:
            base_from = "FROM words w JOIN word_categories wc ON w.id = wc.word_id"
            where_clauses = ["wc.category_main = ?"]
            params = [category]
        else:
            base_from = "FROM words w"
            where_clauses = ["1=1"]
            params = []
            
        if rhyme_group:
            where_clauses.append("w.rhyme_group = ?")
            params.append(rhyme_group)
            
        if rhyme:
            where_clauses.append("w.last_rhyme = ?")
            params.append(rhyme.strip().lower())
            
        if tone is not None:
            if isinstance(tone, (list, tuple, set)):
                clean_list = [int(t) for t in tone if str(t).isdigit()]
                if clean_list:
                    placeholders = ','.join(['?'] * len(clean_list))
                    where_clauses.append(f"w.tone IN ({placeholders})")
                    params.extend(clean_list)
            elif isinstance(tone, str):
                clean_list = [int(t) for t in re.split(r'[,.\s]+', tone.strip()) if t.isdigit()]
                if len(clean_list) == 1:
                    where_clauses.append("w.tone = ?")
                    params.append(clean_list[0])
                elif len(clean_list) > 1:
                    placeholders = ','.join(['?'] * len(clean_list))
                    where_clauses.append(f"w.tone IN ({placeholders})")
                    params.extend(clean_list)
            elif isinstance(tone, int):
                where_clauses.append("w.tone = ?")
                params.append(tone)
                
        if char_count:
            where_clauses.append("w.char_count = ?")
            params.append(char_count)
            
        if pos:
            where_clauses.append("w.pos LIKE ?")
            params.append(f"%{pos}%")
            
        if keyword:
            where_clauses.append("(w.hanji LIKE ? OR w.definition LIKE ? OR w.tailo LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
            
        where_sql = " AND ".join(where_clauses)
        
        # 計算總數
        count_sql = f"SELECT COUNT(DISTINCT w.id) {base_from} WHERE {where_sql}"
        c.execute(count_sql, params)
        total_count = c.fetchone()[0]

        is_fallback_group = False
        fallback_group = ""
        # 若指定了精確子韻母 (如 ann) 與特定條件後無完全相同子韻母之詞，自動展開其所屬 13 大通押部 (如 OPEN_A)
        if total_count == 0 and rhyme:
            clean_rh = rhyme.strip().lower()
            parent_grp = self.matcher.variant_to_group.get(clean_rh, "")
            if parent_grp:
                # 重建把 w.last_rhyme = ? 替換為 w.rhyme_group = parent_grp 的條件
                fb_where_clauses = []
                fb_params = []
                p_idx = 0
                for cl in where_clauses:
                    num_q = cl.count('?')
                    chunk_p = params[p_idx:p_idx + num_q]
                    p_idx += num_q
                    if cl == "w.last_rhyme = ?":
                        fb_where_clauses.append("w.rhyme_group = ?")
                        fb_params.append(parent_grp)
                    elif cl == "w.rhyme_group = ?":
                        continue
                    else:
                        fb_where_clauses.append(cl)
                        fb_params.extend(chunk_p)
                where_sql = " AND ".join(fb_where_clauses)
                params = fb_params
                c.execute(f"SELECT COUNT(DISTINCT w.id) {base_from} WHERE {where_sql}", params)
                fb_total = c.fetchone()[0]
                if fb_total > 0:
                    total_count = fb_total
                    is_fallback_group = True
                    fallback_group = parent_grp
        
        # 查詢詳細詞目
        group_by = "GROUP BY w.id" if category else ""
        select_sql = f"""
            SELECT w.id, w.word_type, w.hanji, w.tailo, w.pos, w.definition, 
                   w.rhyme_group, w.last_rhyme, w.tone, w.char_count, w.category_main,
                   (SELECT GROUP_CONCAT(category_main, '、') FROM word_categories WHERE word_id = w.id) as categories
            {base_from}
            WHERE {where_sql}
            {group_by}
            ORDER BY (CASE WHEN w.definition LIKE '(%' THEN 0 ELSE 1 END) ASC, w.char_count ASC, LENGTH(w.definition) DESC
            LIMIT ? OFFSET ?
        """
        c.execute(select_sql, params + [limit, offset])
        rows = c.fetchall()
        conn.close()
        
        words = []
        for r in rows:
            cats = r["categories"] if "categories" in r.keys() and r["categories"] else (r["category_main"] if "category_main" in r.keys() else "")
            words.append({
                "id": r["id"],
                "hanji": r["hanji"],
                "tailo": r["tailo"],
                "pos": r["pos"],
                "definition": r["definition"],
                "rhyme_group": r["rhyme_group"],
                "last_rhyme": r["last_rhyme"] if "last_rhyme" in r.keys() else "",
                "tone": r["tone"],
                "char_count": r["char_count"],
                "category_main": r["category_main"] if "category_main" in r.keys() else "",
                "categories": cats
            })
            
        return {
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "is_fallback_group": is_fallback_group,
            "fallback_group": fallback_group,
            "strict_rhyme": rhyme or "",
            "words": words
        }

    def get_dictionary_facets(self, 
                              rhyme_group: Optional[str] = None, 
                              rhyme: Optional[str] = None, 
                              category: Optional[str] = None) -> Dict[str, Any]:
        """
        獲取詞典分類與韻部的雙向統計 Facets，支援：
        1. 選定韻部/韻腳時，計算各分類的詞數分佈（如選 ann 韻時顯示各分類詞數及同部通押詞數）
        2. 選定分類時，計算 13 大通押部與全部子韻腳的詞數分佈（如選天氣、昆蟲、菜餚時顯示各韻部詞數）
        """
        conn = self.get_db_connection()
        c = conn.cursor()
        
        # 1. 統計各主題分類詞數 (若已選定 rhyme 或 rhyme_group 則帶入過濾)
        cat_query = """
            SELECT wc.category_main, COUNT(DISTINCT w.id) as cnt
            FROM words w
            JOIN word_categories wc ON w.id = wc.word_id
        """
        cat_params = []
        cat_where = []
        parent_group = ""
        if rhyme:
            clean_rh = rhyme.strip().lower()
            cat_where.append("w.last_rhyme = ?")
            cat_params.append(clean_rh)
            parent_group = self.matcher.variant_to_group.get(clean_rh, "")
        elif rhyme_group:
            cat_where.append("w.rhyme_group = ?")
            cat_params.append(rhyme_group)
            
        if cat_where:
            cat_query += " WHERE " + " AND ".join(cat_where)
        cat_query += " GROUP BY wc.category_main"
        
        c.execute(cat_query, cat_params)
        cat_map = {row["category_main"]: row["cnt"] for row in c.fetchall()}

        # 若選定了具體子韻母 (如 ann)，同步計算其所屬通押部 (如 OPEN_A) 各分類詞數，方便通押檢索
        group_cat_map = {}
        if rhyme and parent_group:
            c.execute("""
                SELECT wc.category_main, COUNT(DISTINCT w.id) as cnt
                FROM words w
                JOIN word_categories wc ON w.id = wc.word_id
                WHERE w.rhyme_group = ?
                GROUP BY wc.category_main
            """, (parent_group,))
            group_cat_map = {row["category_main"]: row["cnt"] for row in c.fetchall()}
        
        categories_list = []
        all_cats = list(dict.fromkeys(CATEGORY_ORDER + list(cat_map.keys())))
        for cat_name in all_cats:
            cnt = cat_map.get(cat_name, 0)
            g_cnt = group_cat_map.get(cat_name, cnt)
            categories_list.append({
                "name": cat_name,
                "icon": CATEGORY_ICONS.get(cat_name, "🏷️"),
                "count": cnt,
                "group_count": g_cnt,
                "parent_group": parent_group,
                "active": (cat_name == category)
            })
            
        # 若已有選定韻腳或韻部，保留核心優先分類置頂，其餘依數量排序
        if rhyme or rhyme_group:
            priority_list = ["天氣", "植物", "動物", "菜餚", "魚類", "昆蟲", "心情"]
            categories_list.sort(key=lambda x: (
                0 if x["name"] in priority_list else 1,
                priority_list.index(x["name"]) if x["name"] in priority_list else 99,
                -x["count"],
                -x.get("group_count", 0)
            ))
            
        # 2. 統計 13 大通押部詞數 (若已選定 category 則帶入過濾)
        rg_query = "SELECT w.rhyme_group, COUNT(DISTINCT w.id) as cnt FROM words w"
        rg_params = []
        if category:
            rg_query += " JOIN word_categories wc ON w.id = wc.word_id WHERE wc.category_main = ?"
            rg_params.append(category)
        rg_query += " GROUP BY w.rhyme_group"
        
        c.execute(rg_query, rg_params)
        rg_map = {row["rhyme_group"]: row["cnt"] for row in c.fetchall() if row["rhyme_group"]}
        
        rhyme_groups_meta = self.matcher.rhyme_groups if hasattr(self, 'matcher') and hasattr(self.matcher, 'rhyme_groups') else {}
        if not rhyme_groups_meta:
            from pathlib import Path
            import json
            json_path = Path(__file__).parent / "rhyme_groups.json"
            if json_path.exists():
                with open(json_path, "r", encoding="utf-8") as jf:
                    rhyme_groups_meta = json.load(jf)
                    
        rhyme_groups_list = []
        for gid, meta in rhyme_groups_meta.items():
            rhyme_groups_list.append({
                "group_id": gid,
                "description": meta.get("description", gid),
                "type": meta.get("type", "open"),
                "count": rg_map.get(gid, 0),
                "variants": meta.get("variants", []),
                "active": (gid == rhyme_group)
            })
            
        # 3. 統計具體子韻母 (last_rhyme) - 完整列出不截斷，並將常用核心韻腳如 ann, a, ang, ong, i, u, e, oo 等置頂
        rhyme_where = ["w.last_rhyme IS NOT NULL", "w.last_rhyme != ''"]
        rhyme_params = []
        rhyme_from = "FROM words w"
        if category:
            rhyme_from += " JOIN word_categories wc ON w.id = wc.word_id"
            rhyme_where.append("wc.category_main = ?")
            rhyme_params.append(category)
        if rhyme_group:
            rhyme_where.append("w.rhyme_group = ?")
            rhyme_params.append(rhyme_group)
            
        rhyme_sql = f"""
            SELECT w.last_rhyme, COUNT(DISTINCT w.id) as cnt 
            {rhyme_from} 
            WHERE {" AND ".join(rhyme_where)}
            GROUP BY w.last_rhyme 
            ORDER BY cnt DESC
        """
        c.execute(rhyme_sql, rhyme_params)
        raw_sub_rhymes = [{"rhyme": r["last_rhyme"], "count": r["cnt"], "active": (r["last_rhyme"] == rhyme)} for r in c.fetchall()]

        # 確保若當前選定了某個 rhyme (如 ann)，即使在該分類下嚴格詞數為 0，也保留在列表中顯示為 active
        existing_rhyme_names = {r["rhyme"] for r in raw_sub_rhymes}
        if rhyme and rhyme.strip().lower() not in existing_rhyme_names:
            raw_sub_rhymes.insert(0, {"rhyme": rhyme.strip().lower(), "count": 0, "active": True})
        elif not rhyme_group and "ann" not in existing_rhyme_names:
            raw_sub_rhymes.append({"rhyme": "ann", "count": 0, "active": (rhyme == "ann")})

        # 置頂代表性韻腳（讓 ann 韻、a 韻、i 韻、u 韻、e 韻、oo 韻、ang 韻、ong 韻 等在第一排即可點選）
        featured_rhymes = ["ann", "a", "ia", "ua", "iann", "uann", "i", "inn", "u", "e", "ue", "enn", "oo", "o", "io", "ai", "ui", "au", "iau", "iu", "ang", "an", "ian", "uan", "am", "in", "ing", "un", "ong", "iong", "ng"]
        sub_rhymes = sorted(
            raw_sub_rhymes,
            key=lambda x: (
                0 if x["active"] else 1,
                0 if x["rhyme"] in featured_rhymes else 1,
                featured_rhymes.index(x["rhyme"]) if x["rhyme"] in featured_rhymes else 999,
                -x["count"]
            )
        )
        
        conn.close()
        
        return {
            "active_filters": {
                "category": category,
                "rhyme_group": rhyme_group,
                "rhyme": rhyme
            },
            "categories": categories_list,
            "rhyme_groups": rhyme_groups_list,
            "sub_rhymes": sub_rhymes
        }

    def suggest_rhyming_words(self, current_line: str, 
                              target_rhyme_group: str, 
                              role_index: int = 2,
                              tone_filter: Optional[str] = None,
                              category_filter: Optional[str] = None,
                              top_k: int = 16) -> List[Dict[str, Any]]:
        """
        智慧換字詞：針對當前行在四句聯中的角色與目標押韻部，推薦語意契合且聲調合律的台語詞
        """
        if not target_rhyme_group:
            return []
            
        clean_line = re.sub(r'[\s\.,\?!，。？！…—~～、]+$', '', current_line.strip())
        if not clean_line:
            return []
            
        # 依據角色設定推薦聲調集合 (周定邦老師格律)
        is_stop_rhyme = target_rhyme_group.startswith('STOP_')
        if role_index in (2, 4):
            if is_stop_rhyme:
                recommended_tones = {8}
                allowed_tones = {4, 8}
            else:
                recommended_tones = {1, 5}
                allowed_tones = {1, 5, 7, 8} # 禁用 2, 3, 4
        elif role_index in (1, 3):
            if is_stop_rhyme:
                recommended_tones = {4}
                allowed_tones = {4, 8}
            else:
                recommended_tones = {1, 2, 3, 4, 5, 7, 8} # 自由發揮
                allowed_tones = {1, 2, 3, 4, 5, 7, 8}
        else:
            recommended_tones = {1, 2, 3, 4, 5, 7, 8}
            allowed_tones = {1, 2, 3, 4, 5, 7, 8}

        conn = self.get_db_connection()
        c = conn.cursor()
        
        # 1. 抓取原句末尾的字或詞查找近義詞
        last_char = clean_line[-1]
        last_two = clean_line[-2:] if len(clean_line) >= 2 else ""
        
        synonym_candidates = []
        c.execute("""
        SELECT w2.id, w2.hanji, w2.tailo, w2.pos, w2.definition, w2.rhyme_group, w2.tone, w2.char_count
        FROM words w1
        JOIN synonyms s ON w1.id = s.word_id
        JOIN words w2 ON s.synonym_id = w2.id
        WHERE (w1.hanji = ? OR w1.hanji = ?) AND w2.rhyme_group = ?
        """, (last_two, last_char, target_rhyme_group))
        for r in c.fetchall():
            synonym_candidates.append({
                "hanji": r["hanji"],
                "tailo": r["tailo"],
                "pos": r["pos"],
                "definition": r["definition"],
                "rhyme_group": r["rhyme_group"],
                "tone": r["tone"],
                "source": "近義辭庫精準匹配",
                "score": 95
            })

        # 計算原句要替換的末尾基底長度與詞性
        orig_tail_len = 1
        orig_pos = ""
        last_char = clean_line[-1] if clean_line else ""
        last_two = clean_line[-2:] if len(clean_line) >= 2 else ""

        if len(clean_line) >= 2:
            w_info = self.lookup_word(last_two)
            if w_info:
                orig_tail_len = 2
                orig_pos = w_info[0].get("pos", "")
        if not orig_pos and last_char:
            c_info = self.lookup_char(last_char)
            if c_info:
                orig_pos = c_info[0].get("pos", "")
        base_line = clean_line[:-orig_tail_len]

        # 2. 情境關聯詞比對：依據整句出現的主題關鍵字，在目標韻部中找情境詞
        detected_themes = []
        for theme, kw_list in THEMATIC_KEYWORDS.items():
            if any(kw in clean_line for kw in kw_list):
                detected_themes.append(theme)
        if not detected_themes:
            detected_themes = ["思念情感", "人生歲月"] # 預設通用抒情

        # 取得目標韻部的精選詞（嚴格限制 char_count == orig_tail_len，以保證字數與格律完全對齊！）
        c.execute("""
        SELECT id, hanji, tailo, pos, definition, rhyme_group, tone, char_count
        FROM words
        WHERE rhyme_group = ? AND char_count = ? AND definition != ''
        ORDER BY id ASC LIMIT 300
        """, (target_rhyme_group, orig_tail_len))
        pool = c.fetchall()
        # 若同字數候選較少，適度擴充
        if len(pool) < 20:
            c.execute("""
            SELECT id, hanji, tailo, pos, definition, rhyme_group, tone, char_count
            FROM words
            WHERE rhyme_group = ? AND char_count <= 2 AND definition != ''
            ORDER BY id ASC LIMIT 300
            """, (target_rhyme_group,))
            pool = c.fetchall()

        category_candidates = []
        if category_filter:
            c.execute("""
            SELECT DISTINCT w.id, w.hanji, w.tailo, w.pos, w.definition, w.rhyme_group, w.tone, w.char_count
            FROM words w
            JOIN word_categories wc ON w.id = wc.word_id
            WHERE wc.category_main = ? AND w.rhyme_group = ? AND w.definition != ''
            ORDER BY w.char_count ASC, LENGTH(w.definition) DESC
            LIMIT 150
            """, (category_filter, target_rhyme_group))
            for r in c.fetchall():
                score = 120
                hanji = r["hanji"]
                if len(hanji) == orig_tail_len:
                    score += 40
                elif len(hanji) == 2:
                    score += 20
                if orig_pos:
                    for main_p in ["動詞", "形容詞", "名詞", "副詞"]:
                        if main_p in orig_pos and main_p in (r["pos"] or ""):
                            score += 25
                category_candidates.append({
                    "hanji": hanji,
                    "tailo": r["tailo"],
                    "pos": r["pos"],
                    "definition": r["definition"],
                    "rhyme_group": r["rhyme_group"],
                    "tone": r["tone"],
                    "source": f"【{category_filter}】主題推薦",
                    "score": score
                })
        conn.close()

        theme_candidates = []
        for r in pool:
            hanji = r["hanji"]
            definition = r["definition"]
            pos = r["pos"]
            score = 60
            
            # 若字數恰好等於原詞長度，大幅加分
            if len(hanji) == orig_tail_len:
                score += 35

            # 若與原詞詞性相符，加分以確保語法通順
            if orig_pos:
                for main_p in ["動詞", "形容詞", "名詞", "副詞"]:
                    if main_p in orig_pos and main_p in pos:
                        score += 25
            
            # 若詞義包含原句的主題關鍵字，加分
            for theme in detected_themes:
                for kw in THEMATIC_KEYWORDS[theme]:
                    if kw in definition or kw in hanji:
                        score += 15
                        
            # 若為動詞/形容詞/名詞加分 (歌詞尾常用)
            if any(p in pos for p in ["動詞", "形容詞", "名詞"]):
                score += 5
                
            theme_candidates.append({
                "hanji": hanji,
                "tailo": r["tailo"],
                "pos": pos,
                "definition": definition,
                "rhyme_group": r["rhyme_group"],
                "tone": r["tone"],
                "source": "詞性與情境相符推薦",
                "score": score
            })

        # 合併候選詞並標註聲調與評分加權 (周定邦老師格律)
        if category_candidates:
            raw_candidates = category_candidates
        else:
            raw_candidates = synonym_candidates + theme_candidates
        for cand in raw_candidates:
            t = cand.get("tone")
            is_rec = t in recommended_tones
            cand["is_recommended_tone"] = is_rec

            if role_index in (2, 4):
                if is_stop_rhyme:
                    if t == 8:
                        cand["tone_badge_text"] = "🌟 最優 8調 (入聲4 8 4 8格律)"
                        cand["tone_badge_type"] = "optimal"
                        cand["score"] += 50
                    elif t == 4:
                        cand["tone_badge_text"] = "⚠️ 4調 (入聲韻跤宜為8調)"
                        cand["tone_badge_type"] = "warning"
                    else:
                        cand["tone_badge_text"] = f"❌ {t}調 (非入聲調)"
                        cand["tone_badge_type"] = "danger"
                        cand["score"] -= 40
                else:
                    if t in (1, 5):
                        cand["tone_badge_text"] = f"🌟 最優 {t}調 (1、5最好)"
                        cand["tone_badge_type"] = "optimal"
                        cand["score"] += 50
                    elif t in (7, 8):
                        cand["tone_badge_text"] = f"合格 {t}調 (實務以1/5圓順)"
                        cand["tone_badge_type"] = "acceptable"
                        cand["score"] += 20
                    elif t in (2, 3, 4):
                        cand["tone_badge_text"] = f"❌ 禁用 {t}調 (降調/易下墜)"
                        cand["tone_badge_type"] = "danger"
                        cand["score"] -= 50
                    else:
                        cand["tone_badge_text"] = f"{t}調"
                        cand["tone_badge_type"] = "neutral"
            elif role_index in (1, 3):
                if is_stop_rhyme:
                    if t == 4:
                        cand["tone_badge_text"] = f"🌟 最優 4調 (入聲4 8 4 8格律)"
                        cand["tone_badge_type"] = "optimal"
                        cand["score"] += 50
                    else:
                        cand["tone_badge_text"] = f"{t}調 (入聲宜為4調)"
                        cand["tone_badge_type"] = "warning"
                else:
                    cand["tone_badge_text"] = f"{t}調 (自由發揮)"
                    cand["tone_badge_type"] = "neutral"
                    cand["score"] += 20
            else:
                cand["tone_badge_text"] = f"{t}調 (自由發揮)"
                cand["tone_badge_type"] = "neutral"

        # 若使用者指定只顯示推薦聲調，進行篩選
        if tone_filter == "recommended":
            if role_index in (2, 4) and not is_stop_rhyme:
                # 舒聲韻跤：嚴格剔除 2, 3, 4 聲，只呈現 1, 5, 7, 8 聲
                raw_candidates = [c for c in raw_candidates if c.get("tone") in (1, 5, 7, 8)]
            elif role_index in (2, 4) and is_stop_rhyme:
                # 入聲韻跤：只保留 8 聲
                raw_candidates = [c for c in raw_candidates if c.get("tone") == 8]
            elif role_index in (1, 3) and is_stop_rhyme:
                # 入聲第 1、3 句：只保留 4 聲
                raw_candidates = [c for c in raw_candidates if c.get("tone") == 4]
            # 舒聲 1、3 句自由發揮，不限制
        elif tone_filter in ("optimal_1_5", "1_5"):
            raw_candidates = [c for c in raw_candidates if c.get("tone") in (1, 5)]
        elif tone_filter in ("acceptable_7_8", "7_8"):
            raw_candidates = [c for c in raw_candidates if c.get("tone") in (7, 8)]
        elif tone_filter and tone_filter.isdigit():
            raw_candidates = [c for c in raw_candidates if c.get("tone") == int(tone_filter)]

        # 依分數排序並去除重複
        sorted_cands = sorted(raw_candidates, key=lambda x: x["score"], reverse=True)
        unique_results = []
        seen = set()
        for cand in sorted_cands:
            if cand["hanji"] not in seen and cand["hanji"] != last_char and cand["hanji"] != last_two:
                seen.add(cand["hanji"])
                preview = base_line + cand["hanji"]
                cand["preview_line"] = preview
                unique_results.append(cand)
                if len(unique_results) >= top_k:
                    break
                    
        return unique_results

    def _build_ai_adjustment_prompt(self, current_line: str, 
                                    target_rhyme_group: str,
                                    prev_line: str = "", 
                                    next_line: str = "",
                                    role_index: int = 2,
                                    style: str = "抒情",
                                    tone_filter: Optional[str] = "recommended",
                                    category_filter: Optional[str] = None) -> str:
        clean_cur = current_line.strip()
        raw_chars = re.sub(r"[^\w\u4e00-\u9fff]", "", clean_cur)
        char_count = len(raw_chars) if raw_chars else 7
        is_stop_rhyme = target_rhyme_group.startswith("STOP_")

        role_name = "韻跤句（第2或第4句）" if role_index in (2, 4) else ("起句（第1句）" if role_index == 1 else "轉折句（第3句）")

        if role_index in (2, 4):
            if is_stop_rhyme:
                tone_req = "依周定邦老師入聲『4 8 4 8』專門格律，本句尾字聲調必須為【第 8 聲（陽入調）】，尾音帶 -p, -t, -k, -h 塞音！"
            else:
                tone_req = "依周定邦老師唸歌格律『降的不用，1、5 最好』：【嚴禁使用第 2、3、4 聲降調】，尾字聲調必須為【第 1 聲（陰平）】或【第 5 聲（陽平）】（最優最圓順），或第 7、8 聲（合格）。"
        elif role_index == 1:
            if is_stop_rhyme:
                tone_req = "依周定邦老師入聲『4 8 4 8』專門格律，第 1 句尾字聲調必須為【第 4 聲（陰入調）】！"
            else:
                tone_req = "依周定邦老師格律採自由發揮，不限制聲調與平仄，文意自然生動即可，若入同部韻視為加分。"
        else: # 3
            if is_stop_rhyme:
                tone_req = "依周定邦老師入聲『4 8 4 8』專門格律，第 3 句尾字聲調必須為【第 4 聲（陰入調）】！"
            else:
                tone_req = "依周定邦老師格律採自由發揮，第 3 句為轉折句，不限制聲調與平仄，文意轉折深刻即可。"

        grp_info = self.matcher.rhyme_groups.get(target_rhyme_group, {})
        variants = ", ".join(grp_info.get("variants", [])[:8])
        grp_desc = grp_info.get("description", "")

        return f"""你是一位精通台灣歌仔冊、唸歌（七字調、四句聯）與台語創作的國寶級大師。
請針對當前台語歌詞進行【文意高度契合、字數嚴格相同、音韻與聲調精確合律】的智慧改寫與換句調整：

【創作情境與歌詞上下文】
- 上一句：{prev_line or '（無）'}
- 當前句：{current_line}
- 下一句：{next_line or '（無）'}
- 原句字數：恰好 {char_count} 個漢字（極重要！七字調必須保持 {char_count} 字，不可變動字數）
- 歌詞風格/情境：{style}
{f"- 主題題材限制：請融入「" + category_filter + "」之生活意象與道地語彙，使歌詞具有鮮明的主題氛圍。" if category_filter else ""}
- 四句聯角色：{role_name}
- 目標押韻部：{target_rhyme_group}（{grp_desc}，核心韻母：{variants}）
- 聲調與格律要求：{tone_req}

【必須遵守之三大鐵律】
1. 【字數絕對一致】：所有改寫句、倒裝句、上下句建議，漢字字數【必須恰好等於 {char_count} 字】！絕不可多一字或少一字，以維持台語歌謠節奏！
2. 【文意高度連貫】：改寫必須深度融入上下文的文字意思與生活情境（如宴席酒菜、深情相思、人生感嘆、山水風景等），語句道地自然，絕不可生硬亂拼！
3. 【尾字押韻合格】：每句句尾字必須確實屬於 {target_rhyme_group} 部，且聲調嚴格符合上述格律要求。

請直接輸出嚴格的 JSON 物件（不要包含 ```json 或額外開場白）：
{{
  "replacements": [
    {{
      "line": "完整改寫句（恰好 {char_count} 字，末字押 {target_rhyme_group} 部且符合聲調）",
      "end_char": "末字",
      "explanation": "文意修辭與情境契合說明"
    }}
  ],
  "inversions": [
    {{
      "line": "道地台語倒裝/修辭重組句（恰好 {char_count} 字，末字押 {target_rhyme_group} 部且符合聲調）",
      "end_char": "末字",
      "type": "語序倒裝/詞性對偶",
      "explanation": "倒裝修辭說明"
    }}
  ],
  "prev_line_alts": [
    {{
      "line": "改寫上一句以順暢引導當前句（恰好 {char_count} 字，押 {target_rhyme_group} 部）",
      "end_char": "末字",
      "explanation": "上一句銜接說明"
    }}
  ],
  "next_line_alts": [
    {{
      "line": "對偶承接下一句（恰好 {char_count} 字，押 {target_rhyme_group} 部）",
      "end_char": "末字",
      "explanation": "下一句承接說明"
    }}
  ]
}}
請各提供 2~4 個優質候選。"""

    def _parse_and_verify_ai_adjustments(self, raw_ai: str,
                                        current_line: str,
                                        target_rhyme_group: str,
                                        role_index: int = 2) -> Optional[Dict[str, Any]]:
        clean_cur = current_line.strip()
        raw_chars = re.sub(r"[^\w\u4e00-\u9fff]", "", clean_cur)
        target_char_count = len(raw_chars) if raw_chars else 7
        is_stop_rhyme = target_rhyme_group.startswith('STOP_')

        if not raw_ai:
            return None

        clean_json = re.sub(r"^```(?:json)?\s*", "", raw_ai.strip())
        clean_json = re.sub(r"\s*```$", "", clean_json)
        start_idx = clean_json.find('{')
        end_idx = clean_json.rfind('}')
        if start_idx != -1 and end_idx != -1:
            clean_json = clean_json[start_idx:end_idx+1]
        else:
            return None

        try:
            data = json.loads(clean_json)
        except Exception:
            return None

        def get_tone_badge(t):
            if role_index in (2, 4):
                if is_stop_rhyme:
                    if t == 8: return "🌟 最優 8調 (入聲4 8 4 8格律)", "optimal"
                    elif t == 4: return "⚠️ 4調 (入聲韻跤宜為8調)", "warning"
                    else: return f"❌ {t}調 (非入聲調)", "danger"
                else:
                    if t in (1, 5): return f"🌟 最優 {t}調 (1、5最好)", "optimal"
                    elif t in (7, 8): return f"合格 {t}調 (實務以1/5圓順)", "acceptable"
                    elif t in (2, 3, 4): return f"❌ 禁用 {t}調 (降調/易下墜)", "danger"
                    else: return f"{t}調", "neutral"
            else:
                if is_stop_rhyme:
                    if t == 4: return "🌟 最優 4調 (入聲4 8 4 8格律)", "optimal"
                    else: return f"{t}調 (入聲宜為4調)", "warning"
                else:
                    return f"{t}調 (自由發揮)", "neutral"

        replacements = []
        for item in data.get("replacements", []):
            ln = item.get("line", "").strip()
            if not ln: continue
            clean_ln_chars = re.sub(r"[^\w\u4e00-\u9fff]", "", ln)
            an = self.analyze_single_line(ln, target_rhyme_group=target_rhyme_group)
            
            # 入聲與舒聲互斥檢驗
            if is_stop_rhyme and not an.get("rhyme_group", "").startswith("STOP_"):
                continue
            if not is_stop_rhyme and an.get("rhyme_group", "").startswith("STOP_"):
                continue

            t = an.get("tone")
            b_text, b_type = get_tone_badge(t)
            char_tag = f"[{len(clean_ln_chars)}字]"
            
            score = 100
            if len(clean_ln_chars) == target_char_count:
                score += 30
            if an.get("rhyme_group") == target_rhyme_group:
                score += 50
            if b_type == "optimal":
                score += 40
            elif b_type == "acceptable":
                score += 20
            elif b_type == "danger":
                score -= 60
                
            replacements.append({
                "suggested_line": ln,
                "replaced_word": an.get("end_char", ln[-1]),
                "tailo": an.get("end_tailo", ""),
                "tone": t,
                "is_recommended_tone": b_type in ("optimal", "acceptable"),
                "tone_badge_text": b_text,
                "tone_badge_type": b_type,
                "char_count": len(clean_ln_chars),
                "char_tag": char_tag,
                "pos": "AI文意整句創作",
                "definition": item.get("explanation", ""),
                "reason": f"【AI依文意格律改寫・{char_tag}】{item.get('explanation', '')}（尾字「{an.get('end_char')}」押 {an.get('rhyme_group')} 韻，{b_text}）",
                "source": "Gemini AI 智慧全句改寫 (文意相符・字數對齊)",
                "score": score
            })

        replacements.sort(key=lambda x: x["score"], reverse=True)

        # 若是韻跤句 (第2, 4句)，優先過濾降調字（2、3、4聲），只保留最優 1/5 聲或合格 7/8 聲
        if role_index in (2, 4) and not is_stop_rhyme:
            valid_reps = [r for r in replacements if r["tone_badge_type"] in ("optimal", "acceptable")]
            if valid_reps:
                replacements = valid_reps
        elif role_index in (2, 4) and is_stop_rhyme:
            valid_reps = [r for r in replacements if r["tone"] == 8]
            if valid_reps:
                replacements = valid_reps

        inversions = []
        for item in data.get("inversions", []):
            ln = item.get("line", "").strip()
            if not ln: continue
            clean_ln_chars = re.sub(r"[^\w\u4e00-\u9fff]", "", ln)
            an = self.analyze_single_line(ln, target_rhyme_group=target_rhyme_group)
            t = an.get("tone")
            b_text, b_type = get_tone_badge(t)
            char_tag = f"[{len(clean_ln_chars)}字]"
            inversions.append({
                "type": item.get("type", "台語倒裝修辭"),
                "line": ln,
                "char_count": len(clean_ln_chars),
                "char_tag": char_tag,
                "note": f"【{char_tag}】{item.get('explanation', '')}（尾字「{an.get('end_char')}」押 {an.get('rhyme_group')}，{b_text}）"
            })

        prev_alts = []
        for item in data.get("prev_line_alts", []):
            ln = item.get("line", "").strip()
            if not ln: continue
            clean_ln_chars = re.sub(r"[^\w\u4e00-\u9fff]", "", ln)
            an = self.analyze_single_line(ln, target_rhyme_group=target_rhyme_group)
            char_tag = f"[{len(clean_ln_chars)}字]"
            prev_alts.append({
                "direction": "改上一句以呼應當前句",
                "suggested_prev": ln,
                "suggested_current": clean_cur,
                "char_count": len(clean_ln_chars),
                "char_tag": char_tag,
                "rhyme_group": an.get("rhyme_group", target_rhyme_group),
                "explanation": f"【{char_tag}】{item.get('explanation', '')}（通押 {an.get('rhyme_group')} 韻）"
            })

        next_alts = []
        for item in data.get("next_line_alts", []):
            ln = item.get("line", "").strip()
            if not ln: continue
            clean_ln_chars = re.sub(r"[^\w\u4e00-\u9fff]", "", ln)
            an = self.analyze_single_line(ln, target_rhyme_group=target_rhyme_group)
            char_tag = f"[{len(clean_ln_chars)}字]"
            next_alts.append({
                "line": ln,
                "char_count": len(clean_ln_chars),
                "char_tag": char_tag,
                "rhyme_group": an.get("rhyme_group", target_rhyme_group),
                "note": f"【{char_tag}】{item.get('explanation', '')}（對偶承接，押 {an.get('rhyme_group')} 韻）"
            })

        if not replacements and not inversions:
            return None

        return {
            "word_replacements": replacements,
            "inversions": inversions,
            "prev_line_alternatives": prev_alts,
            "next_line_continuations": next_alts,
            "is_ai_generated": True
        }

    def _local_suggest_sentence_adjustments(self, current_line: str,
                                            target_rhyme_group: str,
                                            prev_line: str = "",
                                            next_line: str = "",
                                            style: str = "抒情",
                                            role_index: int = 2,
                                            tone_filter: Optional[str] = None,
                                            category_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        本地精選詞庫與歌仔冊種子句之備援換句引擎（保證字數嚴格對齊）
        """
        clean_cur = current_line.strip()
        clean_prev = prev_line.strip()
        clean_next = next_line.strip()
        is_stop_rhyme = target_rhyme_group.startswith('STOP_')

        # 1. 取得候選替換字詞
        word_suggestions = self.suggest_rhyming_words(
            clean_cur, target_rhyme_group,
            role_index=role_index,
            tone_filter=tone_filter,
            category_filter=category_filter,
            top_k=16
        )

        # 2. 句尾字替換推薦列表 (嚴格對齊字數)
        word_replacement_lines = []
        for w in word_suggestions:
            hanji = w["hanji"]
            w_len = len(hanji)
            # 安全對齊字數：替換掉原句末尾等長之字元
            if len(clean_cur) >= w_len:
                fixed_preview = clean_cur[:-w_len] + hanji
            else:
                fixed_preview = hanji
            char_tag = f"[{len(fixed_preview)}字]"
            word_replacement_lines.append({
                "suggested_line": fixed_preview,
                "replaced_word": hanji,
                "tailo": w["tailo"],
                "tone": w["tone"],
                "is_recommended_tone": w.get("is_recommended_tone", False),
                "tone_badge_text": w.get("tone_badge_text", ""),
                "tone_badge_type": w.get("tone_badge_type", "neutral"),
                "char_count": len(fixed_preview),
                "char_tag": char_tag,
                "pos": w["pos"],
                "definition": w["definition"],
                "reason": f"替換為「{hanji}」（{w['tailo']}，{w.get('tone_badge_text', '')}），押 {target_rhyme_group} 部，釋義：{w['definition'][:28]}",
                "source": "本地精準詞庫 (字數嚴格對齊)"
            })

        # 3. 句型倒裝與修辭建議
        inversion_suggestions = []
        if word_suggestions:
            top_w = word_suggestions[0]["hanji"]
            w_len = len(top_w)
            if len(clean_cur) >= 7:
                # 七字調常見的 4-3 句型倒裝：後三字或前四字前置
                p1 = clean_cur[:4]
                p2 = clean_cur[4:-w_len] if len(clean_cur) > 4 + w_len else clean_cur[4:]
                inv_line = f"{p2}{p1[:-w_len]}{top_w}" if len(p1) >= w_len else f"{clean_cur[:-w_len]}{top_w}"
                if len(inv_line) == len(clean_cur):
                    inversion_suggestions.append({
                        "type": "台語前後短語對偶倒裝",
                        "line": inv_line,
                        "char_count": len(inv_line),
                        "char_tag": f"[{len(inv_line)}字]",
                        "note": f"將動態語句前置，自然收在同韻字「{top_w}」"
                    })

        # 4. 前後句互換
        alternations = []
        cur_analysis = self.analyze_single_line(clean_cur, target_rhyme_group=target_rhyme_group)
        cur_grp = cur_analysis.get("rhyme_group")
        if cur_grp and clean_prev:
            prev_alts = self.suggest_rhyming_words(clean_prev, cur_grp, role_index=2, top_k=3)
            for pa in prev_alts:
                pa_w = pa["hanji"]
                p_len = len(pa_w)
                fixed_prev = clean_prev[:-p_len] + pa_w if len(clean_prev) >= p_len else pa_w
                alternations.append({
                    "direction": "改上一句以遷就本句",
                    "suggested_prev": fixed_prev,
                    "suggested_current": clean_cur,
                    "char_count": len(fixed_prev),
                    "char_tag": f"[{len(fixed_prev)}字]",
                    "rhyme_group": cur_grp,
                    "explanation": f"保留當前句「{clean_cur}」，將上一句改為「{fixed_prev}」，兩句通押 {cur_grp} 韻！"
                })

        # 5. 接續下一句 (優先由文庫種子四句聯中尋找合適句子)
        kua_references = self.find_kua_a_tsheh_references(rhyme_group=target_rhyme_group, limit=4)
        next_suggestions = []
        for ref in kua_references:
            for ln in ref.get("lines", []):
                if ln.get("line_in_stanza") in (3, 4) and ln.get("rhyme_group") == target_rhyme_group:
                    txt = ln.get("line_text")
                    if txt and txt != clean_cur:
                        next_suggestions.append({
                            "line": txt,
                            "char_count": len(txt),
                            "char_tag": f"[{len(txt)}字]",
                            "rhyme_group": target_rhyme_group,
                            "note": f"引用歌仔冊《{ref.get('doc_title')}》承接句，通押 {target_rhyme_group} 韻"
                        })
                        if len(next_suggestions) >= 3:
                            break
            if len(next_suggestions) >= 3:
                break

        return {
            "word_replacements": word_replacement_lines,
            "inversions": inversion_suggestions,
            "prev_line_alternatives": alternations,
            "next_line_continuations": next_suggestions,
            "is_ai_generated": False
        }

    async def suggest_sentence_adjustments_async(self, current_line: str,
                                                 target_rhyme_group: str,
                                                 prev_line: str = "",
                                                 next_line: str = "",
                                                 style: str = "抒情",
                                                 role_index: int = 2,
                                                 tone_filter: Optional[str] = None,
                                                 category_filter: Optional[str] = None,
                                                 api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        全方位改句、換句、前後句替換、倒裝與周定邦老師格律引導引擎 (異步 AI 優先)
        """
        clean_cur = current_line.strip()
        clean_prev = prev_line.strip()
        clean_next = next_line.strip()
        is_stop_rhyme = target_rhyme_group.startswith('STOP_')

        # 聲調指導與角色資訊 (周定邦老師格律)
        if role_index in (2, 4):
            if is_stop_rhyme:
                tone_guide = {
                    "role_index": role_index,
                    "role_name": "韻跤句",
                    "is_stop": True,
                    "recommended_tones": [8],
                    "title": "入聲句專門格律：第 2、4 句尾字必為第 8 聲（陽入）",
                    "tip": "周定邦老師入聲四句專門格律『4 8 4 8』：第 1 句 4 聲、第 2 句 8 聲、第 3 句 4 聲、第 4 句 8 聲。已自動挑出第 8 聲入聲詞置頂！"
                }
            else:
                tone_guide = {
                    "role_index": role_index,
                    "role_name": "韻跤句",
                    "is_stop": False,
                    "recommended_tones": [1, 5],
                    "title": "周定邦老師唸歌格律：韻跤句（第 2、4 句）「降的不用，1、5 最好」",
                    "tip": "❌ 嚴格禁用降調（第 2、3、4 聲），唱腔易下墜。合格聲調為第 1、5、7、8 聲；最優為第 1、5 聲（1、5 最好，最為圓順）。已自動挑出合律詞目，排除了降調字！"
                }
        elif role_index in (1, 3):
            if is_stop_rhyme:
                tone_guide = {
                    "role_index": role_index,
                    "role_name": "起句" if role_index == 1 else "轉折句",
                    "is_stop": True,
                    "recommended_tones": [4],
                    "title": f"入聲句專門格律：第 {role_index} 句尾字必為第 4 聲（陰入）",
                    "tip": "周定邦老師入聲四句專門格律『4 8 4 8』：第 1 句 4 聲、第 2 句 8 聲、第 3 句 4 聲、第 4 句 8 聲。"
                }
            else:
                tone_guide = {
                    "role_index": role_index,
                    "role_name": "首句" if role_index == 1 else "轉折句",
                    "is_stop": False,
                    "recommended_tones": [1, 2, 3, 4, 5, 7, 8],
                    "title": f"周定邦老師唸歌格律：第 {role_index} 句採「自由發揮」",
                    "tip": f"第 {role_index} 句尾字自由發揮，不限制聲調與平仄，文意順暢即可，若有入同部韻視為加分！"
                }
        else:
            tone_guide = {
                "role_index": role_index,
                "role_name": "自由句",
                "is_stop": False,
                "recommended_tones": [1, 2, 3, 4, 5, 7, 8],
                "title": "自由發揮句",
                "tip": "不限制平仄與聲調。"
            }

        kua_references = self.find_kua_a_tsheh_references(
            rhyme_group=target_rhyme_group,
            limit=4
        )

        active_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        result_data = None

        # 優先嘗試 Gemini AI 智慧全句改寫與換句
        if active_key:
            try:
                ai_prompt = self._build_ai_adjustment_prompt(
                    current_line=clean_cur,
                    target_rhyme_group=target_rhyme_group,
                    prev_line=clean_prev,
                    next_line=clean_next,
                    role_index=role_index,
                    style=style,
                    tone_filter=tone_filter,
                    category_filter=category_filter
                )
                raw_ai = await self.call_gemini_ai(ai_prompt, api_key=active_key, response_json=True)
                if raw_ai and not raw_ai.startswith("Gemini 呼叫失敗"):
                    result_data = self._parse_and_verify_ai_adjustments(
                        raw_ai, current_line=clean_cur,
                        target_rhyme_group=target_rhyme_group,
                        role_index=role_index
                    )
            except Exception as e:
                result_data = None

        # 若 AI 未啟用或失敗，使用升級版之本地備援引擎
        if not result_data or not result_data.get("word_replacements"):
            result_data = self._local_suggest_sentence_adjustments(
                current_line=clean_cur,
                target_rhyme_group=target_rhyme_group,
                prev_line=clean_prev,
                next_line=clean_next,
                style=style,
                role_index=role_index,
                tone_filter=tone_filter,
                category_filter=category_filter
            )

        result_data.update({
            "current_line": clean_cur,
            "target_rhyme_group": target_rhyme_group,
            "group_desc": self.matcher.rhyme_groups.get(target_rhyme_group, {}).get("description", ""),
            "tone_guide": tone_guide,
            "kua_a_tsheh_references": kua_references,
            "engine": "gemini_ai" if result_data.get("is_ai_generated") else "local_lexicon"
        })

        return result_data

    def suggest_sentence_adjustments(self, current_line: str, 
                                     target_rhyme_group: str,
                                     prev_line: str = "", 
                                     next_line: str = "",
                                     style: str = "抒情",
                                     role_index: int = 2,
                                     tone_filter: Optional[str] = None,
                                     category_filter: Optional[str] = None,
                                     api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        同步相容包裝
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # 已在運行中的 loop，使用本地備援回傳
            res = self._local_suggest_sentence_adjustments(
                current_line=current_line,
                target_rhyme_group=target_rhyme_group,
                prev_line=prev_line,
                next_line=next_line,
                style=style,
                role_index=role_index,
                tone_filter=tone_filter,
                category_filter=category_filter
            )
            res.update({
                "current_line": current_line.strip(),
                "target_rhyme_group": target_rhyme_group,
                "group_desc": self.matcher.rhyme_groups.get(target_rhyme_group, {}).get("description", ""),
                "kua_a_tsheh_references": self.find_kua_a_tsheh_references(rhyme_group=target_rhyme_group, limit=4),
                "engine": "local_lexicon"
            })
            return res
        else:
            return asyncio.run(self.suggest_sentence_adjustments_async(
                current_line=current_line,
                target_rhyme_group=target_rhyme_group,
                prev_line=prev_line,
                next_line=next_line,
                style=style,
                role_index=role_index,
                tone_filter=tone_filter,
                category_filter=category_filter,
                api_key=api_key
            ))


    async def call_gemini_ai(self, prompt: str, api_key: Optional[str] = None, response_json: bool = False) -> Optional[str]:
        """
        呼叫 Google Gemini API 進行高階台語歌詞生成與文意潤飾
        """
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            return "尚未設定 API Key，請先於右上角設定。"
            
        models_to_try = ["gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-flash-latest", "gemini-pro-latest"]
        gen_config: Dict[str, Any] = {
            "temperature": 0.7,
            "maxOutputTokens": 1500
        }
        if response_json:
            gen_config["responseMimeType"] = "application/json"

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": gen_config
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            last_error = ""
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                return parts[0].get("text", "")
                    else:
                        try:
                            err_data = resp.json()
                            last_error = err_data.get("error", {}).get("message", resp.text)
                        except Exception:
                            last_error = resp.text
                except Exception as e:
                    last_error = str(e)
            
            return f"Gemini 呼叫失敗 ({last_error})，請檢查 Key 是否具備權限或稍後再試。"

    async def test_gemini_key(self, api_key: Optional[str] = None) -> Tuple[bool, str]:
        """
        測試指定的 Gemini API Key 是否有效
        """
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            return False, "尚未提供 API Key，請輸入 Key 或在 .env 設定。"

        models_to_try = ["gemini-3.1-flash-lite", "gemini-3.8-flash", "gemini-flash-latest", "gemini-pro-latest"]
        payload = {
            "contents": [{"parts": [{"text": "請回覆：OK"}]}],
            "generationConfig": {"maxOutputTokens": 5}
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            last_err = ""
            for model in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                try:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        return True, f"連線成功！Gemini AI ({model}) 已準備就緒。"
                    else:
                        try:
                            err_json = resp.json()
                            last_err = err_json.get("error", {}).get("message", resp.text)
                        except Exception:
                            last_err = resp.text
                except Exception as e:
                    last_err = str(e)
            return False, f"驗證失敗: {last_err}"


