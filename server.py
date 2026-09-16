import json, math, os, re, sqlite3, threading, webbrowser, hashlib, struct, csv, unicodedata, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html.parser import HTMLParser
from html import unescape
from urllib.parse import urlparse, parse_qs

BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,'invokers.db')
CONFIG_MAP_CSV=os.path.join(BASE,'configid_hero_map.csv')
PROFILE_HOME=os.path.join(os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or os.path.expanduser('~'), 'SmishiesLab')
PROFILE_JSON=os.path.join(PROFILE_HOME,'hero_profiles.json')
HOST='127.0.0.1'; PORT=8501
AUTO_TIMINGS_FILE=os.path.join(BASE,'auto_timings.json')
ASCENSION_DATA_FILE=os.path.join(BASE,'ascension_multipliers.json')
CHARACTER_STATIC_FILE=os.path.join(BASE,'character_static_1302.json')
RELIC_STATIC_FILE=os.path.join(BASE,'relic_static_data.json')
ARENA_STATIC_FILE=os.path.join(BASE,'arena_static_data.json')
VERSION_FILE=os.path.join(BASE,'version.json')

def _app_version():
    try:
        with open(VERSION_FILE,'r',encoding='utf-8-sig') as f:
            return str((json.load(f) or {}).get('version') or 'inconnue')
    except Exception:
        return 'inconnue'


def _load_static_character_sources():
    """Authoritative tables extracted from the game's StaticCharacterData/CharacterConfig."""
    with open(ASCENSION_DATA_FILE,'r',encoding='utf-8') as f:
        ad=json.load(f)
    with open(CHARACTER_STATIC_FILE,'r',encoding='utf-8') as f:
        cd=json.load(f)
    multipliers={int(k):[float(x) for x in v] for k,v in (ad.get('ranks') or {}).items()}
    rows=cd.get('characters') or []
    if not multipliers or not rows:
        raise RuntimeError('StaticCharacterData extraction is empty')
    return multipliers,rows

ASCENSION_MULTIPLIERS, STATIC_1302_HERO_ROWS = _load_static_character_sources()

STATIC_1302_CONFIG_MAP = {}
for _row in STATIC_1302_HERO_ROWS:
    _cfg=str(_row.get('config_id') or '')
    _name=str(_row.get('name') or '')
    if not _cfg or not _name:
        continue
    STATIC_1302_CONFIG_MAP[_cfg]={
        'hero_name':_name,
        'gdid':int(_row.get('gdid') or 0),
        'code':str(_row.get('code') or ''),
        'source':'StaticCharacterData/CharacterConfig 0.60.1302',
        'confidence':1.0
    }

# CharacterConfig et arbre d'eveil valides. Ce registre est extensible aux autres heros.
HERO_PROGRESSION = {
 '17264861641262248': {
  'name':'Silanth','base':{'health':47,'atk':54,'defense':44,'run_speed':115,'crit_rate':.05,'crit_dmg':.50,
   'accuracy':10,'resistance':0,'instinct':0,'combo_points':0,'skill_speed_points':0,'skill_recovery_points':0,'mana_points':0},
  'awake_base':{},
  'nodes':{
   2101:{'atk_pct':.25,'def_pct':.05,'health_pct':.05},2102:{'atk_pct':.08},2107:{'atk_pct':.08},
   2103:{'mana_points':6},2104:{'health_pct':.08},2105:{'crit_rate':.005},2106:{'health_pct':.08},
   2110:{'crit_rate':.005},2111:{'crit_rate':.005},2108:{'crit_rate':.005},2109:{'def_pct':.08},
   2201:{'atk_pct':.25,'def_pct':.05,'health_pct':.05},2202:{'atk_pct':.08},2203:{'mana_points':12},
   2204:{},2207:{'atk_pct':.08},2208:{'accuracy':5},2209:{'accuracy':5},2210:{'accuracy':5},
   2211:{'health_pct':.08},2205:{'accuracy':5},2206:{'def_pct':.08},
   2301:{'atk_pct':.30,'def_pct':.10,'health_pct':.10},2304:{'atk_pct':.10},2306:{'run_speed':10},
   2302:{'atk_pct':.10},2305:{'health_pct':.10},
  }
 }
}

def _load_extracted_progression():
    """Load the exact offline tables generated from static.data, if bundled."""
    try:
        chars=json.load(open(os.path.join(BASE,'character_base_stats.json'),encoding='utf-8')).get('characters') or {}
        nodes_raw=json.load(open(os.path.join(BASE,'awake_nodes.json'),encoding='utf-8')).get('nodes') or {}
        awake=json.load(open(os.path.join(BASE,'base_awake_stats.json'),encoding='utf-8')).get('soul_signs') or {}
        # Complete 0.60.1302 CharacterConfig extraction (222 playable Invokers).
        # This supplements/replaces the older 90-entry static.data extraction.
        for sr in STATIC_1302_HERO_ROWS:
            config_id=str(sr.get('config_id') or '')
            if not config_id: continue
            chars[config_id]={'name':sr.get('name'),'gdid':int(sr.get('gdid') or 0),'code':sr.get('code'),
                'soul_sign':int(sr.get('soul_sign') or 0),
                'health':int(sr.get('health') or 0),'attack':int(sr.get('attack') or 0),
                'defense':int(sr.get('defense') or 0),'run_speed':int(sr.get('run_speed') or 0),
                'critical_rate':0.05000000074505806,'critical_damage':0.5,'ignore_defense':0,
                # CharacterConfig common defaults; hero-specific awakening is layered below.
                'resistance':10,'accuracy':0,'instinct':0,'combo_speed':0,'skill_speed':0,
                'skill_recovery':0,'mana_generation':0}
    except Exception:
        return
    # CharacterStatBonus enum mapping calibrated against the official Awakening totals.
    # The raw extraction labels after Resistance are shifted:
    # critical_damage -> Crit Rate, critical_rate -> Crit DMG,
    # instinct -> Combo Speed, combo_speed -> Skill Speed,
    # skill_speed -> Skill Recovery, skill_recovery -> Mana Gen,
    # mana_generation -> Instinct.
    node_key={'attack_pct':'atk_pct','defense_pct':'def_pct','health_pct':'health_pct','critical_damage':'crit_rate',
              'critical_rate':'crit_dmg','accuracy':'accuracy','resistance':'resistance','run_speed':'run_speed',
              'instinct':'combo_points','combo_speed':'skill_speed_points','skill_speed':'skill_recovery_points',
              'skill_recovery':'mana_points','mana_generation':'instinct'}
    nodes={}
    for node_id,row in nodes_raw.items():
        nodes[int(node_id)]={node_key[k]:v for k,v in (row.get('bonuses') or {}).items() if k in node_key}
    for config_id,row in chars.items():
        sign=str(int(row.get('soul_sign') or 0)); ab=awake.get(sign) or {}
        HERO_PROGRESSION[str(config_id)]={'name':row.get('name'),'soul_sign':int(sign),'nodes':nodes,
          'base':{'health':row.get('health'),'atk':row.get('attack'),'defense':row.get('defense'),'run_speed':row.get('run_speed'),
                  'crit_rate':row.get('critical_rate'),'crit_dmg':row.get('critical_damage'),'accuracy':row.get('accuracy'),
                  'resistance':row.get('resistance'),'instinct':row.get('instinct'),'combo_points':row.get('combo_speed'),
                  'skill_speed_points':row.get('skill_speed'),'skill_recovery_points':row.get('skill_recovery'),
                  'mana_points':row.get('mana_generation')},
          'awake_base':{'health':ab.get('health'),'atk':ab.get('attack'),'defense':ab.get('defense'),'run_speed':ab.get('run_speed'),
                        'crit_rate':ab.get('critical_rate'),'crit_dmg':ab.get('critical_damage'),
                        # BaseAwakeStat extraction labels for Accuracy/Resistance are reversed.
                        # Validated in-game: Ardell sign 2 => +3 PRE, Gralmund sign 7 => +4 PRE.
                        'accuracy':ab.get('resistance'),'resistance':ab.get('accuracy'),
                        # Other BaseAwakeStat fields are read literally unless independently calibrated.
                        'instinct':ab.get('instinct'),'combo_points':ab.get('combo_speed'),
                        'skill_speed_points':ab.get('skill_speed'),'skill_recovery_points':ab.get('skill_recovery'),
                        'mana_points':ab.get('mana_generation')}}

_load_extracted_progression()

def _load_auto_timings():
    try:
        raw=json.load(open(AUTO_TIMINGS_FILE,'r',encoding='utf-8-sig'))
        return {str(x.get('Hero') or '').strip().lower():x for x in raw if str(x.get('Hero') or '').strip()}
    except Exception:
        return {}

AUTO_TIMINGS=_load_auto_timings()

def auto_timing_row(name):
    return AUTO_TIMINGS.get(str(name or '').strip().lower())

def auto_base_chain_time(name, auto_idx, mana=None):
    """Base gameplay cadence for one chained auto (before Combo Speed).
    Uses extracted ComboAnimationRequiredTime. Falls back to the legacy 5-way average."""
    row=auto_timing_row(name)
    if row:
        v=num(row.get(f'Auto{int(auto_idx)}_chain_s'))
        if v>0:return v
    mana=mana if mana is not None else mana_row(name)
    combo_base=num((mana or {}).get('Combo chaîne — lancement total base (s)'),3.0) or 3.0
    return combo_base/5.0

def auto_chain_cycle_base(name, mana=None):
    row=auto_timing_row(name)
    if row:
        v=num(row.get('Combo5_chain_total_s'))
        if v>0:return v
        vals=[num(row.get(f'Auto{i}_chain_s')) for i in range(1,6)]
        if all(x>0 for x in vals):return sum(vals)
    mana=mana if mana is not None else mana_row(name)
    return num((mana or {}).get('Combo chaîne — lancement total base (s)'),3.0) or 3.0

def auto_cast_time(name, auto_idx, combo_mult=1.0, mana=None):
    return max(.03,auto_base_chain_time(name,auto_idx,mana)/max(.05,num(combo_mult,1.0)))

BOSS_SETUPS={
    'Personnalisé': {'name':'Personnalisé','stage':None,'level':None,'hp':0,'attack':0,'defense':1320,'resistance':0,'element':'Neutre','acc_floor':None,'acc_certainty':None},
    'Ulgorim 16': {'name':'Ulgorim','stage':16,'level':100,'hp':172800,'attack':744,'defense':8540,'resistance':475,'element':'Feu','acc_floor':355,'acc_certainty':475},
    'Pentiax 16': {'name':'Pentiax','stage':16,'level':100,'hp':864000,'attack':744,'defense':8540,'resistance':475,'element':'Feu','acc_floor':355,'acc_certainty':475},
    'Yskara 16': {'name':'Yskara','stage':16,'level':100,'hp':144000,'attack':298,'defense':5600,'resistance':475,'element':'Vent','acc_floor':355,'acc_certainty':475},
    'Galvos 16': {'name':'Galvos','stage':16,'level':100,'hp':1296000,'attack':238,'defense':1400,'resistance':475,'element':'Eau','acc_floor':355,'acc_certainty':475},
    'Hyxxis 16': {'name':'Hyxxis','stage':16,'level':100,'hp':432000,'attack':119,'defense':6720,'resistance':475,'element':'Feu','acc_floor':355,'acc_certainty':475},
    'Koltmos 16': {'name':'Koltmos','stage':16,'level':100,'hp':1728000,'attack':744,'defense':8540,'resistance':475,'element':'Vent','acc_floor':355,'acc_certainty':475},
    'Sakiel 16': {'name':'Sakiel','stage':16,'level':100,'hp':230400,'attack':30,'defense':3,'resistance':475,'element':'Eau','acc_floor':355,'acc_certainty':475},
    'Aktar 16': {'name':'Aktar','stage':16,'level':100,'hp':432000,'attack':4464,'defense':7280,'resistance':475,'element':'Terre','acc_floor':355,'acc_certainty':475},
    'Omnissi Astral 16': {'name':'Omnissi Astral','stage':16,'level':100,'hp':1440000,'attack':684,'defense':1680,'resistance':475,'element':'Astral','acc_floor':355,'acc_certainty':475},
    'Omnissi Feu 16': {'name':'Omnissi Feu','stage':16,'level':100,'hp':1728000,'attack':684,'defense':1680,'resistance':475,'element':'Feu','acc_floor':355,'acc_certainty':475},
    'Omnissi Terre 16': {'name':'Omnissi Terre','stage':16,'level':100,'hp':1440000,'attack':446,'defense':1680,'resistance':475,'element':'Terre','acc_floor':355,'acc_certainty':475},
    'Omnissi Vent 16': {'name':'Omnissi Vent','stage':16,'level':100,'hp':1440000,'attack':446,'defense':1680,'resistance':475,'element':'Vent','acc_floor':355,'acc_certainty':475},
    'Omnissi Eau 16': {'name':'Omnissi Eau','stage':16,'level':100,'hp':1440000,'attack':744,'defense':1680,'resistance':475,'element':'Eau','acc_floor':355,'acc_certainty':475},
    'Omnissi Lumière 16': {'name':'Omnissi Lumière','stage':16,'level':100,'hp':1440000,'attack':684,'defense':1680,'resistance':475,'element':'Lumière','acc_floor':355,'acc_certainty':475},
    'Omnissi Ténèbres 16': {'name':'Omnissi Ténèbres','stage':16,'level':100,'hp':1728000,'attack':684,'defense':1680,'resistance':475,'element':'Ténèbres','acc_floor':355,'acc_certainty':475},
}


# ---------- Titans liés / conversions de stats ----------
# Bound Effects repris de l'onglet Titans du calculateur. Les valeurs sont interpolées 0★→6★.
TITANS={
 'Aucun': {'stat':None,'unit':None,'mode':'Global','normal':(0,0),'dungeon':(0,0)},
 'Cindrake': {'stat':'ATK','unit':'%','mode':'Global','normal':(.25,.50),'dungeon':(.25,.50)},
 'Terravun': {'stat':'DEF','unit':'%','mode':'Global','normal':(.25,.50),'dungeon':(.25,.50)},
 'Wyvold': {'stat':'ATK','unit':'%','mode':'Global','normal':(.25,.50),'dungeon':(.25,.50)},
 'Araknia': {'stat':'PRE','unit':'points','mode':'Global','normal':(70,140),'dungeon':(70,140)},
 'Arbarion': {'stat':'HP','unit':'%','mode':'Global','normal':(.20,.40),'dungeon':(.20,.40)},
 'Baggodal': {'stat':'Combo Speed','unit':'points','mode':'Dual','normal':(28,56),'dungeon':(49,98)},
 'Gargoth': {'stat':'DEF','unit':'%','mode':'Dual','normal':(.16,.32),'dungeon':(.28,.56)},
 'Keltaur': {'stat':'Combo Speed','unit':'points','mode':'Dual','normal':(28,56),'dungeon':(49,98)},
 'Mekiddo': {'stat':'ATK','unit':'%','mode':'Global','normal':(.20,.40),'dungeon':(.20,.40)},
 'Minarth': {'stat':'ATK','unit':'%','mode':'Dual','normal':(.16,.32),'dungeon':(.28,.56)},
 'Myrmadir': {'stat':'PRE','unit':'points','mode':'Dual','normal':(56,112),'dungeon':(98,196)},
 'Reltalis': {'stat':'ATK','unit':'%','mode':'Global','normal':(.20,.40),'dungeon':(.20,.40)},
 'Aratax': {'stat':'Combo Speed','unit':'points','mode':'Dual','normal':(24,48),'dungeon':(43,86)},
 'Bragnott': {'stat':'Combo Speed','unit':'points','mode':'Global','normal':(31,62),'dungeon':(31,62)},
 'Carchus': {'stat':'HP','unit':'%','mode':'Global','normal':(.18,.36),'dungeon':(.18,.36)},
 'Eldathir': {'stat':'HP','unit':'%','mode':'Dual','normal':(.14,.28),'dungeon':(.25,.50)},
 'Quadrax': {'stat':'PRE','unit':'points','mode':'Dual','normal':(48,96),'dungeon':(86,172)},
 'Radlath': {'stat':'Skill Speed','unit':'points','mode':'Global','normal':(31,62),'dungeon':(31,62)},
 'Visciant': {'stat':'HP','unit':'%','mode':'Global','normal':(.18,.36),'dungeon':(.18,.36)},
 'Amprix': {'stat':'ATK','unit':'%','mode':'Global','normal':(.15,.30),'dungeon':(.15,.30)},
 'Cairnai': {'stat':'PRE','unit':'points','mode':'Global','normal':(52,104),'dungeon':(52,104)},
 'Dathokal': {'stat':'Combo Speed','unit':'points','mode':'Global','normal':(26,52),'dungeon':(26,52)},
 'Ferrogar': {'stat':'PRE','unit':'points','mode':'Dual','normal':(42,84),'dungeon':(74,148)},
 'Geodoz': {'stat':'ATK','unit':'%','mode':'Dual','normal':(.12,.24),'dungeon':(.21,.42)},
 'Hamaga': {'stat':'Combo Speed','unit':'points','mode':'Dual','normal':(21,42),'dungeon':(37,74)},
 'Honoshi': {'stat':'ATK','unit':'%','mode':'Dual','normal':(.12,.24),'dungeon':(.21,.42)},
 'Komodyre': {'stat':'RES','unit':'points','mode':'Global','normal':(52,104),'dungeon':(52,104)},
 'Kordyne': {'stat':'HP','unit':'%','mode':'Global','normal':(.15,.30),'dungeon':(.15,.30)},
 'Litria': {'stat':'ATK','unit':'%','mode':'Global','normal':(.15,.30),'dungeon':(.15,.30)},
 'Quelron': {'stat':'RES','unit':'points','mode':'Global','normal':(52,104),'dungeon':(52,104)},
 'Sionach': {'stat':'ATK','unit':'%','mode':'Dual','normal':(.12,.24),'dungeon':(.21,.42)},
 'Themista': {'stat':'HP','unit':'%','mode':'Global','normal':(.15,.30),'dungeon':(.15,.30)},
 'Vollexos': {'stat':'ATK','unit':'%','mode':'Dual','normal':(.12,.24),'dungeon':(.21,.42)},
 'Wolrath': {'stat':'HP','unit':'%','mode':'Dual','normal':(.12,.24),'dungeon':(.21,.42)},
}
def _speed_points_to_pct(points):
    """Combo Speed / Skill Speed exact game formula.
    <= 50 pts: 0.2% per point.
    > 50 pts: 10*ln(10*points)-52.3 percent, rounded to 0.1%.
    """
    p=max(0.0,float(points or 0))
    if p<=50:
        shown=.2*p
    else:
        shown=10.0*math.log(10.0*p)-52.3
        shown=round(shown,1)
    return shown/100.0

def _speed_pct_to_points(rate):
    """Inverse of the exact Combo/Skill Speed display formula."""
    shown=max(0.0,float(rate or 0))*100.0
    if shown<=10.0:
        return shown/.2
    return math.exp((shown+52.3)/10.0)/10.0

def combo_points_to_pct(p):
    return _speed_points_to_pct(p)

def combo_pct_to_points(r):
    return _speed_pct_to_points(r)

def skill_points_to_pct(p):
    return _speed_points_to_pct(p)

def skill_pct_to_points(r):
    return _speed_pct_to_points(r)

def recovery_points_to_pct(points):
    """Skill Recovery exact game formula.
    <= 100 pts: 0.25% per point.
    > 100 pts: 25*ln(10*(points+50))-157.87 percent, rounded to 0.1%.
    """
    p=max(0.0,float(points or 0))
    if p<=100:
        shown=.25*p
    else:
        shown=25.0*math.log(10.0*(p+50.0))-157.87
        shown=round(shown,1)
    return shown/100.0

def recovery_pct_to_points(rate):
    """Inverse of the exact Skill Recovery display formula."""
    shown=max(0.0,float(rate or 0))*100.0
    if shown<=25.0:
        return shown/.25
    return math.exp((shown+157.87)/25.0)/10.0-50.0

def mana_points_to_pct(points):
    """Mana Generation Rating -> displayed fraction.
    Game formula: 0.5 * points up to 50; above 50:
    25 * ln(10 * points) - 130.37, rounded to one decimal percent.
    """
    p=max(0.0,float(points or 0))
    if p<=50:
        shown=0.5*p
    else:
        shown=25.0*math.log(10.0*p)-130.37
    return round(shown,1)/100.0

def mana_pct_to_points(rate):
    """Inverse of mana_points_to_pct, for combining relic/set rating points."""
    shown=max(0.0,float(rate or 0))*100.0
    if shown<=25.0:
        return shown/0.5
    return math.exp((shown+130.37)/25.0)/10.0
def titan_value(name,stars=0,dungeon=False):
    t=TITANS.get(name,TITANS['Aucun']); lo,hi=t['dungeon' if dungeon and t['mode']=='Dual' else 'normal']; st=max(0,min(6,float(stars))); return lo+(hi-lo)*(st/6)
def apply_titan(name, final_stats, titan='Aucun', stars=0, dungeon=False):
    out=dict(final_stats); t=TITANS.get(titan,TITANS['Aucun']); v=titan_value(titan,stars,dungeon); h=hero_row(name) or {}
    stat=t.get('stat')
    if stat=='ATK': out['atk']=num(out.get('atk')) + num(h.get('atk'))*v
    elif stat=='PRE': out['accuracy']=num(out.get('accuracy')) + v
    elif stat=='RES': out['resistance']=num(out.get('resistance')) + v
    elif stat=='Combo Speed': out['combo_speed']=combo_points_to_pct(combo_pct_to_points(num(out.get('combo_speed')))+v)
    elif stat=='Skill Speed': out['skill_speed']=skill_points_to_pct(skill_pct_to_points(num(out.get('skill_speed')))+v)
    out['_titan']={'name':titan,'stars':stars,'dungeon':bool(dungeon),'stat':stat,'unit':t.get('unit'),'value':v}
    return out

def final_to_build(name, st):
    h=hero_row(name) or {}; base=max(.001,num(h.get('atk')))
    return dict(
        atk_pct=max(-.99,num(st.get('atk'),base)/base-1),
        cr_add=num(st.get('crit_rate'))-num(h.get('crit_rate')),
        cd_add=num(st.get('crit_dmg'))-num(h.get('crit_dmg')),
        acc_add=num(st.get('accuracy'))-num(h.get('accuracy')),
        accuracy_final=num(st.get('accuracy')),
        combo_add=num(st.get('combo_speed'))-num(h.get('combo_speed')),
        skill_speed_add=num(st.get('skill_speed'))-num(h.get('skill_speed')),
        recovery_add=num(st.get('skill_recovery'))-num(h.get('skill_recovery')),
        mana_add=num(st.get('mana_gen'))-num(h.get('mana_gen')),
        resistance_final=num(st.get('resistance'),num(h.get('resistance'))),
    )

# ---------- DB helpers ----------
def q(sql,args=()):
    with sqlite3.connect(DB) as con:
        con.row_factory=sqlite3.Row
        return [dict(r) for r in con.execute(sql,args).fetchall()]

def one(sql,args=()):
    rows=q(sql,args); return rows[0] if rows else None

def ensure_profile_table():
    with sqlite3.connect(DB) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS hero_profiles (
            name TEXT PRIMARY KEY, atk REAL, crit_rate REAL, crit_dmg REAL, accuracy REAL, resistance REAL,
            combo_speed REAL, skill_speed REAL, skill_recovery REAL, mana_gen REAL,
            auto_level INTEGER, s1_level INTEGER, s2_level INTEGER, s3_level INTEGER, ult_level INTEGER,
            titan TEXT, titan_stars INTEGER, titan_dungeon INTEGER, element TEXT DEFAULT 'Neutre'
        )''')
        hp_cols={r[1] for r in con.execute('PRAGMA table_info(hero_profiles)')}
        if 'element' not in hp_cols:
            con.execute("ALTER TABLE hero_profiles ADD COLUMN element TEXT DEFAULT 'Neutre'")
        hero_cols={r[1] for r in con.execute('PRAGMA table_info(heroes)')}
        if hero_cols and 'element' not in hero_cols:
            con.execute("ALTER TABLE heroes ADD COLUMN element TEXT DEFAULT 'Neutre'")
        con.commit()



# ---------- Box locale persistante / mapping ConfigId ----------
def ensure_box_tables():
    with sqlite3.connect(DB) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS game_config_map (
            config_id TEXT PRIMARY KEY, hero_name TEXT NOT NULL, confidence REAL DEFAULT 1,
            source TEXT DEFAULT 'manual', updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        # V10.48: chaque exemplaire de héros doit être conservé. Dans V10.47,
        # config_id était la clé primaire et les doublons d'un même héros s'écrasaient.
        cols={r[1]:r for r in con.execute('PRAGMA table_info(box_heroes)')}
        needs_migration=bool(cols) and cols.get('config_id') and int(cols['config_id'][5] or 0)==1
        if needs_migration:
            con.execute("""CREATE TABLE IF NOT EXISTS box_heroes_v1048 (
                inventory_id INTEGER PRIMARY KEY, config_id TEXT NOT NULL, hero_name TEXT,
                rank INTEGER, level INTEGER, copies INTEGER DEFAULT 1, total_experience INTEGER,
                locked INTEGER, in_storage INTEGER, skill_levels_raw TEXT, relics_by_slot TEXT,
                equipped_relic_count INTEGER, imported_at TEXT DEFAULT CURRENT_TIMESTAMP
            )""")
            con.execute("""INSERT OR REPLACE INTO box_heroes_v1048
                (inventory_id,config_id,hero_name,rank,level,copies,total_experience,locked,in_storage,skill_levels_raw,relics_by_slot,equipped_relic_count,imported_at)
                SELECT COALESCE(inventory_id, -rowid),config_id,hero_name,rank,level,COALESCE(copies,1),total_experience,locked,in_storage,skill_levels_raw,relics_by_slot,equipped_relic_count,imported_at FROM box_heroes""")
            con.execute('DROP TABLE box_heroes')
            con.execute('ALTER TABLE box_heroes_v1048 RENAME TO box_heroes')
        con.execute("""CREATE TABLE IF NOT EXISTS box_heroes (
            inventory_id INTEGER PRIMARY KEY, config_id TEXT NOT NULL, hero_name TEXT,
            rank INTEGER, level INTEGER, copies INTEGER DEFAULT 1, total_experience INTEGER,
            awake_level INTEGER DEFAULT 0, awake_node_count INTEGER DEFAULT 0,
            awake_node_ids TEXT,
            locked INTEGER, in_storage INTEGER, skill_levels_raw TEXT,
            corruption_tolerance_1 INTEGER DEFAULT 0, corruption_tolerance_2 INTEGER DEFAULT 0,
            relics_by_slot TEXT, equipped_relic_count INTEGER, imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        bh_cols={r[1] for r in con.execute('PRAGMA table_info(box_heroes)')}
        if 'awake_level' not in bh_cols:
            con.execute('ALTER TABLE box_heroes ADD COLUMN awake_level INTEGER DEFAULT 0')
        if 'awake_node_count' not in bh_cols:
            con.execute('ALTER TABLE box_heroes ADD COLUMN awake_node_count INTEGER DEFAULT 0')
        if 'awake_node_ids' not in bh_cols:
            con.execute('ALTER TABLE box_heroes ADD COLUMN awake_node_ids TEXT')
        if 'corruption_tolerance_1' not in bh_cols:
            con.execute('ALTER TABLE box_heroes ADD COLUMN corruption_tolerance_1 INTEGER DEFAULT 0')
        if 'corruption_tolerance_2' not in bh_cols:
            con.execute('ALTER TABLE box_heroes ADD COLUMN corruption_tolerance_2 INTEGER DEFAULT 0')
        con.execute('CREATE INDEX IF NOT EXISTS idx_box_heroes_config ON box_heroes(config_id)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_box_heroes_name ON box_heroes(hero_name)')
        con.execute("""CREATE TABLE IF NOT EXISTS box_relics (
            inventory_id INTEGER PRIMARY KEY, slot INTEGER, rank INTEGER, rarity INTEGER, set_id INTEGER,
            level INTEGER, stars INTEGER, quality_code INTEGER, is_seen INTEGER DEFAULT 0,
            equipped_hero_id INTEGER, stats_json TEXT, imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""")
        br_cols={r[1] for r in con.execute('PRAGMA table_info(box_relics)')}
        for col,ddl in [('stars','INTEGER'),('quality_code','INTEGER'),('is_seen','INTEGER DEFAULT 0')]:
            if col not in br_cols: con.execute(f'ALTER TABLE box_relics ADD COLUMN {col} {ddl}')
        con.execute('CREATE INDEX IF NOT EXISTS idx_box_relics_hero ON box_relics(equipped_hero_id)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_box_relics_slot ON box_relics(slot)')
        con.execute('CREATE INDEX IF NOT EXISTS idx_box_relics_set ON box_relics(set_id)')
        # V10.87: niveaux personnels de la Salle des trophées (Great Hall), importés depuis PlayerArenaModel.dat.
        con.execute("""CREATE TABLE IF NOT EXISTS arena_hall_levels (
            element_id INTEGER NOT NULL, stat_id INTEGER NOT NULL, level INTEGER NOT NULL,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(element_id,stat_id)
        )""")
        # V10.76: authoritative ConfigId -> hero map from StaticData 0.60.1302.
        # It overrides stale/manual mappings from older heuristic imports.
        valid={r[0].lower():r[0] for r in con.execute('SELECT name FROM heroes WHERE name IS NOT NULL')}
        for cfg,meta in STATIC_1302_CONFIG_MAP.items():
            canon=valid.get(str(meta.get('hero_name') or '').lower())
            if not canon: continue
            con.execute("""INSERT INTO game_config_map(config_id,hero_name,confidence,source,updated_at)
                           VALUES(?,?,1,'static-0.60.1302',CURRENT_TIMESTAMP)
                           ON CONFLICT(config_id) DO UPDATE SET hero_name=excluded.hero_name,confidence=1,source='static-0.60.1302',updated_at=CURRENT_TIMESTAMP""",
                        (str(cfg),canon))
        if os.path.isfile(CONFIG_MAP_CSV):
            valid={r[0].lower():r[0] for r in con.execute('SELECT name FROM heroes WHERE name IS NOT NULL')}
            try:
                with open(CONFIG_MAP_CSV,'r',encoding='utf-8-sig',newline='') as f:
                    for row in csv.DictReader(f):
                        cfg=str(row.get('ConfigId') or '').strip()
                        name=str(row.get('HeroName') or '').strip()
                        canon=valid.get(name.lower())
                        if not cfg or not canon: continue
                        con.execute("""INSERT OR IGNORE INTO game_config_map(config_id,hero_name,confidence,source,updated_at)
                                       VALUES(?,?,1,'official-site-0.60.1302',CURRENT_TIMESTAMP)""",(cfg,canon))
            except Exception:
                pass
        con.commit()

def config_map_all():
    ensure_box_tables()
    return {str(r['config_id']):r for r in q('SELECT * FROM game_config_map')}

def save_config_mappings(mappings):
    ensure_box_tables(); saved=0
    valid={r['name'].lower():r['name'] for r in q('SELECT name FROM heroes WHERE name IS NOT NULL')}
    with sqlite3.connect(DB) as con:
        for m in mappings or []:
            cfg=str(m.get('config_id') or '').strip(); name=str(m.get('hero_name') or '').strip()
            if not cfg or not name: continue
            canon=valid.get(name.lower())
            if not canon: continue
            con.execute("""INSERT INTO game_config_map(config_id,hero_name,confidence,source,updated_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)
                           ON CONFLICT(config_id) DO UPDATE SET hero_name=excluded.hero_name,confidence=excluded.confidence,source=excluded.source,updated_at=CURRENT_TIMESTAMP""",
                        (cfg,canon,float(m.get('confidence') or 1),str(m.get('source') or 'manual')))
            saved+=1
        con.commit()
    return saved

ARENA_ELEMENT_ID_TO_NAME={1:'Feu',2:'Terre',3:'Vent',4:'Eau',5:'Lumière',6:'Ténèbres'}
ARENA_ELEMENT_NAME_TO_ID={v:k for k,v in ARENA_ELEMENT_ID_TO_NAME.items()}

def _load_arena_static_source():
    """Load HallBonuses extracted from StaticArenaData."""
    with open(ARENA_STATIC_FILE,'r',encoding='utf-8') as f:
        d=json.load(f)
    vals={int(k):[float(x) for x in v] for k,v in (d.get('character_stat_bonus_values') or {}).items()}
    if not vals:
        raise RuntimeError('StaticArenaData HallBonuses extraction is empty')
    return vals

ARENA_HALL_VALUES=_load_arena_static_source()
ARENA_HALL_SOURCE='arena_static_data.json fallback'

def inspect_playerarena_hall_raw():
    """Read-only dump of every MemoryPack member in PlayerArenaModel.HallBonuses.
    No semantic assumption about Element/Stat/Level ordering."""
    afp=_find_aggregate_snapshot('PlayerArenaModel.dat')
    if not afp:
        return {'ok':False,'error':'PlayerArenaModel.dat introuvable',**_game_readonly_status()}
    try:
        with _game_ro_open(afp,'rb') as fh:
            data=fh.read()
        mc,lens,root,end=_mp_vt(data,25)
        result={'ok':True,'file':afp,'root_member_count':mc,'root_spans':[],
                'hall_root_index':8,'rows':[],**_game_readonly_status()}
        for i,(s,e) in enumerate(root):
            result['root_spans'].append({'index':i,'start':s,'end':e,'size':e-s,
                                         'prefix_hex':data[s:min(e,s+32)].hex()})
        if len(root)<=8:
            result['error']='PlayerArenaModel sans membre #8'; return result
        s,e=root[8]
        if e-s<4:
            result['error']='HallBonuses trop court'; return result
        count=struct.unpack_from('<i',data,s)[0]
        result['declared_count']=count
        if count<0 or count>1000:
            result['error']='Nombre HallBonuses invalide: %s'%count; return result
        p=s+4
        for idx in range(count):
            imc,ilens,iv,iend=_mp_vt(data,p)
            vals=[]
            for mi,span in enumerate(iv):
                a,b=span
                raw=data[a:b]
                item={'member':mi,'start':a,'end':b,'size':b-a,'hex':raw.hex()}
                if b-a>=4:
                    try:item['i32']=struct.unpack_from('<i',data,a)[0]
                    except Exception:pass
                if b-a>=8:
                    try:item['i64']=struct.unpack_from('<q',data,a)[0]
                    except Exception:pass
                vals.append(item)
            result['rows'].append({
                'row':idx,'member_count':imc,'lengths':ilens,'start':p,'end':iend,
                'members':vals
            })
            p=iend
        return result
    except Exception as e:
        return {'ok':False,'file':afp,'error':str(e),**_game_readonly_status()}

def _decode_playerarena_hall_file(fp):
    """Décodage read-only de PlayerArenaModel.dat.
    Le membre MemoryPack #8 est HallBonuses: Element, CharacterStatBonus, Level.
    Mapping Element validé sur le Hall Eau: 1=Feu, 2=Terre, 3=Vent, 4=Eau, 5=Lumière, 6=Ténèbres.
    """
    if not fp or not os.path.isfile(fp): return []
    with _game_ro_open(fp,'rb') as f:data=f.read()
    mc,lens,root,end=_mp_vt(data,25)
    if len(root)<=8:return []
    s,e=root[8]
    if e-s<4:return []
    count=struct.unpack_from('<i',data,s)[0]
    if count<0 or count>1000:return []
    p=s+4; out=[]
    for _ in range(count):
        imc,ilens,iv,iend=_mp_vt(data,p)
        if len(iv)<3:break
        element=_mp_i32(data,iv[0]); stat=_mp_i32(data,iv[1]); level=_mp_i32(data,iv[2])
        if element in ARENA_ELEMENT_ID_TO_NAME and stat in ARENA_HALL_VALUES and level and 1<=level<=15:
            out.append({'element_id':element,'element':ARENA_ELEMENT_ID_TO_NAME[element],
                        'stat_id':stat,'level':level})
        p=iend
    return out

def import_arena_hall_only():
    """Importe uniquement la Salle des trophées depuis PlayerArenaModel.dat.
    Ne touche ni aux héros, ni aux reliques, ni aux profils sauvegardés.
    """
    ensure_box_tables()
    afp=_find_aggregate_snapshot('PlayerArenaModel.dat')
    if not afp:
        return {'ok':False,'error':'PlayerArenaModel.dat introuvable'}
    rows=_decode_playerarena_hall_file(afp)
    with sqlite3.connect(DB) as con:
        con.execute('DELETE FROM arena_hall_levels')
        for hb in rows:
            con.execute("""INSERT OR REPLACE INTO arena_hall_levels
                (element_id,stat_id,level,imported_at)
                VALUES(?,?,?,CURRENT_TIMESTAMP)""",
                (int(hb.get('element_id')),int(hb.get('stat_id')),int(hb.get('level'))))
        con.commit()
    by_element={}
    for hb in rows:
        el=hb.get('element') or str(hb.get('element_id'))
        by_element[el]=by_element.get(el,0)+1
    return {'ok':True,'imported':len(rows),'file':afp,'by_element':by_element}

def _arena_hall_bonus_for_element(element):
    eid=ARENA_ELEMENT_NAME_TO_ID.get(normalize_element(element))
    out={'atk_flat':0.0,'atk_pct':0.0,'crit_rate':0.0,'crit_dmg':0.0,'accuracy':0.0,'resistance':0.0,
         'combo_points':0.0,'skill_speed_points':0.0,'skill_recovery_points':0.0,'mana_points':0.0,
         'hp_pct':0.0,'def_pct':0.0,'instinct':0.0,'unapplied':{}}
    if not eid:return out
    ensure_box_tables()
    rows=q('SELECT stat_id,level FROM arena_hall_levels WHERE element_id=?',(eid,))
    for r in rows:
        sid=int(r.get('stat_id') or 0); lv=int(r.get('level') or 0)
        vals=ARENA_HALL_VALUES.get(sid) or []
        if not (1<=lv<=len(vals)):continue
        v=vals[lv-1]
        key={4:'atk_pct',5:'def_pct',6:'hp_pct',7:'crit_rate',8:'crit_dmg',9:'accuracy',10:'resistance',
             12:'combo_points',13:'skill_speed_points',14:'skill_recovery_points',15:'mana_points',16:'instinct'}.get(sid)
        if key:out[key]+=v

    return out

def _arena_hall_bonus_for_hero(name):
    return _arena_hall_bonus_for_element(hero_element(name))

TROPHY_DPS_STATS={
    4:('ATQ %','atk_pct'),
    7:('Taux crit','crit_rate'),
    8:('Dég crit','crit_dmg'),
    9:('PRÉ','accuracy'),
    12:('VIT combo','combo_points'),
    13:('VIT compétence','skill_speed_points'),
    14:('Récup. compétence','skill_recovery_points'),
    15:('Gén. mana','mana_points'),
}

def _arena_hall_level(element,stat_id):
    eid=ARENA_ELEMENT_NAME_TO_ID.get(normalize_element(element))
    if not eid:return 0
    r=one('SELECT level FROM arena_hall_levels WHERE element_id=? AND stat_id=?',(eid,int(stat_id)))
    return int((r or {}).get('level') or 0)

def _trophy_apply_next_level(name, stat_id, current_level, current_stats, box_build):
    vals=ARENA_HALL_VALUES.get(int(stat_id)) or []
    nxt=int(current_level)+1
    if nxt<1 or nxt>len(vals):return None
    old=float(vals[current_level-1]) if current_level>=1 else 0.0
    new=float(vals[nxt-1])
    delta=new-old
    st=dict(current_stats or {})
    naked=(box_build or {}).get('pre_relic_stats') or {}
    sid=int(stat_id)
    if sid==4:
        st['atk']=num(st.get('atk'))+num(naked.get('atk'))*delta
    elif sid==7:
        st['crit_rate']=num(st.get('crit_rate'))+delta
    elif sid==8:
        st['crit_dmg']=num(st.get('crit_dmg'))+delta
    elif sid==9:
        st['accuracy']=num(st.get('accuracy'))+delta
    elif sid==12:
        st['combo_speed']=combo_points_to_pct(combo_pct_to_points(num(st.get('combo_speed')))+delta)
    elif sid==13:
        st['skill_speed']=skill_points_to_pct(skill_pct_to_points(num(st.get('skill_speed')))+delta)
    elif sid==14:
        st['skill_recovery']=recovery_points_to_pct(recovery_pct_to_points(num(st.get('skill_recovery')))+delta)
    elif sid==15:
        st['mana_gen']=mana_points_to_pct(mana_pct_to_points(num(st.get('mana_gen')))+delta)
    else:
        return None
    return st,delta,new

def _trophy_sim_audit(name, sim, levels):
    log=(sim or {}).get('log') or []
    casts={'Auto':0,'Skill 1':0,'Skill 2':0,'Skill 3':0,'Ultimate':0}
    for x in log:
        a=str(x.get('action') or '')
        if a.startswith('Auto'): casts['Auto']+=1
        elif a in casts: casts[a]+=1
    out={'casts':casts,'damage_by':dict((sim or {}).get('damage_by') or {})}
    if str(name).strip().lower()=='brandis':
        ur=coeff_row(name,(levels or {}).get('ult',7)) or {}
        nominal=max(1,int(num(ur.get('Ult Hits'),1)))
        triples=sum(1 for x in log if x.get('action')=='Ultimate' and int(num(x.get('hits'),1))>=nominal*3)
        out['brandis_ult_x3']=triples
        out['brandis_ult_total']=casts.get('Ultimate',0)
        out['brandis_nominal_ult_hits']=nominal
    return out

def optimize_trophy_hall(element, hero_names=None, duration=120, boss_def=1320, boss_res=0, boss_hp=0, boss_atk=0, boss_element='Neutre', costs=None):
    element=normalize_element(element)
    if element not in ARENA_ELEMENT_NAME_TO_ID:
        return {'error':'Élément invalide.'}
    ensure_box_tables()
    owned={str(x.get('hero_name') or '').strip() for x in q("SELECT DISTINCT hero_name FROM box_heroes WHERE hero_name IS NOT NULL AND trim(hero_name)<>''")}
    requested=[str(x).strip() for x in (hero_names or []) if str(x).strip()]
    if requested:
        names=[n for n in requested if n in owned and normalize_element(hero_element(n))==element]
    else:
        names=sorted(n for n in owned if normalize_element(hero_element(n))==element)
    if not names:
        return {'error':f'Aucun héros {element} sélectionné dans la box.'}

    parsed_costs=[]
    for x in (costs or []):
        try: parsed_costs.append(max(0.0,float(x)))
        except: parsed_costs.append(0.0)
    while len(parsed_costs)<15: parsed_costs.append(0.0)

    baselines={}
    usable=[]
    for name in names:
        bh=box_hero_for_name(name)
        build=(bh or {}).get('box_build') or {}
        st=build.get('final_stats')
        if not st: continue
        p=profile_for(name); lv=profile_levels(p)
        sim=simulate_combat(name,lv,duration,boss_def,boss_res,boss_hp,boss_atk,boss_element,comparison_mode=True,**final_to_build(name,st))
        if not sim: continue
        baselines[name]={'dps':num(sim.get('dps')),'stats':st,'box_build':build,'levels':lv,'audit':_trophy_sim_audit(name,sim,lv)}
        usable.append(name)
    if not usable:
        return {'error':'Aucun héros sélectionné ne peut être simulé avec les données actuelles.'}

    base_total=sum(baselines[n]['dps'] for n in usable)
    rows=[]
    for sid,(label,key) in TROPHY_DPS_STATS.items():
        cur=_arena_hall_level(element,sid)
        if cur>=15: continue
        nxt=cur+1
        cost=parsed_costs[nxt-1] if nxt-1<len(parsed_costs) else 0.0
        hero_rows=[]; total_after=0.0; pct_gains=[]
        delta_value=None; next_value=None
        for name in usable:
            b=baselines[name]
            changed=_trophy_apply_next_level(name,sid,cur,b['stats'],b['box_build'])
            if not changed: continue
            st2,dv,nv=changed; delta_value=dv; next_value=nv
            sim2=simulate_combat(name,b['levels'],duration,boss_def,boss_res,boss_hp,boss_atk,boss_element,comparison_mode=True,**final_to_build(name,st2))
            d2=num((sim2 or {}).get('dps'),b['dps'])
            gain=d2-b['dps']; pct=(gain/b['dps'] if b['dps']>0 else 0.0)
            total_after+=d2; pct_gains.append(pct)
            hero_rows.append({'hero':name,'before_dps':round(b['dps'],2),'after_dps':round(d2,2),'gain_dps':round(gain,2),'gain_pct':pct,
                              'before_audit':b.get('audit') or {},'after_audit':_trophy_sim_audit(name,sim2,b['levels'])})
        gain_total=total_after-base_total
        avg_pct=sum(pct_gains)/len(pct_gains) if pct_gains else 0.0
        ratio=(gain_total/cost) if cost>0 else None
        rows.append({'stat_id':sid,'stat':label,'current_level':cur,'next_level':nxt,
                     'current_value':float((ARENA_HALL_VALUES.get(sid) or [0])[cur-1]) if cur>=1 else 0.0,
                     'next_value':next_value,'delta_value':delta_value,'cost':cost,
                     'base_total_dps':round(base_total,2),'after_total_dps':round(total_after,2),
                     'gain_total_dps':round(gain_total,2),'gain_avg_pct':avg_pct,
                     'dps_per_medal':round(ratio,6) if ratio is not None else None,
                     'heroes':sorted(hero_rows,key=lambda x:x['gain_dps'],reverse=True)})
    # If costs are supplied, ratio is the primary score; otherwise expose raw DPS gain.
    if any(r.get('cost',0)>0 for r in rows):
        rows.sort(key=lambda r:(r['dps_per_medal'] is not None, r['dps_per_medal'] or -1e99, r['gain_total_dps']),reverse=True)
        metric='dps_per_medal'
    else:
        rows.sort(key=lambda r:r['gain_total_dps'],reverse=True); metric='gain_total_dps'
    return {'ok':True,'element':element,'heroes':usable,'hero_count':len(usable),'duration':duration,
            'base_total_dps':round(base_total,2),'metric':metric,'costs':parsed_costs,'rows':rows}

def persist_decoded_box(decoded):
    ensure_box_tables(); rows=decoded.get('instances') or decoded.get('rows') or []; imported=0; mapped=0; relic_imported=0
    with sqlite3.connect(DB) as con:
        # Un import représente un instantané complet : on remplace uniquement la box locale,
        # jamais les fichiers du jeu.
        con.execute('DELETE FROM box_heroes')
        con.execute('DELETE FROM box_relics')
        con.execute('DELETE FROM arena_hall_levels')
        for hb in decoded.get('hall_bonuses') or []:
            con.execute("""INSERT OR REPLACE INTO arena_hall_levels(element_id,stat_id,level,imported_at)
                           VALUES(?,?,?,CURRENT_TIMESTAMP)""",
                        (int(hb.get('element_id')),int(hb.get('stat_id')),int(hb.get('level'))))
        # V10.51 : importe TOUTES les reliques du compte, y compris celles non équipées.
        # PlayerRelicsModel contient l'inventaire complet.
        all_relics=decoded.get('relics') or []
        hero_name_by_iid={int(x.get('inventory_id')):(x.get('name_candidate') or x.get('hero_name')) for x in rows if x.get('inventory_id') is not None}
        for r in all_relics:
            rid=r.get('inventory_id')
            if rid is None: continue
            con.execute("""INSERT OR REPLACE INTO box_relics
                (inventory_id,slot,rank,rarity,set_id,level,stars,quality_code,is_seen,equipped_hero_id,stats_json,imported_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
                (rid,r.get('slot'),r.get('rank'),r.get('rarity'),r.get('set'),r.get('level'),r.get('stars'),r.get('quality_code'),
                 1 if r.get('is_seen') else 0,r.get('equipped_hero_id'),json.dumps(r.get('stats') or [],ensure_ascii=False)))
            relic_imported+=1
        seen_relics=set(r.get('inventory_id') for r in all_relics if r.get('inventory_id') is not None)
        for x in rows:
            cfg=str(x.get('config_id') or '')
            iid=x.get('inventory_id')
            if not cfg or iid is None: continue
            name=x.get('name_candidate') or x.get('hero_name')
            _skills=x.get('skill_levels_raw') or {}
            try:
                _skills={int(k):int(v) for k,v in _skills.items()}
            except Exception:
                _skills={}
            con.execute("""INSERT OR REPLACE INTO box_heroes
                (inventory_id,config_id,hero_name,rank,level,copies,total_experience,awake_level,awake_node_count,awake_node_ids,locked,in_storage,skill_levels_raw,corruption_tolerance_1,corruption_tolerance_2,relics_by_slot,equipped_relic_count,imported_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
                (iid,cfg,name,x.get('rank'),x.get('level'),1,x.get('total_experience'),x.get('awake_level') or 0,x.get('awake_node_count') or 0,
                 json.dumps(x.get('awake_node_ids') or []),
                 1 if x.get('locked') else 0,1 if x.get('in_storage') else 0,json.dumps(x.get('skill_levels_raw') or {},ensure_ascii=False),
                 int(_skills.get(7,0)),int(_skills.get(8,0)),
                 json.dumps(x.get('relics_by_slot') or {},ensure_ascii=False),x.get('equipped_relic_count') or 0))
            # Les reliques ont déjà été importées globalement ci-dessus.
            # On fiabilise seulement le lien vers le héros à partir de RelicsBySlot.
            for rid in (x.get('relics_by_slot') or {}).values():
                if rid is not None:
                    con.execute('UPDATE box_relics SET equipped_hero_id=? WHERE inventory_id=?',(iid,rid))
            imported+=1; mapped+=1 if name else 0
        con.commit()
    # V10.50: ne PAS injecter de pseudo-stats finales dans les profils.
    # La table heroes est une référence max (lvl 60 / progression max), alors que la box
    # peut contenir un exemplaire lvl 40 / éveil partiel. On conserve donc les bonus reliques
    # et la progression réelle, mais on laisse les fiches Combat/Comparateur intactes tant que
    # la courbe de progression + les bonus de nœuds exacts ne sont pas décodés.
    names=sorted(set((x.get('name_candidate') or x.get('hero_name')) for x in rows if (x.get('name_candidate') or x.get('hero_name'))))
    exact=sum(1 for x in rows if str(x.get('config_id') or '') in HERO_PROGRESSION)
    # V10.87: "Mettre à jour ma box" met réellement à jour les stats sauvegardées.
    # On conserve niveaux de skills / Titan via apply_box_profile(), mais on remplace les anciennes
    # stats devenues obsolètes (ex. Mana Hall encore à 3% dans un profil sauvegardé).
    profiles_updated=0
    for hero_name in names:
        try:
            rr=apply_box_profile(hero_name)
            if rr and rr.get('ok'): profiles_updated+=1
        except Exception:
            pass
    return {'imported':imported,'mapped':mapped,'relics_imported':relic_imported,'profiles_updated':profiles_updated,
            'unique_heroes':len(names),'progression_stats_applied':bool(exact),'exact_progression_instances':exact,
            'hall_bonuses_imported':len(decoded.get('hall_bonuses') or [])}

RELIC_STAT_NAMES = {1:'ATQ',2:'DEF',3:'PV',4:'ATQ %',5:'DEF %',6:'PV %',7:'Taux crit',8:'Dég crit',9:'PRÉ',10:'RÉS',11:'VIT déplacement',12:'VIT combo',13:'VIT compétence',14:'RÉCUP compétence',15:'Gén mana',16:'Instinct'}

def _box_relic_rows(hero_inventory_id):
    rows=q('SELECT * FROM box_relics WHERE equipped_hero_id=? ORDER BY slot,inventory_id',(hero_inventory_id,))
    for r in rows:
        try:r['stats']=json.loads(r.get('stats_json') or '[]')
        except:r['stats']=[]
    return rows


# Relic set IDs recovered from the game RelicSet enum. Public set names/effects
# follow the current Invokers relic guide. A 5-piece set ALSO grants its 3-piece tier.
def _load_relic_static_source():
    """Load relic configuration extracted from StaticRelicData."""
    with open(RELIC_STATIC_FILE,'r',encoding='utf-8') as f:
        d=json.load(f)
    sets={int(k):v for k,v in (d.get('sets') or {}).items()}
    stages={int(rank):{int(stat):vals for stat,vals in stats.items()}
            for rank,stats in (d.get('substat_stage') or {}).items()}
    rolls=tuple(float(x) for x in (d.get('roll_strengths') or []))
    initial={int(k):int(v) for k,v in (d.get('initial_substats_by_rarity') or {}).items()}
    if not sets or not stages or not rolls or not initial:
        raise RuntimeError('StaticRelicData extraction is empty')
    return sets,stages,rolls,initial

RELIC_SET_INFO, RELIC_SUBSTAT_STAGE, RELIC_ROLL_STRENGTHS, RELIC_INITIAL_SUBS = _load_relic_static_source()

def _relic_upgrade_events(rarity, level):
    initial=RELIC_INITIAL_SUBS.get(int(rarity or 0),0)
    thresholds=max(0,min(4,int(level or 0)//5))
    unlocks=max(0,min(thresholds,4-initial))
    return max(0,thresholds-unlocks), min(4,initial+thresholds)

def _roll_sequences(coeffs, upgrades):
    import itertools
    n=upgrades+1
    out=[]
    for rolls in itertools.product(RELIC_ROLL_STRENGTHS, repeat=n):
        v=sum(coeffs[i]*rolls[i] for i in range(n))
        out.append((v,rolls))
    return out

def _best_substat_fit(rank, stat_id, value, max_upgrades):
    coeffs=(RELIC_SUBSTAT_STAGE.get(int(rank or 0)) or {}).get(int(stat_id or 0))
    if not coeffs:return None
    best=None
    for k in range(max_upgrades+1):
        for v,rolls in _roll_sequences(coeffs,k):
            err=abs(float(value)-v)
            # percentages display to 2 decimals, flat stats usually integer; allow display rounding noise.
            tol=0.011 if int(stat_id) in (4,5,6,7,8) else 0.51
            score=(0 if err<=tol else err, err, k)
            if best is None or score<best[0]: best=(score,k,v,rolls,err)
    if not best:return None
    _,k,v,rolls,err=best
    vals=[x[0] for x in _roll_sequences(coeffs,k)]
    percentile=100.0*sum(1 for x in vals if x<=v+1e-9)/len(vals) if vals else 0
    return {'upgrades':k,'expected':v,'error':err,'rolls':list(rolls),'roll_score':100*sum(rolls)/len(rolls),'percentile':percentile}

def _quality_percentile_from_rolls(rolls):
    # Exact CDF of the mean of N iid {70,80,90,100}% rolls, via DP (no 4^N explosion).
    n=len(rolls)
    if not n:return None
    obs=sum(round(x*10) for x in rolls)
    dist={0:1}
    for _ in range(n):
        nd={}
        for total,count in dist.items():
            for v in (7,8,9,10): nd[total+v]=nd.get(total+v,0)+count
        dist=nd
    denom=4**n
    return 100.0*sum(c for total,c in dist.items() if total<=obs)/denom

def relic_roll_potential(name,boss_res=0):
    hero=box_hero_for_name(name)
    if not hero:return {'error':'Héros absent de la box'}
    inv=int(hero.get('inventory_id') or 0)
    relics=_box_relic_rows(inv)
    rows=[]; all_rolls=[]; supported=0
    for r in relics:
        rank=int(r.get('stars') or r.get('rank') or 0); rarity=int(r.get('rarity') or 0); level=int(r.get('level') or 0)
        total_upgrades, expected_sub_count=_relic_upgrade_events(rarity,level)
        subs=[st for st in (r.get('stats') or []) if int(st.get('position') or 0)>1]
        # Jointly assign upgrade counts so their sum matches the number of upgrade events.
        fits=[]
        if rank in RELIC_SUBSTAT_STAGE and subs:
            import itertools
            choices=[]
            for st in subs:
                byk=[]
                for k in range(total_upgrades+1):
                    f=_best_substat_fit(rank,int(st.get('stat_id') or 0),num(st.get('value')),k)
                    if f and f['upgrades']==k: byk.append((k,f))
                choices.append(byk)
            best_combo=None
            if all(choices):
                for combo in itertools.product(*choices):
                    if sum(x[0] for x in combo)!=total_upgrades: continue
                    err=sum(x[1]['error'] for x in combo)
                    if best_combo is None or err<best_combo[0]: best_combo=(err,combo)
            if best_combo:
                for st,(_,f) in zip(subs,best_combo[1]):
                    fits.append({'stat_id':int(st.get('stat_id') or 0),'stat':st.get('stat'),'value':num(st.get('value')),**f})
                    all_rolls.extend(f['rolls'])
                supported+=1
        rolls=[x for f in fits for x in f['rolls']]
        pct=_quality_percentile_from_rolls(rolls) if rolls else None
        rows.append({'inventory_id':r.get('inventory_id'),'slot':r.get('slot'),'rank':rank,'rarity':rarity,'level':level,'set_id':r.get('set_id'),
                     'set_name':(RELIC_SET_INFO.get(int(r.get('set_id') or 0)) or {}).get('name'),'upgrade_events':total_upgrades,
                     'expected_sub_count':expected_sub_count,'substats':fits,'roll_score':(100*sum(rolls)/len(rolls) if rolls else None),'percentile':pct,
                     'supported':bool(fits)})
    overall=_quality_percentile_from_rolls(all_rolls) if all_rolls else None
    avg=100*sum(all_rolls)/len(all_rolls) if all_rolls else None

    # HERO-SPECIFIC COLLECTION FIT.
    # For every equipped slot, compare the current relic with every relic of the same slot in the user's
    # imported collection. The other seven equipped pieces stay fixed, so 3p/5p set thresholds are respected.
    # This is deliberately a fast proxy percentile; the full relic optimizer still uses real combat simulation
    # to decide final DPS winners.
    p=profile_for(name); saved=has_saved_profile(name)
    raw={k:num(p.get(k)) for k in ('atk','crit_rate','crit_dmg','accuracy','resistance','combo_speed','skill_speed','skill_recovery','mana_gen')}
    naked=_stats_without_relics(name,raw,relics,saved)
    all_collection=_optimizer_relic_rows(inv,'all')
    byslot={i:[] for i in range(1,9)}
    for rr in all_collection:
        sl=int(rr.get('slot') or 0)
        if sl in byslot: byslot[sl].append(rr)
    current_by_slot={int(r.get('slot') or 0):r for r in relics}
    fit_by_id={}
    slot_pcts=[]; near_best=[]
    for sl,cur in current_by_slot.items():
        pool=byslot.get(sl) or []
        if not pool: continue
        base7=[x for x in relics if int(x.get('slot') or 0)!=sl]
        scored=[]
        for cand in pool:
            build=base7+[cand]
            b=_relic_total_bonus(build)
            st=_stats_with_relic_bonus(naked,b)
            score=_relic_proxy_score(st,float(boss_res or 0))
            scored.append((score,int(cand.get('inventory_id') or 0)))
        scored.sort(key=lambda x:x[0])
        cid=int(cur.get('inventory_id') or 0)
        cur_score=next((x[0] for x in scored if x[1]==cid),None)
        if cur_score is None: continue
        n=len(scored)
        pct=100.0*sum(1 for sc,_ in scored if sc<=cur_score+1e-12)/n
        rank_desc=1+sum(1 for sc,_ in scored if sc>cur_score+1e-12)
        best=max(sc for sc,_ in scored)
        worst=min(sc for sc,_ in scored)
        rel=100.0 if best<=worst+1e-12 else 100.0*(cur_score-worst)/(best-worst)
        best_ratio=100.0*cur_score/best if best>0 else 100.0
        fit_by_id[cid]={'hero_percentile':pct,'hero_slot_rank':rank_desc,'hero_slot_total':n,
                        'hero_fit_score':rel,'hero_best_ratio':best_ratio,'hero_proxy':cur_score,'hero_best_proxy':best}
        slot_pcts.append(pct); near_best.append(best_ratio)
    for row in rows:
        row.update(fit_by_id.get(int(row.get('inventory_id') or 0),{}))
    hero_pct=(sum(slot_pcts)/len(slot_pcts)) if slot_pcts else None
    hero_best=(sum(near_best)/len(near_best)) if near_best else None
    return {'hero':name,'inventory_id':hero.get('inventory_id'),'relic_count':len(relics),'supported_relics':supported,
            'rolls_count':len(all_rolls),'roll_score':avg,'percentile':overall,'relics':rows,
            'hero_percentile':hero_pct,'hero_best_ratio':hero_best,'boss_res':float(boss_res or 0),
            'scope':'Qualité pure des jets + pertinence de chaque relique pour ce héros dans ta collection.',
            'limitations':['Calcul exact des rolls activé pour les reliques 5★ et 6★.',
                           'Le percentile de rolls mesure uniquement la qualité 70/80/90/100.',
                           'Le percentile héros compare chaque relique équipée aux reliques du même slot de ta collection, en gardant les 7 autres pièces fixes et en tenant compte des bonus de set.',
                           'Le percentile héros utilise le proxy DPS rapide de Smishie’s Lab; l’Optimiseur de reliques reste la référence finale car ses meilleurs builds sont validés par la simulation de combat.']}

def _zero_relic_bonus():
    return {'atk_flat':0.0,'atk_pct':0.0,'crit_rate':0.0,'crit_dmg':0.0,'accuracy':0.0,'resistance':0.0,
            'combo_points':0.0,'skill_speed_points':0.0,'skill_recovery_points':0.0,'mana_points':0.0,
            'hp_flat':0.0,'def_flat':0.0,'hp_pct':0.0,'def_pct':0.0,'instinct':0.0,
            'unapplied':{},'set_counts':{},'set_bonuses':[]}

def _set_bonus_summary(relics):
    counts={}
    for r in relics or []:
        sid=int(r.get('set_id') or 0)
        if sid:
            counts[sid]=counts.get(sid,0)+1
    out=_zero_relic_bonus(); out['set_counts']=counts
    for sid,n in counts.items():
        info=RELIC_SET_INFO.get(sid)
        if not info: continue
        applied=[]
        if n>=3:
            for k,v in info.get('three',{}).items(): out[k]=num(out.get(k))+num(v)
            applied.append('3p')
        if n>=5:
            for k,v in info.get('five',{}).items(): out[k]=num(out.get(k))+num(v)
            applied.append('5p')
        if applied:
            out['set_bonuses'].append({'set_id':sid,'name':info['name'],'pieces':n,'tiers':applied,'total':info.get('total'),'note':info.get('note'),'tolerance':info.get('tolerance')})
    return out

def _relic_total_bonus(relics):
    direct=_relic_bonus_summary(relics)
    sets=_set_bonus_summary(relics)
    out=_zero_relic_bonus()
    for k in ('atk_flat','atk_pct','crit_rate','crit_dmg','accuracy','resistance','combo_points','skill_speed_points','skill_recovery_points','mana_points','hp_flat','def_flat','hp_pct','def_pct','instinct'):
        out[k]=num(direct.get(k))+num(sets.get(k))
    out['unapplied']=dict(direct.get('unapplied') or {})
    out['set_counts']=sets.get('set_counts',{})
    out['set_bonuses']=sets.get('set_bonuses',[])
    return out

def _relic_bonus_summary(relics):
    b=_zero_relic_bonus()
    for r in relics or []:
        for st in r.get('stats') or []:
            sid=int(st.get('stat_id') or 0); v=num(st.get('value'))
            if sid==1:b['atk_flat']+=v
            elif sid==2:b['def_flat']+=v
            elif sid==3:b['hp_flat']+=v
            elif sid==4:b['atk_pct']+=v/100.0
            elif sid==5:b['def_pct']+=v/100.0
            elif sid==6:b['hp_pct']+=v/100.0
            elif sid==7:b['crit_rate']+=v/100.0
            elif sid==8:b['crit_dmg']+=v/100.0
            elif sid==9:b['accuracy']+=v
            elif sid==10:b['resistance']+=v
            elif sid==12:b['combo_points']+=v
            elif sid==13:b['skill_speed_points']+=v
            elif sid==14:b['skill_recovery_points']+=v
            elif sid==15:b['mana_points']+=v
            else:
                key=RELIC_STAT_NAMES.get(sid,str(sid)); b['unapplied'][key]=b['unapplied'].get(key,0)+v
    return b

def box_build_for_instance(name,hero_instance):
    if not hero_instance:return None
    h=hero_row(name) or {}; relics=_box_relic_rows(hero_instance.get('inventory_id')); relic_b=_relic_total_bonus(relics)
    hall_b=_arena_hall_bonus_for_hero(name)
    # V10.87: la Salle des trophées fait bien partie des stats finales affichées.
    # Le bug venait du mapping Element: Sarienne est Terre et PlayerArena utilise Element=2 pour Terre.
    b=_bonus_add(relic_b,hall_b)
    cfg=HERO_PROGRESSION.get(str(hero_instance.get('config_id') or ''))
    if cfg:
        rank=int(hero_instance.get('rank') or 0); level=int(hero_instance.get('level') or 0); curve=ASCENSION_MULTIPLIERS.get(rank) or []
        if 1 <= level <= len(curve):
            mult=curve[level-1]; base=cfg['base']; awb=cfg.get('awake_base') or {}
            awb_recovery=num(awb.get('skill_recovery_points'))
            naked={'health':round((num(base.get('health'))+num(awb.get('health')))*10*mult),
                   'atk':round((num(base.get('atk'))+num(awb.get('atk')))*mult),
                   'defense':round((num(base.get('defense'))+num(awb.get('defense')))*mult),
                   'run_speed':num(base.get('run_speed'))+num(awb.get('run_speed')),
                   'crit_rate':num(base.get('crit_rate'))+num(awb.get('crit_rate')),
                   'crit_dmg':num(base.get('crit_dmg'))+num(awb.get('crit_dmg')),
                   'accuracy':num(base.get('accuracy'))+num(awb.get('accuracy')),
                   'resistance':num(base.get('resistance'))+num(awb.get('resistance')),
                   'instinct':num(base.get('instinct'))+num(awb.get('instinct')),
                   'combo_speed':combo_points_to_pct(num(base.get('combo_points'))+num(awb.get('combo_points'))),
                   'skill_speed':skill_points_to_pct(num(base.get('skill_speed_points'))+num(awb.get('skill_speed_points'))),
                   'skill_recovery':recovery_points_to_pct(num(base.get('skill_recovery_points'))+awb_recovery),
                   'mana_gen':mana_points_to_pct(num(base.get('mana_points'))+num(awb.get('mana_points')))}
            raw_node_ids=hero_instance.get('awake_node_ids') or []
            try: node_ids=json.loads(raw_node_ids) if isinstance(raw_node_ids,str) else list(raw_node_ids)
            except Exception: node_ids=[]
            node_breakdown={'health_pct':0.0,'atk_pct':0.0,'def_pct':0.0,'run_speed':0.0,'crit_rate':0.0,'crit_dmg':0.0,
                            'accuracy':0.0,'resistance':0.0,'instinct':0.0,'combo_points':0.0,'skill_speed_points':0.0,
                            'skill_recovery_points':0.0,'mana_points':0.0}
            for node_id in node_ids:
                n=(cfg.get('nodes') or {}).get(int(node_id)) or {}
                for _k in node_breakdown:
                    node_breakdown[_k]+=num(n.get(_k))
                # AwakeNode % bonuses are stored as additions based on the character's
                # base stat, not on the already level-scaled value. Multiplying them again by
                # the ascension curve massively overstates high-level heroes (notably Ruthos).
                naked['health']+=num(base.get('health'))*10*num(n.get('health_pct'))
                naked['atk']+=num(base.get('atk'))*num(n.get('atk_pct'))
                naked['defense']+=num(base.get('defense'))*num(n.get('def_pct'))
                naked['run_speed']+=num(n.get('run_speed')); naked['crit_rate']+=num(n.get('crit_rate'))
                naked['crit_dmg']+=num(n.get('crit_dmg')); naked['accuracy']+=num(n.get('accuracy'))
                naked['resistance']+=num(n.get('resistance')); naked['instinct']+=num(n.get('instinct'))
                naked['combo_speed']=combo_points_to_pct(combo_pct_to_points(naked['combo_speed'])+num(n.get('combo_points')))
                naked['skill_speed']=skill_points_to_pct(skill_pct_to_points(naked['skill_speed'])+num(n.get('skill_speed_points')))
                naked['skill_recovery']=recovery_points_to_pct(recovery_pct_to_points(naked['skill_recovery'])+num(n.get('skill_recovery_points')))
                naked['mana_gen']=mana_points_to_pct(mana_pct_to_points(naked['mana_gen'])+num(n.get('mana_points')))
            naked['health']=round(naked['health']); naked['atk']=round(naked['atk']); naked['defense']=round(naked['defense'])
            final=_stats_with_relic_bonus(naked,b)
            final.update({'health':round(naked['health']*(1+num(b.get('hp_pct')))+num(b.get('hp_flat'))),
                          'defense':round(naked['defense']*(1+num(b.get('def_pct')))+num(b.get('def_flat'))),
                          'run_speed':naked['run_speed'],'instinct':naked['instinct']+b['instinct']})
            return {'pre_relic_stats':naked,'final_stats':final,'reference_stats_max':None,'relic_bonus':relic_b,'hall_bonus':hall_b,'combined_external_bonus':b,'relics':relics,
                    'relic_count':len(relics),'inventory_id':hero_instance.get('inventory_id'),'progression_exact':True,
                    'level_multiplier':mult,'awake_nodes_applied':len(node_ids),
                    'stat_breakdown':{
                        'base':dict(base),
                        'awake_nodes':node_breakdown,
                        'relics':relic_b,
                        'hall':hall_b,
                        'naked_after_nodes':dict(naked),
                        'final':dict(final)
                    }}
    base_atk=num(h.get('atk')); base_combo=num(h.get('combo_speed')); base_speed=num(h.get('skill_speed')); base_rec=num(h.get('skill_recovery'))
    final={
        'atk':base_atk*(1+b['atk_pct'])+b['atk_flat'],
        'crit_rate':num(h.get('crit_rate'))+b['crit_rate'],
        'crit_dmg':num(h.get('crit_dmg'))+b['crit_dmg'],
        'accuracy':num(h.get('accuracy'))+b['accuracy'],
        'resistance':num(h.get('resistance'))+b['resistance'],
        'combo_speed':combo_points_to_pct(combo_pct_to_points(base_combo)+b['combo_points']),
        'skill_speed':skill_points_to_pct(skill_pct_to_points(base_speed)+b['skill_speed_points']),
        'skill_recovery':recovery_points_to_pct(recovery_pct_to_points(base_rec)+b['skill_recovery_points']),
        'mana_gen':mana_points_to_pct(mana_pct_to_points(num(h.get('mana_gen')))+b['mana_points']),
    }
    return {'final_stats':None,'reference_stats_max':final,'relic_bonus':relic_b,'hall_bonus':hall_b,'combined_external_bonus':b,'relics':relics,'relic_count':len(relics),
            'inventory_id':hero_instance.get('inventory_id'),'progression_exact':False}

def box_hero_for_name(name):
    ensure_box_tables()
    r=one('SELECT * FROM box_heroes WHERE lower(hero_name)=lower(?) ORDER BY rank DESC, level DESC, equipped_relic_count DESC, total_experience DESC LIMIT 1',(name,))
    if not r:return None
    c=one('SELECT COUNT(*) AS n FROM box_heroes WHERE lower(hero_name)=lower(?)',(name,))
    r['copies']=int((c or {}).get('n') or 1)
    for k in ('skill_levels_raw','relics_by_slot','awake_node_ids'):
        try:r[k]=json.loads(r.get(k) or '{}')
        except:r[k]={}
    build=box_build_for_instance(name,r)
    if build:r['box_build']=build
    return r

def box_relic_inventory(slot=None,set_id=None,equipped=None,stat_id=None,limit=500):
    ensure_box_tables(); where=[]; args=[]
    if slot not in (None,'','all'):
        where.append('r.slot=?'); args.append(int(slot))
    if set_id not in (None,'','all'):
        where.append('r.set_id=?'); args.append(int(set_id))
    if equipped=='yes': where.append('r.equipped_hero_id IS NOT NULL')
    elif equipped=='no': where.append('r.equipped_hero_id IS NULL')
    sql="SELECT r.*,h.hero_name AS equipped_hero_name FROM box_relics r LEFT JOIN box_heroes h ON h.inventory_id=r.equipped_hero_id"
    if where: sql+=' WHERE '+' AND '.join(where)
    sql+=' ORDER BY COALESCE(r.stars,0) DESC, COALESCE(r.level,0) DESC, r.slot, r.inventory_id LIMIT ?'
    args.append(max(1,min(int(limit or 500),5000)))
    rows=q(sql,tuple(args)); out=[]
    for r in rows:
        try: stats=json.loads(r.get('stats_json') or '[]')
        except: stats=[]
        if stat_id not in (None,'','all') and not any(int(x.get('stat_id') or 0)==int(stat_id) for x in stats):
            continue
        r['stats']=stats; r.pop('stats_json',None); r['set_name']=(RELIC_SET_INFO.get(int(r.get('set_id') or 0)) or {}).get('name'); out.append(r)
    counts=one("SELECT COUNT(*) total, SUM(CASE WHEN equipped_hero_id IS NOT NULL THEN 1 ELSE 0 END) equipped, SUM(CASE WHEN equipped_hero_id IS NULL THEN 1 ELSE 0 END) unequipped FROM box_relics") or {'total':0,'equipped':0,'unequipped':0}
    sets=[r['set_id'] for r in q('SELECT DISTINCT set_id FROM box_relics WHERE set_id IS NOT NULL ORDER BY set_id')]
    return {'rows':out,'counts':counts,'sets':sets,'shown':len(out)}



def _optimizer_relic_rows(hero_inventory_id=None, mode='all'):
    """Return every decoded relic usable by the optimizer, with owner metadata."""
    ensure_box_tables()
    sql="SELECT r.*,h.hero_name AS equipped_hero_name FROM box_relics r LEFT JOIN box_heroes h ON h.inventory_id=r.equipped_hero_id"
    args=[]
    if mode=='free':
        sql+=' WHERE r.equipped_hero_id IS NULL OR r.equipped_hero_id=?'
        args.append(int(hero_inventory_id or -1))
    sql+=' ORDER BY r.slot, COALESCE(r.stars,0) DESC, COALESCE(r.level,0) DESC, r.inventory_id'
    rows=q(sql,tuple(args)); out=[]
    for r in rows:
        try:r['stats']=json.loads(r.get('stats_json') or '[]')
        except:r['stats']=[]
        r.pop('stats_json',None)
        r['set_name']=(RELIC_SET_INFO.get(int(r.get('set_id') or 0)) or {}).get('name')
        out.append(r)
    return out

def _stats_without_relics(name, raw_profile, current_relics, profile_is_saved):
    """Infer the hero stats before relics. If no personal saved profile exists, use the DB reference stats."""
    h=hero_row(name) or {}
    if not profile_is_saved:
        return {
            'atk':num(h.get('atk')),'crit_rate':num(h.get('crit_rate')),'crit_dmg':num(h.get('crit_dmg')),
            'accuracy':num(h.get('accuracy')),'resistance':num(h.get('resistance')),
            'combo_speed':num(h.get('combo_speed')),'skill_speed':num(h.get('skill_speed')),
            'skill_recovery':num(h.get('skill_recovery')),'mana_gen':num(h.get('mana_gen')),
        }
    b=_relic_total_bonus(current_relics)
    atk=max(1.0,(num(raw_profile.get('atk'))-b['atk_flat'])/max(.01,1+b['atk_pct']))
    return {
        'atk':atk,
        'crit_rate':max(0.0,num(raw_profile.get('crit_rate'))-b['crit_rate']),
        'crit_dmg':max(0.0,num(raw_profile.get('crit_dmg'))-b['crit_dmg']),
        'accuracy':num(raw_profile.get('accuracy'))-b['accuracy'],
        'resistance':num(raw_profile.get('resistance'))-b['resistance'],
        'combo_speed':combo_points_to_pct(max(0.0,combo_pct_to_points(num(raw_profile.get('combo_speed')))-b['combo_points'])),
        'skill_speed':skill_points_to_pct(max(0.0,skill_pct_to_points(num(raw_profile.get('skill_speed')))-b['skill_speed_points'])),
        'skill_recovery':recovery_points_to_pct(max(0.0,recovery_pct_to_points(num(raw_profile.get('skill_recovery')))-b['skill_recovery_points'])),
        'mana_gen':mana_points_to_pct(max(0.0,mana_pct_to_points(num(raw_profile.get('mana_gen')))-b['mana_points'])),
    }

def _stats_with_relic_bonus(naked,b):
    return {
        'atk':max(1.0,num(naked.get('atk'))*(1+b['atk_pct'])+b['atk_flat']),
        'crit_rate':max(0.0,num(naked.get('crit_rate'))+b['crit_rate']),
        'crit_dmg':max(0.0,num(naked.get('crit_dmg'))+b['crit_dmg']),
        'accuracy':num(naked.get('accuracy'))+b['accuracy'],
        'resistance':num(naked.get('resistance'))+b['resistance'],
        'combo_speed':combo_points_to_pct(max(0.0,combo_pct_to_points(num(naked.get('combo_speed')))+b['combo_points'])),
        'skill_speed':skill_points_to_pct(max(0.0,skill_pct_to_points(num(naked.get('skill_speed')))+b['skill_speed_points'])),
        'skill_recovery':recovery_points_to_pct(max(0.0,recovery_pct_to_points(num(naked.get('skill_recovery')))+b['skill_recovery_points'])),
        'mana_gen':mana_points_to_pct(max(0.0,mana_pct_to_points(num(naked.get('mana_gen')))+b['mana_points'])),
    }

def _relic_proxy_score(st,boss_res=0):
    """Fast nonlinear proxy only for pruning. Final ranking always uses the real combat simulator."""
    cr=max(0.0,min(1.0,num(st.get('crit_rate')))); cd=max(0.0,num(st.get('crit_dmg')))
    atk=max(1.0,num(st.get('atk'))); combo=max(0.0,num(st.get('combo_speed')))
    speed=max(0.0,num(st.get('skill_speed'))); rec=max(0.0,num(st.get('skill_recovery'))); mana=max(0.0,num(st.get('mana_gen')))
    # PRE only matters around the boss resistance threshold; use a bounded incentive.
    pre=num(st.get('accuracy')); pre_factor=1.0
    if boss_res>0:
        gap=max(-120.0,min(120.0,pre-boss_res)); pre_factor=1.0+0.04*((gap+120.0)/240.0)
    return atk*(1+cr*cd)*(1+.65*combo+.40*speed+.55*rec+.30*mana)*pre_factor

def _bonus_add(a,b):
    out={}
    for k in ('atk_flat','atk_pct','crit_rate','crit_dmg','accuracy','resistance','combo_points','skill_speed_points','skill_recovery_points','mana_points','hp_flat','def_flat','hp_pct','def_pct','instinct'):
        out[k]=num(a.get(k))+num(b.get(k))
    out['unapplied']={}
    return out

def optimize_relics_for_dps(name,duration=120,boss_def=1320,boss_res=0,boss_hp=0,boss_atk=0,boss_element='Neutre',mode='all',protected_heroes=None,top_per_slot=28,beam_width=350,sim_candidates=60):
    hero=box_hero_for_name(name)
    if not hero:
        return {'error':'Ce héros n\'est pas présent dans la box importée.'}
    inv=int(hero.get('inventory_id') or 0)
    current_relics=_box_relic_rows(inv)
    p=profile_for(name); saved=has_saved_profile(name)
    raw={k:num(p.get(k)) for k in ('atk','crit_rate','crit_dmg','accuracy','resistance','combo_speed','skill_speed','skill_recovery','mana_gen')}
    naked=_stats_without_relics(name,raw,current_relics,saved)
    levels=profile_levels(p)

    # Current build: saved personal stats are authoritative if present; otherwise reconstruct from reference+naked relic bonuses.
    if saved:
        current_raw=raw
    else:
        current_raw=_stats_with_relic_bonus(naked,_relic_total_bonus(current_relics))
    current_stats=apply_titan(name,current_raw,p.get('titan') or 'Aucun',p.get('titan_stars') or 0,bool(p.get('titan_dungeon')))
    current_sim=simulate_combat(name,levels,duration,boss_def,boss_res,boss_hp,boss_atk,boss_element,comparison_mode=True,**final_to_build(name,current_stats))

    # Sildrea is unusually sensitive to Crit Rate / Skill Speed / Recovery because crits during
    # her multi-hit Ultimate trigger cooldown reductions. Keep a much wider search frontier.
    if str(name).strip().lower()=='sildrea':
        top_per_slot=max(int(top_per_slot),42)
        beam_width=max(int(beam_width),1400)
        sim_candidates=max(int(sim_candidates),280)
    all_relics=_optimizer_relic_rows(inv,mode)
    protected={str(x or '').strip().lower() for x in (protected_heroes or []) if str(x or '').strip()}
    protected.discard(str(name or '').strip().lower())
    if protected:
        all_relics=[r for r in all_relics if not (r.get('equipped_hero_name') and str(r.get('equipped_hero_name')).strip().lower() in protected)]
    byslot={i:[] for i in range(1,9)}
    current_ids={int(r.get('inventory_id') or 0) for r in current_relics}
    for r in all_relics:
        sl=int(r.get('slot') or 0)
        if sl not in byslot: continue
        rb=_relic_bonus_summary([r]); r['_bonus']=rb
        one_stats=_stats_with_relic_bonus(naked,rb)
        r['_proxy']=_relic_proxy_score(one_stats,boss_res)
        byslot[sl].append(r)
    missing=[sl for sl,rs in byslot.items() if not rs]
    if missing:
        return {'error':'Aucune relique disponible pour le(s) slot(s) '+', '.join(map(str,missing))+'. Importe d\'abord PlayerRelicsModel.dat.'}

    # Prune each slot, but always retain the relic currently worn in that slot.
    for sl in byslot:
        rs=sorted(byslot[sl],key=lambda r:r['_proxy'],reverse=True)
        keep=rs[:max(8,int(top_per_slot))]
        seen={int(x.get('inventory_id') or 0) for x in keep}
        for r in rs:
            if int(r.get('inventory_id') or 0) in current_ids and int(r.get('inventory_id') or 0) not in seen:
                keep.append(r); seen.add(int(r.get('inventory_id') or 0))
        # Preserve several strong pieces from every set so a 3p/5p synergy is not pruned too early.
        per_set={}
        for r in rs:
            sid=int(r.get('set_id') or 0)
            if sid not in RELIC_SET_INFO: continue
            if per_set.get(sid,0)>=3: continue
            rid=int(r.get('inventory_id') or 0)
            if rid not in seen:
                keep.append(r); seen.add(rid)
            per_set[sid]=per_set.get(sid,0)+1
        byslot[sl]=keep

    # Beam search is SET-AWARE: crossing 3p/5p thresholds immediately changes the score.
    beam=[(0.0,[],_zero_relic_bonus())]
    for sl in range(1,9):
        nxt=[]
        for _,chosen,_agg in beam:
            for r in byslot[sl]:
                newchosen=chosen+[r]
                nb=_relic_total_bonus(newchosen); st=_stats_with_relic_bonus(naked,nb)
                score=_relic_proxy_score(st,boss_res)
                nxt.append((score,newchosen,nb))
        nxt.sort(key=lambda x:x[0],reverse=True)
        beam=nxt[:max(50,int(beam_width))]

    # Real combat simulation decides the winner among the best proxy combinations.
    tested=[]
    for proxy,chosen,agg in beam[:max(10,int(sim_candidates))]:
        rawst=_stats_with_relic_bonus(naked,agg)
        st=apply_titan(name,rawst,p.get('titan') or 'Aucun',p.get('titan_stars') or 0,bool(p.get('titan_dungeon')))
        sim=simulate_combat(name,levels,duration,boss_def,boss_res,boss_hp,boss_atk,boss_element,comparison_mode=True,**final_to_build(name,st))
        if sim:
            tested.append({'dps':sim['dps'],'total_damage':sim['total_damage'],'stats':st,'raw_stats':rawst,'relics':chosen,'bonus':agg,'proxy':proxy})
    # Hard safety rule: the currently equipped build is itself a finalist, evaluated by the
    # exact same simulator. The optimizer can therefore NEVER recommend a lower-DPS build.
    curdps=(current_sim or {}).get('dps',0.0)
    if current_sim and current_relics:
        tested.append({'dps':curdps,'total_damage':current_sim.get('total_damage',0.0),'stats':current_stats,
                       'raw_stats':current_raw,'relics':current_relics,'bonus':_relic_total_bonus(current_relics),
                       'proxy':_relic_proxy_score(current_raw,boss_res),'is_current':True})
    tested.sort(key=lambda x:x['dps'],reverse=True)
    if not tested:return {'error':'Aucune combinaison n\'a pu être simulée.'}
    best=tested[0]
    # Guard against floating-point / stochastic edge cases.
    if best.get('dps',0.0) < curdps - 1e-9:
        best=next((x for x in tested if x.get('is_current')),best)
    best_ids={int(r.get('inventory_id') or 0) for r in best['relics']}
    current_by_slot={int(r.get('slot') or 0):r for r in current_relics}
    rows=[]
    for r in sorted(best['relics'],key=lambda x:int(x.get('slot') or 0)):
        rr={k:v for k,v in r.items() if not k.startswith('_')}
        sl=int(rr.get('slot') or 0); old=current_by_slot.get(sl)
        rr['current_id']=int(old.get('inventory_id') or 0) if old else None
        rr['change']=rr['current_id']!=int(rr.get('inventory_id') or 0)
        rows.append(rr)
    # Classement des meilleures COMPOSITIONS DE SETS réellement trouvées dans la collection.
    # On garde le meilleur build simulé pour chaque signature de sets afin d'éviter 20 variantes identiques.
    set_rankings=[]; seen_sigs=set()
    for cand in tested:
        counts={}
        for rr in cand.get('relics') or []:
            sid=int(rr.get('set_id') or 0); counts[sid]=counts.get(sid,0)+1
        active=[]; inactive=0
        for sid,n in sorted(counts.items(), key=lambda kv:(-kv[1], kv[0])):
            info=RELIC_SET_INFO.get(sid)
            if info and n>=3: active.append({'set_id':sid,'name':info['name'],'pieces':n,'tier':'5p' if n>=5 else '3p','effect':info.get('total') if n>=5 else None})
            else: inactive+=n
        sig=tuple((x['set_id'],x['pieces']) for x in active)+(('off',inactive),)
        if sig in seen_sigs: continue
        seen_sigs.add(sig)
        label=' + '.join(f"{x['name']} {x['tier']}" for x in active) or 'Aucun bonus de set actif'
        if inactive: label += f" + {inactive} pièce{'s' if inactive>1 else ''} libre{'s' if inactive>1 else ''}"
        set_rankings.append({'rank':len(set_rankings)+1,'label':label,'active_sets':active,'free_pieces':inactive,
                             'dps':cand['dps'],'gain_dps':cand['dps']-curdps,'gain_pct':(cand['dps']/curdps-1) if curdps else 0,
                             'relic_ids':[int(x.get('inventory_id') or 0) for x in cand.get('relics') or []]})
        if len(set_rankings)>=8: break
    return {
        'hero':name,'mode':mode,'inventory_id':inv,'profile_source':'fiche personnelle enregistrée' if saved else 'référence MAX (approximation)',
        'collection_relics':len(all_relics),'protected_heroes':sorted(protected),'candidates_per_slot':{str(k):len(v) for k,v in byslot.items()},'simulated_combinations':len(tested),
        'current':{'dps':curdps,'stats':current_stats,'relic_ids':sorted(current_ids),'sets':_relic_total_bonus(current_relics).get('set_bonuses',[])},
        'best':{'dps':best['dps'],'total_damage':best['total_damage'],'stats':best['stats'],'relics':rows,'bonus':best['bonus'],'sets':best['bonus'].get('set_bonuses',[])},
        'set_rankings':set_rankings,
        'gain_dps':best['dps']-curdps,'gain_pct':(best['dps']/curdps-1) if curdps else 0,'improved':best['dps']>curdps+1e-9,
        'limitations':['Le build actuel est toujours simulé comme candidat et sert de plancher DPS.','Voodoo, lifesteal Vampire, heal/shield Paragon, Move SPD et tolérances 3p ne gonflent pas artificiellement le DPS.','Les bonus 5p des sets de tolérance (+20% HP/ATQ/DEF) sont appliqués.']
    }

def _load_profile_store():
    try:
        if os.path.exists(PROFILE_JSON):
            with open(PROFILE_JSON,'r',encoding='utf-8') as f:
                d=json.load(f)
                return d if isinstance(d,dict) else {}
    except Exception: pass
    return {}

def _write_profile_store(store):
    os.makedirs(PROFILE_HOME,exist_ok=True)
    tmp=PROFILE_JSON+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f: json.dump(store,f,ensure_ascii=False,indent=2)
    os.replace(tmp,PROFILE_JSON)

def has_saved_profile(name):
    ensure_profile_table(); key=str(name or '').strip().lower()
    store=_load_profile_store()
    if any(str(k).lower()==key for k in store): return True
    return one('SELECT name FROM hero_profiles WHERE lower(name)=lower(?)',(name,)) is not None

def profile_for(name):
    ensure_profile_table()
    store=_load_profile_store(); key=str(name or '').strip().lower()
    h=hero_row(name) or {}
    for k,v in store.items():
        if k.lower()==key and isinstance(v,dict):
            out=dict(v); out['element']=normalize_element(out.get('element') or h.get('element')); out['_source']='saved'
            return out
    r=one('SELECT * FROM hero_profiles WHERE lower(name)=lower(?)',(name,))
    if r:
        # Migration automatique vers le stockage persistant hors du dossier de version.
        store[str(name)]=r; _write_profile_store(store); r['_source']='saved'
        return r
    # V10.68 : si la progression exacte de la box est disponible, elle devient le
    # build par défaut des simulations. On ne confond plus la référence MAX avec
    # les statistiques réelles de l'exemplaire possédé.
    try:
        bx=box_hero_for_name(name)
        bb=(bx or {}).get('box_build') or {}
        fs=bb.get('final_stats')
        if fs and bb.get('progression_exact'):
            return {
                'name':name,'atk':num(fs.get('atk')),'crit_rate':num(fs.get('crit_rate')),'crit_dmg':num(fs.get('crit_dmg')),
                'accuracy':num(fs.get('accuracy')),'resistance':num(fs.get('resistance')),'combo_speed':num(fs.get('combo_speed')),
                'skill_speed':num(fs.get('skill_speed')),'skill_recovery':num(fs.get('skill_recovery')),'mana_gen':num(fs.get('mana_gen')),
                'auto_level':7,'s1_level':7,'s2_level':7,'s3_level':7,'ult_level':7,'titan':'Aucun','titan_stars':0,'titan_dungeon':0,
                'element':normalize_element(h.get('element')),'_source':'box_exact'
            }
        if bx:
            source='box_unresolved'
        else:
            source='reference_max'
    except Exception:
        source='reference_max'
    return {
        'name':name,'atk':num(h.get('atk')),'crit_rate':num(h.get('crit_rate')),'crit_dmg':num(h.get('crit_dmg')),
        'accuracy':num(h.get('accuracy')),'resistance':num(h.get('resistance')),'combo_speed':num(h.get('combo_speed')),
        'skill_speed':num(h.get('skill_speed')),'skill_recovery':num(h.get('skill_recovery')),'mana_gen':num(h.get('mana_gen')),
        'auto_level':7,'s1_level':7,'s2_level':7,'s3_level':7,'ult_level':7,'titan':'Aucun','titan_stars':0,'titan_dungeon':0,
        'element':normalize_element(h.get('element')),'_source':source
    }

def save_profile(data):
    ensure_profile_table(); name=str(data.get('name') or '').strip()
    if not name: return False
    rec={'name':name,'atk':num(data.get('atk')),'crit_rate':num(data.get('crit_rate')),'crit_dmg':num(data.get('crit_dmg')),'accuracy':num(data.get('accuracy')),'resistance':num(data.get('resistance')),'combo_speed':num(data.get('combo_speed')),'skill_speed':num(data.get('skill_speed')),'skill_recovery':num(data.get('skill_recovery')),'mana_gen':num(data.get('mana_gen')),'auto_level':int(num(data.get('auto_level'),7)),'s1_level':int(num(data.get('s1_level'),7)),'s2_level':int(num(data.get('s2_level'),7)),'s3_level':int(num(data.get('s3_level'),7)),'ult_level':int(num(data.get('ult_level'),7)),'titan':str(data.get('titan') or 'Aucun'),'titan_stars':int(num(data.get('titan_stars'),0)),'titan_dungeon':1 if data.get('titan_dungeon') else 0,'element':normalize_element(data.get('element'))}
    vals=tuple(rec[k] for k in ('name','atk','crit_rate','crit_dmg','accuracy','resistance','combo_speed','skill_speed','skill_recovery','mana_gen','auto_level','s1_level','s2_level','s3_level','ult_level','titan','titan_stars','titan_dungeon','element'))
    with sqlite3.connect(DB) as con:
        con.execute('''INSERT INTO hero_profiles(name,atk,crit_rate,crit_dmg,accuracy,resistance,combo_speed,skill_recovery,mana_gen,skill_speed,auto_level,s1_level,s2_level,s3_level,ult_level,titan,titan_stars,titan_dungeon,element) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET atk=excluded.atk,crit_rate=excluded.crit_rate,crit_dmg=excluded.crit_dmg,accuracy=excluded.accuracy,resistance=excluded.resistance,combo_speed=excluded.combo_speed,skill_recovery=excluded.skill_recovery,mana_gen=excluded.mana_gen,skill_speed=excluded.skill_speed,auto_level=excluded.auto_level,s1_level=excluded.s1_level,s2_level=excluded.s2_level,s3_level=excluded.s3_level,ult_level=excluded.ult_level,titan=excluded.titan,titan_stars=excluded.titan_stars,titan_dungeon=excluded.titan_dungeon,element=excluded.element''', (rec['name'],rec['atk'],rec['crit_rate'],rec['crit_dmg'],rec['accuracy'],rec['resistance'],rec['combo_speed'],rec['skill_recovery'],rec['mana_gen'],rec['skill_speed'],rec['auto_level'],rec['s1_level'],rec['s2_level'],rec['s3_level'],rec['ult_level'],rec['titan'],rec['titan_stars'],rec['titan_dungeon'],rec['element']))
        con.execute('UPDATE heroes SET element=? WHERE lower(name)=lower(?)',(rec['element'],name))
        con.commit()
    store=_load_profile_store(); store[name]=rec; _write_profile_store(store)
    return True

def _box_skill_levels(hero_instance, fallback=None):
    """Convert PlayerHero SkillLevels into the five profile levels used by the simulator.

    PlayerHero v22 stores seven SkillKind entries. Mapping validated in-game:
    1=Auto, 3=S1, 4=S2, 5=S3, 2=Ult; 7 and 8 are corruption tolerances.

    The persisted value is a zero-based upgrade count (0..10), while the UI and
    coefficient tables use displayed skill levels 1..11, hence +1.
    Older snapshots using compact 0..4 or direct 1..5 levels remain supported.
    """
    fallback=fallback or {}
    raw=(hero_instance or {}).get('skill_levels_raw') or {}
    if isinstance(raw,str):
        try: raw=json.loads(raw)
        except Exception: raw={}
    vals={}
    for k,v in (raw or {}).items():
        try: vals[int(k)]=int(v)
        except Exception: pass

    names=['auto_level','s1_level','s2_level','s3_level','ult_level']
    out={n:int(num(fallback.get(n),7)) for n in names}
    keys=set(vals)

    # Current PlayerHero v22 format. Validated against Nirvelle in-game:
    # SkillKind 1=Auto, 3=S1, 4=S2, 5=S3, 2=Ultimate.
    # SkillKinds 7/8 are corruption tolerances and are handled separately.
    if {1,2,3,4,5}.issubset(keys):
        for n,k in zip(names,[1,3,4,5,2]):
            upgrade=vals.get(k)
            if upgrade is not None and 0<=upgrade<=10:
                out[n]=upgrade+1
        return out

    # Legacy format: zero-based slot ids with direct displayed levels.
    if keys and keys.issubset({0,1,2,3,4}):
        for n,k in zip(names,[0,1,2,3,4]):
            lv=vals.get(k)
            if lv is not None and 1<=lv<=11:
                out[n]=lv
        return out

    # Legacy format: one-based slot ids with direct displayed levels.
    if keys and keys.issubset({1,2,3,4,5}):
        for n,k in zip(names,[1,2,3,4,5]):
            lv=vals.get(k)
            if lv is not None and 1<=lv<=11:
                out[n]=lv
    return out

def apply_box_profile(name):
    """Replace one saved profile with the exact imported-box build, including imported skill levels while preserving Titan choices."""
    bx=box_hero_for_name(name)
    bb=(bx or {}).get('box_build') or {}
    fs=bb.get('final_stats')
    if not (fs and bb.get('progression_exact')):
        return {'ok':False,'error':'Aucune reconstruction exacte de box disponible pour ce héros.'}
    old=None
    store=_load_profile_store(); key=str(name or '').strip().lower()
    for k,v in store.items():
        if str(k).lower()==key and isinstance(v,dict):
            old=dict(v); break
    if old is None:
        old=one('SELECT * FROM hero_profiles WHERE lower(name)=lower(?)',(name,)) or {}
    h=hero_row(name) or {}
    imported_levels=_box_skill_levels(bx,old)
    rec={
        'name':name,
        'atk':num(fs.get('atk')),'crit_rate':num(fs.get('crit_rate')),'crit_dmg':num(fs.get('crit_dmg')),
        'accuracy':num(fs.get('accuracy')),'resistance':num(fs.get('resistance')),
        'combo_speed':num(fs.get('combo_speed')),'skill_speed':num(fs.get('skill_speed')),
        'skill_recovery':num(fs.get('skill_recovery')),'mana_gen':num(fs.get('mana_gen')),
        'auto_level':imported_levels['auto_level'],'s1_level':imported_levels['s1_level'],
        's2_level':imported_levels['s2_level'],'s3_level':imported_levels['s3_level'],
        'ult_level':imported_levels['ult_level'],
        'titan':str(old.get('titan') or 'Aucun'),'titan_stars':int(num(old.get('titan_stars'),0)),
        'titan_dungeon':1 if old.get('titan_dungeon') else 0,
        'element':normalize_element(old.get('element') or h.get('element'))
    }
    save_profile(rec)
    return {'ok':True,'profile':rec,'box_build':bb}

def profile_levels(p):
    return {'auto':int(p.get('auto_level') or 7),'s1':int(p.get('s1_level') or 7),'s2':int(p.get('s2_level') or 7),'s3':int(p.get('s3_level') or 7),'ult':int(p.get('ult_level') or 7)}

def _apply_hall_effective_stats(name,st):
    """Stats effectives avec Salle des trophées, sans modifier les stats de fiche."""
    out=dict(st); hb=_arena_hall_bonus_for_hero(name)
    out['atk']=num(out.get('atk'))*(1+num(hb.get('atk_pct')))
    out['crit_rate']=num(out.get('crit_rate'))+num(hb.get('crit_rate'))
    out['crit_dmg']=num(out.get('crit_dmg'))+num(hb.get('crit_dmg'))
    out['accuracy']=num(out.get('accuracy'))+num(hb.get('accuracy'))
    out['resistance']=num(out.get('resistance'))+num(hb.get('resistance'))
    out['combo_speed']=combo_points_to_pct(combo_pct_to_points(num(out.get('combo_speed')))+num(hb.get('combo_points')))
    out['skill_speed']=skill_points_to_pct(skill_pct_to_points(num(out.get('skill_speed')))+num(hb.get('skill_speed_points')))
    out['skill_recovery']=recovery_points_to_pct(recovery_pct_to_points(num(out.get('skill_recovery')))+num(hb.get('skill_recovery_points')))
    out['mana_gen']=mana_points_to_pct(mana_pct_to_points(num(out.get('mana_gen')))+num(hb.get('mana_points')))
    out['_hall_bonus']=hb
    return out

def profile_stats(name,p=None,include_hall=False):
    p=p or profile_for(name)
    st={'atk':num(p.get('atk')),'crit_rate':num(p.get('crit_rate')),'crit_dmg':num(p.get('crit_dmg')),'accuracy':num(p.get('accuracy')),'resistance':num(p.get('resistance')),'combo_speed':num(p.get('combo_speed')),'skill_speed':num(p.get('skill_speed')),'skill_recovery':num(p.get('skill_recovery')),'mana_gen':num(p.get('mana_gen'))}
    st=apply_titan(name,st,p.get('titan') or 'Aucun',p.get('titan_stars') or 0,bool(p.get('titan_dungeon')))
    return st

def num(v,default=0.0):
    try:
        if v is None or v=='': return default
        return float(str(v).replace(',','.'))
    except: return default

def parse_seconds(v,default=999.0):
    if v is None: return default
    if isinstance(v,(int,float)): return float(v)
    m=re.search(r'[-+]?\d+(?:[.,]\d+)?',str(v))
    return float(m.group(0).replace(',','.')) if m else default

def dmult(defense):
    d=max(0.0,float(defense)); return 1/(1+0.0001696*d+0.00000001245*d*d)

ELEMENT_ALIASES={
    'fire':'Feu','feu':'Feu','water':'Eau','eau':'Eau','wind':'Vent','vent':'Vent',
    'earth':'Terre','terre':'Terre','light':'Lumière','lumiere':'Lumière','lumière':'Lumière',
    'dark':'Ténèbres','tenebres':'Ténèbres','ténèbres':'Ténèbres','neutral':'Neutre','neutre':'Neutre',
    'astral':'Astral','':'Neutre',None:'Neutre'
}
ELEMENTS=('Neutre','Feu','Eau','Vent','Terre','Lumière','Ténèbres','Astral')
ELEMENT_BEATS={'Eau':'Feu','Feu':'Terre','Terre':'Vent','Vent':'Eau'}
CORE_ELEMENTS=set(ELEMENT_BEATS)

def normalize_element(v):
    if v is None: return 'Neutre'
    raw=str(v).strip(); key=raw.lower()
    return ELEMENT_ALIASES.get(key, raw if raw in ELEMENTS else 'Neutre')

def elemental_modifiers(attacker, target, pve=True, player_attacker=True):
    """Return direct combat modifiers for an elemental matchup.
    debuff_delta and crit_delta are percentage-point deltas expressed as fractions.
    PvE simulations here model the player's Invoker attacking the boss.
    """
    a=normalize_element(attacker); t=normalize_element(target)
    out={'attacker':a,'target':t,'relation':'Neutre','damage_mult':1.0,'debuff_delta':0.0,'crit_delta':0.0}
    # Astral Omnissi is always element-neutral. Neutral/unknown or same-element is neutral.
    if 'Astral' in (a,t) or 'Neutre' in (a,t) or a==t: return out
    # Four-element wheel.
    if a in CORE_ELEMENTS and t in CORE_ELEMENTS:
        if ELEMENT_BEATS.get(a)==t:
            out.update(relation='Avantage',damage_mult=1.30,debuff_delta=-0.20)
        elif ELEMENT_BEATS.get(t)==a:
            out.update(relation='Désavantage',damage_mult=0.70,debuff_delta=0.50,crit_delta=-0.50)
        return out
    # Light / Dark attacking the four normal elements.
    if a in ('Lumière','Ténèbres') and t in CORE_ELEMENTS:
        out.update(relation='Bonus Lumière/Ténèbres',damage_mult=1.15,debuff_delta=-0.10)
        return out
    # Four normal elements attacking Light / Dark.
    if a in CORE_ELEMENTS and t in ('Lumière','Ténèbres'):
        out.update(relation='Malus vs Lumière/Ténèbres',damage_mult=0.85,debuff_delta=0.25,crit_delta=-0.25)
        return out
    # Light <-> Dark: player gets full advantage in PvE. In PvP both directions counter.
    if {a,t}=={'Lumière','Ténèbres'}:
        if (not pve) or player_attacker:
            out.update(relation='Avantage',damage_mult=1.30,debuff_delta=-0.20)
        return out
    return out

def hero_row(name): return one('SELECT * FROM heroes WHERE lower(name)=lower(?)',(name,))

def hero_element(name):
    ensure_profile_table()
    store=_load_profile_store(); key=str(name or '').strip().lower()
    for k,v in store.items():
        if str(k).lower()==key and isinstance(v,dict) and v.get('element'):
            return normalize_element(v.get('element'))
    h=hero_row(name) or {}
    return normalize_element(h.get('element'))
def mana_row(name): return one('SELECT * FROM mana_raw WHERE lower("Personnage")=lower(?)',(name,))

def level_key(v):
    s=str(v).strip()
    if s in ('♛','11','Crown','crown'): return 11
    try: return int(float(s.replace(',','.')))
    except: return None

def coeff_row(name, level):
    target=level_key(level) or 7
    rows=q('SELECT * FROM coefficients_raw WHERE lower("Personnage")=lower(?)',(name,))
    if not rows: return None
    exact=[]; numeric=[]
    for r in rows:
        lv=level_key(r.get('Niveau skill'))
        if lv is not None:
            numeric.append((abs(lv-target),r))
            if lv==target: exact.append(r)
    if exact: return exact[0]
    if numeric: return sorted(numeric,key=lambda x:x[0])[0][1]
    return rows[0]

def normalize_levels(levels=None, fallback=7):
    levels=levels or {}
    return {k:(level_key(levels.get(k)) or fallback) for k in ('auto','s1','s2','s3','ult')}

# ---------- Theory model ----------
def hero_theory(name, levels=None, boss_def=1320, atk_pct=1.5, cr_add=.7, cd_add=1.4, combo_add=.25, recovery_add=.2, mana_add=.2):
    lv=normalize_levels(levels); h=hero_row(name); rows={k:coeff_row(name,lv[k]) for k in lv}
    if not h or not all(rows.values()): return None
    atk=num(h.get('atk'))*(1+atk_pct); cr=min(1,num(h.get('crit_rate'))+cr_add); cd=num(h.get('crit_dmg'))+cd_add; crit=1+cr*cd; dm=dmult(boss_def)
    ra,r1,r2,r3,ru=rows['auto'],rows['s1'],rows['s2'],rows['s3'],rows['ult']
    combo_coef=sum(num(ra.get(c)) for c in ['Auto 1','Auto 2','Auto 3','Auto 4','Auto 5'])
    mr=mana_row(name); combo_base=auto_chain_cycle_base(name,mr)
    combo_time=max(.1,combo_base/(1+num(h.get('combo_speed'))+combo_add)); autos=atk*combo_coef*crit/combo_time*dm
    recovery=num(h.get('skill_recovery'))+recovery_add; skill_parts={}
    for key,r,coef_col,cd_col in [('S1',r1,'S1 Coeff total','Cooldown S1'),('S2',r2,'S2 Coeff total','Cooldown S2'),('S3',r3,'S3 Coeff total','Cooldown S3')]:
        coefv=num(r.get(coef_col)); cdv=max(.1,parse_seconds(r.get(cd_col),999)/(1+recovery)); skill_parts[key]=atk*crit*coefv/cdv*dm
    skills=sum(skill_parts.values()); ult_coef=num(ru.get('Ult Coeff total')); ult_cd=max(.1,parse_seconds(ru.get('Cooldown Ult'),15)/(1+recovery)); ult=0
    if mr and ult_coef>0:
        combo_mana=num(mr.get('Combo Ult total')); m1=num(mr.get('S1 Ult')); m2=num(mr.get('S2 Ult')); m3=num(mr.get('S3 Ult')); cost=max(1,num(mr.get('Coût Ult connu'),999999)-25)
        cd1=max(.1,parse_seconds(r1.get('Cooldown S1'),999)/(1+recovery)); cd2=max(.1,parse_seconds(r2.get('Cooldown S2'),999)/(1+recovery)); cd3=max(.1,parse_seconds(r3.get('Cooldown S3'),999)/(1+recovery))
        mana_rate=(combo_mana/combo_time+m1/cd1+m2/cd2+m3/cd3)*(1+num(h.get('mana_gen'))+mana_add); interval=max(ult_cd,cost/max(.0001,mana_rate)); ult=atk*crit*ult_coef/interval*dm
    return {'Autos':autos,'S1':skill_parts['S1'],'S2':skill_parts['S2'],'S3':skill_parts['S3'],'Skills':skills,'Ultimate':ult,'Total':autos+skills+ult,'levels':lv}

# ---------- Combat simulation ----------
DEBUFF_NAMES={'DEF Down','RES Down','Weakness','Shock','ATK Down','Move SPD Down','Skill Recovery Down','Cooldown Increase','ACC Down','Crit Rate Down','Crit DMG Down','Combo SPD Down','Skill SPD Down'}
# Tous les boss du jeu sont immunisés aux contrôles de foule.
# Ces effets peuvent exister dans les fiches héros mais ne doivent jamais être
# appliqués au boss ni contribuer au DPS/support score dans les simulations boss.
BOSS_CC_IMMUNE_EFFECTS={
    'Blind','Chain','Disable','Freeze','Hex','Jinx','Knockback','Launch',
    'Mindworm','Pull','Push','Shock','Stun','Suppression','Taunt'
}
BUFF_NAMES={'ATK Up','Crit Rate Up','Crit DMG Up','Combo SPD Up','Skill SPD Up','DEF Up','RES Up','Skill Recovery Up','Mana Generation Up'}

EFFECT_ALIASES={
    'Cooldown Reduction':'Cooldown reduction',
    'Cooldown increase':'Cooldown Increase',
    'Heal reduction':'Heal Reduction',
    'Weaken':'Weakness',
}
PERCENT_EFFECTS=DEBUFF_NAMES|BUFF_NAMES|{
    'Burn','Bleed','Damage Bonus','Conditional Damage Up','Damage Bonus per Debuff',
    'Damage bonus per debuff','Damage per debuff','Damage Bonus per Buff','Damage Bonus per 10% Lost HP',
    'DEF Ignore per target buff','Ultimate Mana Gain %','Buff Steal / Ultimate Mana Gain %'
}
FLAT_EFFECTS={
    'Cooldown reduction','Cooldown Increase','Buff Duration Extension','Debuff Duration Extension',
    'Bleed Duration Extension','Buff Duration Reduction','Buff Duration Shortening',
    'Debuff Duration Reduction','Debuff Duration Shortening','Stolen Buff Duration Extension',
    'Knockback','Launch','Gain Titan Mana','Titan Mana Gain','Titan Mana Loss',
    'Gain Ultimate Mana','Ultimate Mana Gain','Ultimate Mana Gain (crit)','Ultimate Mana Gain (non-crit)',
    'Ultimate Mana Gain / hit','Ultimate Mana Loss','Self Active Skill Cooldown Reduction',
    'Ally Active Skill Cooldown Reduction','Active Skill Cooldown Reduction',
    'Active Skill 2 Cooldown Reduction','Active Skill 3 Cooldown Reduction'
}

def canonical_effect(effect):
    e=str(effect or '').strip()
    return EFFECT_ALIASES.get(e,e)

def pct_value(effect, v):
    effect=canonical_effect(effect)
    # Some composite effects store values such as "20 / 40"; they are deliberately
    # left at 0 here and handled only by hero-specific logic rather than guessed.
    try:
        if isinstance(v,str) and ('/' in v or '+' in v): return 0.0
    except Exception: pass
    x=num(v,0)
    if effect in FLAT_EFFECTS: return x
    if effect in PERCENT_EFFECTS or effect.endswith(' Up') or effect.endswith(' Down') or 'Damage Bonus' in effect:
        return x/100.0
    return x

def action_effects(r,prefix):
    out=[]
    for i in (1,2):
        raw=r.get(f'{prefix} Effet {i}')
        if not raw:
            continue
        e=canonical_effect(raw)
        raw_value=r.get(f'{prefix} Valeur {i}')
        duration=num(r.get(f'{prefix} Durée {i}'),0)
        condition=r.get(f'{prefix} Condition {i}') or ''

        # Certaines données officielles regroupent deux buffs dans une même cellule
        # (ex. Furnos S2: "Crit Rate Up / Crit DMG Up" = "30 / 50").
        # Le moteur doit les traiter comme deux familles de buffs indépendantes.
        if e=='Crit Rate Up / Crit DMG Up':
            parts=[x.strip() for x in str(raw_value or '').split('/')]
            if len(parts)>=2:
                out.append({'name':'Crit Rate Up','value':num(parts[0],0)/100.0,'raw_value':parts[0],'duration':duration,'condition':condition})
                out.append({'name':'Crit DMG Up','value':num(parts[1],0)/100.0,'raw_value':parts[1],'duration':duration,'condition':condition})
                continue
        out.append({'name':e,'value':pct_value(e,raw_value),'raw_value':raw_value,'duration':duration,'condition':condition})
    return out

def deterministic_roll(seed):
    b=hashlib.sha256(seed.encode('utf-8')).digest()[:8]
    return int.from_bytes(b,'big')/2**64

def initial_resist_chance(acc,res):
    """Signed Initial Resist Chance (IRC), before Phase-2 modifiers.

    Official table:
      - direct 1:1 between -50 and +50;
      - outside that range, logarithmic diminishing returns;
      - 50 => 50%, 100 => 89.6%, 120 => 100%, 150 => 112.7%, 500 => 181.5%.
    IRC deliberately remains signed/unclamped until the end of Phase 2.
    """
    diff=float(res)-float(acc)
    if -50.0 <= diff <= 50.0:
        return diff/100.0
    sign=1.0 if diff>0 else -1.0
    ad=abs(diff)
    # Exact logarithmic curve anchored to the official 50=>50% and 120=>100% milestones.
    slope=50.0/(math.log(120.0)-math.log(50.0))
    pct=50.0+slope*(math.log(ad)-math.log(50.0))
    return sign*(pct/100.0)

def effect_pass_chance(acc,res):
    # Land chance is the inverse of Final Resist Chance when no phase-2
    # modifiers are present. PRE >= RES therefore guarantees the debuff.
    resist=max(0.0,min(1.0,initial_resist_chance(acc,res)))
    return 1.0-resist

def final_debuff_pass_chance(acc,res,resist_modifiers=0.0):
    """Invokers 2-phase Resistance Check.

    Phase 1: compute signed Initial Resist Chance (IRC) from RES-ACC.
    Phase 2: add/subtract Resist Chance Modifiers directly to IRC.
    Only after every modifier is applied do we normalize Final Resist Chance
    to [0, 100%]. Land Chance is exactly 1 - Final Resist Chance.

    resist_modifiers is expressed from the RESIST-CHANCE point of view:
      + values increase Resist Chance (ACC Down, RES Up, target element advantage)
      - values decrease Resist Chance (ACC Up, RES Down, target element disadvantage)
    """
    irc=initial_resist_chance(acc,res)
    frc=max(0.0,min(1.0,irc+num(resist_modifiers)))
    return 1.0-frc

def resistance_check_breakdown(acc,res,resist_modifiers=0.0):
    irc=initial_resist_chance(acc,res)
    raw_frc=irc+num(resist_modifiers)
    frc=max(0.0,min(1.0,raw_frc))
    return {
        'acc':float(acc),'res':float(res),'res_minus_acc':float(res)-float(acc),
        'irc':irc,'resist_modifiers':num(resist_modifiers),
        'frc_before_clamp':raw_frc,'frc':frc,'land_chance':1.0-frc
    }


TEAM_BUFF_NAMES={'ATK Up','Crit Rate Up','Crit DMG Up','Combo SPD Up','Skill SPD Up','Skill Recovery Up','Mana Generation Up','ACC Up','RES Up','DEF Up','Move SPD Up'}
TEAM_TARGET_DEBUFF_NAMES=set(DEBUFF_NAMES)|{'Weakness','Shock'}

# Certaines fiches officielles décrivent le type d'effet sans encoder explicitement
# la cible dans les colonnes Effet/Condition. Ces buffs doivent rester personnels
# et ne jamais être projetés sur le carry dans le moteur Best Support.
SELF_ONLY_SUPPORT_EFFECTS={
    ('volkam','Ultimate','Crit Rate Up'),
    ('volkam','Ultimate','Crit DMG Up'),
}

# Héros qui n'apportent aucun buff/debuff utile aux alliés dans le contexte
# "Meilleur support". Leurs effets utiles sont personnels.
NON_SUPPORT_HEROES={'klissa'}

def team_buff_targets_allies(effect, source=None, action=None):
    cond=str(effect.get('condition') or '').lower()
    # Les buffs explicitement Self ne sont pas propagés à l'équipe.
    if 'self' in cond: return False
    src=str(source or '').strip().lower()
    eff=effect.get('name')
    # Klissa: son ATK Up est personnel, quel que soit le skill qui le déclenche.
    if src=='klissa' and eff=='ATK Up': return False
    key=(src, str(action or '').strip(), eff)
    if key in SELF_ONLY_SUPPORT_EFFECTS: return False
    return eff in TEAM_BUFF_NAMES and num(effect.get('duration'),0)>0

def support_buff_schedule(name, duration=120, adds_mode='none', boss_element='Neutre', support_mode='real', stats_override=None, levels_override=None):
    """Timeline V1 d'un support: vraie rotation/cooldowns/mana selon sa fiche,
    et extraction des buffs qui peuvent toucher les alliés. Les dégâts du support
    ne sont pas ajoutés au DPS du carry."""
    if not name or name=='Aucun': return {'name':'Aucun','events':[],'actions':0,'stats':{},'levels':{}}
    if str(name).strip().lower() in NON_SUPPORT_HEROES:
        return {'name':name,'events':[],'actions':0,'stats':{},'levels':{},'excluded_from_support':True}
    h=hero_row(name); pr=profile_for(name); lv=profile_levels(pr); st=profile_stats(name,pr); mr=mana_row(name)
    sm=str(support_mode or 'real').lower()
    if levels_override is not None: lv=dict(levels_override)
    if stats_override is not None: st=dict(stats_override)

    # Ma box = vraie fiche importée.
    # Stats de base = stats natives du héros + skills niveau 1.
    # Max support = stats natives + skills max + PRE 1000 et 30% sur les
    # quatre stats de rythme utiles au soutien.
    if stats_override is None and levels_override is None and sm in ('base','base_stats','native'):
        lv={k:1 for k in ('auto','s1','s2','s3','ult')}
        st={
            'atk':num(h.get('atk')),
            'crit_rate':num(h.get('crit_rate')),
            'crit_dmg':num(h.get('crit_dmg')),
            'accuracy':num(h.get('accuracy')),
            'resistance':num(h.get('resistance')),
            'combo_speed':num(h.get('combo_speed')),
            'skill_speed':num(h.get('skill_speed')),
            'skill_recovery':num(h.get('skill_recovery')),
            'mana_gen':num(h.get('mana_gen')),
        }
    elif stats_override is None and levels_override is None and sm in ('best','max','normalized'):
        lv={k:11 for k in ('auto','s1','s2','s3','ult')}
        st={
            'atk':num(h.get('atk')),
            'crit_rate':num(h.get('crit_rate')),
            'crit_dmg':num(h.get('crit_dmg')),
            'accuracy':1000.0,
            'resistance':num(h.get('resistance')),
            'combo_speed':0.30,
            'skill_speed':0.30,
            'skill_recovery':0.30,
            'mana_gen':0.30,
        }
    rows={k:coeff_row(name,lv[k]) for k in lv}
    if not h or not all(rows.values()): return {'name':name,'events':[],'actions':0,'stats':st,'levels':lv}
    combo_base=auto_chain_cycle_base(name,mr)
    combo_mult=max(.05,1+num(st.get('combo_speed'))); skill_mult=max(.05,1+num(st.get('skill_speed'))); rec_mult=max(.05,1+num(st.get('skill_recovery')))
    elem=elemental_modifiers(hero_element(name),boss_element,pve=True,player_attacker=True)
    mana_mult=max(0,1+num(st.get('mana_gen'))); crit=max(0,min(1,num(st.get('crit_rate'))+elem['crit_delta'])); ult_cost=max(1,num((mr or {}).get('Coût Ult connu'),1100))
    ready={'s1':0.0,'s2':0.0,'s3':0.0,'ult':0.0}; mana=0.0; auto_idx=1; t=0.0; seq=0; occ={}; events=[]
    while t<duration and seq<3000:
        seq+=1
        if t>=ready['ult'] and mana>=ult_cost and (num(rows['ult'].get('Ult Coeff total'))>0 or action_effects(rows['ult'],'Ult')):
            key='ult'; action='Ultimate'; r=rows['ult']; pref='Ult'; hits=max(1,int(num(r.get('Ult Hits'),1))); cast=max(.05,num(h.get('cast_ult'),1)/skill_mult); cd=parse_seconds(r.get('Cooldown Ult'),15)/rec_mult; mg=0
        elif t>=ready['s1'] and (num(rows['s1'].get('S1 Coeff total'))>0 or action_effects(rows['s1'],'S1')):
            key='s1'; action='Skill 1'; r=rows['s1']; pref='S1'; hits=max(1,int(num(r.get('S1 Hits'),1))); cast=max(.05,num(h.get('cast_s1'),1)/skill_mult); cd=parse_seconds(r.get('Cooldown S1'),999)/rec_mult; mg=num((mr or {}).get('S1 Ult'))
        elif t>=ready['s2'] and (num(rows['s2'].get('S2 Coeff total'))>0 or action_effects(rows['s2'],'S2')):
            key='s2'; action='Skill 2'; r=rows['s2']; pref='S2'; hits=max(1,int(num(r.get('S2 Hits'),1))); cast=max(.05,num(h.get('cast_s2'),1)/skill_mult); cd=parse_seconds(r.get('Cooldown S2'),999)/rec_mult; mg=num((mr or {}).get('S2 Ult'))
        elif t>=ready['s3'] and (num(rows['s3'].get('S3 Coeff total'))>0 or action_effects(rows['s3'],'S3')):
            key='s3'; action='Skill 3'; r=rows['s3']; pref='S3'; hits=max(1,int(num(r.get('S3 Hits'),1))); cast=max(.05,num(h.get('cast_s3'),1)/skill_mult); cd=parse_seconds(r.get('Cooldown S3'),999)/rec_mult; mg=num((mr or {}).get('S3 Ult'))
        else:
            key='auto'; action=f'Auto {auto_idx}'; r=rows['auto']; pref='Auto 5' if auto_idx==5 else None; hits=1; cast=auto_cast_time(name,auto_idx,combo_mult,mr); cd=0; mg=num((mr or {}).get('Auto Ult moyen / attaque (5)'),num((mr or {}).get('Combo Ult total'))/5 if mr else 0)
        start=t; occ[action]=occ.get(action,0)+1
        crits=sum(1 for hi in range(hits) if deterministic_roll(f'support|{name}|{action}|{occ[action]}|{hi}')<crit)
        if pref:
            for e in action_effects(r,pref):
                is_team_buff=team_buff_targets_allies(e,name,action)
                is_target_debuff=(e.get('name') in TEAM_TARGET_DEBUFF_NAMES or ' Down' in str(e.get('name') or '')) and num(e.get('duration'),0)>0
                if not (is_team_buff or is_target_debuff): continue
                # Tous les boss sont immunisés aux contrôles de foule : on
                # n'émet pas ces événements dans la timeline des supports.
                if is_target_debuff and e.get('name') in BOSS_CC_IMMUNE_EFFECTS:
                    continue
                c=(e.get('condition') or '').lower()
                # Correctif de donnée connu: Nirvelle S3 ATK Up n'est accordé que si le coup tue une cible.
                if name.lower()=='nirvelle' and action=='Skill 3' and e['name']=='ATK Up': c='on kill'
                if ('critical hit' in c or ('crit' in c and 'non-critical' not in c)) and crits<=0: continue
                if 'non-critical' in c and crits>0: continue
                if 'kill' in c:
                    rates={'none':0.0,'rare':0.15,'frequent':0.50}
                    rate=rates.get(str(adds_mode).lower(),0.0)
                    if deterministic_roll(f'kill|{name}|{action}|{occ[action]}')>=rate: continue
                events.append({'source':name,'effect':e['name'],'value':e['value'],'start':start,'end':min(duration,start+e['duration']),'action':action,'condition':('On kill' if 'kill' in c else (e.get('condition') or 'Toujours')),'kind':('buff' if is_team_buff else 'debuff_attempt'),'accuracy':num(st.get('accuracy')),'attacker_element':hero_element(name),'element_debuff_delta':elem['debuff_delta']})
        if key=='ult': mana=max(0,mana-ult_cost); ready['ult']=start+cd; auto_idx=1
        elif key in ('s1','s2','s3'): ready[key]=start+cd; mana+=mg*mana_mult; auto_idx=1
        else: mana+=mg*mana_mult; auto_idx=1 if auto_idx==5 else auto_idx+1
        mana=min(ult_cost,mana); t+=cast
    return {'name':name,'events':events,'actions':seq,'stats':st,'levels':lv,'element':hero_element(name),'element_matchup':elem}

def support_buff_schedule_preset(name,duration=120,adds_mode='none',boss_element='Neutre',preset='box'):
    key=str(preset or 'box').strip().lower()
    if key=='box':
        return support_buff_schedule(name,duration,adds_mode,boss_element,'real')
    _,st,lv,_,_=combat_preset_for(name,key)
    return support_buff_schedule(name,duration,adds_mode,boss_element,'real',stats_override=st,levels_override=lv)

def prepare_team_buffs(supports,duration,adds_mode='none',boss_res=0,boss_element='Neutre',support_mode='real'):
    raw=[]; support_info=[]
    for n in supports or []:
        if not n or n=='Aucun': continue
        z=support_buff_schedule(n,duration,adds_mode,boss_element,support_mode); raw.extend(z['events']); support_info.append({'name':n,'actions':z['actions'],'buff_casts':sum(1 for e in z['events'] if e.get('kind')=='buff'),'debuff_attempts':sum(1 for e in z['events'] if e.get('kind')=='debuff_attempt'),'stats':z.get('stats',{}),'levels':z.get('levels',{}),'element':z.get('element','Neutre'),'element_matchup':z.get('element_matchup',{})})
    # Résout les débuffs des supports contre la RES du boss. Un RES Down déjà posé
    # augmente la réussite des tentatives suivantes, comme pour le carry.
    resolved=[]
    for e in sorted(raw,key=lambda x:(x['start'],x['source'],x['effect'])):
        x=dict(e)
        if x.get('kind')=='debuff_attempt':
            active_res_down=max([r['value'] for r in resolved if r.get('kind')=='debuff' and r.get('effect')=='RES Down' and r['start']<=x['start']<r['end']] or [0.0])
            resist_mod=num(x.get('element_debuff_delta'))-active_res_down
            chance=final_debuff_pass_chance(num(x.get('accuracy')),boss_res,resist_mod)
            x['pass_chance']=chance
            roll=deterministic_roll(f"supportdebuff|{x['source']}|{x['action']}|{x['effect']}|{x['start']:.6f}")
            x['success']=roll<chance
            if not x['success']:
                continue
            x['kind']='debuff'
        resolved.append(x)
    # Même source + même famille: la nouvelle application remplace l'ancienne.
    grouped={}
    for e in sorted(resolved,key=lambda x:(x['effect'],x['source'],x['start'])):
        k=(e['effect'],e['source']); a=grouped.setdefault(k,[])
        if a and a[-1]['end']>e['start']: a[-1]['end']=e['start']
        a.append(dict(e))
    events=[e for arr in grouped.values() for e in arr if e['end']>e['start']]
    events.sort(key=lambda x:(x['start'],x['source'],x['effect']))
    # expose les succès de débuff par support
    for si in support_info:
        si['debuff_successes']=sum(1 for e in events if e.get('kind')=='debuff' and e.get('source')==si['name'])
    return events,support_info

def summarize_team_buffs(events,duration):
    out=[]
    for eff in sorted(set(e['effect'] for e in events)):
        ee=[e for e in events if e['effect']==eff]
        bounds=sorted(set([0.0,duration]+[x for e in ee for x in (e['start'],e['end'])]))
        uptime=0.0; weighted=0.0; sources=set()
        for a,b in zip(bounds,bounds[1:]):
            if b<=a: continue
            mid=(a+b)/2; active=[e for e in ee if e['start']<=mid<e['end']]
            if active:
                # Même famille = un seul buff: le plus fort est actif. En cas d'égalité,
                # l'application la plus ancienne garde la priorité.
                win=sorted(active,key=lambda e:(-e['value'],e['start']))[0]
                uptime+=b-a; weighted+=win['value']*(b-a); sources.add(win['source'])
        out.append({'effect':eff,'sources':', '.join(sorted(sources)),'applications':len(ee),'uptime_s':round(uptime,2),'uptime':uptime/duration if duration else 0,'avg_active_value':weighted/uptime if uptime else 0,'max_value':max((e['value'] for e in ee),default=0)})
    return out

def simulate_combat(name, levels=None, duration=120, boss_def=1320, boss_res=0, boss_hp=0, boss_atk=0, boss_element='Neutre', atk_pct=1.5, cr_add=.7, cd_add=1.4, combo_add=.25, skill_speed_add=.2, recovery_add=.2, mana_add=.2, acc_add=340, accuracy_final=None, resistance_final=None, comparison_mode=False, disabled_effects=None, analyze_effect_gains=False, team_supports=None, disabled_team_buffs=None, adds_mode='none', prepared_team=None):
    disabled_effects=set(disabled_effects or [])
    lv=normalize_levels(levels); h=hero_row(name); mr=mana_row(name); rows={k:coeff_row(name,lv[k]) for k in lv}
    if not h or not all(rows.values()): return None
    hero_elem=hero_element(name); elem_mod=elemental_modifiers(hero_elem,boss_element,pve=True,player_attacker=True)
    atk_base=num(h.get('atk'))*(1+atk_pct); cr_base=min(1,num(h.get('crit_rate'))+cr_add); cdmg_base=num(h.get('crit_dmg'))+cd_add
    combo_base=auto_chain_cycle_base(name,mr)
    base_mana_gen=1+num(h.get('mana_gen'))+mana_add; acc=num(accuracy_final) if accuracy_final is not None else num(h.get('accuracy'))+acc_add
    mana=0.0; ult_cost=max(1,num((mr or {}).get('Coût Ult connu'),1100)); t=0.0; auto_idx=1; rowno=0; total=0.0; action_occurrences={}
    ready={'s1':0.0,'s2':0.0,'s3':0.0,'ult':0.0}; active={}; intervals={}; stats={}; log=[]; damage_by={'Auto':0,'Skill 1':0,'Skill 2':0,'Skill 3':0,'Ultimate':0,'DoT':0}; burns=[]; self_burn_until=0.0
    if prepared_team is None:
        team_events,support_info=prepare_team_buffs(team_supports or [],duration,adds_mode,boss_res,boss_element)
    else:
        # Classement optimisé : la timeline des supports fixes est identique pour
        # tous les héros évalués. Elle est préparée une seule fois par requête /api/rank.
        team_events=prepared_team.get('events',[])
        support_info=prepared_team.get('support_info',[])
    disabled_team_buffs=set(disabled_team_buffs or []); team_boundaries=sorted(set(x for e in team_events for x in (e['start'],e['end']))); team_boundary_idx=0

    def active_value(effect, now):
        a=active.get(effect)
        return a['value'] if a and a['expiry']>now else 0.0
    def team_buff_value(effect,now):
        if effect in disabled_team_buffs: return 0.0
        vals=[e for e in team_events if e.get('kind','buff')=='buff' and e['effect']==effect and e['start']<=now<e['end']]
        if not vals:return 0.0
        return sorted(vals,key=lambda e:(-e['value'],e['start']))[0]['value']
    def team_debuff_value(effect,now):
        vals=[e for e in team_events if e.get('kind')=='debuff' and e['effect']==effect and e['start']<=now<e['end']]
        if not vals:return 0.0
        return max(e['value'] for e in vals)
    def effective_buff_value(effect,now):
        # Les buffs de même famille ne se cumulent pas: le plus fort est actif.
        return max(active_value(effect,now),team_buff_value(effect,now))
    def effective_debuff_value(effect,now):
        # Carry + supports: le débuff le plus fort de la famille est retenu.
        return max(active_value(effect,now),team_debuff_value(effect,now))
    def target_debuff_count(now):
        own={k for k,a in active.items() if a.get('expiry',0)>now and (k in DEBUFF_NAMES or k in ('Burn','Bleed','Weakness') or 'Down' in k)}
        team={e['effect'] for e in team_events if e.get('kind')=='debuff' and e['start']<=now<e['end']}
        return len(own|team)
    def self_buff_count(now):
        return len({k for k,a in active.items() if a.get('expiry',0)>now and (k in BUFF_NAMES or k.endswith(' Up'))} | {e['effect'] for e in team_events if e.get('kind','buff')=='buff' and e['effect'] not in disabled_team_buffs and e['start']<=now<e['end']})
    def mana_gen_factor(now):
        return max(0.0,base_mana_gen+effective_buff_value('Mana Generation Up',now))
    def debuff_pass_chance(now):
        # Phase 2 operates on Resist Chance, not on the ACC/RES stats themselves.
        # ACC Up and RES Down subtract percentage points from Resist Chance.
        # Elemental matchup is also a Resist Chance modifier from the target's perspective.
        resist_mod=elem_mod['debuff_delta']-effective_buff_value('ACC Up',now)-effective_debuff_value('RES Down',now)
        return final_debuff_pass_chance(acc,boss_res,resist_mod)
    def register_interval(effect,start,end): intervals.setdefault(effect,[]).append((max(0,start),min(duration,end)))
    def brandis_burn_cap_mult(action, level):
        """Official Brandis Burn target damage caps, expressed as xATK per tick.

        Brand Heresy (S1) burns Brandis himself, so it never contributes target
        DoT here. Fiery Prayer (S2), Litany of Flames (S3), and Conflagration
        (Ultimate) use the published per-level target Burn caps:
        200/200/250/250/300/300/350/350/400/400/500 % ATK.
        """
        L=max(1,min(11,int(level if isinstance(level,(int,float)) else (11 if str(level)=='♛' else 1))))
        target_caps=[2.0,2.0,2.5,2.5,3.0,3.0,3.5,3.5,4.0,4.0,5.0]
        if action in ('Skill 2','Skill 3','Ultimate'):
            return target_caps[L-1]
        # Defensive fallback for any legacy/imported target Burn row.
        return target_caps[L-1]
    def process_dot_ticks(until):
        nonlocal total
        if not burns or until<=0: return
        for b in burns:
            while b['next_tick']<=until+1e-12 and b['next_tick']<=b['end']+1e-12 and b['next_tick']<=duration+1e-12:
                tick=min((boss_hp*b['pct']) if boss_hp>0 else 0.0, b['atk_cap']) if boss_hp>0 else b['atk_cap']
                if tick>0:
                    total+=tick; damage_by['DoT']=damage_by.get('DoT',0)+tick
                    b['damage']+=tick; b['ticks']+=1
                b['next_tick']+=b['interval']
    base_recovery_mult=1+num(h.get('skill_recovery'))+recovery_add
    def adjust_ready_for_recovery(now, old_bonus, new_bonus):
        old_mult=max(.05,base_recovery_mult+old_bonus); new_mult=max(.05,base_recovery_mult+new_bonus)
        if abs(old_mult-new_mult)<1e-12:return
        for kk in ('s1','s2','s3','ult'):
            if ready[kk]>now:
                remaining_base=(ready[kk]-now)*old_mult
                ready[kk]=now+remaining_base/new_mult
    def expire_dynamic_buffs(now):
        a=active.get('Skill Recovery Up')
        if a and a['expiry']<=now:
            expiry=a['expiry']; old=effective_buff_value('Skill Recovery Up',expiry-1e-9)
            active.pop('Skill Recovery Up',None)
            new=effective_buff_value('Skill Recovery Up',expiry+1e-9)
            adjust_ready_for_recovery(expiry,old,new)
    def apply_effect(e, now, action, seq, crits=0, hits=1, pass_chance_snapshot=None):
        nonlocal ready, mana, self_burn_until
        nm=e['name'];
        if nm in disabled_effects: return False
        st=stats.setdefault(nm,{'effect':nm,'attempts':0,'triggered':0,'acc_tests':0,'chance_sum':0.0,'successes':0,'applications':0,'value':e['value'],'duration':e['duration'],'actions':set(),'condition':e['condition']})
        st['attempts']+=1; st['actions'].add(action); st['value']=e['value']; st['duration']=e['duration']
        cond=(e.get('condition') or '').lower()
        # Brandis: distinguish the Burn carried by Brandis from Burns placed on the target.
        # S2 has two alternative Burn rows depending on whether Brandis is currently Burning.
        if name=='Brandis' and nm=='Burn':
            has_self_burn=self_burn_until>now
            if 'no burn on brandis' in cond and has_self_burn: return False
            if 'if brandis has burn' in cond and not has_self_burn: return False
        # Cezal special handling: Skill 3 CDR always happens once, then repeats once on crit.
        # Auto 5 CDR always targets Skill 3. These mechanics must not be reduced to the
        # generic "crit condition" / random-target handler below.
        cezal_s3_cdr = (name=='Cezal' and action=='Skill 3' and nm=='Cooldown reduction')
        cezal_a5_cdr = (name=='Cezal' and action=='Auto 5' and nm=='Cooldown reduction')
        devi_a5_cdr = (name=='Devi' and action=='Auto 5' and nm=='Cooldown reduction')
        devi_ult_self_cdr = (name=='Devi' and action=='Ultimate' and nm=='Self Active Skill Cooldown Reduction')
        devi_s2_mana = (name=='Devi' and action=='Skill 2' and nm=='Ultimate Mana Gain / hit')
        if devi_a5_cdr:
            condition_ok = (crits==0) if 'non-critical' in cond else (crits>0)
        elif devi_ult_self_cdr:
            condition_ok = crits>0
        elif devi_s2_mana:
            condition_ok = True
        else:
            condition_ok = True if (cezal_s3_cdr or cezal_a5_cdr) else ((crits>0) if ('critical hit' in cond or ('crit' in cond and 'non-critical' not in cond)) else True)
        if not condition_ok: return False
        # Explicit proc chances (e.g. Brandis Auto 5: 20% chance) are rolled independently.
        mproc=re.search(r'([0-9]+(?:\.[0-9]+)?)%\s*chance',cond)
        if mproc:
            proc=float(mproc.group(1))/100.0
            if deterministic_roll(f'{name}|proc|{seq}|{action}|{nm}')>=proc: return False
        st['triggered']+=1
        # Les simulations de combat ici ciblent un boss : tous les effets de
        # contrôle de foule sont immunisés globalement et ne doivent ni passer
        # le test PRE/RES, ni créer d'uptime, ni augmenter les dégâts.
        if nm in BOSS_CC_IMMUNE_EFFECTS:
            st['condition']=(e.get('condition') or nm)+' → Boss immunisé au contrôle de foule'
            return False
        # Brandis target Burns explicitly require Accuracy. His self-Burn does not
        # test the boss's RES.
        brandis_target_burn=(name=='Brandis' and nm=='Burn' and 'self' not in cond)
        needs_acc=(nm in DEBUFF_NAMES or 'Down' in nm or nm in ('Weakness','Cooldown Increase') or 'accuracy required' in cond or brandis_target_burn)
        chance=(pass_chance_snapshot if pass_chance_snapshot is not None else debuff_pass_chance(now)) if needs_acc else 1.0
        if needs_acc:
            st['acc_tests']+=1
            st['chance_sum']=st.get('chance_sum',0.0)+chance
        passed=deterministic_roll(f'{name}|{seq}|{action}|{nm}')<chance
        if not passed: return False
        st['successes']+=1
        if name=='Brandis' and nm=='Burn':
            # S1 burns Brandis himself; this is a state/condition, not boss damage.
            if 'self' in cond:
                self_burn_until=max(self_burn_until, now+e['duration'])
                st['applications']+=1
                st['condition']=(e.get('condition') or 'Self Burn')+' → Brandis'
                register_interval('Self Burn',now,self_burn_until)
                return True
            # Target Burn: stackable DoT. Tick rate scales with Skill Speed.
            level_key={'Auto 5':'auto','Skill 1':'s1','Skill 2':'s2','Skill 3':'s3','Ultimate':'ult'}.get(action,'auto')
            level=lv.get(level_key,1)
            cap_mult=brandis_burn_cap_mult(action,level)
            atk_now,_,_,_,skillsp_now,_,_,_=current_multipliers(now)
            interval=2.0/max(.05,skillsp_now)
            # Brandis: only the Ultimate repeats 3 times while Brandis is Burning.
            # S2 does NOT repeat; it switches to its stronger/longer Burn variant,
            # which is already handled by the conditional Burn rows above.
            reps=3 if (action=='Ultimate' and self_burn_until>now) else 1
            for ri in range(reps):
                burns.append({'start':now,'end':min(duration,now+e['duration']),'pct':max(0,e['value']),'atk_cap':max(0,atk_now*cap_mult),'interval':interval,'next_tick':now+interval,'damage':0.0,'ticks':0,'source':action})
                st['applications']+=1
            active['Burn']={'value':e['value'],'expiry':max(active.get('Burn',{}).get('expiry',0),now+e['duration'])}
            register_interval('Burn',now,now+e['duration'])
            st['condition']=(e.get('condition') or 'Burn')+(f' → {reps} stack(s), tick {interval:.2f}s' if reps>1 else f' → tick {interval:.2f}s')
            return True
        if name=='Kisanka' and action=='Skill 2' and nm in ('Gain Ultimate Mana','Ultimate Mana Gain','Ultimate Mana Gain (crit)','Ultimate Mana Gain (non-crit)','Ultimate Mana Gain / hit'):
            # Kisanka S2: every hit grants mana; critical hits grant the larger amount.
            # Values by skill level from the public skill data. This is additional to
            # the normal mana generated by the skill's launch duration.
            kisanka_s2_mana={1:(25,50),2:(25,58),3:(25,58),4:(28,58),5:(28,64),6:(28,64),7:(32,64),8:(32,72),9:(36,72),10:(40,72),11:(40,80)}
            skl=max(1,min(11,int(lv.get('s2',1) or 1)))
            noncrit_gain,crit_gain=kisanka_s2_mana[skl]
            noncrits=max(0,hits-crits)
            gained=(noncrits*noncrit_gain + crits*crit_gain)*mana_gen_factor(now)
            mana=min(ult_cost,mana+gained)
            st['applications']+=hits
            st['condition']=f'Each hit → +{noncrit_gain} mana; crit → +{crit_gain} mana ({noncrits} normal, {crits} crit)'
        elif devi_s2_mana:
            gained=e['value']*hits*mana_gen_factor(now)
            mana=min(ult_cost,mana+gained)
            st['applications']+=hits
            st['condition']=f'Each hit → +{e["value"]:g} mana × {hits}'
        elif devi_ult_self_cdr:
            candidates=['s1','s2','s3']
            occ=action_occurrences.get(action,1)
            targets=[]
            for ci in range(crits):
                idx=int(deterministic_roll(f'{name}|selfcdr|{action}|{occ}|{ci+1}')*len(candidates)) % len(candidates)
                target=candidates[idx]
                ready[target]=max(now,ready[target]-e['value'])
                targets.append(target.upper())
                st['applications']+=1
            st['condition']=f'Each critical hit → random Active Skill' + ((' → '+', '.join(targets)) if targets else '')
        elif nm in ('Gain Ultimate Mana','Ultimate Mana Gain','Ultimate Mana Gain (crit)','Ultimate Mana Gain (non-crit)','Ultimate Mana Gain / hit','Ultimate Mana Gain %'):
            # Generic Ultimate-mana effects. Conditions tied to kill/ally state are not
            # invented; when they cannot be established in a solo boss simulation they
            # remain visible in Analyse effets but do not grant mana.
            cond_l=cond.lower()
            if 'kill' in cond_l or 'ally' in cond_l:
                return False
            mult=1
            if 'per debuff' in cond_l:
                mult=max(0,target_debuff_count(now))
            elif 'each hit' in cond_l or '/ hit' in nm.lower():
                mult=hits
            if nm=='Ultimate Mana Gain (crit)': mult=crits
            elif nm=='Ultimate Mana Gain (non-crit)': mult=max(0,hits-crits)
            amount=e['value']
            if nm=='Ultimate Mana Gain %': amount=ult_cost*e['value']
            gained=max(0,amount*mult*mana_gen_factor(now))
            mana=min(ult_cost,mana+gained)
            st['applications']+=max(1,mult) if gained>0 else 0
            st['condition']=(e['condition'] or 'Ultimate mana')+f' → +{gained:.1f} mana'
        elif nm in ('Active Skill 2 Cooldown Reduction','Active Skill 3 Cooldown Reduction'):
            target='s2' if '2' in nm else 's3'
            ready[target]=max(now,ready[target]-e['value'])
            st['applications']+=1
            st['condition']=(e['condition'] or nm)+f' → {target.upper()}'
        elif nm in ('Active Skill Cooldown Reduction','Self Active Skill Cooldown Reduction'):
            candidates=['s1','s2','s3']
            occ=action_occurrences.get(action,1)
            idx=int(deterministic_roll(f'{name}|genericcdr|{action}|{occ}|{seq}')*len(candidates)) % len(candidates)
            target=candidates[idx]
            ready[target]=max(now,ready[target]-e['value'])
            st['applications']+=1
            st['condition']=(e['condition'] or nm)+f' → {target.upper()}'
        elif nm.lower() in ('cooldown reduction','cooldown reduction ') or nm=='Cooldown reduction':
            if devi_a5_cdr:
                target='s2'
                ready[target]=max(now,ready[target]-e['value'])
                st['applications']+=1
                st['condition']=f'{e["condition"]} → S2'
            elif cezal_a5_cdr:
                target='s3'
                ready[target]=max(now,ready[target]-e['value'])
                st['applications']+=1
                st['condition']=f'Active Skill 3 → S3'
            elif cezal_s3_cdr:
                # Guaranteed first reduction on one deterministic random active skill.
                candidates=['s1','s2','s3']
                occ=action_occurrences.get(action,1)
                idx=int(deterministic_roll(f'{name}|cdr|{action}|{occ}|1')*len(candidates)) % len(candidates)
                target=candidates[idx]
                ready[target]=max(now,ready[target]-e['value'])
                targets=[target.upper()]
                st['applications']+=1
                # Repeat once if Skill 3 crits.
                if crits>0:
                    idx2=int(deterministic_roll(f'{name}|cdr|{action}|{occ}|2')*len(candidates)) % len(candidates)
                    target2=candidates[idx2]
                    ready[target2]=max(now,ready[target2]-e['value'])
                    targets.append(target2.upper())
                    st['applications']+=1
                st['condition']=f'Random Active Skill' + ('; repeat on crit' if crits>0 else '') + ' → ' + ', '.join(targets)
            else:
                candidates=['s1','s2','s3']; target=candidates[seq%3]; ready[target]=max(now,ready[target]-e['value']); st['applications']+=1; st['condition']=f'{e["condition"]} → {target.upper()}'
        elif nm=='Cooldown Increase':
            st['applications']+=1
            # Target-side control: recorded, not applied to self rotation.
            pass
        elif nm=='Buff Duration Extension':
            # Alasinthe / effets similaires : la description peut demander de prolonger
            # un nombre limité de buffs *aléatoires*. L'ancienne logique prolongeait
            # tous les buffs actifs, ce qui gonflait artificiellement leur uptime.
            candidates=[k for k,a in active.items() if k in BUFF_NAMES and a['expiry']>now]
            cond_l=(e.get('condition') or '').lower()
            n_targets=1
            m=re.search(r'(?:up to\s*)?(\d+)\s+random buff',cond_l)
            if m: n_targets=max(1,int(m.group(1)))
            if candidates:
                # Tirage déterministe, pour conserver exactement la même simulation
                # lors des comparaisons contrefactuelles avec/sans effet.
                pool=list(candidates); chosen=[]
                occ=action_occurrences.get(action,1)
                for pick in range(min(n_targets,len(pool))):
                    idx=int(deterministic_roll(f'{name}|buffext|{action}|{occ}|{seq}|{pick}')*len(pool)) % len(pool)
                    chosen.append(pool.pop(idx))
                for k in chosen:
                    active[k]['expiry']+=e['value']; register_interval(k,now,active[k]['expiry'])
                st['applications']+=len(chosen)
                st['condition']=(e.get('condition') or 'Random buff') + (' → '+', '.join(chosen) if chosen else '')
            else:
                st['applications']+=0
        elif nm=='Debuff Duration Extension':
            st['applications']+=1
            for k,a in active.items():
                if (k in DEBUFF_NAMES or 'Down' in k) and a['expiry']>now: a['expiry']+=e['value']; register_interval(k,now,a['expiry'])
        elif e['duration']>0:
            st['applications']+=1
            old_bonus=effective_buff_value(nm,now-1e-9) if nm=='Skill Recovery Up' else 0.0
            expiry=now+e['duration']; active[nm]={'value':e['value'],'expiry':expiry}; register_interval(nm,now,expiry)
            if nm=='Skill Recovery Up': adjust_ready_for_recovery(now,old_bonus,effective_buff_value(nm,now+1e-9))
        else:
            st['applications']+=1
        return True

    def current_multipliers(now):
        atk=atk_base*(1+effective_buff_value('ATK Up',now)); cr=max(0,min(1,cr_base+effective_buff_value('Crit Rate Up',now)+elem_mod['crit_delta'])); cd=cdmg_base+effective_buff_value('Crit DMG Up',now)
        combo=1+num(h.get('combo_speed'))+combo_add+effective_buff_value('Combo SPD Up',now)
        skillsp=1+num(h.get('skill_speed'))+skill_speed_add+effective_buff_value('Skill SPD Up',now)
        rec=1+num(h.get('skill_recovery'))+recovery_add+effective_buff_value('Skill Recovery Up',now)
        bdef=boss_def*(1-effective_debuff_value('DEF Down',now))
        weaken=effective_debuff_value('Weakness',now)
        shock_mult=1.0  # boss immunisé au Shock / contrôle de foule
        weak=(1+weaken)*shock_mult-1
        return atk,cr,cd,combo,skillsp,rec,bdef,weak

    while t<duration and rowno<3000:
        process_dot_ticks(t)
        expire_dynamic_buffs(t)
        while team_boundary_idx<len(team_boundaries) and team_boundaries[team_boundary_idx]<=t+1e-12:
            bt=team_boundaries[team_boundary_idx]; oldr=effective_buff_value('Skill Recovery Up',bt-1e-9); newr=effective_buff_value('Skill Recovery Up',bt+1e-9)
            if abs(oldr-newr)>1e-12: adjust_ready_for_recovery(bt,oldr,newr)
            team_boundary_idx+=1
        rowno+=1; atk,cr,cdmg,combo_mult,skillsp_mult,rec_mult,bdef,weak=current_multipliers(t)
        # choose action
        if t>=ready['ult'] and mana>=ult_cost and (num(rows['ult'].get('Ult Coeff total'))>0 or action_effects(rows['ult'],'Ult')): key='ult'; action='Ultimate'; r=rows['ult']; coef=num(r.get('Ult Coeff total')); hits=max(1,int(num(r.get('Ult Hits'),1))); cast=max(.05,num(h.get('cast_ult'),1)/skillsp_mult); cdsec=parse_seconds(r.get('Cooldown Ult'),15)/rec_mult; pref='Ult'; mana_base=0
        elif t>=ready['s1'] and (num(rows['s1'].get('S1 Coeff total'))>0 or action_effects(rows['s1'],'S1')): key='s1'; action='Skill 1'; r=rows['s1']; coef=num(r.get('S1 Coeff total')); hits=max(1,int(num(r.get('S1 Hits'),1))); cast=max(.05,num(h.get('cast_s1'),1)/skillsp_mult); cdsec=parse_seconds(r.get('Cooldown S1'),999)/rec_mult; pref='S1'; mana_base=num((mr or {}).get('S1 Ult'))
        elif t>=ready['s2'] and (num(rows['s2'].get('S2 Coeff total'))>0 or action_effects(rows['s2'],'S2')): key='s2'; action='Skill 2'; r=rows['s2']; coef=num(r.get('S2 Coeff total')); hits=max(1,int(num(r.get('S2 Hits'),1))); cast=max(.05,num(h.get('cast_s2'),1)/skillsp_mult); cdsec=parse_seconds(r.get('Cooldown S2'),999)/rec_mult; pref='S2'; mana_base=num((mr or {}).get('S2 Ult'))
        elif t>=ready['s3'] and (num(rows['s3'].get('S3 Coeff total'))>0 or action_effects(rows['s3'],'S3')): key='s3'; action='Skill 3'; r=rows['s3']; coef=num(r.get('S3 Coeff total')); hits=max(1,int(num(r.get('S3 Hits'),1))); cast=max(.05,num(h.get('cast_s3'),1)/skillsp_mult); cdsec=parse_seconds(r.get('Cooldown S3'),999)/rec_mult; pref='S3'; mana_base=num((mr or {}).get('S3 Ult'))
        else:
            key='auto'; action=f'Auto {auto_idx}'; r=rows['auto']; coef=num(r.get(f'Auto {auto_idx}')); hits=1; cast=auto_cast_time(name,auto_idx,combo_mult,mr); cdsec=0; pref='Auto 5' if auto_idx==5 else None; mana_base=num((mr or {}).get('Auto Ult moyen / attaque (5)'), num((mr or {}).get('Combo Ult total'))/5 if mr else 0)
        # Brandis Ultimate repeats 3 times while Brandis is Burning.
        if name=='Brandis' and action=='Ultimate' and self_burn_until>t:
            hits*=3; coef*=3
        start=t
        next_auto_before=auto_idx
        action_occurrences[action]=action_occurrences.get(action,0)+1
        occ=action_occurrences[action]
        # Combat normal: critiques déterministes par timeline. Analyse Recovery/Speed:
        # dégâts critiques moyens + déclenchements crit ancrés sur l'occurrence du skill,
        # afin qu'un changement de vitesse ne change pas artificiellement la suite de crits.
        if comparison_mode:
            crit_flags=[deterministic_roll(f'{name}|condcrit|{action}|{occ}|{hi}')<cr for hi in range(hits)]
            crits=sum(1 for x in crit_flags if x)
            crit_mult=1+cr*cdmg
        else:
            crit_flags=[deterministic_roll(f'{name}|crit|{rowno}|{hi}')<cr for hi in range(hits)]
            crits=sum(1 for x in crit_flags if x)
            crit_mult=1+(crits/hits)*cdmg
        # Immediate damage modifiers carried by the action itself.
        action_bonus=0.0
        pre_effects=action_effects(r,pref) if pref else []
        for pe in pre_effects:
            pnm=pe['name'];
            if pnm in disabled_effects: continue
            pc=(pe.get('condition') or '').lower(); pv=pe['value']
            if pnm in ('Damage Bonus per Debuff','Damage bonus per debuff','Damage per debuff'):
                b=pv*target_debuff_count(start)
                m=re.search(r'cap\s*\+?([0-9]+(?:\.[0-9]+)?)%',pc)
                if m: b=min(b,float(m.group(1))/100.0)
                action_bonus+=b
            elif pnm=='Damage Bonus per Buff':
                action_bonus+=pv*self_buff_count(start)
            elif pnm=='Damage Bonus':
                if 'per debuff' in pc:
                    b=pv*target_debuff_count(start)
                    m=re.search(r'cap\s*\+?([0-9]+(?:\.[0-9]+)?)%',pc)
                    if m: b=min(b,float(m.group(1))/100.0)
                    action_bonus+=b
                elif 'per buff' in pc:
                    action_bonus+=pv*self_buff_count(start)
                elif 'target has no buffs' in pc:
                    action_bonus+=pv  # boss dummy has no modeled buffs
                elif pc in ('','always'):
                    action_bonus+=pv
        dmg=atk*coef*crit_mult*dmult(bdef)*(1+weak)*(1+action_bonus)*elem_mod['damage_mult']
        # Counterfactual autos réellement perdues pendant un cast : on part de la
        # prochaine auto de la chaîne au moment où le skill est lancé et on ne compte
        # que les autos complètes qui auraient pu finir pendant l'animation.
        lost_auto_count=0
        lost_auto_damage=0.0
        lost_auto_sequence=[]
        if key!='auto':
            remaining=cast
            ai=next_auto_before
            while lost_auto_count<100:
                ai_cast=auto_cast_time(name,ai,combo_mult,mr)
                if remaining+1e-12<ai_cast:break
                acoef=num(rows['auto'].get(f'Auto {ai}'))
                if comparison_mode:
                    amult=1+cr*cdmg
                else:
                    # Le coût d'opportunité doit rester stable et lisible : dégâts
                    # critiques moyens, indépendants du RNG de la timeline normale.
                    amult=1+cr*cdmg
                admg=atk*acoef*amult*dmult(bdef)*(1+weak)
                lost_auto_damage+=admg
                lost_auto_count+=1
                lost_auto_sequence.append(f'Auto {ai}')
                remaining-=ai_cast
                ai=1 if ai==5 else ai+1
        # Devi S3: the first hit grants Crit DMG Up, so the second hit already benefits.
        if name=='Devi' and action=='Skill 3' and hits>=2:
            s3buff=next((e for e in action_effects(r,'S3') if e['name']=='Crit DMG Up'),None)
            if s3buff:
                per_hit_coef=coef/hits
                extra_prob=cr if comparison_mode else (1.0 if crit_flags[1] else 0.0)
                dmg += atk*per_hit_coef*s3buff['value']*extra_prob*dmult(bdef)*(1+weak)*elem_mod['damage_mult']
        total+=dmg; damage_by['Auto' if key=='auto' else action]+=dmg
        effects=[e for e in pre_effects if e['name'] not in disabled_effects]; effect_results=[]
        # cooldown/mana state changes
        if key=='ult':
            mana=max(0,mana-ult_cost); ready['ult']=start+cdsec; auto_idx=1
        elif key in ('s1','s2','s3'):
            ready[key]=start+cdsec; auto_idx=1; mana+=mana_base*mana_gen_factor(start)
        else:
            mana+=mana_base*mana_gen_factor(start)
        mana=min(ult_cost,mana)
        action_pass_chance=debuff_pass_chance(start)
        res_down_before=effective_debuff_value('RES Down',start)
        for e in effects:
            ok=apply_effect(e,start,action,rowno,crits,hits,action_pass_chance); effect_results.append(f"{e['name']} {'✓' if ok else '✗'}")
        # Auto chain increments after processing Auto5 effect
        if key=='auto': auto_idx=1 if auto_idx==5 else auto_idx+1
        t=min(duration,t+cast)
        log.append({'n':rowno,'time':round(start,3),'action':action,'duration':round(cast,3),'hits':hits,'crits':crits,'damage':round(dmg,2),'mana_after':round(mana,1),'s1_cd':round(max(0,ready['s1']-t),2),'s2_cd':round(max(0,ready['s2']-t),2),'s3_cd':round(max(0,ready['s3']-t),2),'ult_cd':round(max(0,ready['ult']-t),2),'effects':', '.join(effect_results),'next_auto_before':next_auto_before,'lost_auto_count':lost_auto_count,'lost_auto_damage':round(lost_auto_damage,2),'lost_auto_sequence':', '.join(lost_auto_sequence),'boss_def_effective':round(bdef,2),'res_down_active':round(res_down_before,4),'debuff_pass_chance':round(action_pass_chance,4),'mana_gen_factor':round(mana_gen_factor(start),4)})

    process_dot_ticks(duration)
    def union_time(xs):
        xs=sorted((max(0,a),min(duration,b)) for a,b in xs if b>a)
        if not xs:return 0
        s,e=xs[0]; tot=0
        for a,b in xs[1:]:
            if a<=e:e=max(e,b)
            else:tot+=e-s;s,e=a,b
        return tot+e-s
    def effect_engine_status(nm):
        handled={
            'DEF Down','RES Down','Weakness','Shock','ATK Up','Crit Rate Up','Crit DMG Up','Combo SPD Up','Skill SPD Up',
            'Skill Recovery Up','Mana Generation Up','Cooldown reduction','Cooldown Increase','Buff Duration Extension',
            'Debuff Duration Extension','Gain Ultimate Mana','Ultimate Mana Gain','Ultimate Mana Gain (crit)',
            'Ultimate Mana Gain (non-crit)','Ultimate Mana Gain / hit','Ultimate Mana Gain %',
            'Active Skill 2 Cooldown Reduction','Active Skill 3 Cooldown Reduction','Active Skill Cooldown Reduction',
            'Self Active Skill Cooldown Reduction','Damage Bonus','Damage Bonus per Debuff','Damage bonus per debuff',
            'Damage per debuff','Damage Bonus per Buff'
        }
        record_only={'ATK Down','Move SPD Down','Skill Recovery Down','ACC Down','Crit Rate Down','Crit DMG Down','Combo SPD Down','Skill SPD Down','DEF Up','RES Up','Move SPD Up'}
        if nm in handled: return 'Pris en compte'
        if nm=='Burn' and name=='Brandis': return 'Pris en compte — DoT stackable'
        if nm in ('Burn','Bleed'): return 'DoT à modéliser précisément'
        if nm in record_only: return 'Sans impact DPS solo direct'
        return 'Détecté — logique spécifique à vérifier'
    eff=[]
    for nm,st in stats.items():
        up=union_time(intervals.get(nm,[])); eff.append({'effect':nm,'type':'Debuff' if (nm in DEBUFF_NAMES or 'Down' in nm) else 'Buff' if (nm in BUFF_NAMES or 'Up' in nm) else 'Spécial','attempts':st['attempts'],'triggered':st.get('triggered',st['attempts']),'acc_tests':st.get('acc_tests',0),'successes':st['successes'],'rate':st['successes']/st.get('triggered',1) if st.get('triggered',0) else 0,'expected_rate':(st.get('chance_sum',0.0)/st.get('acc_tests',1) if st.get('acc_tests',0) else 1.0),'applications':st['applications'],'value':st['value'],'duration':st['duration'],'uptime_s':round(up,2),'uptime':up/duration if duration else 0,'actions':', '.join(sorted(st['actions'])),'condition':st['condition'],'engine_status':effect_engine_status(nm)})
    eff.sort(key=lambda x:(0 if x['type']=='Debuff' else 1 if x['type']=='Buff' else 2,x['effect']))
    if analyze_effect_gains and eff:
        base_dps=(total/duration) if duration else 0
        for e in eff:
            nm=e['effect']
            cf=simulate_combat(name,lv,duration,boss_def,boss_res,boss_hp,boss_atk,boss_element,atk_pct,cr_add,cd_add,combo_add,skill_speed_add,recovery_add,mana_add,acc_add,accuracy_final,resistance_final,comparison_mode,disabled_effects|{nm},False,team_supports,disabled_team_buffs,adds_mode)
            e['gain_dps']=round(base_dps-(cf['dps'] if cf else base_dps),2)
            e['gain_damage']=round(e['gain_dps']*duration,2)
            e['gain_pct']=round((e['gain_dps']/((cf['dps'] if cf else base_dps) or 1)),6)
    else:
        for e in eff: e['gain_dps']=0.0; e['gain_damage']=0.0; e['gain_pct']=0.0
    dot_by_source={}
    for b in burns:
        src=b.get('source') or 'DoT'
        dot_by_source[src]=dot_by_source.get(src,0.0)+num(b.get('damage'))
    final_stats={'atk':round(atk_base,2),'crit_rate':cr_base,'crit_dmg':cdmg_base,'accuracy':acc,'resistance':num(h.get('resistance')) if resistance_final is None else num(resistance_final),'combo_speed':num(h.get('combo_speed'))+combo_add,'skill_speed':num(h.get('skill_speed'))+skill_speed_add,'skill_recovery':num(h.get('skill_recovery'))+recovery_add,'mana_gen':num(h.get('mana_gen'))+mana_add}; resistance_check=resistance_check_breakdown(acc,boss_res,elem_mod['debuff_delta']); build={'atk_pct':atk_pct,'crit_rate_add':cr_add,'crit_dmg_add':cd_add,'accuracy_add':acc_add,'accuracy_final':acc,'combo_speed_add':combo_add,'skill_speed_add':skill_speed_add,'skill_recovery_add':recovery_add,'mana_gen_add':mana_add,'resistance_final':resistance_final}; return {'hero':name,'duration':duration,'total_damage':round(total,2),'dps':round(total/duration,2) if duration else 0,'actions':len(log),'damage_by':{k:round(v,2) for k,v in damage_by.items()},'dot_by_source':{k:round(v,2) for k,v in dot_by_source.items()},'log':log,'effects':eff,'levels':lv,'final_stats':final_stats,'base_stats':h,'build':build,'boss':{'defense':boss_def,'resistance':boss_res,'hp':boss_hp,'attack':boss_atk,'element':boss_element},'hero_element':hero_elem,'element_matchup':elem_mod,'resistance_check':resistance_check,'supports':support_info,'team_buffs':summarize_team_buffs([e for e in team_events if e['effect'] not in disabled_team_buffs],duration),'auto_timings':({'source':'extracted','base_chain_s':[auto_base_chain_time(name,i,mr) for i in range(1,6)],'base_cycle_s':auto_chain_cycle_base(name,mr)} if auto_timing_row(name) else {'source':'legacy_fallback','base_chain_s':[auto_base_chain_time(name,i,mr) for i in range(1,6)],'base_cycle_s':auto_chain_cycle_base(name,mr)}),'note':'Simulation Smishie’s Lab déterministe. Les buffers jouent leur rotation en parallèle, appliquent leurs buffs équipe et tentent leurs débuffs sur le boss avec leur PRE contre sa RES. Les modificateurs élémentaires PvE affectent dégâts, Crit Rate et chance de débuff du carry et des supports. Pour une même famille, le buff le plus fort est actif; un buff plus faible peut reprendre après expiration. Une nouvelle application de la même source remplace l’ancienne.'}




class _GGSkillHTMLParser(HTMLParser):
    BLOCKS={'p','div','li','br','h1','h2','h3','h4','section','article','tr','td'}
    def __init__(self):
        super().__init__(); self.sections=[]; self._heading=None; self._body=[]; self._hbuf=[]; self._in_h3=False; self._skip=0
    def handle_starttag(self,tag,attrs):
        tag=tag.lower()
        if tag in ('script','style','svg'): self._skip+=1; return
        if self._skip:return
        if tag=='h3':
            if self._heading is not None:self.sections.append((self._heading,' '.join(self._body)))
            self._heading=None; self._body=[]; self._hbuf=[]; self._in_h3=True
        elif tag in self.BLOCKS:
            self._body.append(' ')
    def handle_endtag(self,tag):
        tag=tag.lower()
        if tag in ('script','style','svg') and self._skip:
            self._skip-=1; return
        if self._skip:return
        if tag=='h3':
            self._heading=' '.join(self._hbuf).strip(); self._in_h3=False
        elif tag in self.BLOCKS:self._body.append(' ')
    def handle_data(self,data):
        if self._skip:return
        t=' '.join(str(data or '').split())
        if not t:return
        if self._in_h3:self._hbuf.append(t)
        elif self._heading is not None:self._body.append(t)
    def close(self):
        super().close()
        if self._heading is not None:self.sections.append((self._heading,' '.join(self._body)))

def _gg_slug(name):
    s=unicodedata.normalize('NFKD',str(name or '')).encode('ascii','ignore').decode('ascii').lower()
    s=s.replace('&',' and ').replace("'",' ')
    return re.sub(r'[^a-z0-9]+','-',s).strip('-')

def _gg_fetch_hero_page(name):
    slug=_gg_slug(name)
    slugs=[slug]
    # Naming mismatch between the in-game roster and some public databases.
    if str(name or '').strip().lower()=='roxxi and gum':
        slugs=['roxxi-and-gum','roxxi-gumm','roxxi-gum','roxxi-and-gumm']
    urls=[]
    for s in slugs:
        urls.extend([
            f'https://www.ggnoluck.com/en/invokers/heroes/{s}',
            f'https://www.ggnoluck.com/en/invokers/guides/heroes/{s}/build',
        ])
    last=None
    for url in urls:
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 SmishiesLab-AoE/1.0','Accept-Language':'en'})
            with urllib.request.urlopen(req,timeout=8) as r:
                raw=r.read().decode('utf-8','replace')
            if len(raw)>1000:return url,raw
        except Exception as e:last=e
    raise RuntimeError(str(last or 'page GGNoLuck introuvable'))

def _gg_target_count_from_text(text, rarity=None):
    t=' '.join(unescape(str(text or '')).split())
    # Explicit "selected target + N around it" => total is N+1.
    m=re.search(r'Selects\s+1\s+enemy.*?Attacks\s+(?:the\s+)?(\d+)\s+enemies.*?around\s+the\s+target',t,re.I)
    if m:return min(11,int(m.group(1))+1),'selected+around'
    # Explicit total target count.
    for pat in (
        r'Attacks\s+(?:the\s+)?(\d+)\s+enemies\b',
        r'Pulls\s+(\d+)\s+enemies\b',
        r'Hits\s+(\d+)\s+enemies\b',
        r'Damages\s+(\d+)\s+enemies\b',
    ):
        m=re.search(pat,t,re.I)
        if m:return min(11,int(m.group(1))),'explicit'
    # Clear single-target wording wins over later references to "targets".
    if re.search(r'Attacks\s+1\s+enemy\b',t,re.I):
        return 1,'single'
    # Geometry/path AoE without an explicit count. Use the game's rarity target cap,
    # but only when the wording clearly says multiple enemies can be damaged.
    geom=(
        re.search(r'damaging\s+each\s+enemy\s+hit',t,re.I) or
        re.search(r'all\s+enemies',t,re.I) or
        re.search(r'enemies\s+in\s+(?:a|the)\s+\d',t,re.I) or
        re.search(r'(?:cone|radius|area|path).*?(?:enemies|targets)',t,re.I)
    )
    if geom:
        caps={'common':8,'uncommon':8,'rare':8,'epic':9,'legendary':10}
        cap=caps.get(str(rarity or '').strip().lower())
        if cap:return cap,'geometry-cap'
    return None,None

def _gg_extract_aoe_for_hero(name):
    url,html=_gg_fetch_hero_page(name)
    p=_GGSkillHTMLParser(); p.feed(html); p.close()
    sections=p.sections
    hero=hero_row(name) or {}
    rarity=hero.get('rarity')
    out={}; evidence={}; unresolved=[]
    aliases={'Active 1':'Skill 1','Active 2':'Skill 2','Active 3':'Skill 3','Ultimate':'Ultimate'}
    for suffix,action in aliases.items():
        matches=[(h,b) for h,b in sections if str(h).strip().lower().endswith(suffix.lower())]
        if not matches:
            unresolved.append(action); continue
        h,b=matches[0]
        n,kind=_gg_target_count_from_text(b,rarity)
        if n is None:
            unresolved.append(action); continue
        out[action]=n
        evidence[action]={'heading':h,'kind':kind,'excerpt':' '.join(b.split())[:300]}

    combos=[(h,b) for h,b in sections if str(h).strip().lower()=='combo' or str(h).strip().lower().endswith(' combo')]
    if combos:
        body=' '.join(combos[0][1].split())
        mapped=False

        # Older GGNoLuck layout: Hit 1..Hit 6.
        # Hit 1 is the opening strike; the game's five autos are Hit 2..Hit 6.
        hitpos=[]
        for m in re.finditer(r'\b([1-9])\.\s*Hit\s+\1\b',body,re.I):
            hitpos.append((int(m.group(1)),m.start(),m.end()))
        if hitpos:
            byhit={}
            for j,(hn,s,e) in enumerate(hitpos):
                seg=body[e:(hitpos[j+1][1] if j+1<len(hitpos) else len(body))]
                n,kind=_gg_target_count_from_text(seg,rarity)
                if n is not None: byhit[hn]=(n,kind,seg[:300])
            if all(h in byhit for h in range(2,7)):
                for auto_idx,h in enumerate(range(2,7),1):
                    n,kind,seg=byhit[h]; action=f'Auto {auto_idx}'
                    out[action]=n
                    evidence[action]={'heading':f'Combo Hit {h}','kind':kind,'excerpt':' '.join(seg.split())[:300]}
                mapped=True

        # Newer layout: Combo 0 is opening, Combo 1..5 are the five autos.
        if not mapped:
            marks=[]
            for m in re.finditer(r'\bCombo\s+([0-5])(?:\s*·\s*Combo\s+([0-5]))?',body,re.I):
                nums=[int(m.group(1))]
                if m.group(2) is not None: nums.append(int(m.group(2)))
                marks.append((nums,m.start(),m.end()))
            bycombo={}
            for j,(nums,s,e) in enumerate(marks):
                seg=body[e:(marks[j+1][1] if j+1<len(marks) else len(body))]
                n,kind=_gg_target_count_from_text(seg,rarity)
                if n is None: continue
                for hn in nums: bycombo[hn]=(n,kind,seg[:300])
            if all(h in bycombo for h in range(1,6)):
                for h in range(1,6):
                    n,kind,seg=bycombo[h]; action=f'Auto {h}'
                    out[action]=n
                    evidence[action]={'heading':f'Combo {h}','kind':kind,'excerpt':' '.join(seg.split())[:300]}
                mapped=True

        if not mapped:
            unresolved.extend([f'Auto {i}' for i in range(1,6)])
    else:
        unresolved.extend([f'Auto {i}' for i in range(1,6)])
    return {'hero':name,'url':url,'targets':out,'evidence':evidence,'unresolved':sorted(set(unresolved))}

def import_ggnoluck_aoe_all():
    ensure_aoe_table()
    # Rebuild automatic rows from scratch. Manual corrections are preserved.
    with sqlite3.connect(DB) as con:
        con.execute("DELETE FROM aoe_targets WHERE lower(source)='ggnoluck'")
        con.commit()
    heroes=[r['name'] for r in q('SELECT name FROM heroes WHERE name IS NOT NULL ORDER BY name')]
    done=[]; failed=[]; saved=0
    for name in heroes:
        try:
            d=_gg_extract_aoe_for_hero(name)
            if d.get('targets'):
                saved+=save_aoe_targets(name,d['targets'],'ggnoluck')
            done.append({'hero':name,'targets':d.get('targets') or {},'unresolved':d.get('unresolved') or [],'url':d.get('url')})
        except Exception as e:
            failed.append({'hero':name,'error':str(e)})
    return {'ok':True,'heroes_total':len(heroes),'heroes_read':len(done),'failed_count':len(failed),
            'saved_actions':saved,'done':done,'failed':failed[:100]}

AOE_KNOWN_TARGETS={
    # Confirmed mechanics.
    'Moros': {'Auto 1':1,'Auto 2':1,'Auto 3':1,'Auto 4':1,'Auto 5':11,'Skill 1':1,'Skill 2':10,'Skill 3':11,'Ultimate':11},
    # Cezal: only the fifth real auto is AoE; GGNoLuck represents it as Combo/Hit 6 after the opening hit.
    'Cezal': {'Auto 1':1,'Auto 2':1,'Auto 3':1,'Auto 4':1,'Auto 5':9},
    # User-confirmed: Sildrea has AoE only on S2 and S3; autos, S1 and Ult are single-target.
    'Sildrea': {'Auto 1':1,'Auto 2':1,'Auto 3':1,'Auto 4':1,'Auto 5':1,'Skill 1':1,'Skill 2':10,'Skill 3':10,'Ultimate':1},
}

def ensure_aoe_table():
    with sqlite3.connect(DB) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS aoe_targets (
            hero_name TEXT NOT NULL,
            action TEXT NOT NULL,
            targets INTEGER NOT NULL DEFAULT 1,
            source TEXT DEFAULT 'manual',
            confidence REAL DEFAULT 1,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(hero_name,action)
        )""")
        con.commit()

def _aoe_actions():
    return [f'Auto {i}' for i in range(1,6)]+['Skill 1','Skill 2','Skill 3','Ultimate']

def _aoe_text_blob_for_action(name,action):
    # Search every textual cell of the selected coefficient row. This lets the
    # detector benefit automatically from richer coefficient imports later.
    pr=profile_for(name); lv=profile_levels(pr)
    key={'Auto 1':'auto','Auto 2':'auto','Auto 3':'auto','Auto 4':'auto','Auto 5':'auto',
         'Skill 1':'s1','Skill 2':'s2','Skill 3':'s3','Ultimate':'ult'}.get(action)
    if not key:return ''
    row=coeff_row(name,lv.get(key,7)) or {}
    vals=[]
    for k,v in row.items():
        if v is None:continue
        s=str(v)
        if s and not re.fullmatch(r'[-+0-9., %x×/s]+',s.strip(),re.I):
            vals.append(s)
    return ' | '.join(vals)

def infer_aoe_targets_from_text(name,enemies=11):
    """Conservative text inference: only explicit target counts or 'all enemies'."""
    out={}
    evidence={}
    for action in _aoe_actions():
        txt=_aoe_text_blob_for_action(name,action)
        low=txt.lower()
        val=None; why=None
        if re.search(r'\b(all|every)\s+(enemies|enemy|targets|opponents)\b',low):
            val=max(1,int(enemies)); why='all enemies'
        else:
            pats=[
                r'\bup to\s+(\d+)\s+(?:enemies|enemy|targets|opponents)\b',
                r'\b(\d+)\s+(?:enemies|enemy|targets|opponents)\b',
                r'\b(?:hits?|attacks?)\s+(\d+)\s+(?:enemies|targets|opponents)\b',
            ]
            for pat in pats:
                m=re.search(pat,low)
                if m:
                    val=max(1,int(m.group(1))); why=m.group(0); break
        if val is not None:
            out[action]=val
            evidence[action]={'targets':val,'evidence':why,'text':txt[:500]}
    return out,evidence

def saved_aoe_targets(name):
    ensure_aoe_table()
    rows=q('SELECT action,targets,source,confidence FROM aoe_targets WHERE lower(hero_name)=lower(?)',(name,))
    return {r['action']:{'targets':int(r['targets']),'source':r.get('source') or 'manual','confidence':num(r.get('confidence'),1)} for r in rows}

def save_aoe_targets(name,targets,source='manual'):
    ensure_aoe_table(); saved=0
    src=str(source or 'manual')
    with sqlite3.connect(DB) as con:
        for action,val in (targets or {}).items():
            if action not in _aoe_actions():continue
            n=max(1,min(11,int(val or 1)))
            cur=con.execute('SELECT source FROM aoe_targets WHERE lower(hero_name)=lower(?) AND action=?',(name,action)).fetchone()
            # Automatic imports must never overwrite a user-confirmed manual mapping.
            if src=='ggnoluck' and cur and str(cur[0] or '').lower()=='manual':
                continue
            con.execute("""INSERT INTO aoe_targets(hero_name,action,targets,source,confidence,updated_at)
                           VALUES(?,?,?,?,1,CURRENT_TIMESTAMP)
                           ON CONFLICT(hero_name,action) DO UPDATE SET targets=excluded.targets,source=excluded.source,confidence=1,updated_at=CURRENT_TIMESTAMP""",
                        (name,action,n,src))
            saved+=1
        con.commit()
    return saved

def aoe_default_targets(name,enemies=11):
    out={a:1 for a in _aoe_actions()}
    sources={a:'unknown' for a in _aoe_actions()}
    saved=saved_aoe_targets(name)
    # Automatic source, only when the skill parser resolved it cleanly.
    for a,meta in saved.items():
        if str(meta.get('source') or '').lower()=='ggnoluck':
            out[a]=int(meta['targets']); sources[a]='ggnoluck'
    # Project-validated mechanics override imported data.
    for a,v in AOE_KNOWN_TARGETS.get(str(name or ''),{}).items():
        out[a]=v; sources[a]='validated'
    # Explicit/manual corrections always win.
    for a,meta in saved.items():
        if str(meta.get('source') or '').lower()!='ggnoluck':
            out[a]=int(meta['targets']); sources[a]=meta.get('source') or 'manual'
    out={a:min(max(1,int(v)),int(enemies)) for a,v in out.items()}
    return out,sources

def simulate_aoe(name,preset='box',duration=60,enemies=11,defense=0,resistance=0,element='Neutre',target_overrides=None):
    """AoE sandbox on effectively infinite-HP enemies.

    Rotation and single-target damage come from simulate_combat. Each direct action
    and each DoT source is then expanded by the number of enemies that action can hit.
    Unknown target counts remain 1 and are explicitly reported as such so the UI never
    pretends an unmapped skill is AoE.
    """
    enemies=max(1,min(11,int(enemies or 11)))
    bld,st,lv,label,key=combat_preset_for(name,preset)
    base=simulate_combat(name,lv,duration,defense,resistance,1e15,0,element,**bld)
    if not base:return None
    targets,target_sources=aoe_default_targets(name,enemies)
    for k,v in (target_overrides or {}).items():
        if k in targets:
            targets[k]=max(1,min(enemies,int(v or 1)))
    # Never hit more enemies than exist.
    targets={k:min(enemies,max(1,int(v))) for k,v in targets.items()}

    direct_by_action={}
    aoe_direct=0.0
    for row in base.get('log',[]):
        action=row.get('action') or ''
        dmg=num(row.get('damage'))
        mult=targets.get(action,1)
        direct_by_action.setdefault(action,{'single_target_damage':0.0,'aoe_damage':0.0,'casts':0,'targets':mult})
        z=direct_by_action[action]
        z['single_target_damage']+=dmg; z['aoe_damage']+=dmg*mult; z['casts']+=1
        aoe_direct+=dmg*mult

    aoe_dot=0.0; dot_rows={}
    for src,dmg in (base.get('dot_by_source') or {}).items():
        mult=targets.get(src,1)
        dot_rows[src]={'single_target_damage':num(dmg),'aoe_damage':num(dmg)*mult,'targets':mult}
        aoe_dot+=num(dmg)*mult

    total=aoe_direct+aoe_dot
    rows=[]
    for action,z in direct_by_action.items():
        rows.append({'action':action,'targets':z['targets'],'casts':z['casts'],
                     'single_target_damage':round(z['single_target_damage'],2),
                     'aoe_damage':round(z['aoe_damage'],2)})
    for src,z in dot_rows.items():
        rows.append({'action':src+' DoT','targets':z['targets'],'casts':'—',
                     'single_target_damage':round(z['single_target_damage'],2),
                     'aoe_damage':round(z['aoe_damage'],2)})
    rows.sort(key=lambda x:num(x.get('aoe_damage')),reverse=True)
    mapped=[k for k,v in targets.items() if v>1]
    return {'hero':name,'preset':key,'preset_label':label,'preset_stats':st,'preset_levels':lv,
            'duration':duration,'enemies':enemies,'defense':defense,'resistance':resistance,'element':element,
            'targets':targets,'target_sources':target_sources,'mapped_aoe_actions':mapped,'total_damage':round(total,2),
            'dps':round(total/duration,2) if duration else 0,
            'single_target_dps':base.get('dps',0),'rows':rows,
            'note':'PV ennemis simulés comme quasi infinis. Les actions non encore cartographiées restent à 1 cible jusqu’à validation.'}

def attack_crit_analysis(name, atk_final=0, cr_final=.7, cd_final=1.4, bonus_atk=.225, bonus_cr=.225, bonus_cd=.30):
    h=hero_row(name)
    if not h:return None
    base=num(h.get('atk')); atk=max(.001,num(atk_final,base)); cr=min(1,max(0,num(cr_final))); cd=max(0,num(cd_final))
    def score(a,r,d): return a*(1+min(1,r)*d)
    cur=score(atk,cr,cd)
    opts=[('Actuel',atk,cr,cd),('+ ATK %',atk+base*bonus_atk,cr,cd),('+ Crit Rate',atk,min(1,cr+bonus_cr),cd),('+ Crit DMG',atk,cr,cd+bonus_cd)]
    out=[]
    for label,a,r,d in opts:
        ss=score(a,r,d); out.append({'option':label,'atk':a,'crit_rate':r,'crit_dmg':d,'crit_mult':1+r*d,'score':ss,'gain':ss/cur-1 if cur else 0})
    ranked=sorted(out[1:],key=lambda x:x['score'],reverse=True)
    try: t_atk_cr=((atk*bonus_cr*cd)/(base*bonus_atk)-1)/cd
    except: t_atk_cr=None
    try: t_atk_cd=(base*bonus_atk)/(atk*bonus_cd-base*bonus_atk*cd)
    except: t_atk_cd=None
    try: t_cr_cd=(bonus_cr*cd)/bonus_cd
    except: t_cr_cd=None
    try: t_cd_atk_cr=(base*bonus_atk)/(atk*bonus_cr-base*bonus_atk*cr)
    except: t_cd_atk_cr=None
    try: t_cd_cr_cd=(cr*bonus_cd)/bonus_cr
    except: t_cd_cr_cd=None
    return {'hero':name,'base_atk':base,'current':{'atk':atk,'crit_rate':cr,'crit_dmg':cd,'score':cur},'bonuses':{'atk':bonus_atk,'crit_rate':bonus_cr,'crit_dmg':bonus_cd},'options':out,'recommendation':ranked[0]['option'] if ranked else None,'thresholds':{'atk_vs_cr':t_atk_cr,'atk_vs_cd':t_atk_cd,'cr_vs_cd':t_cr_cd,'cd_atk_vs_cr':t_cd_atk_cr,'cd_cr_vs_cd':t_cd_cr_cd}}

def recovery_speed_analysis(name, levels, duration, boss_def,boss_res,boss_hp,boss_atk,element, current_stats, tested_stats):
    h=hero_row(name)
    if not h:return None
    mr=mana_row(name)
    combo_base=auto_chain_cycle_base(name,mr)
    b0=final_to_build(name,current_stats); b1=final_to_build(name,tested_stats)
    base=simulate_combat(name,levels,duration,boss_def,boss_res,boss_hp,boss_atk,element,comparison_mode=True,**b0)
    test=simulate_combat(name,levels,duration,boss_def,boss_res,boss_hp,boss_atk,element,comparison_mode=True,**b1)
    if not base or not test:return None

    skills=('Skill 1','Skill 2','Skill 3','Ultimate')
    def summarize(sim):
        acts={k:{'casts':0,'damage':0.0,'time':0.0,'lost_count':0,'lost_damage':0.0,'lost_sequence':[]} for k in skills}
        auto_count=0; auto_damage=0.0; auto_time=0.0
        for x in sim['log']:
            a=x.get('action',''); dmg=num(x.get('damage')); tm=num(x.get('duration'))
            if a in acts:
                acts[a]['casts']+=1; acts[a]['damage']+=dmg; acts[a]['time']+=tm
                acts[a]['lost_count']+=int(num(x.get('lost_auto_count')))
                acts[a]['lost_damage']+=num(x.get('lost_auto_damage'))
                seq=x.get('lost_auto_sequence','')
                if seq: acts[a]['lost_sequence'].append(seq)
            elif str(a).startswith('Auto'):
                auto_count+=1; auto_damage+=dmg; auto_time+=tm
        skill_time=sum(a['time'] for a in acts.values())
        skill_damage=sum(a['damage'] for a in acts.values())
        time_for_autos=max(.001,duration-skill_time)
        # Same idea as the Google Sheet: auto DPS during time where the hero is free to auto.
        auto_dps_active=auto_damage/time_for_autos if time_for_autos>0 else 0
        avg_auto_damage=auto_damage/auto_count if auto_count else 0
        avg_auto_time=auto_time/auto_count if auto_count else 0
        details=[]
        for k,a in acts.items():
            casts=a['casts']; blocked=a['time']; dmg=a['damage']
            avg_cast=blocked/casts if casts else 0
            dmg_per=dmg/casts if casts else 0
            # Coût exact : autos complètes qui auraient réellement pu être jouées
            # pendant les casts, à partir de la position courante de la chaîne Auto1→Auto5.
            auto_lost=a['lost_damage']
            autos_missed=a['lost_count']
            net=dmg-auto_lost
            seq=' | '.join(a['lost_sequence'])
            details.append({'skill':k,'casts':casts,'skill_damage':dmg,'damage_per_cast':dmg_per,'cast_time':avg_cast,'blocked_time':blocked,'autos_missed':autos_missed,'auto_damage_lost':auto_lost,'lost_auto_sequence':seq,'net_total':net,'net_per_cast':net/casts if casts else 0,'verdict':'WORTH' if net>0 else 'PERTE DPS' if casts else 'NON CASTÉ'})
        combo_real=combo_base/max(.001,1+num(sim['final_stats'].get('combo_speed')))
        combo_hz=1/combo_real if combo_real>0 else 0
        auto_hz=5*combo_hz
        return {'dps':sim['dps'],'total_damage':sim['total_damage'],'skill_damage':skill_damage,'auto_damage':auto_damage,'auto_count':auto_count,'avg_auto_damage':avg_auto_damage,'avg_auto_time':avg_auto_time,'auto_dps_active':auto_dps_active,'blocked_time':skill_time,'occupation':skill_time/duration if duration else 0,'time_for_autos':max(0,duration-skill_time),'combo_base_time':combo_base,'combo_real_time':combo_real,'combo_per_second':combo_hz,'autos_per_second_theoretical':auto_hz,'details':details,'final_stats':sim['final_stats']}
    a=summarize(base); b=summarize(test)
    extra_skill=b['skill_damage']-a['skill_damage']; auto_change=b['auto_damage']-a['auto_damage']; total_change=b['total_damage']-a['total_damage']; other_change=total_change-extra_skill-auto_change
    delta={'dps':b['dps']-a['dps'],'total_damage':total_change,'skill_damage':extra_skill,'auto_damage':auto_change,'other_damage':other_change,'blocked_time':b['blocked_time']-a['blocked_time'],'auto_count':b['auto_count']-a['auto_count'],'occupation':b['occupation']-a['occupation']}
    # Pair skill rows for easy UI comparison.
    paired=[]
    bd={x['skill']:x for x in a['details']}; td={x['skill']:x for x in b['details']}
    for k in skills:
        x=bd[k]; y=td[k]
        paired.append({'skill':k,'current':x,'tested':y,'delta_casts':y['casts']-x['casts'],'delta_skill_damage':y['skill_damage']-x['skill_damage'],'delta_auto_damage_lost':y['auto_damage_lost']-x['auto_damage_lost'],'delta_net':y['net_total']-x['net_total']})
    return {'hero':name,'current':a,'tested':b,'delta':delta,'details':paired}


def recovery_balance_analysis(name, levels, duration, boss_def,boss_res,boss_hp,boss_atk,element, current_stats):
    """Trouve la meilleure répartition Recovery / Skill Speed à budget total constant.
    Le budget = Recovery affichée + Skill Speed affichée de l'utilisateur.
    Combo Speed et toutes les autres stats restent fixes.
    """
    h=hero_row(name)
    if not h:return None
    cur=dict(current_stats)
    total=max(0.0,num(cur.get('skill_recovery'))+num(cur.get('skill_speed')))
    # Pas de 1 point de pourcentage. On inclut précisément le build actuel et les bornes.
    step=0.01
    vals={0.0,total,num(cur.get('skill_recovery'))}
    n=int(total/step)+1
    for i in range(n+1):
        r=min(total,i*step); vals.add(round(r,10))
    rows=[]
    for r in sorted(vals):
        sp=max(0.0,total-r)
        st=dict(cur); st['skill_recovery']=r; st['skill_speed']=sp
        b=final_to_build(name,st)
        sim=simulate_combat(name,levels,duration,boss_def,boss_res,boss_hp,boss_atk,element,comparison_mode=True,**b)
        if sim: rows.append({'recovery':r,'skill_speed':sp,'dps':sim['dps'],'total_damage':sim['total_damage']})
    if not rows:return None
    rows.sort(key=lambda x:x['dps'],reverse=True)
    best=rows[0]
    cur_b=final_to_build(name,cur)
    cur_sim=simulate_combat(name,levels,duration,boss_def,boss_res,boss_hp,boss_atk,element,comparison_mode=True,**cur_b)
    # Gains marginaux à +1 point de pourcentage sans retirer l'autre stat.
    marg={}
    for key in ('skill_recovery','skill_speed','combo_speed'):
        st=dict(cur); st[key]=num(st.get(key))+0.01
        sim=simulate_combat(name,levels,duration,boss_def,boss_res,boss_hp,boss_atk,element,comparison_mode=True,**final_to_build(name,st))
        marg[key]=(sim['dps']-cur_sim['dps']) if sim and cur_sim else 0
    # Zone quasi optimale = au moins 99,5 % du meilleur DPS à budget identique.
    threshold=best['dps']*0.995
    zone=[x for x in rows if x['dps']>=threshold]
    zone_rec=(min(x['recovery'] for x in zone),max(x['recovery'] for x in zone)) if zone else (best['recovery'],best['recovery'])
    zone_sp=(min(x['skill_speed'] for x in zone),max(x['skill_speed'] for x in zone)) if zone else (best['skill_speed'],best['skill_speed'])
    # Quelques points autour du meilleur pour rendre la courbe lisible.
    by_rec=sorted(rows,key=lambda x:x['recovery'])
    near=sorted(by_rec,key=lambda x:abs(x['recovery']-best['recovery']))[:9]
    near=sorted(near,key=lambda x:x['recovery'])
    return {'hero':name,'budget':total,'current':{'recovery':num(cur.get('skill_recovery')),'skill_speed':num(cur.get('skill_speed')),'combo_speed':num(cur.get('combo_speed')),'dps':cur_sim['dps'] if cur_sim else 0},'best':best,'gain_vs_current':best['dps']-(cur_sim['dps'] if cur_sim else 0),'zone':{'recovery_min':zone_rec[0],'recovery_max':zone_rec[1],'skill_speed_min':zone_sp[0],'skill_speed_max':zone_sp[1]},'marginal_dps_per_1pct':marg,'near_best':near}



# ---------- Import local depuis Invokers: Titan Legacy ----------
# Sécurité : ce module est volontairement en LECTURE SEULE vis-à-vis des fichiers du jeu.
# Toute écriture doit rester confinée à la base propre de Smishie's Lab (invokers.db).
GAME_IMPORT_READ_ONLY = True

def _game_ro_open(path, mode='rb'):
    """Open a game file strictly read-only. Any write-capable mode is rejected."""
    if not GAME_IMPORT_READ_ONLY:
        raise RuntimeError('Le verrou lecture seule du module jeu est désactivé.')
    # Refuse all write/update/append/create modes, including +.
    if any(ch in mode for ch in ('w','a','x','+')):
        raise PermissionError('Smishie\'s Lab interdit toute écriture dans les fichiers Invokers.')
    if mode not in ('rb','r','rt'):
        raise PermissionError('Mode d\'ouverture non autorisé pour un fichier Invokers.')
    return open(path, mode)

def _game_readonly_status():
    return {'read_only': True, 'policy': 'lecture seule stricte',
            'writes_to_game_files': False,
            'note': "Les fichiers Invokers sont uniquement lus. Les profils importés sont enregistrés seulement dans invokers.db de Smishie's Lab."}
def _candidate_game_roots():
    env=os.environ
    user=env.get('USERPROFILE') or os.path.expanduser('~')
    appdata=env.get('APPDATA') or os.path.join(user,'AppData','Roaming')
    local=env.get('LOCALAPPDATA') or os.path.join(user,'AppData','Local')
    low=os.path.join(user,'AppData','LocalLow')
    roots=[
        os.path.join(appdata,'zone.hitzone.invokers.launcher'),
        os.path.join(appdata,'zone.hitzone.invokers.launcher','game'),
        os.path.join(local,'zone.hitzone.invokers.launcher'),
        os.path.join(local,'Invokers Titan Legacy'),
        os.path.join(local,'Programs','Invokers Titan Legacy'),
        os.path.join(low,'Hitzone'), os.path.join(low,'HitZone'),
        os.path.join(low,'zone.hitzone.invokers'), os.path.join(low,'Invokers Titan Legacy'),
    ]
    # Unity range souvent les saves dans LocalLow/<Company>/<Product>. On découvre
    # prudemment les dossiers dont le nom évoque Invokers/Hitzone/zone.
    for base in (low,local,appdata):
        if not os.path.isdir(base): continue
        try:
            for n1 in os.listdir(base):
                p1=os.path.join(base,n1)
                if not os.path.isdir(p1): continue
                key=n1.lower()
                if any(k in key for k in ('invoker','hitzone','zone')):
                    roots.append(p1)
                try:
                    for n2 in os.listdir(p1):
                        p2=os.path.join(p1,n2)
                        if os.path.isdir(p2) and any(k in (n1+' '+n2).lower() for k in ('invoker','hitzone','zone')):
                            roots.append(p2)
                except OSError: pass
        except OSError: pass
    out=[]
    for r in roots:
        if r and os.path.isdir(r) and r not in out: out.append(r)
    return out

GAME_EXTS={'.json','.db','.sqlite','.sqlite3','.ldb','.log','.dat','.sav','.bin','.txt','.prefs','.config'}

def _data_candidates(root):
    out=[]
    if not root or not os.path.isdir(root): return out
    for base,dirs,files in os.walk(root):
        # On garde les stockages web/Unity (Local Storage, leveldb), mais ignore les caches lourds.
        dirs[:] = [d for d in dirs if d.lower() not in {'crashpad','logs','temp','tmp','shadercache','gpucache'}]
        for fn in files:
            low=fn.lower(); fp=os.path.join(base,fn)
            try: sz=os.path.getsize(fp)
            except OSError: continue
            if sz<=0 or sz>80*1024*1024: continue
            ext=os.path.splitext(low)[1]
            interesting=(ext in GAME_EXTS or any(k in low for k in ('box','save','player','profile','invoker','relic','titan','leveldb','local storage','prefs')))
            # Les fichiers LevelDB MANIFEST/CURRENT n'ont parfois pas d'extension.
            if low.startswith(('manifest-','current')): interesting=True
            if interesting: out.append((fp,sz))
    return out

def _load_json_file(path):
    try:
        with _game_ro_open(path,'rb') as f: raw=f.read()
        for enc in ('utf-8-sig','utf-16','utf-8'):
            try: txt=raw.decode(enc); break
            except Exception: txt=None
        if not txt: return None
        txt=txt.strip()
        if not txt or txt[0] not in '[{': return None
        return json.loads(txt)
    except Exception: return None

def _walk_json(obj,path='$',depth=0,maxdepth=12):
    if depth>maxdepth: return
    yield path,obj
    if isinstance(obj,dict):
        for k,v in obj.items(): yield from _walk_json(v,f'{path}.{k}',depth+1,maxdepth)
    elif isinstance(obj,list):
        for i,v in enumerate(obj[:5000]): yield from _walk_json(v,f'{path}[{i}]',depth+1,maxdepth)

def _norm_key(k): return re.sub(r'[^a-z0-9]','',str(k).lower())
def _pick(d,*aliases):
    if not isinstance(d,dict): return None
    nd={_norm_key(k):v for k,v in d.items()}
    for a in aliases:
        k=_norm_key(a)
        if k in nd and nd[k] not in (None,''): return nd[k]
    return None

def _pct(v):
    x=num(v,None)
    if x is None: return None
    return x/100 if abs(x)>3 else x

def _hero_name_from_obj(d,hero_names):
    cand=_pick(d,'name','heroName','invokerName','characterName','displayName','unitName')
    if isinstance(cand,str):
        hit=hero_names.get(cand.strip().lower())
        if hit:return hit
    return None

def _profile_from_obj(d,hero_name):
    p={'name':hero_name}; found=0
    amap={
      'atk':('atk','attack','finalAtk','attackFinal','totalAtk','attackTotal'),
      'crit_rate':('critRate','criticalRate','critChance','criticalChance','finalCritRate'),
      'crit_dmg':('critDmg','critDamage','criticalDamage','finalCritDmg'),
      'accuracy':('accuracy','acc','precision','pre','finalAccuracy'),
      'resistance':('resistance','res','finalResistance'),
      'combo_speed':('comboSpeed','comboSpd','finalComboSpeed'),
      'skill_speed':('skillSpeed','skillSpd','finalSkillSpeed'),
      'skill_recovery':('skillRecovery','recovery','skillHaste','finalSkillRecovery'),
      'mana_gen':('manaGen','manaGeneration','finalManaGen'),}
    for dst,als in amap.items():
        v=_pick(d,*als)
        if v is not None:
            p[dst]=_pct(v) if dst in ('crit_rate','crit_dmg','combo_speed','skill_speed','skill_recovery','mana_gen') else num(v); found+=1
    levels={'auto_level':('autoLevel','basicLevel','comboLevel','autoSkillLevel'),'s1_level':('s1Level','skill1Level','ability1Level'),'s2_level':('s2Level','skill2Level','ability2Level'),'s3_level':('s3Level','skill3Level','ability3Level'),'ult_level':('ultLevel','ultimateLevel','skill4Level')}
    for dst,als in levels.items():
        v=_pick(d,*als)
        if v is not None: p[dst]=int(num(v,7)); found+=1
    return p if found>=2 else None

def _raw_hero_mentions(path, hero_names, max_read=40*1024*1024):
    try:
        with _game_ro_open(path,'rb') as f: raw=f.read(max_read)
    except Exception: return []
    low=raw.lower(); hits=[]
    for lname,pretty in hero_names.items():
        b=lname.encode('utf-8','ignore')
        if len(b)>=4 and b in low: hits.append(pretty)
        if len(hits)>=25: break
    return hits

def _sqlite_info(path, hero_names):
    try:
        with _game_ro_open(path,'rb') as f: sig=f.read(16)
        if sig!=b'SQLite format 3\x00': return None
        con=sqlite3.connect(f'file:{path}?mode=ro',uri=True); cur=con.cursor()
        tables=[r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        con.close()
        return tables[:30]
    except Exception: return None


GAME_DIFF_SNAPSHOT={}
LAST_GAME_DIFF=[]

def _snapshot_game_files():
    """Capture size/mtime of files under likely Invokers user-data roots.
    Metadata-only so this stays fast even with large Unity data files.
    """
    roots=_candidate_game_roots()
    snap={}; total=0
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for base,dirs,files in os.walk(root):
            # Avoid huge immutable install trees when possible; keep user-data/cache stores.
            lowbase=base.lower()
            dirs[:] = [d for d in dirs if d.lower() not in {'crashpad','shadercache','gpucache','temp','tmp'}]
            for fn in files:
                fp=os.path.join(base,fn)
                try:
                    st=os.stat(fp)
                except OSError:
                    continue
                # Ignore giant binary assets; a profile/cache file should be far smaller.
                if st.st_size > 200*1024*1024:
                    continue
                key=os.path.normcase(os.path.abspath(fp))
                snap[key]={'path':fp,'root':root,'size':st.st_size,'mtime_ns':st.st_mtime_ns}
                total+=1
                if total>=50000:
                    break
            if total>=50000:
                break
        if total>=50000:
            break
    return {'roots':roots,'files':snap,'count':len(snap)}

def start_game_diff_snapshot():
    global GAME_DIFF_SNAPSHOT
    GAME_DIFF_SNAPSHOT=_snapshot_game_files()
    return {'ok':True,'count':GAME_DIFF_SNAPSHOT.get('count',0),'roots':GAME_DIFF_SNAPSHOT.get('roots',[]),**_game_readonly_status()}

def compare_game_diff_snapshot():
    global LAST_GAME_DIFF
    before=GAME_DIFF_SNAPSHOT or {'files':{},'roots':[]}
    after=_snapshot_game_files()
    b=before.get('files',{}); a=after.get('files',{})
    changed=[]
    hero_names={r['name'].lower():r['name'] for r in q('SELECT name FROM heroes WHERE name IS NOT NULL')}
    for key,cur in a.items():
        old=b.get(key)
        status=None
        if old is None:
            status='créé'
        elif old.get('size')!=cur.get('size') or old.get('mtime_ns')!=cur.get('mtime_ns'):
            status='modifié'
        if not status:
            continue
        fp=cur['path']; low=os.path.basename(fp).lower(); rel=os.path.relpath(fp,cur['root'])
        obj=_load_json_file(fp)
        top=[]; ftype='fichier'; mentions=[]; sqltables=None
        if obj is not None:
            ftype='JSON'; top=list(obj.keys())[:12] if isinstance(obj,dict) else [f'list[{len(obj)}]'] if isinstance(obj,list) else [type(obj).__name__]
        else:
            sqltables=_sqlite_info(fp,hero_names)
            if sqltables is not None:
                ftype='SQLite'; top=['tables: '+', '.join(sqltables[:8])]
            elif low.endswith(('.ldb','.log')) or 'leveldb' in fp.lower():
                ftype='LevelDB/log'
        # Only content-scan reasonably small changed files.
        if cur['size'] <= 40*1024*1024:
            mentions=_raw_hero_mentions(fp,hero_names)
        changed.append({
            'status':status,'root':cur['root'],'file':rel,'full_path':fp,
            'size_before':old.get('size') if old else None,'size_after':cur['size'],
            'delta_size':cur['size']-(old.get('size',0) if old else 0),
            'type':ftype,'top_keys':top,'hero_mentions':mentions[:12],
            'hero_mention_count':len(mentions)
        })
    for key,old in b.items():
        if key not in a:
            changed.append({'status':'supprimé','root':old['root'],'file':os.path.relpath(old['path'],old['root']),
                            'full_path':old['path'],'size_before':old['size'],'size_after':0,'delta_size':-old['size'],
                            'type':'fichier','top_keys':[],'hero_mentions':[],'hero_mention_count':0})
    # Highest-value files first: user-data roots, DB/JSON/LevelDB, then recency delta.
    def score(x):
        p=(x.get('full_path') or '').lower()
        userroot=int('locallow' in p or ('appdata\\local' in p and 'programs' not in p) or ('appdata\\roaming' in p and '\\game\\' not in p))
        typ=int(x.get('type') in ('JSON','SQLite','LevelDB/log'))
        hint=int(any(k in p for k in ('player','profile','save','cache','local storage','leveldb','prefs','account','inventory','collection')))
        return (userroot,hint,typ,x.get('hero_mention_count',0),abs(x.get('delta_size',0)))
    changed.sort(key=score, reverse=True)
    LAST_GAME_DIFF=changed[:300]
    return {'ok':True,'before_count':before.get('count',0),'after_count':after.get('count',0),'changed_count':len(changed),'changed':LAST_GAME_DIFF,**_game_readonly_status()}

def _redact_game_text(text):
    # Avoid displaying credentials/tokens that can appear in logs.
    text=re.sub(r'(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._~+\-/=]+', r'\1[REDACTED]', text)
    text=re.sub(r'(?i)(access[_-]?token|refresh[_-]?token|id[_-]?token|session[_-]?token|password|passwd|cookie)\s*[:=]\s*[\"\']?[^\s,;\"\']+', r'\1=[REDACTED]', text)
    # JWT-like blobs.
    text=re.sub(r'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}(?:\.[A-Za-z0-9_-]{10,})?', '[REDACTED_JWT]', text)
    return text

def _printable_strings(raw, min_len=5):
    # ASCII/UTF-8-ish strings from binary/log files, read-only.
    parts=re.findall(rb'[\x20-\x7e]{%d,}' % min_len, raw)
    out=[]
    for b in parts:
        try: t=b.decode('utf-8','ignore').strip()
        except Exception: continue
        if t: out.append(t)
    return out

def analyze_last_game_diff():
    hero_names=[r['name'] for r in q('SELECT name FROM heroes WHERE name IS NOT NULL')]
    hero_lows=[x.lower() for x in hero_names]
    keywords=('invoker','hero','heroes','collection','inventory','roster','character','unit','profile','account',
              'relic','equipment','equip','titan','skill','level','rank','awak','stat','attack','defense','accuracy',
              'resistance','crit','speed','recovery','mana','loadout','api','graphql','grpc','http','socket','player')
    reports=[]
    for item in (LAST_GAME_DIFF or []):
        if item.get('status')=='supprimé':
            continue
        fp=item.get('full_path')
        if not fp or not os.path.isfile(fp):
            continue
        try: size=os.path.getsize(fp)
        except OSError: continue
        # Focus on user-data files and cap reads. Large static binaries are deliberately skipped.
        low=fp.lower()
        priority=any(k in low for k in ('player.log','otlp_','pending_bi_events','breadcrumb','local storage','leveldb','cache','profile','save'))
        if size>8*1024*1024 and not priority:
            continue
        try:
            with _game_ro_open(fp,'rb') as f: raw=f.read(min(size,8*1024*1024))
        except Exception:
            continue
        strings=_printable_strings(raw)
        interesting=[]; urls=[]; hero_hits=[]
        for t in strings:
            tl=t.lower()
            if ('http://' in tl or 'https://' in tl or 'wss://' in tl or 'ws://' in tl):
                for u in re.findall(r'(?:https?|wss?)://[^\s\"\'<>]+', t, flags=re.I):
                    u=_redact_game_text(u)[:500]
                    if u not in urls: urls.append(u)
            hs=[hero_names[i] for i,h in enumerate(hero_lows) if len(h)>=4 and h in tl]
            if hs:
                for h in hs:
                    if h not in hero_hits: hero_hits.append(h)
            if hs or any(k in tl for k in keywords):
                clean=_redact_game_text(t)
                if len(clean)>900: clean=clean[:900]+'…'
                if clean not in interesting:
                    interesting.append(clean)
            if len(interesting)>=80 and len(urls)>=20:
                break
        if interesting or urls or hero_hits:
            reports.append({
                'file':item.get('file'),'full_path':fp,'type':item.get('type'),'size':size,
                'hero_hits':hero_hits[:30],'urls':urls[:25],'excerpts':interesting[:80]
            })
    def rscore(x):
        p=x['full_path'].lower()
        return (int('otlp_' in p),int('player.log' in p),len(x['hero_hits']),len(x['urls']),len(x['excerpts']))
    reports.sort(key=rscore, reverse=True)
    return {'ok':True,'files_analyzed':len(reports),'reports':reports[:20],**_game_readonly_status()}


def scan_player_aggregate_artifacts():
    """Read-only targeted scan for player-state artifacts discovered from the game's own logs/traces.
    This does NOT attach to the process or intercept traffic; it only reads files already written by Invokers.
    """
    roots=_candidate_game_roots()
    markers=[
        'PlayerAggregate','InitializePlayerAggregate','ActualizePlayer','PlayerModel','HeroModel',
        'HeroOverviewModel','HeroOverviewGameState','SetupHero','CharacterId','character id',
        'Equipment','Gear','Relic','Titan','SkillLevel','Inventory','Loadout','Choreograph'
    ]
    marker_low=[m.lower() for m in markers]
    rows=[]; seen=set()
    # Include normal candidates plus profiler traces and small/medium unknown files in user-data roots.
    candidates=[]
    for root in roots:
        if not os.path.isdir(root): continue
        for base,dirs,files in os.walk(root):
            dirs[:] = [d for d in dirs if d.lower() not in {'crashpad','shadercache','gpucache','temp','tmp'}]
            for fn in files:
                fp=os.path.join(base,fn)
                try: sz=os.path.getsize(fp)
                except OSError: continue
                if sz<=0 or sz>120*1024*1024: continue
                low=fp.lower()
                # Focus on files likely to contain runtime/user state.
                if not (low.endswith(('.trace','.log','.dat','.bin','.sav','.db','.sqlite','.sqlite3','.ldb','.json')) or
                        any(k in low for k in ('player','aggregate','profile','save','cache','local storage','leveldb','trace','choreograph'))):
                    continue
                real=os.path.normcase(os.path.abspath(fp))
                if real in seen: continue
                seen.add(real); candidates.append((root,fp,sz))
    for root,fp,sz in candidates:
        # Read cap is deliberately conservative and read-only.
        cap=min(sz,24*1024*1024)
        try:
            with _game_ro_open(fp,'rb') as f: raw=f.read(cap)
        except Exception:
            continue
        strings=_printable_strings(raw,4)
        matches=[]; ids=[]; sets=[]
        score=0
        for t in strings:
            tl=t.lower()
            hit=[markers[i] for i,m in enumerate(marker_low) if m in tl]
            if hit:
                clean=_redact_game_text(t)
                if len(clean)>700: clean=clean[:700]+'…'
                if clean not in matches: matches.append(clean)
                score += len(set(hit))*3
            # IDs shown by HeroOverview debug strings are especially useful.
            for m in re.finditer(r'(?i)character\s*id\s*[:=]\s*(\d+)', t):
                if m.group(1) not in ids: ids.append(m.group(1)); score += 4
            # Equipment set/resource names seen in profiler traces.
            for m in re.finditer(r'(?i)Set_[A-Za-z0-9_]+', t):
                v=m.group(0)
                if v not in sets: sets.append(v); score += 2
            if len(matches)>=60: break
        if score or ids or sets:
            rel=os.path.relpath(fp,root)
            rows.append({'root':root,'file':rel,'full_path':fp,'size':sz,'score':score,
                         'markers':matches[:35],'character_ids':ids[:50],'equipment_sets':sets[:50],
                         'is_trace':fp.lower().endswith('.trace')})
    rows.sort(key=lambda x:(x['score'],x['is_trace'],len(x['character_ids']),len(x['equipment_sets']),x['size']), reverse=True)
    return {'ok':True,'count':len(rows),'artifacts':rows[:80],**_game_readonly_status()}



# ---------- Offline snapshot box decoder (read-only) ----------
def _mp_read_varint(data,pos):
    first=struct.unpack_from('b',data,pos)[0]; pos+=1
    if 0 <= first <= 127: return first,pos
    if -120 <= first <= -1: return first,pos
    if first==-121: return data[pos],pos+1
    if first==-122: return struct.unpack_from('b',data,pos)[0],pos+1
    if first==-123: return struct.unpack_from('<H',data,pos)[0],pos+2
    if first==-124: return struct.unpack_from('<h',data,pos)[0],pos+2
    if first==-125: return struct.unpack_from('<I',data,pos)[0],pos+4
    if first==-126: return struct.unpack_from('<i',data,pos)[0],pos+4
    if first==-127: return struct.unpack_from('<Q',data,pos)[0],pos+8
    if first==-128: return struct.unpack_from('<q',data,pos)[0],pos+8
    raise ValueError('MemoryPack varint inconnu: %r'%first)

def _mp_vt(data,start):
    mc=data[start]; pos=start+1; lens=[]
    for _ in range(mc):
        v,pos=_mp_read_varint(data,pos); lens.append(v)
    vals=[]; cur=pos
    for L in lens:
        if L < 0: raise ValueError('Longueur MemoryPack invalide')
        vals.append((cur,cur+L)); cur+=L
    if cur>len(data): raise ValueError('Objet MemoryPack tronqué')
    return mc,lens,vals,cur

def _mp_i32(data,rng):
    s,e=rng; return struct.unpack_from('<i',data,s)[0] if e-s>=4 else None

def _mp_i64(data,rng):
    s,e=rng; return struct.unpack_from('<q',data,s)[0] if e-s>=8 else None

def _mp_bool(data,rng):
    s,e=rng; return bool(data[s]) if e-s>=1 else None

def _mp_dict_i32_i32(data,rng):
    s,e=rng
    if e-s<4:return {}
    n=struct.unpack_from('<i',data,s)[0]
    if n<0 or 4+8*n>e-s:return {}
    out={}; p=s+4
    for _ in range(n):
        k,v=struct.unpack_from('<ii',data,p);p+=8;out[k]=v
    return out

def _mp_pairs_i32(data,rng):
    # Current PlayerHero snapshot stores a list of simple (id, level) structs here.
    return _mp_dict_i32_i32(data,rng)

def _mp_list_i32(data,rng):
    s,e=rng
    if e-s<4:return []
    n=struct.unpack_from('<i',data,s)[0]
    if n<0 or n>256 or 4+4*n>e-s:return []
    return list(struct.unpack_from('<'+'i'*n,data,s+4)) if n else []

def _find_aggregate_snapshot(name):
    target=name.lower()
    for root in _candidate_game_roots():
        if not os.path.isdir(root):continue
        # Prefer the canonical aggregate_snapshots directory.
        cand=os.path.join(root,'aggregate_snapshots',name)
        if os.path.isfile(cand):return cand
        for base,dirs,files in os.walk(root):
            if os.path.basename(base).lower()!='aggregate_snapshots' and 'aggregate_snapshots' not in base.lower():
                if len(base.split(os.sep))-len(root.split(os.sep))>4: dirs[:]=[]
            for fn in files:
                if fn.lower()==target:return os.path.join(base,fn)
    return None

def _find_static_data_file():
    cands=[]
    for root in _candidate_game_roots():
        if not os.path.isdir(root):continue
        for rel in (os.path.join('Invokers_Data','StreamingAssets','static.data'),os.path.join('StreamingAssets','static.data'),'static.data'):
            fp=os.path.join(root,rel)
            if os.path.isfile(fp):
                try:cands.append((os.path.getmtime(fp),fp))
                except OSError:pass
        sd=os.path.join(root,'static_data')
        if os.path.isdir(sd):
            for fn in os.listdir(sd):
                if fn.lower().startswith('static-data.') and fn.lower().endswith('.dat'):
                    fp=os.path.join(sd,fn)
                    try:cands.append((os.path.getmtime(fp),fp))
                    except OSError:pass
    return max(cands)[1] if cands else None

def _read_7bit_int(data,pos):
    """BinaryReader.Read7BitEncodedInt compatible reader."""
    value=0; shift=0
    for _ in range(5):
        if pos>=len(data): raise ValueError('Chaîne ChunkPack tronquée')
        b=data[pos]; pos+=1
        value|=(b & 0x7f)<<shift
        if not (b & 0x80): return value,pos
        shift+=7
    raise ValueError('Longueur de chaîne ChunkPack invalide')

def _read_dotnet_string(data,pos):
    n,pos=_read_7bit_int(data,pos)
    if n<0 or pos+n>len(data): raise ValueError('Chaîne ChunkPack hors limites')
    return data[pos:pos+n].decode('utf-8','replace'),pos+n

def _brotli_decompress_bytes(raw):
    """Use an optional Brotli implementation without making app startup depend on it."""
    last=None
    for modname in ('brotli','brotlicffi'):
        try:
            mod=__import__(modname)
            return mod.decompress(raw),modname
        except ImportError as e:
            last=e
        except Exception as e:
            raise ValueError('Décompression Brotli impossible: %s'%e)
    raise RuntimeError('Module Brotli Python absent (brotli/brotlicffi)')

def _mp_unmanaged_array(data,pos,item_size):
    if pos+4>len(data): raise ValueError('Array MemoryPack tronqué')
    n=struct.unpack_from('<i',data,pos)[0]; pos+=4
    if n<0: return [],pos
    if n>1000000 or pos+n*item_size>len(data): raise ValueError('Array MemoryPack invalide')
    out=[data[pos+i*item_size:pos+(i+1)*item_size] for i in range(n)]
    return out,pos+n*item_size

def _parse_chunkpack_header_blob(data):
    if not data: raise ValueError('Header ChunkPack vide')
    members=data[0]
    if members not in (3,255):
        raise ValueError('Header MemoryPack inattendu: %s'%members)
    if members==255: raise ValueError('Header ChunkPack null')
    pos=1
    keys_raw,pos=_mp_unmanaged_array(data,pos,16)
    chunks_raw,pos=_mp_unmanaged_array(data,pos,16)
    hashes_raw,pos=_mp_unmanaged_array(data,pos,8)
    keys=[]
    for raw in keys_raw:
        # PackChunkKey: Int64 Id, byte Category, 7 bytes explicit padding.
        keys.append({'id':struct.unpack_from('<q',raw,0)[0],'category':raw[8]})
    chunks=[]
    for raw in chunks_raw:
        # PackChunk: Int32 Offset, Size, UncompressedSize, bool IsCompressed (+3 pad).
        chunks.append({'offset':struct.unpack_from('<i',raw,0)[0],
                       'size':struct.unpack_from('<i',raw,4)[0],
                       'uncompressed_size':struct.unpack_from('<i',raw,8)[0],
                       'compressed':bool(raw[12])})
    hashes=[struct.unpack_from('<Q',raw,0)[0] for raw in hashes_raw]
    if len(keys)!=len(chunks):
        raise ValueError('Header ChunkPack incohérent: %s clés / %s chunks'%(len(keys),len(chunks)))
    return {'member_count':members,'keys':keys,'chunks':chunks,'hashes':hashes,'bytes_consumed':pos}

def _static_chunkpack_decoded():
    """Return decoded ChunkPack header + raw data in read-only mode."""
    fp=_find_static_data_file()
    if not fp:return None,None,None,None
    with _game_ro_open(fp,'rb') as fh:data=fh.read()
    if len(data)<24:return fp,None,None,None
    pos=0
    tag,version=struct.unpack_from('<II',data,pos); pos+=8
    if tag!=0x50435A48:return fp,None,None,None
    config_version,pos=_read_dotnet_string(data,pos)
    shared_version,pos=_read_dotnet_string(data,pos)
    if pos+8>len(data):return fp,None,None,None
    header_size,header_result_size=struct.unpack_from('<ii',data,pos); pos+=8
    if header_size<0 or pos+header_size>len(data):return fp,None,None,None
    header_blob,_=_brotli_decompress_bytes(data[pos:pos+header_size]); pos+=header_size
    hdr=_parse_chunkpack_header_blob(header_blob)
    return fp,data,pos,hdr

def _decode_static_chunk(data,chunk_data_start,ch):
    s=chunk_data_start+int(ch.get('offset') or 0); e=s+int(ch.get('size') or 0)
    if not (0<=s<=e<=len(data)):return None
    packed=data[s:e]
    try:
        raw,_=_brotli_decompress_bytes(packed) if ch.get('compressed') else (packed,None)
        return raw
    except Exception:
        return None

def probe_static_for_hero(name,limit=80):
    """Find StaticData chunks plausibly related to one hero.

    This is deliberately diagnostic: it does not assign semantics until a field is
    calibrated against known in-game mechanics.
    """
    fp,data,start,hdr=_static_chunkpack_decoded()
    if not data or not hdr:return {'ok':False,'hero':name,'file':fp,'error':'static.data non décodable'}
    row=next((x for x in STATIC_1302_HERO_ROWS if str(x.get('name') or '').lower()==str(name or '').lower()),None)
    if not row:return {'ok':False,'hero':name,'file':fp,'error':'CharacterConfig introuvable'}
    gdid=int(row.get('gdid') or 0); cfg=int(str(row.get('config_id') or '0') or 0); code=str(row.get('code') or ''); nm=str(row.get('name') or name)
    sigs=[]
    if gdid:sigs.append(('gdid_i32',struct.pack('<i',gdid)))
    if cfg:sigs.append(('config_i64',struct.pack('<q',cfg)))
    if code:sigs.append(('code_ascii',code.encode('utf-8')))
    if nm:sigs.append(('name_utf8',nm.encode('utf-8')))
    hits=[]
    cats={}
    for idx,(key,ch) in enumerate(zip(hdr['keys'],hdr['chunks'])):
        cats[key.get('category')]=cats.get(key.get('category'),0)+1
        # Key-id match is especially strong and costs no decompression.
        reasons=[]
        if int(key.get('id') or 0) in (gdid,cfg):reasons.append('key_id')
        raw=None
        if reasons:
            raw=_decode_static_chunk(data,start,ch)
        else:
            # Only scan moderately sized chunks; giant main aggregate is handled separately.
            if int(ch.get('uncompressed_size') or ch.get('size') or 0)<=2_000_000:
                raw=_decode_static_chunk(data,start,ch)
                if raw:
                    for lab,sig in sigs:
                        if sig and raw.find(sig)>=0:reasons.append(lab)
        if not reasons:continue
        if raw is None:raw=_decode_static_chunk(data,start,ch)
        preview={}
        if raw:
            ints=[struct.unpack_from('<i',raw,i)[0] for i in range(0,min(len(raw)-3,128),4)]
            small=[x for x in ints if -1<=x<=50]
            # printable strings help reveal SkillConfig/member names or embedded codes.
            strs=[m.group(0).decode('utf-8','replace') for m in re.finditer(rb'[A-Za-z][A-Za-z0-9_./ -]{3,80}',raw[:4096])]
            preview={'size':len(raw),'first_96_hex':raw[:96].hex(),'small_i32_first128':small[:40],'strings':strs[:30]}
        hits.append({'index':idx,'category':key.get('category'),'id':key.get('id'),'reasons':reasons,
                     'compressed':bool(ch.get('compressed')),'size':ch.get('size'),'uncompressed_size':ch.get('uncompressed_size'),
                     'preview':preview})
        if len(hits)>=int(limit):break
    return {'ok':True,'hero':nm,'gdid':gdid,'config_id':str(cfg),'code':code,'file':fp,
            'category_counts':cats,'candidate_count':len(hits),'candidates':hits,
            'read_only':True,'note':'Diagnostic brut : aucune sémantique AoE n’est appliquée automatiquement.'}

def inspect_static_chunkpack():
    """Read-only parser for the game's current ChunkPack static.data container."""
    fp=_find_static_data_file()
    if not fp:
        return {'ok':False,'error':'static.data / static-data.*.dat introuvable',**_game_readonly_status()}
    try:
        with _game_ro_open(fp,'rb') as fh: data=fh.read()
        if len(data)<24: raise ValueError('Fichier StaticData trop court')
        pos=0
        tag,version=struct.unpack_from('<II',data,pos); pos+=8
        if tag!=0x50435A48:
            raise ValueError('Signature ChunkPack invalide: 0x%08X'%tag)
        config_version,pos=_read_dotnet_string(data,pos)
        shared_version,pos=_read_dotnet_string(data,pos)
        if pos+8>len(data): raise ValueError('Tailles du header ChunkPack absentes')
        header_size,header_result_size=struct.unpack_from('<ii',data,pos); pos+=8
        if header_size<0 or header_result_size<0 or pos+header_size>len(data):
            raise ValueError('Tailles du header ChunkPack invalides')
        compressed_header=data[pos:pos+header_size]; pos+=header_size
        try:
            header_blob,brotli_backend=_brotli_decompress_bytes(compressed_header)
        except RuntimeError as e:
            return {'ok':True,'file':fp,'tag':'0x%08X'%tag,'file_version':version,
                    'config_version':config_version,'shared_version':shared_version,
                    'header_size':header_size,'header_uncompressed_size':header_result_size,
                    'chunk_data_start':pos,'brotli_available':False,'header_decoded':False,
                    'warning':str(e),**_game_readonly_status()}
        if len(header_blob)!=header_result_size:
            raise ValueError('Header décompressé: %s octets, attendu %s'%(len(header_blob),header_result_size))
        hdr=_parse_chunkpack_header_blob(header_blob)
        rows=[]
        for idx,(key,ch) in enumerate(zip(hdr['keys'],hdr['chunks'])):
            rows.append({'index':idx,**key,**ch,
                         'hash':hdr['hashes'][idx] if idx<len(hdr['hashes']) else None})
        main=None
        for row in rows:
            if row['category']==0 and row['id']==0:
                main=dict(row); break
        main_probe=None
        if main:
            s=pos+main['offset']; e=s+main['size']
            if 0<=s<=e<=len(data):
                packed=data[s:e]
                try:
                    if main['compressed']:
                        raw,_=_brotli_decompress_bytes(packed)
                    else:
                        raw=packed
                    main_probe={'decoded_size':len(raw),
                                'expected_size':main['uncompressed_size'],
                                'first_byte':raw[0] if raw else None,
                                'first_64_hex':raw[:64].hex()}
                except Exception as e:
                    main_probe={'error':str(e)}
        return {'ok':True,'file':fp,'file_size':len(data),'tag':'0x%08X'%tag,
                'file_version':version,'config_version':config_version,'shared_version':shared_version,
                'header_size':header_size,'header_uncompressed_size':header_result_size,
                'chunk_data_start':pos,'brotli_available':True,'brotli_backend':brotli_backend,
                'header_decoded':True,'chunk_count':len(rows),'chunks':rows[:200],
                'main_chunk':main,'main_probe':main_probe,**_game_readonly_status()}
    except Exception as e:
        return {'ok':False,'file':fp,'error':str(e),**_game_readonly_status()}

def _extract_live_arena_hall_values():
    """Extract StaticArenaData.HallBonuses directly from the game's main StaticData chunk.

    MemoryPack layout validated on 0.60.1302:
      Int32 CharacterStatBonus + Int32 array_count(15) + 15 unmanaged F64(Q32) values.
    The 12 Hall stat entries are serialized contiguously.
    """
    fp=_find_static_data_file()
    if not fp:
        return None
    with _game_ro_open(fp,'rb') as fh:
        data=fh.read()
    if len(data)<24:
        return None

    pos=0
    tag,version=struct.unpack_from('<II',data,pos); pos+=8
    if tag!=0x50435A48:
        return None
    config_version,pos=_read_dotnet_string(data,pos)
    shared_version,pos=_read_dotnet_string(data,pos)
    if pos+8>len(data):
        return None
    header_size,header_result_size=struct.unpack_from('<ii',data,pos); pos+=8
    if header_size<0 or pos+header_size>len(data):
        return None
    header_blob,_=_brotli_decompress_bytes(data[pos:pos+header_size]); pos+=header_size
    hdr=_parse_chunkpack_header_blob(header_blob)

    main=None
    for key,ch in zip(hdr['keys'],hdr['chunks']):
        if key.get('category')==0 and key.get('id')==0:
            main=ch; break
    if not main:
        return None
    s=pos+int(main['offset']); e=s+int(main['size'])
    if not (0<=s<=e<=len(data)):
        return None
    packed=data[s:e]
    raw,_=_brotli_decompress_bytes(packed) if main.get('compressed') else (packed,None)
    if int(main.get('uncompressed_size') or 0) and len(raw)!=int(main['uncompressed_size']):
        return None

    hall_ids=(4,5,6,7,8,9,10,12,13,14,15,16)
    candidates=[]
    for sid in hall_ids:
        pat=struct.pack('<ii',sid,15)
        start=0
        while True:
            idx=raw.find(pat,start)
            if idx<0: break
            arr_start=idx+8
            arr_end=arr_start+15*8
            if arr_end<=len(raw):
                raw_vals=[struct.unpack_from('<q',raw,arr_start+i*8)[0] for i in range(15)]
                vals=[v/4294967296.0 for v in raw_vals]
                mono=all(vals[i]>=vals[i-1] for i in range(1,15))
                nonneg=all(v>=0 for v in vals)
                plausible=mono and nonneg and len({round(v,9) for v in vals})>=10
                if sid in (4,5,6,7,8):
                    plausible=plausible and vals[-1]<=2.0
                else:
                    plausible=plausible and vals[-1]<=10000.0
                if plausible:
                    candidates.append((idx,sid,vals))
            start=idx+1

    # The real HallBonuses dictionary is one compact block containing all 12 ids.
    candidates.sort()
    best=None
    for i in range(len(candidates)):
        base=candidates[i][0]
        block=[x for x in candidates if base<=x[0]<=base+4096]
        by={}
        for off,sid,vals in block:
            by.setdefault(sid,(off,vals))
        if all(sid in by for sid in hall_ids):
            span=max(by[s][0] for s in hall_ids)-min(by[s][0] for s in hall_ids)
            score=(len(by),-span)
            if best is None or score>best[0]:
                best=(score,by)
    if not best:
        return None

    by=best[1]
    values={sid:[float(v) for v in by[sid][1]] for sid in hall_ids}
    offsets={sid:int(by[sid][0]) for sid in hall_ids}
    return {
        'values':values,
        'offsets':offsets,
        'file':fp,
        'config_version':config_version,
        'shared_version':shared_version,
        'main_size':len(raw),
        'source':'StaticArenaData.HallBonuses live'
    }

def _refresh_live_arena_hall_values():
    global ARENA_HALL_VALUES,ARENA_HALL_SOURCE
    try:
        live=_extract_live_arena_hall_values()
        if live and live.get('values'):
            ARENA_HALL_VALUES=live['values']
            ARENA_HALL_SOURCE='%s (%s)'%(live.get('source'),live.get('config_version'))
            return live
    except Exception as e:
        ARENA_HALL_SOURCE='arena_static_data.json fallback (%s)'%e
    return None

def scan_static_hall_f64_arrays():
    """Read-only heuristic scanner for 15-value F64 arrays inside the main StaticData chunk.
    Used only to locate StaticArenaData.HallBonuses before enabling live decoding."""
    pack=inspect_static_chunkpack()
    if not pack.get('ok') or not pack.get('main_chunk'):
        return {'ok':False,'error':pack.get('error') or 'Chunk principal introuvable',
                'pack':pack,**_game_readonly_status()}
    fp=pack.get('file'); main=pack['main_chunk']
    try:
        with _game_ro_open(fp,'rb') as fh: data=fh.read()
        # Re-read container prefix to locate chunk_data_start reliably.
        pos=8
        _,pos=_read_dotnet_string(data,pos)
        _,pos=_read_dotnet_string(data,pos)
        header_size,header_result_size=struct.unpack_from('<ii',data,pos); pos+=8
        pos+=header_size
        s=pos+int(main['offset']); e=s+int(main['size'])
        packed=data[s:e]
        raw,_=_brotli_decompress_bytes(packed) if main.get('compressed') else (packed,None)
        scales=[
            ('q32',4294967296.0),
            ('1e6',1000000.0),
            ('1e9',1000000000.0),
            ('q16',65536.0),
            ('1e4',10000.0),
        ]
        out=[]
        n=len(raw)
        # MemoryPack arrays of unmanaged F64 are typically: Int32 count + count*8 raw bytes.
        for off in range(0,n-124):
            if raw[off:off+4]!=b'\x0f\x00\x00\x00':
                continue
            vals=[struct.unpack_from('<q',raw,off+4+i*8)[0] for i in range(15)]
            if all(v==0 for v in vals): continue
            best=None
            for label,scale in scales:
                ds=[v/scale for v in vals]
                finite=all(abs(x)<100000 for x in ds)
                mono=all(ds[i]>=ds[i-1] for i in range(1,15))
                nonneg=all(x>=0 for x in ds)
                # Hall curves are generally non-negative and usually monotone.
                small=sum(1 for x in ds if 0<=x<=1000)
                score=(20 if finite else 0)+(20 if nonneg else 0)+(30 if mono else 0)+small
                if best is None or score>best[0]:
                    best=(score,label,ds)
            if not best or best[0]<55: continue
            # Favor arrays with actual progression; reject mostly identical/random huge patterns.
            ds=best[2]
            unique=len(set(round(x,10) for x in ds))
            if unique<4: continue
            prev=raw[max(0,off-16):off].hex()
            out.append({
                'offset':off,
                'prefix16_hex':prev,
                'raw_i64':vals,
                'best_scale':best[1],
                'decoded':[round(x,10) for x in ds],
                'monotone':all(ds[i]>=ds[i-1] for i in range(1,15)),
                'unique':unique
            })
            if len(out)>=250: break
        return {'ok':True,'file':fp,'config_version':pack.get('config_version'),
                'main_decoded_size':len(raw),'candidate_count':len(out),
                'candidates':out,**_game_readonly_status()}
    except Exception as e:
        return {'ok':False,'file':fp,'error':str(e),**_game_readonly_status()}

_LIVE_ARENA_HALL_INFO=_refresh_live_arena_hall_values()

def scan_static_data_cache():
    """Locate downloaded StaticData versions in Unity persistentDataPath/static_data.
    Read-only diagnostic: reports paths, sizes and simple version hints only."""
    rows=[]; seen=set()
    for root in _candidate_game_roots():
        if not os.path.isdir(root): continue
        for base,dirs,files in os.walk(root):
            # Keep the scan shallow except when a static_data directory is encountered.
            rel_depth=len(os.path.relpath(base,root).split(os.sep)) if base!=root else 0
            if rel_depth>5:
                dirs[:]=[]
                continue
            if os.path.basename(base).lower()!='static_data':
                continue
            for fn in files:
                fp=os.path.join(base,fn); key=os.path.normcase(os.path.abspath(fp))
                if key in seen: continue
                seen.add(key)
                try:
                    st=os.stat(fp)
                    with _game_ro_open(fp,'rb') as fh: head=fh.read(512)
                except OSError:
                    continue
                printable=''.join(chr(b) if 32<=b<127 else ' ' for b in head)
                vers=sorted(set(re.findall(r'\d+\.\d+\.\d+(?:[-+][A-Za-z0-9._-]+)?', printable)))
                rows.append({'root':root,'path':fp,'file':fn,'size':st.st_size,'mtime':st.st_mtime,
                             'version_hints':vers[:8]})
    rows.sort(key=lambda x:(x.get('mtime',0),x.get('size',0)),reverse=True)
    return {'count':len(rows),'files':rows,**_game_readonly_status()}

def _mp_upgradeable_skills(data,span):
    """Decode PlayerHero.SkillLevels = List<UpgradeableSkill>.
    UpgradeableSkill is effectively (SkillKind, Level). Handles unmanaged 8-byte
    records and version-tolerant 2-member objects.
    Returns {skill_kind: level}.
    """
    s,e=span
    if e-s<4:return {}
    try:
        count=struct.unpack_from('<i',data,s)[0]
    except Exception:
        return {}
    if count<0 or count>32:return {}
    p=s+4; out={}
    # Common MemoryPack path for an unmanaged/value-type pair.
    if p+count*8<=e:
        vals={}
        ok=True
        for i in range(count):
            kind,level=struct.unpack_from('<ii',data,p+i*8)
            if not (-1<=kind<=32 and 0<=level<=20):
                ok=False; break
            vals[int(kind)]=int(level)
        if ok and vals:
            return vals
    # Version-tolerant object fallback.
    p=s+4
    try:
        for _ in range(count):
            mc,lens,spans,p2=_mp_vt(data,p)
            if len(spans)<2:return {}
            kind=_mp_i32(data,spans[0]); level=_mp_i32(data,spans[1])
            if kind is None or level is None:return {}
            out[int(kind)]=int(level)
            p=p2
        return out
    except Exception:
        return {}

def inspect_box_hero_skilllevels(name):
    """Read-only raw inspector for one PlayerHero.SkillLevels member."""
    fp=_find_aggregate_snapshot('PlayerHeroesModel.dat')
    if not fp:
        return {'ok':False,'error':'PlayerHeroesModel.dat introuvable',**_game_readonly_status()}
    target=None
    for cfg,row in STATIC_1302_CONFIG_MAP.items():
        if str(row.get('hero_name') or '').strip().lower()==str(name or '').strip().lower():
            try: target=int(cfg)
            except Exception: target=None
            break
    if target is None:
        return {'ok':False,'error':'Héros inconnu: %s'%name,**_game_readonly_status()}
    try:
        with _game_ro_open(fp,'rb') as fh:data=fh.read()
        mc,lens,root,end=_mp_vt(data,25)
        if len(root)<2:return {'ok':False,'error':'PlayerHeroesModel incomplet',**_game_readonly_status()}
        s,e=root[1]; count=struct.unpack_from('<i',data,s)[0]; p=s+4
        rows=[]
        for _ in range(count):
            dict_id=struct.unpack_from('<i',data,p)[0]; p+=4
            hmc,hlens,hv,hend=_mp_vt(data,p)
            cfg=_mp_i64(data,hv[1]) if len(hv)>1 else None
            if cfg==target:
                item={'dictionary_id':dict_id,'inventory_id':_mp_i32(data,hv[0]),
                      'config_id':cfg,'member_count':hmc,'member_lengths':hlens}
                skill_idx=21 if len(hv)>21 else (10 if len(hv)>10 else None)
                if skill_idx is not None:
                    a,b=hv[skill_idx]; raw=data[a:b]
                    item['skill_member_index']=skill_idx
                    item['skill_span']={'start':a,'end':b,'size':b-a,'hex':raw.hex()}
                    if b-a>=4:
                        n=struct.unpack_from('<i',data,a)[0]
                        item['declared_count']=n
                        item['compact_i32_pairs']=[]
                        if 0<=n<=32 and a+4+n*8<=b:
                            for i in range(n):
                                x,y=struct.unpack_from('<ii',data,a+4+i*8)
                                item['compact_i32_pairs'].append([x,y])
                        # Try object-by-object version-tolerant parsing, without assuming semantics.
                        objs=[]; q=a+4
                        if 0<=n<=32:
                            for i in range(n):
                                try:
                                    omc,olens,ov,oend=_mp_vt(data,q)
                                    members=[]
                                    for mi,(ms,me) in enumerate(ov):
                                        rr=data[ms:me]
                                        z={'member':mi,'size':me-ms,'hex':rr.hex()}
                                        if me-ms>=4:
                                            z['i32']=struct.unpack_from('<i',data,ms)[0]
                                        if me-ms>=8:
                                            z['i64']=struct.unpack_from('<q',data,ms)[0]
                                        members.append(z)
                                    objs.append({'index':i,'member_count':omc,'lengths':olens,
                                                 'start':q,'end':oend,'members':members})
                                    q=oend
                                except Exception as ex:
                                    objs.append({'index':i,'error':str(ex),'start':q}); break
                        item['vt_objects']=objs
                    item['decoded_current']=_mp_upgradeable_skills(data,hv[skill_idx])
                rows.append(item)
            p=hend
        return {'ok':True,'hero':name,'target_config_id':target,'file':fp,'matches':rows,
                **_game_readonly_status()}
    except Exception as e:
        return {'ok':False,'hero':name,'file':fp,'error':str(e),**_game_readonly_status()}

def _decode_playerheroes_file(fp):
    with _game_ro_open(fp,'rb') as f:data=f.read()
    # Snapshot wrapper observed in the game's aggregate_snapshots: 25-byte envelope.
    mc,lens,root,end=_mp_vt(data,25)
    if len(root)<2:raise ValueError('PlayerHeroesModel incomplet')
    s,e=root[1]; count=struct.unpack_from('<i',data,s)[0]; p=s+4
    if count<0 or count>10000:raise ValueError('Nombre de héros improbable')
    heroes=[]
    for _ in range(count):
        dict_id=struct.unpack_from('<i',data,p)[0];p+=4
        hmc,hlens,hv,hend=_mp_vt(data,p)
        if len(hv)<13:raise ValueError('PlayerHero incomplet')
        relics=_mp_dict_i32_i32(data,hv[11])
        accessories=_mp_dict_i32_i32(data,hv[12])
        # PlayerHero v22 (0.60.1302): skill upgrade progression is stored in member 21.
        # Older snapshots used member 10, so keep it as a compatibility fallback.
        skills={}
        if len(hv)>21:
            skills=_mp_upgradeable_skills(data,hv[21])
        if not skills and len(hv)>10:
            skills=_mp_upgradeable_skills(data,hv[10])
        heroes.append({
            'dictionary_id':dict_id,'inventory_id':_mp_i32(data,hv[0]),'config_id':_mp_i64(data,hv[1]),
            'rank':_mp_i32(data,hv[2]),'level':_mp_i32(data,hv[3]),'experience':_mp_i32(data,hv[4]),
            'total_experience':_mp_i32(data,hv[5]),'locked':_mp_bool(data,hv[6]),'in_storage':_mp_bool(data,hv[7]),
            'marker':_mp_i32(data,hv[8]),'relics_by_slot':relics,'accessories_by_slot':accessories,
            # PlayerHero v22: AwakeLevel est le membre 15 et la liste exacte des noeuds le membre 16.
            'awake_level':(_mp_i32(data,hv[15]) if len(hv)>15 and (_mp_i32(data,hv[15]) or 0) in range(0,7) else 0),
            'awake_node_count':(len(_mp_list_i32(data,hv[16])) if len(hv)>16 else 0),
            'awake_node_ids':(_mp_list_i32(data,hv[16]) if len(hv)>16 else []),
            'skill_levels_raw':skills,
            'corruption_tolerance_1':int(skills.get(7,0)) if isinstance(skills,dict) else 0,
            'corruption_tolerance_2':int(skills.get(8,0)) if isinstance(skills,dict) else 0,
            'member_count':hmc
        })
        p=hend
    return heroes

def _decode_playerrelic_stats_blob(fp):
    # Binary layout reverse-engineered from PlayerRelicsModel.dat.
    marker=bytes.fromhex('09040404040408040184ae00')
    stat_offsets=[59,93,127,161,195]
    pct_stats={4,5,6,7,8}
    try:
        with _game_ro_open(fp,'rb') as f:buf=f.read()
    except Exception:return {}
    out={}; start=0
    while True:
        m=buf.find(marker,start)
        if m<0:break
        start=m+1
        try:
            rid=struct.unpack_from('<I',buf,m+12)[0]; slot=struct.unpack_from('<I',buf,m+16)[0]
            stars=struct.unpack_from('<I',buf,m+20)[0]; quality=struct.unpack_from('<I',buf,m+24)[0]
            set_id=struct.unpack_from('<I',buf,m+28)[0]; level=struct.unpack_from('<I',buf,m+40)[0]
            if not (1<=slot<=8 and 1<=stars<=6 and 0<=level<=30):continue
            stats=[]; valid=True
            for idx,rel in enumerate(stat_offsets,1):
                sid=struct.unpack_from('<I',buf,m+rel)[0]
                if sid not in RELIC_STAT_NAMES:valid=False;break
                q32=struct.unpack_from('<I',buf,m+rel+4)[0]; flat=struct.unpack_from('<I',buf,m+rel+8)[0]
                value=round((q32/2**32)*100,6) if sid in pct_stats else flat
                stats.append({'position':idx,'stat_id':sid,'stat':RELIC_STAT_NAMES[sid],'value':value,'kind':'%' if sid in pct_stats else 'points'})
            if valid:out[rid]={'inventory_id':rid,'slot':slot,'stars':stars,'quality_code':quality,'set':set_id,'level':level,'stats':stats}
        except (struct.error,IndexError):continue
    return out

def _decode_playerrelics_file(fp):
    with _game_ro_open(fp,'rb') as f:data=f.read()
    mc,lens,root,end=_mp_vt(data,25)
    if len(root)<2:raise ValueError('PlayerRelicsModel incomplet')
    s,e=root[1]; count=struct.unpack_from('<i',data,s)[0];p=s+4
    if count<0 or count>50000:raise ValueError('Nombre de reliques improbable')
    decoded_stats=_decode_playerrelic_stats_blob(fp); relics=[]
    for _ in range(count):
        dict_id=struct.unpack_from('<i',data,p)[0];p+=4
        rmc,rlens,rv,rend=_mp_vt(data,p)
        eq=None
        if len(rv)>5:
            a,b=rv[5]
            if b-a>=8:
                has,val=struct.unpack_from('<ii',data,a);eq=val if has else None
        rid=_mp_i32(data,rv[0]); extra=decoded_stats.get(rid,{})
        relics.append({'dictionary_id':dict_id,'inventory_id':rid,'slot':_mp_i32(data,rv[1]),
                       'rank':_mp_i32(data,rv[2]),'rarity':_mp_i32(data,rv[3]),'set':_mp_i32(data,rv[4]),
                       'equipped_hero_id':eq,'level':_mp_i32(data,rv[6]),'is_seen':_mp_bool(data,rv[7]),
                       'stars':extra.get('stars'),'quality_code':extra.get('quality_code'),'stats':extra.get('stats') or []})
        p=rend
    return relics

def _static_cfg_name_candidates(static_fp,config_ids):
    if not static_fp:return {}
    try:
        sz=os.path.getsize(static_fp)
        if sz>500*1024*1024:return {}
        with _game_ro_open(static_fp,'rb') as f:raw=f.read()
    except Exception:return {}
    db_names=[r['name'] for r in q('SELECT name FROM heroes WHERE name IS NOT NULL ORDER BY name')]
    name_bytes=[]
    for n in db_names:
        try:name_bytes.append((n,n.encode('utf-8').lower()))
        except:name_bytes.append((n,b''))
    out={}
    for cfg in config_ids:
        if cfg is None:continue
        needle=struct.pack('<q',int(cfg)); starts=[]; pos=0
        while len(starts)<12:
            j=raw.find(needle,pos)
            if j<0:break
            starts.append(j);pos=j+1
        scored={}
        for j in starts:
            lo=max(0,j-8192);hi=min(len(raw),j+8192);win=raw[lo:hi].lower()
            for name,nb in name_bytes:
                if not nb or len(nb)<3:continue
                k=win.find(nb)
                if k>=0:
                    dist=abs((lo+k)-j);score=max(1,8192-dist)
                    if score>scored.get(name,0):scored[name]=score
        ranked=sorted(scored.items(),key=lambda kv:kv[1],reverse=True)[:5]
        nearby=[]
        seen_tok=set()
        for j in starts[:4]:
            lo=max(0,j-1024);hi=min(len(raw),j+1024)
            win=raw[lo:hi]
            for m in re.finditer(rb'[A-Za-z][A-Za-z0-9_\-]{2,47}',win):
                try:tok=m.group(0).decode('ascii')
                except Exception:continue
                low=tok.lower()
                if low in seen_tok:continue
                seen_tok.add(low)
                # Keep useful-looking internal codes/keys, not generic binary noise.
                if any(c.isdigit() for c in tok) or '_' in tok or tok[:1].isupper():
                    nearby.append(tok)
                if len(nearby)>=16:break
            if len(nearby)>=16:break
        out[str(cfg)]={'occurrences':len(starts),'candidates':[{'name':n,'score':sc} for n,sc in ranked],
                       'nearby_tokens':nearby[:16]}
    return out

def decode_local_box():
    hfp=_find_aggregate_snapshot('PlayerHeroesModel.dat')
    rfp=_find_aggregate_snapshot('PlayerRelicsModel.dat')
    afp=_find_aggregate_snapshot('PlayerArenaModel.dat')
    sfp=_find_static_data_file()
    if not hfp:
        return {'ok':False,'error':'PlayerHeroesModel.dat introuvable','heroes_file':None,'relics_file':rfp,'static_data_file':sfp,**_game_readonly_status()}
    heroes=_decode_playerheroes_file(hfp)
    relics=_decode_playerrelics_file(rfp) if rfp else []
    hall_bonuses=_decode_playerarena_hall_file(afp) if afp else []
    bycfg={}
    for h in heroes:
        cfg=h.get('config_id')
        if cfg is None:continue
        cur=bycfg.get(cfg)
        key=(h.get('rank') or 0,h.get('level') or 0,h.get('total_experience') or 0,len(h.get('relics_by_slot') or {}))
        if cur is None: bycfg[cfg]={'copies':1,'best':h,'_key':key}
        else:
            cur['copies']+=1
            if key>cur['_key']:cur['best']=h;cur['_key']=key
    names=_static_cfg_name_candidates(sfp,list(bycfg))
    manual_maps=config_map_all()
    equipped_by_hero={}
    for r in relics:
        hid=r.get('equipped_hero_id')
        if hid is not None:equipped_by_hero.setdefault(hid,[]).append(r)
    # Mapping par config une seule fois, puis application à CHAQUE exemplaire.
    cfgmeta={}; mapped=0
    for cfg,item in bycfg.items():
        ninfo=names.get(str(cfg),{}); nc=ninfo.get('candidates',[]); mm=manual_maps.get(str(cfg)); exact=STATIC_1302_CONFIG_MAP.get(str(cfg))
        name=(exact or {}).get('hero_name') or (mm or {}).get('hero_name') or (nc[0]['name'] if nc else None)
        confidence=(exact or {}).get('confidence',1) if exact else ((mm or {}).get('confidence',1) if mm else (nc[0]['score'] if nc else 0))
        source=(exact or {}).get('source') if exact else ((mm or {}).get('source') if mm else ('static-data' if nc else None))
        cfgmeta[cfg]=(name,confidence,source,nc,ninfo)
        if name:mapped+=1
    relic_by_id={r.get('inventory_id'):r for r in relics if r.get('inventory_id') is not None}
    instances=[]
    for h in heroes:
        cfg=h.get('config_id')
        if cfg is None: continue
        name,confidence,source,nc,ninfo=cfgmeta.get(cfg,(None,0,None,[],{}))
        rids=list((h.get('relics_by_slot') or {}).values())
        details=[relic_by_id[rid] for rid in rids if rid in relic_by_id]
        instances.append({'config_id':str(cfg),'name_candidate':name,'name_score':confidence,'name_source':source,
                          'inventory_id':h.get('inventory_id'),'rank':h.get('rank'),'level':h.get('level'),
                          'awake_level':h.get('awake_level') or 0,'awake_node_count':h.get('awake_node_count') or 0,
                          'awake_node_ids':h.get('awake_node_ids') or [],
                          'total_experience':h.get('total_experience'),'locked':h.get('locked'),'in_storage':h.get('in_storage'),
                          'skill_levels_raw':h.get('skill_levels_raw') or {},
                          'corruption_tolerance_1':h.get('corruption_tolerance_1') or 0,
                          'corruption_tolerance_2':h.get('corruption_tolerance_2') or 0,
                          'relics_by_slot':h.get('relics_by_slot') or {},
                          'equipped_relic_count':len(details),'equipped_relics':details})
    rows=[]
    for cfg,item in sorted(bycfg.items(),key=lambda kv:(-(kv[1]['best'].get('rank') or 0),-(kv[1]['best'].get('level') or 0),kv[0])):
        best=item['best']; name,confidence,source,nc,ninfo=cfgmeta[cfg]
        rows.append({'config_id':str(cfg),'name_candidate':name,'name_score':confidence,'name_source':source,'other_candidates':nc[1:4],
                     'static_occurrences':int(ninfo.get('occurrences') or 0),'nearby_tokens':ninfo.get('nearby_tokens') or [],
                     'copies':item['copies'],'inventory_id':best.get('inventory_id'),'rank':best.get('rank'),'level':best.get('level'),
                     'awake_level':best.get('awake_level') or 0,'awake_node_count':best.get('awake_node_count') or 0,
                     'awake_node_ids':best.get('awake_node_ids') or [],
                     'total_experience':best.get('total_experience'),'locked':best.get('locked'),'in_storage':best.get('in_storage'),
                     'skill_levels_raw':best.get('skill_levels_raw') or {},'relics_by_slot':best.get('relics_by_slot') or {},
                     'equipped_relic_count':len([rid for rid in (best.get('relics_by_slot') or {}).values() if rid in relic_by_id])})
    return {'ok':True,'heroes_file':hfp,'relics_file':rfp,'arena_file':afp,'static_data_file':sfp,'hero_entries':len(heroes),
            'unique_config_ids':len(bycfg),'relic_entries':len(relics),'relics_with_stats':sum(1 for r in relics if r.get('stats')),
            'mapped_names':mapped,'rows':rows,'instances':instances,'relics':relics,'hall_bonuses':hall_bonuses,
            'hall_bonus_count':len(hall_bonuses),**_game_readonly_status()}

def scan_game_import():
    roots=_candidate_game_roots()
    hero_names={r['name'].lower():r['name'] for r in q('SELECT name FROM heroes WHERE name IS NOT NULL')}
    files=[]; detected={}; seen=set()
    for root in roots:
        for fp,sz in _data_candidates(root):
            real=os.path.normcase(os.path.abspath(fp))
            if real in seen: continue
            seen.add(real)
            rel=os.path.relpath(fp,root)
            obj=_load_json_file(fp)
            hits=0; top=[]; ftype='fichier'
            if obj is not None:
                ftype='JSON'; top=list(obj.keys())[:20] if isinstance(obj,dict) else [f'list[{len(obj)}]'] if isinstance(obj,list) else [type(obj).__name__]
                for jpath,node in _walk_json(obj):
                    if not isinstance(node,dict): continue
                    hn=_hero_name_from_obj(node,hero_names)
                    if not hn: continue
                    pr=_profile_from_obj(node,hn)
                    if pr:
                        score=len(pr)
                        if hn not in detected or score>detected[hn]['score']: detected[hn]={'score':score,'profile':pr,'file':rel,'json_path':jpath}
                        hits+=1
            sqltables=_sqlite_info(fp,hero_names)
            if sqltables is not None:
                ftype='SQLite'; top=['tables: '+', '.join(sqltables[:8])]
            lowname=os.path.basename(fp).lower()
            if ftype=='fichier' and (lowname.endswith(('.ldb','.log')) or 'leveldb' in fp.lower()): ftype='LevelDB'
            mentions=_raw_hero_mentions(fp,hero_names)
            # Ne surcharge pas le rapport avec les fichiers statiques sans aucun indice,
            # sauf JSON (utile pour diagnostiquer le dossier sélectionné).
            if obj is not None or mentions or ftype in ('SQLite','LevelDB') or any(k in lowname for k in ('save','player','profile','prefs','box')):
                files.append({'root':root,'file':rel,'size':sz,'type':ftype,'top_keys':top,'hero_stat_hits':hits,'hero_mentions':mentions[:12],'hero_mention_count':len(mentions)})
    # Priorise les fichiers qui citent des héros / bases locales.
    files.sort(key=lambda x:(x.get('hero_stat_hits',0)>0,x.get('hero_mention_count',0),x.get('type') in ('SQLite','LevelDB'),x.get('size',0)), reverse=True)
    return {'roots':roots,'files':files[:250],'profiles':[v for _,v in sorted(detected.items())],'count':len(detected),'diagnostic_hits':sum(1 for x in files if x.get('hero_mention_count',0)>0),**_game_readonly_status()}

def apply_game_import(scan=None):
    scan=scan or scan_game_import(); saved=[]; skipped=[]
    for item in scan.get('profiles',[]):
        pr=dict(item.get('profile') or {}); name=pr.get('name')
        if not name: continue
        cur=profile_for(name); merged=dict(cur); merged.update(pr); merged['name']=name
        if save_profile(merged): saved.append(name)
        else: skipped.append(name)
    return {'ok':True,'saved':saved,'skipped':skipped,'count':len(saved),'scan':scan}

# ---------- HTML ----------
HTML = r'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Smishie's Lab</title><style>
:root{--bg:#0b1020;--panel:#141b31;--p2:#1c2644;--text:#eef3ff;--muted:#9eacd0;--a:#7c9cff;--ok:#43d39e;--warn:#ffd166;--b:#2a365c}*{box-sizing:border-box}body{margin:0;font-family:Segoe UI,Arial;background:var(--bg);color:var(--text)}header{padding:22px 28px;border-bottom:1px solid var(--b)}h1{margin:0}.muted{color:var(--muted)}nav,.subnav{display:flex;gap:8px;flex-wrap:wrap;padding:14px 28px}.subnav{padding:0 0 16px}.tab,.subtab,button,select,input{background:var(--p2);color:var(--text);border:1px solid var(--b);border-radius:9px;padding:9px 12px}.active{background:var(--a)!important;color:#081020}.wrap{padding:0 28px 40px}.hidden{display:none}.controls,.levels{display:flex;gap:9px;flex-wrap:wrap;align-items:end;margin:10px 0 16px}.levels{padding:12px;background:#10182d;border:1px solid var(--b);border-radius:12px}.control{display:flex;flex-direction:column;gap:5px;min-width:120px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card{background:var(--panel);border:1px solid var(--b);border-radius:13px;padding:14px}.big{font-size:24px;font-weight:700}.note{padding:11px;border-left:3px solid var(--warn);background:#171b2b;margin:12px 0}.scroll{max-height:62vh;overflow:auto;border:1px solid var(--b);border-radius:12px}table{width:100%;border-collapse:collapse;background:var(--panel)}th,td{padding:8px 10px;border-bottom:1px solid var(--b);white-space:nowrap;text-align:left}th{position:sticky;top:0;background:#1a2340}.good{color:var(--ok);font-weight:700}.support-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.compare-edit{display:grid;grid-template-columns:1fr 1fr;gap:14px}.donut-wrap{display:flex;gap:18px;align-items:center;flex-wrap:wrap}.donut{width:190px;height:190px;border-radius:50%;position:relative;flex:0 0 auto}.donut:after{content:'';position:absolute;inset:36px;background:var(--panel);border-radius:50%}.legend{display:grid;gap:6px}.legend-row{display:flex;gap:8px;align-items:center}.sw{width:11px;height:11px;border-radius:3px;background:var(--a)}@media(max-width:1100px){.support-grid{grid-template-columns:1fr 1fr}}@media(max-width:850px){.grid{grid-template-columns:1fr 1fr}.compare-edit{grid-template-columns:1fr}}@media(max-width:560px){.grid,.support-grid{grid-template-columns:1fr}}
</style></head><body><header><h1>🧪 Smishie's Lab</h1><div class=muted>version installée affichée dans la console</div></header>
<nav><button class="tab active" data-main="hero">Fiche héros</button><button class=tab data-main="relics">Mes reliques</button><button class=tab data-main="sim">Simulation de combat</button><button class=tab data-main="opt">Optimisation</button><button class=tab data-main="rank">Classement</button></nav><div class=wrap>
<section id=hero><div class=controls><div class=control><label>Héros</label><select id=heroSel></select></div><div class=control><label>Élément</label><select id=heroElement><option>Neutre</option><option>Feu</option><option>Eau</option><option>Vent</option><option>Terre</option><option>Lumière</option><option>Ténèbres</option></select></div></div><div class=card><h3>Ma box</h3><div class=note>🔒 Lecture seule : Smishie's Lab lit automatiquement les données locales d'Invokers sans modifier les fichiers du jeu et sans rien envoyer sur Internet.</div><div class=controls><button id=importBoxBtn>Importer ma box</button></div><div id=gameImportStatus class=good></div><div id=gameImportReport class=scroll></div></div><h3>Fiche utilisée par les simulations</h3><div class=note>Les stats, niveaux de skills, éveil, reliques et Salle des trophées sont actualisés via « Importer ma box ».</div><div id=heroBuild class=levels></div><h3>Niveaux des compétences</h3><div id=heroLevels class=levels></div><div id=heroSaveStatus class=good></div><h3>Ma box</h3><div id=heroBoxInfo class=card></div><h3>Référence MAX du héros (niveau 60 / progression maximale)</h3><div id=heroStats class=grid></div><div id=heroCoeff class=scroll></div><h3>Timings autos extraits du jeu</h3><div class=note>Le simulateur utilise le temps de chaînage propre à chaque Auto 1→5 pour construire la timeline. La durée complète est conservée ici comme référence visuelle.</div><div id=heroAutoTimings class=scroll></div></section>
<section id=relics class=hidden><h2>Mes reliques</h2><div class=note>Inventaire importé directement depuis <b>PlayerRelicsModel.dat</b>. Il comprend les reliques équipées <b>et non équipées</b>. Lecture seule du jeu.</div><div id=relicCounts class=grid></div><div class=controls><div class=control><label>Pièce</label><select id=relicSlot><option value=all>Toutes</option><option value=1>Arme</option><option value=2>Bouclier</option><option value=3>Casque</option><option value=4>Épaulières</option><option value=5>Gantelets</option><option value=6>Plastron</option><option value=7>Ceinture</option><option value=8>Bottes</option></select></div><div class=control><label>Set ID</label><select id=relicSet><option value=all>Tous</option></select></div><div class=control><label>Équipement</label><select id=relicEquipped><option value=all>Toutes</option><option value=yes>Équipées</option><option value=no>Non équipées</option></select></div><div class=control><label>Stat</label><select id=relicStat><option value=all>Toutes</option><option value=1>ATQ</option><option value=2>DEF</option><option value=3>PV</option><option value=4>ATQ %</option><option value=5>DEF %</option><option value=6>PV %</option><option value=7>Taux crit</option><option value=8>Dég crit</option><option value=9>PRÉ</option><option value=10>RÉS</option><option value=12>VIT combo</option><option value=13>VIT compétence</option><option value=14>RÉCUP compétence</option><option value=15>Gén mana</option></select></div><button id=relicRefresh>Actualiser</button></div><div id=relicTable class=scroll></div></section>
<section id=sim class=hidden><div class=subnav><button class="subtab active" data-sub="combat">Combat</button><button class=subtab data-sub="effects">Analyse effets</button><button class=subtab data-sub="compare">Comparateur</button><button class=subtab data-sub="bestSupport">Meilleur support</button><button class=subtab data-sub="aoeCombat">Combat AoE</button></div>
<div id=combat>
<h3>Stats du boss</h3><div class=controls><div class=control><label>Boss</label><select id=simBoss></select></div><div class=control><label>Élément du boss</label><select id=simElement><option value=Auto>Auto (preset)</option><option value=Neutre>Neutre</option><option value=Fire>Feu</option><option value=Water>Eau</option><option value=Earth>Terre</option><option value=Wind>Vent</option><option value=Light>Lumière</option><option value=Dark>Ténèbres</option><option value=Astral>Astral</option></select></div><div class=control><label>Durée</label><input id=simDur type=number value=120></div></div><div id=simBossCards class=grid></div>
<h3>Build du héros</h3><div class=controls><div class=control><label>Héros principal</label><select id=combatHero></select></div><div class=control><label>Preset</label><select id=combatPreset><option value=box>Ma box</option><option value=early>Early game</option><option value=mid>Mid game</option><option value=late>Late game</option></select></div></div><div class=note id=combatPresetNote>Ma box : stats et niveaux réellement importés.</div><h4>Stats du héros principal</h4><div id=simHeroStats class=grid></div><h4>Niveaux des skills</h4><div id=simHeroLevels class=grid></div>
<h3>Buffers</h3><div class=controls><div class=control><label>Buffer 1</label><select id=support1></select></div><div class=control><label>Buffer 2</label><select id=support2></select></div><div class=control><label>Buffer 3</label><select id=support3></select></div><div class=control><label>Buffer 4</label><select id=support4></select></div><div class=control><label>Adds / minions</label><select id=addsMode><option value=none>Aucun</option><option value=rare>Rares</option><option value=frequent>Fréquents</option></select></div><button id=combatBtn>Lancer la simulation</button></div>
<div class=note>Chaque buffer utilise sa propre fiche enregistrée, sa rotation et ses conditions réelles. Les buffs d'une même famille ne se cumulent pas : le plus fort est actif.</div><div id=supportBuilds class=support-grid></div>
<h3>Résumé combat</h3><div id=combatSummary class=grid></div><h3>Apport des buffers</h3><div id=supportContribution class=scroll></div><h3>Buffs équipe / débuffs boss</h3><div id=teamBuffTable class=scroll></div><div id=combatNote class=note></div><h3>Timeline du combat</h3><div id=combatTable class=scroll></div></div>
<div id=bestSupport class=hidden>
<h3>Meilleur support pour la situation de combat</h3>
<div class=controls><div class=control><label>Preset support</label><select id=bestSupportMode><option value=real>Ma box</option><option value=base>Stats de base</option><option value=max>Max support</option></select></div></div><div class=note id=bestSupportModeNote>Ma box : uniquement les héros que tu possèdes, avec leur vraie fiche importée.</div>
<div class=note>Recherche parmi <b>tous les rôles</b> (Support, Tank, Melee, Range…), mais seuls les héros qui produisent réellement un buff ou un debuff utile sont simulés. Les dégâts personnels du candidat sont toujours ignorés : seul l'impact de ses effets sur le DPS du héros principal est mesuré.</div>
<div class=controls><button id=bestSupportBtn>Analyser les meilleurs supports</button></div>
<div id=bestSupportStatus class=note>Sélectionne ton héros et ton boss dans l'onglet Combat, puis lance l'analyse.</div>
<h3>Top 3 individuels</h3><div id=bestSupportTop class=scroll></div>
<h3>Meilleur trio parmi les meilleurs candidats</h3><div id=bestSupportTrio class=card></div>
</div>
<div id=aoeCombat class=hidden>
<h3>Combat AoE</h3>
<div class=note>Sandbox multi-cibles : ennemis à PV quasi infinis. Le moteur garde la rotation réelle du héros puis multiplie chaque action par son nombre de cibles. Les portées non encore décodées restent à 1 cible et peuvent être corrigées ici.</div>
<div class=controls>
<div class=control><label>Héros</label><select id=aoeHero></select></div>
<div class=control><label>Preset</label><select id=aoePreset><option value=box>Ma box</option><option value=early>Early game</option><option value=mid>Mid game</option><option value=late>Late game</option></select></div>
<div class=control><label>Ennemis</label><input id=aoeEnemies type=number min=1 max=11 value=11></div>
<div class=control><label>Durée</label><input id=aoeDur type=number min=5 value=60></div>
<div class=control><label>Boss (DEF / RÉS / élément)</label><select id=aoeBoss></select></div>
<button id=aoeBtn>Simuler</button></div>
<h4>Cibles touchées par action</h4><div id=aoeTargets class=controls></div><div class=controls><button id=aoeSaveTargets>Enregistrer ces portées</button><button id=aoeProbeStatic>Analyser static.data</button><button id=aoeImportAll>Importer AoE des 222 héros</button></div><div id=aoeTargetStatus class=note></div><div id=aoeProbeStatus class=note></div>
<div id=aoeSummary class=grid></div><div id=aoeStatus class=note></div>
<h4>Détail AoE</h4><div id=aoeTable class=scroll></div>
<h3>Classement AoE</h3>
<div class=note>Classement par DPS AoE décroissant avec le même nombre d'ennemis, la même durée et le même boss preset.</div>
<div class=controls><button id=aoeRankBtn>Calculer le classement AoE</button></div>
<div id=aoeRankStatus class=note></div>
<div id=aoeRankTable class=scroll></div>
</div>
<div id=effects class=hidden><h3>Stats du boss</h3><div id=effectsBoss class=grid></div><h3>Stats du héros</h3><div id=effectsHero class=grid></div><div id=effectsSummary class=grid></div><h3>Répartition des dégâts</h3><div id=damagePie class=card></div><h3>Effets</h3><div id=effectsTable class=scroll></div></div>
<div id=compare class=hidden><div class=controls><div class=control><label>Héros 1</label><select id=aSel></select></div><div class=control><label>Héros 2</label><select id=bSel></select></div><button id=cmpBtn>Comparer</button></div><div class=note id=comparePresetNote>Preset repris de la Simulation de combat.</div><div id=cmpWinner class=good></div><div id=cmpGrid class=grid></div></div></section>
<section id=opt class=hidden><div class=subnav><button class="subtab active" data-opt="crit">ATK vs Crit Rate vs Crit DMG</button><button class=subtab data-opt="recovery">Recovery / Skill Speed / Combo Speed</button><button class=subtab data-opt="relicopt">Optimiseur de reliques DPS</button><button class=subtab data-opt="setopt">Optimiseur de sets</button><button class=subtab data-opt="potential">Potentiel & percentile</button><button class=subtab data-opt="trophyopt">Salle des trophées</button></div><div class=controls><div class=control><label>Héros</label><select id=optHero></select></div><div class=control><label>Boss</label><select id=optBoss></select></div><div class=control><label>Durée</label><input id=optDur type=number value=120></div></div><div id=optBuildWrap><h3>Build de la fiche héros</h3><div id=optBuild class=grid></div></div><div id=optLevels class=levels></div><div id=crit><div class=controls><div class=control><label>Bonus ATK à comparer</label><input id=bonusAtk value=22.5></div><div class=control><label>Bonus Crit Rate</label><input id=bonusCr value=22.5></div><div class=control><label>Bonus Crit DMG</label><input id=bonusCd value=30></div><button id=critBtn>Analyser</button></div><div id=critCards class=grid></div><div id=critOptions class=scroll></div><div id=critThresh class=scroll></div></div><div id=recovery class=hidden>
<div class=note>Entre directement les stats finales de ton héros. Les dégâts autos perdus sont calculés à partir des autos complètes réellement empêchées pendant chaque animation, en respectant la position Auto1→Auto5. Les critiques restent moyennés pour comparer les vitesses sans bruit de RNG.</div>
<h3>Stats actuelles</h3><div id=recCurrentStats class=levels></div>
<h3>Stats testées</h3><div id=recTestStats class=levels></div>
<button id=recBtn>Comparer Actuel vs Testé</button> <button id=recBalanceBtn>Trouver l’équilibre Recovery / Skill Speed</button>
<h3>Équilibre recommandé</h3><div id=recBalanceCards class=grid></div><div id=recBalanceTable class=scroll></div><h3>Bilan</h3><div id=recCards class=grid></div>
<div id=recCompare class=scroll></div>
<h3>Détail par skill : dégâts du skill vs autos réellement perdues</h3><div id=recDetails class=scroll></div>
</div><div id=relicopt class=hidden><div class=note><b>Optimisation réelle par simulation :</b> Smishie’s Lab présélectionne les meilleures reliques par slot, construit les meilleures combinaisons, puis utilise le simulateur de combat pour classer les finalistes. Les 8 slots sont obligatoirement respectés.</div><div class=controls><div class=control><label>Reliques autorisées</label><select id=relicOptMode><option value=all>Toute ma collection — déplacement autorisé</option><option value=free>Disponibles + reliques du héros</option></select></div><div class=control style="min-width:260px"><label>Héros protégés</label><select id=relicProtectedHeroes multiple size=6></select></div><button id=relicOptBtn>Optimiser mes 8 reliques</button></div><div class=note>Les reliques équipées sur les héros protégés ne peuvent pas être prises par l’optimiseur.</div><div id=relicOptStatus class=note></div><h3>Résultat DPS</h3><div id=relicOptSummary class=grid></div><h3>Comparaison des stats</h3><div id=relicOptStats class=scroll></div><h3>Reliques recommandées</h3><div id=relicOptTable class=scroll></div><div id=relicOptLimits class=note></div></div><div id=setopt class=hidden><div class=note><b>Optimiseur de sets :</b> cherche les meilleures combinaisons de sets réellement faisables avec ta collection, puis les classe avec la simulation de combat complète. Un set n’est pas recommandé parce qu’il “semble offensif” : il doit réellement augmenter le DPS du héros contre le boss choisi.</div><div class=controls><div class=control><label>Reliques autorisées</label><select id=setOptMode><option value=all>Toute ma collection — déplacement autorisé</option><option value=free>Disponibles + reliques du héros</option></select></div><button id=setOptBtn>Trouver mes meilleurs sets</button></div><div id=setOptStatus class=note></div><div id=setOptSummary class=grid></div><h3>Classement des compositions</h3><div id=setOptTable class=scroll></div><div id=setOptAdvice class=note></div></div><div id=potential class=hidden><div class=note><b>Potentiel & qualité pour ce héros :</b> le percentile de rolls juge uniquement les jets 70/80/90/100. Le <b>percentile héros</b> répond à une autre question : « parmi les reliques de ma collection pour ce même slot, à quel point cette pièce est-elle adaptée au DPS de ce héros ? » Les 7 autres pièces restent équipées pendant la comparaison, donc les bonus de set 3p/5p sont pris en compte.</div><div class=controls><button id=potentialBtn>Analyser les reliques équipées</button></div><div id=potentialStatus class=note></div><div id=potentialSummary class=grid></div><h3>Détail par relique</h3><div id=potentialTable class=scroll></div><div id=potentialLimits class=note></div></div>
<div id=trophyopt class=hidden>
<div class=note><b>Optimiseur Salle des trophées :</b> teste virtuellement le prochain niveau de chaque stat DPS pour tous les héros sélectionnés d'un même élément. Aucun niveau réel n'est modifié.</div>
<div class=controls>
  <div class=control><label>Élément</label><select id=trophyElement><option>Feu</option><option>Eau</option><option>Vent</option><option>Terre</option><option>Lumière</option><option>Ténèbres</option></select></div>
  <div class=control style="min-width:300px"><label>Héros utilisés</label><select id=trophyHeroes multiple size=8></select></div>
  <button id=trophySelectAll>Tout sélectionner</button>
  <button id=trophyClear>Tout décocher</button>
</div>
<div class=note>Le boss et la durée sont ceux sélectionnés en haut de l'onglet Optimisation. La PRÉ est évaluée via les vrais tests PRÉ/RÉS et l'uptime réel des debuffs.</div>
<h3>Coût des niveaux</h3>
<div class=note>Entre le coût en médailles pour acheter chaque niveau 1→15, séparé par des virgules. Tant que cette table n'est pas renseignée, l'outil classe par gain DPS brut et n'invente aucun coût.</div>
<div class=controls><div class=control style="min-width:650px"><label>Coûts niveaux 1→15</label><input id=trophyCosts placeholder="ex. coût niv1, niv2, ... niv15"></div><button id=trophyBtn>Optimiser la Salle</button></div>
<div id=trophyStatus class=note></div>
<div id=trophySummary class=grid></div>
<h3>Priorité des prochains niveaux</h3><div id=trophyTable class=scroll></div>
<h3>Audit de rotation — détail par héros</h3><div class=note>Clique une amélioration dans le tableau ci-dessus pour voir exactement combien de S1/S2/S3/Ult sont lancés avant et après. Pour Brandis, la colonne Ult ×3 montre combien d'Ultimes bénéficient du self-Burn.</div><div id=trophyHeroDetail class=scroll></div>
</div></section>
<section id=rank class=hidden><div class=controls><div class=control><label>Preset classement</label><select id=rankMode><option value=box>Ma box</option><option value=early>Early game</option><option value=mid>Mid game</option><option value=late>Late game</option></select></div><div class=control><label>Preset supports</label><select id=rankSupportMode><option value=box>Ma box</option><option value=early>Early game</option><option value=mid>Mid game</option><option value=late>Late game</option></select></div><div class=control><label>Boss</label><select id=rankBoss></select></div><div class=control><label>Élément du boss</label><select id=rankElement><option value=Auto selected>Auto (preset)</option><option value=Neutre>Neutre</option><option value=Fire>Feu</option><option value=Water>Eau</option><option value=Earth>Terre</option><option value=Wind>Vent</option><option value=Light>Lumière</option><option value=Dark>Ténèbres</option><option value=Astral>Astral</option></select></div><div class=control><label>Durée</label><input id=rankDur type=number value=120 min=10 step=10></div><div class=control><label>Rareté</label><select id=rarity><option>Toutes</option></select></div><div class=control><label>Rôle</label><select id=role><option>Tous</option></select></div><button id=rankBtn>Calculer</button></div><h3>Buffers / Debuffers du classement</h3><div class=controls><div class=control><label>Slot 1</label><select id=rankSupport1></select></div><div class=control><label>Slot 2</label><select id=rankSupport2></select></div><div class=control><label>Slot 3</label><select id=rankSupport3></select></div><div class=control><label>Slot 4</label><select id=rankSupport4></select></div></div><div class=note>Les 4 slots n'ajoutent aucun dégât personnel au classement : seuls leurs buffs et debuffs modifient le héros testé. Un héros choisi comme support est exclu du classement pour éviter un doublon dans la même équipe.</div><div class=note id=rankModeNote>Ma box : classement avec les builds réellement importés.</div>Ma box : classement avec les builds réellement importés.</div><div id=rankStatus class=note></div><div id=rankTable class=scroll></div></section>
</div><script>
let heroes=[],bosses={},titans={},lastCombat=null; const F=n=>new Intl.NumberFormat('fr-BE',{maximumFractionDigits:0}).format(n||0),F1=n=>new Intl.NumberFormat('fr-BE',{maximumFractionDigits:1}).format(n||0),P=n=>new Intl.NumberFormat('fr-BE',{style:'percent',maximumFractionDigits:1}).format(n||0); async function api(u){let r=await fetch(u);if(!r.ok)throw Error(await r.text());return r.json()} function opts(e,a,d){e.innerHTML=a.map(x=>`<option ${x===d?'selected':''}>${x}</option>`).join('')} const lk={auto:'Auto',s1:'S1',s2:'S2',s3:'S3',ult:'Ult'};
function levels(el,id){el.innerHTML=Object.keys(lk).map(k=>`<div class=control><label>${lk[k]}</label><select id=${id}_${k}>${[1,2,3,4,5,6,7,8,9,10,11].map(x=>`<option value=${x} ${x===7?'selected':''}>${x===11?'♛':x}</option>`).join('')}</select></div>`).join('')} function LV(id,pre=''){return Object.keys(lk).map(k=>`${pre}${k}=${document.getElementById(id+'_'+k).value}`).join('&')}
const buildDefs=[['atk','ATK affichée',2500],['cr','Crit Rate affiché %',70],['cd','Crit DMG affiché %',140],['acc','PRE',340],['res','RES',100],['combo','Combo Speed affichée %',25],['speed','Skill Speed affichée %',20],['rec','Recovery affichée %',20],['mana','Mana Gen affichée %',20]]; function build(el,id){el.innerHTML=buildDefs.map(([k,l,v])=>`<div class=control><label>${l}</label><input id=${id}_${k} type=number step=.1 value=${v}></div>`).join('')+`<div class=control><label>Titan lié</label><select id=${id}_titan>${Object.keys(titans).map(x=>`<option>${x}</option>`).join('')}</select></div><div class=control><label>Empowerment</label><select id=${id}_stars>${[0,1,2,3,4,5,6].map(x=>`<option value=${x}>${x}★</option>`).join('')}</select></div><div class=control><label>Contexte Titan</label><select id=${id}_dungeon><option value=0>Normal</option><option value=1>Donjon</option></select></div>`} function B(id,pre=''){return `${pre}atk_final=${+document.getElementById(id+'_atk').value}&${pre}cr_final=${+document.getElementById(id+'_cr').value/100}&${pre}cd_final=${+document.getElementById(id+'_cd').value/100}&${pre}pre_final=${+document.getElementById(id+'_acc').value}&${pre}res_final=${+document.getElementById(id+'_res').value}&${pre}combo_final=${+document.getElementById(id+'_combo').value/100}&${pre}skill_speed_final=${+document.getElementById(id+'_speed').value/100}&${pre}recovery_final=${+document.getElementById(id+'_rec').value/100}&${pre}mana_final=${+document.getElementById(id+'_mana').value/100}&${pre}titan=${encodeURIComponent(document.getElementById(id+'_titan').value)}&${pre}titan_stars=${document.getElementById(id+'_stars').value}&${pre}titan_dungeon=${document.getElementById(id+'_dungeon').value}`}
const recDefs=[['atk','ATK final',0,1],['cr','Crit Rate %',0,.1],['cd','Crit DMG %',0,.1],['acc','PRE finale',0,1],['res','RES finale',0,1],['combo','Combo Speed %',0,.1],['mana','Mana Gen %',0,.1],['rec','Recovery %',0,.1],['speed','Skill Speed %',0,.1]];
function recFields(el,id){el.innerHTML=recDefs.map(([k,l,v,st])=>`<div class=control><label>${l}</label><input id=${id}_${k} type=number step=${st} value=${v}></div>`).join('')}
function recTestFields(el,id){el.innerHTML=[['combo','Combo Speed testée %'],['rec','Recovery testée %'],['speed','Skill Speed testée %']].map(([k,l])=>`<div class=control><label>${l}</label><input id=${id}_${k} type=number step=.1 value=0></div>`).join('')}
function recStats(id){return {atk:+document.getElementById(id+'_atk').value,crit_rate:+document.getElementById(id+'_cr').value/100,crit_dmg:+document.getElementById(id+'_cd').value/100,accuracy:+document.getElementById(id+'_acc').value,resistance:+document.getElementById(id+'_res').value,combo_speed:+document.getElementById(id+'_combo').value/100,mana_gen:+document.getElementById(id+'_mana').value/100,skill_recovery:+document.getElementById(id+'_rec').value/100,skill_speed:+document.getElementById(id+'_speed').value/100}}
function recQ(prefix,o){return Object.entries(o).map(([k,v])=>`${prefix}_${k}=${encodeURIComponent(v)}`).join('&')}
function setBuildValues(id,p){let m={atk:p.atk,cr:p.crit_rate*100,cd:p.crit_dmg*100,acc:p.accuracy,res:p.resistance,combo:p.combo_speed*100,speed:p.skill_speed*100,rec:p.skill_recovery*100,mana:p.mana_gen*100};for(let k in m){let e=document.getElementById(id+'_'+k);if(e)e.value=Math.round((m[k]||0)*100)/100}let t=document.getElementById(id+'_titan');if(t)t.value=p.titan||'Aucun';let st=document.getElementById(id+'_stars');if(st)st.value=p.titan_stars||0;let dg=document.getElementById(id+'_dungeon');if(dg)dg.value=p.titan_dungeon?1:0}
function profileCards(d){let p=d.profile,st=d.final_stats;return statCards(st)+cards({'Auto':p.auto_level==11?'♛':p.auto_level,'S1':p.s1_level==11?'♛':p.s1_level,'S2':p.s2_level==11?'♛':p.s2_level,'S3':p.s3_level==11?'♛':p.s3_level,'Ult':p.ult_level==11?'♛':p.ult_level,'Titan':p.titan||'Aucun'})}
async function getProfile(name){return api(`/api/profile?name=${encodeURIComponent(name)}`)}

let trophyOwned=[];
async function loadTrophyHeroes(){
  try{trophyOwned=await api('/api/box-hero-names')}catch(e){trophyOwned=[]}
  renderTrophyHeroes();
}
function renderTrophyHeroes(){
  let el=trophyElement.value;
  let hs=heroes.filter(h=>trophyOwned.includes(h.name)&&h.element===el);
  let previous=new Set([...trophyHeroes.selectedOptions].map(o=>o.value));
  trophyHeroes.innerHTML=hs.map(h=>`<option value="${h.name}" ${previous.size?(previous.has(h.name)?'selected':''):'selected'}>${h.name} — ${h.role||''}</option>`).join('');
}
function trophySelected(){return [...trophyHeroes.selectedOptions].map(o=>o.value)}
async function trophyRun(){
  let b=bosses[optBoss.value]; if(!b){trophyStatus.textContent='Boss introuvable.';return}
  let names=trophySelected(); if(!names.length){trophyStatus.textContent='Sélectionne au moins un héros.';return}
  trophyBtn.disabled=true;trophyStatus.textContent='Simulation des prochains niveaux pour '+names.length+' héros…';
  try{
    let u='/api/trophy-opt?element='+encodeURIComponent(trophyElement.value)
      +'&heroes='+encodeURIComponent(names.join('|'))
      +'&duration='+encodeURIComponent(optDur.value||120)
      +'&defense='+encodeURIComponent(b.defense||0)
      +'&resistance='+encodeURIComponent(b.resistance||0)
      +'&hp='+encodeURIComponent(b.hp||0)
      +'&attack='+encodeURIComponent(b.attack||0)
      +'&boss_element='+encodeURIComponent(b.element||'Neutre')
      +'&costs='+encodeURIComponent(trophyCosts.value||'');
    let d=await api(u);
    if(d.error)throw Error(d.error);
    trophySummary.innerHTML=cards({'Élément':d.element,'Héros simulés':d.hero_count,'DPS total actuel':F(d.base_total_dps),'Classement':d.metric==='dps_per_medal'?'DPS / médaille':'Gain DPS brut'});
    trophyTable.innerHTML='<table><tr><th>#</th><th>Stat</th><th>Niveau</th><th>Gain stat</th><th>Coût</th><th>Gain DPS total</th><th>Gain moyen</th><th>DPS / médaille</th><th>Principal bénéficiaire</th><th>Audit rotation</th></tr>'
      +d.rows.map((r,i)=>{let top=(r.heroes||[])[0];let audit='—';if(top){let a=top.before_audit||{},z=top.after_audit||{},ac=a.casts||{},zc=z.casts||{};audit=`S1 ${ac['Skill 1']||0}→${zc['Skill 1']||0} · S2 ${ac['Skill 2']||0}→${zc['Skill 2']||0} · S3 ${ac['Skill 3']||0}→${zc['Skill 3']||0} · Ult ${ac['Ultimate']||0}→${zc['Ultimate']||0}`;if(top.hero==='Brandis')audit+=` · Ult×3 ${a.brandis_ult_x3||0}→${z.brandis_ult_x3||0}`;}return `<tr data-trophy-row="${i}"><td>${i+1}</td><td><b>${r.stat}</b></td><td>${r.current_level}→${r.next_level}</td><td>${r.delta_value==null?'—':F1(r.delta_value)}</td><td>${r.cost>0?F(r.cost):'—'}</td><td class=good>+${F1(r.gain_total_dps)}</td><td>${P(r.gain_avg_pct)}</td><td class=good>${r.dps_per_medal==null?'—':F1(r.dps_per_medal)}</td><td>${top?top.hero+' (+'+F1(top.gain_dps)+')':'—'}</td><td>${audit}</td></tr>`}).join('')+'</table>';
    let renderDetail=(idx)=>{let r=d.rows[idx];if(!r)return;trophyHeroDetail.innerHTML='<h4>'+r.stat+' '+r.current_level+'→'+r.next_level+'</h4><table><tr><th>Héros</th><th>DPS avant</th><th>DPS après</th><th>Gain DPS</th><th>Gain %</th><th>S1</th><th>S2</th><th>S3</th><th>Ult</th><th>Brandis Ult ×3</th></tr>'+(r.heroes||[]).map(x=>{let a=x.before_audit||{},z=x.after_audit||{},ac=a.casts||{},zc=z.casts||{};let tri=(x.hero==='Brandis')?((a.brandis_ult_x3||0)+'→'+(z.brandis_ult_x3||0)):'—';return `<tr><td>${x.hero}</td><td>${F1(x.before_dps)}</td><td>${F1(x.after_dps)}</td><td class=good>+${F1(x.gain_dps)}</td><td>${P(x.gain_pct)}</td><td>${ac['Skill 1']||0}→${zc['Skill 1']||0}</td><td>${ac['Skill 2']||0}→${zc['Skill 2']||0}</td><td>${ac['Skill 3']||0}→${zc['Skill 3']||0}</td><td>${ac['Ultimate']||0}→${zc['Ultimate']||0}</td><td>${tri}</td></tr>`}).join('')+'</table>'};
    renderDetail(0);
    trophyTable.querySelectorAll('[data-trophy-row]').forEach(tr=>tr.onclick=()=>{renderDetail(+tr.dataset.trophyRow);trophyHeroDetail.scrollIntoView({behavior:'smooth',block:'start'})});
    trophyStatus.textContent='Calcul terminé. Clique une ligne pour voir quels héros profitent réellement de l’amélioration.';
  }catch(e){trophyStatus.textContent='Erreur : '+e.message}
  finally{trophyBtn.disabled=false}
}
async function loadRecStats(){let d=await getProfile(optHero.value),x=d.final_stats||{};let vals={atk:+x.atk||0,cr:(+x.crit_rate||0)*100,cd:(+x.crit_dmg||0)*100,acc:+x.accuracy||0,res:+x.resistance||0,combo:(+x.combo_speed||0)*100,mana:(+x.mana_gen||0)*100,rec:(+x.skill_recovery||0)*100,speed:(+x.skill_speed||0)*100};for(let k in vals)document.getElementById('recCur_'+k).value=Math.round(vals[k]*100)/100;document.getElementById('recTest_combo').value=Math.round(vals.combo*100)/100;document.getElementById('recTest_rec').value=Math.round(vals.rec*100)/100;document.getElementById('recTest_speed').value=Math.round(vals.speed*100)/100;let p=d.profile;for(let k of ['auto','s1','s2','s3','ult']){let e=document.getElementById('opt_'+k);if(e)e.value=p[k+'_level']||7}optBuild.innerHTML=profileCards(d)}
function cards(obj){return Object.entries(obj).map(([k,v])=>`<div class=card><div class=muted>${k}</div><div class=big>${v}</div></div>`).join('')} function bossCards(b){return cards({'PV':F(b.hp),'ATK':F(b.attack),'DEF':F(b.defense),'RES':F(b.resistance),'Élément':b.element,'PRE plancher':b.acc_floor??'—','PRE certitude':b.acc_certainty??'—'})} function statCards(s){let x={};if(s.health!=null)x.PV=F(s.health);x['ATK final']=F(s.atk);if(s.defense!=null)x.DEF=F(s.defense);x['Crit Rate']=P(s.crit_rate);x['Crit DMG']=P(s.crit_dmg);x.PRE=F(s.accuracy);x.RES=F(s.resistance);if(s.run_speed!=null)x['VIT déplacement']=F(s.run_speed);x['Combo Speed']=P(s.combo_speed);x['Skill Speed']=P(s.skill_speed);x.Recovery=P(s.skill_recovery);x['Mana Gen']=P(s.mana_gen);return cards(x)}
function showMain(id){document.querySelectorAll('section').forEach(x=>x.classList.add('hidden'));document.getElementById(id).classList.remove('hidden');document.querySelectorAll('[data-main]').forEach(x=>x.classList.toggle('active',x.dataset.main===id))} document.querySelectorAll('[data-main]').forEach(x=>x.onclick=()=>showMain(x.dataset.main)); document.querySelectorAll('[data-sub]').forEach(x=>x.onclick=()=>{['combat','effects','compare','bestSupport','aoeCombat'].forEach(i=>document.getElementById(i).classList.toggle('hidden',i!==x.dataset.sub));document.querySelectorAll('[data-sub]').forEach(y=>y.classList.toggle('active',y===x));if(x.dataset.sub==='effects'&&lastCombat)renderEffects(lastCombat)});document.querySelectorAll('[data-opt]').forEach(x=>x.onclick=()=>{['crit','recovery','relicopt','setopt','potential','trophyopt'].forEach(i=>document.getElementById(i).classList.toggle('hidden',i!==x.dataset.opt));document.querySelectorAll('[data-opt]').forEach(y=>y.classList.toggle('active',y===x));optBuildWrap.classList.toggle('hidden',x.dataset.opt!=='crit')});
async function hero(){let pd=await getProfile(heroSel.value),p=pd.profile;setBuildValues('hero',p);heroElement.value=p.element||'Neutre';if(p._source==='box_exact')heroSaveStatus.textContent='✓ Build automatique : statistiques finales reconstruites depuis ta box (niveau + rang + éveil + reliques).';else if(p._source==='box_unresolved')heroSaveStatus.textContent='⚠ Ce héros est dans ta box, mais sa CharacterConfig manque encore : les champs ci-dessous restent la référence MAX et ne sont PAS ses stats réelles. Renseigne-les manuellement en attendant.';else if(p._source==='reference_max')heroSaveStatus.textContent='Référence MAX par défaut — aucune stat réelle de box calculable pour ce héros.';else heroSaveStatus.textContent='Fiche personnelle enregistrée.';for(let k of ['auto','s1','s2','s3','ult'])document.getElementById('heroLvl_'+k).value=p[k+'_level']||7;let d=await api(`/api/hero?name=${encodeURIComponent(heroSel.value)}&auto=${p.auto_level}&s1=${p.s1_level}&s2=${p.s2_level}&s3=${p.s3_level}&ult=${p.ult_level}`);heroStats.innerHTML=cards({'Élément':p.element||d.hero.element||'Neutre'})+statCards({atk:d.hero.atk,crit_rate:d.hero.crit_rate,crit_dmg:d.hero.crit_dmg,accuracy:d.hero.accuracy,resistance:d.hero.resistance,combo_speed:d.hero.combo_speed,skill_speed:d.hero.skill_speed,skill_recovery:d.hero.skill_recovery,mana_gen:d.hero.mana_gen});heroCoeff.innerHTML='<table><tr><th>Compétence</th><th>Niveau</th><th>Coeff total</th><th>Hits</th><th>Cooldown</th><th>Effet</th><th>Valeur</th></tr>'+[['s1','S1'],['s2','S2'],['s3','S3'],['ult','Ult']].map(([k,l])=>{let r=d.coeffs[k],pp=k==='ult'?'Ult':k.toUpperCase();return `<tr><td>${l}</td><td>${r['Niveau skill']}</td><td>${r[pp+' Coeff total']??'—'}</td><td>${r[pp+' Hits']??'—'}</td><td>${r['Cooldown '+pp]??'—'}</td><td>${r[pp+' Effet 1']??'—'}</td><td>${r[pp+' Valeur 1']??'—'}</td></tr>`}).join('')+'</table>';let at=await api(`/api/auto-timings?name=${encodeURIComponent(heroSel.value)}`);
if(at.timings){
  let z=at.timings;
  let rr=[['Ouverture',z.Opening_chain_s,z.Opening_full_cast_s]];
  for(let i=1;i<=5;i++)rr.push([`Auto ${i}`,z[`Auto${i}_chain_s`],z[`Auto${i}_full_cast_s`]]);
  heroAutoTimings.innerHTML=`<div class=grid>${cards({'Cycle 5 autos (chaînage)':(+z.Combo5_chain_total_s).toFixed(3)+' s','Cycle 5 autos (anim complète)':(+z.Combo5_full_cast_total_s).toFixed(3)+' s','Source':'SkillConfig / static.data'})}</div><table><tr><th>Action</th><th>Temps chaînage base</th><th>Animation complète</th></tr>${rr.map(x=>`<tr><td>${x[0]}</td><td>${(+x[1]).toFixed(3)} s</td><td>${(+x[2]).toFixed(3)} s</td></tr>`).join('')}</table>`;
}else{
  heroAutoTimings.innerHTML='<div class=note>Aucun timing extrait pour ce héros : le simulateur utilise temporairement le fallback historique.</div>';
}
await loadHeroBoxInfo()
}
async function useBoxProfile(){
 heroSaveStatus.textContent='Application des stats exactes de la box…';
 let r=await fetch('/api/profile/use-box',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:heroSel.value})});
 let d=await r.json();
 if(!r.ok||!d.ok)throw Error(d.error||'Stats box indisponibles');
 heroSaveStatus.textContent='✓ Fiche remplacée par les statistiques exactes de ta box.';
 await hero();
 if(combatHero.value===heroSel.value)await combat();
}
async function saveHeroProfile(){let p={name:heroSel.value,atk:+hero_atk.value,crit_rate:+hero_cr.value/100,crit_dmg:+hero_cd.value/100,accuracy:+hero_acc.value,resistance:+hero_res.value,combo_speed:+hero_combo.value/100,skill_speed:+hero_speed.value/100,skill_recovery:+hero_rec.value/100,mana_gen:+hero_mana.value/100,auto_level:+heroLvl_auto.value,s1_level:+heroLvl_s1.value,s2_level:+heroLvl_s2.value,s3_level:+heroLvl_s3.value,ult_level:+heroLvl_ult.value,titan:hero_titan.value,titan_stars:+hero_stars.value,titan_dungeon:hero_dungeon.value==='1',element:heroElement.value};let r=await fetch('/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});if(!r.ok)throw Error(await r.text());heroSaveStatus.textContent='Fiche enregistrée — tous les modes utiliseront ce build.';await hero();if(combatHero.value===heroSel.value)await combat()}
async function saveCompareProfile(prefix,sel,status){let p={name:sel.value,atk:+document.getElementById(prefix+'_atk').value,crit_rate:+document.getElementById(prefix+'_cr').value/100,crit_dmg:+document.getElementById(prefix+'_cd').value/100,accuracy:+document.getElementById(prefix+'_acc').value,resistance:+document.getElementById(prefix+'_res').value,combo_speed:+document.getElementById(prefix+'_combo').value/100,skill_speed:+document.getElementById(prefix+'_speed').value/100,skill_recovery:+document.getElementById(prefix+'_rec').value/100,mana_gen:+document.getElementById(prefix+'_mana').value/100,auto_level:+document.getElementById(prefix+'_auto').value,s1_level:+document.getElementById(prefix+'_s1').value,s2_level:+document.getElementById(prefix+'_s2').value,s3_level:+document.getElementById(prefix+'_s3').value,ult_level:+document.getElementById(prefix+'_ult').value,titan:document.getElementById(prefix+'_titan').value,titan_stars:+document.getElementById(prefix+'_stars').value,titan_dungeon:document.getElementById(prefix+'_dungeon').value==='1'};let r=await fetch('/api/profile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(p)});if(!r.ok)throw Error(await r.text());status.textContent='Fiche enregistrée.';await compare()}
async function loadCompareProfile(prefix,name){let p=await getProfile(name);setBuildValues(prefix,p.profile);for(let k of ['auto','s1','s2','s3','ult'])document.getElementById(prefix+'_'+k).value=p.profile[k+'_level']||7}
let heroSaveTimer=null;function scheduleHeroSave(){clearTimeout(heroSaveTimer);heroSaveStatus.textContent='Sauvegarde…';heroSaveTimer=setTimeout(()=>saveHeroProfile().catch(e=>heroSaveStatus.textContent='Erreur sauvegarde: '+e.message),500)}
function common(id){let b=bosses[document.getElementById(id+'Boss').value];return `duration=${document.getElementById(id+'Dur').value}&boss=${b.defense}&boss_res=${b.resistance}&boss_hp=${b.hp}&boss_atk=${b.attack}&element=${encodeURIComponent(b.element)}`}
async function combat(){let b=bosses[simBoss.value];let elem=(simElement.value==='Auto'?b.element:simElement.value);let sups=[support1.value,support2.value,support3.value,support4.value];let preset=combatPreset.value;let d=await api(`/api/combat?name=${encodeURIComponent(combatHero.value)}&preset=${encodeURIComponent(preset)}&support1=${encodeURIComponent(sups[0])}&support2=${encodeURIComponent(sups[1])}&support3=${encodeURIComponent(sups[2])}&support4=${encodeURIComponent(sups[3])}&adds_mode=${encodeURIComponent(addsMode.value)}&duration=${simDur.value}&boss=${b.defense}&boss_res=${b.resistance}&boss_hp=${b.hp}&boss_atk=${b.attack}&element=${encodeURIComponent(elem)}`);lastCombat=d;simHeroStats.innerHTML=statCards(d.preset_stats||d.final_stats||{});let lv=d.preset_levels||{};simHeroLevels.innerHTML=cards({'Auto':lv.auto==11?'♛':lv.auto,'S1':lv.s1==11?'♛':lv.s1,'S2':lv.s2==11?'♛':lv.s2,'S3':lv.s3==11?'♛':lv.s3,'Ult':lv.ult==11?'♛':lv.ult,'Preset':d.preset_label||preset});supportBuilds.innerHTML=(d.supports||[]).map(x=>`<div class=card><h3>${x.name}</h3><div class=muted>Élément ${x.element||'Neutre'} · ${x.element_matchup?.relation||'Neutre'}</div>${statCards(x.stats||{})}<div class=muted>Auto ${x.levels?.auto||'—'} · S1 ${x.levels?.s1||'—'} · S2 ${x.levels?.s2||'—'} · S3 ${x.levels?.s3||'—'} · Ult ${x.levels?.ult||'—'}<br>Débuffs: ${x.debuff_successes||0}/${x.debuff_attempts||0}</div></div>`).join('')||'<div class=note>Aucun buffer sélectionné.</div>';let sn=(d.supports||[]).map(x=>x.name).join(' + ')||'Aucun';combatSummary.innerHTML=cards({'Élément carry':d.hero_element||'Neutre','Matchup':d.element_matchup?.relation||'Neutre','Mod. dégâts':((d.element_matchup?.damage_mult||1)-1>=0?'+':'')+P((d.element_matchup?.damage_mult||1)-1),'Mod. Crit':(d.element_matchup?.crit_delta>=0?'+':'')+P(d.element_matchup?.crit_delta||0),'Mod. débuff':(d.element_matchup?.debuff_delta>=0?'+':'')+P(d.element_matchup?.debuff_delta||0),'DPS carry':F1(d.dps),'DPS sans buffers':F1(d.dps_without_supports||d.dps),'Gain buffers':(d.support_gain_dps>=0?'+':'')+F1(d.support_gain_dps||0),'Synergie / chevauchement':(d.support_synergy_dps>=0?'+':'')+F1(d.support_synergy_dps||0),'Dégâts':F(d.total_damage),'Actions carry':d.actions,'Buffers':sn});supportContribution.innerHTML='<table><tr><th>Buffer</th><th>DPS avec lui seul</th><th>Gain seul</th><th>Gain %</th><th>Apport marginal équipe</th><th>Buffs principaux</th></tr>'+((d.support_contributions||[]).map(x=>`<tr><td>${x.name}</td><td>${F1(x.dps_with_only)}</td><td>${x.gain_dps>=0?'+':''}${F1(x.gain_dps)}</td><td>${x.gain_pct>=0?'+':''}${P(x.gain_pct)}</td><td>${x.marginal_gain_dps>=0?'+':''}${F1(x.marginal_gain_dps)}</td><td>${(x.buffs||[]).map(b=>`${b.effect} (${P(b.uptime)})`).join(' · ')||'—'}</td></tr>`).join('')||'<tr><td colspan=6>Aucun buffer sélectionné.</td></tr>')+'</table>';teamBuffTable.innerHTML='<table><tr><th>Effet</th><th>Source active</th><th>Applications</th><th>Valeur max</th><th>Uptime</th></tr>'+((d.team_buffs||[]).map(x=>`<tr><td>${x.effect}</td><td>${x.sources||'—'}</td><td>${x.applications}</td><td>${P(x.max_value)}</td><td>${P(x.uptime)}</td></tr>`).join('')||'<tr><td colspan=5>Aucun buff équipe / débuff boss détecté.</td></tr>')+'</table>';combatNote.textContent=d.note;combatTable.innerHTML='<table><tr><th>#</th><th>Temps</th><th>Action</th><th>Durée</th><th>Hits</th><th>Crits</th><th>Dégâts</th><th>Mana</th><th>Effets</th></tr>'+d.log.map(x=>`<tr><td>${x.n}</td><td>${F1(x.time)}</td><td>${x.action}</td><td>${F1(x.duration)}</td><td>${x.hits}</td><td>${x.crits}</td><td>${F(x.damage)}</td><td>${F1(x.mana_after)}</td><td>${x.effects}</td></tr>`).join('')+'</table>';renderEffects(d)}
function renderEffects(d){effectsBoss.innerHTML=bossCards(d.boss||{});effectsHero.innerHTML=statCards(d.final_stats||{});effectsSummary.innerHTML=cards({'PRE utilisée':F1(d.resistance_check?.acc||d.final_stats?.accuracy||0),'RÉS boss':F1(d.resistance_check?.res||0),'RES-PRE':F1(d.resistance_check?.res_minus_acc||0),'IRC':P(d.resistance_check?.irc||0),'Modif élément':P(d.element_matchup?.debuff_delta||0),'FRC':P(d.resistance_check?.frc||0),'Chance debuff':P(d.resistance_check?.land_chance||0),'DPS':F1(d.dps),'Effets détectés':d.effects.length,'Actions':d.actions});effectsTable.innerHTML='<table><tr><th>Type</th><th>Effet</th><th>Casts</th><th>Succès</th><th>Chance théorique</th><th>Uptime</th><th>Condition</th><th>Gain DPS</th><th>Gain dégâts</th><th>Gain %</th></tr>'+d.effects.map(x=>`<tr><td>${x.type}</td><td>${x.effect}</td><td>${x.attempts}</td><td>${x.successes}</td><td>${P(x.expected_rate??1)}</td><td>${P(x.uptime)}</td><td>${x.condition||'Toujours'}</td><td>${x.gain_dps>0?'+':''}${F1(x.gain_dps||0)}</td><td>${x.gain_damage>0?'+':''}${F(x.gain_damage||0)}</td><td>${x.gain_pct>0?'+':''}${P(x.gain_pct||0)}</td></tr>`).join('')+'</table>';let dm=d.damage_by||{},parts=[['Autos',dm.Auto||0],['S1',dm['Skill 1']||0],['S2',dm['Skill 2']||0],['S3',dm['Skill 3']||0],['Ult',dm.Ultimate||0],['DoT',dm.DoT||0]],tot=parts.reduce((a,x)=>a+x[1],0)||1,acc=0,cols=['#7c9cff','#43d39e','#ffd166','#e07aef','#ff7b72','#6ed0e0'],stops=parts.map((x,i)=>{let a=acc/tot*360;acc+=x[1];let b=acc/tot*360;return `${cols[i]} ${a}deg ${b}deg`});damagePie.innerHTML=`<div class=donut-wrap><div class=donut style="background:conic-gradient(${stops.join(',')})"></div><div class=legend>${parts.map((x,i)=>`<div class=legend-row><span class=sw style="background:${cols[i]}"></span><b>${x[0]}</b> ${P(x[1]/tot)} · ${F(x[1])}</div>`).join('')}</div></div>`}
async function compare(){let b=bosses[simBoss.value],preset=combatPreset.value,elem=(simElement.value==='Auto'?b.element:simElement.value);let d=await api(`/api/compare?a=${encodeURIComponent(aSel.value)}&b=${encodeURIComponent(bSel.value)}&preset=${encodeURIComponent(preset)}&duration=${simDur.value}&boss=${b.defense}&boss_res=${b.resistance}&boss_hp=${b.hp}&boss_atk=${b.attack}&element=${encodeURIComponent(elem)}`);let labels={box:'Ma box',early:'Early game',mid:'Mid game',late:'Late game'};comparePresetNote.textContent=`Preset : ${labels[preset]||preset} — même boss et même durée que la Simulation de combat.`;cmpWinner.textContent=d.winner?`${d.winner} devant de ${F1(d.diff_dps)} DPS (${P(d.pct)})`:'Égalité';cmpGrid.innerHTML=[d.a,d.b].map(x=>`<div class=card><h3>${x.hero}</h3><div class=big>${F1(x.dps)} DPS</div>${statCards(x.final_stats)}<div class=muted>Auto/S1/S2/S3/Ult : ${['auto','s1','s2','s3','ult'].map(k=>x.preset_levels?.[k]===11?'♛':(x.preset_levels?.[k]??'—')).join(' / ')}</div><hr>Autos ${F(x.damage_by.Auto)} · S1 ${F(x.damage_by['Skill 1'])} · S2 ${F(x.damage_by['Skill 2'])} · S3 ${F(x.damage_by['Skill 3'])} · Ult ${F(x.damage_by.Ultimate)}</div>`).join('')}
async function critAnalysis(){let d=await api(`/api/crit-analysis?name=${encodeURIComponent(optHero.value)}&bonus_atk=${+bonusAtk.value/100}&bonus_cr=${+bonusCr.value/100}&bonus_cd=${+bonusCd.value/100}`);critCards.innerHTML=cards({'ATK actuel':F(d.current.atk),'Crit Rate':P(d.current.crit_rate),'Crit DMG':P(d.current.crit_dmg),'Meilleur choix':d.recommendation});critOptions.innerHTML='<table><tr><th>Option</th><th>ATK</th><th>Crit Rate</th><th>Crit DMG</th><th>Score relatif</th><th>Gain</th></tr>'+d.options.map(x=>`<tr><td>${x.option}</td><td>${F(x.atk)}</td><td>${P(x.crit_rate)}</td><td>${P(x.crit_dmg)}</td><td>${F1(x.score)}</td><td>${P(x.gain)}</td></tr>`).join('')+'</table>';let t=d.thresholds;critThresh.innerHTML='<table><tr><th>Point de bascule</th><th>Seuil</th></tr>'+[['ATK % ↔ Crit Rate',t.atk_vs_cr],['ATK % ↔ Crit DMG',t.atk_vs_cd],['Crit Rate ↔ Crit DMG',t.cr_vs_cd],['Crit DMG : ATK % ↔ Crit Rate',t.cd_atk_vs_cr],['Crit DMG : Crit Rate ↔ Crit DMG',t.cd_cr_vs_cd]].map(x=>`<tr><td>${x[0]}</td><td>${P(x[1])}</td></tr>`).join('')+'</table>'}
async function recAnalysis(){let b=bosses[optBoss.value];let cur=recStats('recCur'),test={...cur,combo_speed:+recTest_combo.value/100,skill_recovery:+recTest_rec.value/100,skill_speed:+recTest_speed.value/100};let d=await api(`/api/recovery-analysis?name=${encodeURIComponent(optHero.value)}&duration=${optDur.value}&boss=${b.defense}&boss_res=${b.resistance}&boss_hp=${b.hp}&boss_atk=${b.attack}&element=${encodeURIComponent(b.element)}&${LV('opt')}&${recQ('cur',cur)}&${recQ('test',test)}`);
let q=d.delta;recCards.innerHTML=cards({'Temps combo base':d.current.combo_base_time.toFixed(3)+' s','Temps combo réel actuel':d.current.combo_real_time.toFixed(3)+' s','Temps combo réel testé':d.tested.combo_real_time.toFixed(3)+' s','Fréquence combo actuelle':d.current.combo_per_second.toFixed(3)+' combo/s','Fréquence combo testée':d.tested.combo_per_second.toFixed(3)+' combo/s','Autos théoriques actuelles':d.current.autos_per_second_theoretical.toFixed(2)+' auto/s','Autos théoriques testées':d.tested.autos_per_second_theoretical.toFixed(2)+' auto/s','DPS actuel':F1(d.current.dps),'DPS testé':F1(d.tested.dps),'Δ DPS':(q.dps>=0?'+':'')+F1(q.dps),'Δ dégâts total':(q.total_damage>=0?'+':'')+F(q.total_damage),'Δ dégâts skills':(q.skill_damage>=0?'+':'')+F(q.skill_damage),'Δ dégâts autos':(q.auto_damage>=0?'+':'')+F(q.auto_damage),'Δ autos effectuées':(q.auto_count>=0?'+':'')+F1(q.auto_count),'Δ temps immobilisé':(q.blocked_time>=0?'+':'')+F1(q.blocked_time)+' s'});
recCompare.innerHTML='<table><tr><th>Mesure</th><th>Actuel</th><th>Testé</th><th>Écart</th></tr>'+[
['Combo Speed',P(d.current.final_stats.combo_speed),P(d.tested.final_stats.combo_speed),P(d.tested.final_stats.combo_speed-d.current.final_stats.combo_speed)],
['Temps combo réel',d.current.combo_real_time.toFixed(3)+' s',d.tested.combo_real_time.toFixed(3)+' s',(d.tested.combo_real_time-d.current.combo_real_time>=0?'+':'')+(d.tested.combo_real_time-d.current.combo_real_time).toFixed(3)+' s'],
['Fréquence combo',d.current.combo_per_second.toFixed(3)+' combo/s',d.tested.combo_per_second.toFixed(3)+' combo/s',(d.tested.combo_per_second-d.current.combo_per_second>=0?'+':'')+(d.tested.combo_per_second-d.current.combo_per_second).toFixed(3)+' combo/s'],
['Autos théoriques / s',d.current.autos_per_second_theoretical.toFixed(2),d.tested.autos_per_second_theoretical.toFixed(2),(d.tested.autos_per_second_theoretical-d.current.autos_per_second_theoretical>=0?'+':'')+(d.tested.autos_per_second_theoretical-d.current.autos_per_second_theoretical).toFixed(2)],
['Skill Speed',P(d.current.final_stats.skill_speed),P(d.tested.final_stats.skill_speed),P(d.tested.final_stats.skill_speed-d.current.final_stats.skill_speed)],
['Recovery',P(d.current.final_stats.skill_recovery),P(d.tested.final_stats.skill_recovery),P(d.tested.final_stats.skill_recovery-d.current.final_stats.skill_recovery)],
['DPS',F1(d.current.dps),F1(d.tested.dps),(q.dps>=0?'+':'')+F1(q.dps)],
['Dégâts totaux',F(d.current.total_damage),F(d.tested.total_damage),(q.total_damage>=0?'+':'')+F(q.total_damage)],
['Dégâts skills',F(d.current.skill_damage),F(d.tested.skill_damage),(q.skill_damage>=0?'+':'')+F(q.skill_damage)],
['Dégâts autos',F(d.current.auto_damage),F(d.tested.auto_damage),(q.auto_damage>=0?'+':'')+F(q.auto_damage)],
['Autos réellement effectuées',F1(d.current.auto_count),F1(d.tested.auto_count),(q.auto_count>=0?'+':'')+F1(q.auto_count)],
['Temps immobilisé',F1(d.current.blocked_time)+' s',F1(d.tested.blocked_time)+' s',(q.blocked_time>=0?'+':'')+F1(q.blocked_time)+' s'],
['Occupation skills',P(d.current.occupation),P(d.tested.occupation),(q.occupation>=0?'+':'')+P(q.occupation)],
['Temps disponible autos',F1(d.current.time_for_autos)+' s',F1(d.tested.time_for_autos)+' s',(d.tested.time_for_autos-d.current.time_for_autos>=0?'+':'')+F1(d.tested.time_for_autos-d.current.time_for_autos)+' s'],
['Dégâts autres effets','—','—',(q.other_damage>=0?'+':'')+F(q.other_damage)]].map(x=>`<tr>${x.map(y=>`<td>${y}</td>`).join('')}</tr>`).join('')+'</table>';
recDetails.innerHTML='<table><tr><th>Skill</th><th>Build</th><th>Casts</th><th>Dégâts skill</th><th>Dégâts/cast</th><th>Animation/cast</th><th>Temps bloqué</th><th>Autos réellement perdues</th><th>Dégâts autos perdus</th><th>Bilan net</th><th>Verdict</th></tr>'+d.details.flatMap(x=>[['Actuel',x.current],['Testé',x.tested]].map(([lab,z])=>`<tr><td>${x.skill}</td><td>${lab}</td><td>${z.casts}</td><td>${F(z.skill_damage)}</td><td>${F(z.damage_per_cast)}</td><td>${F1(z.cast_time)} s</td><td>${F1(z.blocked_time)} s</td><td>${F(z.autos_missed)}</td><td>${F(z.auto_damage_lost)}</td><td>${F(z.net_total)}</td><td>${z.verdict}</td></tr>`)).join('')+'</table>'}
async function recBalance(){let b=bosses[optBoss.value];let cur=recStats('recCur');recBalanceBtn.disabled=true;recBalanceBtn.textContent='Recherche…';try{let d=await api(`/api/recovery-balance?name=${encodeURIComponent(optHero.value)}&duration=${optDur.value}&boss=${b.defense}&boss_res=${b.resistance}&boss_hp=${b.hp}&boss_atk=${b.attack}&element=${encodeURIComponent(b.element)}&${LV('opt')}&${recQ('cur',cur)}`);let z=d.zone,m=d.marginal_dps_per_1pct;recBalanceCards.innerHTML=cards({'Budget Rec + Skill Speed':P(d.budget),'Recovery conseillé':P(d.best.recovery),'Skill Speed conseillé':P(d.best.skill_speed),'Combo Speed conservée':P(d.current.combo_speed),'DPS actuel':F1(d.current.dps),'DPS équilibré':F1(d.best.dps),'Gain estimé':(d.gain_vs_current>=0?'+':'')+F1(d.gain_vs_current)+' DPS','Zone Recovery':P(z.recovery_min)+' → '+P(z.recovery_max),'Zone Skill Speed':P(z.skill_speed_min)+' → '+P(z.skill_speed_max),'+1% Recovery':(m.skill_recovery>=0?'+':'')+F1(m.skill_recovery)+' DPS','+1% Skill Speed':(m.skill_speed>=0?'+':'')+F1(m.skill_speed)+' DPS','+1% Combo Speed':(m.combo_speed>=0?'+':'')+F1(m.combo_speed)+' DPS'});recBalanceTable.innerHTML='<table><tr><th>Recovery</th><th>Skill Speed</th><th>DPS</th><th>Écart vs meilleur</th></tr>'+d.near_best.map(x=>`<tr><td>${P(x.recovery)}</td><td>${P(x.skill_speed)}</td><td>${F1(x.dps)}</td><td>${F1(x.dps-d.best.dps)}</td></tr>`).join('')+'</table>'}finally{recBalanceBtn.disabled=false;recBalanceBtn.textContent='Trouver l’équilibre Recovery / Skill Speed'}}
async function scanGame(){scanGameBtn.disabled=true;scanGameBtn.textContent='Scan…';gameImportStatus.textContent='Recherche des données locales Invokers…';try{let d=await api('/api/game-import/scan');window.lastGameScan=d;gameImportStatus.textContent=d.roots.length?`🔒 Lecture seule active · ${d.count} fiche(s) directement importable(s). ${d.diagnostic_hits||0} fichier(s) contiennent des noms de héros.`:'🔒 Lecture seule active · Aucun dossier Invokers trouvé automatiquement.';applyGameBtn.disabled=!d.count;gameImportReport.innerHTML='<table><tr><th>Dossier</th><th>Fichier</th><th>Type</th><th>Taille</th><th>Héros cités</th><th>Structure</th><th>Fiches stats</th></tr>'+((d.files||[]).map(x=>`<tr><td>${x.root}</td><td>${x.file}</td><td>${x.type||''}</td><td>${Math.round(x.size/1024)} Ko</td><td>${x.hero_mention_count||0}${(x.hero_mentions||[]).length?' : '+x.hero_mentions.join(', '):''}</td><td>${(x.top_keys||[]).join(', ')}</td><td>${x.hero_stat_hits}</td></tr>`).join('')||'<tr><td colspan=7>Aucun fichier de données pertinent détecté.</td></tr>')+'</table>'}catch(e){gameImportStatus.textContent='Erreur scan : '+e.message}finally{scanGameBtn.disabled=false;scanGameBtn.textContent='Scanner le jeu'}}
async function snapshotGame(){snapshotGameBtn.disabled=true;gameImportStatus.textContent='Création de l\'instantané…';try{let d=await fetch('/api/game-import/snapshot',{method:'POST'}).then(r=>r.json());gameImportStatus.textContent=`Instantané AVANT enregistré : ${d.count} fichiers surveillés. Ouvre maintenant ta box dans Invokers, puis clique « Comparer APRÈS ».`;gameImportReport.innerHTML=''}catch(e){gameImportStatus.textContent='Erreur instantané : '+e.message}finally{snapshotGameBtn.disabled=false}}
async function diffGame(){diffGameBtn.disabled=true;gameImportStatus.textContent='Comparaison des fichiers…';try{let d=await api('/api/game-import/diff');gameImportStatus.textContent=`${d.changed_count} fichier(s) créé(s) ou modifié(s) depuis l\'instantané.`;gameImportReport.innerHTML='<table><tr><th>État</th><th>Dossier</th><th>Fichier</th><th>Type</th><th>Avant</th><th>Après</th><th>Δ</th><th>Héros cités</th><th>Structure</th></tr>'+((d.changed||[]).map(x=>`<tr><td>${x.status}</td><td>${x.root}</td><td>${x.file}</td><td>${x.type||''}</td><td>${x.size_before==null?'—':Math.round(x.size_before/1024)+' Ko'}</td><td>${Math.round((x.size_after||0)/1024)} Ko</td><td>${Math.round((x.delta_size||0)/1024)} Ko</td><td>${x.hero_mention_count||0}${(x.hero_mentions||[]).length?' : '+x.hero_mentions.join(', '):''}</td><td>${(x.top_keys||[]).join(', ')}</td></tr>`).join('')||'<tr><td colspan=9>Aucun fichier modifié détecté.</td></tr>')+'</table>'}catch(e){gameImportStatus.textContent='Erreur comparaison : '+e.message}finally{diffGameBtn.disabled=false}}
async function analyzeDiff(){analyzeDiffBtn.disabled=true;gameImportStatus.textContent='Analyse en lecture seule des fichiers modifiés…';try{let d=await api('/api/game-import/analyze-diff');gameImportStatus.textContent=`🔒 ${d.files_analyzed} fichier(s) avec contenu potentiellement utile. Les tokens éventuels sont masqués.`;let html='';for(let r of (d.reports||[])){html+=`<div class=card><h4>${r.file}</h4><div><b>Héros :</b> ${(r.hero_hits||[]).join(', ')||'aucun'}</div>`;if((r.urls||[]).length)html+=`<div><b>Endpoints/URLs :</b><pre>${(r.urls||[]).join('\n')}</pre></div>`;if((r.excerpts||[]).length)html+=`<div><b>Chaînes pertinentes :</b><pre>${(r.excerpts||[]).join('\n---\n')}</pre></div>`;html+='</div>'}gameImportReport.innerHTML=html||'<div class=note>Aucune chaîne exploitable trouvée dans les fichiers modifiés.</div>'}catch(e){gameImportStatus.textContent='Erreur analyse : '+e.message}finally{analyzeDiffBtn.disabled=false}}
async function scanStaticCache(){staticCacheBtn.disabled=true;gameImportStatus.textContent='Recherche du cache StaticData téléchargé par le jeu…';try{let d=await api('/api/game-import/static-cache');gameImportStatus.textContent=d.count?`🔒 ${d.count} fichier(s) StaticData local(aux) détecté(s). Le plus récent est affiché en premier.`:'🔒 Aucun fichier trouvé dans persistentDataPath/static_data.';gameImportReport.innerHTML='<table><tr><th>Fichier</th><th>Taille</th><th>Version détectée</th><th>Chemin</th></tr>'+((d.files||[]).map(x=>`<tr><td><b>${x.file}</b></td><td>${Math.round(x.size/1024)} Ko</td><td>${(x.version_hints||[]).join(', ')||'—'}</td><td><code>${x.path}</code></td></tr>`).join('')||'<tr><td colspan=4>Aucun cache StaticData trouvé.</td></tr>')+'</table>'}catch(e){gameImportStatus.textContent='Erreur scan StaticData : '+e.message}finally{staticCacheBtn.disabled=false}}
async function scanAggregate(){aggregateScanBtn.disabled=true;gameImportStatus.textContent='Recherche ciblée PlayerAggregate en lecture seule…';try{let d=await api('/api/game-import/player-aggregate');gameImportStatus.textContent=`🔒 ${d.count} artefact(s) lié(s) au PlayerAggregate détecté(s).`;let html='<table><tr><th>Score</th><th>Fichier</th><th>Taille</th><th>IDs héros</th><th>Sets équipement</th><th>Marqueurs</th></tr>';html+=((d.artifacts||[]).map(x=>`<tr><td>${x.score}</td><td>${x.file}${x.is_trace?' <b>(trace)</b>':''}</td><td>${Math.round(x.size/1024)} Ko</td><td>${(x.character_ids||[]).join(', ')||'—'}</td><td>${(x.equipment_sets||[]).join(', ')||'—'}</td><td><pre>${(x.markers||[]).slice(0,10).join('\n---\n')}</pre></td></tr>`).join('')||'<tr><td colspan=6>Aucun artefact PlayerAggregate détecté.</td></tr>');html+='</table>';gameImportReport.innerHTML=html}catch(e){gameImportStatus.textContent='Erreur scan PlayerAggregate : '+e.message}finally{aggregateScanBtn.disabled=false}}

const RELIC_SLOT_NAMES={1:'Arme',2:'Bouclier',3:'Casque',4:'Épaulières',5:'Gantelets',6:'Plastron',7:'Ceinture',8:'Bottes'};
function relicSlotName(x){return RELIC_SLOT_NAMES[Number(x)]||('Slot '+x)}

async function loadHeroBoxInfo(){try{let d=await api('/api/box-hero?name='+encodeURIComponent(heroSel.value));let x=d.box;if(!x){heroBoxInfo.innerHTML='<span class=muted>Ce héros n\'est pas encore identifié dans la box importée.</span>';return}let bb=x.box_build||{},f=bb.final_stats||null,ref=bb.reference_stats_max||null,b=bb.relic_bonus||{},rs=bb.relics||[],sb=bb.stat_breakdown||{},base=sb.base||{},awn=sb.awake_nodes||{},hall=sb.hall||{},relb=sb.relics||{};let rel=Object.entries(x.relics_by_slot||{}).map(([k,v])=>relicSlotName(k)+': '+v).join(' · ')||'—';let rtable=rs.length?'<div class=scroll><table><tr><th>Pièce</th><th>ID</th><th>Niv.</th><th>Stats</th></tr>'+rs.map(r=>`<tr><td>${relicSlotName(r.slot)}</td><td>${r.inventory_id??'—'}</td><td>${r.level??'—'}</td><td>${(r.stats||[]).map(st=>`${st.stat} ${st.kind==='%'?F1(st.value)+'%':F(st.value)}`).join(' · ')||'—'}</td></tr>`).join('')+'</table></div>':'';let sourceTable=sb.final?`<h4>Détail PRE / RÉS par source</h4><table><tr><th>Source</th><th>PRÉ</th><th>RÉS</th></tr><tr><td>Base + éveil de base</td><td>${F((base.accuracy||0)+((bb.pre_relic_stats||{}).accuracy||0)-(awn.accuracy||0)-((base.accuracy||0)))}</td><td>${F((base.resistance||0)+((bb.pre_relic_stats||{}).resistance||0)-(awn.resistance||0)-((base.resistance||0)))}</td></tr><tr><td>Nœuds d'éveil</td><td>${F(awn.accuracy||0)}</td><td>${F(awn.resistance||0)}</td></tr><tr><td>Reliques</td><td>${F(relb.accuracy||0)}</td><td>${F(relb.resistance||0)}</td></tr><tr><td>Salle des trophées</td><td>${F(hall.accuracy||0)}</td><td>${F(hall.resistance||0)}</td></tr><tr><td><b>Total</b></td><td><b>${F((sb.final||{}).accuracy||0)}</b></td><td><b>${F((sb.final||{}).resistance||0)}</b></td></tr></table>`:'';heroBoxInfo.innerHTML=`<div class=grid><div><b>Niveau</b><div class=big>${x.level??'—'}</div></div><div><b>Rang</b><div class=big>${x.rank??'—'}</div></div><div><b>Éveil</b><div class=big>${x.awake_level??0}</div></div><div><b>Nœuds</b><div class=big>${x.awake_node_count??0}</div></div><div><b>Copies</b><div class=big>${x.copies??1}</div></div><div><b>Reliques décodées</b><div class=big>${bb.relic_count??0}</div></div></div>`+(f?'<h4>Stats finales exactes</h4>'+statCards(f):'')+sourceTable+(ref?'<div class=note><b>⚠ Référence max uniquement :</b> les valeurs de la base correspondent au héros niveau 60 / progression maximale. Elles ne sont pas utilisées comme stats de cet exemplaire.</div>':'')+`<div class=note><b>Bonus reliques :</b> ATQ plat ${F(b.atk_flat||0)} · ATQ ${P(b.atk_pct||0)} · Crit ${P(b.crit_rate||0)} · Dég crit ${P(b.crit_dmg||0)} · PRÉ ${F(b.accuracy||0)} · RÉS ${F(b.resistance||0)} · Combo ${F(b.combo_points||0)} pts · Skill Speed ${F(b.skill_speed_points||0)} pts · Recovery ${F(b.skill_recovery_points||0)} pts<br><b>Skills bruts :</b> ${Object.entries(x.skill_levels_raw||{}).map(([k,v])=>k+':'+v).join(', ')||'—'}<br><b>IDs reliques :</b> ${rel}<br><span class=muted>Mana et stat ID 11 sont conservés mais pas injectés tant que leur échelle n'est pas validée.</span></div>`+rtable}catch(e){heroBoxInfo.textContent='Box : '+e.message}}
async function loadRelics(){try{let q=`slot=${encodeURIComponent(relicSlot.value)}&set=${encodeURIComponent(relicSet.value)}&equipped=${encodeURIComponent(relicEquipped.value)}&stat=${encodeURIComponent(relicStat.value)}&limit=1500`;let d=await api('/api/box-relics?'+q),c=d.counts||{};relicCounts.innerHTML=cards({'Total':c.total||0,'Équipées':c.equipped||0,'Non équipées':c.unequipped||0,'Affichées':d.shown||0});let cur=relicSet.value;if(relicSet.options.length<=1){(d.sets||[]).forEach(x=>relicSet.add(new Option('Set '+x,x)));relicSet.value=cur}let rows=d.rows||[];relicTable.innerHTML=rows.length?'<table><tr><th>ID</th><th>Pièce</th><th>★</th><th>Niv.</th><th>Set</th><th>Rareté</th><th>Équipée sur</th><th>Stats</th></tr>'+rows.map(r=>`<tr><td>${r.inventory_id}</td><td>${relicSlotName(r.slot)}</td><td>${r.stars??r.rank??'—'}</td><td>${r.level??'—'}</td><td>${r.set_name?`${r.set_name} (#${r.set_id})`:(r.set_id??'—')}</td><td>${r.rarity??r.quality_code??'—'}</td><td>${r.equipped_hero_name||'<span class=muted>Non équipée</span>'}</td><td>${(r.stats||[]).map(st=>`${st.stat} ${st.kind==='%'?F1(st.value)+'%':F(st.value)}`).join(' · ')||'—'}</td></tr>`).join('')+'</table>':'<div class=note>Aucune relique importée. Clique sur « Importer ma box ».</div>'}catch(e){relicTable.textContent='Reliques : '+e.message}}
async function importHallOnly(){
 importHallBtn.disabled=true;importHallBtn.textContent='Import en cours…';gameImportStatus.textContent='Lecture de PlayerArenaModel.dat…';
 try{
  let r=await fetch('/api/game-import/import-hall',{method:'POST'});
  let d=await r.json();
  if(!r.ok||!d.ok)throw Error(d.error||'Import Salle impossible');
  let detail=Object.entries(d.by_element||{}).map(([k,v])=>k+' : '+v).join(' · ');
  gameImportStatus.textContent='✅ Salle des trophées importée : '+(d.imported||0)+' bonus'+(detail?' · '+detail:'');
  await hero();
 }catch(e){
  gameImportStatus.textContent='Erreur import Salle : '+e.message;
 }finally{
  importHallBtn.disabled=false;importHallBtn.textContent='Importer la Salle des trophées';
 }
}

async function importBoxOneClick(){
 importBoxBtn.disabled=true;importBoxBtn.textContent='Import en cours…';gameImportReport.innerHTML='';gameImportStatus.textContent='Recherche et décodage de ta box…';
 try{
  let d=await api('/api/game-import/decode-box');
  window.lastDecodedBox=d;
  if(!d.ok)throw Error(d.error||'Décodage impossible');
  gameImportStatus.textContent=`Box trouvée : ${d.hero_entries||0} héros · ${d.relic_entries||0} reliques. Import des données…`;
  let r=await fetch('/api/game-import/import-box',{method:'POST'});
  let x=await r.json();
  if(!r.ok)throw Error(x.error||'Import box impossible');
  gameImportStatus.textContent=`✅ Box importée : ${x.imported||0} exemplaires · ${x.mapped||0} héros identifiés · ${x.relics_imported||0} reliques · Salle des trophées importée · stats et niveaux de skills mis à jour pour ${x.profiles_updated||0} profils.`;
  gameImportReport.innerHTML='';
  await loadRelics();await hero();
 }catch(e){
  gameImportStatus.textContent='Erreur import de la box : '+e.message;
 }finally{
  importBoxBtn.disabled=false;importBoxBtn.textContent='Importer ma box';
 }
}

async function decodeBox(){decodeBoxBtn.disabled=true;gameImportStatus.textContent='Décodage hors ligne de PlayerHeroesModel / PlayerRelicsModel…';try{let d=await api('/api/game-import/decode-box');window.lastDecodedBox=d;if(!d.ok)throw Error(d.error||'Décodage impossible');gameImportStatus.textContent=`🔒 ${d.hero_entries} entrées héros · ${d.unique_config_ids} ConfigId uniques · ${d.relic_entries} reliques (${d.relics_with_stats||0} avec stats décodées) · ${d.mapped_names} héros identifiés automatiquement.`;let names=heroes.map(h=>h.name);let html='<div class=controls><button id=saveBoxMappingsBtn>Enregistrer les correspondances</button><button id=importDecodedBoxBtn>Importer cette box</button></div><table><tr><th>Héros</th><th>ConfigId exact</th><th>Source</th><th>Copies</th><th>Inv. ID</th><th>Rang</th><th>Niveau</th><th>Éveil</th><th>Nœuds</th><th>Skills bruts</th><th>Reliques équipées</th></tr>';html+=(d.rows||[]).map(x=>{let o='<option value="">— non mappé —</option>'+names.map(n=>`<option ${n===x.name_candidate?'selected':''}>${n}</option>`).join('');return `<tr><td><select class=cfgMap data-cfg="${x.config_id}">${o}</select></td><td><code>${x.config_id}</code></td><td>${x.name_source||'—'}</td><td>${x.copies}</td><td>${x.inventory_id}</td><td>${x.rank}</td><td>${x.level}</td><td>${x.awake_level??0}</td><td>${x.awake_node_count??0}</td><td>${Object.entries(x.skill_levels_raw||{}).map(([k,v])=>k+':'+v).join(', ')||'—'}</td><td>${x.equipped_relic_count}</td></tr>`}).join('');html+='</table>';gameImportReport.innerHTML=html;saveBoxMappingsBtn.onclick=saveBoxMappings;importDecodedBoxBtn.onclick=importDecodedBox}catch(e){gameImportStatus.textContent='Erreur décodage box : '+e.message}finally{decodeBoxBtn.disabled=false}}
async function saveBoxMappings(){let mappings=[...document.querySelectorAll('.cfgMap')].filter(x=>x.value).map(x=>({config_id:x.dataset.cfg,hero_name:x.value,source:'manual',confidence:1}));let r=await fetch('/api/game-import/save-mappings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mappings})});let d=await r.json();if(!r.ok)throw Error(d.error||'Sauvegarde impossible');gameImportStatus.textContent=`${d.saved} correspondance(s) ConfigId → héros enregistrée(s).`;await decodeBox()}
async function importDecodedBox(){let r=await fetch('/api/game-import/import-box',{method:'POST'});let d=await r.json();if(!r.ok)throw Error(d.error||'Import box impossible');gameImportStatus.textContent=`Ma box importée : ${d.imported} exemplaires, ${d.mapped} identifiés, ${d.relics_imported||0} reliques possédées importées, progression réelle conservée · fiches de simulation non écrasées.`;await hero()}

async function applyGame(){applyGameBtn.disabled=true;applyGameBtn.textContent='Import…';try{let r=await fetch('/api/game-import/apply',{method:'POST'});let d=await r.json();if(!r.ok)throw Error(d.error||'Import impossible');gameImportStatus.textContent=`${d.count} fiches héros importées.`;await hero();await loadCompareProfile('a',aSel.value);await loadCompareProfile('b',bSel.value)}catch(e){gameImportStatus.textContent='Erreur import : '+e.message}finally{applyGameBtn.textContent='Importer les stats détectées';applyGameBtn.disabled=!(window.lastGameScan&&window.lastGameScan.count)}}
async function bestSupports(){
 let b=bosses[simBoss.value],elem=(simElement.value==='Auto'?b.element:simElement.value); bestSupportBtn.disabled=true; bestSupportBtn.textContent='Analyse en cours…'; bestSupportStatus.textContent='Recherche des buffers/debuffers utiles dans tous les rôles…'; bestSupportTop.innerHTML=''; bestSupportTrio.innerHTML='';
 try{
  let d=await api(`/api/best-supports?name=${encodeURIComponent(combatHero.value)}&duration=${simDur.value}&boss=${b.defense}&boss_res=${b.resistance}&boss_hp=${b.hp}&boss_atk=${b.attack}&element=${encodeURIComponent(elem)}&support_mode=${encodeURIComponent(bestSupportMode.value)}`);
  bestSupportStatus.textContent=`${d.tested||0} buffers/debuffers utiles testés pour ${d.hero} contre ${simBoss.value}. Profil : ${d.support_mode==='max'?'Max support':d.support_mode==='base'?'Stats de base':'Ma box'}. DPS seul : ${F1(d.base_dps)}.`;
  let rows=(d.top3||[]).map((x,i)=>`<tr><td>${i+1}</td><td><b>${x.name}</b></td><td>${x.role||''}</td><td>${F1(x.dps)}</td><td class=good>+${F1(x.gain_dps)} (${P(x.gain_pct)})</td><td>${x.buff_gain_dps>=0?'+':''}${F1(x.buff_gain_dps)}</td><td>${x.debuff_gain_dps>=0?'+':''}${F1(x.debuff_gain_dps)}</td><td>${x.interaction_gain_dps>=0?'+':''}${F1(x.interaction_gain_dps)}</td><td><b>${x.profile_label||''}</b><br><span class=muted>PRE ${F(x.support_stats?.accuracy||0)} · Recovery ${P(x.support_stats?.skill_recovery||0)} · Skill Speed ${P(x.support_stats?.skill_speed||0)}<br>Auto/S1/S2/S3/Ult : ${['auto','s1','s2','s3','ult'].map(k=>(x.support_levels?.[k]===11?'♛':(x.support_levels?.[k]??'—'))).join(' / ')}</span></td><td>${(x.buffs||[]).map(e=>`${e.effect} (${P(e.uptime)})`).join(' · ')||'—'}</td><td>${(x.debuffs||[]).map(e=>`${e.effect} (${P(e.uptime)})`).join(' · ')||'—'}</td></tr>`).join('');
  bestSupportTop.innerHTML='<table><tr><th>#</th><th>Support</th><th>Rôle</th><th>DPS carry</th><th>Gain total</th><th>Buffs seuls</th><th>Debuffs seuls</th><th>Interaction</th><th>Profil utilisé</th><th>Buffs actifs</th><th>Debuffs actifs</th></tr>'+rows+'</table>';
  let t=d.best_trio;
  if(t){
    let marg=(t.marginal_contributions||[]).map(x=>`<tr><td><b>${x.name}</b></td><td class=good>+${F1(x.gain_dps)}</td><td>${P(x.gain_pct)}</td><td>${F1(x.dps_without)}</td></tr>`).join('');
    let alt=d.second_trio;
    let excl=t.best_excluded_individual;
    bestSupportTrio.innerHTML=`<div class=big>${t.names.join(' + ')}</div><div class=grid style="margin-top:12px">${cards({'DPS seul':F1(d.base_dps),'DPS avec trio':F1(t.dps),'Gain':`+${F1(t.gain_dps)} (${P(t.gain_pct)})`,'Candidats trio':d.trio_pool||0})}</div><h4 style="margin-top:16px">Contribution marginale dans ce trio</h4><table><tr><th>Support</th><th>DPS apporté dans ce trio</th><th>Gain vs DPS solo</th><th>DPS du duo sans lui</th></tr>${marg}</table>${alt?`<div class=note style="margin-top:12px"><b>Meilleure alternative :</b> ${alt.names.join(' + ')} — ${F1(alt.dps)} DPS, soit ${F1(t.dps-alt.dps)} DPS de moins que le trio retenu.</div>`:''}${excl?`<div class=muted style="margin-top:8px"><b>Meilleur support individuel non retenu :</b> ${excl.name} (+${F1(excl.gain_dps)}, ${P(excl.gain_pct)} seul). Un excellent résultat individuel peut être redondant avec les effets des deux autres supports.</div>`:''}<div class=muted style="margin-top:10px">Le trio est recherché parmi les meilleurs supports individuels afin de limiter le temps de calcul.</div>`;
  }else bestSupportTrio.innerHTML='Aucun trio pertinent trouvé.';
 }catch(e){bestSupportStatus.textContent='Erreur : '+e.message; throw e}finally{bestSupportBtn.disabled=false;bestSupportBtn.textContent='Analyser les meilleurs supports'}
}


async function relicOptimize(){
 let b=bosses[optBoss.value];relicOptBtn.disabled=true;relicOptBtn.textContent='Optimisation en cours…';relicOptStatus.textContent='Présélection des reliques, recherche des combinaisons puis simulations DPS…';
 try{
  let protectedHeroes=[...relicProtectedHeroes.selectedOptions].map(o=>o.value).filter(x=>x&&x!==optHero.value);let protectedQ=protectedHeroes.map(x=>'protected='+encodeURIComponent(x)).join('&');let d=await api(`/api/relic-optimize?name=${encodeURIComponent(optHero.value)}&mode=${encodeURIComponent(relicOptMode.value)}&duration=${optDur.value}&boss=${b.defense}&boss_res=${b.resistance}&boss_hp=${b.hp}&boss_atk=${b.attack}&element=${encodeURIComponent(b.element)}${protectedQ?'&'+protectedQ:''}`);
  relicOptStatus.textContent=`${d.collection_relics||0} reliques utilisables · ${d.simulated_combinations||0} combinaisons finalistes simulées · base stats : ${d.profile_source||'—'}. ${d.improved?'Meilleur build trouvé.':'Aucun build supérieur au build actuel : on garde les reliques actuelles.'}`;
  relicOptSummary.innerHTML=cards({'DPS actuel':F1(d.current?.dps||0),'DPS optimisé':F1(d.best?.dps||0),'Gain DPS':(d.gain_dps>=0?'+':'')+F1(d.gain_dps||0),'Gain %':(d.gain_pct>=0?'+':'')+P(d.gain_pct||0)});
  {
    let cur=d.current?.stats||{}, best=d.best?.stats||{};
    let defs=[['ATQ','atk','flat'],['Crit Rate','crit_rate','pct'],['Crit DMG','crit_dmg','pct'],['PRE','accuracy','flat'],['RÉS','resistance','flat'],['VIT combo','combo_speed','pct'],['VIT compétence','skill_speed','pct'],['Récup compétence','skill_recovery','pct'],['Gén mana','mana_gen','pct']];
    let rows=defs.map(([label,key,kind])=>{let a=cur[key]??0,z=best[key]??0,diff=z-a,fmt=v=>kind==='pct'?P(v):F1(v);return `<tr><td><b>${label}</b></td><td>${fmt(a)}</td><td>${fmt(z)}</td><td class="${diff>0?'good':''}">${diff>=0?'+':''}${fmt(diff)}</td></tr>`}).join('');
    let curSets=(d.current?.sets||[]).map(x=>x.name+' '+x.tiers.join('+')+(x.total?' ('+x.total+')':'')).join(' · ')||'Aucun';
    let bestSets=(d.best?.sets||[]).map(x=>x.name+' '+x.tiers.join('+')+(x.total?' ('+x.total+')':'')).join(' · ')||'Aucun';
    relicOptStats.innerHTML='<table><tr><th>Stat</th><th>Équipement actuel</th><th>Équipement recommandé</th><th>Écart</th></tr>'+rows+`<tr><td><b>Sets</b></td><td>${curSets}</td><td>${bestSets}</td><td>—</td></tr></table>`;
  }
  let rs=d.best?.relics||[];
  relicOptTable.innerHTML='<table><tr><th>Pièce</th><th>Relique recommandée</th><th>Actuelle</th><th>Action</th><th>Set</th><th>Niv.</th><th>Propriétaire actuel</th><th>Stats</th></tr>'+rs.map(r=>`<tr><td><b>${relicSlotName(r.slot)}</b></td><td><b>#${r.inventory_id}</b></td><td>${r.current_id?'#'+r.current_id:'—'}</td><td class=${r.change?'good':''}>${r.change?'CHANGER':'GARDER'}</td><td>${r.set_name?`${r.set_name} (#${r.set_id})`:(r.set_id??'—')}</td><td>${r.level??'—'}</td><td>${r.equipped_hero_name||'Libre'}</td><td>${(r.stats||[]).map(st=>`${st.stat} ${st.kind==='%'?F1(st.value)+'%':F(st.value)}`).join(' · ')||'—'}</td></tr>`).join('')+'</table>';
  relicOptLimits.innerHTML='<b>À savoir :</b> '+(d.limitations||[]).join(' · ');
 }catch(e){relicOptStatus.textContent='Erreur : '+e.message;throw e}finally{relicOptBtn.disabled=false;relicOptBtn.textContent='Optimiser mes 8 reliques'}
}

async function setOptimize(){
 let b=bosses[optBoss.value];setOptBtn.disabled=true;setOptBtn.textContent='Recherche en cours…';setOptStatus.textContent='Test des reliques, des seuils 3p/5p et des meilleures compositions par simulation DPS…';
 try{
  let d=await api(`/api/relic-optimize?name=${encodeURIComponent(optHero.value)}&mode=${encodeURIComponent(setOptMode.value)}&duration=${optDur.value}&boss=${b.defense}&boss_res=${b.resistance}&boss_hp=${b.hp}&boss_atk=${b.attack}&element=${encodeURIComponent(b.element)}`);
  let rows=d.set_rankings||[], best=rows[0];
  setOptStatus.textContent=`${d.simulated_combinations||0} builds finalistes simulés — ${d.collection_relics||0} reliques examinées — boss ${optBoss.value}.`;
  setOptSummary.innerHTML=cards({'DPS actuel':F1(d.current?.dps||0),'Meilleur DPS':F1(d.best?.dps||0),'Gain':`${F1((d.gain_pct||0)*100)} %`,'Set conseillé':best?best.label:'—'});
  setOptTable.innerHTML=rows.length?'<table><tr><th>#</th><th>Composition</th><th>DPS</th><th>Gain vs actuel</th><th>Écart au meilleur</th></tr>'+rows.map((r,i)=>{let gap=best&&best.dps?100*(r.dps/best.dps-1):0;return `<tr><td>${i+1}</td><td><b>${r.label}</b></td><td>${F1(r.dps)}</td><td class=${r.gain_pct>0?'good':''}>${r.gain_pct>=0?'+':''}${F1(100*r.gain_pct)} %</td><td>${i===0?'MEILLEUR':F1(gap)+' %'}</td></tr>`}).join('')+'</table>':'<div class=note>Aucune composition classable.</div>';
  if(best){let alt=rows[1];setOptAdvice.innerHTML=`<b>Conseil :</b> pour <b>${optHero.value}</b> contre <b>${optBoss.value}</b>, vise d’abord <b>${best.label}</b>. ${alt?`La meilleure alternative est <b>${alt.label}</b> (${F1(100*(alt.dps/best.dps-1))} % par rapport au meilleur).`:''}<br><span class=muted>Le classement dépend du héros, du boss, de la durée et des reliques réellement présentes dans ta collection.</span>`}else setOptAdvice.textContent='';
 }catch(e){setOptStatus.textContent='Erreur : '+e.message;setOptSummary.innerHTML='';setOptTable.innerHTML='';setOptAdvice.innerHTML='';throw e}finally{setOptBtn.disabled=false;setOptBtn.textContent='Trouver mes meilleurs sets'}
}

async function relicPotential(){
 potentialBtn.disabled=true;potentialBtn.textContent='Analyse en cours…';potentialStatus.textContent='Reconstruction des rolls 70/80/90/100 à partir des valeurs importées…';
 try{let b=bosses[optBoss.value]||{};let d=await api(`/api/relic-potential?name=${encodeURIComponent(optHero.value)}&boss_res=${encodeURIComponent(b.resistance||0)}`);
  potentialStatus.textContent=`${d.supported_relics||0}/${d.relic_count||0} reliques analysées · ${d.rolls_count||0} jets reconstruits · comparaison héros sur ${optBoss.value}.`;
  potentialSummary.innerHTML=cards({'Score moyen des rolls':d.roll_score==null?'—':F1(d.roll_score)+'%','Percentile rolls':d.percentile==null?'—':F1(d.percentile)+'e','Percentile héros / collection':d.hero_percentile==null?'—':F1(d.hero_percentile)+'e','Proximité moyenne du meilleur slot':d.hero_best_ratio==null?'—':F1(d.hero_best_ratio)+'%','Reliques analysées':`${d.supported_relics||0}/${d.relic_count||0}`,'Jets reconstruits':d.rolls_count||0});
  let rs=d.relics||[];potentialTable.innerHTML='<table><tr><th>Pièce</th><th>Relique</th><th>★</th><th>Niv.</th><th>Score rolls</th><th>Percentile rolls</th><th>Percentile héros</th><th>Rang collection</th><th>Proche du meilleur</th><th>Substats reconstruites</th></tr>'+rs.map(r=>`<tr><td><b>${relicSlotName(r.slot)}</b></td><td>#${r.inventory_id}</td><td>${r.rank||'—'}★</td><td>${r.level??'—'}</td><td>${r.roll_score==null?'—':F1(r.roll_score)+'%'}</td><td>${r.percentile==null?'—':F1(r.percentile)+'e'}</td><td>${r.hero_percentile==null?'—':F1(r.hero_percentile)+'e'}</td><td>${r.hero_slot_rank==null?'—':r.hero_slot_rank+'/'+r.hero_slot_total}</td><td>${r.hero_best_ratio==null?'—':F1(r.hero_best_ratio)+'%'}</td><td>${r.supported?(r.substats||[]).map(x=>`${x.stat} ${x.value}${[4,5,6,7,8].includes(x.stat_id)?'%':''} · +${x.upgrades} · rolls ${x.rolls.map(v=>Math.round(v*100)+'%').join('/')}`).join('<br>'):'Rang non encore décodé'}</td></tr>`).join('')+'</table>';
  potentialLimits.innerHTML='<b>Interprétation :</b> '+d.scope+'<br><b>Limites :</b> '+(d.limitations||[]).join(' · ');
 }catch(e){potentialStatus.textContent='Analyse indisponible : ce héros n’est pas présent dans la box importée.';potentialSummary.innerHTML='';potentialTable.innerHTML='';potentialLimits.innerHTML='';}finally{potentialBtn.disabled=false;potentialBtn.textContent='Analyser les reliques équipées'}
}

const aoeActionIds=[['Auto 1','a1'],['Auto 2','a2'],['Auto 3','a3'],['Auto 4','a4'],['Auto 5','a5'],['Skill 1','s1'],['Skill 2','s2'],['Skill 3','s3'],['Ultimate','ult']];
function renderAoeTargetInputs(defaults={}){aoeTargets.innerHTML=aoeActionIds.map(([lab,id])=>`<div class=control><label>${lab}</label><input id=aoeT_${id} type=number min=1 max=200 value="${defaults[lab]||1}"></div>`).join('')}
function aoeTargetQuery(){return aoeActionIds.map(([lab,id])=>`&t_${id}=${Math.max(1,+document.getElementById('aoeT_'+id).value||1)}`).join('')}
async function loadAoeDefaults(){let d=await api(`/api/aoe-defaults?name=${encodeURIComponent(aoeHero.value)}&enemies=${aoeEnemies.value}`);renderAoeTargetInputs(d.targets||{});let parts=aoeActionIds.map(([lab])=>`${lab}: ${d.targets?.[lab]||1} [${d.sources?.[lab]||'unknown'}]`);aoeTargetStatus.textContent=parts.join(' · ')}
async function importAllAoe(){aoeImportAll.disabled=true;aoeImportAll.textContent='Import en cours…';aoeProbeStatus.textContent='Lecture des fiches GGNoLuck pour tous les héros…';try{let r=await fetch('/api/aoe-import-all',{method:'POST'});let d=await r.json();if(!r.ok||!d.ok)throw Error(d.error||'Import impossible');let fails=(d.failed||[]).map(x=>x.hero).filter(Boolean);aoeProbeStatus.textContent=`Import AoE terminé : ${d.heroes_read}/${d.heroes_total} héros lus · ${d.saved_actions} actions enregistrées · ${d.failed_count} échec(s)`+(fails.length?` — échec : ${fails.join(', ')}`:'')+'.';await loadAoeDefaults();await aoeCombatRun();await aoeRankRun()}catch(e){aoeProbeStatus.textContent='Erreur import AoE : '+e.message}finally{aoeImportAll.disabled=false;aoeImportAll.textContent='Importer AoE des 222 héros'}}
async function probeAoeStatic(){aoeProbeStatic.disabled=true;aoeProbeStatus.textContent='Analyse locale de static.data…';try{let d=await api(`/api/aoe-static-probe?name=${encodeURIComponent(aoeHero.value)}`);if(!d.ok){aoeProbeStatus.textContent='Probe: '+(d.error||'indisponible');return}let rows=(d.candidates||[]).slice(0,12).map(x=>`cat ${x.category} · id ${x.id} · ${(x.reasons||[]).join('+')} · ${x.uncompressed_size||x.size} o`);aoeProbeStatus.textContent=`static.data: ${d.candidate_count} chunk(s) candidat(s) pour ${d.hero} (${d.code}, GDID ${d.gdid}). `+(rows.length?rows.join(' | '):'Aucun match direct.') }finally{aoeProbeStatic.disabled=false}}
async function saveAoeTargets(){let targets={};for(let [lab,id] of aoeActionIds)targets[lab]=Math.max(1,+document.getElementById('aoeT_'+id).value||1);let r=await fetch('/api/aoe-targets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:aoeHero.value,targets})});if(!r.ok)throw Error(await r.text());aoeTargetStatus.textContent='✓ Portées enregistrées pour '+aoeHero.value;await aoeCombatRun()}
async function aoeRankRun(){aoeRankBtn.disabled=true;aoeRankBtn.textContent='Calcul…';aoeRankStatus.textContent='Classement AoE en cours…';try{let b=bosses[aoeBoss.value];let d=await api(`/api/aoe-rank?preset=${encodeURIComponent(aoePreset.value)}&duration=${aoeDur.value}&enemies=${aoeEnemies.value}&defense=${b.defense}&resistance=${b.resistance}&element=${encodeURIComponent(b.element)}`);aoeRankStatus.textContent=`${d.length} héros simulés — ${aoeEnemies.value} ennemis — boss ${aoeBoss.value}.`;aoeRankTable.innerHTML='<table><tr><th>#</th><th>Héros</th><th>Élément</th><th>Rareté</th><th>Rôle</th><th>DPS AoE</th><th>DPS mono</th><th>Dégâts AoE</th><th>Actions AoE connues</th></tr>'+d.map((x,i)=>`<tr><td>${i+1}</td><td>${x.name}</td><td>${x.element||'Neutre'}</td><td>${x.rarity||''}</td><td>${x.role||''}</td><td><b>${F1(x.dps)}</b></td><td>${F1(x.single_target_dps)}</td><td>${F(x.total_damage)}</td><td>${(x.mapped_aoe_actions||[]).join(', ')||'—'}</td></tr>`).join('')+'</table>'}finally{aoeRankBtn.disabled=false;aoeRankBtn.textContent='Calculer le classement AoE'}}
async function aoeCombatRun(){aoeBtn.disabled=true;aoeBtn.textContent='Simulation…';try{let b=bosses[aoeBoss.value];let d=await api(`/api/aoe-combat?name=${encodeURIComponent(aoeHero.value)}&preset=${encodeURIComponent(aoePreset.value)}&duration=${aoeDur.value}&enemies=${aoeEnemies.value}&defense=${b.defense}&resistance=${b.resistance}&element=${encodeURIComponent(b.element)}${aoeTargetQuery()}`);aoeSummary.innerHTML=cards({'Héros':d.hero,'Preset':d.preset_label,'Ennemis':d.enemies,'DPS AoE total':F1(d.dps),'DPS mono de référence':F1(d.single_target_dps),'Dégâts AoE':F(d.total_damage)});aoeStatus.textContent=d.note+(d.mapped_aoe_actions?.length?' AoE renseignées : '+d.mapped_aoe_actions.join(', ')+'.':' Aucune action AoE >1 cible renseignée.');aoeTable.innerHTML='<table><tr><th>Action</th><th>Cibles</th><th>Casts</th><th>Dégâts mono</th><th>Dégâts AoE</th></tr>'+d.rows.map(x=>`<tr><td>${x.action}</td><td>${x.targets}</td><td>${x.casts}</td><td>${F(x.single_target_damage)}</td><td><b>${F(x.aoe_damage)}</b></td></tr>`).join('')+'</table>'}finally{aoeBtn.disabled=false;aoeBtn.textContent='Simuler'}}
let rankRun=0; async function rank(){const run=++rankRun;let b=bosses[rankBoss.value],mode=rankMode.value,supportMode=rankSupportMode.value;let rankElem=(rankElement.value==='Auto'?b.element:rankElement.value);let sups=[rankSupport1.value,rankSupport2.value,rankSupport3.value,rankSupport4.value];rankBtn.disabled=true;rankBtn.textContent='Calcul en cours…';rankStatus.textContent='Simulation en cours…';let supq=`&support1=${encodeURIComponent(sups[0])}&support2=${encodeURIComponent(sups[1])}&support3=${encodeURIComponent(sups[2])}&support4=${encodeURIComponent(sups[3])}`;try{let d=await api(`/api/rank?mode=${mode}&support_mode=${encodeURIComponent(supportMode)}&rarity=${encodeURIComponent(rarity.value)}&role=${encodeURIComponent(role.value)}&duration=${rankDur.value}&boss=${b.defense}&boss_res=${b.resistance}&boss_hp=${b.hp}&boss_atk=${b.attack}&element=${encodeURIComponent(rankElem)}${supq}`);if(run!==rankRun)return;let active=[...new Set(sups.filter(x=>x&&x!=='Aucun'))];let modeLabel=mode==='box'?'Ma box':mode==='early'?'Early game':mode==='mid'?'Mid game':'Late game';let supportModeLabel=supportMode==='box'?'Ma box':supportMode==='early'?'Early game':supportMode==='mid'?'Mid game':'Late game';rankStatus.textContent=`${d.length} héros simulés — preset héros : ${modeLabel} — preset supports : ${supportModeLabel} — élément boss : ${rankElem}${active.length?' — supports : '+active.join(' + '):' — sans support'}.`;rankTable.innerHTML='<table><tr><th>#</th><th>Héros</th><th>Élément</th><th>Rareté</th><th>Rôle</th><th>DPS simulé</th><th>Dégâts</th><th>ATK</th><th>Crit</th><th>Crit DMG</th><th>PRE</th><th>Combo</th><th>Skill Speed</th><th>Recovery</th></tr>'+d.map((x,i)=>`<tr><td>${i+1}</td><td>${x.name}</td><td>${x.element||'Neutre'}</td><td>${x.rarity||''}</td><td>${x.role||''}</td><td>${F1(x.dps)}</td><td>${F(x.total_damage)}</td><td>${F(x.final_stats.atk)}</td><td>${P(x.final_stats.crit_rate)}</td><td>${P(x.final_stats.crit_dmg)}</td><td>${F(x.final_stats.accuracy)}</td><td>${P(x.final_stats.combo_speed)}</td><td>${P(x.final_stats.skill_speed)}</td><td>${P(x.final_stats.skill_recovery)}</td></tr>`).join('')+'</table>'}catch(e){if(run===rankRun)rankStatus.textContent='Erreur classement : '+e.message;throw e}finally{if(run===rankRun){rankBtn.disabled=false;rankBtn.textContent='Calculer'}}}
(async()=>{heroes=await api('/api/heroes');let n=heroes.map(x=>x.name);let ownedHeroNames=await api('/api/box-hero-names');relicProtectedHeroes.innerHTML=ownedHeroNames.map(x=>`<option value="${x}">${x}</option>`).join('');[heroSel,combatHero,aSel,bSel,optHero].forEach((e,i)=>opts(e,n,i===3?'Sildrea':'Senhachi'));opts(aoeHero,n,'Moros');renderAoeTargetInputs({});for(let e of [support1,support2,support3,support4,rankSupport1,rankSupport2,rankSupport3,rankSupport4])opts(e,['Aucun',...n],'Aucun');[support1,support2,support3,support4].forEach(e=>e.onchange=combat);[rankSupport1,rankSupport2,rankSupport3,rankSupport4].forEach(e=>e.onchange=rank);rankSupportMode.onchange=rank;rankElement.onchange=rank;addsMode.onchange=combat;bosses=await api('/api/boss-setups');titans=await api('/api/titans');[simBoss,optBoss,rankBoss,aoeBoss].forEach(e=>{Object.keys(bosses).forEach(x=>e.add(new Option(x,x)));e.value='Ulgorim 16'});optBoss.onchange=async()=>{await critAnalysis();await recAnalysis();await relicPotential()};rankBoss.onchange=rank;simBossCards.innerHTML=bossCards(bosses[simBoss.value]);simBoss.onchange=()=>{simBossCards.innerHTML=bossCards(bosses[simBoss.value]);simElement.value='Auto';combat();compare()};simElement.onchange=()=>{combat();compare()};build(heroBuild,'hero');levels(heroLevels,'heroLvl');levels(optLevels,'opt');trophyElement.onchange=renderTrophyHeroes;
trophySelectAll.onclick=()=>[...trophyHeroes.options].forEach(o=>o.selected=true);
trophyClear.onclick=()=>[...trophyHeroes.options].forEach(o=>o.selected=false);
trophyBtn.onclick=trophyRun;
heroSel.onchange=hero;combatHero.onchange=combat;combatPreset.onchange=()=>{let notes={box:'Ma box : stats et niveaux réellement importés.',early:'Early : skills 1 · ATQ +30% · Crit 20% · Dég crit 50% · PRE +80 · Combo/Skill/Recovery/Mana +5%.',mid:'Mid : skills 5 · ATQ +80% · Crit 50% · Dég crit 75% · PRE +220 · Combo/Skill/Recovery/Mana +15%.',late:'Late : skills max · ATQ +150% · Crit 100% · Dég crit 120% · PRE +400 · Combo/Skill/Recovery/Mana +30%.'};combatPresetNote.textContent=notes[combatPreset.value]||'';combat();compare()};aSel.onchange=compare;bSel.onchange=compare;recFields(recCurrentStats,'recCur');recTestFields(recTestStats,'recTest');optHero.onchange=async()=>{await loadRecStats();await critAnalysis();await recAnalysis();await relicPotential()};[...new Set(heroes.map(x=>x.rarity).filter(Boolean))].sort().forEach(x=>rarity.add(new Option(x,x)));[...new Set(heroes.map(x=>x.role).filter(Boolean))].sort().forEach(x=>role.add(new Option(x,x)));rankMode.onchange=()=>{let notes={box:'Ma box : classement avec les builds réellement importés.',early:'Early : skills 1 · ATQ +30% · Crit 20% · Dég crit 50% · PRE +80 · Combo/Skill/Recovery/Mana +5%.',mid:'Mid : skills 5 · ATQ +80% · Crit 50% · Dég crit 75% · PRE +220 · Combo/Skill/Recovery/Mana +15%.',late:'Late : skills max · ATQ +150% · Crit 100% · Dég crit 120% · PRE +400 · Combo/Skill/Recovery/Mana +30%.'};rankModeNote.textContent=notes[rankMode.value]||'';rank()};combatBtn.onclick=combat;bestSupportMode.onchange=()=>{let notes={real:'Ma box : uniquement les héros que tu possèdes, avec leur vraie fiche importée.',base:'Stats de base : stats natives du héros et tous les skills niveau 1.',max:'Max support : stats natives, skills max, PRE 1000, Combo/Skill Speed/Recovery/Mana +30%.'};bestSupportModeNote.textContent=notes[bestSupportMode.value]||''};bestSupportBtn.onclick=bestSupports;cmpBtn.onclick=compare;critBtn.onclick=critAnalysis;recBtn.onclick=recAnalysis;recBalanceBtn.onclick=recBalance;relicOptBtn.onclick=relicOptimize;setOptBtn.onclick=setOptimize;potentialBtn.onclick=relicPotential;rankBtn.onclick=rank;aoeHero.onchange=async()=>{await loadAoeDefaults();await aoeCombatRun()};aoePreset.onchange=()=>{aoeCombatRun();aoeRankRun()};aoeEnemies.onchange=async()=>{await loadAoeDefaults();await aoeCombatRun();await aoeRankRun()};aoeBoss.onchange=()=>{aoeCombatRun();aoeRankRun()};aoeBtn.onclick=aoeCombatRun;aoeRankBtn.onclick=aoeRankRun;aoeSaveTargets.onclick=saveAoeTargets;aoeProbeStatic.onclick=probeAoeStatic;aoeImportAll.onclick=importAllAoe;importBoxBtn.onclick=importBoxOneClick;relicRefresh.onclick=loadRelics;[relicSlot,relicSet,relicEquipped,relicStat].forEach(e=>e.onchange=loadRelics);await loadRelics();await hero();await loadRecStats();await loadTrophyHeroes();await combat();await compare();await critAnalysis();await recAnalysis();await relicPotential();await loadAoeDefaults();await aoeCombatRun();await aoeRankRun();await rank()})().catch(e=>document.body.insertAdjacentHTML('beforeend',`<pre>${e.stack}</pre>`));
</script></body></html>'''

COMBAT_PRESETS={
    'early': {
        'label':'Early game','skill_level':1,
        'atk_bonus_pct':0.30,'crit_rate':0.20,'crit_dmg':0.50,'accuracy_bonus':80,
        'combo_speed':0.05,'skill_speed':0.05,'skill_recovery':0.05,'mana_gen':0.05
    },
    'mid': {
        'label':'Mid game','skill_level':5,
        'atk_bonus_pct':0.80,'crit_rate':0.50,'crit_dmg':0.75,'accuracy_bonus':220,
        'combo_speed':0.15,'skill_speed':0.15,'skill_recovery':0.15,'mana_gen':0.15
    },
    'late': {
        'label':'Late game','skill_level':11,
        'atk_bonus_pct':1.50,'crit_rate':1.00,'crit_dmg':1.20,'accuracy_bonus':400,
        'combo_speed':0.30,'skill_speed':0.30,'skill_recovery':0.30,'mana_gen':0.30
    },
}

def combat_preset_for(name,preset='box'):
    """Build standardized Early/Mid/Late combat states without overwriting Ma box.

    Presets are expressed from each hero's native/reference stats so heroes keep
    their natural stat differences while receiving the same investment standard.
    """
    p=profile_for(name)
    box_st=profile_stats(name,p)
    key=str(preset or 'box').strip().lower()
    if key not in COMBAT_PRESETS:
        return final_to_build(name,box_st),box_st,profile_levels(p),'Ma box','box'

    cfg=COMBAT_PRESETS[key]
    h=hero_row(name) or {}
    base_atk=max(1.0,num(h.get('atk')))
    base_pre=num(h.get('accuracy'))
    base_res=num(h.get('resistance'))

    pst={
        'atk':base_atk*(1.0+cfg['atk_bonus_pct']),
        'crit_rate':cfg['crit_rate'],
        'crit_dmg':cfg['crit_dmg'],
        'accuracy':base_pre+cfg['accuracy_bonus'],
        'resistance':base_res,
        'combo_speed':cfg['combo_speed'],
        'skill_speed':cfg['skill_speed'],
        'skill_recovery':cfg['skill_recovery'],
        'mana_gen':cfg['mana_gen'],
    }
    lv={k:int(cfg['skill_level']) for k in ('auto','s1','s2','s3','ult')}
    return final_to_build(name,pst),pst,lv,cfg['label'],key

class H(BaseHTTPRequestHandler):
    def sendj(self,obj,status=200):
        raw=json.dumps(obj,ensure_ascii=False,default=str).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',len(raw)); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        p=urlparse(self.path); qs=parse_qs(p.query)
        def f(k,d):
            try:return float(qs.get(k,[str(d)])[0])
            except:return d
        def levels(pre=''):
            return {k:qs.get(pre+k,['7'])[0] for k in ('auto','s1','s2','s3','ult')}
        def stats_input(pre=''):
            return dict(atk=f(pre+'atk_final',2500),crit_rate=f(pre+'cr_final',.70),crit_dmg=f(pre+'cd_final',1.40),accuracy=f(pre+'pre_final',340),resistance=f(pre+'res_final',100),combo_speed=f(pre+'combo_final',.25),skill_speed=f(pre+'skill_speed_final',.20),skill_recovery=f(pre+'recovery_final',.20),mana_gen=f(pre+'mana_final',.20))
        def manual_build_for(name,pre=''):
            st=apply_titan(name,stats_input(pre),qs.get(pre+'titan',['Aucun'])[0],f(pre+'titan_stars',0),bool(int(f(pre+'titan_dungeon',0))))
            return final_to_build(name,st),st
        def saved_build_for(name):
            p=profile_for(name); st=profile_stats(name,p); return final_to_build(name,st),st,p
        try:
            if p.path in ('/','/index.html'):
                raw=HTML.encode(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',len(raw)); self.end_headers(); self.wfile.write(raw); return
            if p.path=='/api/game-import/scan': self.sendj(scan_game_import()); return
            if p.path=='/api/game-import/diff': self.sendj(compare_game_diff_snapshot()); return
            if p.path=='/api/game-import/player-aggregate': self.sendj(scan_player_aggregate_artifacts()); return
            if p.path=='/api/game-import/static-cache': self.sendj(scan_static_data_cache()); return
            if p.path=='/api/game-import/static-pack': self.sendj(inspect_static_chunkpack()); return
            if p.path=='/api/game-import/static-hall-scan': self.sendj(scan_static_hall_f64_arrays()); return
            if p.path=='/api/game-import/static-hall-live': self.sendj({'ok':bool(_LIVE_ARENA_HALL_INFO),'source':ARENA_HALL_SOURCE,'live':_LIVE_ARENA_HALL_INFO,'values':ARENA_HALL_VALUES,**_game_readonly_status()}); return
            if p.path=='/api/game-import/player-arena-hall-raw': self.sendj(inspect_playerarena_hall_raw()); return
            if p.path=='/api/game-import/hero-skills-raw':
                skill_qs=parse_qs(p.query); name=(skill_qs.get('name') or [''])[0]
                self.sendj(inspect_box_hero_skilllevels(name)); return
            if p.path=='/api/game-import/decode-box': self.sendj(decode_local_box()); return
            if p.path=='/api/game-import/analyze-diff': self.sendj(analyze_last_game_diff()); return
            if p.path=='/api/heroes': self.sendj(q('SELECT name,faction,rarity,role,element FROM heroes WHERE name IS NOT NULL ORDER BY name')); return
            if p.path=='/api/boss-setups': self.sendj(BOSS_SETUPS); return
            if p.path=='/api/titans': self.sendj(TITANS); return
            if p.path=='/api/box-hero':
                self.sendj({'box':box_hero_for_name(qs.get('name',[''])[0])}); return
            if p.path=='/api/box-hero-names':
                ensure_box_tables(); self.sendj([x.get('hero_name') for x in q("SELECT DISTINCT hero_name FROM box_heroes WHERE hero_name IS NOT NULL AND trim(hero_name)<>'' ORDER BY lower(hero_name)")]); return
            if p.path=='/api/box-relics':
                self.sendj(box_relic_inventory(qs.get('slot',['all'])[0],qs.get('set',['all'])[0],qs.get('equipped',['all'])[0],qs.get('stat',['all'])[0],qs.get('limit',['500'])[0])); return
            if p.path=='/api/profile':
                n=qs.get('name',[''])[0]; pr=profile_for(n); self.sendj({'profile':pr,'final_stats':profile_stats(n,pr)}); return
            if p.path=='/api/hero':
                n=qs.get('name',[''])[0]; lv=levels(); self.sendj({'hero':hero_row(n),'coeffs':{k:coeff_row(n,v) for k,v in lv.items()}}); return
            if p.path=='/api/auto-timings':
                name=qs.get('name',[''])[0]; row=auto_timing_row(name)
                if row:self.sendj({'hero':name,'source':'extracted','timings':row})
                else:self.sendj({'hero':name,'source':'legacy_fallback','timings':None,'cycle_base_s':auto_chain_cycle_base(name)})
                return
            if p.path=='/api/trophy-opt':
                element=qs.get('element',['Eau'])[0]
                names=[x for x in qs.get('heroes',[''])[0].split('|') if x]
                costs=[x for x in qs.get('costs',[''])[0].split(',') if x.strip()!='']
                self.sendj(optimize_trophy_hall(element,names,f('duration',120),f('defense',1320),f('resistance',0),f('hp',0),f('attack',0),qs.get('boss_element',['Neutre'])[0],costs)); return
            if p.path=='/api/aoe-audit':
                n=qs.get('name',[''])[0]; targets,sources=aoe_default_targets(n,max(1,min(11,int(f('enemies',11))))); self.sendj({'hero':n,'targets':targets,'sources':sources,'saved':saved_aoe_targets(n),'validated':AOE_KNOWN_TARGETS.get(n,{})}); return
            if p.path=='/api/aoe-static-probe':
                n=qs.get('name',[''])[0]; self.sendj(probe_static_for_hero(n)); return
            if p.path=='/api/aoe-defaults':
                n=qs.get('name',[''])[0]; enemies=max(1,min(11,int(f('enemies',11)))); targets,sources=aoe_default_targets(n,enemies); inferred,evidence=infer_aoe_targets_from_text(n,enemies); self.sendj({'hero':n,'targets':targets,'sources':sources,'evidence':evidence}); return
            if p.path=='/api/aoe-rank':
                preset=qs.get('preset',['box'])[0]; duration=f('duration',60); enemies=max(1,min(11,int(f('enemies',11)))); defense=f('defense',0); resistance=f('resistance',0); element=qs.get('element',['Neutre'])[0]
                out=[]
                for h in q('SELECT name,rarity,role,element FROM heroes WHERE name IS NOT NULL'):
                    if preset=='box' and not has_saved_profile(h['name']): continue
                    r=simulate_aoe(h['name'],preset,duration,enemies,defense,resistance,element)
                    if not r: continue
                    out.append({'name':h['name'],'rarity':h.get('rarity'),'role':h.get('role'),'element':h.get('element'),
                                'dps':r.get('dps',0),'single_target_dps':r.get('single_target_dps',0),
                                'total_damage':r.get('total_damage',0),'mapped_aoe_actions':r.get('mapped_aoe_actions',[])})
                out.sort(key=lambda x:x['dps'],reverse=True)
                self.sendj(out); return
            if p.path=='/api/aoe-combat':
                n=qs.get('name',[''])[0]; preset=qs.get('preset',['box'])[0]
                keymap={'a1':'Auto 1','a2':'Auto 2','a3':'Auto 3','a4':'Auto 4','a5':'Auto 5','s1':'Skill 1','s2':'Skill 2','s3':'Skill 3','ult':'Ultimate'}
                ov={label:max(1,int(f('t_'+short,1))) for short,label in keymap.items()}
                r=simulate_aoe(n,preset,f('duration',60),f('enemies',11),f('defense',0),f('resistance',0),qs.get('element',['Neutre'])[0],ov)
                self.sendj(r or {'error':'données manquantes'},200 if r else 400); return
            if p.path=='/api/combat':
                name=qs.get('name',[''])[0]; preset=qs.get('preset',['box'])[0]; b,st,combat_lv,preset_label,preset_key=combat_preset_for(name,preset); supports=[qs.get(f'support{i}',['Aucun'])[0] for i in range(1,5)]; dur=f('duration',120); r=simulate_combat(name,combat_lv,dur,f('boss',1320),f('boss_res',0),f('boss_hp',0),f('boss_atk',0),qs.get('element',['Neutre'])[0],**b,analyze_effect_gains=True,team_supports=supports,adds_mode=qs.get('adds_mode',['none'])[0]);
                if r:
                    base=simulate_combat(name,combat_lv,dur,f('boss',1320),f('boss_res',0),f('boss_hp',0),f('boss_atk',0),qs.get('element',['Neutre'])[0],**b)
                    base_dps=base['dps'] if base else r['dps']
                    r['dps_without_supports']=base_dps
                    r['support_gain_dps']=round(r['dps']-base_dps,2)
                    # Mesure individuelle des buffers sur le même carry / boss / durée.
                    # Gain seul = buffer actif sans l'autre.
                    # Apport marginal = perte de DPS si on retire ce buffer du duo.
                    indiv=[]; single_sims={}
                    active_supports=[x for x in supports if x and x!='Aucun']
                    for sn in active_supports:
                        one=simulate_combat(name,combat_lv,dur,f('boss',1320),f('boss_res',0),f('boss_hp',0),f('boss_atk',0),qs.get('element',['Neutre'])[0],**b,team_supports=[sn],adds_mode=qs.get('adds_mode',['none'])[0])
                        if one: single_sims[sn]=one
                    for sn in active_supports:
                        one=single_sims.get(sn)
                        other_names=[x for x in active_supports if x!=sn]
                        if other_names:
                            other=single_sims.get(other_names[0]) if len(other_names)==1 else simulate_combat(name,combat_lv,dur,f('boss',1320),f('boss_res',0),f('boss_hp',0),f('boss_atk',0),qs.get('element',['Neutre'])[0],**b,team_supports=other_names,adds_mode=qs.get('adds_mode',['none'])[0])
                            marginal=round(r['dps']-(other['dps'] if other else base_dps),2)
                        else:
                            marginal=round((one['dps'] if one else base_dps)-base_dps,2)
                        gain=round((one['dps'] if one else base_dps)-base_dps,2)
                        buffs=(one or {}).get('team_buffs',[])
                        indiv.append({'name':sn,'dps_with_only':(one or {}).get('dps',base_dps),'gain_dps':gain,'gain_pct':gain/base_dps if base_dps else 0,'marginal_gain_dps':marginal,'buffs':buffs})
                    sum_indiv=sum(x['gain_dps'] for x in indiv)
                    r['support_contributions']=indiv
                    r['support_synergy_dps']=round(r['support_gain_dps']-sum_indiv,2)
                    r['titan']=st.get('_titan')
                    r['preset']=preset_key; r['preset_label']=preset_label; r['preset_stats']=st; r['preset_levels']=combat_lv
                self.sendj(r or {'error':'données manquantes'},200 if r else 400); return
            if p.path=='/api/best-supports':
                from itertools import combinations
                name=qs.get('name',[''])[0]; bld,st,pr=saved_build_for(name); lv=profile_levels(pr); dur=f('duration',120); bd=f('boss',1320); br=f('boss_res',0); bhp=f('boss_hp',0); batk=f('boss_atk',0); elem=qs.get('element',['Neutre'])[0]; support_mode=qs.get('support_mode',['real'])[0]
                base=simulate_combat(name,lv,dur,bd,br,bhp,batk,elem,**bld)
                if not base: self.sendj({'error':'données manquantes'},400); return
                base_dps=base['dps']; results=[]
                candidates=q("SELECT name,role FROM heroes WHERE name IS NOT NULL ORDER BY name")
                owned_names=None
                if str(support_mode or 'real').lower()=='real':
                    ensure_box_tables()
                    owned_names={str(x.get('hero_name') or '').strip().lower() for x in q("SELECT DISTINCT hero_name FROM box_heroes WHERE hero_name IS NOT NULL AND trim(hero_name)<>''")}
                for c in candidates:
                    sn=c['name']
                    if sn==name: continue
                    if str(sn).strip().lower() in NON_SUPPORT_HEROES: continue
                    if owned_names is not None and str(sn).strip().lower() not in owned_names: continue
                    events,info=prepare_team_buffs([sn],dur,'none',br,elem,support_mode)
                    if not events: continue
                    prepared={'events':events,'support_info':info}
                    full=simulate_combat(name,lv,dur,bd,br,bhp,batk,elem,**bld,team_supports=[sn],prepared_team=prepared)
                    if not full: continue
                    buff_events=[e for e in events if e.get('kind')=='buff']
                    debuff_events=[e for e in events if e.get('kind')=='debuff']
                    if buff_events:
                        bo=simulate_combat(name,lv,dur,bd,br,bhp,batk,elem,**bld,team_supports=[sn],prepared_team={'events':buff_events,'support_info':info})
                        buff_gain=round((bo['dps'] if bo else base_dps)-base_dps,2)
                    else: buff_gain=0.0
                    if debuff_events:
                        do=simulate_combat(name,lv,dur,bd,br,bhp,batk,elem,**bld,team_supports=[sn],prepared_team={'events':debuff_events,'support_info':info})
                        debuff_gain=round((do['dps'] if do else base_dps)-base_dps,2)
                    else: debuff_gain=0.0
                    gain=round(full['dps']-base_dps,2)
                    si=(info[0] if info else {}); results.append({'name':sn,'role':c.get('role'),'profile_label':('Max support' if support_mode in ('best','max','normalized') else 'Stats de base' if support_mode in ('base','base_stats','native') else 'Ma box'),'support_stats':si.get('stats',{}),'support_levels':si.get('levels',{}),'dps':full['dps'],'gain_dps':gain,'gain_pct':gain/base_dps if base_dps else 0,'buff_gain_dps':buff_gain,'debuff_gain_dps':debuff_gain,'interaction_gain_dps':round(gain-buff_gain-debuff_gain,2),'buffs':summarize_team_buffs(buff_events,dur),'debuffs':summarize_team_buffs(debuff_events,dur)})
                results.sort(key=lambda x:x['gain_dps'],reverse=True)
                positive=[x for x in results if x['gain_dps']>0]
                trio_candidates=positive[:8]
                trio_results=[]
                for combo in combinations([x['name'] for x in trio_candidates],3):
                    combo=list(combo)
                    events,info=prepare_team_buffs(combo,dur,'none',br,elem,support_mode)
                    rr=simulate_combat(name,lv,dur,bd,br,bhp,batk,elem,**bld,team_supports=combo,prepared_team={'events':events,'support_info':info})
                    if not rr: continue
                    gain=round(rr['dps']-base_dps,2)
                    trio_results.append({'names':combo,'dps':rr['dps'],'gain_dps':gain,'gain_pct':gain/base_dps if base_dps else 0})
                trio_results.sort(key=lambda x:x['gain_dps'],reverse=True)
                best_trio=trio_results[0] if trio_results else None
                second_trio=trio_results[1] if len(trio_results)>1 else None
                if best_trio:
                    # Contribution marginale réelle dans CE trio : perte si on retire le support
                    # tout en conservant les deux autres. Cela met en évidence les redondances.
                    marg=[]
                    for sn in best_trio['names']:
                        others=[x for x in best_trio['names'] if x!=sn]
                        ev2,inf2=prepare_team_buffs(others,dur,'none',br,elem,support_mode)
                        rr2=simulate_combat(name,lv,dur,bd,br,bhp,batk,elem,**bld,team_supports=others,prepared_team={'events':ev2,'support_info':inf2})
                        dps2=rr2['dps'] if rr2 else base_dps
                        mg=round(best_trio['dps']-dps2,2)
                        marg.append({'name':sn,'gain_dps':mg,'gain_pct':mg/base_dps if base_dps else 0,'dps_without':dps2})
                    best_trio['marginal_contributions']=sorted(marg,key=lambda x:x['gain_dps'],reverse=True)
                    # Meilleur support individuel non retenu, pratique pour expliquer pourquoi le Top 3 individuel
                    # n'est pas nécessairement le meilleur trio.
                    excluded=next((x for x in positive if x['name'] not in best_trio['names']),None)
                    best_trio['best_excluded_individual']={'name':excluded['name'],'gain_dps':excluded['gain_dps'],'gain_pct':excluded['gain_pct']} if excluded else None
                self.sendj({'hero':name,'base_dps':base_dps,'tested':len(results),'support_mode':support_mode,'top3':results[:3],'best_trio':best_trio,'second_trio':second_trio,'trio_pool':len(trio_candidates)}); return
            if p.path=='/api/compare':
                common=(f('duration',120),f('boss',1320),f('boss_res',0),f('boss_hp',0),f('boss_atk',0),qs.get('element',['Neutre'])[0]); an=qs.get('a',[''])[0]; bn=qs.get('b',[''])[0]; preset=qs.get('preset',['box'])[0]
                ab,ast,alv,alabel,_=combat_preset_for(an,preset); bb,bst,blv,blabel,_=combat_preset_for(bn,preset)
                a=simulate_combat(an,alv,*common,**ab); b=simulate_combat(bn,blv,*common,**bb)
                if not a or not b:self.sendj({'error':'données manquantes'},400);return
                a['preset_levels']=alv; a['preset_label']=alabel; b['preset_levels']=blv; b['preset_label']=blabel
                diff=a['dps']-b['dps']; self.sendj({'a':a,'b':b,'preset':preset,'winner':a['hero'] if diff>0 else b['hero'] if diff<0 else None,'diff_dps':abs(diff),'pct':abs(diff)/max(1,min(a['dps'],b['dps']))}); return
            if p.path=='/api/relic-optimize':
                name=qs.get('name',[''])[0]; mode=qs.get('mode',['all'])[0]; protected=qs.get('protected',[])
                r=optimize_relics_for_dps(name,f('duration',120),f('boss',1320),f('boss_res',0),f('boss_hp',0),f('boss_atk',0),qs.get('element',['Neutre'])[0],mode,protected)
                self.sendj(r,400 if r.get('error') else 200); return
            if p.path=='/api/relic-potential':
                r=relic_roll_potential(qs.get('name',[''])[0],num(qs.get('boss_res',[0])[0])); self.sendj(r,400 if r.get('error') else 200); return
            if p.path=='/api/crit-analysis':
                name=qs.get('name',[''])[0]; _,st,_=saved_build_for(name); self.sendj(attack_crit_analysis(name,st.get('atk'),st.get('crit_rate'),st.get('crit_dmg'),f('bonus_atk',.225),f('bonus_cr',.225),f('bonus_cd',.3))); return
            if p.path=='/api/recovery-analysis':
                cur={'atk':f('cur_atk',0),'crit_rate':f('cur_crit_rate',0),'crit_dmg':f('cur_crit_dmg',0),'accuracy':f('cur_accuracy',0),'resistance':f('cur_resistance',0),'combo_speed':f('cur_combo_speed',0),'mana_gen':f('cur_mana_gen',0),'skill_recovery':f('cur_skill_recovery',0),'skill_speed':f('cur_skill_speed',0)}
                tst={'atk':f('test_atk',0),'crit_rate':f('test_crit_rate',0),'crit_dmg':f('test_crit_dmg',0),'accuracy':f('test_accuracy',0),'resistance':f('test_resistance',0),'combo_speed':f('test_combo_speed',0),'mana_gen':f('test_mana_gen',0),'skill_recovery':f('test_skill_recovery',0),'skill_speed':f('test_skill_speed',0)}
                self.sendj(recovery_speed_analysis(qs.get('name',[''])[0],levels(),f('duration',120),f('boss',1320),f('boss_res',0),f('boss_hp',0),f('boss_atk',0),qs.get('element',['Neutre'])[0],cur,tst)); return
            if p.path=='/api/recovery-balance':
                cur={'atk':f('cur_atk',0),'crit_rate':f('cur_crit_rate',0),'crit_dmg':f('cur_crit_dmg',0),'accuracy':f('cur_accuracy',0),'resistance':f('cur_resistance',0),'combo_speed':f('cur_combo_speed',0),'mana_gen':f('cur_mana_gen',0),'skill_recovery':f('cur_skill_recovery',0),'skill_speed':f('cur_skill_speed',0)}
                self.sendj(recovery_balance_analysis(qs.get('name',[''])[0],levels(),f('duration',120),f('boss',1320),f('boss_res',0),f('boss_hp',0),f('boss_atk',0),qs.get('element',['Neutre'])[0],cur)); return
            if p.path=='/api/rank':
                rr=qs.get('rarity',['Toutes'])[0]; role=qs.get('role',['Tous'])[0]; mode=qs.get('mode',['box'])[0]; support_mode=qs.get('support_mode',['box'])[0]; out=[]
                duration=f('duration',120); bd=f('boss',1320); br=f('boss_res',0); bhp=f('boss_hp',0); batk=f('boss_atk',0); elem=qs.get('element',['Neutre'])[0]
                supports=[]
                for k in ('support1','support2','support3','support4'):
                    sn=qs.get(k,['Aucun'])[0]
                    if sn and sn!='Aucun' and sn not in supports: supports.append(sn)
                # Les supports, le boss et la durée sont fixes pour tout le classement :
                # prépare leur timeline UNE fois, puis réutilise-la pour chaque carry.
                # Avant v10.40, cette partie était recalculée jusqu'à ~222 fois.
                prepared_team=None
                if supports:
                    raw=[]; pi=[]
                    for sn in supports:
                        z=support_buff_schedule_preset(sn,duration,'none',elem,support_mode)
                        raw.extend(z.get('events',[]))
                        pi.append({'name':sn,'actions':z.get('actions',0),'buff_casts':sum(1 for e in z.get('events',[]) if e.get('kind')=='buff'),'debuff_attempts':sum(1 for e in z.get('events',[]) if e.get('kind')=='debuff_attempt'),'stats':z.get('stats',{}),'levels':z.get('levels',{}),'element':z.get('element','Neutre'),'element_matchup':z.get('element_matchup',{})})
                    resolved=[]
                    for e in sorted(raw,key=lambda x:(x['start'],x['source'],x['effect'])):
                        x=dict(e)
                        if x.get('kind')=='debuff_attempt':
                            active_res_down=max([r['value'] for r in resolved if r.get('kind')=='debuff' and r.get('effect')=='RES Down' and r['start']<=x['start']<r['end']] or [0.0])
                            resist_mod=num(x.get('element_debuff_delta'))-active_res_down
                            chance=final_debuff_pass_chance(num(x.get('accuracy')),br,resist_mod)
                            x['pass_chance']=chance
                            roll=deterministic_roll(f"supportdebuff|{x['source']}|{x['action']}|{x['effect']}|{x['start']:.6f}")
                            x['success']=roll<chance
                            if not x['success']: continue
                            x['kind']='debuff'
                        resolved.append(x)
                    grouped={}
                    for e in sorted(resolved,key=lambda x:(x['effect'],x['source'],x['start'])):
                        k=(e['effect'],e['source']); a=grouped.setdefault(k,[])
                        if a and a[-1]['end']>e['start']: a[-1]['end']=e['start']
                        a.append(dict(e))
                    pe=[e for arr in grouped.values() for e in arr if e['end']>e['start']]
                    pe.sort(key=lambda x:(x['start'],x['source'],x['effect']))
                    for si in pi:
                        si['debuff_successes']=sum(1 for e in pe if e.get('kind')=='debuff' and e.get('source')==si['name'])
                    prepared_team={'events':pe,'support_info':pi}
                for h in q('SELECT name,faction,rarity,role,element FROM heroes WHERE name IS NOT NULL'):
                    if h['name'] in supports: continue
                    if rr!='Toutes' and h.get('rarity')!=rr:continue
                    if role!='Tous' and h.get('role')!=role:continue
                    if mode=='box' and not has_saved_profile(h['name']): continue
                    bld,st,lv,_,_=combat_preset_for(h['name'],mode)
                    r=simulate_combat(h['name'],lv,duration,bd,br,bhp,batk,elem,**bld,team_supports=supports,prepared_team=prepared_team)
                    if r:out.append({**h,'element':r.get('hero_element') or h.get('element') or 'Neutre','dps':r['dps'],'total_damage':r['total_damage'],'actions':r['actions'],'final_stats':r['final_stats'],'damage_by':r['damage_by']})
                out.sort(key=lambda x:x['dps'],reverse=True); self.sendj(out);return
            self.sendj({'error':'Not found'},404)
        except Exception as e:self.sendj({'error':str(e)},500)
    def do_POST(self):
        p=urlparse(self.path)
        try:
            if p.path=='/api/game-import/snapshot':
                self.sendj(start_game_diff_snapshot()); return
            if p.path=='/api/game-import/apply':
                self.sendj(apply_game_import()); return
            if p.path=='/api/game-import/save-mappings':
                n=int(self.headers.get('Content-Length','0') or 0); data=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
                self.sendj({'ok':True,'saved':save_config_mappings(data.get('mappings') or [])}); return
            if p.path=='/api/game-import/import-hall':
                r=import_arena_hall_only()
                self.sendj(r,200 if r.get('ok') else 400); return
            if p.path=='/api/game-import/import-box':
                d=decode_local_box()
                if not d.get('ok'): self.sendj(d,400); return
                self.sendj({'ok':True,**persist_decoded_box(d)}); return
            if p.path=='/api/profile/use-box':
                nbytes=int(self.headers.get('Content-Length','0') or 0)
                data=json.loads(self.rfile.read(nbytes).decode('utf-8') or '{}')
                name=str(data.get('name') or '').strip()
                r=apply_box_profile(name)
                self.sendj(r,200 if r.get('ok') else 400); return
            if p.path=='/api/aoe-import-one':
                nbytes=int(self.headers.get('Content-Length','0') or 0); data=json.loads(self.rfile.read(nbytes).decode('utf-8') or '{}')
                name=str(data.get('name') or '').strip()
                if not name:self.sendj({'error':'Héros manquant'},400); return
                try:
                    d=_gg_extract_aoe_for_hero(name); saved=save_aoe_targets(name,d.get('targets') or {},'ggnoluck')
                    self.sendj({'ok':True,'hero':name,'saved_actions':saved,'targets':d.get('targets') or {},'url':d.get('url'),'unresolved':d.get('unresolved') or []})
                except Exception as e:
                    self.sendj({'ok':False,'hero':name,'error':str(e)},400)
                return
            if p.path=='/api/aoe-import-all':
                self.sendj(import_ggnoluck_aoe_all()); return
            if p.path=='/api/aoe-targets':
                nbytes=int(self.headers.get('Content-Length','0') or 0); data=json.loads(self.rfile.read(nbytes).decode('utf-8') or '{}')
                name=str(data.get('name') or '').strip()
                if not name:self.sendj({'error':'Héros manquant'},400); return
                saved=save_aoe_targets(name,data.get('targets') or {},'manual')
                self.sendj({'ok':True,'saved':saved}); return
            if p.path=='/api/profile':
                n=int(self.headers.get('Content-Length','0') or 0); data=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
                if not save_profile(data): self.sendj({'error':'Nom héros manquant'},400); return
                pr=profile_for(data.get('name')); self.sendj({'ok':True,'profile':pr,'final_stats':profile_stats(data.get('name'),pr)}); return
            self.sendj({'error':'Not found'},404)
        except Exception as e:self.sendj({'error':str(e)},500)
    def log_message(self,fmt,*args): pass
if __name__=='__main__':
    print("Smishie's Lab v%s — http://127.0.0.1:8501"%_app_version())
    print('Garde cette fenêtre ouverte pendant utilisation.')
    threading.Timer(1.0,lambda:webbrowser.open(f'http://{HOST}:{PORT}')).start()
    try:ThreadingHTTPServer((HOST,PORT),H).serve_forever()
    except OSError as e:
        print('Port 8501 occupé. Ferme une ancienne fenêtre Smishie/Invokers Lab puis relance.',e);input('Entrée pour fermer...')
