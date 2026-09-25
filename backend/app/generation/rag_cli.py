"""CLI và công cụ debug cho pipeline RAG."""

from __future__ import annotations

import logging
import sys
from pprint import pprint

from .claim_generation import build_context, make_generation_prompt
from .gemini_client import generate_with_retry
from .rag_config import GRAPH_CONFIG
from .retrieval_node import get_retriever


def quiet_noisy_loggers() -> None:
    for name in (
        "huggingface_hub",
        "huggingface_hub.utils._http",
        "sentence_transformers",
        "transformers",
        "chromadb",
        "httpx",
        "httpcore",
        "urllib3",
        "google_genai",
        "google_genai.models",
        "google.genai",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)


def debug_question(question: str) -> None:
    from .rag_graph import answer_question

    print("=" * 100)
    print("QUESTION")
    print("=" * 100)
    print(question)

    results = get_retriever().retrieve(
        question,
        top_n=int(GRAPH_CONFIG["retrieve_top_n"]),
    )
    print("\n" + "=" * 100)
    print(f"RETRIEVED ({len(results)})")
    print("=" * 100)
    for index, result in enumerate(results, start=1):
        print(f"\n[{index}]")
        print("Provision :", result.get("provision_id"))
        print("Breadcrumb:", result.get("breadcrumb"))
        print("Score     :", result.get("rrf_score"))
        print("Retriever :", result.get("sources"))
        print("Text:")
        print(result.get("text"))
        print("-" * 80)

    context = build_context(results)
    prompt = make_generation_prompt(question, context)
    print("\n" + "=" * 100)
    print("CONTEXT")
    print("=" * 100)
    print(context)
    print("\nContext length:", len(context))
    print("\n" + "=" * 100)
    print("PROMPT")
    print("=" * 100)
    print(prompt)
    print("\nPrompt length:", len(prompt))
    print("\n" + "=" * 100)
    print("GEMINI")
    print("=" * 100)
    try:
        print("\nGemini answer:\n")
        print(generate_with_retry(prompt))
    except Exception as error:
        print("\nGemini ERROR:\n")
        print(error)
    print("\n" + "=" * 100)
    print("FULL PIPELINE")
    print("=" * 100)
    pprint(answer_question(question))


def main() -> None:
    from .rag_graph import answer_question

    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s:%(name)s:%(message)s",
    )
    quiet_noisy_loggers()
    args = sys.argv[1:]
    debug = "--debug" in args
    if debug:
        args.remove("--debug")
    question = " ".join(args).strip() or (
        "Tôi muốn đầu tư một cảng cạn mới, diện tích tối thiểu theo quy định "
        "là bao nhiêu và phải đáp ứng các tiêu chí xác định nào?"
    )
    if debug:
        debug_question(question)
        return

    result = answer_question(question)
    print("TRẠNG THÁI:", result.get("status"))
    print("TRẢ LỜI:\n", result["answer"])
    print("\nNGUỒN:")
    for source in result["sources"]:
        print(
            f"  - {source['provision_id']} — {source['breadcrumb']} "
            f"(score={source.get('rrf_score')}, "
            f"retriever={source.get('retriever_sources')})"
        )
    if result["warnings"]:
        print("\nCẢNH BÁO HẬU KIỂM:")
        for warning in result["warnings"]:
            print(f"  ! {warning}")
