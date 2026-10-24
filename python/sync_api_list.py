#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日同步上游接口清单（api_list.json）

在 GitHub Actions 的「两日一更备分接口」工作流里每天运行一次（cwd 是仓库根目录，
但本脚本的路径一律按脚本自身位置推导，不依赖 cwd）。

上游默认 https://raw.githubusercontent.com/lubin776/0/main/api_list.json，
可以用环境变量 API_LIST_UPSTREAM 覆盖（本地自测时指向假服务器）。

安全原则：
- 下载失败、JSON 损坏、条数异常等任何校验不通过 → 保留本地旧文件，
  输出 ::warning::，退出码 0，绝不让工作流失败；
- 校验通过且内容有变化才覆盖 api_list.json；
- 永远不修改 api_list.local.json（那是用户自己的补充清单）。
"""

import json
import os
import sys
import time
import urllib.request

DEFAULT_UPSTREAM = "https://raw.githubusercontent.com/lubin776/0/main/api_list.json"
TIMEOUT = 30          # 单次请求超时（秒）
RETRIES = 2           # 失败后重试次数（总共最多尝试 3 次）
MIN_API_COUNT = 30    # 上游清单至少要有这么多条
MIN_KEEP_RATIO = 0.5  # 并且不少于本地现有条数的 50%（防止上游写坏把清单清空）

# 路径全部按脚本位置推导：python/sync_api_list.py → 仓库根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_LIST_PATH = os.path.join(ROOT_DIR, "api_list.json")
API_LIST_LOCAL_PATH = os.path.join(ROOT_DIR, "api_list.local.json")


def _warn(msg):
    """输出 GitHub Actions 警告（只提示，不会让任务失败）"""
    print(f"::warning::{msg}", flush=True)


def _load_json(path):
    """读取 JSON 文件；不存在或解析失败返回 None"""
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None


def _api_list_count(cfg):
    """取配置里 API_LIST 的条数，非法配置返回 0"""
    if isinstance(cfg, dict) and isinstance(cfg.get("API_LIST"), list):
        return len(cfg["API_LIST"])
    return 0


def _is_http_url(value):
    """是否是 http(s) 地址（允许地址前后有空白）"""
    return isinstance(value, str) and value.strip().lower().startswith(("http://", "https://"))


def _validate_config(cfg, local_count):
    """
    校验上游清单，返回 (是否通过, 原因列表)

    通过条件：
    1. 是 JSON 对象，且有 API_LIST / API_MIRRORS 两个字段；
    2. API_LIST 是列表，每项是 [名称, http(s) 地址, ...]：名称非空，
       第 2 个元素起都是 http(s) 地址（上游部分接口会在同一项里写多条地址，
       所以允许长度大于 2）；
    3. API_LIST 条数 ≥ MIN_API_COUNT，且不少于本地现有条数的 MIN_KEEP_RATIO。
    """
    errors = []
    if not isinstance(cfg, dict):
        return False, ["顶层不是 JSON 对象"]
    if "API_LIST" not in cfg:
        errors.append("缺少 API_LIST 字段")
    if "API_MIRRORS" not in cfg:
        errors.append("缺少 API_MIRRORS 字段")
    if errors:
        return False, errors

    api_list = cfg["API_LIST"]
    if not isinstance(api_list, list):
        return False, ["API_LIST 不是列表"]
    for idx, item in enumerate(api_list):
        loc = f"API_LIST[{idx}]"
        if not isinstance(item, (list, tuple)):
            errors.append(f"{loc} 不是 [名称, 地址] 列表")
        elif len(item) < 2:
            errors.append(f"{loc} 少于 2 个元素")
        else:
            if not isinstance(item[0], str) or not item[0].strip():
                errors.append(f"{loc} 名称为空")
            if not all(_is_http_url(u) for u in item[1:]):
                errors.append(f"{loc} 含非 http(s) 地址")
        if len(errors) >= 5:
            errors.append("……（更多错误已省略）")
            break

    mirrors = cfg["API_MIRRORS"]
    if not isinstance(mirrors, (dict, list)):
        errors.append("API_MIRRORS 既不是对象也不是列表")

    count = len(api_list)
    if count < MIN_API_COUNT:
        errors.append(f"API_LIST 只有 {count} 条，少于下限 {MIN_API_COUNT} 条")
    if local_count > 0 and count < local_count * MIN_KEEP_RATIO:
        errors.append(
            f"API_LIST 只有 {count} 条，少于本地现有 {local_count} 条的 {MIN_KEEP_RATIO:.0%}"
        )
    return (not errors), errors


def _mirror_names(cfg):
    """取 API_MIRRORS 里的接口名集合（兼容 dict 和 [名称, [地址…]] 列表）"""
    mirrors = cfg.get("API_MIRRORS") if isinstance(cfg, dict) else None
    if isinstance(mirrors, dict):
        return {str(k) for k in mirrors.keys()}
    if isinstance(mirrors, list):
        names = set()
        for item in mirrors:
            if isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
                names.add(item[0])
        return names
    return set()


def _interface_names(cfg):
    """取清单里所有接口名（API_LIST + API_MIRRORS），用于对比新增/删除"""
    names = set()
    if not isinstance(cfg, dict):
        return names
    for item in cfg.get("API_LIST") or []:
        if isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
            names.add(item[0])
    names |= _mirror_names(cfg)
    return names


def _download(url):
    """下载上游清单文本；失败重试 RETRIES 次，最终仍失败则抛异常"""
    headers = {
        "User-Agent": "IPTV-api-list-sync/1.0 (+https://github.com/Harrywang0117/IPTV)",
        "Accept": "application/json,text/plain,*/*",
    }
    last_err = None
    for attempt in range(RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read()
            return raw.decode("utf-8-sig", errors="replace")
        except Exception as e:
            last_err = e
            if attempt < RETRIES:
                wait = 3 * (attempt + 1)
                print(f"  第 {attempt + 1} 次下载失败：{e}；{wait} 秒后重试")
                time.sleep(wait)
    raise RuntimeError(str(last_err))


def _write_config(cfg):
    """按项目现有风格写 api_list.json（中文不转义、2 空格缩进、结尾换行）
    先写临时文件再原子替换，避免中途失败留下半个坏文件。"""
    tmp_path = API_LIST_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp_path, API_LIST_PATH)


def main():
    upstream = os.environ.get("API_LIST_UPSTREAM", "").strip() or DEFAULT_UPSTREAM
    print("=" * 62)
    print("  同步上游接口清单 api_list.json")
    print("=" * 62)
    print(f"  上游地址: {upstream}")
    print(f"  本地文件: {API_LIST_PATH}")

    # 本地旧清单：既用来做「50% 下限」对比，也用来判断新增/删除的接口
    local_cfg = _load_json(API_LIST_PATH)
    if local_cfg is None and os.path.exists(API_LIST_PATH):
        _warn(f"本地 {API_LIST_PATH} 无法解析，本次按无本地清单处理")
    local_count = _api_list_count(local_cfg)
    print(f"  本地现有: {local_count} 条" + ("" if os.path.exists(API_LIST_PATH) else "（文件不存在）"))

    # 1. 下载上游清单
    try:
        text = _download(upstream)
    except Exception as e:
        _warn(f"下载上游清单失败，保留本地旧文件：{e}")
        return 0
    print(f"  下载完成: {len(text)} 字符")

    # 2. 解析 + 校验；任何一步失败都保留旧文件、只告警
    try:
        new_cfg = json.loads(text)
    except Exception as e:
        _warn(f"上游返回的不是合法 JSON，保留本地旧文件：{e}")
        return 0

    ok, errors = _validate_config(new_cfg, local_count)
    if not ok:
        for err in errors:
            _warn(f"上游清单校验失败：{err}")
        _warn("已保留本地旧文件 api_list.json（本次未更新）")
        return 0

    # 3. 对比新增/删除的接口名称（日志用）
    new_count = _api_list_count(new_cfg)
    old_names = _interface_names(local_cfg)
    new_names = _interface_names(new_cfg)
    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)
    print(f"  上游条数: {new_count}（本地 {local_count}）")
    print(f"  新增接口 {len(added)} 个" + (f"：{'、'.join(added)}" if added else ""))
    print(f"  删除接口 {len(removed)} 个" + (f"：{'、'.join(removed)}" if removed else ""))

    # 只比较 API_LIST / API_MIRRORS 的内容（忽略其它字段和 JSON 格式差异）
    old_core = None
    if isinstance(local_cfg, dict):
        old_core = {
            "API_LIST": local_cfg.get("API_LIST"),
            "API_MIRRORS": local_cfg.get("API_MIRRORS"),
        }
    new_core = {
        "API_LIST": new_cfg.get("API_LIST"),
        "API_MIRRORS": new_cfg.get("API_MIRRORS"),
    }
    if old_core == new_core:
        print("  ✓ 内容无变化，不写入文件")
        print("=" * 62)
        return 0

    # 4. 校验通过且内容有变化 → 覆盖 api_list.json
    try:
        _write_config(new_cfg)
    except Exception as e:
        _warn(f"写入 api_list.json 失败，保留本地旧文件：{e}")
        return 0
    print(f"  ✓ 已更新 {API_LIST_PATH}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # 兜底：任何意外都不让工作流失败
        _warn(f"同步脚本异常（已忽略，保留本地旧文件）：{e}")
        sys.exit(0)
