# 밸류X 기업 크롤러 서버
# 파일명: crawler_server.py
# 실행: python crawler_server.py

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import time
import random
import re
import json

app = Flask(__name__)
CORS(app)  # CRM에서 호출 허용

# 공통 헤더 (봇 감지 우회)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ko-KR,ko;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def clean_phone(text):
    """전화번호 정규화"""
    match = re.search(r'0\d{1,2}-\d{3,4}-\d{4}', text or '')
    return match.group() if match else ''

def random_delay():
    """서버 부하 방지 딜레이"""
    time.sleep(random.uniform(0.8, 2.0))


# ─────────────────────────────────────────
# 1. 공공데이터포털 중소기업현황 API
# ─────────────────────────────────────────
@app.route('/api/crawl/public', methods=['GET'])
def crawl_public_api():
    """
    공공데이터포털 중소기업현황정보 API
    API 키 발급: https://www.data.go.kr/data/15043671/openapi.do
    """
    api_key   = request.args.get('api_key', '')
    industry  = request.args.get('industry', '')   # 업종코드 (C=제조, J=IT 등)
    region    = request.args.get('region', '')      # 지역코드 (11=서울 등)
    page_size = request.args.get('size', '20')

    if not api_key:
        return jsonify({'error': 'API 키가 필요합니다. data.go.kr에서 발급받으세요.'}), 400

    url = 'https://apis.data.go.kr/1160100/service/GetCorpBasicInfoService_V2/getCorpOutline_V2'
    params = {
        'serviceKey': api_key,
        'pageNo': 1,
        'numOfRows': page_size,
        'resultType': 'json',
        'indutyCode': industry,
        'sigunguCode': region,
    }

    try:
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])

        results = []
        for item in items:
            results.append({
                'company': item.get('corpNm', ''),
                'ceo':     item.get('repNm', ''),
                'phone':   item.get('telno', ''),
                'address': item.get('adres', ''),
                'industry': item.get('indutyNm', ''),
                'founded': item.get('enpFnddDt', ''),
                'source':  '공공API',
            })

        return jsonify({'count': len(results), 'results': results})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# 2. 대한상공회의소 회원사 크롤링
# ─────────────────────────────────────────
@app.route('/api/crawl/korchambiz', methods=['GET'])
def crawl_korchambiz():
    """
    대한상공회의소 기업정보 (korchambiz.net)
    """
    industry = request.args.get('industry', '제조업')
    region   = request.args.get('region', '서울')
    count    = int(request.args.get('count', '20'))

    region_map = {
        '서울': '1100', '경기': '4100', '인천': '2800',
        '부산': '2600', '대구': '2700', '광주': '2900', '대전': '3000'
    }
    region_code = region_map.get(region, '1100')

    results = []
    page = 1

    while len(results) < count:
        url = f'https://www.korchambiz.net/member/memberSearch.do'
        params = {
            'searchGubun': '1',
            'searchIndCls': industry,
            'searchSido': region_code,
            'pageIndex': page,
        }

        try:
            res = requests.get(url, params=params, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table.list tbody tr')

            if not rows:
                break

            for row in rows:
                cols = row.select('td')
                if len(cols) < 4:
                    continue

                company = cols[0].get_text(strip=True)
                ceo     = cols[1].get_text(strip=True)
                phone   = cols[2].get_text(strip=True)
                address = cols[3].get_text(strip=True)

                if company:
                    results.append({
                        'company':  company,
                        'ceo':      ceo,
                        'phone':    clean_phone(phone),
                        'address':  address,
                        'industry': industry,
                        'region':   region,
                        'source':   '대한상공회의소',
                    })

                if len(results) >= count:
                    break

            page += 1
            random_delay()

        except Exception as e:
            return jsonify({'error': str(e), 'partial': results}), 500

    return jsonify({'count': len(results), 'results': results[:count]})


# ─────────────────────────────────────────
# 3. 중소벤처기업부 기업정보 크롤링
# ─────────────────────────────────────────
@app.route('/api/crawl/mss', methods=['GET'])
def crawl_mss():
    """
    중소벤처기업부 기업확인서비스 (sminfo.mss.go.kr)
    """
    industry = request.args.get('industry', '')
    region   = request.args.get('region', '')
    count    = int(request.args.get('count', '20'))

    url = 'https://sminfo.mss.go.kr/cm/CM0030L.do'
    params = {
        'indutyClsCode': industry,
        'sidoCode': region,
        'pageUnit': count,
        'pageIndex': 1,
    }

    results = []
    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('.board_list tbody tr')

        for row in rows:
            cols = row.select('td')
            if len(cols) < 3:
                continue
            results.append({
                'company':  cols[0].get_text(strip=True),
                'industry': cols[1].get_text(strip=True) or industry,
                'region':   cols[2].get_text(strip=True) or region,
                'source':   '중소벤처기업부',
            })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'count': len(results), 'results': results})


