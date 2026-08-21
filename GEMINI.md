# Rigorous Verification Protocol

1. **Never Self-Certify Prematurely**: Do not simply write a fix and declare it complete.
2. **Three-Pass Verification**: After completing a stage or implementing a fix, you MUST run programmatic tests (e.g., `py_compile`, API polling, unit tests, etc). You must wait 10 seconds and repeat this verification cycle a total of 3 times to ensure the system is truly stable and no regressions occurred.
3. **Root Cause Analysis**: If a bug occurs multiple times, do not just patch the symptom. Stop and trace the architecture to find and fix the absolute root cause.
4. **Final Verdict**: Only after the three-pass verification succeeds with zero errors may you present the final verdict to the user.
