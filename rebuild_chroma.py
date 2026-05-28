import os

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

from rag_pipeline import rebuild_collection_from_documents


PERSIST_DIRECTORY = os.getenv("PERSIST_DIRECTORY", "/app/chroma_db")
UPDATE_DB_DIRECTORY = os.getenv("UPDATE_DB_DIRECTORY", "/root/chroma_db_update")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "chosun_insight")
UPDATE_COLLECTION_NAME = os.getenv("UPDATE_COLLECTION_NAME", "chosun_daily_update")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
DATA_SAVE_DIR = os.getenv("DATA_SAVE_DIR", "/app/chosun_rag_data")
ORIGIN_DATA_DIR = os.getenv("ORIGIN_DATA_DIR", "")


def load_raw_documents(persist_directory: str, collection_name: str, embeddings) -> list[Document]:
    vectorstore = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )
    raw = vectorstore._collection.get(include=["documents", "metadatas"])
    documents = raw.get("documents", [])
    metadatas = raw.get("metadatas", [])

    return [
        Document(page_content=content, metadata=metadata or {})
        for content, metadata in zip(documents, metadatas)
        if content
    ]


def load_source_documents(data_directory: str) -> list[Document]:
    if not os.path.exists(data_directory):
        return []

    documents = []
    for filename in sorted(os.listdir(data_directory)):
        if not filename.endswith(".txt"):
            continue
        filepath = os.path.join(data_directory, filename)
        with open(filepath, "r", encoding="utf-8") as handle:
            documents.append(
                Document(
                    page_content=handle.read(),
                    metadata={"source": filename},
                )
            )
    return documents


def rebuild_target(
    name: str,
    persist_directory: str,
    collection_name: str,
    embeddings,
    preferred_source_dir: str = "",
) -> None:
    if not os.path.exists(persist_directory):
        print(f"[skip] {name}: {persist_directory} does not exist")
        return

    source_documents = []
    if preferred_source_dir:
        source_documents = load_source_documents(preferred_source_dir)

    if source_documents:
        raw_documents = source_documents
        print(f"[load] {name}: {len(raw_documents)} source files from {preferred_source_dir}")
    else:
        raw_documents = load_raw_documents(persist_directory, collection_name, embeddings)
        print(f"[load] {name}: {len(raw_documents)} raw docs from existing collection")

    rebuilt_count = rebuild_collection_from_documents(
        persist_directory=persist_directory,
        collection_name=collection_name,
        embedding_function=embeddings,
        raw_documents=raw_documents,
        profile_name=name,
    )
    print(f"[done] {name}: rebuilt {rebuilt_count} structured chunks")


if __name__ == "__main__":
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    rebuild_target(
        "origin",
        PERSIST_DIRECTORY,
        COLLECTION_NAME,
        embeddings,
        preferred_source_dir=ORIGIN_DATA_DIR,
    )
    rebuild_target(
        "update",
        UPDATE_DB_DIRECTORY,
        UPDATE_COLLECTION_NAME,
        embeddings,
        preferred_source_dir=DATA_SAVE_DIR,
    )
