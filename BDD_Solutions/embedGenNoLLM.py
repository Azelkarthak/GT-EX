import os
import asyncio
import boto3
import logging
from datetime import datetime
import uuid
from dotenv import load_dotenv

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders.csv_loader import CSVLoader

from langchain.retrievers import ContextualCompressionRetriever
from flashrank import Ranker
from langchain.retrievers.document_compressors import FlashrankRerank

# Load env
load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("aws_access_key_id")
AWS_SECRET_ACCESS_KEY = os.getenv("aws_secret_access_key")
AWS_TEST_OUTPUT_BUCKET = os.getenv("aws_test_output_bucket")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

vectorstore = None


# =========================
# REMOVE DUPLICATES
# =========================
def remove_duplicates(lst):
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]


# =========================
# EMBEDDING
# =========================
def vector_embedding(file_path):
    global vectorstore

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

    logger.info("✅ Embedding ready")


# =========================
# PURE SIMILARITY ENGINE
# =========================
async def generating_defect(issues):
    global vectorstore

    if vectorstore is None:
        vectorstore = Chroma(
            persist_directory="BDD_Solutions/chroma_db",
            embedding_function=embeddings
        )

    issues = remove_duplicates(issues)

    # Reranker
    ranker = Ranker(model_name="ms-marco-TinyBERT-L-2-v2")
    compressor = FlashrankRerank(client=ranker, top_n=5)

    retriever = ContextualCompressionRetriever(
        base_compressor=compressor,
        base_retriever=vectorstore.as_retriever(search_kwargs={"k": 20})
    )

    final_rows = []

    for issue in issues:
        docs = retriever.invoke(issue)

        matches = 0

        for doc in docs:
            score = doc.metadata.get("relevance_score", 1)

            if score < 0.5:
                continue

            content = doc.page_content.replace("\n", " ")

            row = f"{issue},{content}"
            final_rows.append(row)

            matches += 1

            if matches >= 3:
                break

        if matches == 0:
            final_rows.append(f"{issue},Not Found")

    # CSV Header
    csv_output = "Input,Matched Data\n" + "\n".join(final_rows)

    # =========================
    # SAVE TO S3
    # =========================
    key = f"DefectPattern_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.csv"

    s3_client.put_object(
        Bucket=AWS_TEST_OUTPUT_BUCKET,
        Key=key,
        Body=csv_output
    )

    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": AWS_TEST_OUTPUT_BUCKET, "Key": key},
        ExpiresIn=3600
    )

    print(f"✅ File ready: {url}")

    return url


# =========================
# HANDLERS
# =========================
def handle_start_embedding_button_click(filepath):
    logger.info("🚀 Embedding start")
    vector_embedding(filepath)


def handle_defect_detection_button_click(issues):
    logger.info("🚀 Running similarity engine")
    return asyncio.run(generating_defect(issues))