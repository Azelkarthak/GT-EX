import os
import asyncio
import boto3
import logging
from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
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

# Load environment variables
load_dotenv()
AWS_ACCESS_KEY_ID = os.getenv("aws_access_key_id")
AWS_SECRET_ACCESS_KEY = os.getenv("aws_secret_access_key")
AWS_TEST_OUTPUT_BUCKET = os.getenv("aws_test_output_bucket")
# Set OPENAI_API_KEY as an environment variable
GOOGLE_API_KEY = os.getenv("API_KEY")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
    # aws_session_token=AWS_SESSION_TOKEN,
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables to hold embeddings and vector store
embeddings = None
vectorstore = None

def vector_embedding(file_path):
    global embeddings, vectorstore

    try:
        embeddings = OpenAIEmbeddings()
        loader = CSVLoader(file_path=file_path, encoding='utf-8')
        docs = loader.load()
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1200, chunk_overlap=100)
        final_documents = text_splitter.split_documents(docs)
        for id, final_document in enumerate(final_documents):
            final_document.metadata["id"] = id
        vectorstore = Chroma.from_documents(final_documents, embeddings, persist_directory="BDD_Solutions/chroma_db")
        if vectorstore:
            # print("Embedding completed, and vector database is ready.")
            logger.info("Embedding completed, and vector database is ready.")
    except Exception as e:
        # print(f"An error occurred during embedding: {e}")
        logger.error(f"An error occurred during embedding: {e}")
        import traceback
        traceback.print_exc()
    
async def generating_defect(issues):
    global vectorstore
    if vectorstore is None:
        vectorstore = Chroma(persist_directory="BDD_Solutions/chroma_db", embedding_function=OpenAIEmbeddings())
        if vectorstore is None:
            raise ValueError("Vectorstore not initialized. Please run embeddings first.")

    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=GOOGLE_API_KEY, temperature=0)
    model_name = "ms-marco-TinyBERT-L-2-v2"
    flashrank_client = Ranker(model_name=model_name)
    compressor = FlashrankRerank(client=flashrank_client, top_n=5, model=model_name)
    compression_retriever = ContextualCompressionRetriever(base_compressor=compressor, base_retriever=vectorstore.as_retriever(search_kwargs={"k": 20}))

    # Consolidated responses
    consolidated_responses = []

    for issue in issues:  # Iterate through the array of issues
        compressed_docs = compression_retriever.invoke(issue)
        print_formatted_documents(compressed_docs)

        prompt = ChatPromptTemplate.from_template(
            """
            Answer the questions based on the provided context only.
            Please provide the most accurate response based on the question.
            <context>
            {context}
            <context>
            Question: Given the following context, find all issues that have the same meaning as this: "{input}".
            
            For each issue, check if the relevance score is greater than 0.5.
            Return the Issue ID, Summary, Issue key, Status, Project name, Assignee, Components, Priority and input.
            Output the results in CSV format with these columns: Input, Issue ID, Summary, Issue key, Status, Project name, Assignee, Components and Priority.

            IMPORTANT FORMATTING RULES:
            1. Return unique defects if available with each defect must have a different Defect ID.
              1.1 If only one similar defect is found, return that one defect.
              1.2 If no similar defects are found, return a single row with the input followed by "Not Found" for all other fields.
            2. Return defects with relevance score > 0.5 as separate entries
            3. Each entry must be a complete row with all fields properly filled
            4. Do not include any markdown code block formatting (like ```csv) in your response
            5. If no similar defects are found (no defect with relevance score > 0.5), return a single row with the input followed by "Not Found" for all other fields
            6. Limit your response to maximum 3 most relevant defects
            7. Make sure each row uses consistent CSV formatting with commas separating all fields
            """
        )
        
        document_chain = create_stuff_documents_chain(llm, prompt)
        retrieval_chain = create_retrieval_chain(compression_retriever, document_chain)

        responses = retrieval_chain.invoke({'input': issue})
        cleaned_response = responses['answer'].replace('```csv', '').replace('```', '').strip()
        consolidated_responses.append(cleaned_response)  # Collect responses for all issues

    # Consolidate the responses into one CSV output and clean up any markdown formatting
    # consolidated_csv = "\n".join(consolidated_responses)
    # Consolidate the responses into one CSV output
    raw_consolidated_csv = "\n".join(consolidated_responses)
    
    # Clean and validate the CSV response using the validator module
    consolidated_csv = clean_and_validate_response(raw_consolidated_csv)
    
    # Log the cleaning results
    logger.info("CSV response cleaned and validated successfully")
    
    # Save the consolidated CSV to S3
    response = s3_client.put_object(
        Bucket=AWS_TEST_OUTPUT_BUCKET, Key=f"DefectPattern.csv", Body=consolidated_csv
    )

    status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    url = f"https://{AWS_TEST_OUTPUT_BUCKET}.s3.amazonaws.com/DefectPattern.csv"
    logger.info(url)

    if status == 200:
        return url
    else:
        logger.error("Failed to upload CSV to S3.")
        return None

# async def generating_defect(issues):
#     global vectorstore
#     if vectorstore is None:
#         raise ValueError("Vectorstore not initialized. Please run embeddings first.")

#     # Initialize the LLM (without FlashRank-specific configurations)
#     llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=GOOGLE_API_KEY, temperature=0)

#     # Use the vectorstore retriever directly
#     retriever = vectorstore.as_retriever()

#     # Consolidated responses
#     consolidated_responses = []

#     for issue in issues:  # Iterate through the array of issues
#         # Retrieve relevant documents using the retriever
#         retrieved_docs = retriever.invoke(issue)
#         print("Start\n")
#         print(retrieved_docs)
#         print("\nEnd")

#         # Prepare the prompt
#         prompt = ChatPromptTemplate.from_template(
#             """
#             Answer the questions based on the provided context only.
#             Please provide the most accurate response based on the question.
#             <context>
#             {context}
#             <context>
#             Question: Given the following context, find all issues that have the same meaning as this {input}.
#             Return the Issue Key, Summary, Project name, Assignee, Components, and input. 
#             Output the results in CSV format with the following columns: Input, Issue Key, Summary, Project name, Assignee, and Components.
#             If no similar defects are found, return the Input along with "Not Found" in all other fields.
#             """
#         )
        

#         # Create a chain for processing the prompt
#         document_chain = create_stuff_documents_chain(llm, prompt)

#         # Invoke the document chain with the input issue
#         responses = document_chain.invoke({'input': issue, 'context': retrieved_docs})
#         consolidated_responses.append(responses['answer'])  # Collect responses for all issues

#     # Consolidate the responses into one CSV output
#     consolidated_csv = "\n".join(consolidated_responses)

#     # Save the consolidated CSV to S3
#     response = s3_client.put_object(
#         Bucket=AWS_TEST_OUTPUT_BUCKET, Key=f"DefectPattern.csv", Body=consolidated_csv
#     )

#     status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
#     url = f"https://{AWS_TEST_OUTPUT_BUCKET}.s3.amazonaws.com/DefectPattern.csv"
#     print(url)

#     if status == 200:
#         return url
#     else:
#         return None



def handle_start_embedding_button_click(filepath):
    print("Start Embedding button clicked...")
    vector_embedding(filepath)

def handle_defect_detection_button_click(issue):
    print("Start Generating defect...")
    return asyncio.run(generating_defect(issue))
