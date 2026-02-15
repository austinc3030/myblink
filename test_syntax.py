#!/usr/bin/env python3
import sys
import py_compile

try:
    py_compile.compile('app/web_server.py', doraise=True)
    print("✓ web_server.py syntax is valid")
except py_compile.PyCompileError as e:
    print(f"✗ Syntax error in web_server.py:")
    print(e)
    sys.exit(1)

try:
    # Try to import to check runtime issues
    sys.path.insert(0, 'app')
    import web_server
    print("✓ web_server.py imports successfully")
except Exception as e:
    print(f"✗ Import error in web_server.py:")
    print(e)
    sys.exit(1)

print("\nAll checks passed!")
