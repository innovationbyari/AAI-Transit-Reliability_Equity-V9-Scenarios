"""Split the v9 Colab notebook into the modules the Streamlit app runs (transit_ai/*.py).

    python tools/build_from_notebook.py notebooks/Transit_Agentic_AI_Submission_v9.ipynb .

Every module runs in ONE shared namespace, in notebook order (see transit_ai/__init__.py), exactly like running the
notebook top to bottom. Only the cells the scenario dashboard needs are included: no Colab installs, no Gradio
dashboard, no evaluation (Section V), no gallery (Section F) and no ipywidgets orchestrator (Section O).
"""
import json
import pathlib
import re
import sys

NB = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
cells = json.load(open(NB, encoding="utf-8"))["cells"]


def src(i):
    return "".join(cells[i]["source"])


def title(i):
    return src(i).split("\n", 1)[0].replace("#@title", "").strip()


# (module, cells). Titles are checked below so a renumbered notebook fails loudly instead of loading the wrong code.
MODULES = [
    ("setup_llm", [6]),                       # SETUP 3 · live LLM client (templates when no key)
    ("foundations", [8, 9, 10, 12]),          # E1 · helpers, policy rules, synthetic network, scenario builder + presets
    ("vision", [14]),                         # CV · off on the server (USE_CV=false): sample counts
    ("data_inputs", [16, 17, 18]),            # A · DATA_MODE=sample on the server (no NJ Transit login)
    ("engine", [20]),                         # E2 · deterministic validation and scoring
    ("ethics", [22, 23, 24, 25]),             # C · ethics-training gate + rosters
    ("conflict_of_interest", [28, 29, 30]),   # D · conflict-of-interest gate + disclosures
    ("governance", [33]),                     # governance_check()
    ("case_store", [35, 36]),                 # E3 · case record, review, deadlines, outcomes, policy versions
    ("agents_workflow", [39, 41, 43, 45, 47, 49, 51, 53, 55, 57, 59]),   # B · typed agents (Section B sample case)
    ("outputs", [102]),                       # E4 · map, tables and charts
]
EXPECT = {6: "SETUP 3", 8: "E1", 12: "E1 · Scenario builder", 14: "CV", 16: "A1", 20: "E2", 25: "C · Rosters",
          33: "INTEGRATION · governance_check", 35: "E3", 36: "E3", 43: "B · Sample scenario", 45: "B · 3.", 49: "B · Vision Agent",
          102: "E4"}
for i, prefix in EXPECT.items():
    if not title(i).startswith(prefix):
        raise SystemExit(f"cell {i} is '{title(i)}', expected '{prefix}…': the notebook's cells moved, update MODULES")

# Server defaults that differ from the notebook (each can still be changed with an environment variable / secret).
OVERRIDES = {"SHOW_CV_PREVIEW": "False", "USE_CV": "False", "USE_MOBILITY_AID_CV": "False", "DATA_MODE": '"sample"',
             "USE_SLM": "False", "USE_LLM_ORGANIZER": "False"}
PARAM = re.compile(r'^(?P<name>[A-Z_][A-Z0-9_]*)\s*=\s*(?P<val>.+?)\s*#@param.*$')

BASEMAP = '''
def add_basemap(m):
    """CARTO Positron with the CARTO_API_KEY secret (free key: carto.com/basemaps/apikey); OpenStreetMap otherwise."""
    key = read_secret("CARTO_API_KEY")
    if key:
        folium.TileLayer(
            tiles="https://basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}{r}.png?key=" + key,
            attr='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            name="CARTO Positron", max_zoom=20, subdomains="abcd").add_to(m)
    else:
        folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
'''


def transform(code, cell_no):
    out = []
    for line in code.split("\n"):
        if line.lstrip().startswith(("!", "%")):          # Colab shell magics → requirements.txt
            out.append(" " * (len(line) - len(line.lstrip())) + "pass  # " + line.strip() + "   (handled by requirements.txt)")
            continue
        if line.startswith("#@title"):
            out.append("# " + "-" * 100 + f"\n# {line[len('#@title'):].strip()}   [notebook cell {cell_no}]\n# " + "-" * 100)
            continue
        m = PARAM.match(line)
        if m:
            name, val = m["name"], OVERRIDES.get(m["name"], m["val"])
            out.append(f'{name} = param("{name}", {val})  # notebook form field; override with an environment variable')
            continue
        out.append(line)
    code = "\n".join(out)
    code = code.replace("in Colab Secrets", "in the app secrets").replace("Colab Secrets", "app secrets")
    if cell_no == 102 and "CartoDB positron" in code:      # CARTO tiles now need a key; OpenStreetMap otherwise
        code = re.sub(r'tiles="CartoDB positron"', "tiles=None", code)
        code = code.replace("control_scale=True)", "control_scale=True)\n    add_basemap(m)", 1)
        code = BASEMAP + "\n\n" + code
    return code


HEADER = '''"""{title}

Generated from the notebook (cells {cells}) by tools/build_from_notebook.py. Do not edit by hand: edit the notebook
and rebuild. Modules run in ONE shared namespace, in the order in transit_ai/_modules.json, like the notebook.
"""
# ruff: noqa
'''

pkg = OUT / "transit_ai"
pkg.mkdir(parents=True, exist_ok=True)
for mod, idx in MODULES:
    body = "\n\n\n".join(transform(src(i), i) for i in idx)
    (pkg / f"{mod}.py").write_text(HEADER.format(title=title(idx[0]), cells=", ".join(map(str, idx))) + "\n" + body.rstrip() + "\n",
                                   encoding="utf-8")
(pkg / "_modules.json").write_text(json.dumps([m for m, _ in MODULES]), encoding="utf-8")
print(f"wrote {len(MODULES)} modules to {pkg}")
