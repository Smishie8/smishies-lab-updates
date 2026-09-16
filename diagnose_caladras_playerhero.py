import json, os, struct

CFG=17193373869346061
IIDS={908,3941,11782}

def root():
    up=os.environ.get("USERPROFILE")
    if up:
        p=os.path.join(up,"AppData","LocalLow","Hit_Zone","Invokers","aggregate_snapshots","PlayerHeroesModel.dat")
        if os.path.isfile(p): return p
    la=os.environ.get("LOCALAPPDATA")
    if la:
        p=os.path.join(os.path.dirname(la),"LocalLow","Hit_Zone","Invokers","aggregate_snapshots","PlayerHeroesModel.dat")
        if os.path.isfile(p): return p
    return None

def mp_vt(data,p):
    mc=data[p]; p+=1
    if mc==255:
        mc=struct.unpack_from("<i",data,p)[0]; p+=4
    lens=[]
    for _ in range(mc):
        b=data[p]; p+=1
        if b==255:
            ln=struct.unpack_from("<i",data,p)[0]; p+=4
        else: ln=b
        lens.append(ln)
    spans=[]
    q=p
    for ln in lens:
        spans.append((q,q+ln)); q+=ln
    return mc,lens,spans,q

def i32(data,sp):
    a,b=sp
    return struct.unpack_from("<i",data,a)[0] if b-a>=4 else None
def i64(data,sp):
    a,b=sp
    return struct.unpack_from("<q",data,a)[0] if b-a>=8 else None

def decode_i32_list(raw):
    if len(raw)<4:return None
    n=struct.unpack_from("<i",raw,0)[0]
    if n<0 or n>100 or 4+4*n>len(raw): return None
    return [struct.unpack_from("<i",raw,4+4*i)[0] for i in range(n)]

def decode_pairs(raw):
    if len(raw)<4:return None
    n=struct.unpack_from("<i",raw,0)[0]
    if n<0 or n>32 or 4+8*n>len(raw): return None
    vals=[]
    for i in range(n):
        a,b=struct.unpack_from("<ii",raw,4+8*i)
        vals.append([a,b])
    return vals

def analyze(raw):
    out={"size":len(raw),"hex":raw.hex()}
    if len(raw)>=4:
        out["first_i32"]=struct.unpack_from("<i",raw,0)[0]
    li=decode_i32_list(raw)
    if li is not None: out["i32_list"]=li
    pr=decode_pairs(raw)
    if pr is not None: out["i32_pairs"]=pr
    # sliding aligned i32s for small/interesting values
    vals=[]
    for off in range(0,len(raw)-3,4):
        v=struct.unpack_from("<i",raw,off)[0]
        if -10<=v<=100000:
            vals.append({"off":off,"v":v})
    if vals: out["small_i32_aligned"]=vals
    return out

def main():
    fp=root()
    if not fp:
        print(json.dumps({"ok":False,"error":"PlayerHeroesModel.dat introuvable"},ensure_ascii=False,indent=2)); return
    data=open(fp,"rb").read()
    mc,lens,spans,end=mp_vt(data,25)
    s,e=spans[1]
    count=struct.unpack_from("<i",data,s)[0]
    p=s+4
    hits=[]
    for _ in range(count):
        dict_id=struct.unpack_from("<i",data,p)[0]; p+=4
        hmc,hlens,hsp,hend=mp_vt(data,p)
        iid=i32(data,hsp[0]) if len(hsp)>0 else None
        cfg=i64(data,hsp[1]) if len(hsp)>1 else None
        if cfg==CFG or iid in IIDS:
            members=[]
            for idx,sp in enumerate(hsp):
                a,b=sp
                members.append({"index":idx,**analyze(data[a:b])})
            hits.append({"dictionary_id":dict_id,"inventory_id":iid,"config_id":cfg,
                         "member_count":hmc,"member_lengths":hlens,"members":members})
        p=hend
    out={"ok":True,"file":fp,"hero":"Caladras","config_id":CFG,"matches":hits,
         "read_only":True,"writes_to_game_files":False,
         "note":"Dump autonome de tous les membres PlayerHero; aucun fichier du jeu n'est modifié."}
    outp=os.path.abspath("caladras_playerhero_members.json")
    open(outp,"w",encoding="utf-8").write(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps(out,ensure_ascii=False,indent=2))
    print("\nRapport écrit dans:",outp)

if __name__=="__main__": main()
