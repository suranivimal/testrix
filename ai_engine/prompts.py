def test_case_prompt(feature, context=None):
    context_block = f"\n    Context:\n    {context}\n" if context else ""
    return f"""
    You are a QA expert.{context_block}
    Generate detailed test cases for: {feature}
    Include:
    - Positive cases
    - Negative cases
    - Edge cases
    """

def bug_analysis_prompt(bug, context=None):
    context_block = f"\n    Context:\n    {context}\n" if context else ""
    return f"""
    Analyze this bug and provide:{context_block}
    - Possible root cause
    - Severity
    - Fix suggestion

    Bug: {bug}
    """