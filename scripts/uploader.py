"""
后台素材上传进程。
用法：python uploader.py <queue_file>
从 queue_file 读取待上传任务，顺序处理，结果写回同一文件。
"""
import sys, json, os, time, requests, base64, io, datetime
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from PIL import Image

QUEUE_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/Desktop/seedance_output/upload_queue.json")

ASSET_URL = "https://asset.wetoken.lingxixai.com/api/asset"
ASSET_DB  = os.path.join(os.path.dirname(QUEUE_FILE), "asset_ledger.json")

GH_TOKEN = os.environ.get("GH_TOKEN", "")
GH_OWNER = os.environ.get("GH_OWNER", "zzymo123-cyber")
GH_REPO  = os.environ.get("GH_REPO",  "seedance-chars-tmp")
API_KEY  = os.environ.get("WETOKEN_API_KEY", "")

def _headers():
    return {"Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"}

def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _update_job(job_id, **kwargs):
    q = _load(QUEUE_FILE)
    q["jobs"][job_id].update(kwargs)
    _save(QUEUE_FILE, q)

def push_to_github(local_path, filename):
    img = Image.open(local_path).convert("RGB")
    w, h = img.size
    nw, nh = 1024, int(h * 1024 / w)
    buf = io.BytesIO()
    img.resize((nw, nh), Image.LANCZOS).save(buf, "JPEG", quality=88)
    content_b64 = base64.b64encode(buf.getvalue()).decode()

    headers = {"Authorization": f"token {GH_TOKEN}",
               "Accept": "application/vnd.github.v3+json"}
    r = requests.get(
        f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{filename}",
        headers=headers)
    body = {"message": f"upload {filename}", "content": content_b64}
    if r.status_code == 200:
        body["sha"] = r.json()["sha"]
    requests.put(
        f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{filename}",
        headers=headers, json=body)
    return f"https://raw.githubusercontent.com/{GH_OWNER}/{GH_REPO}/main/{filename}"

def upload_media(raw_url, name):
    resp = requests.post(f"{ASSET_URL}/createMedia", headers=_headers(),
                         json={"url": raw_url, "name": name, "assetType": "Image",
                               "moderation": {"Strategy": "Skip"}},
                         verify=False)
    resp.raise_for_status()
    data = resp.json()
    asset_id = data["Result"]["Id"]
    request_id = data["ResponseMetadata"]["RequestId"]

    # 等待 Active
    for _ in range(20):
        time.sleep(3)
        r = requests.get(f"{ASSET_URL}/get", headers=_headers(),
                         params={"id": asset_id}, verify=False)
        result = r.json()["Result"]
        if result["Status"] == "Active":
            break
        if result["Status"] == "Failed":
            raise RuntimeError(result.get("Error", {}).get("Message", "Failed"))

    # 写 asset_ledger
    db = _load(ASSET_DB) if os.path.exists(ASSET_DB) else {"assets": {}}
    db["assets"][asset_id] = {
        "id": asset_id, "asset_uri": f"asset://{asset_id}",
        "source_url": raw_url, "name": name, "type": "Image",
        "status": "Active",
        "uploaded_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "upload_request_id": request_id, "usage_count": 0,
    }
    _save(ASSET_DB, db)
    return f"asset://{asset_id}"

def main():
    if not API_KEY:
        print("缺少 WETOKEN_API_KEY")
        sys.exit(1)

    q = _load(QUEUE_FILE)
    for job_id, job in q["jobs"].items():
        if job["status"] != "pending":
            continue
        print(f"[{job['name']}] 开始上传...")
        _update_job(job_id, status="uploading")
        try:
            filename = job["name"].replace(" ", "_") + ".jpg"
            raw_url = push_to_github(job["path"], filename)
            time.sleep(2)  # CDN 刷新
            asset_uri = upload_media(raw_url, job["name"])
            _update_job(job_id, status="done", asset_uri=asset_uri)
            print(f"[{job['name']}] 完成: {asset_uri}")
        except Exception as e:
            _update_job(job_id, status="failed", error=str(e))
            print(f"[{job['name']}] 失败: {e}")
        time.sleep(1)

    print("所有任务处理完毕")

if __name__ == "__main__":
    main()
