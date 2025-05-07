#!/usr/bin/env python3

import os
import argparse
import sys

# The strings to look for on the line 1 of each file.
TARGET_START_STRING1 = "/* ************************************************************************** */"
TARGET_START_STRING2 = "/******************************************************************************/"
LINES_TO_REMOVE = 11
# File extensions to be searched & modded.
ALLOWED_EXTENSIONS = {".c", ".cpp", ".h", ".hpp", ".tpp"}

def process_file(filepath):
    try:
        # First, read only the first line to check the condition efficiently
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline()

        if first_line.strip() == TARGET_START_STRING1 or first_line.strip() == TARGET_START_STRING2:
            # If it matches, read all lines to modify
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Ensure we don't try to remove more lines than exist
            if len(lines) >= LINES_TO_REMOVE:
                content_to_keep = lines[LINES_TO_REMOVE:]
            else:
                # If the file has fewer than LINES_TO_REMOVE lines but matches,
                # it implies we should make it empty.
                content_to_keep = []

            if content_to_keep:               
            # If the header was removed, and the new first line (original line 12) is empty or only whitespace, remove it too.
                if not content_to_keep[0].strip():  # .strip() removes leading/trailing whitespace.
                    content_to_keep = content_to_keep[1:] # Remove that blank line

            # Write the modded content back to the file
            with open(filepath, 'w', encoding='utf-8', errors='ignore') as f:
                f.writelines(content_to_keep)
            return True
        else:
            return False

    except IOError as e:
        print(f"Error processing file {filepath}: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"An unexpected error occurred with file {filepath}: {e}", file=sys.stderr)
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Erase the first 11 lines from specified source files "
                    "if they start with a specific comment block (rid 42 the headers)."
    )
    parser.add_argument(
        "directory",
        help="The directory to scan for source files."
    )
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Error: Directory '{args.directory}' not found.", file=sys.stderr)
        sys.exit(1)

    modified_files_count = 0
    processed_files_count = 0
    print(f"Scanning dir: {os.path.abspath(args.directory)}\n")

    modified_files_list = []

    for root, _, files in os.walk(args.directory):
        for filename in files:
            _, ext = os.path.splitext(filename)
            if ext.lower() in ALLOWED_EXTENSIONS:
                filepath = os.path.join(root, filename)
                processed_files_count += 1
                print(f"Checking: {filepath}...", end="")
                if process_file(filepath):
                    print(" MODIFIED")
                    modified_files_list.append(filepath)
                    modified_files_count += 1
                else:
                    print(" unchanged.")

    print("\n=> RESULT <=")
    if modified_files_list:
        print(f"Modified {modified_files_count} out of {processed_files_count} scanned files:")
        for f_path in modified_files_list:
            print(f"  - {f_path}")
    else:
        print(f"No files modified out of {processed_files_count} scanned files.")

if __name__ == "__main__":
    main()
