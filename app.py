import os
import base64
import requests
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from rdflib import Graph, Namespace, Literal, RDF, URIRef
from rdflib.namespace import DCTERMS
import logging

app = Flask(__name__)  # <-- Add this line
CORS(app)    

# === Logging setup ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("oslc_app")

# === In-memory requirements store ===
requirements_db = {}   # { "REQ-1": {id, title, description, type, state, links: []} }
next_req_num = 1       # auto-increment ID counter

# === Serve frontend ===
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/ado/workitems")
def list_ado_workitems():
    try:
        url = (f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_apis/wit/wiql?api-version={API_VER}")
        wiql = {
            "query": "SELECT [System.Id], [System.Title] FROM WorkItems WHERE [System.TeamProject] = @project ORDER BY [System.Id] DESC"
        }
        r = requests.post(url, headers=ADO_JSON_HDRS, json=wiql, timeout=30)
        r.raise_for_status()
        ids = [wi["id"] for wi in r.json().get("workItems", [])]
        items = []
        for wid in ids:
            try:
                wi = ado_get(wid)
                items.append({"id": wi["id"], "title": wi["fields"].get("System.Title", "")})
            except Exception as e:
                print(f"Failed to fetch work item {wid}: {e}")
                continue
        return jsonify(items)
    except Exception as e:
        print("Error in /api/ado/workitems:", e)
        return jsonify({"error": str(e)}), 500

# === Basic CRUD & linking for requirements ===
@app.route("/api/requirements", methods=["GET"])
def list_requirements():
    return jsonify(list(requirements_db.values()))

@app.route("/api/requirements", methods=["POST"])
def create_requirement():
    global next_req_num
    data = request.json or {}
    req_id = f"REQ-{next_req_num}"
    next_req_num += 1

    # Validate required fields
    if not data.get("title"):
        return jsonify({"error": "Title is required"}), 400

    requirement = {
        "id": req_id,
        "title": data.get("title", "").strip(),
        "description": data.get("description", "").strip(),
        "type": data.get("type", "Functional").strip(),
        "state": data.get("state", "New").strip(),
        "links": []
    }
    requirements_db[req_id] = requirement
    logger.info(f"Created requirement {req_id}: {requirement['title']}")
    return jsonify(requirement), 201

@app.route("/api/requirements/<req_id>", methods=["PUT"])
def update_requirement(req_id):
    req = requirements_db.get(req_id)
    if not req:
        return jsonify({"error": "Not found"}), 404

    data = request.json or {}
    for field in ("title", "description", "type", "state"):
        if field in data:
            req[field] = data[field].strip()
    logger.info(f"Updated requirement {req_id}")
    return jsonify(req)

@app.route("/api/requirements/<req_id>", methods=["DELETE"])
def delete_requirement(req_id):
    if req_id not in requirements_db:
        return jsonify({"error": "Not found"}), 404

    del requirements_db[req_id]
    # remove any incoming links
    for r in requirements_db.values():
        r["links"] = [l for l in r["links"] if l["target"] != req_id]
    return jsonify({"message": "Deleted"})

@app.route("/api/requirements/<req_id>/links", methods=["POST"])
def add_link(req_id):
    source = requirements_db.get(req_id)
    if not source:
        return jsonify({"error": "Source not found"}), 404

    data = request.json or {}
    target = data.get("target", "").strip()
    link_type = data.get("type", "satisfies").strip()

    if target not in requirements_db:
        return jsonify({"error": "Target not found"}), 404

    if any(l["target"] == target and l["type"] == link_type for l in source["links"]):
        return jsonify({"error": "Link exists"}), 400

    source["links"].append({"type": link_type, "target": target})
    return jsonify(source), 201

@app.route("/api/traceability", methods=["GET"])
def traceability():
    matrix = []
    for req in requirements_db.values():
        for link in req["links"]:
            matrix.append({
                "source": req["id"],
                "type": link["type"],
                "target": link["target"],
                "state": req.get("state", "New")  # Include state for traceability
            })
    return jsonify(matrix)

# === Azure DevOps & OSLC Configuration ===

AZDO_ORG = os.getenv("AZDO_ORG", "robjwoods")
AZDO_PROJECT = os.getenv("AZDO_PROJECT", "OSLC Test")
AZDO_PAT = os.getenv("AZDO_PAT", "")
API_VER      = os.getenv("AZDO_API_VER", "7.0").strip()

if not all([AZDO_ORG, AZDO_PROJECT, AZDO_PAT]):
    raise RuntimeError("Set AZDO_ORG, AZDO_PROJECT, AZDO_PAT env vars")

_auth = base64.b64encode(f":{AZDO_PAT}".encode()).decode()
ADO_JSON_HDRS  = {
    "Authorization": f"Basic {_auth}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}
ADO_PATCH_HDRS = {
    "Authorization": f"Basic {_auth}",
    "Content-Type": "application/json-patch+json",
    "Accept": "application/json"
}

OSLC = Namespace("http://open-services.net/ns/core#")
RM   = Namespace("http://open-services.net/ns/rm#")

def ado_url(item_id: int) -> str:
    return (f"https://dev.azure.com/{AZDO_ORG}/"
            f"{AZDO_PROJECT}/_apis/wit/workItems/{item_id}")

def ado_get(item_id: int) -> dict:
    url = f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_apis/wit/workitems/{item_id}?api-version={API_VER}"
    r = requests.get(url, headers=ADO_JSON_HDRS, timeout=30)
    r.raise_for_status()
    return r.json()

def ado_create(wi_type: str, title: str, desc: str, state: str = "New") -> dict:
    url = (f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/"
           f"_apis/wit/workitems/${wi_type}?api-version={API_VER}")
    patch = [
        {"op": "add", "path": "/fields/System.Title",       "value": title},
        {"op": "add", "path": "/fields/System.Description", "value": desc},
        {"op": "add", "path": "/fields/System.State",       "value": state}
    ]
    r = requests.post(url, headers=ADO_PATCH_HDRS, json=patch, timeout=30)
    r.raise_for_status()
    logger.info(f"Created Azure DevOps work item: {title}")
    return r.json()

def ado_update(item_id: int, title: str = None, desc: str = None, state: str = None) -> dict:
    url = f"https://dev.azure.com/{AZDO_ORG}/{AZDO_PROJECT}/_apis/wit/workitems/{item_id}?api-version={API_VER}"
    patch = []
    if title is not None:
        patch.append({"op": "add", "path": "/fields/System.Title",       "value": title})
    if desc  is not None:
        patch.append({"op": "add", "path": "/fields/System.Description", "value": desc})
    if state is not None:
        patch.append({"op": "add", "path": "/fields/System.State",       "value": state})
    if not patch:
        return ado_get(item_id)
    r = requests.patch(url, headers=ADO_PATCH_HDRS, json=patch, timeout=30)
    r.raise_for_status()
    logger.info(f"Updated Azure DevOps work item {item_id}")
    return r.json()

def import_oslc(g: Graph, default_type="User Story", base="http://example/oslc/req/"):
    subj2id = {}
    # 1st pass: create/update
    for subj in g.subjects(RDF.type, RM.Requirement):
        title = str(next(g.objects(subj, DCTERMS.title),       ""))
        desc  = str(next(g.objects(subj, DCTERMS.description), ""))
        state = str(next(g.objects(subj, OSLC.state), "New"))
        sid   = None
        try:
            sid = int(str(subj).rstrip("/").split("/")[-1])
        except:
            pass

        # Validate if work item already exists in requirements_db
        req_id = str(subj).replace(base, "")
        if req_id in requirements_db:
            # Update in-memory requirement
            req = requirements_db[req_id]
            req["title"] = title or req.get("title", "")
            req["description"] = desc or req.get("description", "")
            req["state"] = state or req.get("state", "New")
            logger.info(f"Updated in-memory requirement {req_id} from OSLC import")
        else:
            requirements_db[req_id] = {
                "id": req_id,
                "title": title,
                "description": desc,
                "type": default_type,
                "state": state,
                "links": []
            }
            logger.info(f"Imported new requirement {req_id} from OSLC")

        # Sync with Azure DevOps
        if sid:
            wi = ado_update(sid, title, desc, state)
        else:
            wi = ado_create(default_type, title, desc, state)
        subj2id[str(subj)] = wi["id"]

    # 2nd pass: add Related links
    for subj in subj2id:
        src_id = subj2id[subj]
        for tgt in g.objects(URIRef(subj), OSLC.relatedTo):
            tid = subj2id.get(str(tgt))
            if not tid:
                try:
                    tid = int(str(tgt).rstrip("/").split("/")[-1])
                except:
                    continue
            ado_add_link(src_id, "System.LinkTypes.Related", tid)

    return subj2id

# === OSLC endpoints ===
@app.route("/api/oslc/export")
def oslc_export():
    ids_q = request.args.get("ids", "")
    if not ids_q:
        return jsonify({"error": "Provide ?ids=1,2,3"}), 400
    try:
        ids = [int(i) for i in ids_q.split(",") if i.strip()]
    except:
        return jsonify({"error": "Invalid IDs"}), 400

    wis = [ado_get(i) for i in ids]
    graph = to_oslc(wis)
    rdf   = graph.serialize(format="application/rdf+xml")
    return Response(rdf, mimetype="application/rdf+xml")

@app.route("/api/oslc/import", methods=["POST"])
def oslc_import():
    if not request.data:
        return jsonify({"error": "Missing RDF/XML body"}), 400
    wi_type = request.args.get("type", "User Story")
    try:
        graph   = parse_oslc(request.data)
        mapping = import_oslc(graph, default_type=wi_type)
        return jsonify({"message": "Imported", "mapping": mapping}), 201
    except requests.HTTPError as e:
        return jsonify({
            "error":   "Azure DevOps API error",
            "details": str(e),
            "body":    getattr(e.response, "text", "")
        }), 502
    except Exception as e:
        return jsonify({"error": "Import failed", "details": str(e)}), 400

# === Run app ===
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
