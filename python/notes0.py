#!/usr/bin/env python3
import os
import re
import sys
import markdown2
import subprocess
import datetime
from pathlib import Path
from typing import Optional, List
from fastapi.responses import HTMLResponse, RedirectResponse

from fastapi import Form

# --- 1. INITIALIZATION & DEPENDENCIES ---

try:
    import pandas as pd
    from fastapi import FastAPI, HTTPException
except ImportError:
    print("Error: Missing dependencies. Please run: pip install fastapi pandas uvicorn")
    sys.exit(1)

def setup():
    """Initialize the notes application directory structure in ~/.notes."""
    base_dir = Path.home() / ".notes"
    notes_dir = base_dir / "notes"
    datasets_dir = base_dir / "datasets"

    notes_dir.mkdir(parents=True, exist_ok=True)
    datasets_dir.mkdir(parents=True, exist_ok=True)

    return {
        "root": base_dir,
        "notes": notes_dir,
        "datasets": datasets_dir
    }

config = setup()
app = FastAPI(title="Future Proof Notes & Data API")

# --- 2. CORE LOGIC ---

def parse_note(file_path: Path):
    """Parses Markdown frontmatter and body."""
    if not file_path.exists():
        return {'title': file_path.stem, 'tags': []}, ""
    
    content = file_path.read_text(encoding='utf-8')
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
    
    if not match:
        return {'title': file_path.stem, 'tags': []}, content

    header_raw, body = match.groups()
    metadata = {}
    for line in header_raw.strip().splitlines():
        if ':' in line:
            key, val = [item.strip() for item in line.split(':', 1)]
            if key.lower() == 'tags':
                val = val.strip('[]').split(',')
                val = [t.strip() for t in val if t.strip()]
            metadata[key.lower()] = val
    return metadata, body.strip()

def save_note(file_path: Path, meta: dict, body: str):
    """Writes metadata and body back to the file in markdown format."""
    meta_copy = meta.copy()
    if 'tags' in meta_copy and isinstance(meta_copy['tags'], list):
        meta_copy['tags'] = f"[{', '.join(meta_copy['tags'])}]"
        
    header_lines = [f"{k}: {v}" for k, v in meta_copy.items()]
    header_text = "\n".join(header_lines)
    new_content = f"---\n{header_text}\n---\n\n{body}"
    file_path.write_text(new_content, encoding='utf-8')

def get_dataset_metadata(filename: str):
    """Uses pandas to extract schema and stats from CSV/JSON datasets."""
    filepath = config["datasets"] / filename
    if not filepath.exists():
        return None
    
    stats = filepath.stat()
    ext = filepath.suffix.lower().replace('.', '')
    
    try:
        df = pd.read_csv(filepath) if ext == 'csv' else pd.read_json(filepath)
        row_count = len(df)
        schema = [{"name": col, "type": str(dtype)} for col, dtype in df.dtypes.items()]
    except Exception:
        row_count, schema = 0, []

    return {
        "id": filepath.stem,
        "title": filepath.stem.replace('_', ' ').title(),
        "created": datetime.datetime.fromtimestamp(stats.st_ctime).isoformat(),
        "modified": datetime.datetime.fromtimestamp(stats.st_mtime).isoformat(),
        "tags": ["dataset", ext],
        "format": ext,
        "rowCount": row_count,
        "schema": schema
    }

# --- 3. API ROUTES (WEB INTERFACE) ---

COMMON_STYLE = """
<style>
    body { font-family: sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #f4f4f9; }
    h1 { color: #333; border-bottom: 2px solid #ddd; padding-bottom: 10px; }
    .section { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 20px; }
    ul { list-style: none; padding: 0; }
    li { margin: 10px 0; border-bottom: 1px solid #eee; padding-bottom: 5px; }
    a { color: #007bff; text-decoration: none; font-weight: bold; }
    a:hover { text-decoration: underline; }
    .btn { display: inline-block; padding: 8px 15px; border-radius: 4px; color: white; text-decoration: none; border: none; cursor: pointer; }
    .btn-save { background: #28a745; }
    .btn-edit { background: #007bff; }
</style>
"""

