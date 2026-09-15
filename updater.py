import argparse, hashlib, json, os, shutil, tempfile, urllib.request, zipfile
from pathlib import Path

APP_DIR=Path(__file__).resolve().parent
VERSION_FILE=APP_DIR/'version.json'; PACKAGED_CONFIG=APP_DIR/'update_config.json'
LOCALAPPDATA=Path(os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or Path.home())
STATE_DIR=LOCALAPPDATA/'SmishiesLab'; STATE_DIR.mkdir(parents=True,exist_ok=True)
USER_CONFIG=STATE_DIR/'update_config.json'; LOG_FILE=STATE_DIR/'updater.log'

def log(msg):
    line=f'[Smishies Updater] {msg}'; print(line)
    try:
        with LOG_FILE.open('a',encoding='utf-8') as f:f.write(line+'\n')
    except Exception:pass

def load_json(path,default=None):
    try:return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except Exception:return {} if default is None else default

def save_json(path,data):Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

def get_config():
    base=load_json(PACKAGED_CONFIG,{})
    if USER_CONFIG.exists():
        user=load_json(USER_CONFIG,{})
        for k,v in user.items():
            if k=='manifest_url' and not str(v or '').strip():continue
            base[k]=v
    else:
        try:save_json(USER_CONFIG,base)
        except Exception:pass
    return base

def version_tuple(v):
    out=[]
    for p in str(v).strip().lstrip('vV').split('.'):
        try:out.append(int(p))
        except:out.append(0)
    return tuple(out)

def current_version():return str(load_json(VERSION_FILE,{}).get('version','0'))
def request(url):return urllib.request.Request(url,headers={'User-Agent':'SmishiesLab-Updater/2.1','Cache-Control':'no-cache'})
def fetch_json(url,timeout=12):
    with urllib.request.urlopen(request(url),timeout=timeout) as r:return json.loads(r.read().decode('utf-8'))
def download(url,dest,timeout=60):
    with urllib.request.urlopen(request(url),timeout=timeout) as r,open(dest,'wb') as f:shutil.copyfileobj(r,f)
def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest().lower()

def backup_file(rel):
    src=APP_DIR/rel
    if not src.exists():return
    dst=STATE_DIR/'backup_before_update'/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)

def apply_local_migrations():
    """Small one-time fixes that can be delivered with the updater itself."""
    p=APP_DIR/'server.py'
    try:
        s=p.read_text(encoding='utf-8')
        replacements = {
            "101: {'name':'Health','three':{'hp_pct':0.15},'five':{'hp_pct':0.30},'total':'HP +45%'},":
                "101: {'name':'Attack','three':{'atk_pct':0.10},'five':{'atk_pct':0.20},'total':'ATQ +30%'},",
            "113: {'name':'Paragon','three':{},'five':{},'total':'Heal/Shield +15% + Ally Move SPD','note':'3p: heal/shield +15%; 5p: ally move speed +3m/s'},":
                "113: {'name':'Predator','three':{'atk_pct':0.10},'five':{'crit_dmg':0.40},'total':'ATQ +10% + Crit DMG +40%'},"
        }
        changed=False
        for old,new in replacements.items():
            if old in s:
                s=s.replace(old,new)
                changed=True
        for old_title in ['V10.60 — Optimisation & mises à jour automatiques','V10.57 — Qualité reliques par héros']:
            if old_title in s:s=s.replace(old_title,'V10.62 — Correction sets Cezal'); changed=True
        if changed:
            backup_file('server.py'); p.write_text(s,encoding='utf-8'); log('Correctif local appliqué : set 101 = Attack et set 113 = Predator.')
    except Exception as e:log(f'Correctif local non appliqué ({e}).')

def safe_extract(zip_path,dest):
    dest=Path(dest).resolve()
    with zipfile.ZipFile(zip_path,'r') as z:
        for m in z.infolist():
            target=(dest/m.filename).resolve()
            if not str(target).startswith(str(dest)):raise RuntimeError('Archive de mise à jour invalide')
        z.extractall(dest)

def locate_payload(root):
    root=Path(root)
    if (root/'server.py').exists():return root
    if (root/'Smishies_Lab'/'server.py').exists():return root/'Smishies_Lab'
    matches=list(root.rglob('server.py'))
    if len(matches)==1:return matches[0].parent
    raise RuntimeError('Impossible de trouver server.py dans la mise à jour')

