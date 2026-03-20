#!/usr/bin/env python3
import os, re, sys, markdown2, subprocess, datetime, shutil
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
import pandas as pd

# --- 1. INITIALIZATION ---
def setup():
    base = Path.home() / ".notes"
    notes, data = base / "notes", base / "datasets"
    notes.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    return {"root": base, "notes": notes, "datasets": data}

config = setup()
app = FastAPI(title="Note & Data Hub")

# --- 2. CORE LOGIC ---
def parse_note(f: Path):
    if not f.exists(): return {"title": f.stem, "tags": []}, ""
    content = f.read_text(encoding='utf-8')
    # Match YAML-style frontmatter
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
    if not match: return {"title": f.stem, "tags": []}, content
    meta = {}
    for line in match.group(1).strip().splitlines():
        if ':' in line:
            k, v = [item.strip() for item in line.split(':', 1)]
            if k.lower() == 'tags':
                v = [t.strip() for t in v.strip('[]').split(',') if t.strip()]
            meta[k.lower()] = v
    return meta, match.group(2).strip()

def save_note(f: Path, meta: dict, body: str):
    if isinstance(meta.get('tags'), list): 
        meta['tags'] = f"[{', '.join(meta['tags'])}]"
    head = "\n".join([f"{k}: {v}" for k, v in meta.items()])
    f.write_text(f"---\n{head}\n---\n\n{body}", encoding='utf-8')

def get_dataset_info(name: str, rows_limit: int = 3):
    f = config["datasets"] / name
    if not f.exists(): return None
    try:
        df = pd.read_csv(f) if f.suffix == '.csv' else pd.read_json(f)
        return {
            "id": name, "rows": len(df), "cols": list(df.columns),
            "preview": df.head(rows_limit).to_dict(orient="records")
        }
    except: return {"id": name, "rows": 0, "preview": []}

# --- 3. UI STYLES ---
COMMON_STYLE = """
<style>
    body { font-family: -apple-system, sans-serif; max-width: 900px; margin: auto; padding: 20px; background: #f8f9fa; color: #333; }
    .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
    .btn { padding: 8px 16px; border-radius: 4px; text-decoration: none; font-weight: bold; cursor: pointer; border: none; display: inline-block; font-size: 0.9em; }
    .btn-primary { background: #007bff; color: white; }
    .btn-success { background: #28a745; color: white; }
    .btn-danger { background: #dc3545; color: white; }
    .note-item { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #eee; }
    .preview-box { overflow-x: auto; max-height: 150px; border: 1px solid #eee; border-radius: 4px; margin-top: 10px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.75em; }
    th, td { border: 1px solid #eee; padding: 6px; text-align: left; white-space: nowrap; }
    th { background: #f9f9f9; color: #666; }
    input[type="text"], input[type="file"], textarea { padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
    form { display: flex; gap: 10px; align-items: center; }
</style>
"""

