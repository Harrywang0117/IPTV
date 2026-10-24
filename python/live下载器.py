#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TVBox 直播源聚合下载器。

功能：
1. 扫描 tvbox/ 下所有接口 JSON，从 lives 数组提取有 name+url 的全部条目
2. 不限制 type，不做任何过滤，URL 去重
3. 模拟 TVBox 环境下载（UA 伪装、指纹），失败重试
4. 套壳自动展开（最多5层），最终层写出播放列表文件
5. 文件名净化：只保留中文/英文/数字，后缀不受影响
6. livelist.txt 第一列与磁盘真实文件名完全对齐
7. 不写伴随 txt 文件，UA 为空输出 null
"""

import ipaddress
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
AGGREGATE_JSON = SCAN_DIR / "海量直播线路.json"
LIVELIST_PATH = REPO_ROOT / "livelist.txt"
# 各脚本生成的聚合输出，扫描时跳过，避免互相回流（名称叠加成「1线1线」）
AGGREGATE_OUTPUTS = {"海量直播线路.json", "海量直播聚合接口.json",
                     "海量py聚合接口.json", "海量采集聚合接口.json"}

DOWNLOAD_TIMEOUT = 25
DOWNLOAD_WORKERS = 8                    # 并发下载线程数
MAX_RETRIES = 3
MAX_UNWRAP_DEPTH = 5
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024   # 单个文件体积上限
MAX_DOWNLOAD_SECONDS = 300              # 单次请求总时长上限（timeout 只限制读间隔）
TODAY = datetime.now().strftime("%Y%m%d")
DEBUG = False


# ---------- 工具函数 ----------
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
    """名称 → 文件名 stem：先 NFKC（②→2、全角→半角），再只保留中文/英文/数字。"""
    clean_stem = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '',
                        unicodedata.normalize("NFKC", name)).strip()
    return clean_stem or "live"


def assign_stems(lives):
    """
    按聚合顺序给每条直播源分配不重复的文件名 stem（不区分大小写，撞名加 _2、_3）。
    对全部条目分配、不看下载成败，保证同一来源每天落到同一个文件名。
    """
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
    """无后缀补 .txt"""
    if Path(name).suffix:
        return name
    return name + ".txt"


# ---------- 下载相关 ----------
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
    """m3u/m3u8/pls 有时也挂在 audio/、video/ 下，需排除。"""
    return ctype.startswith(("video/", "audio/")) and not any(
        k in ctype for k in ("mpegurl", "scpls"))


def looks_like_media(head):
    """FLV 文件头；MPEG-TS 每 188 字节一个 0x47 同步字节（文本里不会出现 NUL）。"""
    if head[:4] == b"FLV\x01":
        return True
    return (len(head) > 376 and head[0] == head[188] == head[376] == 0x47
            and b"\x00" in head[:377])


def read_limited(resp):
    """流式读取响应体，遇到视频流或超出体积/时长上限即中止。"""
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
    """后台线程执行 func，主线程到点直接放弃。

    iter_content 要凑满一个 chunk 才返回，慢速流靠循环内计时中止不了。
    """
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
    """单次流式请求。"""
    with requests.get(url, headers=headers, timeout=timeout,
                      allow_redirects=True, verify=True,
                      stream=True) as resp:
        resp.raise_for_status()
        return read_limited(resp)


def fetch_url(url, ua, timeout=DOWNLOAD_TIMEOUT):
    """模拟 TVBox 指纹请求，带重试；视频流/超限直接放弃不重试。"""
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
    """从文本中提取 HTTP/HTTPS URL。"""
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
    """由最终 URL 决定输出文件名（带后缀）。"""
    path = urlparse(url).path
    fname = Path(path).name
    if not fname:
        return ensure_suffix(base_name)
    stem = Path(fname).stem
    suffix = Path(fname).suffix
    if stem and suffix:
        return f"{base_name}{suffix}"
    return ensure_suffix(base_name)


# ---------- 核心：下载单个直播源 ----------
def fetch_live(live, _chain=None):
    """
    只做网络请求，可在线程池中并发执行。
    返回值：(ok, content, final_url)
    """
    name = live["name"]
    orig_url = live["url"]
    ua = live.get("ua", "")
    _chain = _chain or []

    target = orig_url if not _chain else _chain[-1]

    # 下载
    try:
        content = fetch_url(target, ua)
    except Exception:
        return False, b"", target

    text = content.decode("utf-8", errors="replace")
    urls = parse_urls_from_text(text)

    # 套壳展开：只有1条URL且不同于原始请求
    if len(urls) == 1 and urls[0] != orig_url and urls[0] not in _chain:
        if DEBUG:
            print(f"      [unwrap] {target} -> {urls[0]}")
        new_chain = _chain + [urls[0]]
        if len(new_chain) <= MAX_UNWRAP_DEPTH:
            ok, sub_content, sub_url = fetch_live(
                {"name": name, "url": orig_url, "ua": ua}, new_chain)
            if ok:
                return ok, sub_content, sub_url

    # 当前层就是最终有播放列表内容的一层
    return True, content, target


def save_live(stem, content, final_url):
    """
    写出播放列表文件，返回磁盘上真实写出的文件名。
    stem 由 assign_stems 预先分配（已净化、不重复），后缀由最终 URL 决定。
    """
    disk_filename = derive_filename(stem, final_url)

    # 原样写出：不能在开头加任何行，播放器只从第一行读取节目单(x-tvg-url)和回看配置，
    # txt 格式的列表也会因为多出的 #EXTM3U 被误认成 M3U
    OUTPUT_LIVE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_LIVE_DIR / disk_filename
    with open(out_path, "wb") as f:
        f.write(content)

    return disk_filename


# ---------- 扫描与聚合 ----------
def scan_interfaces():
    print("\n[1/4] 扫描接口文件，提取 lives ...")
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
            # 有名称且有URL，全部提取
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
    print("\n[2/4] 聚合命名 ...")
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


# ---------- 批量下载 ----------
def batch_download(lives):
    print(f"\n[3/4] 下载直播源 ...")
    print(f"  输出目录: {OUTPUT_LIVE_DIR}")
    print(f"  并发数: {DOWNLOAD_WORKERS}")
    results = {}  # name -> (ok, size, disk_filename, final_url)
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


# ---------- 生成 livelist.txt ----------
def generate_livelist(lives, results):
    print("\n[4/4] 生成/合并 livelist.txt ...")

    # 读取旧记录（按文件名索引；历史上同名有多行时保留靠前、也就是较新的那条）
    old_records = {}
    if LIVELIST_PATH.exists():
        with open(LIVELIST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split("|")
                    old_records.setdefault(parts[0], line)

    # 构建新记录
    new_records = {}
    for live in lives:
        name = live["name"]
        if name not in results or not results[name][0]:
            continue
        _, size, disk_filename, final_url = results[name]
        source = Path(live['source']).stem
        ua = (live.get("ua") or "").strip()
        ua_field = ua if ua else "null"

        # 第一列 = 磁盘真实文件名，直接复用，不做二次计算
        line = f"{disk_filename}|{TODAY}|{format_file_size(size)}|{live['url']}|{source}|{ua_field}|"
        new_records[disk_filename] = line

    # 合并：按文件名匹配，本次写出的文件用新记录，本次没更新到的文件保留旧记录
    kept = [line for fn, line in old_records.items() if fn not in new_records]
    final_lines = list(new_records.values()) + kept

    with open(LIVELIST_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(final_lines))

    print(f"  -> {LIVELIST_PATH}")
    print(f"  更新: {len(new_records)}, 保留旧记录: {len(kept)}")


# ---------- 主入口 ----------
def main():
    start = time.time()
    import argparse
    ap = argparse.ArgumentParser(description="TVBox 直播源聚合器")
    ap.add_argument("--debug", action="store_true", help="输出详细调试日志")
    ap.add_argument("--force", action="store_true", help="强制执行")
    args = ap.parse_args()
    global DEBUG
    DEBUG = args.debug

    print("=" * 60)
    print("TVBox Live aggregator")
    print("=" * 60)

    lives = scan_interfaces()
    if not lives:
        print("\n没有有效的直播源，退出")
        return

    aggregated = aggregate(lives)
    results = batch_download(aggregated)
    generate_livelist(aggregated, results)

    print("\n" + "=" * 60)
    print(f"完成，耗时 {time.time() - start:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
