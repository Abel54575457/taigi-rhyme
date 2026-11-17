"""
台語常用詞辭典 28,695 條全方位主題分類與多對多標籤庫重建腳本
分類涵蓋：天氣、植物、動物、菜餚、魚類、昆蟲、心情、飲食、地理、天文、人生、身體、器物、服飾、建築、社會、民俗、文藝、動作、狀態、言語、時空等完整分類
"""

import sys
import sqlite3
import re
import time
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 主題分類優先級（當決定 words.category_main 單一主分類時使用）
CATEGORY_PRIMARY_PRIORITY = [
    "昆蟲", "魚類", "菜餚", "天氣", "天文", "服飾", "建築", "地理", 
    "民俗", "植物", "動物", "心情", "菜餚", "飲食", "人生", "身體", 
    "文藝", "器物", "社會", "動作", "狀態", "時空", "言語", "其他"
]

def classify_word(hanji, tailo, raw_cat, pos, defi):
    raw_cat = raw_cat or ""
    defi = defi or ""
    hanji = hanji or ""
    pos = pos or ""
    
    cats = set()
    
    # 1. 昆蟲 (嚴謹排除非昆蟲名)
    if "昆蟲類" in raw_cat:
        if not re.search(r'(鳥類|魚類|獸類|驅蚊|捕食|計量單位)', defi):
            cats.add("昆蟲")
    elif re.search(r'(昆蟲名|蟲名|種蟲|害蟲|幼蟲|成蟲|甲蟲|蝴蝶|螢火蟲|蜻蜓|蟋蟀|螻蛄|螞蟻|蜜蜂|白蟻|螳螂|知了|蟬|蚊子|跳蚤|毛蟲|蠶|椿象|金龜子|孑孓|蠓仔|虼蚻|火金蛄|水龜|尾蝶|草蜢仔)', defi):
        if re.search(r'(昆蟲|蟲名|種蟲|害蟲|蝴蝶|螢火蟲|蜻蜓|蟋蟀|螻蛄|螞蟻|蜜蜂|白蟻|螳螂|蟬|蚊子|跳蚤|毛蟲|蠓仔|虼蚻|火金蛄|草蜢仔)', defi):
            if not re.search(r'(鳥類|魚類|禽類|獸類|植物名|草名|樹名|器具|香草)', defi):
                cats.add("昆蟲")

    # 2. 魚類 (魚類、海鮮、蝦蟹貝類、水產海洋生物)
    if "魚蝦海獸" in raw_cat:
        if not re.search(r'(菜名|煮法|乾貨|加工食品|一道菜)', defi):
            cats.add("魚類")
    elif re.search(r'(魚名|魚類|海水魚|淡水魚|淡水產|水產|海產|蝦類|蟹類|貝類|貝殼|軟體動物|頭足類|甲殼類|鯨魚|海豚|海龜|鯊魚|水母|烏賊|章魚|花枝|小管|蚵仔|蛤蜊|九孔|海膽|海參|石斑|虱目魚|土魠|白帶魚|鰻魚|鱸魚|鯽魚|鰱魚|鯉魚|鮪魚|鮭魚|鯧魚)', defi):
        if not re.search(r'(菜名|一道菜|料理|食品名|煮好的|烹煮)', defi):
            cats.add("魚類")
    elif re.search(r'(魚|蝦|蟳|蟹|鰻|鯖|鮭|鮫|鰱|鯽|鯧|魠|魩|蚵|蜆|蛤|蚌|螺|魷|鱟|鱘)', hanji) and ("名詞" in pos or not pos):
        if re.search(r'(動物名|水生|水產|棲於|游於|生於水|產於海|產於淡水|海中|生活在水中|海產)', defi):
            if not re.search(r'(菜名|料理|熟食|食品)', defi):
                cats.add("魚類")

    # 3. 菜餚 (熟食料理、臺灣小吃、傳統小吃、佳餚羹湯、糕餅熟食、飯麵菜餚)
    is_dish = False
    if not re.search(r'^\s*\(名詞\)\s*(哺乳動物|禽鳥類|鳥類|昆蟲|瓜果類|根莖類|葉菜類|草本|木本|常綠|落葉|一年生|多年生|果樹|農作物|淡水魚|海水魚|貝類)', defi):
        if not re.search(r'(器具|砧板|刀具|鍋具|容器|家具|餐具|烹調用的器具|廚房|房間)', defi):
            if not re.search(r'(植物名|蔓生植物|豆類|菊科|節日|器官|生病)', defi):
                if re.search(r'(菜名|菜餚|一道菜|台灣小吃|傳統小吃|小吃名|料理名|料理|熟食|做成的菜|烹調成的|道地菜|名菜|著名的菜|佳餚|羹湯|湯品)', defi):
                    is_dish = True
                elif re.search(r'(糕點|點心|包子|饅頭|餃子|煎餃|鍋貼|水餃|餛飩|扁食|肉圓|割包|刈包|碗粿|筒仔米糕|米糕|潤餅|春捲|鼎邊蚖|蚵仔煎|蚵仔麵線|麵線糊|米粉炒|炒米粉|炒麵|炒飯|滷肉飯|爌肉飯|肉燥|肉羹|魷魚羹|土魠魚羹|排骨湯|排骨酥|豬血湯|下水湯|四神湯|薑絲大腸|菜脯蛋|鹹菜鴨|五柳居|三杯雞|麻油雞|燒酒雞|薑母鴨|羊肉爐|砂鍋魚頭|封肉|紅糟肉|蹄膀|滷豬腳|滷蛋|滷味|香腸|米腸|大腸包小腸|甜粿|發粿|紅龜粿|草仔粿|菜頭粿|炸粿|蚵嗲|雞卷|蝦捲|月餅|中秋餅|綠豆椪|蛋黃酥|鳳梨酥|牛舌餅|太陽餅|椪餅|麻糬|豆花|愛玉冰|仙草蜜|剉冰|八寶冰|麵茶|油條|燒餅|火鍋|關東煮|壽司|生魚片|火腿|鹹豬肉|肉乾|肉鬆)', hanji + defi):
                    if re.search(r'(食品|小吃|點心|糕|粿|餅|湯|羹|飯|粥|麵|肉|料理|食用|美味|熟食|煮熟|油炸|烘烤|醃製|包餡|甜點|飲品)', defi):
                        is_dish = True
    if is_dish:
        cats.add("菜餚")

    # 4. 天氣 (氣候、天候、氣溫、落雨、颳風、雷電、霜雪、雺霧、風颱、天陰、晴天、節氣)
    if "氣候溫度" in raw_cat or "節氣" in raw_cat:
        cats.add("天氣")
    elif "自然現象" in raw_cat and re.search(r'(風|雨|雷|電|雲|霜|雪|霧|露|雹|晴|陰|寒|熱|氣溫|天時|氣候|落雨|天光|日曝|乾旱|風颱)', defi + hanji):
        cats.add("天氣")
    elif re.search(r'(天氣|天候|氣候|氣溫|下雨|落雨|降雨|颳風|風吹|打雷|閃電|下雪|霜雪|大霧|濃霧|晨霧|晴天|陰天|好天|寒流|冷氣團|風颱|颱風|西北雨|乾旱|梅雨|天時|氣溫|天陰|雷陣雨)', defi):
        if not re.search(r'(衣服|遮蔽|阻擋|防風|心理|情緒|病名|器具)', defi):
            cats.add("天氣")
    elif re.search(r'^(風|雨|雷|電|霜|雪|霧|露|雺|霰|雹|晴|陰|落雨|出日頭|風颱|好天|歹天|天光|西北雨|寒天|熱天)', hanji) and re.search(r'(天氣|氣候|自然現象|降水|風力|溫度)', defi):
        cats.add("天氣")

    # 5. 動物 (哺乳、走獸、禽鳥、兩棲爬蟲，排除純昆蟲與純魚蝦)
    if any(k in raw_cat for k in ["禽類", "獸類", "爬蟲、兩棲類", "其他動物"]):
        if "昆蟲" not in cats and "魚類" not in cats:
            cats.add("動物")
    elif re.search(r'(哺乳動物|鳥類|鳥名|禽類|野獸|家畜|家禽|兩棲類|爬蟲類|爬蟲動物|獸名|蛇類|青蛙|蟾蜍|狗|貓|水牛|黃牛|乳牛|馬|羊|豬|鹿|猴|虎|獅|豹|象|狼|狐狸|兔|鼠|鴨|鵝|雞|鴿|雀|鵰|雁|鶴|老鷹|八哥|綠繡眼|白頭翁)', defi):
        if "昆蟲" not in cats and "魚類" not in cats:
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
    elif re.search(r'(心情|心境|情緒|喜愛|歡喜|高興|憤怒|發脾氣|傷心|悲傷|思念|想念|擔憂|煩惱|害怕|驚嚇|驚恐|恐懼|勇敢|大膽|膽小|害羞|羞恥|慚愧|後悔|心酸|相思|留戀|著急|心急|得意|失望|絕望|放心|安心|激動|佩服|心痛|痛心|快活|痛苦|怨恨|吃醋|嫉妒|羨慕|牽掛|情深|恩愛|志氣)', defi):
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

    # 13. 天文 (日月星辰、宇宙天象、天頂)
    if "天文" in raw_cat:
        cats.add("天文")
    elif re.search(r'(太陽|日頭|月亮|月娘|星星|星宿|銀河|天頂|天象|星座|彗星|日蝕|月蝕|晨曦|朝霞|夕陽|黃昏|暗暝|流星|北極星)', defi):
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

    if not cats:
        cats.add("其他")
        
    return list(cats)


