import io
import os
from typing import List
import anthropic
import boto3
import re
import tiktoken
from flask import jsonify
from openai import OpenAI
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import pandas as pd
import openpyxl
import csv
from datetime import datetime

load_dotenv()

# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

AWS_ACCESS_KEY_ID = os.getenv("aws_access_key_id")
AWS_SECRET_ACCESS_KEY = os.getenv("aws_secret_access_key")
AWS_GUNIT_BUCKET = os.getenv("aws_gunit_bucket")
region_name = os.getenv("region_name")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=region_name

)

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


# print(os.getenv("openAI_model"))


# def generate_openai_response(prompt):
#     response = client.chat.completions.create(
#         model=os.getenv("openAI_model"),
#         messages=[{"role": "user", "content": prompt}],
#         temperature=0,
#         max_tokens=7000,
#         top_p=1,
#         frequency_penalty=0,
#         presence_penalty=0
#     )
#     return response.choices[0].message.content


def filter_builders_by_lob(df, lob,center):
    print("Column names in the DataFrame:")
    print(df.columns)
    df.columns = df.columns.str.strip()
    print("Column names in the DataFrame:")
    print(df.columns)
    # if 'Entity Name' not in df.columns:
    #     raise KeyError("'Entity Name' is not found in the DataFrame columns")
    # Filter the DataFrame where the selected LOB column has 'Y'
    filtered_df = df[(df[lob] == 'Y') & (df[center] == 'Y')]
    # Return the list of builder names
    return filtered_df['Entitiy Name'].tolist()

def calculate_tokens(text, encoding_name='claude-3-sonnet-20240229'):
    encoding = tiktoken.encoding_for_model(encoding_name)
    tokens = encoding.encode(text)
    return len(tokens)


def get_excel_from_s3(object_name):
    try:
        s3_client_data = s3_client.get_object(Bucket=AWS_GUNIT_BUCKET, Key=object_name)
        raw_data = s3_client_data['Body'].read()
        # print("Raw Data:", raw_data[:100])

        excel_data = pd.read_excel(io.BytesIO(raw_data), engine='openpyxl')

        # print("excel_data", excel_data)
        return excel_data
    except s3_client.exceptions.NoSuchKey:
        return None


def get_object_from_s3(object_name):
    try:
        s3_client_data = s3_client.get_object(Bucket=AWS_GUNIT_BUCKET, Key=object_name)
        return s3_client_data['Body'].read().decode('utf-8')
    except s3_client.exceptions.NoSuchKey:
        return None


def get_feature_data_from_s3(object_name, sheet_names):
    return_list = []
    for sheet_name in sheet_names:
        try:
            # Retrieve the object from S3
            s3_client_data = s3_client.get_object(Bucket=AWS_GUNIT_BUCKET, Key=object_name)
            raw_data = s3_client_data['Body'].read()

            # print("Raw Data:", raw_data[:100])  # Optional: Print a portion of the raw data for debugging

            # Read the Excel file, specifying the sheet name
            excel_data = pd.read_excel(io.BytesIO(raw_data), sheet_name=sheet_name, engine='openpyxl')
            return_list.append(excel_data)

        except s3_client.exceptions.NoSuchKey:
            # print(f"No such key: {object_name}")
            return None
        except ValueError as e:
            # print(f"Error reading sheet {sheet_name}: {e}")
            return None

    return return_list


def extract_code(response):
    if isinstance(response, str):
        code_start = response.find("```")
        code_end = response.rfind("```")
        if code_start != -1 and code_end != -1:
            return response[code_start + 3: code_end].strip()
        return response
    elif hasattr(response, 'text'):
        response_text = response.text
        code_start = response_text.find("```")
        code_end = response_text.rfind("```")
        if code_start != -1 and code_end != -1:
            return response_text[code_start + 3: code_end].strip()
        return response_text
    elif isinstance(response, list) or hasattr(response, '__iter__'):
        for item in response:
            if hasattr(item, 'text'):
                item_text = item.text
                code_start = item_text.find("```")
                code_end = item_text.rfind("```")
                if code_start != -1 and code_end != -1:
                    return item_text[code_start + 3: code_end].strip()
    else:
        raise ValueError("Invalid input type for extract_code function")


