import ast, sys
sys.path.insert(0, r"c:\Users\chdnv\Desktop\ContractGuard")
from contractguard.auditors.drift import extract_env_vars_from_python

# Test the assignment case
code = 'os.environ["SET_VAR"] = "value"'
result = extract_env_vars_from_python(code)
print("Result:", result)

# Now test with a read
code2 = 'x = os.environ["READ_VAR"]'
result2 = extract_env_vars_from_python(code2)
print("Read result:", result2)
