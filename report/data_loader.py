"""data_loader.py — โหลดและแปลง results.json เป็น list of dict"""
import json, statistics, pathlib

SCENARIO_LABELS = {
    "small-comp":    "ไฟล์เล็ก บีบอัดได้ (20×50KB .txt)",
    "small-incomp":  "ไฟล์เล็ก บีบอัดไม่ได้ (20×50KB binary)",
    "medium-comp":   "ไฟล์กลาง บีบอัดได้ (4×5MB .csv)",
    "medium-incomp": "ไฟล์กลาง บีบอัดไม่ได้ (4×5MB binary)",
    "manysmall":     "ไฟล์เล็กจำนวนมาก (100×10KB)",
}
KEY_LABELS = {
    "RSA-2048":   "RSA-2048 (มาตรฐานทั่วไป)",
    "RSA-4096":   "RSA-4096 (ความปลอดภัยสูง)",
    "Curve25519": "Curve25519 ECC (ยุคใหม่)",
}

def load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _best(lang_data: dict) -> tuple[str, float]:
    items = [(v, d["p50_mean"]) for v, d in lang_data.items() if d.get("p50_mean")]
    return min(items, key=lambda x: x[1], default=("n/a", 0.0))

def extract_rows(data: dict) -> list[dict]:
    rows = []
    for sc, keyspecs in data["scenarios"].items():
        for alg, langs in keyspecs.items():
            gv, gp = _best(langs.get("go",   {}))
            jv, jp = _best(langs.get("java", {}))
            if not gp or not jp:
                continue
            diff = abs(gp - jp) / ((gp + jp) / 2) * 100
            if diff <= 5:
                winner, speedup = "TIE", 1.0
            elif gp < jp:
                winner, speedup = "GO", round(jp / gp, 2)
            else:
                winner, speedup = "JAVA", round(gp / jp, 2)
            rows.append({
                "scenario": sc, "pub_alg": alg,
                "go_variant": gv, "java_variant": jv,
                "go_p50": round(gp, 3), "java_p50": round(jp, 3),
                "speedup": speedup, "diff_pct": round(diff, 1),
                "winner": winner,
                "sc_label":  SCENARIO_LABELS.get(sc, sc),
                "key_label": KEY_LABELS.get(alg, alg),
            })
    return rows

def extract_variant_matrix(data: dict) -> list[dict]:
    """
    คืน list ของทุก variant × ทุก scenario × ทุก key type
    เพื่อแสดงตาราง head-to-head ระหว่าง variant ของ Go และ Java
    """
    rows = []
    for sc, keyspecs in data["scenarios"].items():
        for alg, langs in keyspecs.items():
            go_variants  = {v: d for v, d in langs.get("go",   {}).items() if d.get("p50_mean")}
            java_variants = {v: d for v, d in langs.get("java", {}).items() if d.get("p50_mean")}
            if not go_variants or not java_variants:
                continue
            for gv, gd in go_variants.items():
                for jv, jd in java_variants.items():
                    gp = round(gd["p50_mean"], 3)
                    jp = round(jd["p50_mean"], 3)
                    diff = abs(gp - jp) / ((gp + jp) / 2) * 100 if (gp + jp) > 0 else 0
                    if diff <= 5:
                        winner, speedup = "TIE", 1.0
                    elif gp < jp:
                        winner, speedup = "GO", round(jp / gp, 2)
                    else:
                        winner, speedup = "JAVA", round(gp / jp, 2)
                    rows.append({
                        "scenario": sc, "pub_alg": alg,
                        "go_variant": gv, "java_variant": jv,
                        "go_p50": gp, "java_p50": jp,
                        "speedup": speedup, "diff_pct": round(diff, 1),
                        "winner": winner,
                        "sc_label":  SCENARIO_LABELS.get(sc, sc),
                        "key_label": KEY_LABELS.get(alg, alg),
                    })
    return rows


def find_results_json() -> str | None:
    candidates = [
        pathlib.Path(__file__).parent / "results.json",
        pathlib.Path("/tmp/bench_results.json"),
        pathlib.Path("/tmp/bench-out/results.json"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None
