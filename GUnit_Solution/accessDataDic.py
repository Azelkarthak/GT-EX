import requests
from bs4 import BeautifulSoup
import re
import os
from dotenv import load_dotenv

# Load environment variables from .env file     
load_dotenv()


def get_file_content(workspace, repo_slug, branch, file_path, username, app_password):
    url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/src/{branch}/{file_path}"

    response = requests.get(url, auth=(username, app_password))
    if response.status_code == 200:
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')

        paragraphs = soup.find_all('p')
        field_map = {}

        for p in paragraphs:
            text = p.text.strip()

            # Match: "FieldName FieldType"
            match = re.match(r'(\w+)\s+([\w\.]+)', text)
            if match:
                field_name = match.group(1)
                field_type = match.group(2)
                field_map[field_name] = field_type
                print(f"Matched general field: {field_name} -> {field_type}")

            # Match: "FieldName foreign key to TableName"
            foreign_key_match = re.search(r'(\w+)\s+foreign key to (\w+)', text)
            if foreign_key_match:
                field_name = foreign_key_match.group(1)
                field_type = foreign_key_match.group(2)
                field_map[field_name] = field_type

            # Match: "FieldName type key to TypeKeyName"
            type_key_match = re.search(r'(\w+)\s+type key to (\w+)', text)
            if type_key_match:
                field_name = type_key_match.group(1)
                field_type = f"typekey.{type_key_match.group(2)}"
                field_map[field_name] = field_type

            # Match: "FieldName array key for ClassName"
            array_key_match = re.search(r'(\w+)\s+array key for (\w+)', text)
            if array_key_match:
                field_name = array_key_match.group(1)
                field_type = f"ArrayList<{array_key_match.group(2)}>"
                field_map[field_name] = field_type

        return field_map
    else:
        print(f"Failed to fetch HTML from Bitbucket: {response.status_code}")
        return {}

def find_file_by_name(workspace, repo_slug, branch, start_path, filename, username, app_password, depth=10):
    base_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/src/{branch}/{start_path}?max_depth={depth}&pagelen=100"

    url = base_url
    while url:
        print(f"📡 Requesting: {url}")
        response = requests.get(url, auth=(username, app_password))
        print(f"🔄 Status: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ Error: {response.text}")
            return None

        data = response.json()
        print(f"📦 Items fetched: {len(data.get('values', []))}")

        for item in data.get("values", []):
            path = item.get("path", "")
            item_type = item.get("type", "")
            print(f"🧾 {item_type}: {path}")
            if item_type == "commit_file" and path.endswith(filename):
                print(f"✅ Found file: {path}")
                return path

        url = data.get("next", None)

    print(f"❌ File '{filename}' not found in '{start_path}' (depth {depth})")
    return None

print("🚀 Starting file search...")

BITBUCKET_USERNAME = os.getenv('BITBUCKET_USERNAME_PERSONAL')
BITBUCKET_APP_PASSWORD = os.getenv('BITBUCKET_PASSWORD_PERSONAL')
BITBUCKET_WORKSPACE = os.getenv('BITBUCKET_WORKSPACE_PERSONAL')
BITBUCKET_REPO_SLUG = os.getenv('BITBUCKET_REPO_SLUG_PERSONAL')
BITBUCKET_BRANCH = os.getenv('BITBUCKET_BRANCH_PERSONAL')  # or 'master'
start_path = "PolicyCenter"
filename = "Account.html"


print(f"BITBUCKET_USERNAME: {BITBUCKET_USERNAME}")
print(f"BITBUCKET_WORKSPACE: {BITBUCKET_WORKSPACE}")        
print(f"BITBUCKET_REPO_SLUG: {BITBUCKET_REPO_SLUG}")
print(f"BITBUCKET_BRANCH: {BITBUCKET_BRANCH}")
print(f"Start Path: {start_path}")
print(f"BITBUCKET_APP_PASSWORD: {BITBUCKET_APP_PASSWORD}")

file_path = find_file_by_name(BITBUCKET_WORKSPACE, BITBUCKET_REPO_SLUG, BITBUCKET_BRANCH, start_path, filename, BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD)

if file_path:
    print(f"✅ File found at: {file_path}")
    content = get_file_content(BITBUCKET_WORKSPACE, BITBUCKET_REPO_SLUG, BITBUCKET_BRANCH, file_path, BITBUCKET_USERNAME, BITBUCKET_APP_PASSWORD)
    if content:
        print(content)
        
else:
    print(f"❌ File '{filename}' not found.")

