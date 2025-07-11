import requests
import base64


def get_sha_for_path(repo_owner, repo_name, branch='main'):
    try:
        # GitHub API URL to get repository contents
        path = 'modules/configuration/gsrc'
        api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/modules/configuration?ref={branch}"
        print(api_url)

        response = requests.get(api_url)  # Make GET request to GitHub API
        response.raise_for_status()  # Raise an exception for 4xx/5xx status codes

        # Parse JSON response
        contents = response.json()

        if isinstance(contents, list):
            # Iterate through the contents to find the directory or file
            for item in contents:
                if item['path'] == path:
                    # Return the SHA hash of the directory or file
                    return item['sha']

        # If path not found
        print(f"Path '{path}' not found in repository '{repo_owner}/{repo_name}'")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching repository contents: {e}")
        return None


def fetch_file_content(repo_owner, repo_name, file_path):
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/contents/modules/configuration/gsrc/{file_path}"
    print(url)
    response = requests.get(url)
    if response.status_code == 200:
        content = response.json()["content"]
        decoded_content = base64.b64decode(content).decode('utf-8')
        return decoded_content
    else:
        print(f"Failed to fetch file content. Status code: {response.status_code}")
        return None


def get_file_path(repo_owner, repo_name, sha_hash, file_name):
    search_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/git/trees/{sha_hash}?recursive=1"
    print(search_url)
    response = requests.get(search_url)

    response.raise_for_status()  # Raise an exception for 4xx/5xx status codes

    # Parse JSON response
    contents = response.json()

    for item in contents.get('tree', []):
        if item['path'].endswith(file_name):
            file_path = item['path']
            print(file_path)
    return file_path



