---
name: seedance-video-wetoken
description: "Seedance 2.0 视频生成工具（Wetoken REST API）。支持文生视频、首帧/首尾帧图生视频、多模态参考（图+视频+音频）、视频编辑、视频延长、联网搜索增强，自动路由模式。支持批量并发生成。触发：生成视频、seedance、生视频、文生视频、图生视频、编辑视频、延长视频。"
---

# Seedance Video — Wetoken 三方 REST 版

## 输入参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| prompt | string / string[] | 是 | - | 视频描述（单条或批量） |
| images | file[] / url[] | 否 | - | 参考图，role=reference_image |
| first_frame | file / url | 否 | - | 首帧图，启用首帧模式 |
| last_frame | file / url | 否 | - | 尾帧图，启用首尾帧模式 |
| videos | url[] | 否 | - | 参考视频 URL（最多 3 段） |
| audios | file[] / url[] | 否 | - | 参考音频（最多 3 段） |
| duration | int | 否 | 5 | 时长 4-15 秒，-1 自动决定 |
| ratio | string | 否 | adaptive | 21:9/16:9/4:3/1:1/3:4/9:16/adaptive |
| resolution | string | 否 | 720p | 480p/720p/1080p |
| seed | int | 否 | - | 固定种子，复现结果 |
| return_last_frame | bool | 否 | false | 返回尾帧图，用于连续生成 |
| generate_audio | bool | 否 | true | 生成同步音频 |
| watermark | bool | 否 | false | 添加水印 |
| web_search | bool | 否 | false | 启用联网搜索增强 |
| output_dir | string | 否 | ~/Desktop/seedance_output/ | 自定义输出目录 |

## 场景路由

```
用户提供了什么？
├── 只有 prompt                        → 文生视频
├── prompt + first_frame               → 首帧图生视频
├── prompt + first_frame + last_frame  → 首尾帧生视频
├── prompt + images                    → 多参考图生视频
├── prompt + videos                    → 视频延长 / 参考
├── prompt + images + videos           → 视频编辑 / 多模态参考
├── prompt + images + videos + audios  → 多模态参考（全组合）
└── web_search=true                    → 联网搜索增强（可与以上组合）
```

agent 根据输入自动判断场景，展示场景名称让用户确认。

---

## 环境检查

```bash
echo %WETOKEN_API_KEY%
```

缺 Key：去 wetoken.top 获取 API Key，设置环境变量 `WETOKEN_API_KEY`

---

## 执行流程

```
1. 环境检查（WETOKEN_API_KEY）
2. 汇总确认（一次展示所有参数，等用户确认）
   └── 场景 / 提示词 / 时长 / 比例 / 分辨率 / audio / watermark / seed / web_search
3. 构建 content 数组 + 提交任务
4. 轮询等待 → 下载视频
5. 失败 → 询问：重试 / 修改提示词 / 放弃
```

---

## API 配置

```python
import os

BASE_URL = "https://www.wetoken.top/api/v3/contents/generations/tasks"
ASSET_URL = "https://asset.wetoken.lingxixai.com/api/asset"
API_KEY = os.environ.get("WETOKEN_API_KEY")
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}",
}
MODEL = "doubao-seedance-2-0-260128"
```

---

## 素材上传

本地文件必须先上传为素材，获取 `asset://ID` 后才能在视频任务中使用。

### 上传图片素材

