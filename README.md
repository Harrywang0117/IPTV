# TVBox 接口与直播源聚合（自动生成）

每天自动同步上游 TVBox 接口清单，抓取各接口的配置和直播源，备份到本仓库。

> IPTV 直播订阅（咪咕赛事、地方台、港澳台）已迁到家里软路由上运行，不再由本仓库生成。

## 数据流

```
api_list.json（上游 TVBox 接口清单，每天从 lubin776/0 自动同步）
   → python/tvbox_get_api.py      抓每个接口的 JSON → tvbox/
   → python/ry下载器.py           解析在线本地包 → ry/
   → python/live下载器.py          提取并下载所有直播源 → tvbox/live/ + livelist.txt
   → python/接口扫描处理工具.py     生成聚合接口和采集 / py 站列表
```

四个 GitHub Actions 按顺序链式执行：两日一更备分接口 → 每日解析在线本地包 → 每日聚合TVBox直播源 → 接口扫描处理工具。
（定时入口只有「两日一更备分接口」：`cron 5 16 * * *`，UTC 16:05 = 北京时间 00:05，GitHub 可能延迟 1~3 小时。）

## 维护要点

- 改 `python/**` 或 `tvbox/**` 后推送，commit message 加 `[skip ci]`，避免触发「接口扫描处理工具」的 push 事件。
- 只想手动跑某一步：从哪一步触发，它和后面的会按顺序跑；不要同时点多个（并发组只保留 1 个）。
- 自己的 TVBox 接口补充写在 `api_list.local.json`，每天同步上游时不会被覆盖。

## 说明

- 内容来自公开的 TVBox 接口聚合，版权归原平台所有；本仓库只做索引与整理。
