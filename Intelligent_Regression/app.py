from flask import Flask, render_template, request, send_file
import google.generativeai as genai
import requests
import json
import time
import websocket
import select
import requests
from base64 import b64decode
from dotenv import load_dotenv
import os
import re
import time
import random


app = Flask(__name__)

load_dotenv()
api_key = os.getenv("gemini_token")


## Ensure the key exists
if not api_key:
    raise ValueError("API key not found. Please set GEN_AI_API_KEY in your .env file.")

# client = genai.Client(api_key=api_key)
genai.configure(
    api_key=api_key
)


# ---------- Jherkin Test Generator Function ----------
def generate_JherkinTest(rule, lob, keyword, center):
    jherkin_prompt = (
        f'Given the following code content extracted from a Guidewire module {center} LOB: {lob}, generate Functional test scenarios in Gherkin BDD format. Focus on business rules, coverages, endorsement, form , validations and system outcomes — not internal code logic or unit-level conditions.\n\n'
        f'The context is: "{keyword}"\n\n'
        f'Analysis the Entire code and provide the scenarios that test core {center} workflows, including:\n\n'
        '*   **Business-related rules and validations:** Coverage (Limit, Term, Part, Percentage, Factor ,Code) deductibles, endorsements, Modifier, Validation ,Business Rules.\n'
        '*   **Factor Table:** Scenarios covering the factor table based calculation\n'
        '*   **Geographic factors:** State-specific rules, endorsements, and forms.  Pay close attention to how state-specific endorsements are automatically applied or can be manually added/removed.\n'
        '*   **Form:** Form triggered based on different rules.\n\n'
        '*  ** Tables:** Scenarios covering the table data and its impact on the policy.\n\n' 
        "For scenarios involving different values, please use Gherkin 'Examples' tables to represent these variations within a single scenario outline.\n\n"
        "Please apply the tag @regression to the Feature sections that cover core business functionality like Business-related rules,validations,*Geographic factors,Form,Endorsements and Factors.\n"
        f'Try to provide scenarios all possible scenarios for {keyword}.\n\n'


        f'{rule}\n\n'
        
    )


    # Save refinedCode to a txt file
    with open("Intelligent_Regression/jherkin_prompt.txt", "w", encoding="utf-8") as f:
        f.write(jherkin_prompt)

    print("Saved jherkin_prompt to jherkin_prompt.txt")

    while True:
       
       
        response = get_ai_content(jherkin_prompt)

        if not response:
            return "Failed to generate response."

        return response  # Valid response received, return it


