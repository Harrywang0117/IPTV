# IPTV 直播订阅（自动生成）

每天自动抓取 TVBox 接口里的直播源，逐条测线路，生成分类好的 IPTV 订阅（m3u）。

## 数据流

```
api_list.json（上游 TVBox 接口清单，每天从 lubin776/0 自动同步）
   → python/tvbox_get_api.py      抓每个接口的 JSON
   → python/live下载器.py          提取并下载所有直播源（tvbox/live + livelist.txt）
   → python/直播聚合订阅.py         分类 / 跨订阅去重 / 逐条测线路 → iptv/*.m3u
```

四个 GitHub Actions 按顺序链式执行：两日一更备分接口 → 每日解析在线本地包 → 每日聚合TVBox直播源 → 接口扫描处理工具。
（定时入口只有「两日一更备分接口」：`cron 5 16 * * *`，UTC 16:05 = 北京时间 00:05，GitHub 可能延迟 1~3 小时。）

## 订阅

完整列表和「测通率」见 [`iptv/README.md`](iptv/README.md)。常用：

- 体育赛事（咪咕）：`iptv/sports-events.m3u`
- 体育频道：`iptv/sports.m3u`
- 央视卫视：`iptv/cctv.m3u`
- 港澳台：`iptv/hmt.m3u`
- 地方台：`iptv/local-north.m3u` / `local-east.m3u` / `local-south.m3u`
- 少儿 / 专题 / 影视轮播 / 综艺轮播
- 全部频道合并：`iptv/all.m3u`

地址前缀：`https://raw.githubusercontent.com/Harrywang0117/IPTV/main/`
国内访问不稳定时前面加 `https://ghfast.top/`。

## 维护要点

- 改 `python/**` 或 `tvbox/**` 后推送，commit message 加 `[skip ci]`，避免触发「接口扫描处理工具」的 push 事件。
- 只想手动跑某一步：从哪一步触发，它和后面的会按顺序跑；不要同时点多个（并发组只保留 1 个）。
- 本地测试：
  ```bash
  python3 python/直播聚合订阅.py --out-dir /tmp/iptv_test
  ```
  `IPTV_PROBE_EVENTS=0` 可跳过线路探测，`IPTV_PROBE_BUDGET` 控制探测总时长（秒），`IPTV_DEDUPE=0` 可关闭跨订阅去重。
- 自己的 TVBox 接口补充写在 `api_list.local.json`，每天同步上游时不会被覆盖。

## 说明

- 直播源来自公开的 TVBox 接口聚合，版权归原平台所有；本仓库只做索引与整理。
- 明确失效的线路会被自动删除，「测不了」（超时/403/5xx）的保留（GitHub 机器在海外，可能会误判国内源）。
