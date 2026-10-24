#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接口扫描处理：lives + sites 采集 + py"""

import json
import re
import threading
import time
import unicodedata
import requests
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, urlunparse

# ---------- 请求配置（模拟 TVBox 环境） ----------
TVBOX_UAS = [
    "okhttp/3.12.13",
    "Mozilla/5.0 (Linux; Android 9; Pixel 3 XL Build/PQ3A.190801.002; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.120 Mobile Safari/537.36",
    "VLC/3.0.16 LibVLC/3.0.16",
    "AppleCoreMedia/1.0.0.19C56 (iPhone; U; CPU OS 15_2 like Mac OS X; en_us)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "bingcha/1.1 (mianfeifenxiang)",
]
TVBOX_HEADERS = {
    "X-Requested-With": "com.fongmi.android.tv",
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# ---------- 路径配置 ----------
REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIR = REPO_ROOT / "tvbox"
OUTPUT_LIVE_DIR = SCAN_DIR / "live"

AGGREGATE_JSON = SCAN_DIR / "海量直播聚合接口.json"          # ← 已改名
LIVELIST_PATH = REPO_ROOT / "livelist.txt"

# 新增路径
CJ_LIST_PATH = REPO_ROOT / "cjlist.txt"
PY_LIST_PATH = REPO_ROOT / "pylist.txt"
PY_AGG_JSON = SCAN_DIR / "海量py聚合接口.json"
CJ_AGG_JSON = SCAN_DIR / "海量采集聚合接口.json"
# 各脚本生成的聚合输出，扫描时跳过，避免互相回流（名称叠加成「1线1线」）
AGGREGATE_OUTPUTS = {"海量直播线路.json", AGGREGATE_JSON.name,
                     PY_AGG_JSON.name, CJ_AGG_JSON.name}

DOWNLOAD_TIMEOUT = 25
DOWNLOAD_WORKERS = 8                    # 并发下载线程数
MAX_RETRIES = 3
MAX_UNWRAP_DEPTH = 5
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024   # 单个文件体积上限
MAX_DOWNLOAD_SECONDS = 300              # 单次请求总时长上限（timeout 只限制读间隔）
TODAY = datetime.now().strftime("%Y%m%d")
DEBUG = False

# ---------- 模板配置（用于聚合json） ----------
TEMPLATE_CONFIG = {
    "spider": "https://mpimg.cn/down.php/d479d37ee36fa366b646f77d17b76fb1.jar",
    "logo": "https://mpimg.cn/down.php/7c35e9376677a03556efe5193bf23cec.jpg",
    "sites": [
        {
            "key": "jueson",
            "name": "🏠主页┃豆瓣",
            "type": 3,
            "api": "csp_DouDou",
            "searchable": 0,
            "quickSearch": 0,
            "indexs": 1,
            "filterable": 1
        }
    ],
    "parses": [
        {"name": "解析聚合", "type": 3, "url": "Demo"},
        {"name": "xy4k", "type": 1, "url": "https://183933.xyz/xiaye.php?url="}
    ],
    "lives": [],
    "rules": [
        {"name": "农民", "hosts": ["toutiaovod.com"], "regex": ["video/tos/cn"]},
        {"name": "火山", "hosts": ["huoshan.com"], "regex": ["item_id="]},
        {"name": "抖音", "hosts": ["douyin.com"], "regex": ["is_play_url="]},
        {"name": "饭团点击", "hosts": ["dadagui", "freeok", "dadagui"], "script": ["document.querySelector(\"#playleft iframe\").contentWindow.document.querySelector(\"#start\").click();"]},
        {"name": "毛驴点击", "hosts": ["www.maolvys.com"], "script": ["document.getElementsByClassName('swal-button swal-button--confirm')[0].click()"]},
        {"name": "ofiii", "hosts": ["www.ofiii.com"], "script": ["const play=document.getElementsByClassName('play_icon')[0],event=new MouseEvent('click',{bubbles:!0,cancelable:!0,view:window,screenX:100,screenY:100,clientX:50,clientY:50,button:0,shiftKey:!1,ctrlKey:!1,altKey:!1,metaKey:!1,modifierState:0});play.dispatchEvent(event);"]}
    ],
    "doh": [
        {"name": "Google", "url": "https://dns.google/dns-query", "ips": ["8.8.4.4", "8.8.8.8"]},
        {"name": "Cloudflare", "url": "https://cloudflare-dns.com/dns-query", "ips": ["1.1.1.1", "1.0.0.1", "2606:4700:4700::1111", "2606:4700:4700::1001"]},
        {"name": "AdGuard", "url": "https://dns.adguard.com/dns-query", "ips": ["94.140.14.140", "94.140.14.141"]},
        {"name": "DNSWatch", "url": "https://resolver2.dns.watch/dns-query", "ips": ["84.200.69.80", "84.200.70.40"]},
        {"name": "Quad9", "url": "https://dns.quad9.net/dns-quer", "ips": ["9.9.9.9", "149.112.112.112"]}
    ],
    "hosts": [
        "cache.ott.*.itv.cmvideo.cn=base-v4-free-mghy.e.cdn.chinamobile.com",
        "cache.ott.ystenlive.itv.cmvideo.cn=base-v4-free-mghy.e.cdn.chinamobile.com",
        "cache.ott.bestlive.itv.cmvideo.cn=base-v4-free-mghy.e.cdn.chinamobile.com",
        "cache.ott.wasulive.itv.cmvideo.cn=base-v4-free-mghy.e.cdn.chinamobile.com",
        "cache.ott.fifalive.itv.cmvideo.cn=base-v4-free-mghy.e.cdn.chinamobile.com",
        "cache.ott.hnbblive.itv.cmvideo.cn=base-v4-free-mghy.e.cdn.chinamobile.com"
    ],
    "flags": [
        "youku", "优酷", "优 酷", "优酷视频", "qq", "腾讯", "腾 讯", "腾讯视频",
        "iqiyi", "qiyi", "奇艺", "爱奇艺", "爱 奇 艺", "m1905", "xigua",
        "letv", "leshi", "乐视", "乐 视", "sohu", "搜狐", "搜 狐", "搜狐视频",
        "tudou", "pptv", "mgtv", "芒果", "imgo", "芒果TV", "芒 果 T V",
        "bilibili", "哔 哩", "哔 哩 哔 哩"
    ],
    "ijk": [
        {"group": "软解码", "options": [
            {"category": 4, "name": "opensles", "value": "0"},
            {"category": 4, "name": "overlay-format", "value": "842225234"},
            {"category": 4, "name": "framedrop", "value": "1"},
            {"category": 4, "name": "soundtouch", "value": "1"},
            {"category": 4, "name": "start-on-prepared", "value": "1"},
            {"category": 1, "name": "http-detect-range-support", "value": "0"},
            {"category": 1, "name": "fflags", "value": "fastseek"},
            {"category": 2, "name": "skip_loop_filter", "value": "48"},
            {"category": 4, "name": "reconnect", "value": "1"},
            {"category": 4, "name": "enable-accurate-seek", "value": "0"},
            {"category": 4, "name": "mediacodec", "value": "0"},
            {"category": 4, "name": "mediacodec-auto-rotate", "value": "0"},
            {"category": 4, "name": "mediacodec-handle-resolution-change", "value": "0"},
            {"category": 4, "name": "mediacodec-hevc", "value": "0"},
            {"category": 1, "name": "dns_cache_timeout", "value": "600000000"}
        ]},
        {"group": "硬解码", "options": [
            {"category": 4, "name": "opensles", "value": "0"},
            {"category": 4, "name": "overlay-format", "value": "842225234"},
            {"category": 4, "name": "framedrop", "value": "1"},
            {"category": 4, "name": "soundtouch", "value": "1"},
            {"category": 4, "name": "start-on-prepared", "value": "1"},
            {"category": 1, "name": "http-detect-range-support", "value": "0"},
            {"category": 1, "name": "fflags", "value": "fastseek"},
            {"category": 2, "name": "skip_loop_filter", "value": "48"},
            {"category": 4, "name": "reconnect", "value": "1"},
            {"category": 4, "name": "enable-accurate-seek", "value": "0"},
            {"category": 4, "name": "mediacodec", "value": "1"},
            {"category": 4, "name": "mediacodec-auto-rotate", "value": "1"},
            {"category": 4, "name": "mediacodec-handle-resolution-change", "value": "1"},
            {"category": 4, "name": "mediacodec-hevc", "value": "1"},
            {"category": 1, "name": "dns_cache_timeout", "value": "600000000"}
        ]}
    ],
    "ads": ["static-mozai.4gtv.tv"]
}


# ==================== 原有工具函数（完整保留） ====================

def normalize_url(url):
    try:
        p = urlparse(url.strip())
        return urlunparse(p._replace(
            scheme=p.scheme.lower(), netloc=p.netloc.lower(),
            path=p.path.rstrip("/"), fragment=""))
    except Exception:
        return url.strip()


def format_file_size(n):
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f}K"
    return f"{n / (1024 * 1024):.1f}M"


