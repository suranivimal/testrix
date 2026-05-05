from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from rag.data_loader import load_data

_db = None

def _get_db():
    global _db
    if _db is None:
        docs = load_data()
        embedding = HuggingFaceEmbeddings()
        _db = FAISS.from_texts(docs, embedding)
    return _db

def search_context(query):
    db = _get_db()
    results = db.similarity_search(query, k=2)
    return [r.page_content for r in results]