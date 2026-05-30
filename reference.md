# Seedance Video — Wetoken REST 版详细参考

## 场景代码示例

### 1. 文生视频

```python
content = build_content("写实风格，晴朗蓝天下一大片白色雏菊花田，镜头逐渐拉近定格在雏菊特写")
task_id = submit_task(content, duration=5, ratio="16:9")
result = poll_and_download(task_id, output_dir)
```

### 2. 首帧图生视频

```python
content = build_content(
    prompt="女孩睁开眼，温柔地看向镜头，镜头缓缓拉出，可以听到风声",
    first_frame="https://example.com/girl.png"
)
task_id = submit_task(content, generate_audio=True)
```

### 3. 首尾帧生视频

```python
content = build_content(
    prompt="360度环绕运镜",
    first_frame="https://example.com/frame_first.jpeg",
    last_frame="https://example.com/frame_last.jpeg"
)
task_id = submit_task(content)
```

### 4. 多参考图生视频

```python
content = build_content(
    prompt="使用图片1的角色造型，在雨中撑伞行走",
    images=["https://example.com/char_ref1.jpg", "https://example.com/char_ref2.jpg"]
)
task_id = submit_task(content)
```

### 5. 视频延长

```python
content = build_content(
    prompt="延续视频1的叙事，接上视频2和视频3，形成完整的展厅漫游镜头",
    videos=[
        "https://example.com/extend_v1.mp4",
        "https://example.com/extend_v2.mp4",
        "https://example.com/extend_v3.mp4"
    ]
)
task_id = submit_task(content, duration=8)
```

### 6. 视频编辑

```python
content = build_content(
    prompt="将视频1中的杯子替换成图片1中的香水瓶，保持镜头运动不变",
    images=["https://example.com/perfume.jpg"],
    videos=["https://example.com/cup_scene.mp4"]
)
task_id = submit_task(content)
```

### 7. 多模态参考（全组合）

```python
content = build_content(
    prompt="全程使用视频1的镜头语言，使用音频1作为背景音乐，补充图片1和图片2的产品细节",
    images=["https://example.com/product1.jpg", "https://example.com/product2.jpg"],
    videos=["https://example.com/camera_ref.mp4"],
    audios=["https://example.com/bgm.mp3"]
)
task_id = submit_task(content, web_search=False)
```

### 8. 联网搜索增强

```python
content = build_content("生成一段关于最新款电动汽车的产品展示视频")
task_id = submit_task(content, web_search=True)
```

---

## 连续视频生成（return_last_frame）

用前一段视频的尾帧作为下一段的首帧，循环生成连续视频：

```python
prompts = [
    "女孩抱着狐狸，温柔地看向镜头",
    "女孩和狐狸在草地上奔跑，阳光明媚",
    "女孩和狐狸坐在树下休息"
]
first_frame_url = "https://example.com/girl_fox.png"
video_urls = []

for i, p in enumerate(prompts):
    content = build_content(prompt=p, first_frame=first_frame_url)
    task_id = submit_task(content, return_last_frame=True)
    result = poll_and_download(task_id, output_dir)

    if result["status"] == "success" and result["last_frame"]:
        first_frame_url = result["last_frame"]  # 下一段的首帧
        video_urls.append(result["path"])
    else:
        break

# 用 FFmpeg 拼接：ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4
```

---

## 批量模式详细

```python
import concurrent.futures, time

def batch_generate(prompts, content_kwargs_list, output_dir, **submit_kwargs):
    # Phase 1: 顺序提交
    task_map = {}
    for i, (p, ck) in enumerate(zip(prompts, content_kwargs_list)):
        content = build_content(prompt=p, **ck)
        task_id = submit_task(content, **submit_kwargs)
        task_map[i] = task_id
        time.sleep(1)  # 避免限流

    # Phase 2: 并发轮询
    results = [None] * len(prompts)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(poll_and_download, tid, output_dir): idx
                   for idx, tid in task_map.items()}
        for fut in concurrent.futures.as_completed(futures):
            idx = futures[fut]
            results[idx] = fut.result()

    # 用量报告
    for i, r in enumerate(results):
        status = "OK" if r["status"] == "success" else "FAIL"
        print(f"| {i+1} | {status} | {r.get('path', r.get('reason', ''))} |")
    return results
```

---

## 任务管理详细

### 查询任务列表

```python
resp = requests.get(BASE_URL, headers=HEADERS, params={
    "page_size": 10,
    "filter.status": "succeeded",
    "filter.model": "doubao-seedance-2-0-260128"
})
tasks = resp.json()
```

### 查询单个任务

```python
resp = requests.get(f"{BASE_URL}/{task_id}", headers=HEADERS)
data = resp.json()
# data["status"]: queued / running / succeeded / failed / expired
# data["content"]["video_url"]: 视频下载地址
# data["usage"]["completion_tokens"]: token 消耗
```

### 删除任务

```python
resp = requests.delete(f"{BASE_URL}/{task_id}", headers=HEADERS)
# 成功：返回 {}
# 运行中：返回 409 {"error": {"code": "InvalidAction.RunningTaskDeletion"}}
```

---

## 媒体输入限制

