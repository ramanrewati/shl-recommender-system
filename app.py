import os
import re
import tempfile
from google import genai 
import streamlit as st
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate
from langchain_community.vectorstores import FAISS
import scraping_utils


# Initialize Streamlit page config
st.set_page_config(
    page_title="SHL Assessment Recommender",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for dark theme and improved contrast
st.markdown("""
<style>
    .stApp {
        background-color: #121212;
        color: #e0e0e0;
        font-family: 'Inter', sans-serif;
    }
    .stMarkdown h1 {
        color: #bb86fc;
        font-weight: 700;
    }
    .stTextArea textarea {
        border: 2px solid #bb86fc;
        border-radius: 8px;
        padding: 12px;
        background-color: #1e1e1e;
        color: #e0e0e0;
    }
    .stButton button {
        background-color: #6d2abf;
        color: white;
        border-radius: 8px;
        padding: 10px 24px;
        font-weight: 500;
        transition: all 0.3s;
    }
    .stButton button:hover {
        background-color: #985eff;
        transform: translateY(-2px);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #2c2c2c;
        border-radius: 8px !important;
        padding: 10px 20px;
        transition: all 0.3s;
        color: #e0e0e0;
    }
    .stTabs [aria-selected="true"] {
        background-color: #bb86fc !important;
        color: white !important;
    }
    .stSpinner > div {
        color: #bb86fc !important;
    }
</style>
""", unsafe_allow_html=True)

# Remove the sidebar for document processing by not including its code.

# Initialize Google Gen AI client using google-genai SDK
client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

# Initialize the model
with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp:
    temp.write(st.secrets["GOOGLE_CREDENTIALS_JSON_CONTENT"])
    temp.flush()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = temp.name

# Initialize embeddings with the Google Generative AI model
embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")

def load_vector_store():
    """Load FAISS vector store with security checks"""
    if not os.path.exists("faiss_index"):
        st.error("Vector store not found. Please process documents first.")
        return None

    try:
        return FAISS.load_local(
            "faiss_index",
            embeddings,
            allow_dangerous_deserialization=True  # Only for trusted sources
        )
    except Exception as e:
        st.error(f"Error loading vector store: {str(e)}")
        return None

def get_conversational_chain():
    """Create QA chain with proper model configuration"""
    with open("system_prompt.md", "r") as f:
        SYSTEM_PROMPT = f.read()

    prompt_template = f"""
    {SYSTEM_PROMPT}

    Context:\n{{context}}\n
    Query:\n{{question}}\n

    Response:
    """

    # Updated model name to the new google-genai supported model
    model = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-001",
        temperature=0.2,
        top_k=20,
        top_p=0.95,
        verbose=True 
    )

    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"]
    )

    return load_qa_chain(
        model,
        chain_type="stuff",
        prompt=prompt,
        verbose=False
    )

def process_query(query):
    """Process user query with URL scraping and RAG"""
    # URL detection and scraping
    urls = re.findall(r'(https?://\S+)', query)
    scraped_data = ""

    if urls:
        with st.status("🌐 Scraping linked content...", expanded=True):
            for url in urls:
                scraped = scraping_utils.scrape_url(url)
                scraped_data += f"\n\nScraped content from {url}:\n{scraped}"

    full_query = query + scraped_data

    with st.spinner("🔍 Analyzing request with SHL knowledge base..."):
        try:
            db = load_vector_store()
            if db is None:
                return "Error: Knowledge base not loaded"

            docs = db.similarity_search(full_query, k=5)
            chain = get_conversational_chain()
            response = chain.invoke(
                {"input_documents": docs, "question": full_query},
                return_only_outputs=True
            )
            return response["output_text"]
        except Exception as e:
            st.error(f"Analysis error: {str(e)}")
            return None

def render_response(response):
    """Render AI response with beautiful markdown formatting"""
    if not response:
        return

    # Extract sections between XML-like tags
    sections = re.findall(r'<(\w+)>([\s\S]*?)</\1>', response)

    if not sections:
        st.markdown(response)
        return

    # Reorder sections: move "result" to be the first tab if present
    sections = sorted(sections, key=lambda x: 0 if x[0].lower() == "result" else 1)

    # Create tabs for each section
    tab_names = [sec[0].capitalize() for sec in sections]
    tabs = st.tabs(tab_names)

    for i, tab in enumerate(tabs):
        with tab:
            content = sections[i][1].strip()
            if sections[i][0].lower() == "result":
                st.markdown(content, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="
                    background: #1e1e1e;
                    padding: 16px;
                    border-radius: 8px;
                    border-left: 4px solid #bb86fc;
                    margin-bottom: 16px;
                    color: #e0e0e0;
                ">
                {content}
                </div>
                """, unsafe_allow_html=True)

# Main application UI
st.title("SHL Assessment Recommendation System")
st.markdown("""
    <div style="
        background: #2c2c2c;
        padding: 16px;
        border-radius: 8px;
        margin-bottom: 24px;
    ">
    <h3 style="color: #bb86fc; margin-top: 0;">AI-Powered Assessment Matching Engine</h3>
    <p>Describe your assessment needs and get personalized recommendations from SHL's product catalog.</p>
    </div>
""", unsafe_allow_html=True)

query = st.text_area(
    "Describe your assessment needs:",
    placeholder="e.g. 'I need cognitive ability tests under 45 minutes for remote hiring of financial analysts...'",
    height=150,
    key="query_input"
)

if st.button("Generate Recommendations", type="primary"):
    if not query:
        st.warning("Please enter your assessment requirements")
    else:
        response = process_query(query)
        if response:
            render_response(response)
