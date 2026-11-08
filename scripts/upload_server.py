#!/usr/bin/env python3
"""Servidor mínimo para subir vídeos/fotos desde el móvil por la red local.

Uso:  python3 scripts/upload_server.py [escena] [puerto]
Abre http://<ip-del-ordenador>:<puerto>/ en el navegador del móvil.
Los archivos se guardan en data/raw/<escena>/.
"""
import html
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCENE = sys.argv[1] if len(sys.argv) > 1 else "prueba"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
DEST = Path(__file__).resolve().parent.parent / "data" / "raw" / SCENE
DEST.mkdir(parents=True, exist_ok=True)

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Subir a mapa-casa</title>
<style>body{{font-family:sans-serif;margin:24px;max-width:600px}}
button,input{{font-size:1.1em;margin:8px 0}}progress{{width:100%;height:24px}}</style></head>
<body><h2>Subir a: {scene}</h2>
<input type="file" id="f" multiple accept="video/*,image/*"><br>
<button onclick="up()">Subir</button>
<progress id="p" value="0" max="100"></progress><div id="s"></div>
<h3>Ya en el ordenador</h3><ul>{files}</ul>
<script>
async function up(){{
  const files=[...document.getElementById('f').files];
  const s=document.getElementById('s'), p=document.getElementById('p');
  for(const [i,file] of files.entries()){{
    await new Promise((ok,ko)=>{{
      const x=new XMLHttpRequest();
      x.open('PUT','/upload/'+encodeURIComponent(file.name));
      x.upload.onprogress=e=>{{p.value=100*e.loaded/e.total;
        s.textContent=`(${{i+1}}/${{files.length}}) ${{file.name}}: ${{(e.loaded/1e6).toFixed(0)}} / ${{(e.total/1e6).toFixed(0)}} MB`;}};
      x.onload=()=>x.status==200?ok():ko(x.responseText);
      x.onerror=()=>ko('error de red');
      x.send(file);
    }}).catch(e=>{{s.textContent='Error: '+e;throw e;}});
  }}
  s.textContent='¡Listo! '+files.length+' archivo(s) subido(s).';
  setTimeout(()=>location.reload(),1500);
}}
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        files = "".join(
            f"<li>{html.escape(p.name)} ({p.stat().st_size / 1e6:.0f} MB)</li>"
            for p in sorted(DEST.iterdir()) if p.is_file()
        )
        body = PAGE.format(scene=html.escape(SCENE), files=files).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self):
        from urllib.parse import unquote
        if not self.path.startswith("/upload/"):
            self.send_error(404)
            return
        name = os.path.basename(unquote(self.path[len("/upload/"):]))
        name = re.sub(r"[^\w.\-]", "_", name) or "archivo"
        length = int(self.headers.get("Content-Length", 0))
        tmp = DEST / (name + ".part")
        with open(tmp, "wb") as f:
            remaining = length
            while remaining > 0:
                chunk = self.rfile.read(min(1 << 20, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
        if remaining:
            tmp.unlink(missing_ok=True)
            self.send_error(400, "Subida incompleta")
            return
        tmp.rename(DEST / name)
        print(f"Recibido {name} ({length / 1e6:.1f} MB)", flush=True)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")


if __name__ == "__main__":
    print(f"Guardando en {DEST}\nAbre http://<ip>:{PORT}/ en el móvil", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
