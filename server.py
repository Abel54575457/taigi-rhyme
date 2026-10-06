"""
台灣唸歌仔 AI創作工作台 - Web 伺服器
採用 Bottle 輕量級框架，提供 REST API 與單一頁面應用程式 (SPA)
"""

import os
import sys
import json
import asyncio
import re
from pathlib import Path
from bottle import Bottle, request, response, static_file, run
from dotenv import load_dotenv
from rhyme_service import RhymeService

load_dotenv()
sys.stdout.reconfigure(encoding='utf-8')

app = Bottle()
service = RhymeService()

BASE_DIR = Path(__file__).parent.resolve()

def json_response(data, status=200):
    response.status = status
    response.content_type = 'application/json; charset=utf-8'
    return json.dumps(data, ensure_ascii=False)

@app.hook('after_request')
def enable_cors():
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token'

@app.route('/', method='GET')
def index():
    return static_file('index.html', root=str(BASE_DIR))

@app.route('/static/<filename:path>', method='GET')
def serve_static(filename):
    return static_file(filename, root=str(BASE_DIR / 'static'))

@app.route('/api/config', method=['GET'])
def get_config():
    env_has_key = bool(os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'))
    return json_response({
        'has_env_key': env_has_key
    })

@app.route('/api/test_key', method=['POST', 'OPTIONS'])
def test_key_api():
    if request.method == 'OPTIONS':
        return ''
    try:
        data = request.json or {}
        api_key = data.get('api_key', '')
        success, message = asyncio.run(service.test_gemini_key(api_key))
        return json_response({'success': success, 'message': message})
    except Exception as e:
        return json_response({'success': False, 'message': str(e)})

@app.route('/api/rhyme_groups', method='GET')
def get_rhyme_groups():
    return json_response(service.matcher.rhyme_groups)


@app.route('/api/analyze', method=['POST', 'OPTIONS'])
def analyze_lyrics_api():
    if request.method == 'OPTIONS':
        return ''
    try:
        data = request.json or {}
        lyrics = data.get('lyrics', '')
        result = service.analyze_lyrics(lyrics)
        return json_response(result)
    except Exception as e:
        return json_response({'error': str(e)}, status=500)

@app.route('/api/suggest', method=['POST', 'OPTIONS'])
def suggest_api():
    if request.method == 'OPTIONS':
        return ''
    try:
        data = request.json or {}
        current_line = data.get('current_line', '')
        target_rhyme_group = data.get('target_rhyme_group', '')
        prev_line = data.get('prev_line', '')
        next_line = data.get('next_line', '')
        style = data.get('style', '抒情')
        api_key = data.get('api_key', '')
        role_index = int(data.get('role_index', 2))
        tone_filter = data.get('tone_filter', None)
        
        result = service.suggest_sentence_adjustments(
            current_line=current_line,
            target_rhyme_group=target_rhyme_group,
            prev_line=prev_line,
            next_line=next_line,
            style=style,
            role_index=role_index,
            tone_filter=tone_filter
        )
        
        # 若有提供 API Key (無論由前端傳入或由伺服器 .env 讀取) 且有要求 AI 深度潤飾
        active_key = api_key or os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
        if active_key and data.get('request_ai_gemini'):
            role_tone_prompt = ""
            is_stop_rhyme = "STOP" in target_rhyme_group or target_rhyme_group in ("STOP_AT", "STOP_ET", "STOP_OK")
            if role_index in (2, 4):
                if is_stop_rhyme:
                    role_tone_prompt = "- 音律角色：四句聯之「韻跤句」（第2或第4句）。本段為入聲句押韻，依周定邦老師『4 8 4 8』唸歌專門格律，第2句與第4句尾字必須為「第 8 聲（陽入）」，以求鏗鏘合律。"
                else:
                    role_tone_prompt = "- 音律角色：四句聯之「韻跤句」（第2或第4句）。嚴格遵照周定邦老師唸歌實務格律：「降的不用（嚴禁第 2、3、4 聲），1、5最好最圓順」。尾字必須鎖定在「第 1 聲（陰平）」或「第 5 聲（陽平）」，以確保唱腔圓轉順暢，絕不墜音。"
            elif role_index == 3:
                if is_stop_rhyme:
                    role_tone_prompt = "- 音律角色：四句聯之「第3句（轉句）」。本段為入聲句押韻，依周定邦老師『4 8 4 8』唸歌專門格律，第3句尾字必須為「第 4 聲（陰入）」。"
                else:
                    role_tone_prompt = "- 音律角色：四句聯之「第3句（轉句）」。依周定邦老師格律採「自由發揮」，不限制聲調與平仄，文意順暢即可，若有入同部韻視為加分。"
            else:
                if is_stop_rhyme:
                    role_tone_prompt = "- 音律角色：四句聯之「第1句（起句）」。本段為入聲句押韻，依周定邦老師『4 8 4 8』唸歌專門格律，第1句尾字必須為「第 4 聲（陰入）」。"
                else:
                    role_tone_prompt = "- 音律角色：四句聯之「第1句（起句）」。依周定邦老師格律採「自由發揮」，不限制聲調與平仄，若有入同部韻視為加分。"

            prompt = f"""你是一位精通台語流行歌與傳統歌謠的填詞專家。
請針對這行台語歌詞提供詩意、道地且嚴格合律的改寫建議：
- 前一句：{prev_line}
- 當前句：{current_line}
- 後一句：{next_line}
- 目標押韻部：{target_rhyme_group} ({result.get('group_desc')})
- 歌曲風格：{style}
{role_tone_prompt}

請提供：
1. 3 種不同情感層次（如深刻悲切、溫柔釋懷、大器滄桑）的整句改寫，末字必須精準符合 {target_rhyme_group} 韻部與上述指定之周定邦老師格律聲調。
2. 標註改寫句的台羅拼音、聲調數字與韻腳字。
3. 簡述文意與前後句的銜接理由。
請用繁體中文與標準台灣教育部推薦用字回覆。"""
            ai_text = asyncio.run(service.call_gemini_ai(prompt, api_key=api_key))
            result['gemini_suggestions'] = ai_text
            
        return json_response(result)
    except Exception as e:
        return json_response({'error': str(e)}, status=500)

@app.route('/api/dictionary', method=['GET'])
def query_dictionary_api():
    try:
        # 使用 getunicode 獲取 utf-8 query param 解決中文詞性與關鍵字亂碼
        rhyme_group = request.query.getunicode('rhyme_group') or None
        tone_str = request.query.getunicode('tone')
        tone = None
        if tone_str:
            clean_tones = [int(t) for t in re.split(r'[,.\s]+', tone_str.strip()) if t.isdigit()]
            if len(clean_tones) == 1:
                tone = clean_tones[0]
            elif len(clean_tones) > 1:
                tone = clean_tones
        char_count_str = request.query.getunicode('char_count')
        char_count = int(char_count_str) if char_count_str and char_count_str.isdigit() else None
        pos = request.query.getunicode('pos') or None
        keyword = request.query.getunicode('keyword') or None
        limit = int(request.query.get('limit', 40))
        offset = int(request.query.get('offset', 0))
        
        result = service.search_dictionary(
            rhyme_group=rhyme_group,
            tone=tone,
            char_count=char_count,
            pos=pos,
            keyword=keyword,
            limit=limit,
            offset=offset
        )
        return json_response(result)
    except Exception as e:
        return json_response({'error': str(e)}, status=500)

@app.route('/api/char_info', method=['GET'])
def query_char_info():
    try:
        char = request.query.getunicode('char', '')
        results = service.lookup_char(char)
        if not results:
            results = service.lookup_word(char)
        return json_response({'results': results})
    except Exception as e:
        return json_response({'error': str(e)}, status=500)

# ==========================================
# 歌仔冊參考文庫與主題匯入 API (Kua-á-tsheh API)
# ==========================================
@app.route('/api/kua_a_tsheh', method=['GET'])
def get_kua_a_tsheh_list_api():
    try:
        theme = request.query.getunicode('theme') or None
        keyword = request.query.getunicode('keyword') or None
        rhyme_group = request.query.getunicode('rhyme_group') or None
        limit = int(request.query.get('limit', 50))
        offset = int(request.query.get('offset', 0))
        res = service.get_kua_a_tsheh_list(theme=theme, keyword=keyword, rhyme_group=rhyme_group, limit=limit, offset=offset)
        return json_response(res)
    except Exception as e:
        return json_response({'error': str(e)}, status=500)

@app.route('/api/kua_a_tsheh/<doc_id:int>', method=['GET'])
def get_kua_a_tsheh_detail_api(doc_id):
    try:
        res = service.get_kua_a_tsheh_detail(doc_id)
        if not res:
            return json_response({'error': '查無此歌仔冊文章'}, status=404)
        return json_response(res)
    except Exception as e:
        return json_response({'error': str(e)}, status=500)

@app.route('/api/kua_a_tsheh', method=['POST'])
def import_kua_a_tsheh_api():
    try:
        data = request.json or {}
        title = data.get('title', '')
        theme = data.get('theme', '未分類')
        author = data.get('author', '')
        description = data.get('description', '')
        raw_content = data.get('raw_content') or data.get('content') or ''
        
        if not title.strip() or not raw_content.strip():
            return json_response({'error': '文章標題與內容皆為必填'}, status=400)
            
        res = service.import_kua_a_tsheh(
            title=title,
            theme=theme,
            author=author,
            description=description,
            raw_content=raw_content
        )
        return json_response({"success": True, "doc": res, **res}, status=201)
    except Exception as e:
        return json_response({'error': str(e)}, status=500)

@app.route('/api/kua_a_tsheh/<doc_id:int>', method=['DELETE'])
def delete_kua_a_tsheh_api(doc_id):
    try:
        success = service.delete_kua_a_tsheh(doc_id)
        return json_response({'success': success, 'id': doc_id})
    except Exception as e:
        return json_response({'error': str(e)}, status=500)

@app.route('/api/kua_a_tsheh/references', method=['GET'])
def get_kua_a_tsheh_references_api():
    try:
        rhyme_group = request.query.getunicode('rhyme_group') or None
        theme = request.query.getunicode('theme') or None
        keyword = request.query.getunicode('keyword') or None
        limit = int(request.query.get('limit', 5))
        res = service.find_kua_a_tsheh_references(rhyme_group=rhyme_group, theme=theme, keyword=keyword, limit=limit)
        return json_response({'references': res})
    except Exception as e:
        return json_response({'error': str(e)}, status=500)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8899))
    host = os.environ.get('HOST', '0.0.0.0')
    print(f"啟動台語韻腳與寫歌創作工作台：http://{host}:{port}")
    run(app, host=host, port=port, reloader=False, quiet=False)
