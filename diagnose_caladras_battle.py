import argparse
import json
import os
import struct


def game_root():
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        p = os.path.join(userprofile, "AppData", "LocalLow", "Hit_Zone", "Invokers")
        if os.path.isdir(p):
            return p
    localapp = os.environ.get("LOCALAPPDATA")
    if localapp:
        p = os.path.join(os.path.dirname(localapp), "LocalLow", "Hit_Zone", "Invokers")
        if os.path.isdir(p):
            return p
    return None


def find_all(data, needle, limit=1000):
    out = []
    pos = 0
    while len(out) < limit:
        i = data.find(needle, pos)
        if i < 0:
            break
        out.append(i)
        pos = i + 1
    return out


def i32_grid(data, start, end):
    rows = []
    a = max(0, start)
    b = min(len(data), end)
    # align to 4-byte boundary only for readability; raw offset retained
    p = a
    while p + 4 <= b:
        raw = data[p:p+4]
        rows.append({
            "offset": p,
            "hex": raw.hex(),
            "i32": struct.unpack("<i", raw)[0],
            "u32": struct.unpack("<I", raw)[0],
        })
        p += 4
    return rows


def nearby_pairs(data, iid, cfg, radius=192):
    iid_b = struct.pack("<i", iid)
    cfg_b = struct.pack("<q", cfg)
    iid_hits = find_all(data, iid_b)
    cfg_hits = find_all(data, cfg_b)
    pairs = []
    for io in iid_hits:
        nearest = None
        best = None
        for co in cfg_hits:
            d = abs(co - io)
            if d <= radius and (best is None or d < best):
                best = d
                nearest = co
        if nearest is not None:
            a = max(0, min(io, nearest) - radius)
            b = min(len(data), max(io + 4, nearest + 8) + radius)
            pairs.append({
                "inventory_offset": io,
                "config_offset": nearest,
                "distance": nearest - io,
                "start": a,
                "end": b,
                "hex": data[a:b].hex(),
                "i32_grid": i32_grid(data, a, b),
            })
    return pairs


def main():
    ap = argparse.ArgumentParser(description="Read-only targeted scan of PlayerBattleModel.dat")
    ap.add_argument("--hero", default="Caladras")
    ap.add_argument("--config-id", type=int, default=17193373869346061)
    ap.add_argument("--inventory-ids", default="908,3941,11782")
    ap.add_argument("--out", default="caladras_battle_scan.json")
    args = ap.parse_args()

    root = game_root()
    if not root:
        result = {"ok": False, "error": "Dossier Invokers introuvable", "read_only": True}
    else:
        fp = os.path.join(root, "aggregate_snapshots", "PlayerBattleModel.dat")
        if not os.path.isfile(fp):
            result = {"ok": False, "error": "PlayerBattleModel.dat introuvable", "file": fp, "read_only": True}
        else:
            with open(fp, "rb") as f:
                data = f.read()
            invs = [int(x.strip()) for x in args.inventory_ids.split(",") if x.strip()]
            rows = []
            for iid in invs:
                pairs = nearby_pairs(data, iid, args.config_id)
                rows.append({
                    "inventory_id": iid,
                    "pair_count": len(pairs),
                    "pairs": pairs[:80],
                })
            result = {
                "ok": True,
                "hero": args.hero,
                "file": fp,
                "size": len(data),
                "config_id": args.config_id,
                "inventory_ids": invs,
                "results": rows,
                "read_only": True,
                "writes_to_game_files": False,
                "note": "Ce script lit uniquement PlayerBattleModel.dat et écrit son rapport JSON local.",
            }

    out = os.path.abspath(args.out)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nRapport écrit dans:", out)


if __name__ == "__main__":
    main()
