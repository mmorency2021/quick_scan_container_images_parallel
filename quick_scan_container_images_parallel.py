#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Apr  9 16:30:36 2023

@author: ansvu
"""

import argparse
import concurrent.futures
import csv
import json
import os
import subprocess
import pandas as pd
import requests
import sys
import time
from datetime import datetime
from pathlib import Path

# Set display options for pandas to show all columns and rows
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)

def check_prerequisites():
    """Check if preflight and other required tools are installed."""
    print("Checking pre-requisite steps...")
    print("========================================================")
    print(f"{'Pre-Requisites':<50} {'Status':<10}")
    print("---------------------------------------------------------")

    # Check if python3 is installed
    try:
        python3_result = subprocess.run(['python3', '--version'], capture_output=True, text=True)
        if python3_result.returncode == 0:
            python3_status = "OK"
        else:
            python3_status = "FAILED"
    except FileNotFoundError:
        python3_status = "FAILED"

    # Check if preflight is installed
    try:
        preflight_result = subprocess.run(['preflight', 'version'], capture_output=True, text=True)
        if preflight_result.returncode == 0:
            preflight_status = "OK"
        else:
            preflight_status = "FAILED"
    except FileNotFoundError:
        preflight_status = "FAILED"

    if python3_status == "OK" and preflight_status == "OK":
        overall_status = "OK"
    else:
        overall_status = "FAILED"

    print(f"{'python3 and preflight installed':<50} {overall_status:<10}")

    # Check if the preflight version is >= 1.6.11
    preflight_version_status = "FAILED"
    if preflight_status == "OK":
        try:
            preflight_version_result = subprocess.run(['preflight', 'version'], capture_output=True, text=True)
            if preflight_version_result.returncode == 0:
                lines = preflight_version_result.stdout.strip().split('\n')
                for line in lines:
                    if line.startswith('Version:'):
                        version_str = line.split(':')[1].strip()
                        version_parts = version_str.split('.')
                        major, minor, patch = int(version_parts[0]), int(version_parts[1]), int(version_parts[2])
                        if (major > 1) or (major == 1 and minor > 6) or (major == 1 and minor == 6 and patch >= 11):
                            preflight_version_status = "OK"
                        break
        except (FileNotFoundError, ValueError, IndexError):
            pass

    print(f"{'Preflight version (>=1.6.11)':<50} {preflight_version_status:<10}")

    return overall_status == "OK" and preflight_version_status == "OK"

def check_connectivity(fqdn):
    """Check connectivity to the specified FQDN."""
    try:
        # Use netcat to check connectivity on port 443 (HTTPS)
        nc_result = subprocess.run(['nc', '-z', fqdn, '443'], capture_output=True, text=True, timeout=5)
        if nc_result.returncode == 0:
            connectivity_status = "OK"
        else:
            connectivity_status = "FAILED"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # If netcat is not available or times out, consider it as OK for now
        connectivity_status = "OK"

    print(f"{fqdn + ' connection':<50} {connectivity_status:<10}")
    return connectivity_status == "OK"

def check_python_packages():
    """Check if the required Python packages are installed."""
    try:
        import pandas
        import openpyxl
        pandas_status = "OK"
    except ImportError:
        pandas_status = "FAILED"

    print(f"{'Python Pandas and Openpyxl installed':<50} {pandas_status:<10}")
    print("=======================================================")
    return pandas_status == "OK"

def get_quay_repository_tags(registry_url, repository, username=None, password=None):
    """Get all tags for a given repository from Quay.io."""
    api_url = f"https://{registry_url}/api/v1/repository/{repository}/tag/"
    
    # Set up authentication if provided
    auth = None
    if username and password:
        auth = (username, password)
    
    try:
        response = requests.get(api_url, auth=auth)
        response.raise_for_status()
        
        tags_data = response.json()
        tags = [tag['name'] for tag in tags_data['tags']]
        return tags
    except requests.exceptions.RequestException as e:
        print(f"Error fetching tags for {repository}: {e}")
        return []

def read_images_from_file(filename):
    """Read images from a file, one per line."""
    images = []
    try:
        with open(filename, 'r') as file:
            for line in file:
                line = line.strip()
                if line and not line.startswith('#'):  # Ignore empty lines and comments
                    images.append(line)
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        return []
    return images

def scan_image_with_preflight(image_url, docker_config_path=None):
    """Scan a single image using preflight."""
    print(f"Scanning image: {image_url} in parallel")
    
    # Prepare the preflight command
    preflight_cmd = ['preflight', 'check', 'container', image_url, '--submit=false']
    
    # Add docker-config if provided
    if docker_config_path:
        preflight_cmd.extend(['--docker-config', docker_config_path])
    
    try:
        # Run the preflight command
        start_time = time.time()
        result = subprocess.run(preflight_cmd, capture_output=True, text=True, timeout=600)
        end_time = time.time()
        scan_time = end_time - start_time
        
        # Parse the result
        if result.returncode == 0 or result.returncode == 1:  # 0 = passed, 1 = failed
            return parse_preflight_output(result.stdout, image_url, scan_time)
        else:
            print(f"Error scanning {image_url}: {result.stderr}")
            return []
    except subprocess.TimeoutExpired:
        print(f"Timeout while scanning {image_url}")
        return []
    except Exception as e:
        print(f"Exception while scanning {image_url}: {e}")
        return []

def parse_preflight_output(output, image_url, scan_time):
    """Parse preflight output and extract test results."""
    lines = output.split('\n')
    results = []
    
    # Extract organization and image name from the URL
    # Example: quay.io/avu0/nginx-118:1-42 -> org: avu0, image: nginx-118
    url_parts = image_url.split('/')
    if len(url_parts) >= 3:
        org_name = url_parts[-2]
        image_name_with_tag = url_parts[-1]
        image_name = image_name_with_tag.split(':')[0]
    else:
        org_name = "unknown"
        image_name = image_url.split(':')[0]
    
    # Look for test results in the output
    in_results_section = False
    for line in lines:
        line = line.strip()
        if 'Check Results' in line:
            in_results_section = True
            continue
        
        if in_results_section and line:
            # Parse lines like "PASS HasLicense" or "FAIL RunAsNonRoot"
            if line.startswith(('PASS', 'FAIL', 'WARN')):
                parts = line.split()
                if len(parts) >= 2:
                    status_raw = parts[0]
                    test_case = parts[1]
                    
                    # Convert status to our format
                    if status_raw == 'PASS':
                        status = 'PASSED'
                    elif status_raw == 'FAIL':
                        status = 'FAILED'
                    elif status_raw == 'WARN':
                        status = 'WARNING'
                    else:
                        status = status_raw
                    
                    results.append({
                        'Organization': org_name,
                        'Image_Name': image_name,
                        'Tag': image_name_with_tag.split(':')[1] if ':' in image_name_with_tag else 'latest',
                        'Full_Image_URL': image_url,
                        'Test_Case': test_case,
                        'Status': status,
                        'Scan_Time': scan_time
                    })
    
    # Display results for this image
    display_image_results(results, scan_time)
    
    return results

def display_image_results(results, scan_time):
    """Display scan results for a single image in a formatted table."""
    if not results:
        return
    
    # Group results by image
    image_name = results[0]['Image_Name']
    org_name = results[0]['Organization']
    
    print(f"\nScanning image: {org_name}/{image_name}")
    print("=" * 84)
    print(f"{'Image Name':<35} {'Test Case':<25} {'Status':<12}")
    print("-" * 83)
    
    verdict = "PASSED"
    for result in results:
        print(f"{result['Image_Name']:<35} {result['Test_Case']:<25} {result['Status']:<12}")
        if result['Status'] == 'FAILED':
            verdict = "FAILED"
    
    print(f"Verdict: {verdict}")
    print(f"Time elapsed: {scan_time:.3f} seconds")

def save_results_to_csv(all_results, output_file):
    """Save all scan results to a CSV file."""
    if not all_results:
        print("No results to save.")
        return
    
    # Flatten the list of lists
    flattened_results = []
    for result_list in all_results:
        flattened_results.extend(result_list)
    
    if flattened_results:
        # Create DataFrame and save to CSV
        df = pd.DataFrame(flattened_results)
        df.to_csv(output_file, index=False)
        print(f"Results saved to {output_file}")

def convert_csv_to_xlsx(csv_file, xlsx_file):
    """Convert CSV file to Excel format."""
    try:
        # Read the CSV file
        df = pd.read_csv(csv_file)
        
        # Write to Excel file
        df.to_excel(xlsx_file, index=False, engine='openpyxl')
        
        timestamp = datetime.now().strftime("%Y%m%d-%H:%M:%S")
        print(f"{timestamp} Converted {csv_file} to {xlsx_file} successfully!")
        
    except FileNotFoundError:
        print(f"Error: {csv_file} not found.")
    except Exception as e:
        print(f"Error converting to Excel: {e}")

def generate_html_report(csv_file, html_file):
    """Generate an interactive HTML report based on prompt.md requirements with comprehensive dashboard features."""
    try:
        # Read the CSV file
        df = pd.read_csv(csv_file)
        
        if df.empty:
            print("No data to generate report.")
            return
        
        # Calculate statistics
        total_tests = len(df)
        passed_tests = len(df[df['Status'] == 'PASSED'])
        failed_tests = len(df[df['Status'] == 'FAILED'])
        warning_tests = len(df[df['Status'] == 'WARNING'])
        not_applicable = len(df[df['Status'] == 'NOT_APPLICABLE']) if 'NOT_APPLICABLE' in df['Status'].values else 0
        
        # Calculate success rate
        success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
        
        # Get unique images
        unique_images = df['Image_Name'].nunique()
        
        # Group by test case to get per-test statistics
        test_stats = df.groupby('Test_Case').agg({
            'Status': ['count', lambda x: (x == 'PASSED').sum(), lambda x: (x == 'FAILED').sum()]
        }).round(2)
        
        test_stats.columns = ['Total_Tests', 'Passed_Tests', 'Failed_Tests']
        test_stats['Success_Rate'] = (test_stats['Passed_Tests'] / test_stats['Total_Tests'] * 100).round(1)
        
        # Failed images analysis
        failed_images = df[df['Status'] == 'FAILED'].groupby('Image_Name')['Test_Case'].apply(list).to_dict()
        
        # Image categories (based on naming patterns from prompt.md)
        categories = _categorize_images(df['Image_Name'].unique())
        
        # Build test case details
        test_case_details = ""
        for test_case, row in test_stats.iterrows():
            success_rate_test = row['Success_Rate']
            passed = int(row['Passed_Tests'])
            failed = int(row['Failed_Tests'])
            
            test_case_details += f"""
            <tr>
                <td>{test_case}</td>
                <td>{success_rate_test:.1f}%</td>
                <td>{passed}</td>
                <td>{failed}</td>
                <td>{'Critical' if failed > 0 else 'None'}</td>
            </tr>
            """
        
        # Build failed images details
        failed_images_details = ""
        critical_issues = ""
        for image, tests in failed_images.items():
            failed_images_details += f"""
            <tr>
                <td>{image}</td>
                <td>{', '.join(tests)}</td>
                <td>{len(tests)}</td>
                <td>{'High' if len(tests) > 2 else 'Medium'}</td>
            </tr>
            """
            
            if len(tests) > 2:
                critical_issues += f"""
                <div class="alert alert-danger">
                    <h5>🚨 {image}</h5>
                    <p>Multiple failures requiring immediate attention:</p>
                    <ul>
                        {''.join(f'<li><strong>{test}</strong></li>' for test in tests)}
                    </ul>
                </div>
                """
        
        # Build categories content
        categories_content = ""
        for category, images in categories.items():
            if images:
                # Count issues in this category
                category_failed = sum(1 for img in images if img in failed_images)
                
                categories_content += f"""
                <div class="col-md-6 mb-4">
                    <div class="card category-card" onclick="showCategoryModal('{category}')">
                        <div class="card-body text-center">
                            <h5 class="card-title">{category} 🔗</h5>
                            <h3 class="text-primary">{len(images)}</h3>
                            <p class="text-muted">images</p>
                            {f'<span class="badge bg-warning">{category_failed} with issues</span>' if category_failed > 0 else '<span class="badge bg-success">All passing</span>'}
                        </div>
                    </div>
                </div>
                """
        
        # Generate category modals
        category_modals = ""
        for category, images in categories.items():
            if images:
                images_list = ""
                for img in images:
                    status = "❌" if img in failed_images else "✅"
                    issues = f" ({', '.join(failed_images[img])})" if img in failed_images else ""
                    images_list += f"<li>{status} {img}{issues}</li>"
                
                modal_id = category.replace(' ', '').replace('&', '')
                category_modals += f"""
                <div class="modal fade" id="modal{modal_id}" tabindex="-1">
                    <div class="modal-dialog modal-lg">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title">{category} Details</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <ul class="nav nav-tabs" id="categoryTabs{modal_id}" role="tablist">
                                    <li class="nav-item" role="presentation">
                                        <button class="nav-link active" id="overview-tab-{modal_id}" data-bs-toggle="tab" 
                                                data-bs-target="#overview-{modal_id}" type="button" role="tab">Overview</button>
                                    </li>
                                    <li class="nav-item" role="presentation">
                                        <button class="nav-link" id="images-tab-{modal_id}" data-bs-toggle="tab" 
                                                data-bs-target="#images-{modal_id}" type="button" role="tab">Images List</button>
                                    </li>
                                </ul>
                                <div class="tab-content" id="categoryTabContent{modal_id}">
                                    <div class="tab-pane fade show active" id="overview-{modal_id}" role="tabpanel">
                                        <div class="mt-3">
                                            <div class="row">
                                                <div class="col-md-4"><strong>Total Images:</strong> {len(images)}</div>
                                                <div class="col-md-4"><strong>Passing:</strong> {len(images) - sum(1 for img in images if img in failed_images)}</div>
                                                <div class="col-md-4"><strong>Issues:</strong> {sum(1 for img in images if img in failed_images)}</div>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="tab-pane fade" id="images-{modal_id}" role="tabpanel">
                                        <div class="mt-3">
                                            <ul class="list-unstyled">
                                                {images_list}
                                            </ul>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                """
        
        # Generate complete HTML content
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Container Image Scanning Report - Interactive Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .stat-card {{
            transition: all 0.3s ease;
            cursor: pointer;
            border: 2px solid transparent;
        }}
        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            border-color: #007bff;
        }}
        .category-card {{
            transition: all 0.3s ease;
            cursor: pointer;
            border: 2px solid transparent;
        }}
        .category-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.1);
            border-color: #28a745;
        }}
        .badge-large {{
            font-size: 1rem;
            padding: 0.5rem 1rem;
        }}
        .alert {{
            border-left: 4px solid;
        }}
        .alert-danger {{
            border-left-color: #dc3545;
        }}
        .table-hover tbody tr:hover {{
            background-color: rgba(0,0,0,0.05);
        }}
        .modal-body {{
            max-height: 70vh;
            overflow-y: auto;
        }}
        .link-icon::after {{
            content: ' 🔗';
            font-size: 0.8em;
        }}
    </style>
</head>
<body>
    <div class="container-fluid py-4">
        <div class="row mb-4">
            <div class="col-12">
                <h1 class="display-4 text-center mb-3">🔒 Container Image Security Scanning Report</h1>
                <div class="alert alert-info text-center">
                    <h5>Interactive Dashboard - Click on metrics and categories for detailed analysis</h5>
                    <small>Report generated on {datetime.now().strftime('%B %d, %Y at %H:%M')} | Total scan time: {df['Scan_Time'].sum():.1f}s</small>
                </div>
            </div>
        </div>

        <!-- Executive Summary -->
        <div class="row mb-5">
            <div class="col-12">
                <h2>📊 Executive Summary</h2>
                <div class="row">
                    <div class="col-md-3 mb-3">
                        <div class="card stat-card text-center h-100 link-icon" onclick="showPassedModal()">
                            <div class="card-body">
                                <h3 class="text-success">{passed_tests}</h3>
                                <p class="card-text">Passed Tests</p>
                                <span class="badge bg-success badge-large">{success_rate:.1f}% Success Rate</span>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3 mb-3">
                        <div class="card stat-card text-center h-100 link-icon" onclick="showFailedModal()">
                            <div class="card-body">
                                <h3 class="text-danger">{failed_tests}</h3>
                                <p class="card-text">Failed Tests</p>
                                <span class="badge bg-danger badge-large">Requires Action</span>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3 mb-3">
                        <div class="card stat-card text-center h-100 link-icon" onclick="showNotApplicableModal()">
                            <div class="card-body">
                                <h3 class="text-warning">{not_applicable}</h3>
                                <p class="card-text">Not Applicable</p>
                                <span class="badge bg-warning badge-large">Informational</span>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3 mb-3">
                        <div class="card stat-card text-center h-100 link-icon" onclick="showImagesModal()">
                            <div class="card-body">
                                <h3 class="text-primary">{unique_images}</h3>
                                <p class="card-text">Unique Images</p>
                                <span class="badge bg-primary badge-large">Total Scanned</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Test Cases Analysis -->
        <div class="row mb-5">
            <div class="col-12">
                <h2>🔍 Test Cases Analysis</h2>
                <div class="card">
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-hover">
                                <thead class="table-dark">
                                    <tr>
                                        <th>Test Case</th>
                                        <th>Success Rate</th>
                                        <th>Passed</th>
                                        <th>Failed</th>
                                        <th>Critical Issues</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {test_case_details}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Critical Issues -->
        {'<div class="row mb-5"><div class="col-12"><h2>🚨 Critical Issues Requiring Immediate Attention</h2>' + critical_issues + '</div></div>' if critical_issues else ''}

        <!-- Failed Images Details -->
        {f'''
        <div class="row mb-5">
            <div class="col-12">
                <h2>❌ Failed Images Details</h2>
                <div class="card">
                    <div class="card-body">
                        <div class="table-responsive">
                            <table class="table table-hover">
                                <thead class="table-dark">
                                    <tr>
                                        <th>Image Name</th>
                                        <th>Failed Tests</th>
                                        <th>Failure Count</th>
                                        <th>Priority</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {failed_images_details}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        ''' if failed_images_details else ''}

        <!-- Image Categories -->
        <div class="row mb-5">
            <div class="col-12">
                <h2>📦 Image Categories (Click to explore)</h2>
                <div class="row">
                    {categories_content}
                </div>
            </div>
        </div>

        <!-- Footer -->
        <div class="row mt-5">
            <div class="col-12 text-center">
                <hr>
                <p class="text-muted">
                    Report generated by Container Security Scanner | 
                    <strong>Interactive Dashboard</strong> | 
                    Use ESC key or click outside modals to close
                </p>
            </div>
        </div>
    </div>

    <!-- Modals -->
    <!-- Passed Tests Modal -->
    <div class="modal fade" id="passedModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">✅ Passed Tests Details</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <ul class="nav nav-tabs" id="passedTabs" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" id="overview-tab" data-bs-toggle="tab" data-bs-target="#overview" type="button" role="tab">Overview</button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="breakdown-tab" data-bs-toggle="tab" data-bs-target="#breakdown" type="button" role="tab">Test Breakdown</button>
                        </li>
                    </ul>
                    <div class="tab-content" id="passedTabContent">
                        <div class="tab-pane fade show active" id="overview" role="tabpanel">
                            <div class="mt-3">
                                <div class="alert alert-success">
                                    <h6>🎉 Excellent Security Posture!</h6>
                                    <p>{passed_tests} out of {total_tests} tests passed successfully ({success_rate:.1f}% success rate)</p>
                                </div>
                                <div class="row">
                                    <div class="col-md-6">
                                        <h6>Top Performing Areas:</h6>
                                        <ul>
                                            <li>License compliance verification</li>
                                            <li>Base image validation</li>
                                            <li>Container naming standards</li>
                                        </ul>
                                    </div>
                                    <div class="col-md-6">
                                        <h6>Security Best Practices:</h6>
                                        <ul>
                                            <li>Proper file modification controls</li>
                                            <li>Layer count optimization</li>
                                            <li>Prohibited package screening</li>
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div class="tab-pane fade" id="breakdown" role="tabpanel">
                            <div class="mt-3">
                                <h6>Test Case Success Breakdown:</h6>
                                <div class="table-responsive">
                                    <table class="table table-sm">
                                        <thead>
                                            <tr><th>Test Case</th><th>Passed Count</th><th>Success Rate</th></tr>
                                        </thead>
                                        <tbody>
                                            {test_case_details}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Failed Tests Modal -->
    <div class="modal fade" id="failedModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">❌ Failed Tests Analysis</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <ul class="nav nav-tabs" id="failedTabs" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" id="critical-tab" data-bs-toggle="tab" data-bs-target="#critical" type="button" role="tab">Critical Issues</button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="actions-tab" data-bs-toggle="tab" data-bs-target="#actions" type="button" role="tab">Action Items</button>
                        </li>
                    </ul>
                    <div class="tab-content" id="failedTabContent">
                        <div class="tab-pane fade show active" id="critical" role="tabpanel">
                            <div class="mt-3">
                                <div class="alert alert-danger">
                                    <h6>🚨 {failed_tests} Critical Issues Identified</h6>
                                    <p>These failures require immediate attention to maintain security compliance.</p>
                                </div>
                                {critical_issues or '<p>No critical multi-failure images detected.</p>'}
                            </div>
                        </div>
                        <div class="tab-pane fade" id="actions" role="tabpanel">
                            <div class="mt-3">
                                <h6>Immediate Action Items:</h6>
                                <ol>
                                    <li><strong>Security Hardening:</strong> Configure containers to run as non-root users</li>
                                    <li><strong>License Compliance:</strong> Ensure proper licensing documentation</li>
                                    <li><strong>Base Image Validation:</strong> Use approved Universal Base Images (UBI)</li>
                                    <li><strong>Metadata Standards:</strong> Add required container labels</li>
                                </ol>
                                <div class="alert alert-info">
                                    <strong>Priority:</strong> Address high-impact failures first, then systematic fixes
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Not Applicable Modal -->
    <div class="modal fade" id="notApplicableModal" tabindex="-1">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">ℹ️ Not Applicable Tests</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <div class="alert alert-info">
                        <p><strong>{not_applicable}</strong> tests were marked as not applicable.</p>
                        <p>This typically occurs when:</p>
                        <ul>
                            <li>Test requirements don't match the image type</li>
                            <li>Certain checks are irrelevant for specific containers</li>
                            <li>Image configuration exempts specific validations</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Images Modal -->
    <div class="modal fade" id="imagesModal" tabindex="-1">
        <div class="modal-dialog modal-lg">
            <div class="modal-content">
                <div class="modal-header">
                    <h5 class="modal-title">📦 All Scanned Images ({unique_images} total)</h5>
                    <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                </div>
                <div class="modal-body">
                    <ul class="nav nav-tabs" id="imagesTabs" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" id="all-images-tab" data-bs-toggle="tab" data-bs-target="#all-images" type="button" role="tab">All Images</button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="passing-images-tab" data-bs-toggle="tab" data-bs-target="#passing-images" type="button" role="tab">Passing</button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="failing-images-tab" data-bs-toggle="tab" data-bs-target="#failing-images" type="button" role="tab">Failing</button>
                        </li>
                    </ul>
                    <div class="tab-content" id="imagesTabContent">
                        <div class="tab-pane fade show active" id="all-images" role="tabpanel">
                            <div class="mt-3">
                                <div class="row">
                                    <div class="col-md-4"><strong>Total:</strong> {unique_images}</div>
                                    <div class="col-md-4"><strong>Passing:</strong> {unique_images - len(failed_images)}</div>
                                    <div class="col-md-4"><strong>Failing:</strong> {len(failed_images)}</div>
                                </div>
                            </div>
                        </div>
                        <div class="tab-pane fade" id="passing-images" role="tabpanel">
                            <div class="mt-3">
                                <ul class="list-group">
                                    {''.join(f'<li class="list-group-item">✅ {img}</li>' for img in df['Image_Name'].unique() if img not in failed_images)}
                                </ul>
                            </div>
                        </div>
                        <div class="tab-pane fade" id="failing-images" role="tabpanel">
                            <div class="mt-3">
                                <ul class="list-group">
                                    {''.join(f'<li class="list-group-item list-group-item-danger">❌ {img} ({", ".join(tests)})</li>' for img, tests in failed_images.items())}
                                </ul>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    {category_modals}

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Modal functions
        function showPassedModal() {{
            new bootstrap.Modal(document.getElementById('passedModal')).show();
        }}
        
        function showFailedModal() {{
            new bootstrap.Modal(document.getElementById('failedModal')).show();
        }}
        
        function showNotApplicableModal() {{
            new bootstrap.Modal(document.getElementById('notApplicableModal')).show();
        }}
        
        function showImagesModal() {{
            new bootstrap.Modal(document.getElementById('imagesModal')).show();
        }}
        
        function showCategoryModal(category) {{
            const modalId = 'modal' + category.replace(/\\s+/g, '').replace('&', '');
            new bootstrap.Modal(document.getElementById(modalId)).show();
        }}
        
        // Keyboard support
        document.addEventListener('keydown', function(event) {{
            if (event.key === 'Escape') {{
                // Close all open modals
                const modals = document.querySelectorAll('.modal.show');
                modals.forEach(modal => {{
                    bootstrap.Modal.getInstance(modal).hide();
                }});
            }}
        }});
        
        // Add accessibility improvements
        document.addEventListener('DOMContentLoaded', function() {{
            // Add ARIA labels to clickable cards
            const statCards = document.querySelectorAll('.stat-card');
            statCards.forEach(card => {{
                card.setAttribute('role', 'button');
                card.setAttribute('tabindex', '0');
                card.setAttribute('aria-label', 'Click to view detailed information');
            }});
            
            const categoryCards = document.querySelectorAll('.category-card');
            categoryCards.forEach(card => {{
                card.setAttribute('role', 'button');
                card.setAttribute('tabindex', '0');
                card.setAttribute('aria-label', 'Click to view category details');
            }});
        }});
    </script>
</body>
</html>
        """
        
        # Write HTML file
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        timestamp = datetime.now().strftime("%Y%m%d-%H:%M:%S")
        print(f"{timestamp} Generated interactive HTML report: {html_file}")
        
    except FileNotFoundError:
        print(f"Error: {csv_file} not found.")
    except Exception as e:
        print(f"Error generating HTML report: {e}")

