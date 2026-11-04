# B 站接口与检索实现备忘

> 2026-11-04 核实。原文档仓库 `SocialSisterYi/bilibili-API-collect` 已于 2026-01-30 归档，路径仍可用；接口字段未发生 breaking change。实现按「签名 + 缓存 + 失败降级」设计。

## 1. 最小流程

```
SPI 取 buvid（可选） → nav 取 WBI key → search 取 bvid
→ view 取 pages 选 cid → player/v2 取 subtitles
→ subtitle_url 拉 JSON → 按 from/to 定位时间段
```

## 2. WBI 签名

- `GET https://api.bilibili.com/x/web-interface/nav`：无 Cookie 也返回 `code=-101` + `data.wbi_img`。
- `img_url` / `sub_url` 取文件名并去掉 `.png`，拼成 64 字符。
- 按 64 位 `mixinKeyEncTab` 重排，取前 32 位为 `mixin_key`。
- 参数加 `wts`（秒）→ 按 key 升序 → value 去掉 `!'()*` → URL 编码 → 拼 `mixin_key` → MD5 得 `w_rid`。
- 已知向量：
  - `7cd084941338484aae1ad9425b84077c` + `4932caff0ff746eab6f01bf08b70ac45` → `ea1db124af3c7062474693fa704f4ff8`
  - `bar=514&foo=114&wts=1702204169&zab=1919810` → `8f6f2b5b3d485fe1886cec6a0be8c5d4`

```python
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]
```

## 3. 搜索

`GET https://api.bilibili.com/x/web-interface/wbi/search/type`

| 参数 | 说明 |
|---|---|
| `search_type` | 必填，`video` |
| `keyword` | 必填 |
| `page` | 默认 1；`page=51` 仍返回 20 条 |
| `page_size` | 文档未写，实测 1–50；51/100 返回 `-400` |
| `order` | `totalrank` / `click` / `pubdate` / `dm` / `stow` / `scores` |

返回 `data.result[]` 关键字段：`bvid`、`title`（含 `<em class="keyword">`）、`author`、`play`、`description`、`tag`、`duration`、`pubdate`、`typename`。

坑：
- `title` 必须剥 HTML。
- `duration` 是 `MM:SS`，分钟可 >59（`144:46` = 8686 秒）。
- 缺 Referer 时可能返回 `code=0` 但 `data` 只有 `v_voucher`，没有 `result` —— 软拦截，必须识别为失败。

## 4. 详情

`GET https://api.bilibili.com/x/web-interface/view?bvid=...`

- `pages[]`：`cid`、`page`（从 1）、`part`、`duration`（秒）。
- `title`、`desc`、`owner.name`、`stat.view`、`stat.like`、`tname`。
- 不存在的 bvid 返回 `-400`，不是 `-404`。
- `tname` 可能为空串。

## 5. 播放器与字幕

`GET https://api.bilibili.com/x/player/wbi/v2?bvid=...&cid=...`

- `subtitle.subtitles[]`：`lan`、`lan_doc`、`subtitle_url`、`is_lock`、`type`、`ai_type`。
- 未登录时 `subtitles` 通常为空；AI 字幕必须登录。
- `subtitle_url` 是协议相对 `//aisubtitle.hdslb.com/...auth_key=...`，补 `https:`。
- `auth_key` 过期返回 403；可回退 `https://i0.hdslb.com/bfs/subtitle/<sha1>.json`（去 query）。
- 字幕 JSON：`body[]` 只有 `{from,to,location,content}`，`from/to` 为浮点秒，`content` 可含换行。

## 6. 风控与状态码

| 码 | 含义 | 处理 |
|---|---|---|
| `-352` | 风控校验失败（常带 `v_voucher`） | 修签名、补 buvid、降速重试 |
| `-412` | IP 拦截 / WAF | 停 10–30 分钟或换网络；不要死循环 |
| `-799` | 频率限制 | 降到 ≤1 req/s，指数退避 |
| `-400` | 参数错误 | 检查 page_size / bvid |
| `-403` | 权限/字幕过期 | 换匿名镜像或跳过字幕 |
| `-404` | 不存在 | 跳过 |
| `62002/62004/62012` | 稿件/权限状态 | 跳过 |

- 本机 Python `urllib` 可能因 TLS 指纹被 WAF 拦（412）；只有显式 `--allow-curl` 才会回退系统 `curl`。
- 本机若存在代理/抓包根证书，`urllib` 会报 `CERTIFICATE_VERIFY_FAILED`；**不会自动关闭校验**。用 `--ca-file` 指定根证书；确需关闭时显式 `--insecure`，该模式不发送 Cookie。
- 限速默认 1 req/s；搜索/详情/字幕缓存 7 天；失败指数退避。

## 7. 相关度打分

```
锚词覆盖：主锚词 0.65 + 其余锚词均分 0.35
基础分：0.75·标题 + 0.10·分P + 0.10·简介/标签 + 0.05·质量
字幕加分：有字幕且命中时 +0.20·字幕覆盖（只加分，不降低基础分）
门槛：默认 0.5；白名单 UP +0.08
```

硬规则：
1. 链接只能由接口返回的 `bvid`/`pages[].page`/字幕秒数拼成。
2. 每个知识点最多 1–2 条。
3. 只给 D 高或答错的知识点配视频。
4. 每条附匹配理由；没有达标结果只给搜索链接。

## 8. Cookie 安全

- 只从 `BILIBILI_COOKIE` 或 `--cookie-file` 读取。
- 不写 `study_state.json`、日志、报告、Git。
- 输出/错误里打码；只调用只读接口。
- 建议用专用小号；定期失效。

## 9. 参考

- `SocialSisterYi/bilibili-API-collect`（已归档）与社区镜像。
- 本项目 `scripts/review_sprint/bilibili.py` 的实现与测试。
