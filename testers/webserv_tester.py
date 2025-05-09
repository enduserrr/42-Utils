#!/usr/bin/env python3

import subprocess
import os
import time
import sys
import shutil # For rmtree if needed, not currently used for dirs

# --- Configuration Macro (User Defined) ---
CONFIG_FILE_PATH = "config/multi.conf" # Default, can be overridden

# --- Globals for Parsed Config ---
# These will be populated by parse_config
parsed_server_configs = []
# Primary settings (usually from the first server block)
# These are defaults, will be overwritten by parser if config found
PORT1 = 8080
PORT2 = 8081 # Will be set if a second server block with a different port is found
HOST1 = "127.0.0.1"
HOST2 = "127.0.0.1"
SERVER_NAME1 = "localhost"
SERVER_NAME2 = "localhost"
SERVER_ROOT_MAIN = "www" # Main server root for file setup
UPLOAD_STORE_MAIN = "uploads" # Main upload store relative to SERVER_ROOT_MAIN
CGI_BIN_MAIN = "cgi-bin" # Main CGI bin relative to SERVER_ROOT_MAIN
REDIRECT_SRC_MAIN = "redirect" # Main redirect source path
INDEX_PAGE_MAIN = "index.html"

# File to be uploaded and then deleted
FILE_FOR_DELETE_TEST = "basic_post.txt"

# --- Colors ---
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"

# --- Globals for Test Results ---
tests_passed = 0
tests_failed = 0
output_log_file = None

# --- Helper Functions ---

def log_message(message, console_too=False):
    """Logs message to file and optionally to console."""
    if output_log_file:
        output_log_file.write(message + "\n")
        output_log_file.flush()
    if console_too: # For critical errors or summary
        print(message)
        sys.stdout.flush()

def print_status(test_name, success):
    """Logs the test status and updates counters."""
    global tests_passed, tests_failed
    status_msg = f"{GREEN}OK{RESET}" if success else f"{RED}KO{RESET}"
    log_message(f"{test_name:<60}: {status_msg}")
    if success:
        tests_passed += 1
    else:
        tests_failed += 1

def parse_config(config_path):
    """Parses the webserver configuration file."""
    global parsed_server_configs, PORT1, HOST1, SERVER_ROOT_MAIN, UPLOAD_STORE_MAIN, CGI_BIN_MAIN, REDIRECT_SRC_MAIN, SERVER_NAME1, INDEX_PAGE_MAIN, PORT2, HOST2, SERVER_NAME2
    
    servers = []
    try:
        with open(config_path, 'r') as f:
            lines = f.readlines()
    except FileNotFoundError:
        log_message(f"{RED}Error: Configuration file '{config_path}' not found. Exiting.{RESET}", True)
        sys.exit(1)
    except IOError as e:
        log_message(f"{RED}Error: Could not read configuration file '{config_path}': {e}. Exiting.{RESET}", True)
        sys.exit(1)

    current_server = None
    current_location = None
    context_stack = [] # To handle nested blocks (though not fully generic here)

    for line_num, raw_line in enumerate(lines):
        line = raw_line.strip()
        if line.startswith('#') or not line:
            continue

        if line.startswith("server {"):
            if current_server: # Should not happen if blocks are balanced
                log_message(f"{RED}Config Parse Error: Unexpected 'server {{' at line {line_num+1}.{RESET}", True)
                return False
            current_server = {"locations": [], "line": line_num + 1}
            context_stack.append(current_server)
            continue
        elif line.startswith("location ") and "{" in line:
            if not current_server:
                log_message(f"{RED}Config Parse Error: 'location' block outside 'server' block at line {line_num+1}.{RESET}", True)
                return False
            path = line.split("location")[1].split("{")[0].strip()
            current_location = {"path": path, "line": line_num + 1}
            context_stack.append(current_location)
            continue
        elif line == "}":
            if not context_stack:
                log_message(f"{RED}Config Parse Error: Unexpected '}}' at line {line_num+1}.{RESET}", True)
                return False
            
            closed_block = context_stack.pop()
            if closed_block == current_location: # Closed a location block
                if current_server: # Should always be true here
                     current_server.setdefault("locations", []).append(current_location)
                current_location = None
                # Check if parent was a server
                if context_stack and "listen" in context_stack[-1]: # Heuristic for server block
                    pass # Still inside server
                else: # Should not happen if location is always in server
                    log_message(f"{RED}Config Parse Error: Location block not properly nested in server at line {line_num+1}.{RESET}", True)
                    return False

            elif closed_block == current_server: # Closed a server block
                servers.append(current_server)
                current_server = None
            else: # Mismatched block
                log_message(f"{RED}Config Parse Error: Mismatched '}}' at line {line_num+1}.{RESET}", True)
                return False
            continue

        # Inside a block, parse directives
        parts = line.rstrip(';').split()
        if not parts:
            continue
        directive = parts[0]
        values = parts[1:]

        if not context_stack: # Directive outside any block
            log_message(f"{RED}Config Parse Error: Directive '{directive}' outside any block at line {line_num+1}.{RESET}", True)
            return False
        
        target_block = context_stack[-1] # Current block is top of stack

        if directive == "listen":
            try:
                target_block["listen"] = int(values[0])
            except (ValueError, IndexError):
                log_message(f"{RED}Config Parse Error: Invalid 'listen' value at line {line_num+1}.{RESET}", True)
                return False
        elif directive == "host":
            target_block["host"] = values[0] if values else "0.0.0.0"
        elif directive == "server_name":
            target_block["server_names"] = values
        elif directive == "root":
            target_block["root"] = values[0] if values else None
        elif directive == "index":
            target_block["index"] = values
        elif directive == "autoindex":
            target_block["autoindex"] = (values[0].lower() == "on") if values else False
        elif directive == "client_max_body_size":
            target_block["client_max_body_size"] = values[0] if values else "1m"
        elif directive == "error_page":
            try:
                if "error_pages" not in target_block: target_block["error_pages"] = {}
                target_block["error_pages"][int(values[0])] = values[1]
            except (ValueError, IndexError, TypeError):
                log_message(f"{RED}Config Parse Error: Invalid 'error_page' directive at line {line_num+1}.{RESET}", True)
                return False
        elif directive == "upload_store":
            target_block["upload_store"] = values[0] if values else None
        elif directive == "allow_methods":
            target_block["allow_methods"] = [m.upper() for m in values]
        elif directive == "return":
            try:
                target_block["return"] = {"code": int(values[0]), "url": values[1]}
            except (ValueError, IndexError, TypeError):
                log_message(f"{RED}Config Parse Error: Invalid 'return' directive at line {line_num+1}.{RESET}", True)
                return False
        # Add more directives as needed

    if context_stack: # Unclosed blocks
        log_message(f"{RED}Config Parse Error: Unclosed block(s) at end of file, starting line {context_stack[0].get('line', 'N/A')}.{RESET}", True)
        return False

    parsed_server_configs = servers
    log_message(f"Successfully parsed {len(parsed_server_configs)} server block(s).")

    # Populate global convenience vars from the first server block (if any)
    if parsed_server_configs:
        s0 = parsed_server_configs[0]
        PORT1 = s0.get("listen", 8080)
        HOST1 = s0.get("host", "127.0.0.1")
        SERVER_ROOT_MAIN = s0.get("root", "www")
        SERVER_NAME1 = s0.get("server_names", ["localhost"])[0]
        INDEX_PAGE_MAIN = s0.get("index", ["index.html"])[0]

        # Find upload_store: check server, then first matching location '/' or '/uploads'
        UPLOAD_STORE_MAIN = s0.get("upload_store", "uploads") # Default
        # Try to find a more specific upload_store
        for loc in s0.get("locations", []):
            if loc.get("path") == "/" and "upload_store" in loc:
                UPLOAD_STORE_MAIN = loc["upload_store"]
                break # Prefer root location if specified
        for loc in s0.get("locations", []):
            if loc.get("path") == "/uploads" and "upload_store" in loc:
                UPLOAD_STORE_MAIN = loc["upload_store"]
                break # Then /uploads location

        # Find redirect_src: check locations for a 'return' directive
        for loc in s0.get("locations", []):
            if "return" in loc:
                REDIRECT_SRC_MAIN = loc["path"].lstrip('/') # Use the location path as the source
                break
        
        # CGI_BIN_MAIN remains default 'cgi-bin' relative to SERVER_ROOT_MAIN for now
        # Could be made configurable if a cgi location is defined

        if len(parsed_server_configs) > 1:
            s1 = parsed_server_configs[1]
            PORT2 = s1.get("listen", 8081)
            HOST2 = s1.get("host", "127.0.0.1")
            SERVER_NAME2 = s1.get("server_names", ["localhost"])[0]
        log_message(f"Primary config: Port={PORT1}, Host={HOST1}, Root={SERVER_ROOT_MAIN}, Uploads={UPLOAD_STORE_MAIN}")

    return True


