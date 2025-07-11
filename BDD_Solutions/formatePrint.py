def print_formatted_documents(documents):
    print("Start\n")
    
    for i, doc in enumerate(documents):
        content = doc.page_content
        metadata = doc.metadata
        
        print(f"Document {i+1}")
        print("-" * 50)
        
        # Format the content nicely
        lines = content.split("\n")
        for line in lines:
            print(f"  {line}")
            
        print("\nMetadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")
            
        print("-" * 50)
        print()
    
    print("End")