"""Sinh zalo_pc_app/zca_registry.json: danh muc 333 API cua @softtynet/zca-js
(doc truc tiep ma nguon TypeScript cua no), de app Zalo PC goi duoc phan lon API
ma khong phai viet tay tung ham.

    python3 tools/gen_zca_registry.py /duong/dan/zca-src

Moi muc: {name, domain, summary, signature, mode, method, service, path, query,
args[{name,type,required,description}], params{khoa: bieu-thuc}, encrypted, danger,
reason}. `mode`:
  template  moi tham so deu suy ra duoc tu cac truong nhap (goi bang truong);
  raw       co bieu thuc phuc tap: chi goi duoc khi truyen san `params` JSON;
  manual    khong lam tu dong duoc (upload, nhieu buoc, chi chay noi bo): ghi ro ly do.
Bieu thuc: ["arg",ten,mac_dinh?] | ["ctx",ten] | ["lit",gia_tri] | ["bool01",ten]
| ["now"] | ["str",ten] | ["num",ten] | ["json",ten] | ["join",ten].
KHONG doan gia tri: cai nao khong doc duoc thi mode raw/manual, khong bia.
"""
import json
import os
import re
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else "zca-src"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "zalo_pc_app", "zca_registry.json")
DANGER = re.compile(r"(delete|remove|disperse|leave|block|clear|reset|undo|cancel|"
                    r"kick|revoke|logout|ban|reject|lock|disable|purge)", re.I)


def strip_comments(s):
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return re.sub(r"(?m)(?<!:)//.*$", "", s)


def match_close(s, i, open_c, close_c):
    depth = 0
    for j in range(i, len(s)):
        c = s[j]
        if c in "\"'`":
            q = c
            j2 = j + 1
            while j2 < len(s) and s[j2] != q:
                j2 += 2 if s[j2] == "\\" else 1
            # bo qua chuoi: nhay bang cach danh dau
            s = s[:j] + " " * (j2 - j + 1) + s[j2 + 1:]
            continue
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return j
    return -1


def split_top(s, sep=","):
    out, depth, cur, q = [], 0, "", None
    i = 0
    while i < len(s):
        c = s[i]
        if q:
            cur += c
            if c == "\\":
                cur += s[i + 1:i + 2]
                i += 1
            elif c == q:
                q = None
        elif c in "\"'`":
            q = c
            cur += c
        elif c in "([{<" and not (c == "<" and s[i - 1:i] in (" ", "=")):
            depth += 1
            cur += c
        elif c in ")]}>" and not (c == ">" and s[i - 1:i] == "="):
            depth -= 1
            cur += c
        elif c == sep and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += c
        i += 1
    if cur.strip():
        out.append(cur.strip())
    return out


def type_index():
    idx = {}
    for base, _d, files in os.walk(os.path.join(ROOT, "src")):
        for f in files:
            if not f.endswith(".ts"):
                continue
            s = open(os.path.join(base, f), encoding="utf-8").read()
            for m in re.finditer(r"export (?:type|interface) (\w+)\s*(?:=\s*)?\{", s):
                st = m.end() - 1
                en = match_close(s, st, "{", "}")
                if en > 0:
                    idx.setdefault(m.group(1), s[st + 1:en])
    return idx


def fields_of(body):
    out = []
    for m in re.finditer(r"(?:/\*\*(.*?)\*/\s*)?(\w+)(\?)?\s*:\s*([^;\n]+)", body, flags=re.S):
        doc = re.sub(r"\s*\*\s*", " ", m.group(1) or "").strip()
        out.append({"name": m.group(2), "type": m.group(4).strip().rstrip(","),
                    "required": not m.group(3), "description": doc[:160]})
    return out


def parse_expr(e, args, objname):
    e = e.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", e):
        return ["lit", float(e) if "." in e else int(e)]
    if e in ("true", "false"):
        return ["lit", e == "true"]
    if e == "null":
        return ["lit", None]
    m = re.fullmatch(r"(['\"])(.*)\1", e)
    if m:
        return ["lit", m.group(2)]
    if e == "Date.now()":
        return ["now"]
    m = re.fullmatch(r"ctx\.(\w+)", e)
    if m:
        return ["ctx", m.group(1)]
    name = e
    if objname and e.startswith(objname + "."):
        name = e[len(objname) + 1:]
    if re.fullmatch(r"\w+", name) and name in args:
        return ["arg", name]
    m = re.fullmatch(r"(.+?)\s*(\?\?|\|\|)\s*(.+)", e)
    if m:
        a, d = parse_expr(m.group(1), args, objname), parse_expr(m.group(3), args, objname)
        if a and a[0] == "arg" and d and d[0] == "lit":
            return ["arg", a[1], d[1]]
    m = re.fullmatch(r"(String|Number)\((.+)\)", e)
    if m:
        a = parse_expr(m.group(2), args, objname)
        if a and a[0] == "arg":
            return ["str" if m.group(1) == "String" else "num", a[1]]
    m = re.fullmatch(r"(.+?)\s*\?\s*1\s*:\s*0", e)
    if m:
        a = parse_expr(m.group(1), args, objname)
        if a and a[0] == "arg":
            return ["bool01", a[1]]
    m = re.fullmatch(r"JSON\.stringify\((.+)\)", e)
    if m:
        a = parse_expr(m.group(1), args, objname)
        if a and a[0] == "arg":
            return ["json", a[1]]
    m = re.fullmatch(r"(\w+)\.join\((['\"]),?\2?\)", e)
    if m and m.group(1) in args:
        return ["join", m.group(1)]
    return None