def get_unique_name(base, used):
    if base not in used:
        used.add(base)
        return base
    idx = 1
    while True:
        name = f"{base}{idx}线"
        if name not in used:
            used.add(name)
            return name
        idx += 1


def file_stem(name):
    # 先 NFKC（②→2、全角→半角），再只保留中文/英文/数字
    clean_stem = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '',
                        unicodedata.normalize("NFKC", name)).strip()
    return clean_stem or "live"


def assign_stems(lives):
    # 按聚合顺序给全部条目分配不重复的 stem（不区分大小写，撞名加 _2、_3），
    # 不看下载成败，保证同一来源每天落到同一个文件名
    used = set()
    stems = {}
    for live in lives:
        base = file_stem(live["name"])
        stem, idx = base, 2
        while stem.lower() in used:
            stem = f"{base}_{idx}"
            idx += 1
        used.add(stem.lower())
        stems[live["name"]] = stem
    return stems


def ensure_suffix(name):
    if Path(name).suffix:
        return name
    return name + ".txt"


# ---------- 下载相关（完整保留） ----------
def build_headers(ua):
    headers = dict(TVBOX_HEADERS)
    headers["User-Agent"] = (
        ua.strip() if ua and isinstance(ua, str) and ua.strip()
        else TVBOX_UAS[int(time.time()) % len(TVBOX_UAS)]
    )
    return headers


