import os
import time
import asyncio
import boto3
import logging
from dotenv import load_dotenv

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders.csv_loader import CSVLoader

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain

from langchain.retrievers import ContextualCompressionRetriever
from flashrank import Ranker
from langchain.retrievers.document_compressors import FlashrankRerank

from BDD_Solutions.formatePrint import print_formatted_documents
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
# GLOBAL SINGLETONS (🔥 FIX)
# =========================
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

vectorstore = None


# =========================
# EMBEDDING FUNCTION
# =========================
def vector_embedding(file_path):
    global vectorstore

    try:
        loader = CSVLoader(file_path=file_path, encoding='utf-8')
        docs = loader.load()

        splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=100)
        final_docs = splitter.split_documents(docs)

        for i, doc in enumerate(final_docs):
            doc.metadata["id"] = i

        vectorstore = Chroma.from_documents(
            final_docs,
            embeddings,
            persist_directory="BDD_Solutions/chroma_db"
        )

        logger.info("✅ Embedding completed")

    except Exception as e:
        logger.error(f"Embedding error: {e}", exc_info=True)


# =========================
# DEFECT GENERATION (WITH FALLBACK)
# =========================
async def generating_defect(issues):
    global vectorstore

    try:
        if vectorstore is None:
            vectorstore = Chroma(
                persist_directory="BDD_Solutions/chroma_db",
                embedding_function=embeddings
            )

        combined_issues = "\n".join(
            [f"{i+1}. {issue}" for i, issue in enumerate(issues)]
        )

        # =========================
        # RETRIEVER SETUP
        # =========================
        flashrank_client = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")

        compressor = FlashrankRerank(
            client=flashrank_client,
            top_n=5,
            model="ms-marco-TinyBERT-L-2-v2"
        )

        retriever = ContextualCompressionRetriever(
            base_compressor=compressor,
            base_retriever=vectorstore.as_retriever(search_kwargs={"k": 20})
        )

        # Fetch context once
        compressed_docs = retriever.invoke(combined_issues)
        print_formatted_documents(compressed_docs)

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
                Answer strictly based on the provided context.

                <context>
                {context}
                </context>

                Input Issues:
                {input}

                Task:
                - For EACH issue, find similar defects
                - Max 3 results per issue

                Output CSV:
                Input, Issue ID, Summary, Issue key, Status, Project name, Assignee, Components, Priority

                Rules:
                - If no match → "Not Found"
                - No markdown
                """
            )

            document_chain = create_stuff_documents_chain(llm, prompt)
            retrieval_chain = create_retrieval_chain(retriever, document_chain)

            response = retrieval_chain.invoke({"input": combined_issues})

            cleaned_response = response["answer"].replace("```csv", "").replace("```", "").strip()

        except Exception as llm_error:
            logger.warning(f"⚠️ Gemini failed → fallback triggered: {llm_error}")

            if "quota" in str(llm_error).lower():
                logger.warning("🔥 Gemini quota exceeded")

            # =========================
            # 🔥 FALLBACK: PURE SIMILARITY
            # =========================
            simple_retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

            results = []

            for issue in issues:
                docs = simple_retriever.invoke(issue)

                if not docs:
                    results.append(f'"{issue}","Not Found"')
                    continue

                for doc in docs:
                    meta = doc.metadata
                    content = doc.page_content.replace(",", " ")

                    results.append(
                        f'"{issue}","{meta.get("Issue ID","")}","{content}"'
                    )

            cleaned_response = "\n".join(results)

        # =========================
        # CLEAN CSV
        # =========================
        consolidated_csv = clean_and_validate_response(cleaned_response)

        # =========================
        # UPLOAD TO S3
        # =========================
        key = f"DefectPattern_{int(time.time())}.csv"

        s3_response = s3_client.put_object(
            Bucket=AWS_TEST_OUTPUT_BUCKET,
            Key=key,
            Body=consolidated_csv
        )

        status = s3_response.get("ResponseMetadata", {}).get("HTTPStatusCode")

        url = s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": AWS_TEST_OUTPUT_BUCKET,
                "Key": key
            },
            ExpiresIn=3600
        )

        logger.info(f"✅ File uploaded: {url}")

        return url if status == 200 else None

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