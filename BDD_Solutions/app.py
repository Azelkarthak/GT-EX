# import os
# import uuid
# import json

# from flask import Flask, render_template, request, redirect, session, jsonify
# from aws_s3 import generate_bdd_from_jira, generate_bdd_scenario, generate_test_data, upload_file_to_s3
# from jira import get_issues, get_sprintid, get_boardid, get_issues_bug
# from performancecomapre import compare_json
# from summarize_new import summarize_and_store_locally
# from embedGenerate import handle_start_embedding_button_click, handle_defect_detection_button_click

import os
import uuid
import json

from flask import Flask, render_template, request, redirect, session, jsonify
from dotenv import load_dotenv

# Load .env file if present
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# ✅ Import internal modules from the same package
from BDD_Solutions.aws_s3 import (
    generate_bdd_from_jira,
    generate_bdd_scenario,
    generate_test_data,
    upload_file_to_s3
)
from BDD_Solutions.jira import (
    get_issues,
    get_sprintid,
    get_boardid,
    get_issues_bug
)
from BDD_Solutions.performancecomapre import compare_json
from BDD_Solutions.summarize_new import summarize_and_store_locally
from BDD_Solutions.embedGenerate import (
    handle_start_embedding_button_click,
    handle_defect_detection_button_click
)

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_FOLDER = './static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


@app.route("/upload-bdd", methods=['POST'])
def upload_bdd():
    if 'username' not in session:
        session['username'] = str(uuid.uuid4())
    username = session['username']
    file = request.files['file']
    # print('FileName= ' + file.filename)
    file_path = UPLOAD_FOLDER + f"/{username}_input.xlsx"
    if os.path.exists(file_path):
        os.remove(file_path)
    file.save(file_path)
    is_uploaded = upload_file_to_s3(username)
    if is_uploaded:
        os.remove(file_path)
        return redirect('/generate-bdd')
    return render_template('index.html', status="There is some error in uploading file. Please try again.")


@app.route("/generate-bdd")
def generate_bdd():
    username = session['username']
    url = generate_bdd_scenario(username)
    if url is None:
        return render_template('index.html', status="Failed to generate BDD scenario")
    return render_template('index.html', status="Bdd generated successfully", response=url)


@app.route("/get_bdd_jira_boardid", methods=['POST'])
def get_bdd_jira_boardid():
    try:
        jira_url = request.form.get('jira_url')
        email = request.form.get('email')
        password = request.form.get('password')

        print("📥 Received Jira Credentials:")
        print(f"   🔗 URL: {jira_url}")
        print(f"   📧 Email: {email}")
        print(f"   🔒 Password: {password}")

        board_ids = get_boardid(jira_url, email, password)

        if not board_ids:
            print("⚠️ No board IDs returned.")
            return jsonify(board_ids=[])

        print("✅ Board IDs Fetched:", board_ids)
        return jsonify(board_ids=board_ids)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(error=f"❌ Error: {str(e)}")



@app.route("/get_bdd_jira_sprintid", methods=['POST'])
def get_bdd_jira_sprintid():
    try:
        jira_url = request.form.get('jira_url')
        email = request.form.get('email')
        password = request.form.get('password')
        board_id = request.form.get('board_id')
        # print(jira_url)
        # print(email)
        # print(password)
        # print(board_id)
        sprint_ids = get_sprintid(jira_url, email, password, board_id)
        return jsonify(sprint_ids=sprint_ids)

    except Exception as e:
        return jsonify(error=str(e))

@app.route("/get_bdd_jira_issue_bug", methods=['POST'])
def get_bdd_jira_issue_bug():
    try:
        jira_url = request.form.get('jira_url')
        email = request.form.get('email')
        password = request.form.get('password')
        board_id = request.form.get('board_id')
        sprint_id = request.form.get('sprint_id')
        print("Defect",jira_url)
        print("Defect",email)
        print("Defect",password)
        print("Defect","board_id="+board_id)
        print("Defect","sprint_id="+sprint_id)
        issue_bugs = get_issues_bug(jira_url, email, password, board_id, sprint_id)
        # Print out all the issues fetched for verification
        print("Fetched issues: ", issue_bugs)
        return jsonify(issue_bugs=issue_bugs)

    except Exception as e:
        return jsonify(error=str(e))


@app.route("/generate_bdd_jira", methods=['POST'])
def generate_bdd_jira():
    try:
        jira_url = request.form.get('jira_url')
        email = request.form.get('email')
        password = request.form.get('password')
        board_id = request.form.get('board_id')
        sprint_id = request.form.get('sprint_id')
        user_story = get_issues(jira_url=jira_url, email=email, password=password,
                                board_id=board_id, sprint_id=sprint_id)
        if len(user_story) == 0:
            return render_template('index.html', status="No active user stories found")
        url = generate_bdd_from_jira(user_story)
        if url is None:
            return render_template('index.html', status="Failed to generate BDD scenario")
        return render_template('index.html', status="Bdd generated successfully", response=url)
    except:
        return render_template('index.html', status="Provide correct details")
    