def apply_payload(payload,preserve):
    preserve={p.replace('\\','/').strip('/') for p in preserve}
    backup=STATE_DIR/'backup_before_update'; shutil.rmtree(backup,ignore_errors=True)
    for rel in ['server.py','updater.py','LANCER_SMISHIES_LAB.bat','version.json']:backup_file(rel)
    for src in Path(payload).rglob('*'):
        if not src.is_file():continue
        rel=src.relative_to(payload).as_posix()
        if rel in preserve:continue
        dst=APP_DIR/rel; dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)

def apply_file_manifest(manifest,preserve):
    files=manifest.get('files') or []
    if not files:raise RuntimeError('Manifest sans fichiers')
    preserve={p.replace('\\','/').strip('/') for p in preserve}
    backup=STATE_DIR/'backup_before_update'; shutil.rmtree(backup,ignore_errors=True)
    tmp=Path(tempfile.mkdtemp(prefix='smishies_files_'))
    try:
        staged=[]
        for item in files:
            rel=str(item.get('path') or '').replace('\\','/').strip('/'); url=str(item.get('url') or '').strip()
            if not rel or not url:raise RuntimeError('Entrée fichier invalide')
            dest=tmp/rel; dest.parent.mkdir(parents=True,exist_ok=True); download(url,dest)
            expected=str(item.get('sha256') or '').strip().lower()
            if expected and sha256(dest)!=expected:raise RuntimeError(f'SHA-256 incorrect pour {rel}')
            staged.append((rel,dest))
        for rel,dest in staged:
            if rel in preserve:continue
            backup_file(rel); target=APP_DIR/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(dest,target)
        for rel in manifest.get('delete') or []:
            rel=str(rel).replace('\\','/').strip('/')
            if rel in preserve:continue
            target=APP_DIR/rel
            if target.is_file():backup_file(rel); target.unlink()
    finally:shutil.rmtree(tmp,ignore_errors=True)

def check_and_apply(force=False):
    apply_local_migrations()
    cfg=get_config()
    if not cfg.get('enabled',True):log('Mises à jour automatiques désactivées.'); return 0
    manifest_url=str(cfg.get('manifest_url') or '').strip()
    if not manifest_url:log("Source de mise à jour non configurée. L'application démarre normalement."); return 0
    try:manifest=fetch_json(manifest_url,int(cfg.get('timeout_seconds',12)))
    except Exception as e:log(f'Vérification impossible ({e}). Démarrage de la version installée.'); return 0
    remote=str(manifest.get('version') or '0'); local=current_version()
    if not force and version_tuple(remote)<=version_tuple(local):log(f'À jour : v{local}.'); return 0
    log(f'Nouvelle version v{remote} détectée (installée : v{local}).')
    try:
        if manifest.get('files'):
            log('Téléchargement des fichiers de mise à jour…'); apply_file_manifest(manifest,cfg.get('preserve',[]))
        else:
            url=str(manifest.get('url') or '').strip()
            if not url:raise RuntimeError('URL du package absente')
            tmpdir=Path(tempfile.mkdtemp(prefix='smishies_update_')); zpath=tmpdir/'update.zip'
            try:
                log('Téléchargement de la mise à jour…'); download(url,zpath,60)
                expected=str(manifest.get('sha256') or '').strip().lower()
                if expected and sha256(zpath)!=expected:raise RuntimeError('SHA-256 incorrect : téléchargement refusé')
                extract=tmpdir/'payload'; extract.mkdir(); safe_extract(zpath,extract); apply_payload(locate_payload(extract),cfg.get('preserve',[]))
            finally:shutil.rmtree(tmpdir,ignore_errors=True)
        data=load_json(VERSION_FILE,{}); data['version']=remote; data.setdefault('channel',manifest.get('channel',cfg.get('channel','stable'))); save_json(VERSION_FILE,data)
        log(f'Mise à jour terminée : v{remote}.'); return 1
    except Exception as e:log(f'Échec de la mise à jour : {e}. La version installée est conservée.'); return 0

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--check',action='store_true'); ap.add_argument('--force',action='store_true'); ap.add_argument('--show-version',action='store_true'); args=ap.parse_args()
    if args.show_version:print(current_version()); return 0
    check_and_apply(force=args.force); return 0
if __name__=='__main__':raise SystemExit(main())