# --- 4. ROUTES ---
@app.get("/", response_class=HTMLResponse)
def web_home(q: Optional[str] = None):
    # Action Forms
    actions_html = f"""
    <div class='card'>
        <form action='/notes/create' method='post' style='margin-bottom:15px;'>
            <input type='text' name='filename' placeholder='New note title...' style='flex-grow:1' required>
            <button type='submit' class='btn btn-primary'>+ Create Note</button>
        </form>
        <form action='/datasets/import' method='post' enctype='multipart/form-data'>
            <input type='file' name='file' accept='.csv,.json' style='flex-grow:1' required>
            <button type='submit' class='btn btn-success'>📥 Upload Data</button>
        </form>
    </div>
    <form action='/' method='get' style='margin-bottom:20px;'>
        <input type='text' name='q' placeholder='Search notes, tags, or content...' style='flex-grow:1' value='{q or ""}'>
        <button type='submit' class='btn btn-primary'>Search</button>
    </form>"""

    # Library Content
    notes_raw = sorted([f.name for f in config["notes"].glob("*") if f.suffix in ['.md', '.txt']])
    datasets_raw = sorted([f.name for f in config["datasets"].glob("*") if f.suffix in ['.csv', '.json']])

    if q:
        q = q.lower()
        notes_raw = [n for n in notes_raw if q in n.lower() or q in (config["notes"]/n).read_text().lower()]
        datasets_raw = [d for d in datasets_raw if q in d.lower()]

    notes_html = "".join([f"<div class='note-item'><span>{n}</span><a href='/notes/{n}' class='btn btn-primary'>View</a></div>" for n in notes_raw])
    
    datasets_html = ""
    for d_name in datasets_raw:
        info = get_dataset_info(d_name)
        if not info: continue
        headers = "".join([f"<th>{k}</th>" for k in info['cols']])
        rows = "".join([f"<tr>{''.join([f'<td>{v}</td>' for v in r.values()])}</tr>" for r in info['preview']])
        datasets_html += f"""
        <div class='card'>
            <div style='display:flex;justify-content:space-between;align-items:center;'>
                <strong>📊 {d_name}</strong>
                <a href='/datasets/{d_name}/full' class='btn btn-primary' style='font-size:0.7em;'>Full View ↗</a>
            </div>
            <div class='preview-box'><table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div>
        </div>"""

    return f"<html><head>{COMMON_STYLE}</head><body><h1>🚀 Library</h1>{actions_html}<div class='card'><h2>📝 Notes</h2>{notes_html or '<p>No notes found.</p>'}</div><h2>📊 Data</h2>{datasets_html or '<p>No data found.</p>'}</body></html>"

@app.get("/notes/{filename}", response_class=HTMLResponse)
def view_note(filename: str, edit: bool = False):
    filepath = config["notes"] / filename
    if not filepath.exists(): raise HTTPException(404)
    meta, body = parse_note(filepath)
    if edit:
        content = f"<form action='/notes/{filename}/save' method='post'><textarea name='content' style='width:100%;height:450px;'>{body}</textarea><br><br><button type='submit' class='btn btn-primary'>Save</button></form>"
    else:
        content = f"<div class='card'>{markdown2.markdown(body)}</div><div style='display:flex;gap:10px;'><a href='?edit=true' class='btn btn-primary'>Edit</a><a href='/notes/{filename}/delete' class='btn btn-danger' onclick='return confirm(\"Delete?\")'>Delete</a></div>"
    return f"<html><head>{COMMON_STYLE}</head><body><a href='/'>← Back</a><h1>{filename}</h1>{content}</body></html>"

@app.get("/datasets/{filename}/full", response_class=HTMLResponse)
def view_full_dataset(filename: str):
    info = get_dataset_info(filename, rows_limit=1000) # Load up to 1000 rows
    if not info: raise HTTPException(404)
    headers = "".join([f"<th>{k}</th>" for k in info['cols']])
    rows = "".join([f"<tr>{''.join([f'<td>{v}</td>' for v in r.values()])}</tr>" for r in info['preview']])
    return f"<html><head>{COMMON_STYLE}</head><body style='max-width:100%'><a href='/'>← Back</a><h1>📊 {filename}</h1><div class='card' style='overflow:auto;'><table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table></div></body></html>"

@app.post("/notes/{filename}/save")
def save_note_route(filename: str, content: str = Form(...)):
    filepath = config["notes"] / filename
    meta, _ = parse_note(filepath)
    save_note(filepath, meta, content)
    return RedirectResponse(f"/notes/{filename}", status_code=303)

@app.get("/notes/{filename}/delete")
def delete_note_route(filename: str):
    (config["notes"] / filename).unlink(missing_ok=True)
    return RedirectResponse("/", status_code=303)

@app.post("/notes/create")
def create_note_route(filename: str = Form(...)):
    name = filename.replace(" ", "_") + ".md"
    save_note(config["notes"] / name, {"title": filename}, f"# {filename}")
    return RedirectResponse("/", status_code=303)

@app.post("/datasets/import")
async def import_dataset_route(file: UploadFile = File(...)):
    with (config["datasets"] / file.filename).open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return RedirectResponse("/", status_code=303)

if __name__ == "__main__":
    subprocess.run(["uvicorn", f"{Path(__file__).stem}:app", "--reload", "--port", "8080"])