def flatten_consts(rel):
    """{"A.B": "gia tri"} tu `export const X = { A: { B: "..." } }` (chi chuoi)."""
    path = os.path.join(ROOT, "src", "constants", rel)
    if not os.path.exists(path):
        return {}
    s = strip_comments(open(path, encoding="utf-8").read())
    out = {}

    def walk(body, prefix):
        for item in split_top(body):
            m = re.fullmatch(r"(\w+)\s*:\s*(.+)", item, flags=re.S)
            if not m:
                continue
            k, v = m.group(1), m.group(2).strip()
            if v.startswith("{"):
                walk(v[1:v.rfind("}")], prefix + k + ".")
            else:
                sm = re.fullmatch(r"(['\"`])(.*)\1(?:\s+as\s+const)?", v)
                if sm:
                    out[prefix + k] = sm.group(2)
    for m in re.finditer(r"export const (\w+)\s*=\s*\{", s):
        st = m.end() - 1
        en = match_close(s, st, "{", "}")
        if en > 0:
            walk(s[st + 1:en], m.group(1) + ".")
    return out


CONSTS = None


def consts():
    global CONSTS
    if CONSTS is None:
        CONSTS = {}
        for f in ("domains.ts", "endpoints.ts"):
            CONSTS.update(flatten_consts(f))
    return CONSTS


def resolve_url(s):
    """(service, fixed_domain, path, query_literal) hoac None."""
    sv = re.search(r"const serviceURL = utils\.makeURL\(\s*`([^`]*)`\s*(?:,\s*\{([^}]*)\})?\s*\)", s)
    if not sv:
        return None
    t, q = sv.group(1), sv.group(2)
    t = re.sub(r"\$\{(ZALO_(?:ENDPOINTS|DOMAINS)\.[\w.]+)\}",
               lambda m: consts().get(m.group(1), m.group(0)), t)
    head = re.match(r"\$\{([^}]+)\}(.*)", t, flags=re.S)
    if not head:
        return None
    x, path = head.group(1), head.group(2)
    service = fixed = None
    m = re.fullmatch(r"api\.zpwServiceMap\.(\w+)\[0\]", x)
    if m:
        service = m.group(1)
    elif x in ("baseDomain", "voiceCallService"):
        d = re.search(r"const %s\s*=\s*(.+?);" % x, s, flags=re.S)
        e = d.group(1) if d else ""
        k = re.search(r"zpwServiceMap\.(\w+)", e) or \
            re.search(r"getServiceEndpoint\([^,]+,\s*\"(\w+)\"", e)
        if k:
            service = k.group(1)
        fb = re.search(r"(ZALO_DOMAINS\.\w+)", e)
        if fb:
            fixed = consts().get(fb.group(1))
        if not k and not fixed:
            return None
    elif x.startswith("ZALO_DOMAINS."):
        fixed = consts().get(x)
        if not fixed:
            return None
    else:
        return None
    return service, fixed, path, q