@app.get("/", response_class=HTMLResponse)
def api_home():
    notes = [f.name for f in config["notes"].glob("*") if f.suffix in ['.md', '.txt']]
    datasets = [f.name for f in config["datasets"].glob("*.csv")]

    notes_html = "".join([f'<li><a href="/notes/{n}">{n}</a></li>' for n in sorted(notes)])
    data_html = "".join([f'<li><a href="/api/datasets/{d}/metadata">{d}</a></li>' for d in sorted(datasets)])

    return f"""
    <html><head>{COMMON_STYLE}</head><body>
        <h1>🚀 Future Proof Notes</h1>
        
        <!-- NEW: Quick Create Section -->
        <div class="section" style="background: #eef2f7; border: 1px dashed #0366d6;">
            <form action="/notes/create" method="post" style="display: flex; gap: 10px; align-items: center;">
                <input type="text" name="filename" placeholder="New note name (e.g., ideas.md)" 
                       style="flex-grow: 1; padding: 10px; border-radius: 4px; border: 1px solid #ddd;" required>
                <button type="submit" class="btn btn-edit">+ New Note</button>
            </form>
        </div>

        <div class="section">
            <h2>📝 My Notes</h2>
            <ul>{notes_html or "<li>No notes found</li>"}</ul>
        </div>
        ...
    </body></html>
    """


@app.get("/notes/{filename}", response_class=HTMLResponse)
def view_note_api(filename: str, edit: bool = False):
    filepath = config["notes"] / filename
    if not filepath.exists(): raise HTTPException(status_code=404)
    meta, body = parse_note(filepath)
    
    if edit:
        content_area = f"""
            <form action="/notes/{filename}/save" method="post">
                <textarea name="content" style="width:100%; height:450px; font-family:monospace; padding:10px;">{body}</textarea>
                <br><br>
                <div style="display: flex; gap: 10px;">
                    <button type="submit" class="btn btn-save">Save Changes</button>
                    
                    <!-- NEW: Delete Button -->
                    <button type="button" class="btn btn-delete" 
                        onclick="if(confirm('Delete this note forever?')) window.location.href='/notes/{filename}/delete'">
                        Delete Note
                    </button>
                    
                    <a href="/notes/{filename}" style="align-self: center; margin-left: 10px;">Cancel</a>
                </div>
            </form>"""

    else:
        # NEW: Convert Markdown to HTML for viewing
        # 'extras' enables things like tables and task lists
        html_content = markdown2.markdown(body, extras=["fenced-code-blocks", "tables", "task_list"])
        content_area = f"""
            <div class="markdown-body" style="background: #fff; padding: 20px; border: 1px solid #ddd; border-radius: 8px;">
                {html_content}
            </div>
            <br>
            <a href="/notes/{filename}?edit=true" class="btn btn-edit">Edit Note</a>"""

    return f"""
    <html><head>{COMMON_STYLE}</head><body>
        <a href="/">← Back to List</a>
        <h1>{meta.get('title', filename)}</h1>
        <p><strong>Tags:</strong> {", ".join(meta.get('tags', []))}</p>
        {content_area}
    </body></html>
    """

@app.post("/notes/{filename}/save")
def save_note_api(filename: str, content: str = Form(...)):
    filepath = config["notes"] / filename
    meta, _ = parse_note(filepath)
    save_note(filepath, meta, content)
    return HTMLResponse(content=f'<script>window.location.href="/notes/{filename}";</script>')

@app.get("/api/datasets/{filename}/metadata")
def get_metadata_endpoint(filename: str):
    metadata = get_dataset_metadata(filename)
    if not metadata: raise HTTPException(status_code=404)
    return metadata

