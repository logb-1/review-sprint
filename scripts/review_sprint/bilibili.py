"""Bilibili search + subtitle-aware relevance ranking.

Hard rule: a rendered link may only contain a BV id that came from an API
response (or a cached API response).  The model never writes links itself.

The client is deliberately dependency-free (urllib) and testable through an
injected `transport` callable.  Cookie values are read from an environment
variable or a user-supplied file and are never written to disk.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .topics import (
    DOMAINS, anchor_coverage, anchors_for, build_queries, contains_anchor,
    domain_mismatch, is_off_topic,
)
from .util import read_json, strip_html, write_json

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BASE = "https://api.bilibili.com"
BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")


class BiliError(RuntimeError):
    def __init__(self, code: int | str, message: str, payload: Any = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.payload = payload


def load_cookie(path: str | None = None) -> str:
    """Read a cookie from BILIBILI_COOKIE or a file; never persist it."""
    if path:
        text = Path(path).read_text(encoding="utf-8", errors="ignore").strip()
        return " ".join(text.split())
    return " ".join((os.environ.get("BILIBILI_COOKIE") or "").split())


def cookie_status(cookie: str) -> dict[str, Any]:
    names = []
    for part in (cookie or "").split(";"):
        if "=" in part:
            names.append(part.split("=", 1)[0].strip())
    return {"present": bool(cookie), "hasSESSDATA": "SESSDATA" in names, "fields": len(names)}


def search_url(keyword: str) -> str:
    return "https://search.bilibili.com/all?keyword=" + urllib.parse.quote(keyword)


def _parse_count(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        if text.endswith("亿"):
            return int(float(text[:-1]) * 100_000_000)
        if text.endswith("万"):
            return int(float(text[:-1]) * 10_000)
        return int(float(text))
    except ValueError:
        return 0


def _duration_seconds(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value or "").strip()
    if not text:
        return 0
    parts = [p for p in text.split(":") if p.isdigit()]
    if not parts:
        return 0
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total


def _clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", strip_html(value or "")).strip()


def mixin_key(img_key: str, sub_key: str) -> str:
    raw = (img_key or "") + (sub_key or "")
    if len(raw) < 64:
        raise BiliError("wbi", "WBI 原始 key 长度不足")
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def sign_params(params: dict[str, Any], key: str, now: int | None = None) -> dict[str, str]:
    signed = {k: str(v) for k, v in params.items() if v is not None}
    signed["wts"] = str(now if now is not None else int(time.time()))
    items = sorted(signed.items())
    clean = [(k, re.sub(r"[!'()*]", "", v)) for k, v in items]
    query = urllib.parse.urlencode(clean)
    signed["w_rid"] = hashlib.md5((query + key).encode("utf-8")).hexdigest()
    return signed


class BiliClient:
    def __init__(
        self,
        cache_dir: Path,
        *,
        cookie: str = "",
        offline: bool = False,
        rate_seconds: float = 1.0,
        timeout: int = 12,
        transport: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cookie = cookie
        self.offline = offline
        self.rate_seconds = max(0.0, float(rate_seconds))
        self.timeout = timeout
        self.transport = transport
        self._last_request = 0.0
        self._wbi_key = ""
        self._wbi_at = 0.0
        self.stats = {"requests": 0, "cacheHits": 0, "errors": 0, "degraded": False}
        try:
            # Some Bilibili edges present a legacy key; OpenSSL 3 defaults reject it.
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.set_ciphers("DEFAULT@SECLEVEL=1")
        except Exception:
            self._ssl_context = None
        self._insecure_tls = False
        self._buvid_bootstrapped = False

    # ---------------------------------------------------------------- cache
    def _cache_path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self.cache_dir / "bilibili" / (digest + ".json")

    def cache_get(self, key: str, max_age: float) -> Any:
        path = self._cache_path(key)
        data = read_json(path, None)
        if not data:
            return None
        if max_age >= 0 and time.time() - float(data.get("fetchedAt", 0)) > max_age:
            return None
        self.stats["cacheHits"] += 1
        return data.get("payload")

    def cache_put(self, key: str, payload: Any) -> None:
        write_json(self._cache_path(key), {"fetchedAt": time.time(), "key": key, "payload": payload})

    # --------------------------------------------------------------- request
    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _http_json(self, url: str, params: dict[str, str], allow_codes: tuple[int, ...] = ()) -> dict[str, Any]:
        if self.offline:
            raise BiliError("offline", "离线模式不发起网络请求")
        if self.rate_seconds:
            wait = self.rate_seconds - (time.time() - self._last_request)
            if wait > 0:
                time.sleep(wait)
        query = urllib.parse.urlencode(params)
        full = url + ("?" + query if query else "")
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                req = urllib.request.Request(full, headers=self._headers())
                with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl_context) as resp:
                    body = resp.read().decode("utf-8", "ignore")
                self._last_request = time.time()
                self.stats["requests"] += 1
                data = json.loads(body)
                code = data.get("code")
                if code not in (0, None) and code not in allow_codes:
                    raise BiliError(code, data.get("message", "API 返回错误"), data)
                return data
            except BiliError as exc:
                if exc.code in {-352, -412, -799, 62002, 62004, 62012} and attempt < 2:
                    self.stats["degraded"] = True
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if exc.code == -352 and attempt == 0 and not self.cookie and not self._buvid_bootstrapped:
                    self._buvid_bootstrapped = True
                    self._bootstrap_buvid()
                    continue
                raise
            except urllib.error.HTTPError as exc:
                last_error = exc
                self._last_request = time.time()
                # Some WAFs fingerprint urllib; curl's TLS/HTTP stack is accepted.
                if exc.code in {403, 412} and shutil.which("curl"):
                    try:
                        data = self._curl_json(full)
                        code = data.get("code")
                        if code not in (0, None) and code not in allow_codes:
                            raise BiliError(code, data.get("message", "API 返回错误"), data)
                        return data
                    except BiliError:
                        raise
                    except Exception as curl_exc:
                        last_error = curl_exc
                if attempt < 2:
                    time.sleep(1.2 * (2 ** attempt))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                self._last_request = time.time()
                if self._is_cert_error(exc) and not self._insecure_tls:
                    self._insecure_tls = True
                    self.stats["insecureTls"] = True
                    self._ssl_context = ssl._create_unverified_context()
                    continue
                if attempt < 2:
                    time.sleep(1.2 * (2 ** attempt))
        self.stats["errors"] += 1
        raise BiliError("network", f"B 站请求失败: {last_error}")

    def _curl_json(self, full_url: str) -> dict[str, Any]:
        curl = shutil.which("curl")
        if not curl:
            raise BiliError("curl", "系统没有 curl")
        config = [
            'url = "' + full_url.replace("\\", "\\\\").replace('"', '\\"') + '"',
            'header = "User-Agent: ' + USER_AGENT + '"',
            'header = "Referer: https://www.bilibili.com/"',
            'header = "Origin: https://www.bilibili.com"',
            'header = "Accept: application/json, text/plain, */*"',
            "silent",
            "show-error",
            "compressed",
            "max-time = 20",
        ]
        if self.cookie:
            config.append('header = "Cookie: ' + self.cookie.replace('"', '\\"') + '"')
        proc = subprocess.run(
            [curl, "--config", "-"], input="\n".join(config) + "\n",
            text=True, capture_output=True, timeout=25,
        )
        if proc.returncode != 0:
            raise BiliError("curl", (proc.stderr or "curl 失败").strip()[:200])
        self.stats["requests"] += 1
        data = json.loads(proc.stdout)
        if not isinstance(data, dict):
            raise BiliError("curl", "curl 返回的不是 JSON")
        return data

    @staticmethod
    def _is_cert_error(exc: BaseException) -> bool:
        text = str(exc)
        if "CERTIFICATE_VERIFY_FAILED" in text or "certificate verify failed" in text:
            return True
        reason = getattr(exc, "reason", None)
        return isinstance(reason, ssl.SSLCertVerificationError)

    def _bootstrap_buvid(self) -> None:
        """Best-effort anonymous fingerprint cookie; never persisted."""
        try:
            data = self._http_json(f"{BASE}/x/frontend/finger/spi", {})
            payload = data.get("data") or {}
            pairs = []
            if payload.get("b_3"):
                pairs.append("buvid3=" + str(payload["b_3"]))
            if payload.get("b_4"):
                pairs.append("buvid4=" + str(payload["b_4"]))
            if pairs:
                extra = "; ".join(pairs)
                self.cookie = (self.cookie + "; " + extra).strip("; ")
        except BiliError:
            pass

    # ------------------------------------------------------------------- WBI
    def wbi_key(self) -> str:
        if self._wbi_key and time.time() - self._wbi_at < 6 * 3600:
            return self._wbi_key
        cached = self.cache_get("wbi:keys", 6 * 3600)
        if cached:
            self._wbi_key = cached["mixin"]
            self._wbi_at = time.time()
            return self._wbi_key
        if self.transport:
            data = self.transport(f"{BASE}/x/web-interface/nav", {})
        else:
            data = self._http_json(f"{BASE}/x/web-interface/nav", {}, allow_codes=(-101,))
        try:
            info = data["data"]["wbi_img"]
            img = str(info["img_url"]).rsplit("/", 1)[-1].split(".")[0]
            sub = str(info["sub_url"]).rsplit("/", 1)[-1].split(".")[0]
        except (KeyError, TypeError) as exc:
            raise BiliError("wbi", "无法从 nav 接口取得 WBI key") from exc
        key = mixin_key(img, sub)
        self._wbi_key, self._wbi_at = key, time.time()
        self.cache_put("wbi:keys", {"img": img, "sub": sub, "mixin": key})
        return key

    def _signed(self, params: dict[str, Any]) -> dict[str, str]:
        return sign_params(params, self.wbi_key())

    # ---------------------------------------------------------------- search
    def search(self, keyword: str, page: int = 1, page_size: int = 20) -> list[dict[str, Any]]:
        cache_key = f"search:{keyword}:{page}:{page_size}"
        cached = self.cache_get(cache_key, 7 * 86400)
        if cached is not None:
            return cached
        params = {
            "search_type": "video",
            "keyword": keyword,
            "page": page,
            "page_size": page_size,
            "order": "totalrank",
        }
        if self.transport:
            data = self.transport(f"{BASE}/x/web-interface/wbi/search/type", self._signed(params))
        else:
            data = self._http_json(f"{BASE}/x/web-interface/wbi/search/type", self._signed(params))
        result = (data.get("data") or {}).get("result") or []
        if not result and "v_voucher" in (data.get("data") or {}):
            raise BiliError("soft-block", "B 站软拦截：返回了 v_voucher 但没有 result；检查 Referer/UA 或稍后重试")
        videos = [self._normalize_search_item(item) for item in result if item.get("bvid")]
        self.cache_put(cache_key, videos)
        return videos

    def _normalize_search_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "bvid": item.get("bvid", ""),
            "title": _clean_title(item.get("title", "")),
            "author": _clean_title(item.get("author", "")),
            "play": _parse_count(item.get("play")),
            "favorites": _parse_count(item.get("favorites")),
            "description": _clean_title(item.get("description", "")),
            "tag": _clean_title(item.get("tag", "")),
            "duration": _duration_seconds(item.get("duration")),
            "pubdate": int(item.get("pubdate") or 0),
            "typename": _clean_title(item.get("typename", "")),
            "source": "search",
        }

    # ------------------------------------------------------------------ view
    def video_info(self, bvid: str) -> dict[str, Any]:
        cache_key = f"view:{bvid}"
        cached = self.cache_get(cache_key, 7 * 86400)
        if cached is not None:
            return cached
        params = {"bvid": bvid}
        if self.transport:
            data = self.transport(f"{BASE}/x/web-interface/view", params)
        else:
            data = self._http_json(f"{BASE}/x/web-interface/view", params)
        item = data.get("data") or {}
        pages = []
        for page in item.get("pages") or []:
            pages.append({
                "cid": page.get("cid"),
                "page": int(page.get("page") or 1),
                "part": _clean_title(page.get("part", "")),
                "duration": int(page.get("duration") or 0),
            })
        info = {
            "bvid": item.get("bvid", bvid),
            "title": _clean_title(item.get("title", "")),
            "author": _clean_title((item.get("owner") or {}).get("name", "")),
            "description": _clean_title(item.get("desc", "")),
            "duration": int(item.get("duration") or 0),
            "pubdate": int(item.get("pubdate") or 0),
            "play": int((item.get("stat") or {}).get("view") or 0),
            "like": int((item.get("stat") or {}).get("like") or 0),
            "typename": _clean_title(item.get("tname", "")),
            "pages": pages,
            "source": "view",
        }
        self.cache_put(cache_key, info)
        return info

    # ------------------------------------------------------------- subtitles
    def subtitles(self, bvid: str, cid: int | None) -> list[dict[str, Any]]:
        if not cid:
            return []
        cache_key = f"player:{bvid}:{cid}"
        cached = self.cache_get(cache_key, 7 * 86400)
        if cached is not None:
            return cached
        params = {"bvid": bvid, "cid": cid}
        try:
            if self.transport:
                data = self.transport(f"{BASE}/x/player/wbi/v2", self._signed(params))
            else:
                data = self._http_json(f"{BASE}/x/player/wbi/v2", self._signed(params))
        except BiliError:
            self.cache_put(cache_key, [])
            return []
        tracks = ((data.get("data") or {}).get("subtitle") or {}).get("subtitles") or []
        chosen = None
        for track in tracks:
            lang = str(track.get("lan", ""))
            if lang in {"zh-CN", "zh-Hans", "ai-zh", "zh"}:
                chosen = track
                break
        if chosen is None and tracks:
            chosen = tracks[0]
        cues: list[dict[str, Any]] = []
        if chosen and chosen.get("subtitle_url"):
            url = str(chosen["subtitle_url"])
            if url.startswith("//"):
                url = "https:" + url
            urls = [url]
            if "aisubtitle.hdslb.com" in url:
                # auth_key 过期时，i0 镜像 + 去 query 仍可匿名读取（实测）
                fallback = re.sub(r"^https?://aisubtitle\.hdslb\.com", "https://i0.hdslb.com", url)
                urls.append(fallback.split("?", 1)[0])
            for candidate in urls:
                try:
                    if self.transport:
                        raw = self.transport(candidate, {})
                    else:
                        req = urllib.request.Request(candidate, headers=self._headers())
                        with urllib.request.urlopen(req, timeout=self.timeout, context=self._ssl_context) as resp:
                            raw = json.loads(resp.read().decode("utf-8", "ignore"))
                    for cue in raw.get("body") or []:
                        cues.append({
                            "from": float(cue.get("from") or 0),
                            "to": float(cue.get("to") or 0),
                            "content": _clean_title(cue.get("content", "")),
                        })
                    if cues:
                        break
                except Exception:
                    try:
                        raw = self._curl_json(candidate)
                        for cue in raw.get("body") or []:
                            cues.append({
                                "from": float(cue.get("from") or 0),
                                "to": float(cue.get("to") or 0),
                                "content": _clean_title(cue.get("content", "")),
                            })
                        if cues:
                            break
                    except Exception:
                        continue
        self.cache_put(cache_key, cues)
        return cues

    # --------------------------------------------------------------- ranking
    def score_video(
        self,
        kp: dict[str, Any],
        video: dict[str, Any],
        cues: list[dict[str, Any]],
        *,
        domain: str,
        whitelist: list[str] | None = None,
    ) -> dict[str, Any]:
        anchors = anchors_for(kp)
        if not anchors:
            return {"score": 0.0, "rejected": "no-anchor", "reason": "知识点缺少锚词"}
        pages_text = " ".join(p.get("part", "") for p in video.get("pages") or [])
        tag_text = f"{video.get('typename', '')} {video.get('tag', '')}"
        title = video.get("title", "")
        desc = video.get("description", "")
        all_text = " ".join([title, pages_text, desc, tag_text])

        off, word = is_off_topic(all_text, domain)
        if off:
            return {"score": 0.0, "rejected": "negative", "reason": f"命中跑题词「{word}」"}
        if domain_mismatch(all_text, domain):
            return {"score": 0.0, "rejected": "domain", "reason": "跨领域结果"}

        title_cov = anchor_coverage(title, anchors)
        page_cov = anchor_coverage(pages_text, anchors)
        desc_cov = anchor_coverage(desc + " " + tag_text, anchors)
        if not any(contains_anchor(text, anchors[0]) for text in (title, pages_text, desc, tag_text)):
            return {"score": 0.0, "rejected": "anchor", "reason": f"主锚词「{anchors[0]}」未命中标题/分P/简介"}

        cue_hits = 0
        sub_cov = 0.0
        if cues:
            hit_anchors = 0
            for anchor in anchors:
                if any(contains_anchor(cue.get("content", ""), anchor) for cue in cues):
                    hit_anchors += 1
            sub_cov = hit_anchors / len(anchors)
            cue_hits = sum(1 for cue in cues if any(contains_anchor(cue.get("content", ""), a) for a in anchors))

        if cues:
            score = 0.45 * title_cov + 0.10 * page_cov + 0.05 * desc_cov + 0.35 * sub_cov + 0.05 * self._quality(video)
        else:
            # no subtitle evidence: rely more on title/part, but never on optional anchors alone
            score = 0.75 * title_cov + 0.10 * page_cov + 0.10 * desc_cov + 0.05 * self._quality(video)
        if whitelist and any(name and name in video.get("author", "") for name in whitelist):
            score += 0.08
        score = max(0.0, min(1.0, score))

        segment = locate_segment(cues, anchors)
        page = 1
        for p in video.get("pages") or []:
            if any(contains_anchor(p.get("part", ""), a) for a in anchors):
                page = int(p.get("page") or 1)
                break
        link = f"https://www.bilibili.com/video/{video.get('bvid', '')}"
        if page > 1:
            link += f"?p={page}"
        if segment:
            link += ("&" if "?" in link else "?") + f"t={segment['start']}"

        return {
            "score": round(score, 3),
            "rejected": "",
            "reason": self._reason(anchors, title_cov, page_cov, desc_cov, sub_cov, segment, page),
            "anchors": anchors,
            "titleCoverage": round(title_cov, 2),
            "pageCoverage": round(page_cov, 2),
            "descCoverage": round(desc_cov, 2),
            "subtitleCoverage": round(sub_cov, 2),
            "subtitleHits": cue_hits,
            "segment": segment,
            "page": page,
            "link": link,
        }

    @staticmethod
    def _quality(video: dict[str, Any]) -> float:
        play = max(0, int(video.get("play") or 0))
        like = max(0, int(video.get("like") or 0))
        return max(0.0, min(1.0, math.log10(play + 10) / 6.0 * 0.8 + math.log10(like + 10) / 6.0 * 0.2))

    @staticmethod
    def _reason(anchors: list[str], title_cov: float, page_cov: float, desc_cov: float,
                sub_cov: float, segment: dict[str, Any] | None, page: int) -> str:
        parts = []
        if title_cov:
            parts.append(f"标题命中 {int(title_cov * len(anchors))}/{len(anchors)} 个锚词")
        if page_cov:
            parts.append(f"分P 命中 {int(page_cov * len(anchors))}/{len(anchors)}")
        if desc_cov:
            parts.append("简介/标签命中")
        if sub_cov:
            clock = ""
            if segment:
                clock = f"（{format_clock(segment['start'])}–{format_clock(segment['end'])}）"
            parts.append(f"字幕锚词覆盖 {int(sub_cov * len(anchors))}/{len(anchors)}{clock}")
        if page > 1:
            parts.append(f"定位到 P{page}")
        return "；".join(parts) or "锚词命中"

    # ------------------------------------------------------------- recommend
    def recommend(
        self,
        kp: dict[str, Any],
        *,
        domain: str,
        course: str,
        limit: int = 2,
        threshold: float = 0.5,
        whitelist: list[str] | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        cache_key = f"rec:{kp.get('id')}:{','.join(anchors_for(kp))}"
        if not refresh:
            cached = self.cache_get(cache_key, 7 * 86400)
            if cached is not None:
                return cached
        anchors = anchors_for(kp)
        queries = build_queries(anchors, domain, course)
        candidates: dict[str, dict[str, Any]] = {}
        search_errors = []
        for query in queries[:3]:
            try:
                for item in self.search(query):
                    candidates.setdefault(item["bvid"], item)
            except BiliError as exc:
                search_errors.append(str(exc))
        ranked: list[dict[str, Any]] = []
        candidates_list = list(candidates.values())
        candidates_list.sort(
            key=lambda item: anchor_coverage(
                " ".join([item.get("title", ""), item.get("description", ""), item.get("tag", "")]),
                anchors,
            ),
            reverse=True,
        )
        for item in candidates_list[:8]:
            search_text = " ".join([item.get("title", ""), item.get("description", ""), item.get("tag", "")])
            off_topic, _word = is_off_topic(search_text, domain)
            if off_topic or domain_mismatch(search_text, domain):
                continue
            try:
                info = self.video_info(item["bvid"])
            except BiliError:
                info = dict(item)
            info.setdefault("tag", item.get("tag", ""))
            pre_text = info.get("title", "") + " " + " ".join(p.get("part", "") for p in info.get("pages") or []) + " " + info.get("description", "")
            if not any(contains_anchor(pre_text, a) for a in anchors):
                continue
            cid = None
            for page in info.get("pages") or []:
                if any(contains_anchor(page.get("part", ""), a) for a in anchors):
                    cid = page.get("cid")
                    break
            if cid is None and info.get("pages"):
                cid = info["pages"][0].get("cid")
            cues = self.subtitles(info["bvid"], cid) if cid else []
            scored = self.score_video(kp, info, cues, domain=domain, whitelist=whitelist)
            if scored["score"] < threshold or scored.get("rejected"):
                continue
            row = {
                "kpId": kp.get("id"),
                "bvid": info["bvid"],
                "title": info.get("title", ""),
                "author": info.get("author", ""),
                "play": info.get("play", 0),
                "page": scored["page"],
                "start": (scored.get("segment") or {}).get("start"),
                "end": (scored.get("segment") or {}).get("end"),
                "link": scored["link"],
                "score": scored["score"],
                "reason": scored["reason"],
                "anchors": anchors,
                "fetchedAt": int(time.time()),
            }
            ranked.append(row)
        ranked.sort(key=lambda x: (x["score"], x["play"]), reverse=True)
        result = {
            "status": "ok" if ranked else "no_match",
            "kpId": kp.get("id"),
            "anchors": anchors,
            "queries": queries,
            "items": ranked[:limit],
            "searchUrl": search_url(" ".join(anchors[:2]) if anchors else course),
            "errors": search_errors,
        }
        self.cache_put(cache_key, result)
        return result

    # ----------------------------------------------------------------- audit
    def cached_bvids(self) -> set[str]:
        found: set[str] = set()
        root = self.cache_dir / "bilibili"
        if not root.exists():
            return found
        for path in root.glob("*.json"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            found.update(BV_RE.findall(text))
        return found


def locate_segment(cues: list[dict[str, Any]], anchors: list[str], window: int = 120) -> dict[str, Any] | None:
    if not cues or not anchors:
        return None
    best = None
    for i, cue in enumerate(cues):
        start = float(cue.get("from") or 0)
        hits = 0
        first_hit = None
        end = start
        for later in cues[i:]:
            if float(later.get("from") or 0) - start > window:
                break
            text = later.get("content", "")
            count = sum(1 for anchor in anchors if contains_anchor(text, anchor))
            if count and first_hit is None:
                first_hit = float(later.get("from") or 0)
            hits += count
            end = float(later.get("to") or later.get("from") or start)
        if hits <= 0 or first_hit is None:
            continue
        if best is None or hits > best[0]:
            best = (hits, first_hit, end)
    if not best or best[0] <= 0:
        return None
    return {"start": int(best[1]), "end": int(best[2]), "hits": best[0]}


def format_clock(seconds: float | int | None) -> str:
    total = max(0, int(seconds or 0))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
