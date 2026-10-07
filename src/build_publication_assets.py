"""Build publication-ready tables and figures from frozen result packages."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


from src.analyze_heldout_automated import ROOT, read_json, sha256


OUTPUT = ROOT / "results" / "publication_assets_v1.0"
EXPERIMENT_FREEZE = ROOT / "freezes" / "uit-rag-freeze-v1.1-20260819" / "experiment_freeze.json"
AUTO_FREEZE = ROOT / "freezes" / "uit-automated-heldout-analysis-v1.0" / "automated_heldout_analysis_freeze.json"
STATS_FREEZE = ROOT / "freezes" / "uit-paired-statistical-analysis-v1.0" / "paired_statistical_analysis_freeze.json"
ERROR_FREEZE = ROOT / "freezes" / "uit-systematic-error-analysis-v1.0" / "systematic_error_analysis_freeze.json"
AUTO_JSON = ROOT / "results" / "automated_evaluation_v1.0" / "heldout_automated_metrics_v1.0.json"
STATS_JSON = ROOT / "results" / "paired_statistical_analysis_v1.0" / "paired_statistical_results_v1.0.json"
ERROR_JSON = ROOT / "results" / "systematic_error_analysis_v1.0" / "systematic_error_analysis_v1.0.json"
COLORS = {"EN": "#0072B2", "MY": "#D55E00", "MIX": "#009E73"}


def verify_freezes() -> dict[str, str]:
    paths = {"experiment": EXPERIMENT_FREEZE, "automated": AUTO_FREEZE, "statistics": STATS_FREEZE, "error_analysis": ERROR_FREEZE}
    for path in paths.values():
        read_json(path)
    automated = read_json(AUTO_FREEZE)
    statistics = read_json(STATS_FREEZE)
    errors = read_json(ERROR_FREEZE)
    for freeze in (automated, statistics, errors):
        for item in freeze.get("outputs", freeze.get("artifacts", {})).values():
            if "path" in item and sha256(ROOT / item["path"]) != item["sha256"]:
                raise ValueError(f"Frozen result changed: {item['path']}")
    return {name: sha256(path) for name, path in paths.items()}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def table_rows(exp: dict, auto: dict, stats: dict, errors: dict) -> dict[str, list[dict[str, Any]]]:
    benchmark = exp["benchmark"]
    split = benchmark["split_definition"]
    tables = {}
    tables["table1_dataset_split.csv"] = [
        {"Item": "Retrieval chunks", "Total": exp["chunks"]["count"], "Development": "", "Held-out": ""},
        {"Item": "Semantic intents", "Total": benchmark["semantic_intents"], "Development": 5, "Held-out": split["heldout_intents"]},
        {"Item": "Question variants", "Total": benchmark["question_variants"], "Development": split["development_questions"], "Held-out": split["heldout_questions"]},
        {"Item": "Answerable variants", "Total": benchmark["answerable"], "Development": 9, "Held-out": split["heldout_answerable"]},
        {"Item": "Unanswerable variants", "Total": benchmark["unanswerable"], "Development": 6, "Held-out": split["heldout_unanswerable"]},
        {"Item": "EN / MY / MIX", "Total": "79 / 79 / 79", "Development": "5 / 5 / 5", "Held-out": "74 / 74 / 74"},
    ]
    g = exp["generation"]
    tables["table2_experimental_configuration.csv"] = [
        {"Component": "Corpus/chunks", "Frozen setting": f"{exp['chunks']['version']}; {exp['chunks']['count']} chunks"},
        {"Component": "Embedding", "Frozen setting": exp["retrieval"]["embedding_model"]},
        {"Component": "Search", "Frozen setting": f"{exp['retrieval']['similarity_metric']}; Top-k={exp['retrieval']['top_k']}"},
        {"Component": "Generator", "Frozen setting": g["ollama_model"]},
        {"Component": "Prompt/parser", "Frozen setting": f"{g['prompt_version']} / {g['parser_version']}"},
        {"Component": "Resource profile", "Frozen setting": f"{g['resource_profile_version']}; num_ctx={g['settings']['num_ctx']}; num_predict={g['settings']['num_predict']}"},
        {"Component": "Sampling", "Frozen setting": f"temperature={g['settings']['temperature']}; top_p={g['settings']['top_p']}; top_k={g['settings']['top_k']}; seed={g['settings']['seed']}"},
    ]
    retrieval = auto["retrieval"]["answerable_metrics_by_language"]
    tables["table3_retrieval_performance.csv"] = [{"Language": lang, **{k: v for k, v in retrieval[lang].items()}} for lang in ("EN", "MY", "MIX")]
    tables["table3_retrieval_performance.csv"].insert(0, {"Language": "Overall", **auto["retrieval"]["answerable_metrics"]})
    tables["table4_decision_performance.csv"] = []
    for lang in ("EN", "MY", "MIX"):
        m = auto["decision_by_language"][lang]
        tables["table4_decision_performance.csv"].append({"Language": lang, "Accuracy": m["decision_accuracy"]["value"], "Abstention precision": m["abstention_precision"]["value"], "Abstention recall": m["abstention_recall"]["value"], "Abstention F1": m["abstention_f1"]["value"]})
    tables["table5_paired_tests.csv"] = [{k: row[k] for k in ("outcome", "paired_intents", "statistic", "p_value", "proportion_range_effect_size", "significant_at_0_05")} for row in stats["omnibus"]]
    c = auto["contract_and_reliability"]
    tables["table6_contract_reliability.csv"] = [
        {"Metric": "Contract valid", "Numerator": c["contract_valid"]["numerator"], "Denominator": c["contract_valid"]["denominator"], "Value": c["contract_valid"]["value"]},
        {"Metric": "Abstention wording compliant", "Numerator": c["abstention_wording_compliance"]["numerator"], "Denominator": c["abstention_wording_compliance"]["denominator"], "Value": c["abstention_wording_compliance"]["value"]},
        {"Metric": "Mechanically validated ANSWER", "Numerator": c["mechanically_validated_answer_outputs"]["numerator"], "Denominator": c["mechanically_validated_answer_outputs"]["denominator"], "Value": c["mechanically_validated_answer_outputs"]["value"]},
        {"Metric": "Infrastructure event recorded", "Numerator": c["infrastructure_error"]["numerator"], "Denominator": c["infrastructure_error"]["denominator"], "Value": c["infrastructure_error"]["value"]},
    ]
    tables["table7_structural_errors.csv"] = [{"Structural flag": key.replace("_", " ").title(), "Count": value, "Denominator": 222} for key, value in errors["flag_counts"].items()]
    return tables


def _svg_text(x, y, text, anchor="middle", size=14, weight="normal"):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial,sans-serif" font-size="{size}" font-weight="{weight}" fill="#222">{text}</text>'


def save_svg(stem: Path, svg: str) -> None:
    stem.with_suffix(".svg").write_text(svg, encoding="utf-8")


def bar_chart(values: dict[str, list[float]], ylabel: str, title: str, path: Path, ylim=(0, 1), errors=None) -> None:
    width, height = 720, 420; left, top, plot_w, plot_h = 90, 65, 590, 290
    languages=list(values); grouped=len(next(iter(values.values())))>1
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>',_svg_text(25,30,title,"start",18,"bold")]
    for tick in range(5):
        value=ylim[0]+(ylim[1]-ylim[0])*tick/4; y=top+plot_h-(value-ylim[0])/(ylim[1]-ylim[0])*plot_h
        svg += [f'<line x1="{left}" y1="{y}" x2="{left+plot_w}" y2="{y}" stroke="#ddd"/>',_svg_text(left-8,y+5,f"{value:.0%}","end",11)]
    labels=["Hit@1","Hit@3","Hit@5"] if grouped else languages
    if grouped:
        for j,label in enumerate(labels):
            cx=left+(j+.5)*plot_w/3; svg.append(_svg_text(cx,top+plot_h+28,label,size=12))
            for i,lang in enumerate(languages):
                v=values[lang][j]; bw=48; x=cx+(i-1)*55-bw/2; y=top+plot_h-(v-ylim[0])/(ylim[1]-ylim[0])*plot_h
                svg.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{top+plot_h-y}" fill="{COLORS[lang]}"/>')
        for i,lang in enumerate(languages): svg += [f'<rect x="{left+370+i*72}" y="38" width="13" height="13" fill="{COLORS[lang]}"/>',_svg_text(left+388+i*72,49,lang,"start",11)]
    else:
        for i,lang in enumerate(languages):
            v=values[lang][0]; cx=left+(i+.5)*plot_w/3; bw=85; y=top+plot_h-(v-ylim[0])/(ylim[1]-ylim[0])*plot_h
            svg += [f'<rect x="{cx-bw/2}" y="{y}" width="{bw}" height="{top+plot_h-y}" fill="{COLORS[lang]}"/>',_svg_text(cx,top+plot_h+28,lang,size=12),_svg_text(cx,y-10,f"{v:.1%}",size=11)]
            if errors:
                low=v-errors[0][i]; high=v+errors[1][i]; yl=top+plot_h-(low-ylim[0])/(ylim[1]-ylim[0])*plot_h; yh=top+plot_h-(high-ylim[0])/(ylim[1]-ylim[0])*plot_h
                svg += [f'<line x1="{cx}" y1="{yl}" x2="{cx}" y2="{yh}" stroke="#222" stroke-width="2"/>',f'<line x1="{cx-10}" y1="{yl}" x2="{cx+10}" y2="{yl}" stroke="#222"/>',f'<line x1="{cx-10}" y1="{yh}" x2="{cx+10}" y2="{yh}" stroke="#222"/>']
    svg += [f'<text x="22" y="{top+plot_h/2}" text-anchor="middle" transform="rotate(-90 22 {top+plot_h/2})" font-family="Arial,sans-serif" font-size="12" fill="#222">{ylabel}</text>','</svg>']
    save_svg(path,"".join(svg))


def pipeline_figure(path: Path) -> None:
    labels=["UIT public source","148 frozen chunks","E5 + FAISS Top-5","Gemma 3 decision","Frozen analysis"]; svg=['<svg xmlns="http://www.w3.org/2000/svg" width="900" height="260" viewBox="0 0 900 260"><rect width="100%" height="100%" fill="white"/>',_svg_text(25,35,"Frozen experimental and evaluation pipeline","start",18,"bold")]
    for i,label in enumerate(labels):
        x=25+i*175; svg += [f'<rect x="{x}" y="100" width="145" height="65" rx="8" fill="white" stroke="#555"/>',_svg_text(x+72.5,138,label,size=12)]
        if i<4: svg.append(f'<path d="M{x+145} 132 H{x+170}" stroke="#555" marker-end="url(#a)"/>')
    svg.insert(1,'<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" fill="#555"/></marker></defs>'); svg.append('</svg>')
    save_svg(path,"".join(svg))


def run(output: Path = OUTPUT, overwrite: bool = False) -> dict[str, Any]:
    hashes=verify_freezes(); exp=read_json(EXPERIMENT_FREEZE); auto=read_json(AUTO_JSON); stats=read_json(STATS_JSON); errors=read_json(ERROR_JSON)
    if output.exists() and any(output.iterdir()) and not overwrite: raise FileExistsError(f"Publication assets already exist: {output}")
    tables_dir=output/"tables"; figures_dir=output/"figures"; tables_dir.mkdir(parents=True,exist_ok=True); figures_dir.mkdir(parents=True,exist_ok=True)
    tables=table_rows(exp,auto,stats,errors)
    for name,rows in tables.items(): write_csv(tables_dir/name,rows)
    retrieval=auto["retrieval"]["answerable_metrics_by_language"]
    pipeline_figure(figures_dir/"figure1_pipeline")
    bar_chart({l:[retrieval[l][k] for k in ("Hit@1","Hit@3","Hit@5")] for l in ("EN","MY","MIX")},"Answerable retrieval hit rate","Retrieval performance by language",figures_dir/"figure2_retrieval_by_language")
    desc={(r["outcome"],r["language"]):r for r in stats["descriptive"]}
    vals={l:[desc[("decision_correct",l)]["proportion"]] for l in ("EN","MY","MIX")}; errs=[[vals[l][0]-desc[("decision_correct",l)]["ci_95_lower"] for l in vals],[desc[("decision_correct",l)]["ci_95_upper"]-vals[l][0] for l in vals]]
    bar_chart(vals,"Decision accuracy","Structured decision accuracy (95% Wilson CI)",figures_dir/"figure3_decision_accuracy_ci",errors=errs)
    vals={l:[desc[("false_abstention",l)]["proportion"]] for l in ("EN","MY","MIX")}; errs=[[vals[l][0]-desc[("false_abstention",l)]["ci_95_lower"] for l in vals],[desc[("false_abstention",l)]["ci_95_upper"]-vals[l][0] for l in vals]]
    bar_chart(vals,"False-abstention rate","False abstention among answerable intents (95% Wilson CI)",figures_dir/"figure4_false_abstention_ci",ylim=(0,.65),errors=errs)
    labels=[k.replace("_"," ").title() for k in errors["flag_counts"]]; counts=list(errors["flag_counts"].values()); svg=['<svg xmlns="http://www.w3.org/2000/svg" width="760" height="430" viewBox="0 0 760 430"><rect width="100%" height="100%" fill="white"/>',_svg_text(25,30,"Structural error indicators","start",18,"bold")]
    for i,(label,v) in enumerate(zip(labels,counts)): y=70+i*65; svg += [_svg_text(260,y+20,label,"end",12),f'<rect x="275" y="{y}" width="{v*8}" height="32" fill="#0072B2"/>',_svg_text(285+v*8,y+21,str(v),"start",12)]
    svg += [_svg_text(500,410,"Records (overlapping categories)",size=12),'</svg>']; save_svg(figures_dir/"figure5_structural_errors","".join(svg))
    assets=[p for p in output.rglob("*") if p.is_file() and p.name != "publication_assets_manifest_v1.0.json"]
    manifest={"asset_version":"publication-assets-v1.0","source_freeze_hashes":hashes,"semantic_measures":"NOT_EVALUATED","tables":7,"figures":5,"artifacts":{str(p.relative_to(ROOT)):sha256(p) for p in assets}}
    (output/"publication_assets_manifest_v1.0.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--output",type=Path,default=OUTPUT); p.add_argument("--overwrite",action="store_true"); a=p.parse_args(); m=run(a.output,a.overwrite); print("publication tables = 7"); print("publication figures = 5"); print("semantic measures = NOT_EVALUATED")


if __name__ == "__main__": main()
