#!/usr/bin/env python3
import subprocess
import os

BOLD = "\033[1m"
WHITE = "\033[97m" # Bright White
GREY = "\033[90m"  # Bright Black (often appears as Grey)
ITALIC = "\033[3m"
RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"

# Path to the RPN executable
RPN_EXECUTABLE = "./RPN"

# Test cases: (title, argument_string)
test_cases = [
    ("Basic 1", "8 9 * 9 - 9 - 9 - 4 - 1 +"),
    ("Basic 2", "7 7 * 7 -"),
    ("Basic 3", "1 2 * 2 / 2 * 2 4 - +"),
    ("Error Case: Brackets", "(1 + 1)"),
    ("Division", "1 2 /"),
    ("Division by Zero", "5 0 /"),
    ("Too Many Operands Left", "1 2 3 +"),
    ("Operator First", "+ 1 2"),
    ("Empty String", ""),
    ("String with Only Spaces", "  "),
    ("Multi-digit Number (Invalid Token)", "12 3 +"),
    ("Single Number", "5"),
    ("Single Operator (Error)", "+"),
    ("Not Enough Operands for Operator", "1 +"),
    ("Complex Valid Expression", "9 5 * 2 + 3 / 7 - 4 *"),
    ("Expression with Negative Intermediate Result", "2 5 - 3 *"),
]

def rpn_to_infix(rpn_expression):
    tokens = rpn_expression.split()
    if not tokens:
        return ""
    stack = []
    operators = {'+', '-', '*', '/'}

    for token in tokens:
        if token in operators:
            if len(stack) < 2:
                return rpn_expression # Return original if conversion is problematic
            op2 = stack.pop()
            op1 = stack.pop()
            stack.append(f"({op1} {token} {op2})")
        else:
            stack.append(token)

    if len(stack) == 1:
        return stack[0]
    else:
        return rpn_expression # Return original if not a single valid expression

def run_test(title, argument):
    normal_expression = rpn_to_infix(argument)
    print(f"{BOLD}{WHITE}{title}{RESET}\n{ITALIC}{GREY}arg: {argument} => {normal_expression}{RESET}")
    try:
        # Ensure the executable exists and is executable
        if not (os.path.exists(RPN_EXECUTABLE) and os.access(RPN_EXECUTABLE, os.X_OK)):
            print(f"{RED}Error: {RPN_EXECUTABLE} not found or not executable.{RESET}")
            print("-" * 30)
            return

        # Construct the command
        command = [RPN_EXECUTABLE, argument]

        # Run the RPN programclear
        process = subprocess.run(command, capture_output=True, text=True, timeout=5)

        if process.returncode == 0:
            output = process.stdout.strip()
            print(f"{GREEN}{output}{RESET}")
        else:
            error_output = process.stderr.strip()
            print(f"{RED}{error_output}{RESET}")

    except subprocess.TimeoutExpired:
        print(f"{GREY}Error: Command timed out.{RESET}")
    except Exception as e:
        print(f"{RED}An unexpected error occurred while running the test: {e}{RESET}")
    finally:
        print("-" * 30) # Separator

if __name__ == "__main__":
    if not (os.path.exists(RPN_EXECUTABLE) and os.access(RPN_EXECUTABLE, os.X_OK)):
        print(f"{BOLD}{WHITE}Error: The RPN executable '{RPN_EXECUTABLE}' was not found or is not executable.{RESET}")
        print(f"{WHITE}Please compile the C++ program first (e.g., by running 'make').{RESET}")
    else:
        for title, arg_str in test_cases:
            run_test(title, arg_str)