def one(api, types):
    name, domain = api["name"], api["domain"]
    ent = {"name": name, "domain": domain, "summary": api.get("summary", ""),
           "signature": api.get("signature", ""), "danger": bool(DANGER.search(name)),
           "mode": "manual", "reason": ""}
    p = os.path.join(ROOT, "src", "apis", domain, name + ".ts")
    if not os.path.exists(p):
        ent["reason"] = "khong co ma nguon"
        return ent
    raw = open(p, encoding="utf-8").read()
    s = strip_comments(raw)
    ru = resolve_url(s)
    if not ru:
        ent["reason"] = "khong dung dich vu Zalo qua serviceMap (xu ly cuc bo/dac biet)"
        return ent
    service, fixed, path, qlit = ru
    ent["service"], ent["fixed_domain"], ent["path"] = service, fixed, path
    if "${" in path:
        ent["reason"] = "duong dan co bien dong"
        return ent
    if path.startswith("/api/voicecall"):
        ent["reason"] = "cuoc goi: dung bo bao hieu cuoc goi cua app (make_call/answer_call...)"
        return ent
    ent["query"] = {}
    for k, v in re.findall(r"(\w+)\s*:\s*([^,}]+)", qlit or ""):
        ent["query"][k] = v.strip().strip("\"'")
    nreq = s.count("utils.request(")
    if nreq != 1:
        ent["reason"] = "goi %d request (nhieu buoc hoac khong goi)" % nreq
        return ent
    mm = re.search(r"method:\s*\"(GET|POST)\"", s)
    ent["method"] = mm.group(1) if mm else api.get("httpMethod", "GET")
    if "FormData" in s or "multipart" in s.lower() or "uploadFile" in s:
        ent["reason"] = "tai tep len (multipart): dung khung chat/endpoint rieng cua app"
        return ent
    fm = re.search(r"return async function (\w+)\(", s)
    args, objname, argdefs = {}, None, []
    if fm:
        st = fm.end() - 1
        en = match_close(s, st, "(", ")")
        for a in split_top(s[st + 1:en]):
            if not a:
                continue
            am = re.fullmatch(r"(\w+)(\?)?\s*(?::\s*(.+?))?(?:\s*=\s*(.+))?", a, flags=re.S)
            if not am:
                ent["reason"] = "chu ky ham phuc tap: " + a[:40]
                return ent
            argdefs.append((am.group(1), am.group(3) or "any", not am.group(2) and am.group(4) is None))
    docs = dict(re.findall(r"@param\s+(?:\{[^}]*\}\s*)?(\w+)\s+([^\n@]*)", raw))
    flat = []
    if len(argdefs) == 1 and re.fullmatch(r"\w+", argdefs[0][1].split("|")[0].strip()) \
            and argdefs[0][1].strip() in types:
        objname = argdefs[0][0]
        for f in fields_of(types[argdefs[0][1].strip()]):
            args[f["name"]] = f
            flat.append(f)
    else:
        for n, t, req in argdefs:
            f = {"name": n, "type": t.strip(), "required": req,
                 "description": (docs.get(n) or "").strip()[:160]}
            args[n] = f
            flat.append(f)
    ent["args"] = flat
    ent["encrypted"] = "utils.encodeAES" in s
    var = "params"
    vm = re.search(r"utils\.encodeAES\(\s*JSON\.stringify\(\s*(\w+)\s*\)", s)
    if vm:
        var = vm.group(1)
    pm = re.search(r"const %s(?::[^=]+)?\s*=\s*\{" % re.escape(var), s)
    if not pm:
        pm = re.search(r"utils\.encodeAES\(\s*JSON\.stringify\(\s*\{", s)
    params, complex_keys = {}, []
    if pm:
        st = pm.end() - 1
        en = match_close(s, st, "{", "}")
        for item in split_top(s[st + 1:en]):
            if not item:
                continue
            if item.startswith("..."):
                complex_keys.append(item[:30])
                continue
            kv = re.fullmatch(r"(\w+|\"[^\"]+\")\s*:\s*(.+)", item, flags=re.S)
            if kv:
                k, ex = kv.group(1).strip("\""), kv.group(2).strip()
                pe = parse_expr(ex, args, objname)
                if pe is None:
                    complex_keys.append(k)
                    params[k] = ["raw", ex[:80]]
                else:
                    params[k] = pe
            elif re.fullmatch(r"\w+", item):
                pe = parse_expr(item, args, objname)
                if pe is None:
                    complex_keys.append(item)
                else:
                    params[item] = pe
            else:
                complex_keys.append(item[:30])
    elif ent["encrypted"]:
        ent["reason"] = "khong doc duoc doi tuong params"
        return ent
    ent["params"] = params
    ent["complex"] = complex_keys
    ent["mode"] = "raw" if complex_keys else "template"
    return ent


def mark_covered(entries):
    """Danh dau API zca da co san trong 96 dich vu cua app (trung TEN snake_case hoac
    trung DUONG DAN endpoint, ke ca duong 1-1/nhom cua op tach doi) -> `covered_by`.
    Giao dien va HA bo qua cac muc nay de khong hien hai lan."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from zalo_pc_app import services as S
    snake = lambda n: re.sub(r"(?<!^)(?=[A-Z])", "_", n).lower()  # noqa: E731
    names = set(S.OPS) | {sp["addon"] for sp in S.OPS.values()}
    paths = {}
    for act, sp in S.OPS.items():
        if sp.get("path"):
            paths.setdefault(sp["path"], act)
    for act, v in S._SPLIT.items():
        for i in (1, 4):
            if v[i]:
                paths.setdefault(v[i], act)
    for e in entries:
        n = snake(e["name"])
        if n in names:
            e["covered_by"] = n
        elif e.get("path") and e["path"] in paths:
            e["covered_by"] = paths[e["path"]]


def main():
    api = json.load(open(os.path.join(ROOT, "docs/.vitepress/theme/api-data.json"),
                         encoding="utf-8"))
    types = type_index()
    out = [one(a, types) for a in api["apis"]]
    mark_covered(out)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"version": api.get("version"), "total": len(out), "apis": out},
                  f, ensure_ascii=False, indent=0)
    from collections import Counter
    print(OUT, len(out), dict(Counter(e["mode"] for e in out)))


if __name__ == "__main__":
    main()
