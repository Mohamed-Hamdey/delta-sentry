import os
from huggingface_hub import HfApi, login

# 1. Authenticate
login()

# 2. Auto-detect username
api = HfApi()
USERNAME = api.whoami()["name"]
print(f"✅ Authenticated as: {USERNAME}")

# 3. Define the MODEL repo (not the space)
MODEL_REPO_ID = f"{USERNAME}/delta-sentry-b3-weights"
LOCAL_MODEL_PATH = "./models/b3_best.pt"
PATH_IN_REPO = "b3_best.pt" # Path inside the model repo

# 4. Sanity checks
if not os.path.exists(LOCAL_MODEL_PATH):
    raise FileNotFoundError(f"❌ Local file not found: {LOCAL_MODEL_PATH}")
size_mb = os.path.getsize(LOCAL_MODEL_PATH) / (1024 * 1024)
print(f"📦 Local file size: {size_mb:.1f} MB")

# 5. Create the repo if it doesn't exist
api.create_repo(repo_id=MODEL_REPO_ID, repo_type="model", exist_ok=True)
print(f"✅ Model repo ready: {MODEL_REPO_ID}")

# 6. Upload
print(f"⬆️  Uploading {LOCAL_MODEL_PATH} → {MODEL_REPO_ID}/{PATH_IN_REPO}")
api.upload_file(
    path_or_fileobj=LOCAL_MODEL_PATH,
    path_in_repo=PATH_IN_REPO,
    repo_id=MODEL_REPO_ID,
    repo_type="model", # Important: this is now a "model" repo
)
print("✅ Upload complete!")
print(f"   View it at: https://huggingface.co/{MODEL_REPO_ID}")