```python
import requests, time, json, os, datetime

ASSET_DB = os.path.expanduser("~/Desktop/seedance_output/asset_ledger.json")

def _load_asset_db():
    if os.path.exists(ASSET_DB):
        with open(ASSET_DB) as f:
            return json.load(f)
    return {"assets": {}}

def _save_asset_db(db):
    os.makedirs(os.path.dirname(ASSET_DB), exist_ok=True)
    with open(ASSET_DB, "w") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def _record_asset(asset_id, url, name, asset_type, upload_request_id=None):
    """上传成功后记录到素材账本"""
    db = _load_asset_db()
    db["assets"][asset_id] = {
        "id": asset_id,
        "asset_uri": f"asset://{asset_id}",
        "source_url": url,
        "name": name,
        "type": asset_type,
        "status": "Active",
        "uploaded_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "upload_request_id": upload_request_id,  # 上传时的 RequestId，用于问题追踪
        "usage_count": 0,
    }
    _save_asset_db(db)

def upload_image_asset(url, name):
    """上传图片素材，返回 asset://ID。自动查库去重。"""
    db = _load_asset_db()
    for aid, info in db["assets"].items():
        if info["source_url"] == url and info["type"] == "Image":
            return info["asset_uri"]

    resp = requests.post(f"{ASSET_URL}/create", headers=HEADERS,
                         json={"url": url, "name": name})
    resp.raise_for_status()
    data = resp.json()
    asset_id = data["Result"]["Id"]
    request_id = data["ResponseMetadata"]["RequestId"]
    _wait_asset_active(asset_id)
    _record_asset(asset_id, url, name, "Image", upload_request_id=request_id)
    return f"asset://{asset_id}"

def upload_media_asset(url, name, asset_type):
    """上传多媒体素材（Image/Video/Audio），返回 asset://ID"""
    db = _load_asset_db()
    for aid, info in db["assets"].items():
        if info["source_url"] == url and info["type"] == asset_type:
            return info["asset_uri"]

    resp = requests.post(f"{ASSET_URL}/createMedia", headers=HEADERS,
                         json={"url": url, "name": name, "assetType": asset_type,
                               "moderation": {"Strategy": "Skip"}})
    resp.raise_for_status()
    data = resp.json()
    asset_id = data["Result"]["Id"]
    request_id = data["ResponseMetadata"]["RequestId"]
    _wait_asset_active(asset_id)
    _record_asset(asset_id, url, name, asset_type, upload_request_id=request_id)
    return f"asset://{asset_id}"

def _wait_asset_active(asset_id, timeout=60):
    """轮询素材状态直到 Active，不支持高并发查询，间隔 3 秒"""
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{ASSET_URL}/get", headers=HEADERS,
                            params={"id": asset_id})
        resp.raise_for_status()
        result = resp.json()["Result"]
        if result["Status"] == "Active":
            return True
        if result["Status"] == "Failed":
            raise RuntimeError(f"素材处理失败: {asset_id}")
        time.sleep(3)
    raise TimeoutError(f"素材上传超时: {asset_id}")

def get_asset_status(asset_id):
    """查询素材状态"""
    resp = requests.get(f"{ASSET_URL}/get", headers=HEADERS,
                        params={"id": asset_id})
    resp.raise_for_status()
    return resp.json()["Result"]

def list_assets(asset_type=None):
    """查看本地素材账本，可选按类型过滤"""
    db = _load_asset_db()
    assets = list(db["assets"].values())
    if asset_type:
        assets = [a for a in assets if a["type"] == asset_type]
    return assets

def mark_asset_used(asset_id):
    """标记素材被使用（usage_count +1）"""
    db = _load_asset_db()
    if asset_id in db["assets"]:
        db["assets"][asset_id]["usage_count"] += 1
        db["assets"][asset_id]["last_used"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _save_asset_db(db)
```

### 素材上传规则

- **图片**：用 `upload_image_asset(url, name)` → `asset://ID`
- **视频/音频**：用 `upload_media_asset(url, name, asset_type)` → `asset://ID`
- 上传后自动等待 Active 状态，自动记录到 `asset_ledger.json`，相同 URL 自动去重不重复上传
- 查询接口**不支持高并发**，批量上传时顺序执行，间隔 3 秒
- **查看已上传素材**：`list_assets()` 或 `list_assets("Video")` 过滤类型
- **标记使用**：每次视频任务引用 asset 后调用 `mark_asset_used(asset_id)` 记录使用次数

---

## 异步批量上传

上传期间用户可继续交互。任务写入 `upload_queue.json`，由独立后台进程处理，关闭对话也不影响。

### 启动后台上传

```python
import subprocess, sys, uuid, datetime

UPLOAD_QUEUE = os.path.expanduser("~/Desktop/seedance_output/upload_queue.json")
UPLOADER_PY  = os.path.expanduser("~/.qoder/skills/seedance-video-wetoken/scripts/uploader.py")

def _load_queue():
    if os.path.exists(UPLOAD_QUEUE):
        with open(UPLOAD_QUEUE, encoding="utf-8") as f:
            return json.load(f)
    return {"jobs": {}}

def _save_queue(q):
    os.makedirs(os.path.dirname(UPLOAD_QUEUE), exist_ok=True)
    with open(UPLOAD_QUEUE, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)

def upload_async(items):
    """
    把任务写入队列，启动独立后台进程处理，立刻返回。
    items: [(local_path, name), ...] 或 [local_path, ...]
    """
    q = _load_queue()
    for item in items:
        if isinstance(item, (list, tuple)):
            local_path, name = item[0], item[1]
        else:
            local_path = item
            name = os.path.splitext(os.path.basename(local_path))[0]
        job_id = str(uuid.uuid4())[:8]
        q["jobs"][job_id] = {
            "id": job_id, "name": name, "path": local_path,
            "status": "pending", "asset_uri": None, "error": None,
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    _save_queue(q)

    env = os.environ.copy()
    env["WETOKEN_API_KEY"] = API_KEY
    subprocess.Popen(
        [sys.executable, UPLOADER_PY, UPLOAD_QUEUE],
        env=env,
        creationflags=0x00000008 if sys.platform == "win32" else 0,  # DETACHED_PROCESS
    )
    print(f"后台上传已启动，共 {len(items)} 个任务。用 check_uploads() 查进度。")

def check_uploads():
    """查看上传进度，展示所有任务状态表格。"""
    q = _load_queue()
    if not q["jobs"]:
        return "暂无上传任务"
    lines = ["| 名称 | 状态 | asset_uri | 错误 |",
             "|------|------|-----------|------|"]
    for j in q["jobs"].values():
        lines.append(f"| {j['name']} | {j['status']} | {j['asset_uri'] or '-'} | {j['error'] or '-'} |")
    return "\n".join(lines)
```