### 图片
- 格式：jpeg、png、webp、bmp、tiff、gif、heic、heif
- 宽高比（宽/高）：0.4 ~ 2.5
- 宽高长度：300 ~ 6000 px
- 单张 < 30 MB，请求体总计 < 64 MB
- 数量：首帧 1 张 / 首尾帧 2 张 / 多模态参考 1~9 张

### 视频
- 格式：mp4、mov（H.264/HEVC + AAC/MP3）
- 分辨率：480p / 720p / 1080p
- 单个时长 2~15s，最多 3 段，总时长 ≤ 15s
- 宽高比 0.4~2.5，像素 409600~2086876
- 单个 < 50 MB，帧率 24~60 FPS
- **仅接受 URL，不支持本地文件 base64**

### 音频
- 格式：wav、mp3
- 单个时长 2~15s，最多 3 段，总时长 ≤ 15s
- 单个 < 15 MB
- 支持 URL / Base64
- **不可单独输入，必须同时提供图片或视频**

---

## Adaptive 比例规则

| 场景 | 规则 |
|------|------|
| 文生视频 | 根据提示词自动选择最合适的宽高比 |
| 首帧/首尾帧 | 根据首帧图片选择最接近的宽高比 |
| 多模态参考 | 以第一个媒体文件为准（优先级：视频 > 图片） |

### 常见像素值

| 分辨率 | 比例 | 像素 |
|--------|------|------|
| 480p | 16:9 | 864x496 |
| 480p | 4:3 | 752x560 |
| 480p | 1:1 | 640x640 |
| 480p | 3:4 | 560x752 |
| 480p | 9:16 | 496x864 |
| 480p | 21:9 | 992x432 |
| 720p | 16:9 | 1280x720 |
| 720p | 4:3 | 1112x834 |
| 720p | 1:1 | 960x960 |
| 720p | 3:4 | 834x1112 |
| 720p | 9:16 | 720x1280 |
| 720p | 21:9 | 1470x630 |
| 1080p | 16:9 | 1920x1080 |
| 1080p | 4:3 | 1664x1248 |
| 1080p | 1:1 | 1440x1440 |
| 1080p | 3:4 | 1248x1664 |
| 1080p | 9:16 | 1080x1920 |
| 1080p | 21:9 | 2206x946 |

---

## 素材上传 API 详细

### 上传图片素材

```
POST https://asset.wetoken.lingxixai.com/api/asset/create
Authorization: Bearer {WETOKEN_API_KEY}
Content-Type: application/json

{"url": "图片公网地址", "name": "素材名称"}
```

返回：
```json
{"Result": {"Id": "asset-20260324111811-p9fjp"}}
```

### 上传多媒体素材（视频/音频）

```
POST https://asset.wetoken.lingxixai.com/api/asset/createMedia
Authorization: Bearer {WETOKEN_API_KEY}
Content-Type: application/json

{"url": "素材公网地址", "name": "素材名称", "assetType": "Video|Audio|Image"}
```

返回同上。

### 查询素材状态

```
GET https://asset.wetoken.lingxixai.com/api/asset/get?id={asset_id}
Authorization: Bearer {WETOKEN_API_KEY}
```

返回：
```json
{
  "Result": {
    "Id": "asset-xxx",
    "Name": "大门",
    "URL": "原始URL",
    "AssetType": "Image",
    "Status": "Active|Processing|Failed",
    "CreateTime": "...",
    "UpdateTime": "..."
  }
}
```

状态说明：
- **Active**：就绪，可使用
- **Processing**：处理中，不可使用
- **Failed**：处理失败

### 在视频任务中使用素材

content 中将 url 替换为 `asset://ASSET_ID`：

```json
{
  "type": "video_url",
  "video_url": {"url": "asset://asset-20260324111811-p9fjp"},
  "role": "reference_video"
}
```

### 素材上传要求

| 类型 | 格式 | 限制 |
|------|------|------|
| Image | jpeg/png/webp/bmp/tiff/gif/heic/heif | 宽高比 0.4~2.5，300~6000px，<30MB |
| Video | mp4/mov | 480p/720p，2~15s，宽高比 0.4~2.5，<50MB，24~60FPS |
| Audio | wav/mp3 | 2~15s，<15MB |

### 素材账本（asset_ledger.json）

本地持久记录所有上传历史，路径：`~/Desktop/seedance_output/asset_ledger.json`

账本结构：
```json
{
  "assets": {
    "asset-xxx": {
      "id": "asset-xxx",
      "asset_uri": "asset://asset-xxx",
      "source_url": "https://example.com/video.mp4",
      "name": "素材名称",
      "type": "Image|Video|Audio",
      "status": "Active",
      "uploaded_at": "2026-05-29 14:30:00",
      "usage_count": 2,
      "last_used": "2026-05-29 15:00:00"
    }
  }
}
```

常用操作：
```python
# 查看所有素材
assets = list_assets()

# 只看视频素材
videos = list_assets("Video")

# 标记使用（每次视频任务引用 asset 后调用）
mark_asset_used("asset-xxx")
```

特性：
- 相同 `source_url + type` 自动去重，不重复上传
- 查询接口不支持高并发，批量上传需顺序执行，间隔 3 秒

---

## 提示词建议

- 提示词 = 主体 + 运动，背景 + 运动，镜头 + 运动
- 用简洁准确的自然语言
- 图生视频请上传高清高质量图片
- 不符合预期时，将抽象描述换成具象描述，重要内容前置