class DownloadAborted(Exception):
    """响应是音视频流，或超出体积/时长上限，重试无意义"""


def is_media_type(ctype):
    # m3u/m3u8/pls 有时也挂在 audio/、video/ 下，需排除
    return ctype.startswith(("video/", "audio/")) and not any(
        k in ctype for k in ("mpegurl", "scpls"))


def looks_like_media(head):
    # FLV 文件头；MPEG-TS 每 188 字节一个 0x47 同步字节（文本里不会出现 NUL）
    if head[:4] == b"FLV\x01":
        return True
    return (len(head) > 376 and head[0] == head[188] == head[376] == 0x47
            and b"\x00" in head[:377])


def read_limited(resp):
    ctype = resp.headers.get("Content-Type", "").lower()
    if is_media_type(ctype):
        raise DownloadAborted(f"媒体流 Content-Type: {ctype}")
    deadline = time.time() + MAX_DOWNLOAD_SECONDS
    buf = bytearray()
    checked = False
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        buf.extend(chunk)
        if not checked and len(buf) > 376:
            checked = True
            if looks_like_media(buf):
                raise DownloadAborted("响应内容是 FLV/TS 视频流")
        if len(buf) > MAX_DOWNLOAD_BYTES:
            raise DownloadAborted(f"超过 {format_file_size(MAX_DOWNLOAD_BYTES)} 上限")
        if time.time() > deadline:
            raise DownloadAborted(f"下载超过 {MAX_DOWNLOAD_SECONDS}s")
    if not checked and looks_like_media(buf):
        raise DownloadAborted("响应内容是 FLV/TS 视频流")
    return bytes(buf)


def run_with_deadline(func, seconds, *args):
    # iter_content 要凑满一个 chunk 才返回，慢速流靠循环内计时中止不了，
    # 放到后台线程执行，主线程到点直接放弃
    box = {}

    def worker():
        try:
            box["result"] = func(*args)
        except BaseException as e:
            box["error"] = e

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise DownloadAborted(f"下载超过 {seconds}s")
    if "error" in box:
        raise box["error"]
    return box["result"]


def fetch_once(url, headers, timeout):
    with requests.get(url, headers=headers, timeout=timeout,
                      allow_redirects=True, verify=True,
                      stream=True) as resp:
        resp.raise_for_status()
        return read_limited(resp)


