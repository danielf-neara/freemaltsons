from flask import Flask, jsonify, request, send_from_directory
import json, os, re, requests
from bs4 import BeautifulSoup
from datetime import date

app = Flask(__name__, static_folder='static')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'data', 'sessions.json')
LIBRARY_FILE = os.path.join(BASE_DIR, 'data', 'whisky-library.json')

def load_library():
    try:
        with open(LIBRARY_FILE) as f:
            return json.load(f)
    except Exception:
        return []

ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']

# Normalise host names that have been inconsistently entered
HOST_ALIASES = {
    'brass': 'Braas',
    'braas': 'Braas',
    'willie': 'Joess',
    'willie ': 'Joess',
    'fiddy ': 'Fiddy',
    'joess': 'Joess',
}


DM_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-AU,en;q=0.9',
}


def _fetch_dm_products(query):
    """Fetch raw product list from Dan Murphy's search page. Returns list of product dicts."""
    url = f"https://www.danmurphys.com.au/search?searchTerm={requests.utils.quote(query)}"
    try:
        resp = requests.get(url, headers=DM_HEADERS, timeout=10)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, 'html.parser')
        script = soup.find('script', id='__NEXT_DATA__')
        if script:
            data = json.loads(script.string)
            return (data.get('props', {}).get('pageProps', {})
                        .get('searchResults', {}).get('products', []))
    except Exception:
        pass
    return []


def search_dan_murphys(query, limit=8):
    """Search Dan Murphy's, return list of {whisky, dm_url, rrp, image_url}."""
    products = _fetch_dm_products(query)
    results = []
    for p in products[:limit]:
        name = p.get('name', '').strip()
        if not name:
            continue
        results.append({
            'whisky': name,
            'dm_url': 'https://www.danmurphys.com.au' + p.get('url', ''),
            'rrp': p.get('price', {}).get('current'),
            'image_url': (p.get('images') or [{}])[0].get('url'),
            'region': '',
            'source': 'dm',
        })
    return results


def lookup_dan_murphys(query):
    """Search Dan Murphy's, return {dm_url, price, image_url} for the top result, or None."""
    products = _fetch_dm_products(query)
    if not products:
        return None
    p = products[0]
    return {
        'dm_url': 'https://www.danmurphys.com.au' + p.get('url', ''),
        'price': p.get('price', {}).get('current'),
        'image_url': (p.get('images') or [{}])[0].get('url'),
    }


def normalise_host(name):
    if not name:
        return name
    return HOST_ALIASES.get(name.strip().lower(), name.strip())


def roman_to_int(r):
    return ROMAN.index(r) + 1 if r in ROMAN else 0


def int_to_roman(n):
    return ROMAN[n - 1] if 1 <= n <= len(ROMAN) else str(n)


def load_data():
    with open(DATA_FILE) as f:
        data = json.load(f)
    # Normalise host names on load
    for s in data['sessions']:
        s['host'] = normalise_host(s.get('host'))
    return data


def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def compute_next_id(sessions):
    valid = [s for s in sessions if s.get('id') and ':' in (s.get('id') or '')]
    if not valid:
        return 'I:I'
    last = valid[-1]['id']
    parts = last.split(':')
    if len(parts) != 2:
        return 'I:I'
    r, s = parts
    ri, si = roman_to_int(r), roman_to_int(s)
    if ri == 0 or si == 0:
        return 'I:I'
    # Assume current round size of 7 (original 6 + Willie)
    members_per_round = 7
    if si >= members_per_round:
        return f"{int_to_roman(ri + 1)}:I"
    return f"{r}:{int_to_roman(si + 1)}"


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/data')
def get_data():
    data = load_data()
    # Filter out sessions with no meaningful data
    data['sessions'] = [
        s for s in data['sessions']
        if s.get('whisky') or s.get('host')
    ]
    return jsonify(data)


