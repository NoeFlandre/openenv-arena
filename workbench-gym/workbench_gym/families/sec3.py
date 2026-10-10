# SPDX-License-Identifier: Apache-2.0

"""
sec3: deployed flaw (cybersecurity).

The repo holds a Dockerfile whose COPY lines define the release image, a README
and code. ``legacy/`` holds old copies of service code that the Dockerfile never
copies. Exactly one shipped file holds an exploitable flaw. Legacy copies carry
flaws of their own, so a search that ignores what ships finds a legacy file
first (the trap).

Every shipped file also holds one safe use of a generic dangerous API (see
DECOYS): a constant shell command, a key-prefix check, or a helper named
"unverified...". A first-hit search over the shipped code lands on one of these,
so the reader has to check the use, not the name.

Decoys: a legacy copy (the trap), the shipped file with another CWE, and the
same CWE in another shipped file.
"""

import random
import re

from ..core.grading import Field
from .base import Built, Family

# Shipped paths, and the CWE classes each one can hold.
SHIPPED = {
    "lib/net.py": ["CWE-918", "CWE-295", "CWE-798"],
    "lib/session.py": ["CWE-502", "CWE-295", "CWE-89"],
    "services/web/app.py": ["CWE-79", "CWE-601", "CWE-798"],
    "services/web/store.py": ["CWE-89", "CWE-502", "CWE-798"],
    "services/worker/export.py": ["CWE-22", "CWE-918", "CWE-79"],
    "services/worker/jobs.py": ["CWE-78", "CWE-22", "CWE-502"],
}
LEGACY_COUNT = {1: 1, 2: 2, 3: 3}

DOCKERFILE = """FROM python:3.12-slim
WORKDIR /srv
COPY lib/ lib/
COPY services/ services/
CMD ["python", "-m", "services.web.app"]
"""

README = """billing-api
Release image: built from the Dockerfile. Only its COPY sources ship.
legacy/ holds the 2019 port, kept for reference.
"""

VULN_22 = """import os

REPORT_DIR = "/srv/reports"


def read_report(name):
    with open(os.path.join(REPORT_DIR, name)) as fh:
        return fh.read()
"""
SAFE_22 = """import os
REPORT_DIR = "/srv/reports"

def read_report(name):
    path = os.path.realpath(os.path.join(REPORT_DIR, name))
    if not path.startswith(REPORT_DIR + os.sep):
        raise ValueError("bad report name")
    with open(path) as fh:
        return fh.read()
"""

VULN_78 = """import os


def make_thumb(src):
    os.system("convert " + src + " -resize 64x64 thumb.png")
"""
SAFE_78 = """import subprocess


def make_thumb(src):
    subprocess.run(["convert", src, "-resize", "64x64", "thumb.png"], check=True)
"""

VULN_79 = """def greet(params):
    return "<h1>Hello " + params["name"] + "</h1>"
"""
SAFE_79 = """import html


def greet(params):
    return "<h1>Hello " + html.escape(params["name"]) + "</h1>"
"""

VULN_89 = """def find_user(conn, name):
    sql = "SELECT id, email FROM users WHERE name = '" + name + "'"
    return conn.execute(sql).fetchall()
"""
SAFE_89 = """def find_user(conn, name):
    sql = "SELECT id, email FROM users WHERE name = ?"
    return conn.execute(sql, (name,)).fetchall()
"""

VULN_295 = """import ssl
import urllib.request


def call_billing(req):
    ctx = ssl._create_unverified_context()
    return urllib.request.urlopen(req, context=ctx, timeout=5).read()
"""
SAFE_295 = """import ssl
import urllib.request


def call_billing(req):
    ctx = ssl.create_default_context()
    return urllib.request.urlopen(req, context=ctx, timeout=5).read()
"""

VULN_502 = """import base64
import pickle


def load_cart(blob):
    return pickle.loads(base64.b64decode(blob))
"""
SAFE_502 = """import base64
import json


def load_cart(blob):
    return json.loads(base64.b64decode(blob))
"""

VULN_601 = """def login_done(params):
    return 302, {"Location": params["next"]}
"""
SAFE_601 = """def login_done(params):
    nxt = params["next"]
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/"
    return 302, {"Location": nxt}
"""

VULN_798 = """BILLING_KEY = "sk_live_4f9a1c7e02d8"


def billing_headers():
    return {"Authorization": "Bearer " + BILLING_KEY}
"""
SAFE_798 = """import os

BILLING_KEY = os.environ["BILLING_KEY"]


def billing_headers():
    return {"Authorization": "Bearer " + BILLING_KEY}
"""

VULN_918 = """import urllib.request


def fetch_preview(url):
    return urllib.request.urlopen(url, timeout=5).read(2048)
"""
SAFE_918 = """import urllib.parse
import urllib.request
ALLOWED_HOSTS = {"img.example.com"}

def fetch_preview(url):
    if urllib.parse.urlparse(url).hostname not in ALLOWED_HOSTS:
        raise ValueError("host not allowed")
    return urllib.request.urlopen(url, timeout=5).read(2048)
"""

