# your_app.py
import os
import re
import sys
import json
import logging
import traceback
from typing import Optional, List

# Third-party imports (make sure these packages are installed)
import streamlit as st
from google import genai
from langchain_community.embeddings import HuggingFaceInferenceAPIEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains.question_answering import load_qa_chain
from langchain.prompts import PromptTemplate
from langchain_community.vectorstores import FAISS

import scraping_utils  # your custom module

# -----------------------
# Logging configuration
# -----------------------
logger = logging.getLogger("shl_recommender")
logger.setLevel(logging.DEBUG)

# Console handler (terminal)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
console_handler.setFormatter(console_fmt)
logger.addHandler(console_handler)

# File handler
file_handler = logging.FileHandler("app_debug.log", mode="a")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(console_fmt)
logger.addHandler(file_handler)

# Small helper utilities
def _preview(text: Optional[str], n: int = 500) -> str:
    if text is None:
        return "<None>"
    t = str(text)
    return (t[:n] + "…") if len(t) > n else t

def _safe_json_preview(text: str):
    try:
        parsed = json.loads(text)
        return ("OK", parsed)
    except json.JSONDecodeError as e:
        logger.debug("JSON decode error preview: %s", traceback.format_exc())
        return (f"JSONDecodeError: {e}", _preview(text, 400))

def secret_present(key: str) -> bool:
    try:
        present = key in st.secrets and bool(st.secrets.get(key))
        logger.debug("Secret presence check - %s: %s", key, present)
        return present
    except Exception:
        logger.exception("Error checking secret presence for %s", key)
        return False

# -----------------------
# Streamlit page config & CSS
# -----------------------
st.set_page_config(
    page_title="SHL Assessment Recommender",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

# -----------------------
# Embeddings & Vectorstore loader (with logging)
# -----------------------
logger.info("Starting app — checking secret presence")
secret_present("HF_TOKEN")
secret_present("GEMINI_API_KEY")

try:
    embeddings = HuggingFaceInferenceAPIEmbeddings(
        api_key=st.secrets.get("HF_TOKEN", None),
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )
    logger.info("Embeddings instance created: %s", type(embeddings))
except Exception:
    logger.exception("Failed to create HuggingFace embeddings (stacktrace above).")
    embeddings = None

def load_vector_store():
    """Load FAISS vector store with security checks and verbose logging"""
    logger.debug("load_vector_store called. cwd=%s", os.getcwd())
    path = "faiss_index"
    logger.debug("Checking path existence: %s -> %s", path, os.path.exists(path))
    if not os.path.exists(path):
        logger.error("Vector store directory '%s' not found.", path)
        st.error("Vector store not found. Please process documents first.")
        return None

    try:
        db = FAISS.load_local(
            path,
            embeddings,
            allow_dangerous_deserialization=True  # Only for trusted sources
        )
        logger.info("FAISS vector store loaded successfully: %s", type(db))
        # attempt to introspect index size gracefully
        try:
            idx = getattr(db, "index", None)
            logger.debug("FAISS index introspection: %s", str(idx)[:1000])
        except Exception:
            logger.debug("FAISS introspection failed; continuing.")
        return db
    except Exception as e:
        logger.exception("Error loading vector store: %s", e)
        st.error(f"Error loading vector store: {str(e)}")
        return None

# -----------------------
# Conversational chain builder (with logging)
# -----------------------
def get_conversational_chain():
    """Create QA chain with proper model configuration and detailed logging"""
    try:
        with open("system_prompt.md", "r", encoding="utf-8") as f:
            SYSTEM_PROMPT = f.read()
        logger.debug("Loaded system_prompt.md (len=%d)", len(SYSTEM_PROMPT))
    except FileNotFoundError:
        SYSTEM_PROMPT = "You are an assistant specialized in SHL assessments."
        logger.warning("system_prompt.md not found — using fallback prompt.")

    prompt_template = f"""
    {SYSTEM_PROMPT}

    Context:\n{{context}}\n
    Query:\n{{question}}\n

    Response:
    """

    # instantiate model wrapper with verbose logging
    try:
        model = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-001",
            google_api_key=st.secrets.get("GEMINI_API_KEY", None),
            temperature=0.2,
            top_k=20,
            top_p=0.95,
            verbose=True
        )
        logger.info("ChatGoogleGenerativeAI instantiated: %s", getattr(model, "__class__", str(model)))
    except Exception:
        logger.exception("Error instantiating ChatGoogleGenerativeAI.")
        raise

    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"]
    )

    try:
        chain = load_qa_chain(
            model,
            chain_type="stuff",
            prompt=prompt,
            verbose=True
        )
        logger.info("QA chain loaded successfully: %s", type(chain))
        return chain
    except Exception:
        logger.exception("Failed to create QA chain.")
        raise

# -----------------------
# Safe scrape wrapper
# -----------------------
def safe_scrape_url(url: str):
    logger.debug("safe_scrape_url called for: %s", url)
    try:
        scraped = scraping_utils.scrape_url(url)
        if scraped is None:
            logger.warning("scrape_url returned None for %s", url)
            return ""
        logger.debug("Scraped len=%d for %s preview=%s", len(scraped), url, _preview(scraped, 300))
        return scraped
    except Exception:
        logger.exception("Exception while scraping %s", url)
        return f"<!-- SCRAPING ERROR for {url}: see logs -->"