# ---------- AI Content Generation Function ----------
def get_ai_content(prompt, max_retries=3, base_delay=2,temperature=0.0):
    retry_count = 0
    print(f"Generating content for prompt: {prompt[:50]}...")  # Print first 50 chars of the prompt
    while retry_count <= max_retries:
        try:

            model = genai.GenerativeModel("gemini-2.0-flash")
            print("Calling model")
            response = model.generate_content(
                contents=prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temperature
            )
            )
            

            content_text = response.candidates[0].content.parts[0].text

            if "Error" in content_text:
                print(f"AI Response: {content_text}")

            # Extract token counts
            prompt_tokens = response.usage_metadata.prompt_token_count
            response_tokens = response.usage_metadata.candidates_token_count
            total_tokens = response.usage_metadata.total_token_count

            # Print token info
            print(f"\n--- Token Usage ---")
            print(f"Prompt Tokens: {prompt_tokens}")
            print(f"Response Tokens: {response_tokens}")
            print(f"Total Tokens: {total_tokens}\n")

            return content_text

        except Exception as e:
            error_message = str(e)
            print(f"Attempt {retry_count + 1}: Error generating AI content: {error_message}")

            # Retry only on specific transient errors (like 503)
            if "503" in error_message or "UNAVAILABLE" in error_message.upper():
                retry_count += 1
                delay = base_delay * (2 ** (retry_count - 1)) + random.uniform(0, 1)
                print(f"Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                # Non-retryable error
                break

    print("Failed to get a valid response after retries.")
    return None

@app.route('/update_keywords', methods=["GET", "POST"])
def update_keywords():
    if request.method == "GET":
        return render_template('keyword.html')  # Show the form on GET

    # Handle POST
    center = request.form.get('center')
    lob = request.form.get('lob')
    keyword = request.form.get('keyword')
    keyword_dependency = request.form.get('keyword_dependency', '')

    if not (center and lob and keyword):
        return "Missing required fields", 400

    # File paths
    dropdown_mapping_path = 'Intelligent_Regression/static/dropdown_mapping.json'
    keyword_dependency_path = 'Intelligent_Regression/keyword_mapping.json'

    # Load and update dropdown_mapping
    with open(dropdown_mapping_path, 'r') as f1:
        file1_data = json.load(f1)

    if center not in file1_data:
        file1_data[center] = {}

    if lob not in file1_data[center]:
        file1_data[center][lob] = []

    exists = any(k['value'] == keyword for k in file1_data[center][lob])
    if not exists:
        file1_data[center][lob].append({'value': keyword, 'text': keyword})

    with open(dropdown_mapping_path, 'w') as f1:
        json.dump(file1_data, f1, indent=2)

    # Load and update keyword_dependency
    with open(keyword_dependency_path, 'r') as f2:
        file2_data = json.load(f2)

    dependencies = [dep.strip() for dep in keyword_dependency.split(',') if dep.strip()]
    file2_data[keyword] = dependencies

    with open(keyword_dependency_path, 'w') as f2:
        json.dump(file2_data, f2, indent=2)

    return render_template('keyword.html', message="Keyword and dependencies updated successfully")

@app.route('/edit_dependencies', methods=["GET", "POST"])
def edit_dependencies():
    keyword_dependency_path = 'Intelligent_Regression/keyword_mapping.json'

    # Load existing data
    with open(keyword_dependency_path, 'r') as f:
        keyword_data = json.load(f)

    if request.method == "POST":
        keyword = request.form.get('keyword')
        new_deps = request.form.get('new_dependencies', '')
        new_deps_list = [d.strip() for d in new_deps.split(',') if d.strip()]
        keyword_data[keyword] = new_deps_list

        with open(keyword_dependency_path, 'w') as f:
            json.dump(keyword_data, f, indent=2)

        return render_template('edit_dependencies.html', keyword_data=keyword_data, message="Dependency updated successfully.")

    return render_template('edit_dependencies.html', keyword_data=keyword_data)

@app.route('/delete_keyword', methods=["POST"])
def delete_keyword():
    keyword = request.form.get('keyword')

    # File paths
    keyword_dependency_path = 'Intelligent_Regression/keyword_mapping.json'
    dropdown_mapping_path = 'Intelligent_Regression/static/dropdown_mapping.json'

    # Load and update keyword_mapping.json
    with open(keyword_dependency_path, 'r') as f:
        keyword_data = json.load(f)

    if keyword in keyword_data:
        del keyword_data[keyword]
        message = f"Keyword '{keyword}' deleted successfully."
    else:
        message = f"Keyword '{keyword}' not found in keyword mapping."

    with open(keyword_dependency_path, 'w') as f:
        json.dump(keyword_data, f, indent=2)

    # Load and update dropdown_mapping.json
    with open(dropdown_mapping_path, 'r') as f:
        dropdown_data = json.load(f)

    removed_from_dropdown = False
    for system, modules in dropdown_data.items():
        for module, items in modules.items():
            if isinstance(items, list):
                # Filter out any item where value matches keyword
                original_len = len(items)
                dropdown_data[system][module] = [item for item in items if item.get('value') != keyword]
                if len(dropdown_data[system][module]) != original_len:
                    removed_from_dropdown = True

    if removed_from_dropdown:
        message += f" Also removed from dropdown mapping."
    else:
        message += f" No matching entries found in dropdown mapping."

    with open(dropdown_mapping_path, 'w') as f:
        json.dump(dropdown_data, f, indent=2)

    return render_template('edit_dependencies.html', keyword_data=keyword_data, message=message)



@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    # UNALLOWED_EXTENSIONS = ['.class', '.jar', '.exe', '.dll', '.pcfc', '.ttx', '.tti', '.gx','.pcf','.xml', '.wsdl', '.xsd', '.png','.svg', '.woff', '.js','.map', '.eti', '.etx', '.en']
    ALLOWED_EXTENSIONS = ['.java','.gwp','.gs','.grs','.gsx','.gr','.txt']
    if request.method == 'POST':
        lob = request.form.get('lob', '').strip()
        keyword = request.form.get('keyword', '').strip()
        center = request.form.get('center', '').strip()

        if lob and keyword and center:
            matched_paths = find_file_path(lob, keyword, center)
            all_contents = ""
            skiped_files = 0
            matched_files = 0
            keyword_files =0

            for path in matched_paths:
                if not any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS):
                    skiped_files += 1
                    continue

                matched_files += 1
                print(f"Processing file: {path}")
                content = get_github_file_content(path)
                if not content:
                    continue

                if keyword.lower() in path.lower():
                    
                    all_contents += f"\n\n# File: {path}\n{content}"
                    keyword_files += 1
                else:
                    if keyword.lower() in content.lower():
                        
                        all_contents += f"\n\n# File: {path}\n{content}"   
                        keyword_files += 1 
                        print(f"Keyword found in file: {path}")

            if all_contents.strip():
                refinedCode = remove_all_javadoc_comments(all_contents).strip()
                # Save refinedCode to a txt file
                with open("Intelligent_Regression/refined_code.txt", "w", encoding="utf-8") as f:
                    f.write(refinedCode)

                
                # Generate Gherkin using refinedCode
                gherkin_result = generate_JherkinTest(rule=refinedCode,lob=lob, keyword=keyword,center=center)
                print(f"Gherkin Result: {gherkin_result}")
                results.append({'path': 'Combined Files', 'result': gherkin_result})
            
            print(f"Matched Files: {matched_files}")
            print(f"Skipped Files: {skiped_files}")
            print(f"Keyword Files: {keyword_files}")


    return render_template('index.html', results=results)


