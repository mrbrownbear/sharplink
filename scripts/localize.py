#!/usr/bin/env python3
import hashlib
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import mimetypes
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ORIGIN = "https://www.sharplink.com"
ROUTES = ["/", "/about", "/investors", "/ethereum-opportunity", "/dashboard", "/news", "/news/Announcement", "/contact", "/privacy-policy", "/terms-of-use"]
LOCAL_PREFIXES = ("/_nuxt/", "/_fonts/", "/_vercel/image", "/images/", "/svgs/", "/webgl/", "/api/", "/favicon")
EXTERNAL_ASSET_HOSTS = {"a.storyblok.com", "app.storyblok.com"}
TEXT_EXTS = {".html", ".css", ".js", ".json", ".svg", ".txt", ".xml"}
UA = "Mozilla/5.0 SharpLinkLocalizer"
queue = []
queued = set()
records = {}
failures = []

def normalize(url, base=ORIGIN + "/"):
    url = html.unescape(str(url).strip().strip("\"'"))
    if not url or url.startswith(("data:", "blob:", "mailto:", "tel:", "javascript:", "#")):
        return None
    try:
        return urllib.parse.urljoin(base, url)
    except Exception:
        return None

def should_fetch(url):
    p = urllib.parse.urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    if p.netloc == "www.sharplink.com":
        route = p.path.rstrip("/") or "/"
        return route in ROUTES or p.path.startswith(LOCAL_PREFIXES)
    return p.netloc in EXTERNAL_ASSET_HOSTS

def enqueue(url, base=ORIGIN + "/"):
    u = normalize(url, base)
    if u and should_fetch(u) and u not in queued:
        queued.add(u)
        queue.append(u)

def fetch(url):
    last = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=12) as response:
                return response.geturl(), response.headers, response.read()
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise last

def extension(content_type):
    c = (content_type or "").split(";", 1)[0].strip().lower()
    table = {
        "image/avif": ".avif", "image/webp": ".webp", "image/png": ".png",
        "image/jpeg": ".jpg", "image/svg+xml": ".svg", "video/webm": ".webm",
        "video/mp4": ".mp4", "application/pdf": ".pdf", "application/json": ".json",
        "text/css": ".css", "application/javascript": ".js", "text/javascript": ".js",
        "font/woff": ".woff", "font/woff2": ".woff2"
    }
    return table.get(c) or mimetypes.guess_extension(c) or ""

def output_path(url, content_type=""):
    p = urllib.parse.urlparse(url)
    if p.netloc == "www.sharplink.com":
        route = p.path.rstrip("/") or "/"
        if route in ROUTES:
            return Path("index.html") if route == "/" else Path(route.lstrip("/")) / "index.html"
        if p.path == "/_vercel/image":
            source = urllib.parse.parse_qs(p.query).get("url", [""])[0]
            suffix = Path(urllib.parse.urlparse(source).path).suffix or extension(content_type)
            digest = hashlib.sha256(url.encode()).hexdigest()[:16]
            return Path("_vercel") / ("image_" + digest + suffix)
        return Path(p.path.lstrip("/"))
    result = Path("__external__") / p.netloc / p.path.lstrip("/")
    if result.suffix:
        return result
    return Path(str(result) + extension(content_type))

ABS_URL = re.compile(r"https?://[^\\s\"'<>\\\\)]+")
LOCAL_URL = re.compile(r"(?<![A-Za-z0-9])(/(?:_nuxt|_fonts|_vercel/image|images|svgs|webgl|api|favicon)[^\\s\"'<>\\\\)]*)")

def discover(text, base):
    for match in ABS_URL.finditer(text):
        enqueue(match.group(0).rstrip(";,]}"), base)
    for match in LOCAL_URL.finditer(text):
        enqueue(html.unescape(match.group(1).rstrip(";,]}")), base)

def process_one(url):
    try:
        final_url, headers, data = fetch(url)
        ctype = headers.get("Content-Type", "")
        path = output_path(url, ctype)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return url, final_url, ctype, path, data, None
    except Exception as exc:
        return url, None, None, None, None, exc