def fetch_url(url, ua, timeout=DOWNLOAD_TIMEOUT):
    headers = build_headers(ua)
    last_exc = None
    for retry in range(MAX_RETRIES):
        try:
            return run_with_deadline(fetch_once, MAX_DOWNLOAD_SECONDS,
                                     url, headers, timeout)
        except DownloadAborted as e:
            if DEBUG:
                print(f"      [abort] {url}: {e}")
            raise
        except Exception as e:
            last_exc = e
            if DEBUG and retry == MAX_RETRIES - 1:
                import traceback
                traceback.print_exc()
            if retry < MAX_RETRIES - 1:
                time.sleep(1)
    raise last_exc


def parse_urls_from_text(text):
    urls = []
    seen = set()
    for raw in re.findall(r'https?://\S+', text):
        u = raw.strip().strip('"').strip("'").rstrip(',').rstrip(')').rstrip(';')
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
    return urls


def derive_filename(base_name, url):
    path = urlparse(url).path
    fname = Path(path).name
    if not fname:
        return ensure_suffix(base_name)
    stem = Path(fname).stem
    suffix = Path(fname).suffix
    if stem and suffix:
        return f"{base_name}{suffix}"
    return ensure_suffix(base_name)


# ---------- 核心：下载单个直播源（完整保留） ----------
def fetch_live(live, _chain=None):
    # 只做网络请求，可在线程池中并发执行；返回 (ok, content, final_url)
    name = live["name"]
    orig_url = live["url"]
    ua = live.get("ua", "")
    _chain = _chain or []

    target = orig_url if not _chain else _chain[-1]

    try:
        content = fetch_url(target, ua)
    except Exception:
        return False, b"", target

    text = content.decode("utf-8", errors="replace")
    urls = parse_urls_from_text(text)

    if len(urls) == 1 and urls[0] != orig_url and urls[0] not in _chain:
        if DEBUG:
            print(f"      [unwrap] {target} -> {urls[0]}")
        new_chain = _chain + [urls[0]]
        if len(new_chain) <= MAX_UNWRAP_DEPTH:
            ok, sub_content, sub_url = fetch_live(
                {"name": name, "url": orig_url, "ua": ua}, new_chain)
            if ok:
                return ok, sub_content, sub_url

    return True, content, target


def save_live(stem, content, final_url):
    # stem 由 assign_stems 预先分配（已净化、不重复），后缀由最终 URL 决定
    disk_filename = derive_filename(stem, final_url)

    # 原样写出：不能在开头加任何行，播放器只从第一行读取节目单(x-tvg-url)和回看配置，
    # txt 格式的列表也会因为多出的 #EXTM3U 被误认成 M3U
    OUTPUT_LIVE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_LIVE_DIR / disk_filename
    with open(out_path, "wb") as f:
        f.write(content)

    return disk_filename


# ---------- 扫描与聚合（完整保留） ----------
def scan_interfaces():
    print("\n[1/6] 扫描接口文件，提取 lives ...")
    all_lives = []
    used_urls = set()

    if not SCAN_DIR.exists():
        print(f"  目录不存在: {SCAN_DIR}")
        return all_lives

    for json_file in SCAN_DIR.glob("*.json"):
        if json_file.name in AGGREGATE_OUTPUTS:
            continue
        source = json_file.stem
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  跳过 {json_file.name}: {e}")
            continue

        lives = data.get("lives", [])
        if not isinstance(lives, list):
            continue

        valid = 0
        for item in lives:
            if not isinstance(item, dict):
                continue
            item_name = item.get("name", "").strip()
            item_url = item.get("url", "").strip()
            if not item_name or not item_url:
                continue
            if not item_url.startswith(("http://", "https://")):
                continue

            norm = normalize_url(item_url)
            if norm in used_urls:
                continue
            used_urls.add(norm)

            all_lives.append({
                "name": item_name,
                "url": item_url,
                "ua": item.get("ua", ""),
                "source": source,
            })
            valid += 1
        print(f"  {json_file.name}: {valid} 条")

    print(f"  合计（去重后）: {len(all_lives)}")
    return all_lives