import json

def find_file_path(lob, keyword, center):
    # Load keyword mapping from external JSON file
    try:
        with open("Intelligent_Regression/keyword_mapping.json", "r") as json_file:
            keyword_mapping = json.load(json_file)
    except FileNotFoundError:
        print("Error: keyword_mapping.json not found.")
        return []
    except json.JSONDecodeError:
        print("Error: Failed to parse keyword_mapping.json.")
        return []

    # Determine file path based on center
    if center == "PolicyCenter":
        file_list_path = "Intelligent_Regression/pc_file_path.txt"
    elif center == "ClaimCenter":
        file_list_path = "Intelligent_Regression/cc_file_path.txt"
    else:
        print("Invalid center specified. Please use 'PolicyCenter' or 'ClaimCenter'.")
        return []

    matching_paths = []

    # Prepare search terms: keyword + dependencies (no lob prefix)
    mapped_keywords = keyword_mapping.get(keyword, [])
    search_terms = [keyword] + mapped_keywords

    try:
        with open(file_list_path, "r") as file:
            for line in file:
                clean_line = line.strip()
                if any(term in clean_line for term in search_terms):
                    matching_paths.append(clean_line)

        return matching_paths

    except FileNotFoundError:
        print(f"Error: {file_list_path} not found.")
        return []


# Load environment variables from .env file
load_dotenv()

def get_github_file_content(file_path):
    """
    Fetches the content of a file from a GitHub repository using the GitHub API.
    
    :param file_path: Path to the file in the repository (e.g., 'src/app.py').
    :param branch: Branch name (default is 'main').
    :param token: (Optional) GitHub personal access token for authentication.
    :return: File content as a string, or None if not found.
    """
    owner = os.getenv("repo_owner_exa")
    repo = os.getenv("repo_name_exa")
    token = os.getenv("github_token")
    branch="master"
    
    if not owner or not repo:
        print("Error: GITHUB_OWNER and GITHUB_REPO must be set in the .env file.")
        return None
    
    
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={branch}"
    headers = {}
    
    if token:
        headers["Authorization"] = f"token {token}"
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        file_data = response.json()
        content = b64decode(file_data['content']).decode('utf-8')
        return content
    else:
        print(f"Error {response.status_code}: {response.json().get('message', 'Unknown error')}")
        return None


def remove_all_javadoc_comments(code):
    # Remove Javadoc comments: /** ... */
    code_no_javadoc = re.sub(r"/\*\*.*?\*/", '', code, flags=re.DOTALL)

    # Remove extra blank lines (two or more newlines into one)
    code_cleaned = re.sub(r'\n\s*\n+', '\n', code_no_javadoc)

    # Optionally, strip leading/trailing whitespace from the entire code
    return code_cleaned.strip()

def extract_methods_with_keyword(content, keyword):
    methods = []
    lines = content.splitlines()
    inside_method = False
    brace_count = 0
    method_lines = []

    for line in lines:
        stripped = line.strip()

        # Start of a method
        if re.match(r'(private|public)?\s*function\s+\w+\s*\(.*\)\s*\{', stripped) and not inside_method:
            inside_method = True
            brace_count = stripped.count('{') - stripped.count('}')
            method_lines = [line]
        elif inside_method:
            method_lines.append(line)
            brace_count += line.count('{') - line.count('}')
            if brace_count == 0:
                inside_method = False
                method = "\n".join(method_lines)
                if keyword.lower() in method.lower():
                    methods.append(method.strip())

    return methods


def run():
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    