# CWE -> (vulnerable module, safe module, signature only the vulnerable one contains)
TEMPLATES = {
    "CWE-22": (VULN_22, SAFE_22, "open(os.path.join(REPORT_DIR, name))"),
    "CWE-78": (VULN_78, SAFE_78, 'os.system("convert " + src'),
    "CWE-79": (VULN_79, SAFE_79, '"<h1>Hello " + params["name"]'),
    "CWE-89": (VULN_89, SAFE_89, "WHERE name = '\" + name"),
    "CWE-295": (VULN_295, SAFE_295, "ssl._create_unverified_context()"),
    "CWE-502": (VULN_502, SAFE_502, "pickle.loads(base64"),
    "CWE-601": (VULN_601, SAFE_601, '{"Location": params["next"]}'),
    "CWE-798": (VULN_798, SAFE_798, 'BILLING_KEY = "sk_live_'),
    "CWE-918": (VULN_918, SAFE_918, "def fetch_preview(url):\n    return urllib"),
}

# One safe decoy per shipped path: (import it needs or None, code). Each decoy
# calls a generic dangerous API only on constant data, or names a helper
# "unverified...". Every version of a file (vulnerable or safe) gets its decoy, so
# the decoy says nothing about which file is the flaw. lib/net.py always holds an
# os.system() decoy, so a first-hit search over the shipped files answers lib/net.py.
DECOYS = {
    "lib/net.py": ("import os", 'def flush_routes():\n    os.system("ip route flush cache")\n'),
    "lib/session.py": ("import os", 'def flush_to_disk():\n    os.system("sync")\n'),
    "services/web/app.py": (
        None,
        "def unverified_emails(users):\n    return [u.email for u in users if not u.verified]\n",
    ),
    "services/web/store.py": (
        None,
        "def unverified(rows):\n    return [r for r in rows if not r.verified]\n",
    ),
    "services/worker/export.py": (
        None,
        'def is_live_key(key):\n    return key.startswith("sk_live_")\n',
    ),
    "services/worker/jobs.py": (
        "import os",
        'def log_start():\n    os.system("logger -t jobs started")\n',
    ),
}


def _mirror(path: str) -> str:
    """Where the old copy of a shipped file lives, under legacy/."""
    tail = path[len("services/") :] if path.startswith("services/") else path
    return "legacy/" + tail


def _ship(text: str, path: str) -> str:
    """A shipped file: a template plus the path's safe decoy. Legacy copies get no decoy."""
    needed, body = DECOYS[path]
    head = text.rstrip("\n")
    if needed and needed not in head.split("\n"):
        head = needed + "\n" + head
    return head + "\n\n" + body


class DeployedFlaw(Family):
    id = "sec3"
    domain = "cybersecurity"
    title = "Deployed flaw"

    def build(self, level: int, rng: random.Random) -> Built:
        flaw_file = rng.choice(sorted(SHIPPED))
        flaw_cwe = rng.choice(SHIPPED[flaw_file])
        files = {"Dockerfile": DOCKERFILE, "README.md": README}
        for path in sorted(SHIPPED):
            if path == flaw_file:
                files[path] = _ship(TEMPLATES[flaw_cwe][0], path)
            else:
                files[path] = _ship(TEMPLATES[rng.choice(SHIPPED[path])][1], path)

        decoys: list[dict] = []
        for path in rng.sample(sorted(SHIPPED), LEGACY_COUNT[level]):
            cwe = rng.choice(SHIPPED[path])
            files[_mirror(path)] = TEMPLATES[cwe][0]
            decoys.append({"file": _mirror(path), "cwe": cwe})
        other_cwe = rng.choice([c for c in sorted(TEMPLATES) if c != flaw_cwe])
        decoys.append({"file": flaw_file, "cwe": other_cwe})
        other_file = rng.choice([p for p in sorted(SHIPPED) if p != flaw_file])
        decoys.append({"file": other_file, "cwe": flaw_cwe})

        return Built(
            question=(
                "The Dockerfile says what the release image ships. Which shipped file "
                "holds the one exploitable flaw, and what is its CWE? Give file as the "
                "repo path and cwe as CWE-n."
            ),
            files=files,
            fields={"file": Field("text"), "cwe": Field("text")},
            answer={"file": flaw_file, "cwe": flaw_cwe},
            decoys=decoys,
        )

    def solve(self, files: dict[str, str], question: str) -> dict:
        sources = re.findall(r"^COPY (\S+) ", files["Dockerfile"], re.M)
        for path in sorted(files):
            if not any(path.startswith(src) for src in sources):
                continue
            for cwe in sorted(TEMPLATES):
                if TEMPLATES[cwe][2] in files[path]:
                    return {"file": path, "cwe": cwe}
        return {"file": "", "cwe": ""}


FAMILY = DeployedFlaw()
