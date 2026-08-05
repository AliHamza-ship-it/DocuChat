import json
import time
import requests

API_URL = "http://localhost:8000/api"

# 15 Benchmark Evaluation Questions (10 Answerable, 5 Out-of-Domain Refusal tests)
EVAL_DATASET = [
    {"id": 1, "type": "grounded", "question": "What is the primary revenue model of the company?"},
    {"id": 2, "type": "grounded", "question": "What are the key security compliance standards mentioned?"},
    {"id": 3, "type": "grounded", "question": "Who is listed as the primary executive contact for technical support?"},
    {"id": 4, "type": "grounded", "question": "What is the policy for employee remote work stipends?"},
    {"id": 5, "type": "grounded", "question": "How are customer data backups scheduled and preserved?"},
    {"id": 6, "type": "grounded", "question": "What is the maximum allowed duration for software trial licenses?"},
    {"id": 7, "type": "grounded", "question": "What termination clause notice period is required for standard vendor contracts?"},
    {"id": 8, "type": "grounded", "question": "What vector embedding model dimension size is supported by the architecture?"},
    {"id": 9, "type": "grounded", "question": "What is the response SLA for critical priority infrastructure tickets?"},
    {"id": 10, "type": "grounded", "question": "How are API rate limits enforced across enterprise user accounts?"},
    # Explicit Refusal Tests (Information NOT in document context)
    {"id": 11, "type": "refusal", "question": "What was the exact stock price of Apple on January 1, 2010?"},
    {"id": 12, "type": "refusal", "question": "Who won the FIFA World Cup in 1998?"},
    {"id": 13, "type": "refusal", "question": "How do you construct a warp drive according to general relativity?"},
    {"id": 14, "type": "refusal", "question": "What is the secret recipe for Coca-Cola?"},
    {"id": 15, "type": "refusal", "question": "What was the weather in Tokyo yesterday?"}
]

def run_evaluation(auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    results = []
    
    total_retrievals = 0
    grounded_count = 0
    refusal_count = 0
    total_latency = 0.0

    print("=" * 70)
    print("      DOCUCHAT RAG BENCHMARK EVALUATION (15-QUESTION SET)")
    print("=" * 70)

    for item in EVAL_DATASET:
        start_time = time.time()
        res = requests.post(
            f"{API_URL}/chat/query",
            json={"query": item["question"]},
            headers=headers
        )
        latency = round(time.time() - start_time, 3)
        total_latency += latency

        if res.status_code == 200:
            data = res.json()
            answer = data.get("answer", "")
            sources = data.get("sources", [])
            
            is_refusal = "cannot answer" in answer.lower() or "not present" in answer.lower()
            retrieved_chunks = len(sources)
            
            if item["type"] == "refusal" and is_refusal:
                refusal_score = 1.0 # Correct refusal
                refusal_count += 1
            elif item["type"] == "grounded" and not is_refusal and retrieved_chunks > 0:
                grounded_score = 1.0
                grounded_count += 1
            else:
                grounded_score = 0.0

            results.append({
                "id": item["id"],
                "type": item["type"],
                "question": item["question"],
                "latency_sec": latency,
                "sources_retrieved": retrieved_chunks,
                "is_refusal": is_refusal,
                "answer_preview": answer[:100] + "..."
            })

            print(f"[{item['id']}/15] {item['type'].upper()} | Latency: {latency}s | Sources: {retrieved_chunks} | Answer: {answer[:60]}...")
        else:
            print(f"[{item['id']}/15] FAILED | Status Code: {res.status_code}")

    # Generate Evaluation Report Summary
    avg_latency = round(total_latency / len(EVAL_DATASET), 3)
    groundedness_rate = round((grounded_count / 10) * 100, 1)
    refusal_accuracy = round((refusal_count / 5) * 100, 1)

    print("\n" + "=" * 70)
    print("                 FINAL EVALUATION BENCHMARK REPORT")
    print("=" * 70)
    print(f"Total Test Questions Run:      15")
    print(f"Grounded Answer Precision:    {groundedness_rate}% ({grounded_count}/10)")
    print(f"Explicit Refusal Accuracy:    {refusal_accuracy}% ({refusal_count}/5)")
    print(f"Average Pipeline Latency:     {avg_latency} seconds")
    print("=" * 70)

    # Save detailed JSON evaluation report
    report = {
        "summary": {
            "total_questions": 15,
            "groundedness_accuracy_pct": groundedness_rate,
            "refusal_accuracy_pct": refusal_accuracy,
            "average_latency_sec": avg_latency
        },
        "details": results
    }

    with open("backend/evaluation/evaluation_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Detailed report saved to: backend/evaluation/evaluation_report.json\n")

if __name__ == "__main__":
    print("To run evaluation, input an active user access_token:")
    token = input("JWT Token: ").strip()
    if token:
        run_evaluation(token)