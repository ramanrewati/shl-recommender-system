import os
import re
import requests
from google import genai 
import streamlit as st
from langchain.embeddings import HuggingFaceInferenceAPIEmbeddings
from langchain_google_genai import  ChatGoogleGenerativeAI
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

    /* Side service badges (vertical / sideways) */
    .service-badges {
        position: fixed;
        right: 6px;
        top: 120px;
        display: flex;
        gap: 10px;
        z-index: 9999;
        flex-direction: column;
        align-items: center;
        pointer-events: none; /* UI is purely informational, not interactive */
    }
    .service-badge {
        writing-mode: vertical-rl;
        transform: rotate(180deg);
        background: #444;
        color: #fff;
        padding: 8px 10px;
        border-radius: 8px;
        font-weight: 600;
        font-size: 12px;
        border: 2px solid rgba(255,255,255,0.06);
        pointer-events: auto;
    }
    .service-up { background: #1f7a1f; }       /* green */
    .service-down { background: #9b1f1f; }     /* red */
    .service-auth { background: #b06a1f; }     /* orange (auth issue) */

    /* small label under badges */
    .service-label {
        position: fixed;
        right: 6px;
        top: 220px;
        z-index: 9999;
        font-size: 11px;
        color: #cfcfcf;
        text-align: center;
        width: 72px;
    }
</style>
""", unsafe_allow_html=True)


# -----------------------
# Service check functions
# -----------------------
def check_huggingface(hf_token: str, timeout: float = 4.0):
    """
    Check HuggingFace Inference availability by querying the model metadata endpoint.
    Returns tuple (status_str, is_reachable_bool).
    status_str one of: "up", "down", "auth_error", "no_token"
    """
    if not hf_token:
        return ("no_token", False)

    url = "https://api-inference.huggingface.co/models/sentence-transformers/all-MiniLM-L6-v2"
    headers = {"Authorization": f"Bearer {hf_token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            return ("up", True)
        elif resp.status_code in (401, 403):
            # service reachable, but auth issue
            return ("auth_error", True)
        else:
            return ("down", False)
    except requests.RequestException:
        return ("down", False)


def check_gemini(gemini_api_key: str, timeout: float = 4.0):
    """
    Check Gemini (Google Generative API) availability by calling the models/list endpoint.
    Returns tuple (status_str, is_reachable_bool).
    status_str one of: "up", "down", "auth_error", "no_key"
    NOTE: this uses the public generative.googleapis.com endpoint and passes the API key as 'key' param.
    """
    if not gemini_api_key:
        return ("no_key", False)

    url = "https://generative.googleapis.com/v1/models"
    try:
        resp = requests.get(url, params={"key": gemini_api_key}, timeout=timeout)
        if resp.status_code == 200:
            return ("up", True)
        elif resp.status_code in (401, 403):
            return ("auth_error", True)
        else:
            return ("down", False)
    except requests.RequestException:
        return ("down", False)


# Run checks on load (will run each time the app reloads)
hf_token = None
gemini_key = None
try:
    hf_token = st.secrets.get("HF_TOKEN")
except Exception:
    hf_token = None

try:
    gemini_key = st.secrets.get("GEMINI_API_KEY")
except Exception:
    gemini_key = None

hf_status, hf_reachable = check_huggingface(hf_token)
gemini_status, gemini_reachable = check_gemini(gemini_key)


# Map status to CSS class + friendly text
def status_display_info(status_tuple):
    status, reachable = status_tuple
    if status == "up":
        return ("service-up", "UP")
    if status == "auth_error":
        return ("service-auth", "AUTH")
    if status in ("no_token", "no_key"):
        return ("service-auth", "MISSING")
    return ("service-down", "DOWN")


hf_class, hf_text = status_display_info((hf_status, hf_reachable))
gem_class, gem_text = status_display_info((gemini_status, gemini_reachable))


# Inject the side badges HTML
st.markdown(f"""
<div class="service-badges" aria-hidden="true">
    <div class="service-badge {hf_class}" title="HuggingFace Inference status">HF · {hf_text}</div>
    <div class="service-badge {gem_class}" title="Gemini / Google Generative status">GEM · {gem_text}</div>
</div>
<div class="service-label">Service Status</div>
""", unsafe_allow_html=True)


# Also show clear, accessible textual statuses in the sidebar (useful for screen readers / logs)
with st.sidebar:
    st.markdown("### API Health")
    # HuggingFace
    if hf_status == "up":
        st.success("HuggingFace Inference: reachable (200 OK)")
    elif hf_status == "auth_error":
        st.warning("HuggingFace Inference: reachable but auth failed (401/403). Check HF_TOKEN.")
    elif hf_status == "no_token":
        st.error("HuggingFace Inference: HF_TOKEN missing in st.secrets.")
    else:
        st.error("HuggingFace Inference: not reachable (network or service error).")

    # Gemini
    if gemini_status == "up":
        st.success("Gemini (Google Generative API): reachable (200 OK)")
    elif gemini_status == "auth_error":
        st.warning("Gemini (Google Generative API): reachable but auth failed (401/403). Check GEMINI_API_KEY.")
    elif gemini_status == "no_key":
        st.error("Gemini (Google Generative API): GEMINI_API_KEY missing in st.secrets.")
    else:
        st.error("Gemini (Google Generative API): not reachable (network or service error).")

    st.markdown("---")
    st.caption("Checks run on each page reload. Visual badges on the right show quick status.")


# -----------------------
# The rest of your code (unchanged apart from imports & checks above)
# -----------------------

# Initialize embeddings with the hf inference
embeddings = HuggingFaceInferenceAPIEmbeddings(
    api_key=st.secrets["HF_TOKEN"],
    model_name="sentence-transformers/all-MiniLM-L6-v2"
) 

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
        google_api_key=st.secrets["GEMINI_API_KEY"],
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

            docs = db.similarity_search(full_query, k=10)
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