# ─────────────────────────────────────────
# 4. 네이버 플레이스 크롤링
# ─────────────────────────────────────────
@app.route('/api/crawl/naver', methods=['GET'])
def crawl_naver():
    """
    네이버 플레이스 지역 기업 검색
    """
    keyword = request.args.get('keyword', '')
    region  = request.args.get('region', '서울')
    count   = int(request.args.get('count', '20'))

    if not keyword:
        return jsonify({'error': '검색어를 입력해주세요.'}), 400

    query   = f'{region} {keyword}'
    results = []

    # 네이버 지역 검색 API (Naver Developers 키 필요)
    naver_client_id     = 'YOUR_NAVER_CLIENT_ID'      # developers.naver.com 에서 발급
    naver_client_secret = 'YOUR_NAVER_CLIENT_SECRET'

    headers = {
        'X-Naver-Client-Id':     naver_client_id,
        'X-Naver-Client-Secret': naver_client_secret,
    }

    url = 'https://openapi.naver.com/v1/search/local.json'
    params = {
        'query':   query,
        'display': min(count, 5),
        'start':   1,
        'sort':    'random',
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()
        items = data.get('items', [])

        for item in items:
            name    = re.sub('<[^>]+>', '', item.get('title', ''))
            address = item.get('address', '')
            phone   = item.get('telephone', '')
            category= item.get('category', '')

            results.append({
                'company':  name,
                'phone':    clean_phone(phone) or phone,
                'address':  address,
                'industry': category,
                'source':   '네이버 플레이스',
            })

    except Exception as e:
        return jsonify({'error': f'네이버 API 키를 설정해주세요: {e}'}), 500

    return jsonify({'count': len(results), 'results': results})


# ─────────────────────────────────────────
# 5. 기업 홈페이지 연락처 자동 추출
# ─────────────────────────────────────────
@app.route('/api/crawl/extract', methods=['POST'])
def extract_from_url():
    """
    URL 입력 → 기업 연락처 자동 추출
    """
    data = request.json or {}
    url  = data.get('url', '')

    if not url:
        return jsonify({'error': 'URL을 입력해주세요.'}), 400

    try:
        res  = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        # 전화번호 추출
        text   = soup.get_text()
        phones = re.findall(r'0\d{1,2}-\d{3,4}-\d{4}', text)
        phones = list(set(phones))[:5]

        # 이메일 추출
        emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', text)
        emails = list(set(emails))[:3]

        # 회사명 추출 (title 태그)
        title = soup.find('title')
        company = title.get_text(strip=True) if title else ''

        # 대표자명 추출
        ceo_match = re.search(r'대표\s*[:|：]?\s*([가-힣]{2,4})', text)
        ceo = ceo_match.group(1) if ceo_match else ''

        # 주소 추출
        addr_match = re.search(r'(서울|경기|인천|부산|대구|광주|대전|울산)[^\n]{5,50}(로|길|동|구)\s*\d+', text)
        address = addr_match.group() if addr_match else ''

        return jsonify({
            'company': company,
            'ceo':     ceo,
            'phones':  phones,
            'emails':  emails,
            'address': address,
            'url':     url,
            'source':  'URL 추출',
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# 6. 텍스트 일괄 파싱
# ─────────────────────────────────────────
@app.route('/api/crawl/parse-text', methods=['POST'])
def parse_text():
    """
    자유 형식 텍스트에서 기업 정보 추출
    """
    data = request.json or {}
    text = data.get('text', '')

    if not text:
        return jsonify({'error': '텍스트를 입력해주세요.'}), 400

    lines   = text.strip().split('\n')
    results = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        phone_match = re.search(r'(0\d{1,2}-\d{3,4}-\d{4})', line)
        if not phone_match:
            continue

        phone = phone_match.group(1)

        # 이메일
        email_match = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', line)
        email = email_match.group() if email_match else ''

        # 업종 감지
        industry_map = {
            '제조': '제조업', 'IT': 'IT/소프트웨어', '소프트': 'IT/소프트웨어',
            '개발': 'IT/소프트웨어', '건설': '건설업', '도매': '도·소매업',
            '소매': '도·소매업', '유통': '도·소매업', '수출': '수출·무역',
            '무역': '수출·무역', '음식': '음식·숙박업', '숙박': '음식·숙박업',
        }
        industry = '기타'
        for key, val in industry_map.items():
            if key in line:
                industry = val
                break

        # 회사명/대표명 추출
        cleaned = re.sub(r'(0\d{1,2}-\d{3,4}-\d{4})', '', line)
        cleaned = re.sub(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', '', cleaned)
        words   = [w for w in cleaned.split() if len(w) >= 2]

        company = words[0] if words else '미확인'
        ceo     = words[1] if len(words) > 1 else ''

        results.append({
            'company':  company,
            'ceo':      ceo,
            'phone':    phone,
            'email':    email,
            'industry': industry,
            'source':   '텍스트 파싱',
        })

    return jsonify({'count': len(results), 'results': results})


# ─────────────────────────────────────────
# 서버 실행
# ─────────────────────────────────────────
if __name__ == '__main__':
    print('=' * 50)
    print('밸류X 기업 크롤러 서버 시작')
    print('주소: http://localhost:5001')
    print('=' * 50)
    print('사용 가능한 엔드포인트:')
    print('  GET  /api/crawl/public      공공데이터 API')
    print('  GET  /api/crawl/korchambiz  대한상공회의소')
    print('  GET  /api/crawl/mss         중소벤처기업부')
    print('  GET  /api/crawl/naver       네이버 플레이스')
    print('  POST /api/crawl/extract     URL 연락처 추출')
    print('  POST /api/crawl/parse-text  텍스트 파싱')
    print('=' * 50)
    app.run(host='0.0.0.0', port=5001, debug=True)