#!/usr/bin/env python3
"""
A Python script implementation of a container image scanning tool that supports
parallel preflight scans and writes results directly to an XLSX file.
It supports both API‐based mode (using an API token) and offline mode (using an image list file).
"""

import argparse
import sys
import os
import subprocess
import re
import time
import json
import csv
import shutil
import datetime
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment

# ------------------------------------------------------------------------------
# XLSX writing function
# ------------------------------------------------------------------------------

def write_and_format_xlsx(data: List[List[str]], output_xlsx: str) -> None:
    """
    Takes scan result data, sorts it by 'Status' and 'Test Case' (with custom order),
    formats the worksheet, and saves the result as an Excel workbook.
    """
    if not data:
        raise ValueError("No data to write to XLSX")
    
    # Convert to dictionary format for easier processing
    headers = ["Image Name", "Image Tag", "Has Modified Files", "Test Case", "Status"]
    dict_data = []
    for row in data:
        if len(row) >= 5:
            dict_data.append({
                headers[0]: row[0],
                headers[1]: row[1], 
                headers[2]: row[2],
                headers[3]: row[3],
                headers[4]: row[4]
            })
    
    # Sort data by Status and Test Case with custom order
    status_order = {'FAILED': 0, 'NOT_APP': 1, 'PASSED': 2}
    dict_data.sort(key=lambda x: (status_order.get(x.get('Status', ''), 3), x.get('Test Case', '')))
    
    # Create workbook and worksheet
    wb = Workbook()
    ws = wb.active
    
    if ws is None:
        raise ValueError("Failed to create worksheet")
    
    # Set column widths
    column_widths = {
        'A': 20, 'B': 30, 'C': 40, 'D': 30, 'E': 20
    }
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width
    
    # Write headers
    ws.append(headers)
    
    # Write data rows
    for row_data in dict_data:
        ws.append([row_data.get(header, '') for header in headers])
    
    # Enable text wrap for column C (Has Modified Files)
    for cell in ws['C']:
        cell.alignment = Alignment(wrap_text=True)
    
    # Format the Status column (assumed to be column E)
    status_colors = {
        'PASSED': '006400',    # Dark green
        'FAILED': 'FF0000',    # Red
        'NOT_APP': 'FFA500'    # Dark orange
    }
    
    for row in ws.iter_rows(min_row=2, min_col=5, max_col=5):
        for cell in row:
            cell_value = str(cell.value) if cell.value is not None else ""
            if cell_value in status_colors:
                cell.font = Font(color=status_colors[cell_value])
    
    # Set alignment: center for "Status" and "Image Tag", left for others
    for col in ws.columns:
        col_list = list(col)
        if col_list:
            header_value = str(col_list[0].value) if col_list[0].value is not None else ""
            if header_value in ['Status', 'Image Tag']:
                for cell in col_list:
                    cell.alignment = Alignment(horizontal='center', vertical='center')
            else:
                for cell in col_list:
                    cell.alignment = Alignment(horizontal='left', vertical='center')
    
    # Format header row
    header_fill = PatternFill(start_color='ADD8E6', end_color='ADD8E6', fill_type='solid')
    header_font = Font(bold=True, color='000000')
    header_alignment = Alignment(horizontal='center', vertical='center')
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    wb.save(output_xlsx)

# ------------------------------------------------------------------------------
# Legacy CSV-to-XLSX conversion function (kept for backward compatibility)
# ------------------------------------------------------------------------------

