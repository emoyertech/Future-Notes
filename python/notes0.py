#!/usr/bin/env python3
import os
import sys
import subprocess
import datetime
from pathlib import Path
from typing import Optional, List
from fastapi.responses import HTMLResponse

# Core dependencies (Ensure these are installed: pip install fastapi pandas uvicorn)
try:
    import pandas as pd
    from fastapi import FastAPI, HTTPException
except ImportError:
    print("Error: Missing dependencies. Please run: pip install fastapi pandas uvicorn")
    sys.exit(1)

# --- 1. INITIALIZATION ---

def setup():
    """Initialize the notes application directory structure."""
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
app = FastAPI(title="Note & Data API")

# --- 2. CORE LOGIC ---

def parse_note(file_path: Path):
    """Parses a markdown/text file into metadata and body content."""
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return {'title': file_path.name, 'tags': []}, ""

    if not content.startswith('---'):
        return {'title': file_path.stem, 'tags': []}, content

    try:
        _, header_raw, body = content.split('---', 2)
        metadata = {}
        for line in header_raw.strip().splitlines():
            if ':' in line:
                key, val = [item.strip() for item in line.split(':', 1)]
                if key.lower() == 'tags':
                    val = val.strip('[]').split(',')
                    val = [t.strip() for t in val if t.strip()]
                metadata[key.lower()] = val
        
        return metadata, body.strip()
    except (ValueError, IndexError):
        return {'title': file_path.stem, 'tags': []}, content

def save_note(file_path: Path, meta: dict, body: str):
    """Writes metadata and body back to the file in markdown format."""
    meta_copy = meta.copy()
    if 'tags' in meta_copy and isinstance(meta_copy['tags'], list):
        meta_copy['tags'] = f"[{', '.join(meta_copy['tags'])}]"
        
    header_lines = [f"{k}: {v}" for k, v in meta_copy.items()]
    header_text = "\n".join(header_lines)
    new_content = f"---\n{header_text}\n---\n\n{body}"
    file_path.write_text(new_content, encoding='utf-8')

# --- 3. API ROUTES ---

@app.get("/", response_class=HTMLResponse)
def api_home():
    notes = [f.name for f in config["notes"].glob("*") if f.suffix in ['.md', '.txt']]
    datasets = [f.name for f in config["datasets"].glob("*.csv")]

    # Create HTML links for each file
    notes_html = "".join([f'<li><a href="/notes/{n}">{n}</a></li>' for n in notes])
    data_html = "".join([f'<li><a href="/datasets/{d}">{d}</a></li>' for d in datasets])

    return f"""
    <html>
        <head>
            <title>My Notes API</title>
            <style>
                body {{ font-family: sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #f4f4f9; }}
                h1 {{ color: #333; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
                .section {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 20px; }}
                ul {{ list-style: none; padding: 0; }}
                li {{ margin: 10px 0; }}
                a {{ color: #007bff; text-decoration: none; font-weight: bold; }}
                a:hover {{ text-decoration: underline; }}
                .footer {{ font-size: 0.8em; color: #666; text-align: center; }}
            </style>
        </head>
        <body>
            <h1>🚀 Future Proof Notes</h1>
            
            <div class="section">
                <h2>📝 Notes</h2>
                <ul>{notes_html or "<li>No notes found</li>"}</ul>
            </div>

            <div class="section">
                <h2>📊 Datasets</h2>
                <ul>{data_html or "<li>No datasets found</li>"}</ul>
            </div>

            <div class="footer">
                <p>View interactive docs at <a href="/docs">/docs</a></p>
            </div>
        </body>
    </html>
    """

# --- 4. CLI COMMANDS ---

def list_notes(filter_tag: Optional[str] = None):
    notes_path = config["notes"]
    note_files = list(notes_path.glob("*.md")) + list(notes_path.glob("*.txt"))
    
    if not note_files:
        print("No notes found.")
        return

    matches = []
    for f in sorted(note_files):
        meta, _ = parse_note(f) 
        tags = [t.lower() for t in meta.get('tags', [])]
        if not filter_tag or filter_tag.lower() in tags:
            matches.append((f, meta))

    print(f"\n{'Filename':<30} | {'Title'}")
    print("-" * 50)
    for f, meta in matches:
        print(f"{f.name:<30} | {meta.get('title', f.stem)}")
    print(f"\n{len(matches)} note(s) found.")