def extract_base_method_function(all_base_methods, base_method):
    try:
        pattern = rf'public\s+static\s+function\s+{re.escape(base_method)}\s*\([^\)]*\)\s*\{{.*?\}}'
        match = re.search(pattern, all_base_methods, re.DOTALL)

        if match:
            return match.group(0)
        else:
            return None
    except re.error as e:
        print(f"Regex error: {e}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def search_builder(folder_name, file_to_search):
    print("folder_name", folder_name)
    print("file to search", file_to_search)
    try:
        response = s3_client.list_objects_v2(Bucket=AWS_GUNIT_BUCKET, Prefix=folder_name)

        if 'Contents' in response:
            for obj in response['Contents']:
                # print("file to search", file_to_search)
                # print("Checking Key:", obj['Key'])
                # print("obejectKey:", obj['Key'])
                if obj['Key'] == (folder_name + file_to_search):
                    pre_signed_url = s3_client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': AWS_GUNIT_BUCKET, 'Key': obj['Key']},
                        ExpiresIn=3600
                    )
                    return {'file_found': True, 'pre_signed_url': pre_signed_url}

        return {'file_found': False}
    except Exception as e:
        return {'error': str(e)}


def extract_data_from_html(url):
    response = requests.get(url)
    if response.status_code == 200:
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')

        paragraphs = soup.find_all('p')
        field_map = {}

        for p in paragraphs:
            text = p.text.strip()
            match = re.match(r'(\w+)\s+([\w\.]+)', text)
            if match:
                field_name = match.group(1)
                field_type = match.group(2)
                field_map[field_name] = field_type
                print(f"Matched general field: {field_name} -> {field_type}")
            foriegn_key_match = re.search(r'(\w+)\s+foreign key to (\w+)', text)
            if foriegn_key_match:
                field_name = foriegn_key_match.group(1)
                field_type = f"{foriegn_key_match.group(2)}"
                field_map[field_name] = field_type

            type_key_match = re.search(r'(\w+)\s+type key to (\w+)', text)
            if type_key_match:
                field_name = type_key_match.group(1)
                field_type = f"typekey.{type_key_match.group(2)}"
                field_map[field_name] = field_type
                # Check for array key pattern
            array_key_match = re.search(r'(\w+)\s+array key for (\w+)', text)
            if array_key_match:
                field_name = array_key_match.group(1)
                field_type = f"ArrayList<{array_key_match.group(2)}>"
                field_map[field_name] = field_type

        return field_map
    else:
        print("Failed to fetch HTML content from the URL")
        return {}


