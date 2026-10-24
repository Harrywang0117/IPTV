# 直播订阅

由 `python/直播聚合订阅.py` 每天自动生成，最近更新：2026-10-25 02:48（北京时间）。

## 订阅地址

| 订阅 | 频道 | 线路 | 测通率 | 地址 |
|---|---:|---:|---:|---|
| 体育赛事·咪咕（今天/明天/昨天） | 358 | 366 | 36.8% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/sports-events.m3u |
| 体育频道 | 105 | 289 | 24.4% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/sports.m3u |
| 央视卫视 | 170 | 1063 | 62.8% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/cctv.m3u |
| 港澳台 | 532 | 1563 | 45.0% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/hmt.m3u |
| 地方台·华北东北西北 | 301 | 1005 | 35.4% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/local-north.m3u |
| 地方台·华东 | 388 | 1260 | 36.4% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/local-east.m3u |
| 地方台·中南西南 | 494 | 1766 | 23.6% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/local-south.m3u |
| 少儿（频道 + 动画轮播） | 129 | 450 | 42.1% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/kids.m3u |
| 专题频道 | 663 | 1876 | 46.2% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/theme.m3u |
| 影视轮播（电影/电视剧/纪录片） | 662 | 2043 | 40.2% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/vod-movie.m3u |
| 综艺轮播（综艺/相声小品/MV/其他） | 246 | 518 | 44.8% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/vod-show.m3u |
| 全部频道（合并订阅） | 4048 | 12199 | 40.0% | https://raw.githubusercontent.com/Harrywang0117/IPTV/main/iptv/all.m3u |

「测通率」= 本轮实际测通的线路（ok）/ 该文件探测前的线路总数；测不了（超时、403、5xx）的保留，明确失效（404/410/服务器报错/登录提示/HTML 错误页）的直接删掉。

同一条线路只会出现在一个订阅里（赛事 > 频道分类 > 体育，体育里的重复已归到对应频道订阅），把多个订阅一起加进「聚合配置」不会出现重复线路。

最后一行 `all.m3u` 是把上面 11 个订阅按频道名合并成一个链接（约 1.5 万条线路），任何播放器/电视都能直接订阅；APTV/Apple TV 之间仍建议用「聚合配置」+ iCloud 同步。

国内访问 raw.githubusercontent.com 不稳定时，在地址前加 `https://ghfast.top/`。

**APTV 里显示成「一个频道 + 多条线路」**：先把订阅添加为「订阅配置」，再新建一个「聚合配置」只勾选这个订阅。同名频道会合并成一个，右上角显示备选数量，播放失败自动切换（超时在 设置-高级设置-播放超时时间 里改）。

## 主播直播（实时地址，直接订阅）

主播间只有开播时能看，快照没有意义；下面是原始的实时地址，打开就是当前在播的房间。虎牙/斗鱼/YY 的「一起看」轮播房间也在这些实时地址里，不再生成每日快照。

| 名称 | 地址 |
|---|---|
| B站直播 | https://ztha.top/TVBox/lib/bililive.m3u |
| 📡虎牙 | https://sub.ottiptv.cc/huyayqk.m3u |
| 📡斗鱼 | https://sub.ottiptv.cc/douyuyqk.m3u |
| 📡YY | https://sub.ottiptv.cc/yylunbo.m3u |
| 📡BL | https://sub.ottiptv.cc/bililive.m3u |
| B站直播1线 | https://file.icve.com.cn/file_doc/220/1003/370FAE41BD301F89BA1FCD6FDB8D5BD6.m3u |
| 👖裤佬抖音直播 | https://douyin.445569.xyz/live.m3u |
| 👖裤佬快手直播 | https://kuaishou.445569.xyz/list.m3u |
| 👖裤佬虎牙直播 | https://huya.445569.xyz/live.m3u |
| 👖裤佬斗鱼直播 | https://douyu.445569.xyz/live.m3u |
| 👖裤佬酷狗直播 | https://kugou.445569.xyz/live.m3u |
| 👖裤佬来疯直播 | https://laifeng.445569.xyz/live.m3u |
| 👖裤佬百战直播 | https://baizhan.445569.xyz/live.m3u |
| 👖裤佬YY直播 | https://yy.445569.xyz/live.m3u |
| 👖裤佬Twitch直播 | https://twitch.445569.xyz/live.m3u |
| 👖裤佬TikTok直播 | https://tiktok.445569.xyz/live.m3u |
| B站直播2线 | https://yun.urldwz.com/f/9XBkHK/bilibili.m3u |