### 使用流程

```
1. 调用 upload_async(items) → 写队列、启动后台进程、立刻返回
2. 告知用户"已在后台上传，可继续操作"
3. 用户问进度 → 调用 check_uploads() 展示表格
4. 需要 asset_uri → 从 upload_queue.json 或 asset_ledger.json 读取
```

### 后台脚本

`scripts/uploader.py` — 读队列、顺序处理所有 pending 任务、结果写回队列和 asset_ledger.json。
进程独立运行，与 agent 会话无关。重复启动安全（已非 pending 的任务会跳过）。

---

## Content 数组构建（统一函数）

```python
def build_content(prompt, images=None, first_frame=None, last_frame=None,
                  videos=None, audios=None):
    content = [{"type": "text", "text": prompt}]

    if first_frame:
        content.append({"type": "image_url",
                        "image_url": {"url": resolve_media(first_frame, "first_frame")},
                        "role": "first_frame"})
    if last_frame:
        content.append({"type": "image_url",
                        "image_url": {"url": resolve_media(last_frame, "last_frame")},
                        "role": "last_frame"})
    for i, img in enumerate(images or []):
        content.append({"type": "image_url",
                        "image_url": {"url": resolve_media(img, f"ref_img_{i}")},
                        "role": "reference_image"})
    for i, vid in enumerate(videos or []):
        content.append({"type": "video_url",
                        "video_url": {"url": resolve_media(vid, f"ref_vid_{i}", media_type="Video")},
                        "role": "reference_video"})
    for i, aud in enumerate(audios or []):
        content.append({"type": "audio_url",
                        "audio_url": {"url": resolve_media(aud, f"ref_aud_{i}", media_type="Audio")},
                        "role": "reference_audio"})
    return content
```

---

## 媒体解析

```python
import base64

def resolve_media(source, name="media", media_type=None):
    """解析媒体源 → URL / asset://ID / base64

    规则：
    - asset:// 开头 → 直接返回
    - http 开头 → 视频/音频上传为素材返回 asset://ID，图片直接用
    - 本地文件 → 图片/音频 base64，视频报错提示上传
    """
    if isinstance(source, str) and source.startswith("asset://"):
        return source

    if isinstance(source, str) and source.startswith("http"):
        if media_type in ("Video", "Audio"):
            return upload_media_asset(source, name, media_type)
        return source

    if not os.path.isfile(source):
        raise FileNotFoundError(f"文件不存在: {source}")

    ext = source.rsplit(".", 1)[-1].lower()
    if ext in ("mp4", "mov"):
        raise ValueError("本地视频不支持直接使用，请上传到公网获取 URL 后重试")
    return _to_base64(source)

def _to_base64(path):
    ext = path.rsplit(".", 1)[-1].lower()
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
                "tiff": "image/tiff", "wav": "audio/wav", "mp3": "audio/mpeg"}
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime_map.get(ext, 'application/octet-stream')};base64,{b64}"
```

**关键**：视频/音频 URL 会自动上传为素材转 `asset://ID`，图片 URL 直接用。

---

## 提交任务

```python
import requests

def submit_task(content, duration=5, ratio="adaptive", resolution="720p",
                generate_audio=True, watermark=False, seed=None,
                return_last_frame=False, web_search=False):
    body = {
        "model": MODEL,
        "content": content,
        "duration": duration,
        "ratio": ratio,
        "resolution": resolution,
        "generate_audio": generate_audio,
        "watermark": watermark,
    }
    if seed is not None:
        body["seed"] = seed
    if return_last_frame:
        body["return_last_frame"] = True
    if web_search:
        body["tools"] = [{"type": "web_search"}]

    resp = requests.post(BASE_URL, headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()["id"]
```

---

## 轮询与下载

