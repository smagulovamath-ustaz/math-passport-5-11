import os,json,sqlite3,secrets,hashlib,hmac,threading,re
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
DB=Path(os.environ.get('DATABASE_PATH',str(ROOT/'results.sqlite3')))
PASSWORD=os.environ.get('TEACHER_PASSWORD','')
if not PASSWORD: raise SystemExit('Set TEACHER_PASSWORD before starting server (see README).')
SESSIONS=set(); LOCK=threading.Lock()
def db():
 c=sqlite3.connect(DB,timeout=15)
 c.execute('CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL, created_at TEXT NOT NULL)')
 return c
with db() as c: pass
class Handler(BaseHTTPRequestHandler):
 def send(self,code,data,ctype='application/json; charset=utf-8',headers=None):
  raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
  self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
  for k,v in (headers or {}).items():self.send_header(k,v)
  self.end_headers();self.wfile.write(raw)
 def auth(self):
  ck=SimpleCookie()
  try:ck.load(self.headers.get('Cookie',''))
  except Exception:return False
  token=ck.get('teacher_session')
  return bool(token and token.value in SESSIONS)
 def body(self):
  n=int(self.headers.get('Content-Length','0'))
  if n>65536:raise ValueError('Payload too large')
  return json.loads(self.rfile.read(n))
 def do_GET(self):
  path=self.path.split('?')[0]
  if path in ('/','/index.html'):
   return self.send(200,(ROOT/'index.html').read_bytes(),'text/html; charset=utf-8')
  if path in ('/passport_questions.json','/diagnostic_questions.json','/literacy_questions.json'):
   filename=path.lstrip('/')
   try:return self.send(200,(ROOT/filename).read_bytes(),'application/json; charset=utf-8')
   except FileNotFoundError:return self.send(404,{'error':'Question bank not found'})
  if path=='/api/health':return self.send(200,{'ok':True})
  if path=='/api/results':
   if not self.auth():return self.send(401,{'error':'Login required'})
   with LOCK,db() as c:rows=[json.loads(r[0]) for r in c.execute('SELECT data FROM results ORDER BY id').fetchall()]
   return self.send(200,rows)
  self.send(404,{'error':'Not found'})
 def do_POST(self):
  try:data=self.body()
  except Exception:return self.send(400,{'error':'Invalid JSON'})
  path=self.path.split('?')[0]
  if path=='/api/login':
   if not isinstance(data,dict) or not hmac.compare_digest(str(data.get('password','')),PASSWORD):return self.send(401,{'error':'Құпиясөз қате'})
   token=secrets.token_urlsafe(32);SESSIONS.add(token)
   return self.send(200,{'ok':True},headers={'Set-Cookie':f'teacher_session={token}; HttpOnly; SameSite=Strict; Path=/'+('; Secure' if os.environ.get('HTTPS')=='1' else '')})
  if path=='/api/logout':
   ck=SimpleCookie();ck.load(self.headers.get('Cookie',''));t=ck.get('teacher_session')
   if t:SESSIONS.discard(t.value)
   return self.send(200,{'ok':True},headers={'Set-Cookie':'teacher_session=; HttpOnly; Max-Age=0; Path=/'})
  if path=='/api/results':
   if not isinstance(data,dict):return self.send(400,{'error':'Invalid record'})
   if not isinstance(data.get('name'),str) or not 1<=len(data['name'].strip())<=100:return self.send(400,{'error':'Invalid name'})
   if str(data.get('grade')) not in [str(x) for x in range(5,12)]:return self.send(400,{'error':'Invalid grade'})
   if data.get('course') not in ('diagnostic','literacy','passport'):return self.send(400,{'error':'Invalid course'})
   if data.get('course')=='passport' and str(data['grade'])!='11':return self.send(400,{'error':'Invalid grade'})
   if not isinstance(data.get('score'),int) or not isinstance(data.get('total'),int) or not 0<=data['score']<=data['total']<=1000:return self.send(400,{'error':'Invalid score'})
   if not isinstance(data.get('classLetter'),str) or not 1<=len(data['classLetter'])<=5:return self.send(400,{'error':'Invalid class letter'})
   if not re.fullmatch(r'20\d{2}[–-]20\d{2}',str(data.get('schoolYear',''))):return self.send(400,{'error':'Invalid school year'})
   data={k:data[k] for k in ('name','grade','course','score','total','level','topic','weak','details','date','classLetter','schoolYear') if k in data}
   data['received_at']=datetime.now(timezone.utc).isoformat()
   with LOCK,db() as c:c.execute('INSERT INTO results(data,created_at) VALUES (?,?)',(json.dumps(data,ensure_ascii=False),data['received_at']))
   return self.send(201,{'ok':True})
  self.send(404,{'error':'Not found'})
if __name__=='__main__':
 host=os.environ.get('HOST','0.0.0.0');port=int(os.environ.get('PORT','8766'))
 print(f'Math Passport server: http://localhost:{port}/',flush=True)
 ThreadingHTTPServer((host,port),Handler).serve_forever()