def run_curl_exact(test_name, args, timeout=15, expect_http_error=False):
    cmd_display_list = ["curl"] + args
    cmd_str_display = ' '.join(cmd_display_list)
    log_message(f"  {YELLOW}Running: {cmd_str_display}{RESET}")
    log_message(f"  {CYAN}--- curl output start ---{RESET}")
    
    success = False
    curl_output_lines = []
    try:
        process = subprocess.Popen(["curl"] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=timeout)
        
        if stdout:
            log_message("  Stdout:")
            for line in stdout.splitlines():
                log_message(f"    {line}")
                curl_output_lines.append(line)
        if stderr:
            log_message("  Stderr:")
            for line in stderr.splitlines():
                log_message(f"    {line}")
                curl_output_lines.append(line) # Also log stderr for context

        returncode = process.returncode
        log_message(f"  {CYAN}--- curl output end ---{RESET}")
        log_message(f"  {CYAN}curl exit code: {returncode}{RESET}")

        if returncode == 0:
            success = True
        elif returncode == 22 and expect_http_error:
            log_message(f"  {YELLOW}Note: curl exit code 22 treated as OK (HTTP error expected).{RESET}")
            success = True
        else:
            if returncode == 6: log_message(f"  {RED}Curl Error: Could not resolve host.{RESET}")
            elif returncode == 7: log_message(f"  {RED}Curl Error: Connection refused.{RESET}")
            elif returncode == 28: log_message(f"  {RED}Curl Error: Operation Timeout.{RESET}")
            else: log_message(f"  {RED}Curl Error: Exit code {returncode}.{RESET}")
            success = False
    except subprocess.TimeoutExpired:
        log_message(f"  {CYAN}--- curl output end (timeout) ---{RESET}")
        log_message(f"  {RED}Command timed out after {timeout} seconds.{RESET}")
        success = False
    except FileNotFoundError:
        log_message(f"{RED}Error: 'curl' command not found.{RESET}")
        success = False
    except Exception as e:
        log_message(f"  {CYAN}--- curl output end (exception) ---{RESET}")
        log_message(f"  {RED}An unexpected error occurred: {e}{RESET}")
        success = False

    print_status(test_name, success)
    log_message("-" * 30)
    time.sleep(0.2) # Shorter delay
    return success


