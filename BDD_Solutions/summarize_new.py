import os
import pandas as pd
from dotenv import load_dotenv
from google.generativeai import configure, GenerativeModel
import time

load_dotenv()

GOOGLE_API_KEY = os.getenv("API_KEY")

configure(api_key=GOOGLE_API_KEY)
model = GenerativeModel(model_name="gemini-1.0-pro")

# Directory where the summarized file will be saved
UPLOAD_FOLDER = "upload"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def summarize_and_store_locally(file_path, file_type):
    
    try:
        # Load the input file based on the file type (CSV or Excel)
        if file_type == 'csv':
            df = pd.read_csv(file_path)
        elif file_type == 'xlsx':
            df = pd.read_excel(file_path)
        else:
            raise ValueError("Unsupported file type. Use 'csv' or 'excel'.")

        # Drop all columns except Summary, Issue key, Issue id, Project name, Assignee,  Components, and Description
        df = df[['Summary', 'Issue key', 'Issue id', 'Project name', 'Assignee', 'Components']]

        # Ensure 'Summary' column is a string
        df['Summary'] = df['Summary'].astype(str)

        # Check if 'Summarised_Summary' column exists, if not, create it
        if 'abstract' not in df.columns:
            df['abstract'] = None

        # Summarize summary only where 'Summarised_Summary' is null or empty
        for index, row in df.iterrows():
            if pd.isnull(row['abstract']) or row['abstract'] == '':
                summary = row['Summary']
                try:
                    convo = model.start_chat()
                    convo.send_message(
                        f"Summarize the following defect summary: {summary}. "
                        "Summarize in such a manner that it will further be used for fetching similar defect summary."
                    )
                    summary = convo.last.text
                except Exception as e:
                    summary = "Error in summarization"
                    print(f"Error summarizing: {e}")
                
                # Update the DataFrame with the generated summary
                df.at[index, 'abstract'] = summary

                # Wait for 3 seconds before the next request
                time.sleep(3)

        # Save the updated DataFrame to the 'upload' folder
        timestamp = str(int(time.time()))
        output_file_path = os.path.join(UPLOAD_FOLDER, f"summarized_{timestamp}.csv")
        df.to_csv(output_file_path, index=False)

        print(f"File successfully saved to: {output_file_path}")
        return output_file_path

    except Exception as e:
        print(f"An error occurred: {e}")
        return None