import os

# Clear any AWS credentials that would override Earthdata cookie auth
for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN", "AWS_DEFAULT_REGION"):
    os.environ.pop(var, None)