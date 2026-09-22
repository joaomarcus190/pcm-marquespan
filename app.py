from flask import Flask, jsonify, request, send_from_directory, session
import json, os, secrets, threading, sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
USE_PG = bool(DATABASE_URL)
DB = os.path.join(BASE, 'pcm.db')
app = Flask(__name__, static_folder=BASE)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=bool(os.getenv('RENDER')))
lock = threading.Lock()


def pg_conn():
    import psycopg
    return psycopg.connect(DATABASE_URL, sslmode='require' if 'localhost' not in DATABASE_URL else 'disable')


def init_db():
    if USE_PG:
        with pg_conn() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS pcm_state (id INTEGER PRIMARY KEY, payload JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')
            c.execute('''CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, name TEXT NOT NULL, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'Técnico')''')
            c.execute("SELECT 1 FROM pcm_state WHERE id=1")
            if c.fetchone() is None:
                c.execute("INSERT INTO pcm_state(id,payload) VALUES(1,%s)", (json.dumps({'eq': [], 'prev': [], 'os': []}),))
            c.execute('SELECT 1 FROM users LIMIT 1')
            if c.fetchone() is None:
                admin_pw = os.getenv('ADMIN_PASSWORD', 'admin123')
                tech_pw = os.getenv('TECH_PASSWORD', 'equipe123')
                c.execute('INSERT INTO users(name,username,password,role) VALUES(%s,%s,%s,%s)', ('Administrador PCM','admin',generate_password_hash(admin_pw),'PCM'))
                c.execute('INSERT INTO users(name,username,password,role) VALUES(%s,%s,%s,%s)', ('Equipe Manutenção','equipe',generate_password_hash(tech_pw),'Técnico'))
    else:
        with sqlite3.connect(DB) as c:
            c.row_factory = sqlite3.Row
            c.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, username TEXT UNIQUE, password TEXT, role TEXT)')
            if c.execute('SELECT 1 FROM state WHERE id=1').fetchone() is None:
                c.execute('INSERT INTO state(id,payload) VALUES(1,?)',(json.dumps({'eq':[],'prev':[],'os':[]}),))
            if c.execute('SELECT 1 FROM users').fetchone() is None:
                c.execute('INSERT INTO users(name,username,password,role) VALUES(?,?,?,?)',('Administrador PCM','admin',generate_password_hash(os.getenv('ADMIN_PASSWORD','admin123')),'PCM'))
                c.execute('INSERT INTO users(name,username,password,role) VALUES(?,?,?,?)',('Equipe Manutenção','equipe',generate_password_hash(os.getenv('TECH_PASSWORD','equipe123')),'Técnico'))


def current_user():
    uid = session.get('uid')
    if not uid:
        return None
    if USE_PG:
        with pg_conn() as c:
            c.execute('SELECT id,name,username,role FROM users WHERE id=%s', (uid,))
            return c.fetchone()
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        return c.execute('SELECT id,name,username,role FROM users WHERE id=?',(uid,)).fetchone()


def auth(required=True):
    u = current_user()
    if required and not u:
        return None, (jsonify(error='Não autenticado'), 401)
    return u, None


def row_user(row):
    if row is None: return None
    if isinstance(row, dict): return row
    return dict(row) if hasattr(row, 'keys') else {'id': row[0], 'name': row[1], 'username': row[2], 'role': row[3]}


def read_data():
    if USE_PG:
        with pg_conn() as c:
            c.execute('SELECT payload FROM pcm_state WHERE id=1')
            r = c.fetchone()
            return r[0] if r else {'eq': [], 'prev': [], 'os': []}
    with sqlite3.connect(DB) as c:
        c.row_factory = sqlite3.Row
        return json.loads(c.execute('SELECT payload FROM state WHERE id=1').fetchone()['payload'])


def write_data(payload):
    if USE_PG:
        with pg_conn() as c:
            c.execute('UPDATE pcm_state SET payload=%s, updated_at=NOW() WHERE id=1', (json.dumps(payload, ensure_ascii=False),))
    else:
        with sqlite3.connect(DB) as c:
            c.execute('UPDATE state SET payload=? WHERE id=1',(json.dumps(payload,ensure_ascii=False),))