def convert_and_format_csv_to_xlsx(input_csv: str, output_xlsx: str) -> None:
    """
    Reads the CSV file, sorts it by 'Status' and 'Test Case' (with custom order),
    formats the worksheet, and saves the result as an Excel workbook.
    """
    # Read CSV data manually instead of using pandas
    with open(input_csv, 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        data = list(reader)
    
    # Sort data by Status and Test Case with custom order
    status_order = {'FAILED': 0, 'NOT_APP': 1, 'PASSED': 2}
    data.sort(key=lambda x: (status_order.get(x.get('Status', ''), 3), x.get('Test Case', '')))
    
    # Create workbook and worksheet
    wb = Workbook()
    ws = wb.active
    
    if ws is None:
        raise ValueError("Failed to create worksheet")
    
    # Set column widths
    column_widths = {
        'A': 20, 'B': 30, 'C': 40, 'D': 30, 'E': 20
    }
    for col, width in column_widths.items():
        ws.column_dimensions[col].width = width
    
    # Write headers
    if data:
        headers = list(data[0].keys())
        ws.append(headers)
        
        # Write data rows
        for row in data:
            ws.append([row.get(header, '') for header in headers])
    
    # Enable text wrap for column C (Has Modified Files)
    for cell in ws['C']:
        cell.alignment = Alignment(wrap_text=True)
    
    # Format the Status column (assumed to be column E)
    status_colors = {
        'PASSED': '006400',    # Dark green
        'FAILED': 'FF0000',    # Red
        'NOT_APP': 'FFA500'    # Dark orange
    }
    
    for row in ws.iter_rows(min_row=2, min_col=5, max_col=5):
        for cell in row:
            cell_value = str(cell.value) if cell.value is not None else ""
            if cell_value in status_colors:
                cell.font = Font(color=status_colors[cell_value])
    
    # Set alignment: center for "Status" and "Image Tag", left for others
    for col in ws.columns:
        col_list = list(col)
        if col_list:
            header_value = str(col_list[0].value) if col_list[0].value is not None else ""
            if header_value in ['Status', 'Image Tag']:
                for cell in col_list:
                    cell.alignment = Alignment(horizontal='center', vertical='center')
            else:
                for cell in col_list:
                    cell.alignment = Alignment(horizontal='left', vertical='center')
    
    # Format header row
    header_fill = PatternFill(start_color='ADD8E6', end_color='ADD8E6', fill_type='solid')
    header_font = Font(bold=True, color='000000')
    header_alignment = Alignment(horizontal='center', vertical='center')
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
    
    wb.save(output_xlsx)

# ------------------------------------------------------------------------------
# PreflightScanner class
# ------------------------------------------------------------------------------

class PreflightScanner:
    """Main class for handling container image scanning with preflight."""
    
    RESULT_XLSX = "images_scan_results.xlsx"
    MIN_PYTHON_VERSION = (3, 9)
    MIN_PREFLIGHT_VERSION = "1.6.11"

    def __init__(self):
        self.args = self.parse_args()
        self.api_token = self.args.api_token
        self.repo_namespace = self.args.repo_namespace
        self.cnf_prefix = self.args.cnf_prefix
        self.tag_type = self.args.tag_type or "name"
        self.auth_json = self.args.auth_json
        self.fqdn = self.args.fqdn
        self.filter = self.args.filter or "chartrepo"
        self.image_file = self.args.image_file
        self.parallel = self.args.parallel
        self.debug = self.args.debug
        self.image_list: List[str] = []

    def parse_args(self) -> argparse.Namespace:
        """Parse command line arguments."""
        parser = argparse.ArgumentParser(
            description="""Scan container images using preflight in parallel and write results directly to XLSX.

Usage Examples:

API-based:
  ./quick_scan_container_images_parallel.py --repo-namespace avareg_5gc --cnf-prefix "global-|specific" \\
      --auth-json auth.json --api-token xxxxxx --fqdn quay.io --tag-type name --filter "existed_image|tested_image" --parallel 2

Offline:
  ./quick_scan_container_images_parallel.py --image-file image_list.txt --auth-json auth.json --parallel 2
  ./quick_scan_container_images_parallel.py --image-file image_list.txt
  ./quick_scan_container_images_parallel.py --image-file image_list.txt --parallel 2

Note: if preflight scan failed for some reason, then you add --debug
""",
            formatter_class=argparse.RawTextHelpFormatter
        )
        
        # API-based arguments
        parser.add_argument("--repo-namespace", "-rn", 
                          help="Repository namespace (e.g., 'avareg_5gc' or 'avu0').")
        parser.add_argument("--cnf-prefix", "-cp", 
                          help="CNF image prefix to search for (e.g., 'global-' or 'global|non-global').")
        parser.add_argument("--tag-type", "-t", 
                          help="Image tag type: 'name' (default) or 'digest'.")
        parser.add_argument("--api-token", "-at", 
                          help="API token (Bearer Token) for registry access.")
        parser.add_argument("--auth-json", "-d", 
                          help="Path to Docker authentication JSON file (if required).")
        
        # Offline argument
        parser.add_argument("--image-file", "-img", 
                          help="Text file with a list of images (one per line).")
        
        # Common arguments
        parser.add_argument("--fqdn", "-fq", 
                          help="Fully-qualified domain name of your registry (e.g., 'quay.io').")
        parser.add_argument("--filter", "-ft", 
                          help="Filter to exclude images (e.g., 'existed_image|tested_image').")
        parser.add_argument("--parallel", "-p", type=int, default=1, 
                          help="Number of images to scan in parallel (default: 1).")
        parser.add_argument("--debug", action="store_true", 
                          help="Enable debug logging.")
        
        return parser.parse_args()

    def log(self, message: str) -> None:
        """Log a message with timestamp."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H:%M:%S")
        print(f"{timestamp} {message}")

    def exit_with_error(self, message: str) -> None:
        """Log error message and exit."""
        self.log(message)
        sys.exit(1)

    @staticmethod
    def file_exists(filepath: str) -> bool:
        """Check if a file exists."""
        return os.path.exists(filepath)

    def rename_file(self, old_name: str, new_name: str) -> bool:
        """Rename a file safely."""
        if not self.file_exists(old_name):
            self.log(f"Error: file '{old_name}' does not exist")
            return False
        try:
            os.rename(old_name, new_name)
            self.log(f"File '{old_name}' has been renamed to '{new_name}'")
            return True
        except Exception as e:
            self.log(f"Error renaming file: {e}")
            return False

    def print_status(self, description: str, status: str, color: str = "32") -> None:
        """Print formatted status message."""
        if status == "OK":
            color_code = "32"  # Green
        elif status == "NOK":
            color_code = "31"  # Red
        else:
            color_code = "33"  # Yellow
        
        print(f"{description:<48} \033[1;{color_code}m{status:<24}\033[m")

    def check_required_tools(self) -> None:
        """Check if required tools are installed."""
        if shutil.which("python3") and shutil.which("preflight"):
            self.print_status("python3 and preflight installed", "OK")
        else:
            self.print_status("python3 and preflight installed", "NOK")
            sys.exit(1)

    def check_python_version(self) -> None:
        """Check if Python version meets minimum requirements."""
        current_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        min_version = f"{self.MIN_PYTHON_VERSION[0]}.{self.MIN_PYTHON_VERSION[1]}"
        
        if sys.version_info >= self.MIN_PYTHON_VERSION:
            self.print_status(f"Python3 version ({current_version}>={min_version})", "OK")
        else:
            self.print_status(f"Python3 version ({current_version}>={min_version})", "NOK")
            sys.exit(1)

    @staticmethod
    def version_tuple(version_str: str) -> tuple:
        """Convert version string to tuple for comparison."""
        return tuple(map(int, version_str.split(".")))

    def check_preflight_version(self) -> None:
        """Check if preflight version meets minimum requirements."""
        try:
            result = subprocess.run(
                ["preflight", "--version"], 
                capture_output=True, text=True, check=True
            )
            match = re.search(r'(\d+\.\d+\.\d+)', result.stdout)
            if match:
                current_version = match.group(1)
                if self.version_tuple(current_version) < self.version_tuple(self.MIN_PREFLIGHT_VERSION):
                    self.print_status(f"Preflight version ({current_version}>={self.MIN_PREFLIGHT_VERSION})", "NOK")
                    sys.exit(1)
                else:
                    self.print_status(f"Preflight version ({current_version}>={self.MIN_PREFLIGHT_VERSION})", "OK")
            else:
                self.log("Could not determine preflight version.")
                sys.exit(1)
        except subprocess.CalledProcessError as e:
            self.log(f"Error checking preflight version: {e}")
            sys.exit(1)

    def check_python_dependencies(self) -> None:
        """Check if required Python dependencies are installed."""
        try:
            import openpyxl  # noqa: F401
            self.print_status("Python Openpyxl installed", "OK")
        except ImportError as e:
            missing = str(e).split("No module named")[-1].strip(" '")
            self.print_status(f"Python {missing}", "NOK")
            sys.exit(1)

    def check_registry_connection(self) -> None:
        """Check connection to the registry."""
        if not self.fqdn:
            return
            
        if shutil.which("nc"):
            try:
                subprocess.run(
                    ["nc", "-zv4", self.fqdn, "80"], 
                    capture_output=True, text=True, check=True
                )
                self.print_status(f"{self.fqdn} connection", "OK")
            except subprocess.CalledProcessError:
                self.print_status(f"{self.fqdn} connection", "NOK")
                sys.exit(1)
        else:
            self.print_status(f"{self.fqdn} connection", "SKIPPED")

    def check_registry_authentication(self) -> None:
        """Check registry authentication using Bearer token."""
        if not self.api_token or not self.fqdn or not self.repo_namespace:
            return
            
        url = f"https://{self.fqdn}/api/v1/repository?namespace={self.repo_namespace}"
        try:
            result = subprocess.run([
                "curl", "-I", "--silent", "-o", "/dev/null", "-w", "%{http_code}",
                "-X", "GET", "-H", f"Authorization: Bearer {self.api_token}", url
            ], capture_output=True, text=True, check=True)
            
            if result.stdout.strip() == "200":
                self.print_status("Registry auth (Bearer Token)", "OK")
            else:
                self.print_status("Registry auth (Bearer Token)", "NOK")
                sys.exit(1)
        except subprocess.CalledProcessError as e:
            self.log(f"Error checking registry authentication: {e}")
            sys.exit(1)

    def ensure_trailing_newline(self, filepath: str) -> None:
        """Ensure file ends with a newline."""
        try:
            with open(filepath, "rb+") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.write(b"\n")
        except Exception as e:
            self.log(f"Error ensuring trailing newline in {filepath}: {e}")

    def fetch_image_list_from_api(self) -> List[str]:
        """Fetch image list from registry API."""
        if not self.fqdn or not self.repo_namespace:
            return []
            
        try:
            api_url = f"https://{self.fqdn}/api/v1/repository?namespace={self.repo_namespace}"
            proc = subprocess.run([
                "curl", "--silent", "-X", "GET", 
                "-H", f"Authorization: Bearer {self.api_token}", api_url
            ], capture_output=True, text=True, check=True)
            
            data = json.loads(proc.stdout)
            filtered_list = []
            
            for repo in data.get("repositories", []):
                name = repo.get("name", "")
                if self.cnf_prefix and self.cnf_prefix in name and self.filter not in name:
                    filtered_list.append(name)
            
            return filtered_list
        except Exception as e:
            self.log(f"Error fetching repository list: {e}")
            sys.exit(1)

    def build_image_list(self) -> None:
        """Build the list of images to scan."""
        default_images = ['ava-core/univ-nf-ava', 'ava-core/univ-nf-alex']
        
        if not self.api_token:
            # Offline mode - read from file
            if not self.image_file:
                self.exit_with_error("Image file must be provided in offline mode")
            
            self.ensure_trailing_newline(self.image_file)
            with open(self.image_file, "r") as f:
                self.image_list = [line.strip() for line in f if line.strip()]
        else:
            # API mode
            if not self.cnf_prefix:
                self.image_list = default_images
            else:
                filtered_list = self.fetch_image_list_from_api()
                self.image_list = filtered_list + default_images
        
        if not self.image_list:
            self.exit_with_error("No images found. Check the API response or the image list file!")

    def write_results_to_xlsx(self, scan_data: List[List[str]]) -> None:
        """Write scan results directly to Excel format."""
        try:
            write_and_format_xlsx(scan_data, self.RESULT_XLSX)
            self.log(f"Scan results written to {self.RESULT_XLSX} successfully!")
        except Exception as e:
            self.exit_with_error(f"Failed to write results to XLSX: {e}")

    def get_image_details(self, image: str) -> Dict[str, Any]:
        """Get image details either from file or API."""
        try:
            if not self.api_token:
                # Offline mode
                image_details = image.strip()
                parts = image_details.split("/", 1)
                repo_img_tag = parts[1] if len(parts) > 1 else image_details
                img_name = repo_img_tag.split("/")[-1].split(":")[0]
                inspect_url = image_details
                tag = image_details.split(":")[1] if ":" in image_details else ""
            else:
                # API mode
                image_url = f"https://{self.fqdn}/api/v1/repository/{self.repo_namespace}/{image.strip()}"
                proc = subprocess.run([
                    "curl", "--silent", "-X", "GET", 
                    "-H", f"Authorization: Bearer {self.api_token}", image_url
                ], capture_output=True, text=True, check=True)
                
                data = json.loads(proc.stdout)
                
                if self.tag_type == "name":
                    tag_val = data["tags"][0]["name"] if data.get("tags") else ""
                    image_details = f"{data['name']}:{tag_val}"
                else:
                    tag_val = data["tags"][0]["manifest_digest"] if data.get("tags") else ""
                    image_details = f"{data['name']}@{tag_val}"
                
                tag = tag_val
                img_name = image.strip().split("/")[-1]
                repo_img_tag = f"{img_name}:{tag}"
                inspect_url = f"{self.fqdn}/{self.repo_namespace}/{image.strip()}:{tag}"
            
            return {
                "success": True,
                "image_details": image_details,
                "tag": tag,
                "img_name": img_name,
                "repo_img_tag": repo_img_tag,
                "inspect_url": inspect_url
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def parse_preflight_output(self, output: str, img_name: str, tag: str, temp_log_file: str) -> tuple:
        """Parse preflight output and extract results."""
        results = []
        for line in output.splitlines():
            m1 = re.search(r'check=([^ ]+)', line)
            m2 = re.search(r'result=([^ ]+)', line)
            if m1 and m2:
                results.append(f"{img_name},{m1.group(1)},{m2.group(1)}")
        
        # Process results for CSV
        mod_files_map = {}
        mod_status = ""
        csv_rows = []
        
        for line in results:
            parts = line.split(",")
            if len(parts) < 3:
                continue
            
            image_name, test_case, status = parts[0], parts[1], parts[2]
            
            if test_case == "HasModifiedFiles" and status == "FAILED":
                try:
                    with open(temp_log_file, "r") as lf:
                        log_content = lf.read()
                    files = re.findall(r'file=([^ ]+)', log_content)
                    mod_files_map[test_case] = ":".join(files)
                except Exception as e:
                    self.log(f"Error reading temp log: {e}")
                mod_status = "FAILED"
        
        # Build CSV rows
        for line in results:
            parts = line.split(",")
            if len(parts) < 3:
                continue
            
            image_name, test_case, status = parts[0], parts[1], parts[2].replace("ERROR", "NOT_APP")
            mod_files = mod_files_map.get(test_case, "") if mod_status == "FAILED" else ""
            csv_rows.append([image_name, tag, mod_files, test_case, status])
        
        return results, csv_rows

    def format_scan_output(self, results: List[str], img_name: str, repo_img_tag: str, verdict: str, elapsed: float) -> str:
        """Format the scan output for console display."""
        output = f"\nScanning image: {repo_img_tag}\n{'='*80}\n"
        output += f"{'Image Name':<36} {'Test Case':<26} {'Status':<10}\n"
        output += "-" * 79 + "\n"
        
        for line in results:
            parts = line.split(",")
            if len(parts) < 3:
                continue
            
            image_name, test_case, status = parts[0], parts[1], parts[2]
            
            if status == "FAILED":
                output += f"{image_name:<30} {test_case:<32} \033[1;31m{status:<12}\033[m\n"
            elif status == "PASSED":
                output += f"{image_name:<30} {test_case:<32} \033[1;32m{status:<12}\033[m\n"
            else:
                output += f"{image_name:<30} {test_case:<32} \033[1;33m{'NOT_APP':<12}\033[m\n"
        
        # Format verdict
        if verdict == "PASSED":
            verdict_colored = f"\033[1;32m{verdict}\033[m"
        else:
            verdict_colored = f"\033[1;31m{verdict}\033[m"
        
        output += f"Verdict: {verdict_colored}\n"
        output += f"Time elapsed: {elapsed:.3f} seconds\n"
        
        return output

    def scan_single_image(self, image: str) -> Dict[str, Any]:
        """Scan a single container image using preflight."""
        start_time = time.time()
        
        # Create temporary log file
        with tempfile.NamedTemporaryFile(delete=False, mode="w+", suffix=".log") as tmp_log:
            temp_log_file = tmp_log.name
        
        # Set environment variables
        old_logfile = os.environ.get("PFLT_LOGFILE")
        os.environ["PFLT_LOGFILE"] = temp_log_file
        os.environ["PFLT_JUNIT"] = "true"
        os.environ["PFLT_LOGLEVEL"] = "debug"
        
        try:
            # Log scanning mode
            mode = "single" if self.parallel == 1 else "parallel"
            self.log(f"Scanning image: {image} in {mode} mode")
            
            # Get image details
            image_info = self.get_image_details(image)
            if not image_info["success"]:
                raise Exception(image_info["error"])
            
            # Run preflight scan
            preflight_cmd = [
                "preflight", "check", "container", "--platform", "amd64", 
                image_info["inspect_url"]
            ]
            if self.auth_json:
                preflight_cmd.extend(["-d", self.auth_json])
            
            proc = subprocess.run(preflight_cmd, capture_output=True, text=True)
            exit_status = proc.returncode
            combined_output = proc.stdout + proc.stderr
            
            if self.debug:
                print(combined_output)
            
            # Wait for log file to be updated
            time.sleep(0.2)
            
            # Parse results
            results, csv_rows = self.parse_preflight_output(
                combined_output, 
                image_info["img_name"], 
                image_info["tag"], 
                temp_log_file
            )
            
            # Get verdict
            verdict = "NOT_APP"
            try:
                with open(temp_log_file, "r") as lf:
                    log_content = lf.read()
                m_verdict = re.search(r'result:\s*(PASSED|FAILED|NOT_APP)', log_content)
                if m_verdict:
                    verdict = m_verdict.group(1).strip()
            except Exception as e:
                self.log(f"Error reading temporary log: {e}")
            
            if not verdict or verdict == "NOT_APP":
                m_verdict = re.search(r'Preflight result:\s*(PASSED|FAILED|NOT_APP)', combined_output)
                if m_verdict:
                    verdict = m_verdict.group(1).strip()
            
            # Format output
            elapsed = time.time() - start_time
            output = self.format_scan_output(
                results, 
                image_info["img_name"], 
                image_info["repo_img_tag"], 
                verdict, 
                elapsed
            )
            
            return {
                "error": exit_status != 0,
                "csv_rows": csv_rows,
                "elapsed": elapsed,
                "console_output": output,
                "image": image
            }
            
        except Exception as e:
            err_msg = f"Error scanning {image}: {e}"
            self.log(err_msg)
            return {
                "error": True,
                "csv_rows": [],
                "elapsed": time.time() - start_time,
                "console_output": err_msg,
                "image": image
            }
        finally:
            # Cleanup
            if os.path.exists(temp_log_file):
                os.remove(temp_log_file)
            
            # Restore environment
            if old_logfile is not None:
                os.environ["PFLT_LOGFILE"] = old_logfile
            else:
                os.environ.pop("PFLT_LOGFILE", None)

    def scan_images_in_parallel(self) -> bool:
        """Scan multiple images in parallel using ThreadPoolExecutor."""
        total_start = time.time()
        all_scan_data = []
        combined_output = ""
        error_occurred = False
        count = 0

        with ThreadPoolExecutor(max_workers=self.parallel) as executor:
            future_to_image = {
                executor.submit(self.scan_single_image, image): image 
                for image in self.image_list
            }
            
            for future in as_completed(future_to_image):
                result = future.result()
                combined_output += result["console_output"]
                if result["error"]:
                    error_occurred = True
                all_scan_data.extend(result["csv_rows"])
                count += 1

        # Calculate total time
        total_elapsed = time.time() - total_start
        
        # Add summary
        combined_output += "-" * 78 + "\n"
        combined_output += f"Total Images Scanned: {count}\n"
        combined_output += f"Total Scan Time: {time.strftime('%Hh:%Mm:%Ss', time.gmtime(total_elapsed))}\n"
        combined_output += "-" * 78 + "\n"

        # Write results directly to XLSX
        if all_scan_data:
            self.write_results_to_xlsx(all_scan_data)
        
        print(combined_output)
        return not error_occurred

    def run_prerequisite_checks(self) -> None:
        """Run all prerequisite checks."""
        print("\nChecking pre-requisite steps...")
        print("=" * 56)
        print(f"{'Pre-Requisites':<46} {'Status':<10}")
        print("-" * 57)
        
        self.check_required_tools()
        self.check_python_version()
        self.check_preflight_version()
        
        if self.fqdn:
            self.check_registry_connection()
        
        if self.api_token:
            self.check_registry_authentication()
        
        self.check_python_dependencies()
        print("=" * 55)

    def run(self) -> None:
        """Main execution method."""
        self.run_prerequisite_checks()
        self.build_image_list()
        
        # Backup existing results
        if self.file_exists(self.RESULT_XLSX):
            self.rename_file(self.RESULT_XLSX, self.RESULT_XLSX + "_saved")
        
        # Scan images and write directly to Excel
        if not self.scan_images_in_parallel():
            self.exit_with_error("Container image scanning failed.")

def main():
    """Main entry point."""
    scanner = PreflightScanner()
    scanner.run()

if __name__ == "__main__":
    main()