@app.route("/generate_defect", methods=['POST'])
def generate_defect_detection():
    try:
        # Check if "Select All" is chosen
        selected_issue = request.form.get('issue_id')
        all_issues_json = request.form.get('all_issues')  # This will be present if "Select All" is chosen

        # Function to extract the part after the colon
        def extract_issue_description(issue):
            return issue.split(": ", 1)[1] if ": " in issue else issue

        # If "Select All" is selected, process all issues
        if selected_issue == 'select_all' and all_issues_json:
            issues = json.loads(all_issues_json)
            # Extract only the issue descriptions (after the colon)
            issues = [extract_issue_description(issue) for issue in issues]
            print("Processing all issues...", issues)
        else:
            # Process individual issue
            issues = [extract_issue_description(selected_issue)]
            print(issues)
        
        # Pass the cleaned issues to the function
        url = handle_defect_detection_button_click(issue=issues)
        if url is None:
            return render_template('index.html', status="Failed to generate test data")
        return render_template('index.html', status="Test data generated successfully", response=url)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"An error occurred: {e}")
        return render_template('index.html', status="Error processing issues")


# LATEST
# @app.route("/generate_defect", methods=['POST'])
# def generate_defect_detection():
#     try:
#         # Check if "Select All" is chosen
#         selected_issue = request.form.get('issue_id1')
#         all_issues_json = request.form.get('all_issues')  # This will be present if "Select All" is chosen

#         # If "Select All" is selected, process all issues
#         if selected_issue == 'select_all' and all_issues_json:
#             issues = json.loads(all_issues_json)
#             print("Processing all issues...", issues)
#         else:
#             issues = [selected_issue]  # Process individual issue
#             for issue in issues:
#                 print(issue)
        
#         url = handle_defect_detection_button_click(issue=issues)
#         if url is None:
#             return render_template('index.html', status="Failed to generate test data")
#         return render_template('index.html', status="Test data generated successfully", response=url)
#     except Exception as e:
#         print(f"An error occurred: {e}")
#         return render_template('index.html', status="Error processing issues")
        

# @app.route("/generate_defect", methods=['POST'])
# def generate_defect_detection():
#     try:
#         # Get the whole array of issues from the form
#         all_issues_json = request.form.get('all_issues')  # This should contain the full array

#         if all_issues_json:
#             issues = json.loads(all_issues_json)  # Convert the JSON string back into a list
#             print("Processing all issues:", issues)
#         else:
#             return render_template('index.html', status="No issues to process")

#         # Now pass the entire array of issues to the LLM function to generate the defect report
#         url = handle_defect_detection_button_click(issue=issues)

#         if url is None:
#             return render_template('index.html', status="Failed to generate test data")
#         return render_template('index.html', status="Test data generated successfully", response=url)
#     except Exception as e:
#         print(f"An error occurred: {e}")
#         return render_template('index.html', status="Error processing issues")

@app.route("/generate_test", methods=['POST'])
def generate_test():
    lob = request.form.get('lob')
    state = request.form.get('state')
    test_cases = request.form.get('test_cases')
    url = generate_test_data(lob, state, test_cases)
    if url is None:
        return render_template('index.html', status="Failed to generate test data")
    return render_template('index.html', status="Test data generated successfully", response=url)


# Trigger summarization and store in upload
@app.route("/trigger_summarization", methods=["POST"])
def trigger_summarization():
    upload_folder = "./upload"
    print("Triggering summarization...", upload_folder)
    try:
        # Get all files in the upload directory
        files = [os.path.join(upload_folder, f) for f in os.listdir(upload_folder)]
        
        if len(files) == 0:
            return render_template('index.html', status="No files found for embedding")
        
        # Get the file with the latest creation time
        latest_file = max(files, key=os.path.getctime)
        # Determine the file type based on the file extension
        file_type = os.path.splitext(latest_file)[1].lower().replace('.', '')
        
        # Call the embedding function with the latest file
        print((f"Summarization process started for file: {latest_file}"))
        url = summarize_and_store_locally(latest_file,file_type)
        print("Summarization Completed")
        # Return a success message after completion
        return render_template('defect.html', status="Summarization completed successfully", url=url)
    except Exception as e:
        print(f"Error: {e}")
        return render_template('defect.html', status="Error while processing the file")
    

@app.route("/trigger_embedding", methods=["POST"])
def triggerEmbedding():
    upload_folder = "./upload"
    
    print("Triggering embedding...", upload_folder)
    try:
        # Get all files in the upload directory
        files = [os.path.join(upload_folder, f) for f in os.listdir(upload_folder)]
        
        if len(files) == 0:
            return render_template('index.html', status="No files found for embedding")

        # Get the file with the latest creation time
        latest_file = max(files, key=os.path.getctime)
        
        # Call the embedding function with the latest file
        print((f"Embedding process started for file: {latest_file}"))
        url = handle_start_embedding_button_click(latest_file)
        
        return render_template('defect.html',status="Embedding completed successfully")
    
    except Exception as e:
        print(f"Error: {e}")
        return render_template('index.html', status="Error while processing the file")

@app.route("/compare_performance", methods=['POST'])
def compare_performance():
    file1 = request.files['json_file1']
    file2 = request.files['json_file2']
    # Read the files and load them as JSON
    json1 = json.load(file1)
    json2 = json.load(file2)
    print(file1,file2)
    metrics_to_compare = ["minResponseTime", "maxResponseTime", "meanResponseTime",
                          "percentiles1", "percentiles2", "percentiles3", "percentiles4",
                          "standardDeviation"]
    url=compare_json(json1, json2, metrics_to_compare)
    return render_template('index.html', status="Comparison Report generated successfully",response=url)

@app.route('/jira')
def show_jira():
    return render_template("jira.html")

@app.route('/')
def home():
    return render_template('home.html')  # or index.html if you're using that

@app.route('/test')
def show_test():
    return render_template("test.html")

@app.route('/performance')
def show_performance():
    return render_template("performance.html")

@app.route('/defect')
def show_defect():
    return render_template("defect.html")


# def run():
#     port = int(os.environ.get("PORT", 5002))
#     app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