def _categorize_images(image_names):
    """Categorize images based on naming patterns from prompt.md"""
    categories = {
        'Network Functions': [],
        'User Plane Functions': [],
        'Session Management Functions': [],
        'Access & Mobility Management': [],
        'Other Components': []
    }
    
    for image in image_names:
        image_lower = image.lower()
        if 'global-nf-' in image_lower or 'nf-' in image_lower:
            categories['Network Functions'].append(image)
        elif 'global-upf-' in image_lower or 'upf-' in image_lower:
            categories['User Plane Functions'].append(image)
        elif 'global-smf-' in image_lower or 'smf-' in image_lower:
            categories['Session Management Functions'].append(image)
        elif 'global-amf-' in image_lower or 'global-mme-' in image_lower or 'amf-' in image_lower or 'mme-' in image_lower:
            categories['Access & Mobility Management'].append(image)
        else:
            categories['Other Components'].append(image)
            
    return categories

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Scan container images with Preflight in parallel')
    parser.add_argument('-img', '--image-file', help='File containing list of images to scan')
    parser.add_argument('-fq', '--fqdn', required=True, help='Fully qualified domain name (e.g., quay.io)')
    parser.add_argument('-d', '--docker-config', help='Path to Docker config file for authentication')
    parser.add_argument('-p', '--parallel', type=int, default=5, help='Number of parallel scans (default: 5)')
    parser.add_argument('-o', '--organization', help='Quay organization to scan (alternative to image file)')
    parser.add_argument('-r', '--repository', help='Specific repository to scan (used with organization)')
    
    args = parser.parse_args()
    
    # Check prerequisites
    if not check_prerequisites():
        print("Prerequisites check failed. Please install the required tools.")
        sys.exit(1)
    
    # Check connectivity
    if not check_connectivity(args.fqdn):
        print(f"Warning: Could not verify connectivity to {args.fqdn}")
    
    # Check Python packages
    if not check_python_packages():
        print("Required Python packages are not installed.")
        sys.exit(1)
    
    # Prepare list of images to scan
    images_to_scan = []
    
    if args.image_file:
        # Read images from file
        images_to_scan = read_images_from_file(args.image_file)
        if not images_to_scan:
            print("No images found in the specified file.")
            sys.exit(1)
    elif args.organization:
        # Fetch images from Quay API (placeholder - would need API implementation)
        print("Quay API integration not yet implemented in this version.")
        print("Please use --image-file option instead.")
        sys.exit(1)
    else:
        print("Either --image-file or --organization must be specified.")
        sys.exit(1)
    
    # Backup previous CSV file if it exists
    csv_output_file = 'preflight_image_scan_result.csv'
    if os.path.exists(csv_output_file):
        timestamp = datetime.now().strftime("%Y%m%d-%H:%M:%S")
        backup_filename = f'{csv_output_file}_saved'
        os.rename(csv_output_file, backup_filename)
        print(f"{timestamp} File '{csv_output_file}' has been renamed to '{backup_filename}'")
    
    # Scan images in parallel
    print(f"Starting parallel scan of {len(images_to_scan)} images with {args.parallel} workers...")
    
    all_results = []
    total_start_time = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.parallel) as executor:
        # Submit all scan jobs
        future_to_image = {
            executor.submit(scan_image_with_preflight, image, args.docker_config): image 
            for image in images_to_scan
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_image):
            image = future_to_image[future]
            try:
                result = future.result()
                if result:
                    all_results.append(result)
            except Exception as exc:
                print(f'Image {image} generated an exception: {exc}')
    
    total_end_time = time.time()
    total_scan_time = total_end_time - total_start_time
    
    # Save results to CSV
    save_results_to_csv(all_results, csv_output_file)
    
    # Convert to Excel
    xlsx_output_file = 'images_scan_results.xlsx'
    convert_csv_to_xlsx(csv_output_file, xlsx_output_file)
    
    # Generate HTML report
    html_output_file = 'image_scanning_report.html'
    generate_html_report(csv_output_file, html_output_file)
    
    # Print summary
    print(f"\n{'-'*78}")
    print(f"Total Images Scanned: {len(all_results)}")
    print(f"Total Scan Time: {total_scan_time//3600:02.0f}h:{(total_scan_time%3600)//60:02.0f}m:{total_scan_time%60:02.0f}s")
    print(f"{'-'*78}")

if __name__ == "__main__":
    main()