@app.get("/notes/{filename}/delete")
def delete_note_api(filename: str):
    filepath = config["notes"] / filename
    
    if filepath.exists():
        filepath.unlink()  # Permanently deletes the file
        # This sends the user back to the home page (the "/" route)
        return RedirectResponse(url="/", status_code=303)
    
    raise HTTPException(status_code=404, detail="Note not found")

@app.post("/notes/create")
def create_note_api(filename: str = Form(...)):
    # 1. Clean up the name (ensure it ends in .md)
    if not filename.endswith(".md"):
        filename += ".md"
    
    filepath = config["notes"] / filename
    
    # 2. Create the file if it's new
    if not filepath.exists():
        title = filename.replace(".md", "").replace("_", " ").title()
        content = f"---\ntitle: {title}\ntags: []\n---\n\n# {title}\n"
        filepath.write_text(content)
    
    # 3. Send the user straight to the edit page for this new note
    return RedirectResponse(url=f"/notes/{filename}?edit=true", status_code=303)



# --- 4. CLI COMMANDS ---

def list_notes():
    notes_path = config["notes"]
    note_files = list(notes_path.glob("*.md")) + list(notes_path.glob("*.txt"))
    print(f"\n{'Filename':<30} | {'Title'}\n" + "-" * 50)
    for f in sorted(note_files):
        meta, _ = parse_note(f) 
        print(f"{f.name:<30} | {meta.get('title', f.stem)}")

def edit_note(args: List[str]):
    name = " ".join(args) or input("Enter note name: ").strip()
    if not any(name.endswith(ext) for ext in ['.md', '.txt']): name += ".md"
    filepath = config["notes"] / name

    if not filepath.exists():
        title = name.rsplit('.', 1)[0].replace('_', ' ')
        content = f"---\ntitle: {title}\ndate: {datetime.datetime.now().isoformat()}\ntags: []\n---\n\n# {title}\n"
        filepath.write_text(content)

    editor = os.environ.get('EDITOR', 'nano' if os.name != 'nt' else 'notepad')
    subprocess.run([editor, str(filepath)], check=True)
    meta, body = parse_note(filepath)
    save_note(filepath, meta, body)
    print(f"Synced: {name}")

def search_notes(args: List[str]):
    query = " ".join(args).lower() or input("Search term: ").strip().lower()
    found = 0
    for f in list(config["notes"].glob("*.md")) + list(config["notes"].glob("*.txt")):
        meta, body = parse_note(f)
        if query in meta.get('title', '').lower() or query in body.lower():
            found += 1
            print(f"[{found}] {f.name:<25}")
    if not found: print("No matches.")

def delete_note(args: List[str]):
    name = " ".join(args)
    path = config["notes"] / (name if name.endswith('.md') else name + ".md")
    if path.exists() and input(f"Delete {name}? (y/n): ").lower() == 'y':
        path.unlink()
        print("Deleted.")

def start_api():
    file_stem = Path(__file__).stem
    print(f"Server starting on http://127.0.0.1:8080")
    subprocess.run(["uvicorn", f"{file_stem}:app", "--reload", "--port", "8080"])

# --- 5. MAIN INTERFACE ---

def main_menu():
    actions = {'l': list_notes, 's': lambda: search_notes([]), 'e': lambda: edit_note([]), 
               'd': lambda: delete_note([]), 'a': start_api, 'v': lambda: print("Use API for viewing.")}
    while True:
        print("\n[L]ist [S]earch [E]dit [D]elete [A]PI [Q]uit")
        choice = input("Choice: ").strip().lower()
        if choice == 'q': break
        if choice in actions: actions[choice]()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        main_menu()
    else:
        cmd = sys.argv[1].lower()
        if cmd == "api": start_api()
        elif cmd == "list": list_notes()
        elif cmd == "search": search_notes(sys.argv[2:])
        elif cmd == "edit": edit_note(sys.argv[2:])
        else: print("Unknown command.")