def main():
    db_path = "taigi_dict.db"
    print(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
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
    c.execute("SELECT id, hanji, tailo, category, pos, definition FROM words")
    words = c.fetchall()
    print(f"Loaded {len(words)} words.")
    
    batch_cat_inserts = []
    batch_word_updates = []
    
    cat_counts = defaultdict(int)
    
    t0 = time.time()
    for row in words:
        w_id, hanji, tailo, raw_cat, pos, defi = row
        assigned_cats = classify_word(hanji, tailo, raw_cat, pos, defi)
        
        # 決定 words.category_main 單一主分類（依照優先順序）
        primary_cat = "其他"
        for p in CATEGORY_PRIMARY_PRIORITY:
            if p in assigned_cats:
                primary_cat = p
                break
                
        batch_word_updates.append((primary_cat, w_id))
        
        for cat in assigned_cats:
            cat_counts[cat] += 1
            batch_cat_inserts.append((w_id, cat, raw_cat or ''))
            
    print(f"Classification completed in {time.time() - t0:.2f}s.")
    print("Inserting into word_categories...")
    c.executemany("INSERT INTO word_categories (word_id, category_main, category_raw) VALUES (?, ?, ?)", batch_cat_inserts)
    
    print("Updating words.category_main...")
    c.executemany("UPDATE words SET category_main = ? WHERE id = ?", batch_word_updates)
    
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
