from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS

def build_vector_store(md_file):
    with open(md_file, "r") as f:
        markdown = f.read()
    
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3"),
    ]
    
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        return_each_line=False
    )
    chunks = splitter.split_text(markdown)
    
    embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
    db = FAISS.from_documents(chunks, embeddings)
    db.save_local("faiss_index")

if __name__ == "__main__":
    doc_path = "/Users/rewatiramansingh/Desktop/Projects/shl-assignment/shl-assignment/data/shl-docs.md"
    build_vector_store(doc_path)
    print("Vector DB created!")