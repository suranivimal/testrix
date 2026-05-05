from agents.bug_agent import analyze_bug
from services.test_case_service import generate_test_cases


def run_qa_ai(feature_or_bug: str):
    """
    Main orchestration layer
    Combines Bug Analysis + Test Case Generation
    """

    # 🐞 Step 1: Bug Analysis
    bug_result = analyze_bug(feature_or_bug)

    # 🧪 Step 2: Test Case Generation
    test_result = generate_test_cases(feature_or_bug)

    # 🧠 Step 3: Merge Output
    final_output = {
        "input": feature_or_bug,
        "bug_analysis": bug_result,
        "test_cases": test_result
    }

    return final_output