def edit_note(args: List[str]):
    notes_path = config["notes"]
    name = " ".join(args) if args else input("Enter note name: ").strip()
    
    if not any(name.endswith(ext) for ext in ['.md', '.txt']):
        name += ".md"
        
    filepath = notes_path / name

    if not filepath.exists():
        # Fixed the replace logic here
        title = name.rsplit('.', 1)[0].replace('_', ' ')
        content = f"---\ntitle: {title}\ndate: {datetime.datetime.now().isoformat()}\ntags: []\n---\n\n# {title}\n"
        filepath.write_text(content)
        print(f"Creating new file: {name}")

    editor = os.environ.get('EDITOR', 'nano' if os.name != 'nt' else 'notepad')
    subprocess.run([editor, str(filepath)], check=True)

    meta, body = parse_note(filepath)
    meta['modified'] = datetime.datetime.now().isoformat()
    save_note(filepath, meta, body)
    print(f"Synced: {name}")

def search_notes(args: List[str]):
    query = " ".join(args).lower() if args else input("Enter search term: ").strip().lower()
    notes_dir = config["notes"]
    found_count = 0

    print(f"\nSearching for '{query}'...")
    for f in (list(notes_dir.glob("*.md")) + list(notes_dir.glob("*.txt"))):
        meta, body = parse_note(f)
        in_title = query in meta.get('title', '').lower()
        in_tags = any(query in str(t).lower() for t in meta.get('tags', []))
        in_body = query in body.lower()

        if in_title or in_tags or in_body:
            found_count += 1
            locs = [l for l, m in [("Title", in_title), ("Tags", in_tags), ("Content", in_body)] if m]
            print(f"[{found_count}] {f.name:<25} | Found in: {', '.join(locs)}")

    if found_count == 0: print("No matches found.")

def delete_note(args: List[str]):
    name = " ".join(args)
    if not any(name.endswith(ext) for ext in ['.md', '.txt']): name += ".md"
    path = config["notes"] / name
    if path.exists() and input(f"Delete '{name}'? (y/n): ").lower() == 'y':
        path.unlink()
        print("Deleted.")
    else: print("Action cancelled or note not found.")

# --- 5. MAIN INTERFACE ---

def start_api():
    """Helper to start the API server."""
    file_stem = Path(__file__).stem
    subprocess.run(["uvicorn", f"{file_stem}:app", "--reload", "--port", "8080"], check=True)
    print(f"Starting API server on http://127.0.0.1:8000")
    print("Visit http://127.0.0.1 for documentation.")
    try:
        subprocess.run(["uvicorn", f"{file_stem}:app", "--reload"], check=True)
    except KeyboardInterrupt:
        print("\nAPI Server stopped.")

def main_menu():
    while True:
        print("\n--- Main Menu ---")
        print("[L]ist  [S]earch  [E]dit  [D]elete  [A]PI-Start  [Q]uit")
        choice = input("Select an action: ").strip().lower()

        if choice in ('l', 'list'): list_notes()
        elif choice in ('s', 'search'): search_notes([])
        elif choice in ('e', 'edit'): edit_note([])
        elif choice in ('d', 'delete'): delete_note([])
        elif choice in ('a', 'api'): start_api()
        elif choice in ('q', 'quit'): break

if __name__ == "__main__":
    if len(sys.argv) < 2:
        main_menu()
    else:
        cmd = sys.argv[1].lower()
        if cmd == "list": list_notes()
        elif cmd == "search": search_notes(sys.argv[2:])
        elif cmd == "edit": edit_note(sys.argv[2:])
        elif cmd == "delete": delete_note(sys.argv[2:])
        elif cmd == "api": start_api()
        else:
            print("Unknown command. Use: list, search, edit, delete, or api.")
