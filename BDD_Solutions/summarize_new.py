import os
import pandas as pd
from dotenv import load_dotenv
from google import genai
import time

load_dotenv()

API_KEY = os.getenv("API_KEY")

client = genai.Client(api_key=API_KEY)

MODEL_NAME = "models/gemini-2.5-flash"

# Directory where summarized file will be saved
UPLOAD_FOLDER = "upload"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


def summarize_text(summary):

    prompt = f"""
Summarize the following defect summary so it can be used to find similar defects later.

Defect Summary:
{summary}

Return a short semantic summary.
"""

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt
        )

        return response.text

    except Exception as e:
        print("Summarization error:", e)
        return "Error in summarization"


def summarize_and_store_locally(file_path, file_type):

    try:

        # Load input file
        if file_type == "csv":
            df = pd.read_csv(file_path)

        elif file_type == "xlsx":
            df = pd.read_excel(file_path)

        else:
            raise ValueError("Unsupported file type")

        # Keep only needed columns
        df = df[['Summary', 'Issue key', 'Issue id', 'Project name', 'Assignee', 'Components']]

        df['Summary'] = df['Summary'].astype(str)

        if 'abstract' not in df.columns:
            df['abstract'] = None

        for index, row in df.iterrows():

            if pd.isnull(row['abstract']) or row['abstract'] == "":

                summary = row['Summary']

                summarized = summarize_text(summary)

                df.at[index, 'abstract'] = summarized

                # prevent API rate limit
                time.sleep(1)

        timestamp = str(int(time.time()))

        output_file_path = os.path.join(
            UPLOAD_FOLDER,
            f"summarized_{timestamp}.csv"
        )

        df.to_csv(output_file_path, index=False)

        print(f"File saved: {output_file_path}")

        return output_file_path

    except Exception as e:
        print("Error:", e)
        return None