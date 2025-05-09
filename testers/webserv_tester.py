#!/usr/bin/env python3

# Add: easier config for 1-2 server loops + ports, hosts & names for each,
# and ensure siege is killed properly

import subprocess
import os
import re
import time
import sys
import logging
from pathlib import Path

# Modify to match config file location
CONFIG_FILE_PATH = "config/multi.conf"

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_config(config_path):
    """Parse the config file to extract server blocks and their ports."""
    try:
        with open(config_path, 'r') as f:
            content = f.read()
        
        # Split into server blocks (server {})
        server_blocks = re.split(r'server\s*{', content)[1:]
        servers = []
        
        for block in server_blocks:
            ports = re.findall(r'listen\s+(\d+);', block)
            server_names = re.findall(r'server_name\s+([^;]+);', block)
            servers.append({
                'ports': [int(port) for port in ports],
                'server_names': server_names[0].split() if server_names else []
            })
        
        logger.info(f"Found {len(servers)} server blocks with ports: {[s['ports'] for s in servers]}")
        return servers
    
    except FileNotFoundError:
        logger.error(f"Config file not found: {config_path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error parsing config file: {e}")
        sys.exit(1)

def run_command(command, check=True, timeout=30):
    """Run a shell command and return its output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if check and result.returncode != 0:
            logger.error(f"Command failed: {command}\n{result.stderr}")
            return False, result.stderr
        return True, result.stdout
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out: {command}")
        return False, "Timeout"
    except Exception as e:
        logger.error(f"Error running command {command}: {e}")
        return False, str(e)

def prepare_test_files():
    """Prepare test files for chunked requests."""
    logger.info("Preparing test files...")
    run_command("head -c 100000 /dev/urandom > big.txt")
    run_command('yes "this is a line of text" | head -n 5000 > test.txt')

def create_read_err_script():
    """Create read_err.py for testing abrupt client disconnect."""
    script_content = """
# #!/usr/bin/env python3
# import socket
# import time

# def main():
#     s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#     s.connect(('127.0.0.1', 8080))
#     request = b"POST /uploads HTTP/1.1\\r\\nHost: localhost\\r\\nContent-Length: 1000000\\r\\n\\r\\n"
#     s.send(request)
#     s.send(b"partial data")
#     time.sleep(0.1)
#     s.close()

# if __name__ == "__main__":
#     main()
# """
#     with open("read_err.py", "w") as f:
#         f.write(script_content)
#     os.chmod("read_err.py", 0o755)
#     logger.info("Created read_err.py")

def run_basic_tests(port):
    """Run basic tests for a given port."""
    logger.info(f"Running basic tests on port {port}...")
    tests = [
        # Multiple Ports Configuration
        (f"curl http://localhost:{port}", "Basic GET"),
        (f"curl http://localhost:{port+1}", "Alternate Port GET"),
        
        # Client Body Size Limit Enforcement
        (f'curl -v -X POST http://localhost:{port}/uploads '
         '-H "Content-Type: application/x-www-form-urlencoded" '
         '--data-binary "text=Hello%20world"', "POST Body Size"),
        
        # Routing to Different Locations/Directories
        (f"curl http://localhost:{port}/index.html", "Index HTML"),
        (f"curl http://localhost:{port}/cgi-bin/guestbook_display.php", "CGI Route"),
        
        # Custom Error Page Handling (404)
        (f"curl -i http://localhost:{port}/nonexistent_page.txt", "404 Error"),
        
        # Directory Index File Serving
        (f"curl http://localhost:{port}/uploads/", "Directory Index"),
        
        # Method Restriction per Route
        (f"curl http://localhost:{port}/cgi-bin/", "Method Restriction"),
        
        # Basic GET Request Handling
        (f"curl -X GET http://localhost:{port}/index.html", "GET Request"),
        
        # Basic POST Request Handling
        (f'curl -X POST --data "test_data" http://localhost:{port}/uploads', "POST Request"),
        
        # Basic DELETE Request Handling
        (f'curl -v -X DELETE "http://127.0.0.1:{port}/delete?file=test.txt"', "DELETE Request"),
        
        # Unknown/Invalid HTTP Method Handling
        (f"curl -X INVALIDMETHOD http://localhost:{port}/", "Invalid Method"),
        
        # Directory Listing (Autoindex)
        (f"curl -X GET http://localhost:{port}/uploads/", "Autoindex"),
        
        # HTTP Redirection (301/302)
        (f"curl -i http://127.0.0.1:{port}/redirect", "Redirection"),
    ]
    
    for cmd, test_name in tests:
        success, output = run_command(cmd)
        logger.info(f"{test_name}: {'PASS' if success else 'FAIL'}\n{output}")

def run_cgi_tests(port):
    """Run CGI-related tests for a given port."""
    logger.info(f"Running CGI tests on port {port}...")
    tests = [
        # CGI Execution with GET Method
        (f"curl -X GET http://127.0.0.1:{port}/cgi-bin/guestbook_display.php", "CGI GET"),
        
        # CGI Execution with POST Method
        (f'curl -X POST '
         f'-d "username=TestUser" '
         f'-d "message=Hello from curl" '
         f'http://127.0.0.1:{port}/cgi-bin/guestbook.php', "CGI POST"),
        
        # CGI Script Timeout/Infinite Loop Handling
        (f"curl -X GET http://127.0.0.1:{port}/cgi-bin/infinite.php", "CGI Timeout"),
        
        # CGI Script Execution Error Handling
        (f"curl -i http://127.0.0.1:{port}/cgi-bin/fatal_error.php", "CGI Error"),
    ]
    
    for cmd, test_name in tests:
        success, output = run_command(cmd)
        logger.info(f"{test_name}: {'PASS' if success else 'FAIL'}\n{output}")