def aggregate(lives):
    print("\n[2/6] 聚合命名 ...")
    used_names = set()
    aggregated = []

    for item in lives:
        base = item["name"]
        item["name"] = get_unique_name(base, used_names)
        aggregated.append(item)
        if len(aggregated) <= 10:
            print(f"      {len(aggregated)}. {item['name']}  <=  {item['url'][:60]}")
    if len(aggregated) > 10:
        print(f"      ... 共 {len(aggregated)} 条")

    OUTPUT_LIVE_DIR.mkdir(parents=True, exist_ok=True)
    with open(AGGREGATE_JSON, "w", encoding="utf-8") as f:
        json.dump({"lives": aggregated}, f, ensure_ascii=False, indent=2)
    print(f"  索引 -> {AGGREGATE_JSON}")

    return aggregated


def batch_download(lives):
    print(f"\n[3/6] 下载直播源 ...")
    print(f"  输出目录: {OUTPUT_LIVE_DIR}")
    print(f"  并发数: {DOWNLOAD_WORKERS}")
    results = {}
    fail = []
    stems = assign_stems(lives)

    # 网络请求并发；结果按原顺序取回，落盘和日志顺序与串行时一致
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        fetched = pool.map(fetch_live, lives)
        for idx, (live, (ok, content, final_url)) in enumerate(zip(lives, fetched), 1):
            size = len(content) if ok else 0
            disk_filename = save_live(stems[live["name"]], content, final_url) if ok else ""
            results[live["name"]] = (ok, size, disk_filename, final_url)
            status = "ok" if ok else "FAIL"
            size_str = format_file_size(size) if ok else "0B"
            print(f"  [{idx}/{len(lives)}] {live['name']} {status} ({size_str})")
            if not ok:
                fail.append(live["name"])

    ok_count = sum(1 for v in results.values() if v[0])
    print(f"\n  完成: {ok_count}/{len(lives)} 成功")
    if fail:
        print(f"  失败: {', '.join(fail)}")

    return results


def generate_livelist(lives, results):
    print("\n[4/6] 生成/合并 livelist.txt ...")

    # 按文件名索引；历史上同名有多行时保留靠前、也就是较新的那条
    old_records = {}
    if LIVELIST_PATH.exists():
        with open(LIVELIST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split("|")
                    old_records.setdefault(parts[0], line)

    new_records = {}
    for live in lives:
        name = live["name"]
        if name not in results or not results[name][0]:
            continue
        _, size, disk_filename, final_url = results[name]
        source = Path(live['source']).stem
        ua = (live.get("ua") or "").strip()
        ua_field = ua if ua else "null"
        line = f"{disk_filename}|{TODAY}|{format_file_size(size)}|{live['url']}|{source}|{ua_field}|"
        new_records[disk_filename] = line

    # 按文件名匹配：本次写出的文件用新记录，本次没更新到的文件保留旧记录
    kept = [line for fn, line in old_records.items() if fn not in new_records]
    final_lines = list(new_records.values()) + kept

    with open(LIVELIST_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(final_lines))

    print(f"  -> {LIVELIST_PATH}")
    print(f"  更新: {len(new_records)}, 保留旧记录: {len(kept)}")


# ==================== 新增功能 ====================

def scan_sites_all():
    """扫描所有接口JSON的sites数组，提取 type 0/1 和 .py 结尾的站"""
    print("\n[5/6] 扫描接口文件，提取 sites ...")
    cj_items = []       # type 0/1
    py_items = []       # api 以 .py 结尾
    cj_urls = set()
    py_urls = set()

    for json_file in SCAN_DIR.glob("*.json"):
        # 跳过聚合输出自身，避免循环
        if json_file.name in AGGREGATE_OUTPUTS:
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  跳过 {json_file.name}: {e}")
            continue

        sites = data.get("sites", [])
        if not isinstance(sites, list):
            continue

        for s in sites:
            if not isinstance(s, dict):
                continue
            key = str(s.get("key", "")).strip()
            name = str(s.get("name", "")).strip()
            stype = s.get("type")
            api = str(s.get("api", "")).strip()

            if not key or not name or not api:
                continue

            norm_api = normalize_url(api)

            # type 0/1 -> 采集站
            if stype in (0, 1):
                if norm_api in cj_urls:
                    continue
                cj_urls.add(norm_api)
                cj_items.append({
                    "key": key,
                    "name": name,
                    "type": int(stype),
                    "api": api,
                })

            # api 以 .py 结尾
            if api.lower().endswith(".py"):
                if norm_api in py_urls:
                    continue
                py_urls.add(norm_api)
                py_items.append({
                    "key": key,
                    "name": name,
                    "type": int(stype) if isinstance(stype, int) else 3,
                    "api": api,
                    "searchable": 1,
                    "quickSearch": 1,
                    "filterable": 1,
                })

    print(f"  采集站(type 0/1): {len(cj_items)} 条")
    print(f"  py站(.py): {len(py_items)} 条")
    return cj_items, py_items


def write_text_list(path, items):
    """写入 cjlist.txt / pylist.txt，旧记录保留，新记录覆盖"""
    old_records = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    old_records[line.split("|")[0]] = line

    new_records = {}
    for it in items:
        line = f"{it['key']}|{it['name']}|type: {it['type']}|api: {it['api']}"
        new_records[it['key']] = line

    # 合并：新的覆盖旧的，旧的未覆盖的保留
    final_lines = list(new_records.values())
    for k, line in old_records.items():
        if k not in new_records:
            final_lines.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(final_lines) + "\n")

    print(f"  -> {path.name} (新增 {len(new_records)}, 保留旧 {len(old_records)-len(new_records)})")