# -----------------------
# Main processing function (fully instrumented)
# -----------------------
def process_query(query: str):
    """Process user query with URL scraping and RAG — instrumented for terminal logging"""
    logger.debug("process_query called with query (len=%d): %s", len(query), _preview(query, 300))

    # detect URLs
    urls = re.findall(r'(https?://\S+)', query)
    scraped_data = ""
    scraped_sources = []

    if urls:
        logger.info("Found %d url(s) in the query.", len(urls))
        # Use spinner in UI while scraping
        with st.spinner("🌐 Scraping linked content..."):
            for url in urls:
                try:
                    scraped = safe_scrape_url(url)
                    scraped_sources.append({"url": url, "len": len(scraped), "preview": _preview(scraped, 400)})
                    scraped_data += f"\n\nScraped content from {url}:\n{scraped}"
                except Exception:
                    logger.exception("Unhandled exception scraping %s", url)
                    scraped_sources.append({"url": url, "error": "exception during scraping"})
    else:
        logger.debug("No URLs detected in query.")

    # Show quick debug summary in UI
    st.write("Scrape summary:", scraped_sources)
    logger.debug("Scrape summary: %s", scraped_sources)

    full_query = query + "\n\n" + scraped_data

    with st.spinner("🔍 Analyzing request with SHL knowledge base..."):
        try:
            db = load_vector_store()
            if db is None:
                logger.error("Vector store not loaded; aborting process_query.")
                return "Error: Knowledge base not loaded"

            # similarity search
            try:
                docs = db.similarity_search(full_query, k=10)
                logger.info("similarity_search returned %d documents", len(docs))
            except Exception:
                logger.exception("Error during similarity_search")
                raise

            # preview first doc
            if docs:
                preview_text = getattr(docs[0], "page_content", str(docs[0]))
                st.write("First doc preview:", _preview(preview_text, 1000))
                logger.debug("First doc preview: %s", _preview(preview_text, 1000))

            # get chain and call it
            try:
                chain = get_conversational_chain()
            except Exception:
                logger.exception("get_conversational_chain failed")
                raise

            # ensure chain verbosity if possible
            try:
                if hasattr(chain, "verbose"):
                    chain.verbose = True
                    logger.debug("Set chain.verbose = True")
            except Exception:
                logger.debug("Unable to set chain verbose attribute.")

            # Invoke chain (wrapped)
            try:
                logger.debug("Invoking chain with docs and full_query (len=%d)", len(full_query))
                result = chain.invoke(
                    {"input_documents": docs, "question": full_query},
                    return_only_outputs=True
                )
                logger.debug("Chain invoke returned type=%s", type(result))
            except Exception:
                logger.exception("Exception during chain.invoke")
                raise

            # Inspect result shape
            if isinstance(result, dict):
                logger.debug("Chain result keys: %s", list(result.keys()))
                # common LangChain key check
                if "output_text" in result:
                    out = result["output_text"]
                    st.write("Response preview:", _preview(out, 2000))
                    logger.info("Returning output_text (len=%d)", len(out) if out else 0)
                    return out
                else:
                    # Unexpected dict shape — log full repr
                    logger.warning("Unexpected chain result shape. repr truncated: %s", _preview(repr(result), 2000))
                    st.error("Chain returned unexpected result shape. Check terminal logs for details.")
                    return repr(result)
            else:
                # Non-dict result — print / return repr
                logger.warning("Chain returned non-dict result: %s", type(result))
                st.write("Raw chain result (non-dict):", _preview(repr(result), 2000))
                return repr(result)

        except Exception as e:
            logger.exception("process_query top-level exception: %s", e)
            st.error("Analysis error: see terminal logs and app_debug.log for full traceback.")
            st.exception(e)  # show short trace in Streamlit UI
            return None

# -----------------------
# Render response helper
# -----------------------
def render_response(response: str):
    if not response:
        logger.debug("render_response called with empty response.")
        return

    logger.debug("render_response called; len=%d", len(response))
    # Extract sections between XML-like tags
    sections = re.findall(r'<(\w+)>([\s\S]*?)</\1>', response)

    if not sections:
        logger.debug("No XML-style sections found — rendering raw markdown.")
        st.markdown(response)
        return

    # Reorder sections to put result first
    sections = sorted(sections, key=lambda x: 0 if x[0].lower() == "result" else 1)
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

# -----------------------
# UI: Main application
# -----------------------
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

# A handy debug toggle in the UI to show more info in the sidebar
with st.sidebar.expander("Debug controls", expanded=True):
    show_logs = st.checkbox("Show log preview (last 200 lines of app_debug.log)", value=False)
    if show_logs:
        try:
            if os.path.exists("app_debug.log"):
                with open("app_debug.log", "r", encoding="utf-8") as fh:
                    lines = fh.read().splitlines()[-200:]
                    st.text("\n".join(lines))
            else:
                st.text("app_debug.log not yet created.")
        except Exception:
            st.exception("Error reading app_debug.log")

if st.button("Generate Recommendations", type="primary"):
    if not query:
        st.warning("Please enter your assessment requirements")
    else:
        logger.info("User requested recommendations; query len=%d", len(query))
        response = process_query(query)
        if response:
            render_response(response)
        else:
            logger.warning("No response received from process_query.")
            st.error("No response — check terminal logs and app_debug.log for details.")