def run_siege(test_name, args, timeout=40):
    cmd = ["siege"] + args
    log_message(f"  {YELLOW}Running: {' '.join(cmd)}{RESET}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        log_message("  Siege Stdout:")
        for line in result.stdout.strip().splitlines(): log_message(f"    {line}")
        if result.stderr.strip():
            log_message("  Siege Stderr:")
            for line in result.stderr.strip().splitlines(): log_message(f"    {line}")
        
        success = False
        if result.returncode == 0:
            if "Connection refused" in result.stderr or "Connection refused" in result.stdout:
                 log_message(f"  {RED}Siege reported 'Connection refused'.{RESET}")
            elif "Transactions:\t\t\t       0 hits" in result.stdout:
                 log_message(f"  {YELLOW}Warning: Siege reported 0 successful transactions.{RESET}")
            else:
                success = True
        else:
            log_message(f"  {RED}Siege failed with exit code {result.returncode}{RESET}")
        
        print_status(test_name, success)
    except subprocess.TimeoutExpired:
        log_message(f"  {RED}Siege command timed out.{RESET}")
        print_status(test_name, False)
    except FileNotFoundError:
        log_message(f"{RED}Error: 'siege' command not found.{RESET}")
        print_status(test_name, False)
    except Exception as e:
        log_message(f"  {RED}An unexpected error occurred during siege: {e}{RESET}")
        print_status(test_name, False)
    log_message("-" * 30)


def get_full_path(base_path, relative_path):
    """ Safely join base path and relative path, handling leading slashes. """
    if not relative_path: return base_path
    return os.path.join(base_path, relative_path.lstrip('/'))

def check_file_exists(path, try `ls -ld /www` and `ls /www`. If these fail with permission errors, that's the problem):
    """Checks if a file exists."""
    return os.path.isfile(path)

def check.
*   **Relative Path Interpretation:** If `SERVER_ROOT_MAIN` is set to just `"www"` (_file_deleted(path):
    """Checks if a file does not exist."""
    return not os.path.exists(path) # os.path.exists is fine for checking non-existence

def setup_test_files():
    log_message(f"{Strategy Change for `setup_test_files`:**

*   The script will create a *local temporary www directoryBOLD}Setting up test environment. Expecting server root at: {SERVER_ROOT_MAIN}{RESET}")

    # 1. Verify SERVER_ROOT_MAIN exists, is a directory, and is accessible by the script
    if not os.path.exists(SERVER_ROOT_MAIN):
        log_message(f"{RED}Error: Server root path '{SERVER_ROOT* (e.g., `./test_www_area`) where it places files like `index.html`, `empty_MAIN}' does not exist. "
                    f"This path must exist as per server configuration. Exiting.{RESET}",.html`.
*   The server configuration (`multi.conf`) must then be set up to point its `root` directive True)
        sys.exit(1)

    if not os.access(SERVER_ROOT_MAIN, os.R_OK | os.X_OK): # Check for read and execute (list) permissions
        log_message(f to *this temporary directory* for the duration of the test, OR the script must be intelligent enough to place files where"{RED}Error: No read/execute permission on server root path '{SERVER_ROOT_MAIN}' for the script user the *existing server root* expects them, assuming it has write permissions there (which is the original problem).

Given. "
                    f"Cannot verify if it's a directory or access its contents. Exiting.{RESET}", True)
 the constraint that the server is *already running* with a fixed config, the script cannot change the server's root on        sys.exit(1)

    if not os.path.isdir(SERVER_ROOT_MAIN):
 the fly. Therefore, the script *must* assume that the `root` specified in the config (e.g.,        log_message(f"{RED}Error: Server root path '{SERVER_ROOT_MAIN}' is not a `/www`) is where the server looks, and the script *must* have a way to place files there or verify directory. "
                    f"This path must be a directory as per server configuration. Exiting.{RESET}", True)
        sys.exit(1)

    # Check for write permission *inside* SERVER_ROOT_MAIN for test files their existence.

**If the script cannot write to the server's actual `root /www;`:**

The current like index.html
    # This is a slightly different check than os.access(SERVER_ROOT_MAIN, os.W approach of the script creating `index.html` directly in `SERVER_ROOT_MAIN` will fail if `SERVER__OK) which checks if the dir itself is modifiable.
    # We need to be able to create filesROOT_MAIN` is `/www` and the script runner doesn't have permission.

**Let's refine *within* it.
    # A simple way is to try creating a temporary file.
    temp_test `setup_test_files` with more careful checks and clearer logging:**

```python
def setup_test_files():
    log_message(f"{BOLD}Setting up test environment. Configured server root: {SERVER_ROOT__file = os.path.join(SERVER_ROOT_MAIN, ".test_write_permission.tmp")
    try:
        with open(temp_test_file, "w") as f_tmp:
            f_tmp.writeMAIN}{RESET}")

    # --- Verification of SERVER_ROOT_MAIN (e.g., /www) ---
    #("test")
        os.remove(temp_test_file)
    except IOError as e:
         This is the root directory the *webserver* is configured to use.
    # The script needs to know if itlog_message(f"{RED}Error: No write permission *inside* server root directory '{SERVER_ROOT_MAIN}'. "
                    f"Cannot create test files like '{INDEX_PAGE_MAIN}'. Error: {e}. Exiting.{RESET can place/check files here.
    server_root_exists = os.path.isdir(SERVER_ROOT_MAIN}", True)
        sys.exit(1)


    # Construct full paths for upload and cgi directories based)
    script_can_write_to_server_root = os.access(SERVER_ROOT_MAIN on parsed config
    main_upload_full_path = get_full_path(SERVER_ROOT_MAIN, os.W_OK)

    if not server_root_exists:
        log_message(f, UPLOAD_STORE_MAIN)
    main_cgi_full_path = get_full_path("{RED}Error: Configured server root '{SERVER_ROOT_MAIN}' not found or is not a directory. "
                    f"The webserver expects this path. Exiting.{RESET}", True)
        sys.exit(1)SERVER_ROOT_MAIN, CGI_BIN_MAIN)

    # 2. Verify/Create main_upload_full_path and check writability
    if not os.path.isdir(main_upload_full_path):

    
    log_message(f"  Server root '{SERVER_ROOT_MAIN}' exists.")
    if not script        log_message(f"{YELLOW}Warning: Upload store directory '{main_upload_full_path}' not_can_write_to_server_root:
        log_message(f"{YELLOW}Warning: Script found. Attempting to create it.{RESET}")
        try:
            os.makedirs(main_upload_ does not have direct write permission to server root '{SERVER_ROOT_MAIN}'. "
                    f"Will attempt to place filesfull_path, exist_ok=True)
            log_message(f"  Successfully created '{main_upload_full_path}'.")
        except OSError as e:
            log_message(f"{RED}Error: in subdirectories like uploads if they are writable.{RESET}")
        # If we can't write to the root Could not create upload store directory '{main_upload_full_path}': {e}. "
                        f"Ensure the parent, creating index.html directly there will fail.
        # The tests for index.html and empty.html will directory '{os.path.dirname(main_upload_full_path)}' is writable or the directory exists. Exiting rely on them *already existing*
        # in the server's root, placed there by some other means (e.{RESET}", True)
            sys.exit(1)
            
    # Check write permission for the upload directory specifically.g., server setup).
    else:
        log_message(f"  Script has write permission to
    temp_upload_test_file = os.path.join(main_upload_full_path, ". server root '{SERVER_ROOT_MAIN}'.")


    # --- Upload and CGI Directories ---
    # These pathstest_write_permission_upload.tmp")
    try:
        with open(temp_upload_test_file, "w") as f_tmp:
            f_tmp.write("test")
        os.remove are typically relative to SERVER_ROOT_MAIN in the config.
    # The script needs to ensure these subdirectories exist and are(temp_upload_test_file)
    except IOError as e:
        log_message(f"{RED}Error: No write permission *inside* upload store directory '{main_upload_full_path}'. "
 writable *by the server process*
    # for uploads, and exist for CGI scripts. The script itself might need                    f"Cannot create uploaded test files. Error: {e}. Exiting.{RESET}", True)
        sys.exit(1)


    # 3. Verify/Create main_cgi_full_path.
    if not to write here
    # for setting up delete test files.

    main_upload_full_path = get_full os.path.isdir(main_cgi_full_path):
        log_message(f"{YELLOW}_path(SERVER_ROOT_MAIN, UPLOAD_STORE_MAIN)
    main_cgi_full_Warning: CGI directory '{main_cgi_full_path}' not found. Attempting to create it.{RESET}")path = get_full_path(SERVER_ROOT_MAIN, CGI_BIN_MAIN)

    # Check
        try:
            os.makedirs(main_cgi_full_path, exist_ok=True)/Create Upload Directory
    if not os.path.isdir(main_upload_full_path):
        log
            log_message(f"  Successfully created '{main_cgi_full_path}'.")
        except_message(f"{YELLOW}Upload directory '{main_upload_full_path}' not found.{RESET}")
         OSError as e:
            log_message(f"{RED}Error: Could not create CGI directory '{main_cgi_full_path}': {e}. "
                        f"Ensure the parent directory '{os.path.dirname(mainif script_can_write_to_server_root or os.access(os.path.dirname(main_cgi_full_path)}' is writable or the directory exists. Exiting.{RESET}", True)
            _upload_full_path), os.W_OK):
            log_message(f"  Attempting to createsys.exit(1)

    # Create test-specific files within these verified locations
    try:
         upload directory '{main_upload_full_path}'...{RESET}")
            try:
                os.makedirswith open(get_full_path(SERVER_ROOT_MAIN, INDEX_PAGE_MAIN), "w")(main_upload_full_path, exist_ok=True)
                log_message(f"   as f:
            f.write("<html><body><h1>Welcome!</h1></body></html>")
        with open(getSuccessfully created '{main_upload_full_path}'.")
            except OSError as e:
                log_message(f"{_full_path(SERVER_ROOT_MAIN, "empty.html"), "w") as f:
            RED}Error: Could not create upload directory '{main_upload_full_path}': {e}. "
                            f.write("<html><body>Empty Page Content</body></html>")
        
        original_delete_test_filename =f"Ensure appropriate permissions. Exiting.{RESET}", True)
                sys.exit(1)
        else:
 "delete_test_for_basic_section.txt"
        original_delete_test_file_path = get            log_message(f"{RED}Error: Cannot create upload directory '{main_upload_full_path}'_full_path(main_upload_full_path, original_delete_test_filename)
        with open(original_delete_test_file_path, "w") as f:
            f.write(" due to parent directory permissions. Exiting.{RESET}", True)
            sys.exit(1)
    
This file is for the initial basic delete test, located in uploads.")

    except IOError as e:
        log_message(    # Check writability of upload directory (for the script to place test files for deletion)
    if not osf"{RED}Error creating essential test files (e.g., '{INDEX_PAGE_MAIN}') in '{SERVER.access(main_upload_full_path, os.W_OK):
        log_message(f_ROOT_MAIN}' or '{main_upload_full_path}': {e}. Exiting.{RESET}", True)
"{RED}Error: Script does not have write permission to upload directory '{main_upload_full_path}'. "        sys.exit(1)

    # Files created in the script's current working directory (for @file uploads)

                    f"Cannot set up files for delete tests. Exiting.{RESET}", True)
        sys.exit    with open("test.txt", "w") as f: f.write("This is a test file for(1)
    log_message(f"  Upload directory '{main_upload_full_path}' is uploads.")
    
    if not os.path.exists("big_bin.txt"):
        log_message("   accessible and writable by script.")

    # Check/Create CGI Directory
    if not os.path.isdir(Creating large binary file (big_bin.txt, 100KB)...")
        try:
            main_cgi_full_path):
        log_message(f"{YELLOW}CGI directory '{main_cgi_fullwith open("big_bin.txt", "wb") as f:
                f.write(os.ur_path}' not found.{RESET}")
        if script_can_write_to_server_root or os.accessandom(100 * 1024))
        except Exception as e:
            log_message(os.path.dirname(main_cgi_full_path), os.W_OK):
            log(f"    {RED}Failed to create big_bin.txt: {e}{RESET}")

    if not os_message(f"  Attempting to create CGI directory '{main_cgi_full_path}'...{RESET}").path.exists("big_text.txt"): 
        log_message("  Creating large text file (
            try:
                os.makedirs(main_cgi_full_path, exist_ok=True)big_text.txt, 5000 lines)...")
        try:
            with open("big
                log_message(f"  Successfully created '{main_cgi_full_path}'.")
            except_text.txt", "w") as f:
                f.write("this is a line of text\ OSError as e:
                log_message(f"{RED}Error: Could not create CGI directory '{main_n" * 5000)
        except Exception as e:
            log_message(f"cgi_full_path}': {e}. Exiting.{RESET}", True)
                sys.exit(1    {RED}Failed to create big_text.txt: {e}{RESET}")
    
    try:)
        else:
            log_message(f"{RED}Error: Cannot create CGI directory '{main_
        subprocess.run("head -c 100000 /dev/urandom > big.txt", shellcgi_full_path}' due to parent directory permissions. Exiting.{RESET}", True)
            sys.exit(=True, check=True, stderr=subprocess.PIPE)
        log_message("    Created big.txt1)
    log_message(f"  CGI directory '{main_cgi_full_path}' is (binary for chunked test in CWD)")
    except Exception as e:
        log_message(f"     accessible.")


    # --- Create Test-Specific Files ---
    # Place index.html and empty.html in SERVER{RED}Failed to create big.txt (binary in CWD) via head: {e}{RESET}")

    log_message(f"  {YELLOW}Ensure actual CGI scripts (guestbook_display.php etc.) exist in {_ROOT_MAIN if script has permission
    # Otherwise, tests for these files will rely on them already being presentmain_cgi_full_path} and are executable by the server.{RESET}")
    log_message(f.
    try:
        if script_can_write_to_server_root:
            with open"{GREEN}Setup complete.{RESET}")


def cleanup_test_files():
    log_message(f"{BOLD}Cleaning up test environment...{RESET}")
    script_files_to_remove = ["test.txt", "big_bin.txt", "big_text.txt", "big.txt"]
    
    # Construct full paths for server files
    main_upload_full_path = get_full_path(SERVER_ROOT_MAIN, UPLOAD_STORE_MAIN)
    server_files_to_remove = [
         get_full_path(main_upload_full_path, "delete_test_for_basic_section.txt"),
        get_full_path(SERVER_ROOT_MAIN, INDEX_PAGE_MAIN),
        get_full_path(SERVER_ROOT_MAIN, "empty.html"),
        get_full_path(SERVER_ROOT_MAIN, "delete_test.txt"),
        get_full_path(main_upload_full_path, "small_post.txt"),
        get_full_path(main_upload_full_path, FILE_FOR_DELETE_TEST), # basic_post.txt
        get_full_path(main_upload_full_path, "big.txt"), # if uploaded with this name
        get_full_path(main_upload_full_path, "test.txt"),
        get_full_path(main_upload_full_path, "disconnect_test.txt"),
        get_full_path(main_upload_full_path, "another_delete_test.txt"), # old delete test file
    ]
    # Add files from chunked tests assuming they are uploaded to UPLOAD_STORE_MAIN
    # with names derived from the test or a generic name like 'upload'
    # For simplicity, let's assume chunked tests might also create 'big.txt' or 'test.txt' in uploads.

    all_files = script_files_to_remove + server_files_to_remove
    for f_path in all_files:
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
            except OSError as e:
                log_message(f"  {YELLOW}Warning: Could not remove {f_path}: {e}{RESET}")
    log_message(f"{GREEN}Cleanup complete.{RESET}")

# --- Test Group Functions (modified to use global config vars) ---

def run_basic_single_loop_tests():
    # ... (other setup as before) ...
    main_upload_full_path = get_full_path(SERVER_ROOT_MAIN, UPLOAD_STORE_MAIN) # Get this path

    # Original Basic DELETE Request Handling (file is in uploads dir)
    original_delete_test_filename = "delete_test_for_basic_section.txt"
    delete_file_path_server = get_full_path(main_upload_full_path, original_delete_test_filename)
    delete_file_name_url = original_delete_test_filename # Name for URL param

    test_name_delete = "Basic DELETE Request Handling (Initial)"
    # The URL for delete is assumed to be /delete?file=...
    # The server's /delete location (with 'upload_store /uploads/') will look in its upload store.
    delete_url = f"http://{HOST1}:{PORT1}/delete?file={delete_file_name_url}" 

    if not os.path.exists(delete_file_path_server):
         log_message(f"  {YELLOW}Skipping initial DELETE test: File '{delete_file_path_server}' not found for deletion.{RESET}")
         print_status(test_name_delete, False)
    else:
        run_curl_exact(test_name_delete, ["-v", "-X", "DELETE", delete_url])
        log_message(f"  {YELLOW}VERIFY MANUALLY:{RESET} Check curl output in log for success status (e.g., 200/204).")
        time.sleep(1)
        if not os.path.exists(delete_file_path_server): # check_file_deleted can be used too
             log_message(f"  {GREEN}Verification: File '{delete_file_path_server}' is no longer present.{RESET}")
        else:
             log_message(f"  {RED}Verification: File '{delete_file_path_server}' STILL EXISTS after DELETE request.{RESET}")
    # ... (rest of the function) ...


def run_cgi_tests():
    log_message(f"\n{BOLD}--- CGI ---{RESET}")
    log_message(f"{YELLOW}NOTE: Verify HTTP status codes and content manually from curl output in log.{RESET}")
    base_url1 = f"http://{HOST1}:{PORT1}"
    cgi_url_base = f"{base_url1}/{CGI_BIN_MAIN.strip('/')}"

    run_curl_exact("CGI Execution with GET Method", ["-X", "GET", f"{cgi_url_base}/guestbook_display.php"])
    run_curl_exact("CGI Execution with POST Method",
                   ["-X", "POST", "-d", "username=TestUser", "-d", "message=Hello from curl",
                    f"{cgi_url_base}/guestbook.php"])
    run_curl_exact("CGI Script Relative Path File Access", ["-X", "GET", f"{cgi_url_base}/guestbook_display.php"])
    run_curl_exact("CGI Script Timeout/Infinite Loop Handling",
                   ["-X", "GET", f"{cgi_url_base}/infinite.php"],
                   expect_http_error=True, timeout=15)
    run_curl_exact("CGI Script Execution Error Handling",
                   ["-i", f"{cgi_url_base}/fatal_error.php"],
                   expect_http_error=True)

def run_chunked_tests():
    log_message(f"\n{BOLD}--- CHUNKED POST REQUEST ---{RESET}")
    log_message(f"{YELLOW}NOTE: Verify HTTP status codes and content manually from curl output in log.{RESET}")
    base_url1 = f"http://{HOST1}:{PORT1}"
    upload_url_base = f"{base_url1}/{UPLOAD_STORE_MAIN.strip('/')}" # Upload to main upload dir

    # Commands from TESTS.md for file prep are done in setup_test_files for 'big.txt'

    # * CHUNKED BINARY FILE: (using big.txt created in setup)
    if os.path.exists("big.txt"):
        # Ensure big.txt is binary for this test
        try:
            subprocess.run("head -c 100000 /dev/urandom > big.txt", shell=True, check=True, stderr=subprocess.PIPE)
            run_curl_exact("CHUNKED BINARY FILE (big.txt)",
                        ["-v", f"{upload_url_base}/uploaded_big_bin.txt", # Give it a name
                        "-H", "Transfer-Encoding: chunked",
                        "--data-binary", "@big.txt"])
        except Exception as e:
            log_message(f"    {RED}Failed to ensure big.txt is binary: {e}{RESET}")
            print_status("CHUNKED BINARY FILE (big.txt)", False)
    else:
        log_message(f"{YELLOW}Skipping CHUNKED BINARY FILE: big.txt not found.{RESET}")
        print_status("CHUNKED BINARY FILE (big.txt)", False)

    # * CHUNKED TEXT FILE: (using big.txt, now make it text)
    if os.path.exists("big.txt"):
         try:
             subprocess.run("yes \"this is a line of text\" | head -n 5000 > big.txt", shell=True, check=True, stderr=subprocess.PIPE)
             run_curl_exact("CHUNKED TEXT FILE (big.txt)",
                         ["-v", f"{upload_url_base}/uploaded_big_text.txt", # Give it a name
                         "-H", "Transfer-Encoding: chunked",
                         "--data-binary", "@big.txt"])
         except Exception as e:
             log_message(f"    {RED}Failed to make big.txt text: {e}{RESET}")
             print_status("CHUNKED TEXT FILE (big.txt)", False)
    else:
        log_message(f"{YELLOW}Skipping CHUNKED TEXT FILE: big.txt not found.{RESET}")
        print_status("CHUNKED TEXT FILE (big.txt)", False)

    run_curl_exact("CHUNKED TEXT/PLAIN",
                   ["-v", f"{upload_url_base}/uploaded_plain.txt",
                    "-H", "Content-Type: text/plain", "-H", "Transfer-Encoding: chunked",
                    "--data-binary", "hello again from plain text"])
    run_curl_exact("CHUNKED FORM FIELD",
                   ["-v", f"{upload_url_base}/uploaded_form.txt",
                    "-H", "Content-Type: application/x-www-form-urlencoded", "-H", "Transfer-Encoding: chunked",
                    "--data-binary", "username=tester&message=chunked%20rocks"])
    if not os.path.exists("test.txt"):
         log_message(f"{YELLOW}Skipping Chunked Multipart: test.txt not found.{RESET}")
         print_status("CHUNKED MULTIPART/FORM-DATA", False)
    else:
         run_curl_exact("CHUNKED MULTIPART/FORM-DATA (test.txt)",
                      ["-v", f"{upload_url_base}/", # Upload to dir, server names it
                       "-H", "Transfer-Encoding: chunked",
                       "-F", "file=@test.txt"])


def run_delete_tests_after_uploads():
    log_message(f"\n{BOLD}--- DELETE (After Uploads) ---{RESET}")
    log_message(f"{YELLOW}NOTE: Verify HTTP status codes manually from curl output in log.{RESET}")
    
    # Attempt to delete FILE_FOR_DELETE_TEST (e.g., basic_post.txt)
    # which should have been uploaded to UPLOAD_STORE_MAIN
    delete_target_server_path = get_full_path(get_full_path(SERVER_ROOT_MAIN, UPLOAD_STORE_MAIN), FILE_FOR_DELETE_TEST)
    
    # Construct URL for delete. Assumes a /delete location or similar that handles it.
    # The config example has /delete location.
    # The file to delete is passed as a query parameter.
    delete_url = f"http://{HOST1}:{PORT1}/delete?file={FILE_FOR_DELETE_TEST}"
    # Check if the /delete location has a different upload_store
    delete_location_upload_store = UPLOAD_STORE_MAIN # Default
    if parsed_server_configs:
        s0 = parsed_server_configs[0]
        for loc in s0.get("locations", []):
            if loc.get("path") == "/delete" and "upload_store" in loc:
                # If /delete has its own upload_store, the file must be relative to THAT store
                # This logic assumes file name is simple and doesn't contain path itself
                delete_location_upload_store = loc["upload_store"]
                delete_target_server_path = get_full_path(get_full_path(SERVER_ROOT_MAIN, delete_location_upload_store), FILE_FOR_DELETE_TEST)
                break


    log_message(f"  Attempting to delete: {FILE_FOR_DELETE_TEST} via URL: {delete_url}")
    log_message(f"  Expected server path for deletion: {delete_target_server_path}")

    if not os.path.exists(delete_target_server_path):
        log_message(f"  {YELLOW}File '{delete_target_server_path}' does not exist BEFORE delete. Test might not be meaningful or previous upload failed.{RESET}")
        # Don't mark as fail here, let curl try. If server handles non-existent deletes gracefully (404), that's a pass for curl.
    
    test_name = f"DELETE Uploaded File ({FILE_FOR_DELETE_TEST})"
    # A successful DELETE might return 200 OK (with body), 204 No Content, or 404 if file not found (which is OK for curl if expect_http_error)
    # For this test, we expect the file to exist and be deleted, so a 200/204 is ideal.FILE_FOR_DELETE_TEST
    # If server returns 404 because file wasn't there, curl will give exit code 22.
    # We will NOT set expect_http_error=True here, because we want to see if the DELETE itself was processed "successfully" by the server for an existing file.
    # If the file doesn't exist and server gives 404, curl gives 22, which will be KO here.
    # This makes the "OK" more meaningful for a successful deletion.
    deleted_by_curl = run_curl_exact(test_name, ["-v", "-X", "DELETE", delete_url])

    log_message(f"  {YELLOW}VERIFY MANUALLY:{RESET} Check curl output above for success status (e.g., 200/204).")
    time.sleep(1) # Give server time to process deletion
    if check_file_deleted(delete_target_server_path):
         log_message(f"  {GREEN}Verification: File '{delete_target_server_path}' is no longer present.{RESET}")
         if not deleted_by_curl: # If curl failed but file is gone, something is odd
             log_message(f"  {YELLOW}Warning: Curl reported KO, but file is deleted. Check server logic.{RESET}")
    else:
         log_message(f"  {RED}Verification: File '{delete_target_server_path}' STILL EXISTS after DELETE request.{RESET}")
         if deleted_by_curl: # If curl said OK but file is still there, that's a true failure of deletion.
             log_message(f"  {RED}This indicates a server-side failure to delete despite a 2xx response to curl.{RESET}")
             # Override the "OK" from curl if file not actually deleted
             global tests_passed, tests_failed
             if test_name in [item.split(":")[0].strip() for item in open(output_log_file.name).readlines() if ": OK" in item]: # Check if it was marked OK
                 tests_passed -=1
                 tests_failed +=1
                 # Re-log with KO
                 log_message(f"{test_name:<60}: {RED}KO (File not deleted){RESET}")



def run_multi_loop_tests():
    log_message(f"\n{BOLD}--- MULTI LOOP (Server Names) ---{RESET}")
    log_message(f"{YELLOW}NOTE: Verify server behavior manually from curl output in log.{RESET}")

    if not parsed_server_configs or len(parsed_server_configs) < 1:
        log_message(f"{YELLOW}Skipping multi-loop tests: Not enough server blocks parsed.{RESET}")
        print_status("Server Name 1 Access", False)
        print_status("Server Name 2 Access", False)
        return

    s0 = parsed_server_configs[0]
    host_s0 = s0.get("host", HOST1)
    port_s0 = s0.get("listen", PORT1)
    name_s0 = s0.get("server_names", [SERVER_NAME1])[0]
    
    resolve1 = f"{name_s0}:{port_s0}:{host_s0}"
    url1 = f"http://{name_s0}:{port_s0}/"
    run_curl_exact(f"Server Name 1 ({name_s0}) Access", ["--resolve", resolve1, url1])

    if len(parsed_server_configs) > 1:
        s1 = parsed_server_configs[1]
        host_s1 = s1.get("host", HOST2)
        port_s1 = s1.get("listen", PORT2) # Can be same port as s0 if host is different or names are distinct
        name_s1 = s1.get("server_names", [SERVER_NAME2])[0]

        resolve2 = f"{name_s1}:{port_s1}:{host_s1}"
        url2 = f"http://{name_s1}:{port_s1}/"
        run_curl_exact(f"Server Name 2 ({name_s1}) Access", ["--resolve", resolve2, url2])
    else:
        log_message(f"{YELLOW}Skipping Server Name 2 access: Only one server block configured/parsed.{RESET}")
        print_status("Server Name 2 Access", False) # Mark as fail if expected


def run_stress_tests():
    log_message(f"\n{BOLD}--- STRESS TEST - SIEGE ---{RESET}")
    base_url1 = f"http://{HOST1}:{PORT1}" # Use primary server for stress tests
    run_siege("Stress Test: Basic GET Availability", ["-b", "-c50", "-t30s", f"{base_url1}/empty.html"], timeout=45)
    run_siege("Stress Test: Server Stability", ["-b", "-c10", "-t60s", f"{base_url1}/empty.html"], timeout=75)


def run_other_tests():
    log_message(f"\n{BOLD}--- OTHER ---{RESET}")
    log_message(f"{YELLOW}NOTE: Verify behavior manually from output/server logs.{RESET}")
    base_url1 = f"http://{HOST1}:{PORT1}"

    test_name_disconnect = "Handling Abrupt Client Disconnect During Upload"
    log_message(f"  {YELLOW}Running disconnect simulation script (read_err.py)...{RESET}")
    disconnect_passed = False
    try:
        # read_err.py needs to know PORT1 and HOST1.
        # For simplicity, assume it reads them from its own constants or is configured.
        # If not, it should be modified to take them as args.
        result = subprocess.run([sys.executable, "read_err.py"], capture_output=True, text=True, timeout=10)
        log_message(f"  Disconnect script stdout:\n{result.stdout}")
        log_message(f"  Disconnect script stderr:\n{result.stderr}")
        if result.returncode == 0:
             log_message(f"  Disconnect script finished (simulated disconnect sent).")
             disconnect_passed = True
             log_message(f"  {YELLOW}VERIFY MANUALLY:{RESET} Check server logs for errors/resource leaks.")
        elif "Connection refused" in result.stderr:
             log_message(f"  {RED}Disconnect script failed: Connection refused.{RESET}")
        else:
            log_message(f"  {RED}Disconnect script failed (Exit Code: {result.returncode}).{RESET}")
    except Exception as e:
         log_message(f"{RED}Error running disconnect script: {e}{RESET}")
    print_status(test_name_disconnect, disconnect_passed)
    log_message("-" * 30)

    test_name_big_header = "Big header"
    header_size = 8000 # Reduced from 100k due to shell limits
    # Use primary server name for Host header construction
    primary_server_name = SERVER_NAME1
    if parsed_server_configs and parsed_server_configs[0].get("server_names"):
        primary_server_name = parsed_server_configs[0]["server_names"][0]

    big_host_str = f"$(printf 'a%.0s' {{1..{header_size}}}).{primary_server_name}"
    curl_cmd_list = ["-v", "-H", f"Host: {big_host_str}", f"{base_url1}/empty.html"]
    
    log_message(f"  {YELLOW}Running: curl {' '.join(curl_cmd_list)} (using shell=True){RESET}")
    log_message(f"  {CYAN}--- curl output start ---{RESET}")
    success_bh = False
    try:
        process = subprocess.Popen(f"curl {' '.join(curl_cmd_list)}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=15)
        if stdout:
            log_message("  Stdout:")
            for line in stdout.splitlines(): log_message(f"    {line}")
        if stderr:
            log_message("  Stderr:")
            for line in stderr.splitlines(): log_message(f"    {line}")
        
        returncode = process.returncode
        log_message(f"  {CYAN}--- curl output end ---{RESET}")
        log_message(f"  {CYAN}curl exit code: {returncode}{RESET}")

        if returncode == 22: # Expecting 4xx error
            log_message(f"  {YELLOW}Note: curl exit code 22 treated as OK (expected HTTP error for large header).{RESET}")
            success_bh = True
        elif returncode == 0:
             log_message(f"  {RED}Curl exited with 0, but an HTTP error (4xx) was expected.{RESET}")
        else:
            log_message(f"  {RED}Curl Error: Command failed with exit code {returncode}.{RESET}")
    except subprocess.TimeoutExpired:
        log_message(f"  {CYAN}--- curl output end (timeout) ---{RESET}")
        log_message(f"  {RED}Command timed out.{RESET}")
    except Exception as e:
        log_message(f"  {CYAN}--- curl output end (exception) ---{RESET}")
        log_message(f"  {RED}An unexpected error occurred: {e}{RESET}")
    print_status(test_name_big_header, success_bh)
    log_message("-" * 30)

    log_message(f"\n{BOLD}--- Open FDs (Manual Test) ---{RESET}")
    log_message(f"{YELLOW}This test requires manual execution as described in TESTS.md.{RESET}")
    log_message(f"1. {BOLD}Start webserv via Valgrind:{RESET} valgrind --leak-check=full --track-fds=yes ./webserv {CONFIG_FILE_PATH}")
    log_message(f"2. {BOLD}Perform requests.{RESET}")
    log_message(f"3. {BOLD}Stop webserv (Ctrl+C).{RESET}")
    log_message(f"4. {BOLD}Check Valgrind output{RESET} for FD leaks.")

# --- Main Execution ---
if __name__ == "__main__":
    output_filename = "test_results.log"
    try:
        output_log_file = open(output_filename, "w")
    except IOError as e:
        print(f"{RED}Fatal: Could not open log file '{output_filename}': {e}{RESET}")
        sys.exit(1)

    log_message(f"{BOLD}*** Webserver Test Suite (Exact Curl Commands) ***{RESET}")
    log_message(f"Using configuration file: {CONFIG_FILE_PATH}")
    log_message(f"{YELLOW}!!! IMPORTANT: Ensure 'webserv' is running and configured")
    log_message(f"!!! matching the parsed settings from '{CONFIG_FILE_PATH}'.")
    log_message(f"!!! You MUST manually verify HTTP status codes and content")
    log_message(f"!!! from the curl output in '{output_filename}'. 'OK' only means curl")
    log_message(f"!!! executed without connection/transfer errors (or got an expected HTTP error).")
    log_message(f"{RESET}" + "-" * 60)
    
    if not parse_config(CONFIG_FILE_PATH):
        log_message(f"{RED}Exiting due to configuration parsing errors.{RESET}", True)
        output_log_file.close()
        sys.exit(1)
    
    time.sleep(1) # Give a moment to read initial messages if any were printed to console

    setup_test_files()

    try:
        log_message(f"{BOLD}Checking basic server connectivity...{RESET}")
        if not run_curl_exact("Initial Connectivity Check Port 1", [f"http://{HOST1}:{PORT1}/"]):
             log_message(f"{RED}Initial connectivity check failed for Port {PORT1}. Aborting tests.{RESET}", True)
             cleanup_test_files()
             output_log_file.close()
             sys.exit(1)
        log_message(f"{GREEN}Initial connectivity check passed (curl exit code 0).{RESET}")

        run_basic_single_loop_tests()
        run_cgi_tests()
        run_chunked_tests()
        # DELETE test now runs after uploads
        run_delete_tests_after_uploads() 
        run_multi_loop_tests()
        run_stress_tests()
        run_other_tests()

    except KeyboardInterrupt:
        log_message(f"\n{YELLOW}Test execution interrupted by user.{RESET}")
    finally:
        cleanup_test_files()
        
        summary_header = f"\n{BOLD}--- Test Summary ---{RESET}"
        summary_passed = f"{GREEN}Tests resulting in OK status: {tests_passed}{RESET}"
        summary_failed = f"{RED}Tests resulting in KO status: {tests_failed}{RESET}"
        summary_reminder1 = f"{YELLOW}Reminder: 'OK' indicates curl execution success, not necessarily HTTP success.{RESET}"
        summary_reminder2 = f"{YELLOW}Manual verification of '{output_filename}' is required.{RESET}"
        
        log_message(summary_header)
        log_message(summary_reminder1)
        log_message(summary_reminder2)
        log_message(summary_passed)
        log_message(summary_failed)
        log_message("-" * 20)

        # Print summary to console
        print(summary_header)
        print(summary_passed)
        print(summary_failed)
        
        if output_log_file:
            output_log_file.close()

        if tests_failed == 0 and tests_passed > 0:
            log_message(f"{GREEN}{BOLD}All tests executed without curl errors (check log for HTTP details).{RESET}", True)
            sys.exit(0)
        elif tests_passed == 0 and tests_failed == 0:
             log_message(f"{YELLOW}No tests were executed or reported status.{RESET}", True)
             sys.exit(1)
        else:
            log_message(f"{RED}{BOLD}Some tests encountered curl execution errors.{RESET}", True)
            sys.exit(1)