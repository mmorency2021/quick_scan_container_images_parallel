#!/usr/bin/env python3
"""
A Python script implementation of a container image scanning tool that supports
parallel preflight scans and converts CSV results to an XLSX file.
It supports both API‐based mode (using an API token) and offline mode (using an image list file).

Usage Examples:

API-based:
  ./quick_scan_container_images_parallel.py --repo-namespace avareg_5gc --cnf-prefix "global-|specific" \
      --auth-json auth.json --api-token xxxxxx --fqdn quay.io --tag-type name --filter "existed_image|tested_image" --parallel 2

Offline:
  ./quick_scan_container_images_parallel.py --image-file image_list.txt --auth-json auth.json --fqdn quay.io --parallel 2
  ./quick_scan_container_images_parallel.py --image-file image_list.txt --fqdn quay.io
  ./quick_scan_container_images_parallel.py --image-file image_list.txt --fqdn quay.io --parallel 2
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

import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import PatternFill, Font, Alignment

# ------------------------------------------------------------------------------
# CSV-to-XLSX conversion function
# ------------------------------------------------------------------------------

def convert_and_format_csv_to_xlsx(input_csv: str, output_xlsx: str):
    """
    Reads the CSV file, sorts it by 'Status' and 'Test Case' (with custom order),
    formats the worksheet, and saves the result as an Excel workbook.
    """
    df = pd.read_csv(input_csv)
    df = df.sort_values(
        by=['Status', 'Test Case'],
        key=lambda x: x.map({'FAILED': 0, 'NOT_APP': 1, 'PASSED': 2})
    )
    wb = Workbook()
    ws = wb.active

    # Set column widths
    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 40
    ws.column_dimensions['D'].width = 30
    ws.column_dimensions['E'].width = 20

    for row in dataframe_to_rows(df, index=False, header=True):
        ws.append(row)

    # Enable text wrap for column C
    for cell in ws['C']:
        cell.alignment = Alignment(wrap_text=True)

    # Format the Status column (assumed to be column E)
    for row in ws.iter_rows(min_row=2, min_col=5, max_col=5):
        for cell in row:
            if cell.value == 'PASSED':
                cell.font = Font(color='006400')  # Dark green
            elif cell.value == 'FAILED':
                cell.font = Font(color='FF0000')  # Red
            elif cell.value == 'NOT_APP':
                cell.font = Font(color='FFA500')  # Dark orange

    # Set alignment: center for "Status" and "Image Tag", left for others
    for col in ws.columns:
        if col[0].value in ['Status', 'Image Tag']:
            for cell in col:
                cell.alignment = Alignment(horizontal='center', vertical='center')
        else:
            for cell in col:
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
    RESULT_CSV = "preflight_image_scan_result.csv"

    def __init__(self):
        self.args = self.parse_args()
        self.api_token = self.args.api_token
        self.repo_namespace = self.args.repo_namespace
        self.cnf_prefix = self.args.cnf_prefix
        self.tag_type = self.args.tag_type if self.args.tag_type else "name"
        self.auth_json = self.args.auth_json
        self.fqdn = self.args.fqdn
        self.filter = self.args.filter if self.args.filter else "chartrepo"
        self.image_file = self.args.image_file
        self.parallel = self.args.parallel
        self.image_list = []

    def parse_args(self):
        parser = argparse.ArgumentParser(
            description="""Scan container images using preflight in parallel and convert CSV to XLSX.

Usage Examples:

API-based:
  ./quick_scan_container_images_parallel.py --repo-namespace avareg_5gc --cnf-prefix "global-|specific" \\
      --auth-json auth.json --api-token xxxxxx --fqdn quay.io --tag-type name --filter "existed_image|tested_image" --parallel 2

Offline:
  ./quick_scan_container_images_parallel.py --image-file image_list.txt --auth-json auth.json --fqdn quay.io --parallel 2
  ./quick_scan_container_images_parallel.py --image-file image_list.txt --fqdn quay.io
  ./quick_scan_container_images_parallel.py --image-file image_list.txt --fqdn quay.io --parallel 2
