# test_github.py
from github import Github
import os
from dotenv import load_dotenv

load_dotenv()

g = Github(os.getenv("GITHUB_TOKEN"))
repo = g.get_repo(os.getenv("GITHUB_REPO"))
print(f"✅ Connected to repo: {repo.full_name}")