from langchain.text_splitter import MarkdownHeaderTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.embeddings import HuggingFaceInferenceAPIEmbeddings


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


    embeddings = HuggingFaceInferenceAPIEmbeddings(
        api_key=st.secrets["HF_TOKEN"],
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    db = FAISS.from_documents(chunks, embeddings)
    db.save_local("faiss_index")

if __name__ == "__main__":
    doc_path = "/Users/rewatiramansingh/Desktop/Projects/shl-assignment/shl-assignment/data/shl-docs.md"
    build_vector_store(doc_path)
    print("Vector DB created!")

# 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
# AIzaSyCNuz86CuDzjIiesn5UDHz1wuxunQ_a04Q