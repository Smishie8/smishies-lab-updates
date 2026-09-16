import argparse
import json
import os
import struct


def candidate_roots():
    roots = []
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        roots.append(os.path.join(userprofile, "AppData", "LocalLow", "Hit_Zone", "Invokers"))
    localapp = os.environ.get("LOCALAPPDATA")
    if localapp:
        roots.append(os.path.join(os.path.dirname(localapp), "LocalLow", "Hit_Zone", "Invokers"))
    seen = set()
    out = []
    for root in roots:
        root = os.path.abspath(root)
        key = os.path.normcase(root)
        if key not in seen:
            seen.add(key)
            out.append(root)
    return out


def find_snapshot_dirs():
    out = []
    for root in candidate_roots():
        d = os.path.join(root, "aggregate_snapshots")
        if os.path.isdir(d):
            out.append(d)
    return out


def hex_context(data, offset, needle_len, radius=48):
    a = max(0, offset - radius)
    b = min(len(data), offset + needle_len + radius)
    return {
        "offset": offset,
        "start": a,
        "end": b,
        "hex": data[a:b].hex(),
    }


def find_all(data, needle, limit=200):
    hits = []
    pos = 0
    while len(hits) < limit:
        idx = data.find(needle, pos)
        if idx < 0:
            break
        hits.append(idx)
        pos = idx + 1
    return hits


def scan_file(path, config_id, inventory_ids):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        return {"file": path, "error": str(e)}

    needles = [("config_id_i64", struct.pack("<q", int(config_id)))]
    for iid in inventory_ids:
        needles.append((f"inventory_id_{iid}_i32", struct.pack("<i", int(iid))))

    matches = {}
    for label, needle in needles:
        offsets = find_all(data, needle)
        if offsets:
            matches[label] = [hex_context(data, x, len(needle)) for x in offsets[:30]]

    if not matches:
        return None

    return {
        "file": path,
        "size": len(data),
        "matches": matches,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Read-only scanner for Invokers aggregate snapshots. Never writes game files."
    )
    ap.add_argument("--hero", default="Caladras")
    ap.add_argument("--config-id", type=int, default=17193373869346061)
    ap.add_argument(
        "--inventory-ids",
        default="908,3941,11782",
        help="comma-separated inventory IDs",
    )
    ap.add_argument("--out", default="hero_storage_scan.json")
    args = ap.parse_args()

    inventory_ids = [
        int(x.strip()) for x in args.inventory_ids.split(",") if x.strip()
    ]

    snapshot_dirs = find_snapshot_dirs()
    if not snapshot_dirs:
        result = {
            "ok": False,
            "hero": args.hero,
            "error": "aggregate_snapshots introuvable",
            "roots_checked": candidate_roots(),
            "read_only": True,
        }
    else:
        rows = []
        scanned = 0
        for snapdir in snapshot_dirs:
            for name in sorted(os.listdir(snapdir)):
                path = os.path.join(snapdir, name)
                if not os.path.isfile(path):
                    continue
                scanned += 1
                row = scan_file(path, args.config_id, inventory_ids)
                if row:
                    rows.append(row)

        result = {
            "ok": True,
            "hero": args.hero,
            "config_id": args.config_id,
            "inventory_ids": inventory_ids,
            "snapshot_dirs": snapshot_dirs,
            "files_scanned": scanned,
            "files_with_hits": len(rows),
            "results": rows,
            "read_only": True,
            "writes_to_game_files": False,
            "note": "Diagnostic autonome; aucun fichier du jeu ni invokers.db n'est modifié.",
        }

    out_path = os.path.abspath(args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\nRapport écrit dans:", out_path)


if __name__ == "__main__":
    main()
