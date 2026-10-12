from agent import run_agent

tests = [
    "What matches are happening in the next 3 days?",
    "Show me Brazil's last 3 results",
    "What are the Group A standings?",
]

for query in tests:
    print(f"\n{'='*50}")
    print(f"Query: {query}")
    print(f"{'='*50}")
    result = run_agent(query)
    print(f"Answer: {result}")