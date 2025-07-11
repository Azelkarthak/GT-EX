import csv

def clean_csv(input_file, output_file):
    cleaned_rows = []

    with open(input_file, 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        headers = next(reader)
        cleaned_rows.append(headers)

        for row in reader:
            cleaned_row = [value.replace(',', ' ').replace('.', '') for value in row]
            cleaned_rows.append(cleaned_row)

    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(cleaned_rows)

    print(f"Cleaned CSV written to '{output_file}'")

# Example usage
input_csv = 'PC_JIRA.csv'
output_csv = 'cleaned_PC_JIRA2.csv'
clean_csv(input_csv, output_csv)
