import json, os, struct
import server as app

CFG=17193373869346061
IIDS={908,3941,11782}

def analyze_member(data, span):
    a,b=span
    raw=data[a:b]
    out={"start":a,"end":b,"size":b-a,"hex":raw.hex()}
    if len(raw)>=1:
        out["u8"]=raw[0]
    if len(raw)>=4:
        try: out["i32"]=struct.unpack_from("<i",raw,0)[0]
        except Exception: pass
    if len(raw)>=8:
        try: out["i64"]=struct.unpack_from("<q",raw,0)[0]
        except Exception: pass
    try:
        d=app._mp_dict_i32_i32(data,span)
        if d: out["dict_i32_i32"]=d
    except Exception:
        pass
    try:
        li=app._mp_list_i32(data,span)
        if li: out["list_i32"]=li
    except Exception:
        pass
    try:
        sk=app._mp_upgradeable_skills(data,span)
        if sk: out["upgradeable_skills"]=sk
    except Exception:
        pass
    vals=[]
    for off in range(0,len(raw)-3,4):
        v=struct.unpack_from("<i",raw,off)[0]
        if -10<=v<=100000:
            vals.append({"off":off,"v":v})
    if vals: out["small_i32_aligned"]=vals
    return out

def main():
    fp=app._find_aggregate_snapshot("PlayerHeroesModel.dat")
    if not fp:
        print(json.dumps({"ok":False,"error":"PlayerHeroesModel.dat introuvable"},ensure_ascii=False,indent=2))
        return

    with app._game_ro_open(fp,"rb") as f:
        data=f.read()

    mc,lens,root,end=app._mp_vt(data,25)
    if len(root)<2:
        raise RuntimeError("PlayerHeroesModel incomplet")

    s,e=root[1]
    count=struct.unpack_from("<i",data,s)[0]
    p=s+4
    hits=[]

    for _ in range(count):
        dict_id=struct.unpack_from("<i",data,p)[0]
        p+=4
        hmc,hlens,hv,hend=app._mp_vt(data,p)
        iid=app._mp_i32(data,hv[0]) if len(hv)>0 else None
        cfg=app._mp_i64(data,hv[1]) if len(hv)>1 else None

        if cfg==CFG or iid in IIDS:
            members=[]
            for idx,span in enumerate(hv):
                m={"index":idx,**analyze_member(data,span)}
                if idx==10:
                    m["expected_role"]="SkillLevels"
                elif idx==11:
                    m["expected_role"]="RelicsBySlot"
                elif idx==12:
                    m["expected_role"]="AccessoriesBySlot"
                elif idx==15:
                    m["expected_role"]="AwakeLevel"
                elif idx==16:
                    m["expected_role"]="AwakeNodeIds"
                members.append(m)
            hits.append({
                "dictionary_id":dict_id,
                "inventory_id":iid,
                "config_id":cfg,
                "member_count":hmc,
                "member_lengths":hlens,
                "members":members
            })
        p=hend

    out={
        "ok":True,
        "file":fp,
        "hero":"Caladras",
        "config_id":CFG,
        "matches":hits,
        "read_only":True,
        "writes_to_game_files":False,
        "note":"Diagnostic utilisant exactement le parseur MemoryPack de server.py."
    }

    outp=os.path.abspath("caladras_playerhero_members.json")
    with open(outp,"w",encoding="utf-8") as f:
        json.dump(out,f,ensure_ascii=False,indent=2)

    print(json.dumps(out,ensure_ascii=False,indent=2))
    print("\nRapport écrit dans:",outp)

if __name__=="__main__":
    main()
