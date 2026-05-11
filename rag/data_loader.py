import os

def load_data():
    base_path = os.path.join(os.getcwd(), "data")
    documents = []

    for filename in ["test_cases.txt", "bugs.txt"]:
        filepath = os.path.join(base_path, filename)
        if not os.path.exists(filepath):
            print(f"Warning: {filename} not found, skipping.")
            continue
        with open(filepath, "r") as f:
            for line in f:
                if line.strip():
                    documents.append(line.strip())

    return documents