@app.get('/')
def index(): return send_from_directory(BASE, 'index.html')

@app.get('/healthz')
def healthz(): return jsonify(status='ok', database='postgresql' if USE_PG else 'sqlite')

@app.post('/api/login')
def login():
    body = request.get_json() or {}
    username, password = body.get('username','').strip(), body.get('password','')
    if USE_PG:
        with pg_conn() as c:
            c.execute('SELECT id,name,username,password,role FROM users WHERE username=%s', (username,))
            u = c.fetchone()
            if not u or not check_password_hash(u[3], password): return jsonify(error='Usuário ou senha inválidos'), 401
            session['uid'] = u[0]
            return jsonify(id=u[0],name=u[1],username=u[2],role=u[4])
    with sqlite3.connect(DB) as c:
        u = c.execute('SELECT id,name,username,password,role FROM users WHERE username=?',(username,)).fetchone()
    if not u or not check_password_hash(u[3], password): return jsonify(error='Usuário ou senha inválidos'), 401
    session['uid'] = u[0]
    return jsonify(id=u[0],name=u[1],username=u[2],role=u[4])

@app.post('/api/logout')
def logout(): session.clear(); return jsonify(ok=True)

@app.get('/api/me')
def me():
    u,_ = auth(False)
    return (jsonify(row_user(u)) if u else jsonify(authenticated=False)), (200 if u else 401)

@app.get('/api/users')
def users():
    u,e=auth()
    if e:return e
    if USE_PG:
        with pg_conn() as c:
            c.execute('SELECT id,name,username,role FROM users ORDER BY name')
            return jsonify([row_user(x) for x in c.fetchall()])
    with sqlite3.connect(DB) as c:
        c.row_factory=sqlite3.Row
        return jsonify([dict(x) for x in c.execute('SELECT id,name,username,role FROM users ORDER BY name')])

@app.post('/api/users')
def add_user():
    u,e=auth()
    if e:return e
    if row_user(u)['role']!='PCM':return jsonify(error='Apenas PCM pode criar usuários'),403
    b=request.get_json() or {}
    name,username,password,role=b.get('name','').strip(),b.get('username','').strip(),b.get('password',''),b.get('role','Técnico')
    if not name or not username or not password:return jsonify(error='Nome, usuário e senha são obrigatórios'),400
    try:
        if USE_PG:
            with pg_conn() as c:c.execute('INSERT INTO users(name,username,password,role) VALUES(%s,%s,%s,%s)',(name,username,generate_password_hash(password),role))
        else:
            with sqlite3.connect(DB) as c:c.execute('INSERT INTO users(name,username,password,role) VALUES(?,?,?,?)',(name,username,generate_password_hash(password),role))
        return jsonify(ok=True)
    except Exception:
        return jsonify(error='Usuário já existe ou dados inválidos'),400

@app.get('/api/data')
def get_data():
    u,e=auth()
    if e:return e
    return jsonify(read_data())

@app.put('/api/data')
def put_data():
    u,e=auth()
    if e:return e
    if row_user(u)['role']!='PCM':return jsonify(error='Somente PCM pode salvar alterações estruturais'),403
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict) or not all(k in payload for k in ('eq','prev','os')):return jsonify(error='Formato inválido'),400
    with lock: write_data(payload)
    return jsonify(ok=True)

@app.post('/api/action')
def action():
    u,e=auth()
    if e:return e
    b=request.get_json() or {}
    kind,rid,status,note=b.get('kind'),b.get('id'),b.get('status'),b.get('note','')
    if kind not in ('os','prev') or rid is None or status not in ('Aberta','Em execução','Concluída','Pendente'):
        return jsonify(error='Dados inválidos'),400
    with lock:
        payload=read_data(); item=next((x for x in payload.get(kind,[]) if str(x.get('id'))==str(rid)),None)
        if not item:return jsonify(error='Registro não encontrado'),404
        item['status']=status
        if note:item['observacao']=note
        item['atualizado_por']=row_user(u)['name']
        write_data(payload)
    return jsonify(ok=True)

init_db()

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT',5000)),debug=False)
