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
    รองรับทั้ง original format (scenarios[id][alg][lang][variant])
    และ extended format (scenarios[id][lang][variant] + pub_alg field)
    """
    rows = []
    for sc, sc_data in data["scenarios"].items():
        if not isinstance(sc_data, dict):
            continue

        # Extended format: scenarios[sc_id] = {pub_alg, go:{v:{}}, java:{v:{}}}
        if "pub_alg" in sc_data:
            alg = sc_data.get("pub_alg", "RSA-2048")
            go_variants  = {v: d for v, d in sc_data.get("go",   {}).items() if d.get("p50_mean")}
            java_variants = {v: d for v, d in sc_data.get("java", {}).items() if d.get("p50_mean")}
            keyspecs = {alg: {"go": sc_data.get("go",{}), "java": sc_data.get("java",{})}}
        else:
            # Original format: scenarios[sc_id][alg][lang][variant]
            keyspecs = sc_data

        for alg_key, langs in keyspecs.items():
            if not isinstance(langs, dict):
                continue
            go_variants  = {v: d for v, d in langs.get("go",   {}).items() if isinstance(d, dict) and d.get("p50_mean")}
            java_variants = {v: d for v, d in langs.get("java", {}).items() if isinstance(d, dict) and d.get("p50_mean")}
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
                        "scenario": sc, "pub_alg": alg_key,
                        "go_variant": gv, "java_variant": jv,
                        "go_p50": gp, "java_p50": jp,
                        "speedup": speedup, "diff_pct": round(diff, 1),
                        "winner": winner,
                        "sc_label": SCENARIO_LABELS.get(sc, sc),
                        "key_label": KEY_LABELS.get(alg_key, alg_key),
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


def extract_extended_rows(data: dict) -> list[dict]:
    """
    Parse results_full.json / results_extended.json
    Format: scenarios[id] = {pub_alg, corpus, go:{variant:{...}}, java:{variant:{...}}}
    """
    rows = []
    for sc_id, sc_data in data.get("scenarios", {}).items():
        # รองรับทั้ง format เก่า (langs only) และ format ใหม่ (มี pub_alg field)
        if isinstance(sc_data, dict) and "pub_alg" in sc_data:
            # format ใหม่
            pub_alg = sc_data.get("pub_alg", "RSA-2048")
            go_variants   = {v: d for v, d in sc_data.get("go",   {}).items() if d.get("p50_mean")}
            java_variants = {v: d for v, d in sc_data.get("java", {}).items() if d.get("p50_mean")}
        else:
            # format เก่า (scenarios[id][lang][variant])
            pub_alg = "RSA-2048"
            go_variants   = {v: d for v, d in sc_data.get("go",   {}).items() if d.get("p50_mean")}
            java_variants = {v: d for v, d in sc_data.get("java", {}).items() if d.get("p50_mean")}

        if not go_variants or not java_variants:
            continue
        gv, gd = min(go_variants.items(),   key=lambda x: x[1]["p50_mean"])
        jv, jd = min(java_variants.items(), key=lambda x: x[1]["p50_mean"])
        gp = round(gd["p50_mean"], 3)
        jp = round(jd["p50_mean"], 3)
        gthr = gd.get("throughput_mean_mbs")
        jthr = jd.get("throughput_mean_mbs")
        diff = abs(gp - jp) / ((gp + jp) / 2) * 100 if (gp + jp) > 0 else 0
        if diff <= 5:
            winner, speedup = "TIE", 1.0
        elif gp < jp:
            winner, speedup = "GO", round(jp / gp, 2)
        else:
            winner, speedup = "JAVA", round(gp / jp, 2)

        # all variants for the scenario
        all_go   = {v: round(d["p50_mean"],3) for v,d in go_variants.items()}
        all_java = {v: round(d["p50_mean"],3) for v,d in java_variants.items()}

        rows.append({
            "sc_id": sc_id,
            "pub_alg": pub_alg,
            "corpus": sc_data.get("corpus", ""),
            "go_variant": gv, "java_variant": jv,
            "go_p50": gp, "java_p50": jp,
            "go_thr": gthr, "java_thr": jthr,
            "speedup": speedup, "diff_pct": round(diff, 1),
            "winner": winner,
            "all_go":   all_go,
            "all_java": all_java,
        })
    return rows