@app.route('/api/sessions', methods=['POST'])
def add_session():
    data = load_data()
    session = request.json
    session['host'] = normalise_host(session.get('host'))
    if not session.get('id'):
        session['id'] = compute_next_id(data['sessions'])
    data['sessions'].append(session)
    # Sort sessions by round then ordinal
    def sort_key(s):
        sid = s.get('id') or ''
        if ':' in sid:
            parts = sid.split(':')
            return (roman_to_int(parts[0]), roman_to_int(parts[1]))
        return (999, 999)
    data['sessions'].sort(key=sort_key)
    save_data(data)
    return jsonify({'success': True, 'session': session})


@app.route('/api/sessions/<session_id>', methods=['PUT'])
def update_session(session_id):
    data = load_data()
    updates = request.json or {}
    for i, s in enumerate(data['sessions']):
        if s.get('id') == session_id:
            s.update(updates)
            save_data(data)
            return jsonify({'success': True, 'session': s})
    return jsonify({'error': 'Session not found'}), 404


@app.route('/api/next-session')
def next_session():
    data = load_data()
    next_id = compute_next_id(data['sessions'])
    # Use static members list (preserving order), falling back to deriving from session history
    hosts = data.get('members') or sorted({normalise_host(s['host']) for s in data['sessions'] if s.get('host')})
    return jsonify({
        'id': next_id,
        'date': date.today().isoformat(),
        'hosts': hosts,
    })


@app.route('/api/search-whisky')
def search_whisky():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify([])

    data = load_data()

    ql = q.lower()

    # Local results first (previous sessions)
    seen = set()
    results = []
    for s in data['sessions']:
        whisky = s.get('whisky') or ''
        if ql in whisky.lower() and whisky.lower() not in seen:
            seen.add(whisky.lower())
            results.append({
                'whisky': whisky,
                'region': s.get('region', ''),
                'rrp': s.get('rrp'),
                'image_url': s.get('image_url'),
                'source': 'local',
            })

    # Library results to fill remaining slots
    library = load_library()
    for entry in library:
        whisky = entry.get('whisky', '')
        if ql in whisky.lower() and whisky.lower() not in seen:
            seen.add(whisky.lower())
            results.append({
                'whisky': whisky,
                'region': entry.get('region', ''),
                'type': entry.get('type', ''),
                'rrp': None,
                'image_url': None,
                'source': 'library',
            })

    return jsonify(results[:10])


@app.route('/api/image-search-url')
def image_search_url():
    """Return a Google Images search URL for the user to open and find a bottle image."""
    name = request.args.get('name', '').strip()
    if not name:
        return jsonify({'url': None})
    query = requests.utils.quote(f"{name} whisky bottle")
    url = f"https://www.google.com/search?q={query}&tbm=isch"
    return jsonify({'url': url})


@app.route('/api/lookup-product')
def lookup_product():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'error': 'No query provided'})
    result = lookup_dan_murphys(q)
    if result:
        return jsonify(result)
    return jsonify({'error': 'Not found'})


@app.route('/api/enrich-all', methods=['POST'])
def enrich_all():
    data = load_data()
    enriched = 0
    failed = 0
    for s in data['sessions']:
        if not s.get('whisky'):
            continue
        if s.get('image_url') and s.get('rrp') and s.get('dm_url'):
            continue
        result = lookup_dan_murphys(s['whisky'])
        if result:
            if not s.get('image_url') and result.get('image_url'):
                s['image_url'] = result['image_url']
            if not s.get('rrp') and result.get('price'):
                s['rrp'] = result['price']
            if result.get('dm_url'):
                s['dm_url'] = result['dm_url']
            enriched += 1
        else:
            failed += 1
    save_data(data)
    return jsonify({'enriched': enriched, 'failed': failed})


if __name__ == '__main__':
    print("=" * 50)
    print("  Freemaltson's Whisky Nights")
    print("  Open http://localhost:5001 in your browser")
    print("=" * 50)
    app.run(debug=False, port=5001)
