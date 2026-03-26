import os
import time
import asyncio
import boto3
import logging
import shutil
import csv

from dotenv import load_dotenv
from langchain.schema import Document

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain

from langchain.retrievers import ContextualCompressionRetriever
from flashrank import Ranker
from langchain.retrievers.document_compressors import FlashrankRerank

from BDD_Solutions.csv_validator import clean_and_validate_response

# =========================
# LOAD ENV
# =========================
load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("aws_access_key_id")
AWS_SECRET_ACCESS_KEY = os.getenv("aws_secret_access_key")
AWS_TEST_OUTPUT_BUCKET = os.getenv("aws_test_output_bucket")
GOOGLE_API_KEY = os.getenv("API_KEY")

# =========================
# AWS CLIENT
# =========================
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

# =========================
# LOGGING
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# GLOBALS
# =========================
CHROMA_PATH = "BDD_Solutions/chroma_db"

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

vectorstore = None


# =========================
# EMBEDDING (STRUCTURED)
# =========================
def vector_embedding(file_path):
    global vectorstore

    try:
        # 🔥 Clean old DB (prevents corruption)
        if os.path.exists(CHROMA_PATH):
            shutil.rmtree(CHROMA_PATH)
            logger.info("🧹 Old vector DB cleared")

        docs = []

        with open(file_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            # Strip spaces, BOM, and skip empty columns from all headers
            reader.fieldnames = [h.strip() for h in reader.fieldnames if h and h.strip()]
            for i, row in enumerate(reader):
                # Also strip keys in each row
                row = {k.strip(): v for k, v in row.items() if k and k.strip()}
                docs.append(
                    Document(
                        page_content=" | ".join([f"{k}: {v}" for k, v in row.items()]),
                        metadata=row  # ✅ STRUCTURED DATA
                    )
                )

        vectorstore = Chroma.from_documents(
            docs,
            embeddings,
            persist_directory=CHROMA_PATH
        )

        logger.info(f"✅ Embedding completed | Total docs: {len(docs)}")

    except Exception as e:
        logger.error(f"❌ Embedding error: {e}", exc_info=True)


# =========================
# DEFECT GENERATION
# =========================
async def generating_defect(issues):
    global vectorstore

    try:
        # Load DB if not loaded
        if vectorstore is None:
            vectorstore = Chroma(
                persist_directory=CHROMA_PATH,
                embedding_function=embeddings
            )

        issues = list(dict.fromkeys(issues))

        # =========================
        # RETRIEVER
        # =========================
        flashrank_client = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")

        compressor = FlashrankRerank(
            client=flashrank_client,
            top_n=5
        )

        retriever = ContextualCompressionRetriever(
            base_compressor=compressor,
            base_retriever=vectorstore.as_retriever(search_kwargs={"k": 20})
        )

        # =========================
        # BUILD CONTEXT (STRUCTURED)
        # =========================
        context_data = []

        for issue in issues:
            docs = retriever.invoke(issue)

            logger.info(f"Issue: {issue} | Retrieved: {len(docs)} docs")

            for doc in docs:
                context_data.append(doc.metadata)  # ✅ PURE STRUCTURED

        # =========================
        # TRY GEMINI
        # =========================
        try:
            llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
                google_api_key=GOOGLE_API_KEY,
                temperature=0
            )

            prompt = ChatPromptTemplate.from_template(
                """
You are given structured defect data.

Context:
{context}

Input Issues:
{input}

Task:
- For EACH issue, find top 3 similar defects
- Match based on meaning (not exact text)

Output CSV:
Input,Issue ID,Summary,Issue key,Status,Project name,Assignee,Components,Priority

Rules:
- One row per result
- No extra text
- If nothing found → Not Found
"""
            )

            document_chain = create_stuff_documents_chain(llm, prompt)

            response = document_chain.invoke({
                "input": "\n".join(issues),
                "context": str(context_data[:200])  # limit size
            })

            cleaned_response = response.strip()

        except Exception as llm_error:
            logger.warning(f"⚠️ Gemini failed → fallback: {llm_error}")

            # =========================
            # FALLBACK (NO REGEX)
            # =========================
            simple_retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

            results = []
            results.append("Input,Issue ID,Summary,Issue key,Status,Project name,Assignee,Components,Priority")

            for issue in issues:
                docs = simple_retriever.invoke(issue)

                if not docs:
                    results.append(f'"{issue}","Not Found","","","","","","",""')
                    continue

                for doc in docs:
                    meta = doc.metadata

                    results.append(
                        f'"{issue}",'
                        f'"{meta.get("Issue id","")}",'
                        f'"{meta.get("Summary","")}",'
                        f'"{meta.get("Issue key","")}",'
                        f'"{meta.get("Status","")}",'
                        f'"{meta.get("Project name","")}",'
                        f'"{meta.get("Assignee","")}",'
                        f'"{meta.get("Components","")}",'
                        f'"{meta.get("Priority","")}"'
                    )

            cleaned_response = "\n".join(results)

        # =========================
        # CLEAN CSV
        # =========================
        consolidated_csv = clean_and_validate_response(cleaned_response)

        # =========================
        # UPLOAD S3
        # =========================
        key = f"DefectPattern_{int(time.time())}.csv"

        s3_client.put_object(
            Bucket=AWS_TEST_OUTPUT_BUCKET,
            Key=key,
            Body=consolidated_csv.encode("utf-8-sig")
        )

        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": AWS_TEST_OUTPUT_BUCKET, "Key": key},
            ExpiresIn=3600
        )

        logger.info(f"✅ File uploaded: {url}")

        return url

    except Exception as e:
        logger.error(f"❌ Defect generation error: {e}", exc_info=True)
        return None


# =========================
# HANDLERS
# =========================
def handle_start_embedding_button_click(filepath):
    logger.info("🚀 Starting embedding...")
    vector_embedding(filepath)


def handle_defect_detection_button_click(issues):
    logger.info("🚀 Generating defects...")
    return asyncio.run(generating_defect(issues))