def build_agg_json(path, new_sites):
    """将站点列表插入模板，输出聚合JSON，旧文件中的非模板站点保留"""
    # 读旧文件或初始化模板
    if path.exists():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            cfg = json.loads(json.dumps(TEMPLATE_CONFIG, ensure_ascii=False))
    else:
        cfg = json.loads(json.dumps(TEMPLATE_CONFIG, ensure_ascii=False))

    # 确保 sites 字段存在
    if "sites" not in cfg or not isinstance(cfg["sites"], list):
        cfg["sites"] = []

    # 用 key 做去重映射
    site_map = {}
    for s in cfg["sites"]:
        if isinstance(s, dict) and s.get("key"):
            site_map[s["key"]] = s

    # 新站点覆盖同名
    for s in new_sites:
        site_map[s["key"]] = s

    # 保持原顺序 + 新站追加
    ordered = []
    seen = set()
    for s in cfg["sites"]:
        k = s.get("key") if isinstance(s, dict) else None
        if k and k in site_map and k not in seen:
            ordered.append(site_map[k])
            seen.add(k)
    for k, s in site_map.items():
        if k not in seen:
            ordered.append(s)
            seen.add(k)

    cfg["sites"] = ordered

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print(f"  -> {path.name}")


# ---------- 主入口 ----------
def main():
    start = time.time()
    import argparse
    ap = argparse.ArgumentParser(description="TVBox 直播源+采集站+py站 聚合器")
    ap.add_argument("--debug", action="store_true", help="输出详细调试日志")
    ap.add_argument("--force", action="store_true", help="强制执行")
    ap.add_argument("--skip-lives", action="store_true",
                    help="只生成直播聚合JSON，不下载直播源（下载由 live下载器.py 负责）")
    args = ap.parse_args()
    global DEBUG
    DEBUG = args.debug

    print("=" * 60)
    print("TVBox Live + Sites aggregator")
    print("=" * 60)

    # ---- 原有 lives 流程 ----
    lives = scan_interfaces()
    if not lives:
        print("\n没有有效的直播源，跳过下载")
    else:
        aggregated = aggregate(lives)
        if args.skip_lives:
            print("\n[3/6][4/6] --skip-lives：跳过直播源下载和 livelist.txt（由 live下载器.py 负责）")
        else:
            results = batch_download(aggregated)
            generate_livelist(aggregated, results)

    # ---- 新增 sites 流程 ----
    cj_items, py_items = scan_sites_all()

    # 5/6 写 cjlist.txt
    print("\n[5/6] 生成 cjlist.txt ...")
    write_text_list(CJ_LIST_PATH, cj_items)

    # 6/6 写 pylist.txt + 两个聚合JSON
    print("\n[6/6] 生成 pylist.txt + 聚合JSON ...")
    write_text_list(PY_LIST_PATH, py_items)
    build_agg_json(PY_AGG_JSON, py_items)

    # 采集站转成标准格式后插入模板
    cj_sites_for_json = []
    for it in cj_items:
        cj_sites_for_json.append({
            "key": it["key"],
            "name": it["name"],
            "type": it["type"],
            "api": it["api"],
            "searchable": 1,
            "quickSearch": 1,
            "filterable": 1,
        })
    build_agg_json(CJ_AGG_JSON, cj_sites_for_json)

    print("\n" + "=" * 60)
    print(f"全部完成，耗时 {time.time() - start:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
