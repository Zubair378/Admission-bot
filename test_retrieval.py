from sentence_transformers import SentenceTransformer
import chromadb

THRESHOLD = 0.4  # below this, route to SPECIAL instead of answering

model = SentenceTransformer('all-MiniLM-L6-v2')
client = chromadb.PersistentClient(path="./chroma_db")
collection = client.get_or_create_collection(
    name="prospectus",
    metadata={"hnsw:space": "cosine"}
)

test_questions = [
    "What programs does Foundation University offer?",
    "What is the fee structure?",
    "What are the admission requirements?",
    "Is there a hostel available?",
    "What is the last date to apply?",
]

for question in test_questions:
    query_embedding = model.encode([question]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=3)

    top_chunk = results['documents'][0][0]
    top_distance = results['distances'][0][0]
    top_similarity = 1 - top_distance

    print(f"\nQ: {question}")
    print(f"Top similarity: {top_similarity:.2f}")

    if top_similarity >= THRESHOLD:
        print(f"DECISION: AUTO-REPLY")
        print(f"Context to use: {top_chunk[:200]}...")
    else:
        print(f"DECISION: SPECIAL — routed to human")
        print(f"(No confident match found — will not attempt an answer)")