```python
import requests, time, os, datetime

def poll_and_download(task_id, output_dir):
    wait = 10
    while True:
        resp = requests.get(f"{BASE_URL}/{task_id}", headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        if data["status"] == "succeeded":
            video_url = data["content"]["video_url"]
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(output_dir, f"seedance_{ts}.mp4")
            with open(path, "wb") as f:
                for chunk in requests.get(video_url, stream=True).iter_content(8192):
                    f.write(chunk)

            last_frame_path = None
            lf_url = data.get("content", {}).get("last_frame_url")
            if lf_url:
                last_frame_path = os.path.join(output_dir, f"seedance_{ts}_lastframe.png")
                with open(last_frame_path, "wb") as f:
                    for chunk in requests.get(lf_url, stream=True).iter_content(8192):
                        f.write(chunk)

            usage = data.get("usage", {})
            return {"status": "success", "path": path, "last_frame": last_frame_path,
                    "usage": usage}

        elif data["status"] in ("failed", "expired"):
            reason = data.get("error", {}).get("message", data["status"])
            return {"status": "failed", "reason": reason}

        time.sleep(wait)
        wait = min(wait + 5, 60)
```

---

## 批量模式

prompt 为列表时：
1. 顺序提交（间隔 1 秒避免限流）
2. 并发轮询下载（max_workers=8）

详见 [reference.md](reference.md)

---

## 任务管理

```python
# 查询任务列表
resp = requests.get(BASE_URL, headers=HEADERS,
                    params={"page_size": 10, "filter.status": "succeeded"})
tasks = resp.json()

# 删除任务（仅非 running 状态）
resp = requests.delete(f"{BASE_URL}/{task_id}", headers=HEADERS)
# 成功返回 {}，运行中任务返回 409 InvalidAction.RunningTaskDeletion
```

用户说以下词时触发，与生成流程独立：
- **视频任务**："查看视频任务"、"删除任务"
- **素材账本**："查看素材"、"查看已上传素材"、"素材列表"、"已上传了什么"

---

## 失败处理

```
视频生成失败。原因：{reason}
请选择：1. 重试  2. 修改提示词后重试  3. 放弃
```

---

## 输出目录

默认 `~/Desktop/seedance_output/`，自动创建。
命名：`seedance_{YYYYMMDD_HHMMSS}.mp4`，批量加 `_{序号:02d}`。
尾帧：`seedance_{YYYYMMDD_HHMMSS}_lastframe.png`

---

## 用量报告

```
| # | 场景 | 时长 | 比例 | 分辨率 | 状态 | 输出路径 |
|---|------|------|------|--------|------|----------|
| 1 | 文生视频 | 5s | adaptive | 720p | OK | ~/Desktop/seedance_output/seedance_20260529_1430.mp4 |
```

---

## 注意事项

1. **role 必填**：first_frame / last_frame / reference_image / reference_video / reference_audio
2. **视频/音频 URL 自动转素材**：resolve_media 会自动上传为 asset://，有本地缓存去重
3. **本地视频不支持**：请上传到公网获取 URL
4. **音频不能单独输入**：必须同时提供图片或视频
5. **视频 URL 24h 过期**：成功后立即下载
6. **提示词引用**：用 `图片1`、`视频1`、`音频1` 引用 content 中对应媒体（编号按 content 数组顺序，从1开始）
7. **禁止未经确认调用 API**：汇总参数必须展示给用户确认后才提交
8. **素材查询限流**：不支持高并发，批量上传顺序执行间隔 3 秒
9. **素材账本**：`asset_ledger.json` 记录所有上传历史，相同 URL 自动去重不重复上传
10. **Seedance 2.0 不支持**：draft / camera_fixed / frames / service_tier
11. **SSL**：所有请求必须加 `verify=False`，并在脚本顶部禁用警告：`urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)`
12. **sd2-pe 不一定可用**：部分账号未开通，调用返回 503 model_not_found 时直接跳过优化，用用户原始提示词
13. **素材接口只接受公网 URL**：`/create` 和 `/createMedia` 均不接受 base64，不接受 multipart；本地文件必须先上传到公网（如 GitHub raw）才能使用
14. **本地图片上传流程**：压缩到 1024px 以内（JPEG quality 88）→ 推送到 GitHub 公开仓库 → 用 raw URL 调用 `createMedia`
15. **内容审核**：真实人脸图片触发 `InputImageSensitiveContentDetected.PrivacyInformation`（视频任务层）或 `PolicyViolation`（素材层，版权检测）；角色设定板（多角度+文字标注）比单人照更易触发版权检测，优先使用 `primary_image`（单人照版本）

---

## 详细参考

各场景完整代码示例、任务管理详细用法、媒体输入限制 → [reference.md](reference.md)
