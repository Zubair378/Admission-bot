import os
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import chromadb

def extract_text(pdf_path):
    reader = PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

pdf_files = ["data/Prospectus.pdf", "data/fee_structure.pdf"]
full_text = ""
for pdf in pdf_files:
    text = extract_text(pdf)
    print(f"{pdf}: {len(text)} characters extracted")
    full_text += text + "\n"
def chunk_text(text, max_chunk_size=600, overlap=100):
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    chunks = []
    for para in paragraphs:
        if len(para) <= max_chunk_size:
            chunks.append(para)
        else:
            # Paragraph itself is too long — force split it
            start = 0
            while start < len(para):
                end = start + max_chunk_size
                chunks.append(para[start:end])
                start += max_chunk_size - overlap

    return chunks
chunks = chunk_text(full_text)
print(f"Split into {len(chunks)} chunks.")

model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(chunks).tolist()

client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(
    name="prospectus",
    metadata={"hnsw:space": "cosine"}
)

collection.add(
    documents=chunks,
    embeddings=embeddings,
    ids=[f"chunk_{i}" for i in range(len(chunks))]
)

print(f"SUCCESS — {len(chunks)} chunks embedded and stored in Chroma.")