""",
            formatter_class=argparse.RawTextHelpFormatter)
        # API-based arguments
        parser.add_argument("--repo-namespace", "-rn", help="Repository namespace (e.g., 'avareg_5gc' or 'avu0').")
        parser.add_argument("--cnf-prefix", "-cp", help="CNF image prefix to search for (e.g., 'global-' or 'global|non-global').")
        parser.add_argument("--tag-type", "-t", help="Image tag type: 'name' (default) or 'digest'.")
        parser.add_argument("--api-token", "-at", help="API token (Bearer Token) for registry access.")
        parser.add_argument("--auth-json", "-d", help="Path to Docker authentication JSON file (if required).")
        # Offline argument
        parser.add_argument("--image-file", "-img", help="Text file with a list of images (one per line).")
        # Common arguments
        parser.add_argument("--fqdn", "-fq", required=True, help="Fully-qualified domain name of your registry (e.g., 'quay.io').")
        parser.add_argument("--filter", "-ft", help="Filter to exclude images (e.g., 'existed_image|tested_image').")
        # Parallel scanning option
        parser.add_argument("--parallel", "-p", type=int, default=1, help="Number of images to scan in parallel (default: 1).")
        return parser.parse_args()

    def log(self, message):
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H:%M:%S")
        print(f"{timestamp} {message}")

    def exit_with_error(self, message):
        self.log(message)
        sys.exit(1)

    @staticmethod
    def file_exists(filepath):
        return os.path.exists(filepath)

    def rename_file(self, old_name, new_name):
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

    def check_required_tools(self):
        if shutil.which("python3") and shutil.which("preflight"):
            print("{:<48} \033[1;32m{:<24}\033[m".format("python3 and preflight installed", "OK"))
        else:
            print("{:<48} \033[1;31m{:<24}\033[m".format("python3 and preflight installed", "NOK"))
            sys.exit(1)
        if shutil.which("bc"):
            print("{:<48} \033[1;32m{:<24}\033[m".format("bc utility installed", "OK"))
        else:
            print("{:<48} \033[1;31m{:<24}\033[m".format("bc utility installed", "NOK"))
            sys.exit(1)

    @staticmethod
    def version_tuple(version_str):
        return tuple(map(int, version_str.split(".")))

    def check_preflight_version(self):
        MIN_VERSION = "1.6.11"
        try:
            result = subprocess.run(["preflight", "--version"], capture_output=True, text=True, check=True)
            match = re.search(r'(\d+\.\d+\.\d+)', result.stdout)
            if match:
                current_version = match.group(1)
                if self.version_tuple(current_version) < self.version_tuple(MIN_VERSION):
                    print("{:<48} \033[1;31m{:<24}\033[m".format("Preflight version (>=1.6.11)", "NOK"))
                    sys.exit(1)
                else:
                    print("{:<48} \033[1;32m{:<24}\033[m".format("Preflight version (>=1.6.11)", "OK"))
            else:
                self.log("Could not determine preflight version.")
                sys.exit(1)
        except subprocess.CalledProcessError as e:
            self.log("Error checking preflight version: " + str(e))
            sys.exit(1)

    def check_python_dependencies(self):
        try:
            import pandas  # noqa: F401
            import openpyxl  # noqa: F401
            print("{:<48} \033[1;32m{:<24}\033[m".format("Python Pandas and Openpyxl installed", "OK"))
        except ImportError as e:
            missing = str(e).split("No module named")[-1].strip(" '")
            print("{:<48} \033[1;31m{:<24}\033[m".format(f"Python {missing}", "NOK"))
            sys.exit(1)

    def check_registry_connection(self):
        if shutil.which("nc"):
            try:
                subprocess.run(["nc", "-zv4", self.fqdn, "80"], capture_output=True, text=True, check=True)
                print("{:<48} \033[1;32m{:<24}\033[m".format(f"{self.fqdn} connection", "OK"))
            except subprocess.CalledProcessError:
                print("{:<48} \033[1;31m{:<24}\033[m".format(f"{self.fqdn} connection", "NOK"))
                sys.exit(1)
        else:
            print("{:<48} \033[1;33m{:<24}\033[m".format(f"{self.fqdn} connection", "SKIPPED"))

    def check_registry_authentication(self):
        url = f"https://{self.fqdn}/api/v1/repository?namespace={self.repo_namespace}"
        try:
            result = subprocess.run(
                ["curl", "-I", "--silent", "-o", "/dev/null", "-w", "%{http_code}", "-X", "GET",
                 "-H", f"Authorization: Bearer {self.api_token}", url],
                capture_output=True, text=True, check=True)
            if result.stdout.strip() == "200":
                print("{:<48} \033[1;32m{:<24}\033[m".format("Registry auth (Bearer Token)", "OK"))
            else:
                print("{:<48} \033[1;31m{:<24}\033[m".format("Registry auth (Bearer Token)", "NOK"))
                sys.exit(1)
        except subprocess.CalledProcessError as e:
            self.log("Error checking registry authentication: " + str(e))
            sys.exit(1)

    def ensure_trailing_newline(self, filepath):
        try:
            with open(filepath, "rb+") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.write(b"\n")
        except Exception as e:
            self.log(f"Error ensuring trailing newline in {filepath}: {e}")

    def build_image_list(self):
        if not self.api_token:
            self.ensure_trailing_newline(self.image_file)
            with open(self.image_file, "r") as f:
                self.image_list = [line.strip() for line in f if line.strip()]
        else:
            default_images = ['ava-core/univ-nf-ava', 'ava-core/univ-nf-alex']
            if not self.cnf_prefix:
                self.image_list = default_images
            else:
                try:
                    api_url = f"https://{self.fqdn}/api/v1/repository?namespace={self.repo_namespace}"
                    proc = subprocess.run(
                        ["curl", "--silent", "-X", "GET", "-H", f"Authorization: Bearer {self.api_token}", api_url],
                        capture_output=True, text=True, check=True)
                    data = json.loads(proc.stdout)
                    filtered_list = []
                    for repo in data.get("repositories", []):
                        name = repo.get("name", "")
                        if self.cnf_prefix in name and self.filter not in name:
                            filtered_list.append(name)
                    self.image_list = filtered_list + default_images
                except Exception as e:
                    self.log(f"Error fetching repository list: {e}")
                    sys.exit(1)
        if not self.image_list:
            self.log("No images found. Check the API response or the image list file!")
            sys.exit(1)

    def convert_csv_to_xlsx(self):
        if not self.file_exists(self.RESULT_CSV):
            self.log(f"Input CSV {self.RESULT_CSV} does not exist!")
            sys.exit(1)
        try:
            convert_and_format_csv_to_xlsx(self.RESULT_CSV, "images_scan_results.xlsx")
            self.log(f"Converted {self.RESULT_CSV} to images_scan_results.xlsx successfully!")
        except Exception as e:
            self.log(f"Failed to convert CSV to XLSX: {e}")
            sys.exit(1)

    def scan_single_image(self, image):
        start_time = time.time()
        with tempfile.NamedTemporaryFile(delete=False, mode="w+", suffix=".log") as tmp_log:
            temp_log_file = tmp_log.name
        old_logfile = os.environ.get("PFLT_LOGFILE")
        os.environ["PFLT_LOGFILE"] = temp_log_file
        os.environ["PFLT_JUNIT"] = "true"
        os.environ["PFLT_LOGLEVEL"] = "debug"
        self.log(f"Scanning image: {image} in parallel")
        try:
            if not self.api_token:
                image_details = image.strip()
                parts = image_details.split("/", 1)
                repo_img_tag = parts[1] if len(parts) > 1 else image_details
                img_name = repo_img_tag.split("/")[-1].split(":")[0]
                inspect_url = image_details
                tag = image_details.split(":")[1] if ":" in image_details else ""
            else:
                image_url = f"https://{self.fqdn}/api/v1/repository/{self.repo_namespace}/{image.strip()}"
                proc = subprocess.run(
                    ["curl", "--silent", "-X", "GET", "-H", f"Authorization: Bearer {self.api_token}", image_url],
                    capture_output=True, text=True, check=True)
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
        except Exception as e:
            err_msg = f"Error fetching image details for {image}: {e}"
            self.log(err_msg)
            os.remove(temp_log_file)
            if old_logfile is not None:
                os.environ["PFLT_LOGFILE"] = old_logfile
            else:
                os.environ.pop("PFLT_LOGFILE", None)
            return {"error": True, "csv_rows": [], "elapsed": time.time() - start_time,
                    "console_output": err_msg, "image": image}

        output = f"\nScanning image: {repo_img_tag}\n{'='*80}\n"
        preflight_cmd = ["preflight", "check", "container", "--platform", "amd64", inspect_url]
        if self.auth_json:
            preflight_cmd.extend(["-d", self.auth_json])
        try:
            proc = subprocess.run(preflight_cmd, capture_output=True, text=True)
            exit_status = proc.returncode
            combined_output = proc.stdout + proc.stderr

            # Wait briefly for the log file to be updated
            time.sleep(0.2)

            results = []
            for line in combined_output.splitlines():
                m1 = re.search(r'check=([^ ]+)', line)
                m2 = re.search(r'result=([^ ]+)', line)
                if m1 and m2:
                    results.append(f"{img_name},{m1.group(1)},{m2.group(1)}")
            scan_failed = exit_status != 0
            if scan_failed:
                err_msg = f"Preflight scan failed for {inspect_url}"
                self.log(err_msg)
            output += "{:<36} {:<26} {:<10}\n".format("Image Name", "Test Case", "Status")
            output += "-------------------------------------------------------------------------------\n"
            mod_files_map = {}
            mod_status = ""
            csv_rows = []
            for line in results:
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                image_name, test_case, status = parts[0], parts[1], parts[2]
                mod_files = ""
                if mod_status == "FAILED":
                    mod_files = mod_files_map.get(test_case, "")
                if test_case != "HasModifiedFiles":
                    mod_files = ""
                if status == "FAILED":
                    output += "{:<30} {:<32} \033[1;31m{:<12}\033[m\n".format(image_name, test_case, status)
                elif status == "PASSED":
                    output += "{:<30} {:<32} \033[1;32m{:<12}\033[m\n".format(image_name, test_case, status)
                else:
                    output += "{:<20} {:<32} \033[1;33m{:<12}\033[m\n".format(image_name, test_case, "NOT_APP")
                if test_case == "HasModifiedFiles" and status == "FAILED":
                    try:
                        with open(temp_log_file, "r") as lf:
                            log_content = lf.read()
                        files = re.findall(r'file=([^ ]+)', log_content)
                        mod_files_map[test_case] = ":".join(files)
                    except Exception as e:
                        self.log(f"Error reading temp log for {inspect_url}: {e}")
                    mod_status = "FAILED"
            for line in results:
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                image_name, test_case, status = parts[0], parts[1], parts[2].replace("ERROR", "NOT_APP")
                mod_files = mod_files_map.get(test_case, "") if mod_status == "FAILED" else ""
                csv_rows.append([image_name, tag, mod_files, test_case, status])
            try:
                with open(temp_log_file, "r") as lf:
                    log_content = lf.read()
                m_verdict = re.search(r'result:\s*(PASSED|FAILED|NOT_APP)', log_content)
                verdict = m_verdict.group(1).strip() if m_verdict else ""
            except Exception as e:
                self.log(f"Error reading temporary log: {e}")
                verdict = ""
            if not verdict:
                m_verdict = re.search(r'Preflight result:\s*(PASSED|FAILED|NOT_APP)', combined_output)
                verdict = m_verdict.group(1).strip() if m_verdict else "NOT_APP"
            if verdict == "PASSED":
                verdict_colored = f"\033[1;32m{verdict}\033[m"
            else:
                verdict_colored = f"\033[1;31m{verdict}\033[m"
            output += f"Verdict: {verdict_colored}\n"
            open(temp_log_file, "w").close()
            os.remove(temp_log_file)
            if old_logfile is not None:
                os.environ["PFLT_LOGFILE"] = old_logfile
            else:
                os.environ.pop("PFLT_LOGFILE", None)
            elapsed = time.time() - start_time
            output += f"Time elapsed: {elapsed:.3f} seconds\n"
            return {"error": scan_failed, "csv_rows": csv_rows, "elapsed": elapsed,
                    "console_output": output, "image": image}
        except Exception as e:
            err_msg = f"Error running preflight for {inspect_url}: {e}"
            self.log(err_msg)
            os.remove(temp_log_file)
            if old_logfile is not None:
                os.environ["PFLT_LOGFILE"] = old_logfile
            else:
                os.environ.pop("PFLT_LOGFILE", None)
            return {"error": True, "csv_rows": [], "elapsed": time.time() - start_time,
                    "console_output": err_msg, "image": image}

    def scan_images_in_parallel(self):
        total_start = time.time()
        all_csv_rows = []
        combined_output = ""
        error_occurred = False
        count = 0

        with ThreadPoolExecutor(max_workers=self.parallel) as executor:
            future_to_image = {executor.submit(self.scan_single_image, image): image for image in self.image_list}
            for future in as_completed(future_to_image):
                result = future.result()
                combined_output += result["console_output"]
                if result["error"]:
                    error_occurred = True
                all_csv_rows.extend(result["csv_rows"])
                count += 1

        total_elapsed = time.time() - total_start
        combined_output += "------------------------------------------------------------------------------\n"
        combined_output += f"Total Images Scanned: {count}\n"
        combined_output += f"Total Scan Time: {time.strftime('%Hh:%Mm:%Ss', time.gmtime(total_elapsed))}\n"
        combined_output += "------------------------------------------------------------------------------\n"

        with open(self.RESULT_CSV, "w", newline="") as csvfile:
            csvfile.write("Image Name,Image Tag,Has Modified Files,Test Case,Status\n")
            csv_writer = csv.writer(csvfile)
            for row in all_csv_rows:
                csv_writer.writerow(row)
        print(combined_output)
        return not error_occurred

    def run(self):
        print("\nChecking pre-requisite steps...")
        print("========================================================")
        print("{:<46} {:<10}".format("Pre-Requisites", "Status"))
        print("---------------------------------------------------------")
        self.check_required_tools()
        self.check_preflight_version()
        self.check_registry_connection()
        if self.api_token:
            self.check_registry_authentication()
        self.check_python_dependencies()
        print("=======================================================")
        self.build_image_list()
        if self.file_exists(self.RESULT_CSV):
            self.rename_file(self.RESULT_CSV, self.RESULT_CSV + "_saved")
        if self.scan_images_in_parallel():
            self.convert_csv_to_xlsx()
        else:
            self.log("Container image scanning failed; skipping CSV conversion.")
            sys.exit(1)

def main():
    scanner = PreflightScanner()
    scanner.run()

if __name__ == "__main__":
    main()