def replace_column_types(column_type_map, excel_data):
    try:
        type_mapping = dict(zip(excel_data['Datatype Mapping'], excel_data['Unnamed: 1']))

        updated_column_type_map = {k: type_mapping.get(v, v) for k, v in column_type_map.items()}

        return updated_column_type_map
    except KeyError as e:
        print(f"Key error: {e}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None


# def generate_gunit_data(lob, builder, base_method_name, features):
#     folder_name = 'full/'
#     builder_name = f'{builder}.html'
#     result = search_builder(folder_name, builder_name)
#     pre_signed_url = result.get('pre_signed_url', '')
#     print("pre_signed_url:", pre_signed_url)
#
#     field_map = extract_data_from_html(pre_signed_url)
#     print("Field Map:", field_map)
#
#     all_base_methods = get_object_from_s3('baseMethods.txt')
#     contents = get_object_from_s3('entityTableDescriptions.txt')
#     data_builder_template = get_object_from_s3('DataBuilderFormat.txt')
#     gunit_format = get_object_from_s3('GunitFormat.txt')
#     data_generator_template = get_object_from_s3('DataGeneratorFormat.txt')
#     builder = builder.lower()
#     target_entity = 'cc_' + builder
#     pattern = rf'\b{re.escape(target_entity)}\.(\w+)\b'
#     columns = re.findall(pattern, contents)
#     print("Columns:", columns)
#
#     column_type_map = {col: field_map.get(col, 'unknown') for col in columns if
#                        field_map.get(col) != 'softentityreference'}
#     print("Column Type Map:", column_type_map)
#
#     data_type_mapping_template = get_excel_from_s3('DatatypeMapping.xlsx')
#     print("Excel Data:\n", data_type_mapping_template)
#     updated_column_type_map = replace_column_types(column_type_map, data_type_mapping_template)
#     print("Updated Column Type Map:", updated_column_type_map)
#     object_data = get_excel_from_s3('Test_Data_GENAI.xlsx')
#     base_method = extract_base_method_function(all_base_methods, base_method_name)
#     print("Base Methods:", base_method)
#     fields_to_exclude = "createtime, createuser, updatetime, updateuser, ID, publicID, retiredValue,policySystemAdd"
#
#     find_builder = get_object_from_s3(f'{builder}Builder.txt')
#
#     chunk_size = 25
#     data_builder_output = ""
#
#     if not find_builder:
#         column_chunks = [{k: updated_column_type_map[k] for k in list(updated_column_type_map)[i:i + chunk_size]}
#                          for i in range(0, len(updated_column_type_map), chunk_size)]
#         all_methods = []
#         for count, chunk in enumerate(column_chunks):
#             chunk_str = ', '.join([f'{col}: {typ}' for col, typ in chunk.items()])
#             if count == 0:
#                 data_builder_prompt = (
#                     f"{data_builder_template} Here is a basic structure of a builder class in Guidewire using Gosu. "
#                     f"Based on this, create a {builder} builder for the {lob} line of business with the objects {features}. "
#                     f"The {builder} entity has the following columns: {chunk_str}.exclude this fields if there {fields_to_exclude}. Generate only the "
#                     f"code, no extra text.Keep the name of the type of the columns exactly same as the type I am providing"
#                 )
#                 print("data builder prompt", data_builder_prompt)
#                 data_builder_response = generate_openai_response(data_builder_prompt)
#                 data_builder_output = extract_code(data_builder_response)
#             else:
#                 data_builder_prompt = (
#                     f"{data_builder_output} Here is a data builder. Generate only the methods for these columns {chunk_str}, "
#                     f"similar to the methods inside the provided data builder,don't add the code for the class and "
#                     f"also check if this fields are there"
#                     f"{fields_to_exclude} and don't add them in the code. Generate only the code, no extra text."
#                     f"Keep the name of the type of the columns exactly same as the type I am providing"
#                 )
#                 data_builder_response = generate_openai_response(data_builder_prompt)
#                 all_methods.extend(extract_code(data_builder_response).split('\n'))
#
#         data_builder_output += "\n".join(all_methods)
#         data_builder_output += "\n}"
#     else:
#         data_builder_output = find_builder
#
#     data_generator_prompt = (
#         f"{data_builder_output} call the methods inside the builder can you set the properties of a {builder} and  "
#         f"create a data generator for guidewire in gosu only generate the code no extra text.The basic structure of "
#         f"a data generator in guidewire is {data_generator_template} based on this structure create a data generator "
#         f"for {builder} and the data to add for each field should be taken from here {object_data} read the comments "
#         f"in the example i provided and make sure to follow them"
#     )
#     data_generator_response = generate_openai_response(data_generator_prompt)
#     data_generator_output = extract_code(data_generator_response)
#
#     gunit_generation_prompt = (
#         f"{gunit_format} here is what a gunit looks like guidewire in gosu.Now can you create a gunit for this base "
#         f"method{base_method_name} and call this data generator function {data_generator_output} to get test data for this "
#         f"gunit and write the methods being used inside the gunit class not in data generator in guidewire in gosu "
#         f"only generate the code no extra text. Please try to use the imports for the generated builder in this session"
#     )
#     gunit_generation_response = generate_openai_response(gunit_generation_prompt)
#     gunit_generation_output = extract_code(gunit_generation_response)
#     print("Data Builder:\n", data_builder_output)
#     print("Data Generator:\n", data_generator_output, "\n")
#     print("GUnit:\n", gunit_generation_output, "\n")
#     return data_builder_output, gunit_generation_output


client = anthropic.Anthropic(
    api_key=os.getenv('claude_apiKey'),
)


def add_data_to_excel(file_path, data):
    # Check if the file exists
    file_exists = os.path.isfile(file_path)
    with open(file_path, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)

        if not file_exists:
            writer.writerow(['Date Time', 'Builder', 'Model Used', 'Type', 'Input Tokens', 'Output Tokens'])

        writer.writerow(data)


def format_code(response):
    if isinstance(response, list):
        code_blocks = []
        for item in response:
            if isinstance(item, str):
                code_start = item.find("```")
                code_end = item.rfind("```")
                if code_start != -1 and code_end != -1:
                    code_blocks.append(extract_code(item))
            elif hasattr(item, 'text'):
                code_start = item.text.find("```")
                code_end = item.text.rfind("```")
                if code_start != -1 and code_end != -1:
                    code_blocks.append(extract_code(item.text))
                else:
                    code_blocks.append(item.text.strip())

        code_blocks = [block for block in code_blocks if block]
        return "\n\n".join(code_blocks) if code_blocks else None

    elif isinstance(response, str):
        code_start = response.find("```")
        code_end = response.rfind("```")
        if code_start != -1 and code_end != -1:
            return extract_code(response)
        else:
            return response.strip()

    else:
        raise ValueError("Invalid input type for format_code function")


def get_response_haiku(prompt):
    output = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return output.content


def get_response_sonnet(prompt):
    output = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=4000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    return output.content


def generate_gunit_data_claude(lob, builder, base_method_name, features,center):

    cc_folder_name = 'full/'
    pc_folder_name = 'PolicyCenter/'
    bc_folder_name = 'BillingCenter/'
    builder_name = f'{builder}.html'
    builder_name_ootd = f'{builder}Builder'
    builder = builder.lower()

    if center == 'ClaimCenter':
        result = search_builder(cc_folder_name, builder_name)
        contents = get_object_from_s3('cc_entityTableDescriptions.txt')
        target_entity = 'cc_' + builder
        gunit_format = get_object_from_s3('CC_GunitFormat.txt')

        

    elif center == 'PolicyCenter':
        result = search_builder(pc_folder_name, builder_name)
        contents = get_object_from_s3('pc_entityTableDescriptions.txt')
        target_entity = 'pc_' + builder
        gunit_format = get_object_from_s3('PC_GunitFormat.txt')
        print("gunit format !!!!!!!!!!!!!", gunit_format)
        
    elif center == 'BillingCenter':
        result = search_builder(bc_folder_name, builder_name)
        contents = get_object_from_s3('bc_entityTableDescriptions.txt')
        target_entity = 'bc_' + builder
        gunit_format = get_object_from_s3('BC_GunitFormat.txt')
    else:
        print("Invalid center")
    
    
    print("contents:", contents)
    print("target entity:", target_entity)
    pre_signed_url = result.get('pre_signed_url', '')
    print("pre_signed_url:", pre_signed_url)

    field_map = extract_data_from_html(pre_signed_url)
    print("Field Map:", field_map)

    all_base_methods = get_object_from_s3('baseMethods.txt') 
    data_builder_template = get_object_from_s3('DataBuilderFormat.txt')
    data_generator_template = get_object_from_s3('DataGeneratorFormat.txt')
    # builder = builder.lower()
    # target_entity = 'cc_' + builder
    pattern = rf'\b{re.escape(target_entity)}\.(\w+)\b'
    columns = re.findall(pattern, contents)
    print("Columns:", columns)
    ootb_builder_check = get_excel_from_s3('list_of_Builders.xlsx')

    is_present = builder_name_ootd in ootb_builder_check['List of ootb builder'].values
    print("TEDSTSTTTTTTTTT", is_present)

    print(ootb_builder_check)
    prompt_extension = ''

    if is_present:
        data_builder_template = get_object_from_s3('custom_Data_Builder.txt')
        print("Custom builder:", data_builder_template)
        pattern_ext = rf'\b{re.escape(target_entity)}\.(\w+_Ext)\b'
        columns = re.findall(pattern_ext, contents)
        print("Columns with target entity and ending with '_Ext':", columns)
        prompt_extension = 'do not add any extra createbean method for the object add only one method for it just like for the columns.'
    else:
        pattern = rf'\b{re.escape(target_entity)}\.(\w+)\b'
        columns = re.findall(pattern, contents)
        print("Columns:", columns)

    column_type_map = {col: field_map.get(col, 'unknown') for col in columns if
                       field_map.get(col) != 'softentityreference'}
    print("Column Type Map:", column_type_map)

    data_type_mapping_template = get_excel_from_s3('dataTypeMapping.xlsx')
    print("Excel Data:\n", data_type_mapping_template)
    updated_column_type_map = replace_column_types(column_type_map, data_type_mapping_template)
    print("Updated Column Type Map:", updated_column_type_map)
    # object_data = get_excel_from_s3(f'{builder}Data_{lob}.xlsx')
    # print("object_data", object_data.to_string())
    # object_data = object_data.to_string()
    feature_data=get_feature_data_from_s3('Features_data.xlsx',features)
    print('feature data',feature_data)
    base_method = extract_base_method_function(all_base_methods, base_method_name)
    print("Base Methods:", base_method_name)
    fields_to_exclude = "createtime, createuser, updatetime, updateuser, ID, publicID, retiredValue,policySystemAdd"

    find_builder = get_object_from_s3(f'{builder}Builder.txt')
    print("find builder:", find_builder)

    chunk_size = 25
    count2 = 0
    data_builder_output = ""
    combined_code = ""
    input_tokens_builder = 0
    output_tokens_builder = 0
    input_tokens_generator = 0
    output_tokens_generator = 0
    input_tokens_gunit = 0
    output_tokens_gunit = 0
    if find_builder is None:
        print("find builder is none")
        column_chunks = [{k: updated_column_type_map[k] for k in list(updated_column_type_map)[i:i + chunk_size]}
                         for i in range(0, len(updated_column_type_map), chunk_size)]
        data_builder_response = ""
        all_methods = []
        for count, chunk in enumerate(column_chunks):
            chunk_str = ', '.join([f'{col}: {typ}' for col, typ in chunk.items()])
            if count == 0:
                print("ENTERINGGGGGGGGGGG")
                data_builder_prompt = (
                                          f"{data_builder_template} Here is a basic structure of a data builder class in Guidewire using Gosu. "
                                          f"Based on this, create a {builder} builder for {lob} line of business with methods for objects {features} in the builder just like the methods for the columns use the 'addArrayElement' keyword to the objects everytime "
                                          f"The {builder} entity has the following columns: {chunk_str},generate only the methods for the fields in the chunk and objects if provided by me they should be similar to the methods of the columns I want you to create a data based "
                                          f"on the data I provided and also exclude these fields if they exist: {fields_to_exclude}. "
                                          f"Generate only the code for {builder}, no extra text. I only want the builder code just like the reference I "
                                          f"provided. Do not add how to use the builders inside the builder. Add all "
                                          f"the uses and imports from the reference I am providing to the builder you "
                                          f"generate everytime. Keep the data types of the fields exactly the same "
                                          f"and generate methods for all fields. Don't add the name of line of "
                                          f"buisness to the class name of the builder and maintain the methods by "
                                          f"which the data is being set inside the method in the same way as it is "
                                          f"in the reference provided by me"
                                      ) + prompt_extension
                print("data builder prompt:", data_builder_prompt)
                data_builder_response = get_response_sonnet(data_builder_prompt)
                data_builder_output = format_code(data_builder_response)
                # input_tokens_builder = client.count_tokens(data_builder_prompt)
                print("data builder response:", data_builder_response)
                data_builder_response_string = str(data_builder_response)
                # output_tokens_builder = client.count_tokens(data_builder_response_string)
                print("data builder output:", data_builder_output)

                count = count + 1
            else:
                count2 = 1
                data_builder_prompt = (
                    f"{data_builder_output} Here is a data builder. Generate only the methods and not the class for "
                    f"these columns {chunk_str}, similar to the methods inside the provided data builder. Exclude these fields if they exist: "
                    f"{fields_to_exclude}. Generate only the code, no extra text. Keep the data types of the fields exactly the same."
                )
                # input_tokens_builder += client.count_tokens(data_builder_prompt)
                print("input tokens for methods in builder", input_tokens_builder)
                data_builder_response = get_response_sonnet(data_builder_prompt)
                data_builder_response_string = str(data_builder_response)
                # output_tokens_builder += client.count_tokens(data_builder_response_string)
                print("output tokens for methods in builder", output_tokens_builder)
                print("response:", data_builder_response)

                # Extract the text from the TextBlock object
                response_text = data_builder_response[0].text if data_builder_response else ""

                new_methods = format_code(response_text)
                print("new methods:", new_methods)
                if new_methods:
                    all_methods.extend(new_methods.split('\n'))
        if count2 == 1:
            data_builder_output += "\n".join(all_methods)
            data_builder_output += "\n}"

    else:
        data_builder_output = find_builder
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model_used = "Sonnet"
    print("input and output tokens befor saving in the excel", input_tokens_builder, output_tokens_builder)
    data_to_save = [date_time, builder, "Builder", model_used, input_tokens_builder, output_tokens_builder]
    excel_file_path = "GUnit_Solution/temp/Token_Information.csv"
    add_data_to_excel(excel_file_path, data_to_save)
    object_data = get_excel_from_s3(f'{builder}Data_{lob}.xlsx')
    print("object_data", object_data.to_string())
    object_data = object_data.to_string()
    

    data_generator_prompt = (
        f"{data_builder_output} Call the methods inside the builder. Can you set the properties of a {builder} and  "
        f"create a data generator for Guidewire in Gosu? Only generate the code, no extra text. The basic structure of "
        f"a data generator in Guidewire is {data_generator_template}. Based on this structure, create a data generator "
        f"along with these features: {features} only and when adding the features add them normally just like other "
        f"columns not with arraylist and make surew to add the fields for that particular feature."
        f"For {builder}, the data to add for each field should be taken from here: {object_data}and the add the "
        f"features data to it too for this features {features} from here: {feature_data} strictly follow it make sure "
        f"to take the data of these {features} and add it to the generator. The object data"
        f"and the fields which don't have a value here should be set yourself following the trend of the data I provided."
        f"Set the fields according to the field name beside it and read the comments in the example I provided. Make "
        f"sure to follow them. Also, add data for all the fields which"
        f"have methods in the data builder, and for nested builders, do it accordingly. Remove the data which doesn't "
        f"have methods. When returning the value, use the .create() method only.ALso add uses for these feature :{features}like this 'uses gw.api.databuilder.featurename' at the top"
    )
    # input_tokens_generator = client.count_tokens(data_generator_prompt)
    print("data_generator_prompt", data_generator_prompt)
    data_generator_response = get_response_haiku(data_generator_prompt)
    data_generator_response_string = str(data_generator_response)
    # output_tokens_generator = client.count_tokens(data_generator_response_string)
    print("data generator:", data_generator_response)
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model_used = "Haiku"
    data_to_save = [date_time, builder, "Generator", model_used, input_tokens_generator, output_tokens_generator]
    excel_file_path = "GUnit_Solution/temp/Token_Information.csv"
    add_data_to_excel(excel_file_path, data_to_save)

    data_generator_output = format_code(data_generator_response)

    gunit_generation_prompt = (
        f"{gunit_format} Here is what a gunit looks like in Guidewire using Gosu. Now can you create a gunit for this base "
        f"method {base_method_name} and call this data generator function {data_generator_output} to get test data for this "
        f"gunit. Also, keep in mind it's just an example, and add the base method in the gunit and call it directly to test the method . Do "
        f"everything inside the same class as the gunit and extract the whole data generator function from the data "
        f"generator and put it in the gunit class. Use those methods to create the gunit."
        "Also, create the methods needed for the gunit and all the imports and uses required "
        f"according to the comments provided in the reference. Generate this in Gosu and only create "
        f"a single method.Don't add any annotations in the class"
    )
    print("gunit prompt:", gunit_generation_prompt)
    # input_tokens_gunit = client.count_tokens(gunit_generation_prompt)

    gunit_generation_response = get_response_sonnet(gunit_generation_prompt)
    gunit_generation_response_string = str(gunit_generation_response)
    print("gunit response:", gunit_generation_response)
    # output_tokens_gunit = client.count_tokens(gunit_generation_response_string)
    gunit_generation_output = format_code(gunit_generation_response)
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model_used = "Sonnet"  # Replace with the actual model used if different
    data_to_save = [date_time, builder, "Gunit", model_used, input_tokens_gunit, output_tokens_gunit]
    excel_file_path = "GUnit_Solution/temp/Token_Information.csv"
    add_data_to_excel(excel_file_path, data_to_save)

    print("Data Builder input tokens:\n", input_tokens_builder)
    print("Data Builder output token:\n", output_tokens_builder)
    print("Data Builder :\n", data_builder_output)
    print("Data Generator input tokens:\n", input_tokens_generator, "\n")
    print("Data Generator output tokens:\n", output_tokens_generator, "\n")
    print("Data Generator:\n", data_generator_output, "\n")
    print("GUnit input tokens:\n", input_tokens_gunit, "\n")
    print("GUnit output tokens:\n", output_tokens_gunit, "\n")
    print("GUnit:\n", gunit_generation_output, "\n")
    return data_builder_output, gunit_generation_output




def generate_gunit_data_claude_class(lob, builder, file_content, features, center):


    # folder_name = 'full/'
    # builder_name = f'{builder}.html' # builder name to be appended with centers
    # builder_name_ootd = f'{builder}Builder'
    # result = search_builder(folder_name, builder_name)
 
    cc_folder_name = 'full/'
    pc_folder_name = 'PolicyCenter/'
    bc_folder_name = 'BillingCenter/'
    builder_name = f'{builder}.html'
    builder_name_ootd = f'{builder}Builder'
    builder = builder.lower()

    if center == 'ClaimCenter':
        result = search_builder(cc_folder_name, builder_name)
        contents = get_object_from_s3('cc_entityTableDescriptions.txt')
        target_entity = 'cc_' + builder
        

    elif center == 'PolicyCenter':
        result = search_builder(pc_folder_name, builder_name)
        contents = get_object_from_s3('pc_entityTableDescriptions.txt')
        target_entity = 'pc_' + builder

        
    elif center == 'BillingCenter':
        result = search_builder(bc_folder_name, builder_name)
        contents = get_object_from_s3('bc_entityTableDescriptions.txt')
        target_entity = 'bc_' + builder
    else:
        print("Invalid center")
        
    pre_signed_url = result.get('pre_signed_url', '')
    print("pre_signed_url:", pre_signed_url)

    field_map = extract_data_from_html(pre_signed_url)


    all_base_methods = get_object_from_s3('baseMethods.txt')
    data_builder_template = get_object_from_s3('DataBuilderFormat.txt')
    gunit_format = get_object_from_s3('GunitFormat.txt')
    data_generator_template = get_object_from_s3('DataGeneratorFormat.txt')

    pattern = rf'\b{re.escape(target_entity)}\.(\w+)\b'
    print("pattern", pattern)
    columns = re.findall(pattern, contents)
    print("Columns:", columns)
    ootb_builder_check = get_excel_from_s3('list_of_Builders.xlsx')

    is_present = builder_name_ootd in ootb_builder_check['List of ootb builder'].values
    print(is_present)

    print(ootb_builder_check)
    prompt_extension = ""

    if is_present:
        data_builder_template = get_object_from_s3('custom_Data_Builder.txt')
        print("Custom builder:", data_builder_template)
        pattern_ext = rf'\b{re.escape(target_entity)}\.(\w+_Ext)\b'
        columns = re.findall(pattern_ext, contents)
        print("Columns with target entity and ending with '_Ext':", columns)
        prompt_extension = "all the imports and uses required provided in the reference and make extend the same class which it extends in the reference."
    else:
        pattern = rf'\b{re.escape(target_entity)}\.(\w+)\b'
        columns = re.findall(pattern, contents)
        print("Columns:", columns)

    column_type_map = {col: field_map.get(col, 'unknown') for col in columns if
                       field_map.get(col) != 'softentityreference'}
    print("Column Type Map:", column_type_map)

    data_type_mapping_template = get_excel_from_s3('dataTypeMapping.xlsx')
    print("Excel Data:\n", data_type_mapping_template)
    updated_column_type_map = replace_column_types(column_type_map, data_type_mapping_template)
    print("Updated Column Type Map:", updated_column_type_map)
    object_data = get_excel_from_s3(f'{builder}Data_{lob}.xlsx')
    feature_data = None
    if not features :
        feature_data=get_feature_data_from_s3('Features_data.xlsx',features)
        print('feature data',feature_data)
        if object_data is not None:
            print("object_data:", object_data.to_string())
        else:
            print("object_data is None")
    fields_to_exclude = "createtime, createuser, updatetime, updateuser, ID, publicID, retiredValue,policySystemAdd"

    find_builder = get_object_from_s3(f'{builder}Builder.txt')
    print("find builder:", find_builder)
    chunk_size = 25
    count2 = 0
    data_builder_output = ""
    combined_code = ""
    input_tokens_builder = 0
    output_tokens_builder = 0
    input_tokens_generator = 0
    output_tokens_generator = 0
    input_tokens_gunit = 0
    output_tokens_gunit = 0
    if find_builder is None:
        column_chunks = [{k: updated_column_type_map[k] for k in list(updated_column_type_map)[i:i + chunk_size]}
                         for i in range(0, len(updated_column_type_map), chunk_size)]
        data_builder_response = ""
        all_methods = []
        for count, chunk in enumerate(column_chunks):
            chunk_str = ', '.join([f'{col}: {typ}' for col, typ in chunk.items()])
            if count == 0:
                data_builder_prompt = (
                                          f"{data_builder_template} Here is a basic structure of a data builder class in Guidewire using Gosu. "
                                          f"Based on this, create a {builder} builder for {lob} line of business with methods for objects {features} in the builder just like the methods for the columns use the set keyword to add the data to the objects everytime "
                                          f"The {builder} entity has the following columns: {chunk_str},generate only the methods for the fields in the chunk and objects if provided by me they should be similar to the methods of the columns I want you to create a data based "
                                          f"on the data I provided and also exclude these fields if they exist: {fields_to_exclude}. "
                                          f"Generate only the code for {builder}, no extra text. I only want the builder code just like the reference I "
                                          f"provided. Do not add how to use the builders inside the builder. Add all the uses and imports from the reference I am providing to the builder you generate everytime. Keep the data types of the fields exactly the same and generate methods for all fields. "
                                      ) + prompt_extension
                print("data builder prompt:", data_builder_prompt)
                data_builder_response = get_response_sonnet(data_builder_prompt)
                data_builder_output = format_code(data_builder_response)
                # input_tokens_builder = client.count_tokens(data_builder_prompt)
                print("data builder response:", data_builder_response)
                data_builder_response_string = str(data_builder_response)
                # output_tokens_builder = client.count_tokens(data_builder_response_string)
                print("data builder output:", data_builder_output)

                count = count + 1
            else:
                count2 = 1
                data_builder_prompt = (
                    f"{data_builder_output} Here is a data builder. Generate only the methods and not the class for "
                    f"these columns {chunk_str}, similar to the methods inside the provided data builder. Exclude these fields if they exist: "
                    f"{fields_to_exclude}. Generate only the code, no extra text. Keep the data types of the fields exactly the same."
                )
                # input_tokens_builder += client.count_tokens(data_builder_prompt)
                print("input tokens for methods in builder", input_tokens_builder)
                data_builder_response = get_response_sonnet(data_builder_prompt)
                data_builder_response_string = str(data_builder_response)
                # output_tokens_builder += client.count_tokens(data_builder_response_string)
                print("output tokens for methods in builder", output_tokens_builder)
                print("response:", data_builder_response)

                # Extract the text from the TextBlock object
                response_text = data_builder_response[0].text if data_builder_response else ""

                new_methods = format_code(response_text)
                print("new methods:", new_methods)
                if new_methods:
                    all_methods.extend(new_methods.split('\n'))
        if count2 == 1:
            data_builder_output += "\n".join(all_methods)
            data_builder_output += "\n}"

    else:
        data_builder_output = find_builder
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model_used = "Sonnet"
    print("input and output tokens befor saving in the excel", input_tokens_builder, output_tokens_builder)
    data_to_save = [date_time, builder, "Builder", model_used, input_tokens_builder, output_tokens_builder]
    excel_file_path = "GUnit_Solution/temp/Token_Information.csv"
    add_data_to_excel(excel_file_path, data_to_save)

    data_generator_prompt = (
        f"Create a Guidewire data generator in Gosu for {builder} using this template: {data_generator_template}Include only these features: {features}Use this data for field values: {object_data}and {feature_data}Instruction 1. Only generate code, no explanations. 2. Include methods for all fields in the data builder, including nested builders.3. Use .create() method when returning the value.4. For fields without provided values, set appropriate values following the trend of given data.5. Exclude data without corresponding methods.. Start each feature's data when encountering 'NaN' as a field value.{data_builder_output} just use the methods from this data_builder and don't add the whole builder in it create the builder according to the instructions.Make sure you create a generator for {builder}"
    )
    # input_tokens_generator = client.count_tokens(data_generator_prompt)
    print("data_generator_prompt", data_generator_prompt)
    data_generator_response = get_response_sonnet(data_generator_prompt)
    data_generator_response_string = str(data_generator_response)
    # output_tokens_generator = client.count_tokens(data_generator_response_string)
    print("data generator:", data_generator_response)
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model_used = "Sonnet"
    data_to_save = [date_time, builder, "Generator", model_used, input_tokens_generator, output_tokens_generator]
    excel_file_path = "GUnit_Solution/temp/Token_Information.csv"
    add_data_to_excel(excel_file_path, data_to_save)

    data_generator_output = format_code(data_generator_response)

    gunit_generation_prompt = (
        f"{gunit_format} Here is what a gunit looks like in Guidewire using Gosu. Now can you create gunit methods "
        f"for all the base methods in this class : {file_content} and call this data generator function "
        f"{data_generator_output} to get test data for this gunit class. Also, keep in mind it's just an example . Do "
        f"everything inside the same class as the gunit and extract the whole data generator function from the data "
        f"generator and put it in the gunit class. Use those methods to create the gunit. Also, create the methods "
        f"needed for the gunit and all the imports and uses required according to the comments provided in the "
        f"reference. Generate this in Gosu ."
        f"a single method.add.ALso add uses for these feature :{features}like this 'uses gw.api.databuilder.featurename' at the top.Don't add any annotations in the class "
    )
    print("gunit prompt:", gunit_generation_prompt)
    # input_tokens_gunit = client.count_tokens(gunit_generation_prompt)
    gunit_generation_response = get_response_sonnet(gunit_generation_prompt)
    gunit_generation_response_string = str(gunit_generation_response)
    print("gunit response:", gunit_generation_response)
    # output_tokens_gunit = client.count_tokens(gunit_generation_response_string)
    gunit_generation_output = format_code(gunit_generation_response)
    date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model_used = "Sonnet"  # Replace with the actual model used if different
    data_to_save = [date_time, builder, "Gunit", model_used, input_tokens_gunit, output_tokens_gunit]
    excel_file_path = "GUnit_Solution/temp/Token_Information.csv"
    add_data_to_excel(excel_file_path, data_to_save)

    print("Data Builder input tokens:\n", input_tokens_builder)
    print("Data Builder output token:\n", output_tokens_builder)
    print("Data Builder :\n", data_builder_output)
    print("Data Generator input tokens:\n", input_tokens_generator, "\n")
    print("Data Generator output tokens:\n", output_tokens_generator, "\n")
    print("Data Generator:\n", data_generator_output, "\n")
    print("GUnit input tokens:\n", input_tokens_gunit, "\n")
    print("GUnit output tokens:\n", output_tokens_gunit, "\n")
    print("GUnit:\n", gunit_generation_output, "\n")
    print("TESTING FILE CONTENT",file_content)
    return data_builder_output, gunit_generation_output
    