def crawl():
    for route in ROUTES:
        enqueue(ORIGIN + route)
    while queue:
        batch = []
        while queue and len(batch) < 24:
            batch.append(queue.pop(0))
        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(process_one, url) for url in batch]
            for future in as_completed(futures):
                url, final_url, ctype, path, data, exc = future.result()
                if exc is not None:
                    failures.append({"url": url, "error": repr(exc)})
                    print("FAIL", url, repr(exc), file=sys.stderr)
                    continue
                records[url] = {"path": "/" + path.as_posix(), "type": ctype}
                if final_url != url:
                    records[final_url] = records[url]
                if path.suffix.lower() in TEXT_EXTS or any(x in ctype for x in ("text/", "javascript", "json", "svg+xml", "xml")):
                    discover(data.decode("utf-8", errors="ignore"), final_url)
                print("OK", url, "=>", path)

def rewrite():
    pairs = {}
    for url, meta in records.items():
        local = meta["path"]
        pairs[url] = local
        pairs[html.escape(url, quote=False)] = local
        p = urllib.parse.urlparse(url)
        if p.netloc == "www.sharplink.com":
            rel = p.path + (("?" + p.query) if p.query else "")
            pairs[rel] = local
            pairs[html.escape(rel, quote=False)] = local
    ordered = sorted(pairs.items(), key=lambda item: len(item[0]), reverse=True)
    for path in Path(".").rglob("*"):
        if not path.is_file() or ".git" in path.parts or ".github" in path.parts or "scripts" in path.parts:
            continue
        if path.suffix.lower() not in TEXT_EXTS:
            continue
        text = path.read_text("utf-8", errors="ignore")
        before = text
        for remote, local in ordered:
            text = text.replace(remote, local)
        text = text.replace(ORIGIN + "/", "/").replace(ORIGIN, "")
        if text != before:
            path.write_text(text, "utf-8")

def add_guard():
    guard = """(function(){
const blocked='/__offline_blocked__';
const originalFetch=window.fetch;
const map=function(value){
  try{
    const raw=String(value&&value.url?value.url:value);
    if(!raw||raw.startsWith('data:')||raw.startsWith('blob:')||raw.startsWith('about:'))return raw;
    const u=new URL(raw,location.href);
    if(u.origin===location.origin)return raw;
    if(u.hostname==='www.sharplink.com'||u.hostname.endsWith('storyblok.com'))return blocked;
    return raw;
  }catch(e){return value;}
};
window.fetch=function(input,init){
  const raw=input&&input.url?input.url:input;
  const mapped=map(raw);
  if(mapped===blocked)return Promise.reject(new Error('Blocked remote runtime request: '+raw));
  if(typeof Request!=='undefined'&&input instanceof Request&&mapped!==raw)return originalFetch.call(this,new Request(mapped,input),init);
  return originalFetch.call(this,mapped,init);
};
const originalOpen=XMLHttpRequest.prototype.open;
XMLHttpRequest.prototype.open=function(method,url){
  const mapped=map(url);
  if(mapped===blocked)throw new Error('Blocked remote runtime request: '+url);
  arguments[1]=mapped;
  return originalOpen.apply(this,arguments);
};
})();"""
    guard_path = Path("__local/runtime-guard.js")
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    guard_path.write_text(guard + "\\n", "utf-8")
    tag = '<script src="/__local/runtime-guard.js"></script>'
    for page in Path(".").rglob("index.html"):
        text = page.read_text("utf-8", errors="ignore")
        if tag not in text:
            text = text.replace("<head>", "<head>" + tag, 1) if "<head>" in text else tag + text
            page.write_text(text, "utf-8")

def write_config():
    config = {
        "$schema": "https://openapi.vercel.sh/vercel.json",
        "cleanUrls": True,
        "trailingSlash": False,
        "headers": [{"source": "/(.*)", "headers": [{"key": "X-Content-Type-Options", "value": "nosniff"}]}]
    }
    Path("vercel.json").write_text(json.dumps(config, indent=2) + "\\n", "utf-8")

def main():
    crawl()
    rewrite()
    add_guard()
    write_config()
    report = {"origin": ORIGIN, "localized_resources": len(records), "failures": failures}
    Path("localization-report.json").write_text(json.dumps(report, indent=2) + "\\n", "utf-8")
    print(json.dumps(report, indent=2))
    critical = [item for item in failures if any(key in item["url"] for key in ("/_nuxt/", "/_fonts/", "a.storyblok.com", "/_vercel/image", "/api/"))]
    if critical:
        sys.exit(2)

if __name__ == "__main__":
    main()