def run_chunked_tests(port):
    """Run chunked POST request tests for a given port."""
    logger.info(f"Running chunked POST tests on port {port}...")
    tests = [
        # CHUNKED BINARY FILE
        (f'curl -v http://localhost:{port}/uploads '
         '-H "Transfer-Encoding: chunked" '
         '--data-binary "@big.txt"', "Chunked Binary"),
        
        # CHUNKED TEXT FILE
        (f'curl -v http://localhost:{port}/uploads '
         '-H "Transfer-Encoding: chunked" '
         '--data-binary "@test.txt"', "Chunked Text"),
        
        # CHUNKED TEXT/PLAIN
        (f'curl -v http://localhost:{port}/uploads '
         '-H "Content-Type: text/plain" '
         '-H "Transfer-Encoding: chunked" '
         '--data-binary "hello again from plain text"', "Chunked Plain Text"),
        
        # CHUNKED FORM FIELD
        (f'curl -v http://localhost:{port}/uploads '
         '-H "Content-Type: application/x-www-form-urlencoded" '
         '-H "Transfer-Encoding: chunked" '
         '--data-binary "username=tester&message=chunked%20rocks"', "Chunked Form"),
        
        # CHUNKED MULTIPART/FORM-DATA
        (f'curl -v http://localhost:{port}/uploads '
         '-H "Transfer-Encoding: chunked" '
         '-F "file=@test.txt"', "Chunked Multipart"),
    ]
    
    for cmd, test_name in tests:
        success, output = run_command(cmd)
        logger.info(f"{test_name}: {'PASS' if success else 'FAIL'}\n{output}")

def run_delete_tests(port):
    """Run DELETE request tests for a given port."""
    logger.info(f"Running DELETE tests on port {port}...")
    cmd = f'curl -v -X DELETE "http://127.0.0.1:{port}/delete?file=test_1.txt"'
    success, output = run_command(cmd)
    logger.info(f"DELETE Request: {'PASS' if success else 'FAIL'}\n{output}")

def run_multi_loop_tests(servers):
    """Run multi-loop tests for multiple server names on the same port."""
    logger.info("Running multi-loop tests...")
    for i, server in enumerate(servers):
        for server_name in server['server_names']:
            for port in server['ports']:
                ip = f"127.0.0.{i+1}"
                cmd = (f"curl --resolve {server_name}:{port}:{ip} "
                       f"http://{server_name}:{port}/")
                success, output = run_command(cmd)
                logger.info(f"Server {server_name}:{port}: {'PASS' if success else 'FAIL'}\n{output}")

def run_stress_tests(port):
    """Run stress tests using siege for a given port."""
    logger.info(f"Running stress tests on port {port}...")
    tests = [
        # Stress Test: Basic GET Availability
        (f"siege -b -c50 -t15s http://localhost:{port}/index.html", "Stress GET"),
    ]
    
    for cmd, test_name in tests:
        success, output = run_command(cmd, check=False)  # Siege may return non-zero on completion
        logger.info(f"{test_name}: {'PASS' if success else 'FAIL'}\n{output}")

def run_other_tests(port):
    """Run other miscellaneous tests for a given port."""
    logger.info(f"Running other tests on port {port}...")
    
    # Handling Abrupt Client Disconnect During Upload
    create_read_err_script()
    success, output = run_command("python3 read_err.py")
    logger.info(f"Abrupt Disconnect: {'PASS' if success else 'FAIL'}\n{output}")
    
    # Big Header
    cmd = (f'curl -v -H "Host: $(printf \'a%.0s\' {{1..100000}}).testiservu1.com" '
           f'http://127.0.0.1:{port}/index.html')
    success, output = run_command(cmd)
    logger.info(f"Big Header: {'PASS' if success else 'FAIL'}\n{output}")
    
    # Open File Descriptors (Valgrind)
    cmd = "valgrind --leak-check=full --track-fds=yes ./webserv"
    success, output = run_command(cmd, check=False, timeout=60)
    logger.info(f"Valgrind FD Check: {'PASS' if success else 'FAIL'}\n{output}")

def main():
    """Main function to orchestrate the tests."""
    logger.info(f"Starting tests with config file: {CONFIG_FILE_PATH}")
    
    # Parse config to determine server blocks
    servers = parse_config(CONFIG_FILE_PATH)
    if not 1 <= len(servers) <= 3:
        logger.error("Config file must contain 1–3 server blocks")
        sys.exit(1)
    
    # Prepare test files
    prepare_test_files()
    
    # Run tests for each server block
    for server in servers:
        for port in server['ports']:
            logger.info(f"Testing server on port {port}")
            run_basic_tests(port)
            run_cgi_tests(port)
            run_chunked_tests(port)
            run_delete_tests(port)
            run_stress_tests(port)
            run_other_tests(port)
    
    # Run multi-loop tests if multiple servers exist
    if len(servers) > 1:
        run_multi_loop_tests(servers)
    
    logger.info("All tests completed")

if __name__ == "__main__":
    main()