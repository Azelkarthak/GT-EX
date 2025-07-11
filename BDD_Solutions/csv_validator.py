import pandas as pd
import io
import logging

logger = logging.getLogger(__name__)

class CSVResponseValidator:
    """
    A module to validate and clean CSV responses from defect detection.
    Removes unnecessary 'Not Found' entries and ensures proper formatting.
    """
    
    @staticmethod
    def clean_csv_response(csv_content):
        """
        Clean and validate the CSV response content.
        
        Args:
            csv_content (str): Raw CSV content from the LLM response
            
        Returns:
            str: Cleaned CSV content with proper formatting
        """
        try:
            # Split the content into sections based on header repetitions
            sections = CSVResponseValidator._split_into_sections(csv_content)
            cleaned_sections = []
            
            for section in sections:
                cleaned_section = CSVResponseValidator._process_section(section)
                if cleaned_section:
                    cleaned_sections.append(cleaned_section)
            
            # Combine all cleaned sections
            if cleaned_sections:
                # Add header only once at the beginning
                header = "Input,Issue ID,Summary,Issue key,Status,Project name,Assignee,Components,Priority"
                all_rows = [header]
                
                for section in cleaned_sections:
                    # Skip header rows in individual sections
                    section_lines = section.strip().split('\n')
                    for line in section_lines:
                        if line.strip() and not line.startswith("Input,Defect ID"):
                            all_rows.append(line.strip())
                
                return '\n'.join(all_rows)
            else:
                return csv_content
                
        except Exception as e:
            logger.error(f"Error cleaning CSV response: {e}")
            return csv_content
    
    @staticmethod
    def _split_into_sections(csv_content):
        """
        Split CSV content into sections based on header repetitions.
        """
        lines = csv_content.strip().split('\n')
        sections = []
        current_section = []
        header_line = "Input,Issue ID,Summary,Issue key,Status,Project name,Assignee,Components,Priority"
        
        for line in lines:
            if line.strip() == header_line:
                if current_section:
                    sections.append('\n'.join(current_section))
                current_section = [line]
            else:
                current_section.append(line)
        
        if current_section:
            sections.append('\n'.join(current_section))
            
        return sections
    
    @staticmethod
    def _process_section(section_content):
        """
        Process individual section to remove unnecessary 'Not Found' entries.
        
        Args:
            section_content (str): Individual section content
            
        Returns:
            str: Cleaned section content
        """
        try:
            # Use StringIO to read the section as CSV
            csv_buffer = io.StringIO(section_content)
            df = pd.read_csv(csv_buffer)
            
            if df.empty:
                return None
            
            # Check if there are any valid defects (not "Not Found")
            valid_defects = df[df['Issue ID'] != 'Not Found']
            not_found_entries = df[df['Issue ID'] == 'Not Found']
            
            # If there are valid defects and "Not Found" entries, remove "Not Found"
            if not valid_defects.empty and not not_found_entries.empty:
                logger.info(f"Removing {len(not_found_entries)} 'Not Found' entries as valid defects exist")
                cleaned_df = valid_defects
            else:
                # Keep all entries if either all are valid or all are "Not Found"
                cleaned_df = df
            
            # Convert back to CSV format
            csv_output = io.StringIO()
            cleaned_df.to_csv(csv_output, index=False)
            return csv_output.getvalue().strip()
            
        except Exception as e:
            logger.error(f"Error processing section: {e}")
            return section_content
    
    @staticmethod
    def validate_csv_format(csv_content):
        """
        Validate that the CSV has the expected format and columns.
        
        Args:
            csv_content (str): CSV content to validate
            
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        expected_columns = [
            "Input", "Issue ID", "Summary", "Issue key", 
            "Status", "Project name", "Assignee", "Components", "Priority"
        ]
        
        try:
            csv_buffer = io.StringIO(csv_content)
            df = pd.read_csv(csv_buffer)
            
            # Check if all expected columns are present
            missing_columns = set(expected_columns) - set(df.columns)
            if missing_columns:
                return False, f"Missing columns: {missing_columns}"
            
            # Check if DataFrame is not empty
            if df.empty:
                return False, "CSV content is empty"
            
            return True, "CSV format is valid"
            
        except Exception as e:
            return False, f"Error validating CSV: {e}"
    
    @staticmethod
    def get_statistics(csv_content):
        """
        Get statistics about the cleaned CSV content.
        
        Args:
            csv_content (str): CSV content
            
        Returns:
            dict: Statistics about the content
        """
        try:
            csv_buffer = io.StringIO(csv_content)
            df = pd.read_csv(csv_buffer)
            
            total_entries = len(df)
            valid_defects = len(df[df['Issue ID'] != 'Not Found'])
            not_found_entries = len(df[df['Issue ID'] == 'Not Found'])
            unique_inputs = df['Input'].nunique()
            
            return {
                'total_entries': total_entries,
                'valid_defects': valid_defects,
                'not_found_entries': not_found_entries,
                'unique_inputs': unique_inputs
            }
            
        except Exception as e:
            logger.error(f"Error getting statistics: {e}")
            return {}

# Integration function to be used in your existing code
def clean_and_validate_response(raw_csv_response):
    """
    Main function to clean and validate the CSV response.
    
    Args:
        raw_csv_response (str): Raw CSV response from LLM
        
    Returns:
        str: Cleaned and validated CSV content
    """
    validator = CSVResponseValidator()
    
    # Clean the response
    cleaned_csv = validator.clean_csv_response(raw_csv_response)
    
    # Validate the format
    is_valid, message = validator.validate_csv_format(cleaned_csv)
    
    if is_valid:
        stats = validator.get_statistics(cleaned_csv)
        logger.info(f"CSV cleaned successfully. Stats: {stats}")
        logger.info(f"Validation: {message}")
    else:
        logger.warning(f"CSV validation failed: {message}")
    
    return cleaned_csv