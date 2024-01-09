# quick_scan_container_images_online_offline
This script is designed to streamline the Preflight scanning process for container images, whether Quay RESTAPI is utilized or not. Preflight scanning serves the purpose of assessing whether container images adhere to security best practices, specifically regarding CVE tests, without the need for submission to the Backend Catalog.

With the latest Preflight releases, the scanning capability has been enhanced to detect changes or removals of original UBI-based image files within multiple layers of Docker images. This scanning process serves as a preliminary check before submission to the backend, ensuring that all criteria are met.

The script produces test case results, which are initially displayed in the console and then exported to both CSV and XLS formats using a Python script.

## Pre-Requisites
- Clone this github repo then use the scripts  
- Login to Private Registry Server with `podman login -u xxx quay.io`
- To talk to Quay.io Or Private Registry via REST API, it requires oauth and bear token
- Push images to Quay Repository with specific Organization
- Python3 + Pandas and Openpyxl using `sudo pip3 install pandas openpyxl`   
  if `pip3` is not installed yet then `sudo dnf install python3-pip -y`
- netcat (nc) rpm installed if not there it will skip the connectivity checking
- Install preflight 
```shellSession
wget https://github.com/redhat-openshift-ecosystem/openshift-preflight/releases/download/1.8.0/preflight-linux-amd64
chmod +x preflight-linux-amd64
sudo mv preflight-linux-amd64 /usr/local/bin/preflight
```
- Without Quay RESTAPI Token 
if QUAY or private registry server not possible to use RESTAPI then comment out this parameter quay_oauth_api_key from shellscript  
```shellSession
#quay_oauth_api_key="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```
- Update auth.json path if XDG_RUNTIME_DIR Not used   
if not used XDG_RUNTIME_DIR then specify auth.json
```shellSession
auth_json_path="/home/myuser/auth.json"
```

## Quick Images Scan Shell Script Usage
```shellSession
$ bash quick_scan_container_images_online_offline.sh 
------------------------------------------------------------------------------------------------------------------------
Usage: quick_scan_container_images_online_offline.sh -rn|--repo-ns <org_name|user_name> -cp|--cnf-prefix <common_image_name> -t|--tag-type <name|digest> -tk|--api-token <xxxxxx> -fq|--fqdn <quay.io> -ft|--filter <filter_me>
Usage: quick_scan_container_images_online_offline.sh [-h | --help]
Usage Ex1: quick_scan_container_images_online_offline.sh -rn ava -cp "global-|specific" -tk xxxxxx -fq quay.io -t name -ft "existed_image|tested_image"
Usage Ex2: quick_scan_container_images_online_offline.sh --repo-ns avareg_5gc --cnf-prefix global- --tag-type name --fqdn quay.io
Usage Ex3: quick_scan_container_images_online_offline.sh --repo-ns avareg_5gc --cnf-prefix global- --api-token xxxxx --fqdn quay.io
Usage Ex4: quick_scan_container_images_online_offline.sh --repo-ns avareg_5gc --cnf-prefix global-

Note: tag-type and log-type can be excluded from argument
Note1: if quay_oauth_api_key and quay_registry_domain are defined on line #3&4 then use Ex4 to as usage


    -rn|--repo-ns        :  An organization or user name e.g avareg_5gc or avu0
    -cp|--cnf-prefix     :  Is CNF image prefix e.g. global-amf-rnic or using wildcard
                            It also uses more one prefix e.g. "global|non-global"

    -t|--tag-type        :  Image Tag Type whether it requires to use tag or digest name, preferred tag name
                            If name or digest argument is omitted it uses default tag name

    -fq|--fqdn           :  Private registry fqdn/host e.g quay.io

    -tk|--api-token      :  Bearer Token that created by Registry Server Admin from application->oauth-token
 
    -ft|--filter         :  If you want to exclude images or unwanted e.g. chartrepo or tested-images, then
                            pass to script argument like this:
                            quick_scan_container_images_online_offline.sh -rn ava -cp global- -t name -ft "existed_image|tested_image"
    
------------------------------------------------------------------------------------------------------------------------
```
## Quick Image Scan Shell Script Contents
```bash
#!/bin/bash

#if not used XDG_RUNTIME_DIR then specify auth.json
auth_json_path="${XDG_RUNTIME_DIR}/containers/auth.json"

#If QUAY or private registry server not possible to use RESTAPI then comment out this parameter quay_oauth_api_key
quay_oauth_api_key="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
quay_registry_domain="quay.ava.bos2.lab"
preflight_image_scan_result_csv="preflight_image_scan_result.csv"

print_help() {
    echo "------------------------------------------------------------------------------------------------------------------------"
    echo "Usage: $0 -rn|--repo-ns <org_name|user_name> -cp|--cnf-prefix <common_image_name> -t|--tag-type <name|digest> -tk|--api-token <xxxxxx> -fq|--fqdn <quay.io> -ft|--filter <filter_me>"
    echo "Usage: $0 [-h | --help]"
    echo "Usage Ex1: $0 -rn ava -cp \"global-|specific\" -tk xxxxxx -fq quay.io -t name -ft \"existed_image|tested_image\""
    echo "Usage Ex2: $0 --repo-ns avareg_5gc --cnf-prefix global- --tag-type name --fqdn quay.io"
    echo "Usage Ex3: $0 --repo-ns avareg_5gc --cnf-prefix global- --api-token xxxxx --fqdn quay.io"
    echo "Usage Ex4: $0 --repo-ns avareg_5gc --cnf-prefix global-"
    echo ""
    echo "Note: tag-type and log-type can be excluded from argument"
    echo "Note1: if quay_oauth_api_key and quay_registry_domain are defined on line #3&4 then use Ex4 to as usage"
    echo ""
    echo "
    -rn|--repo-ns        :  An organization or user name e.g avareg_5gc or avu0
    -cp|--cnf-prefix     :  Is CNF image prefix e.g. global-amf-rnic or using wildcard
                            It also uses more one prefix e.g. \"global|non-global\"

    -t|--tag-type        :  Image Tag Type whether it requires to use tag or digest name, preferred tag name
                            If name or digest argument is omitted it uses default tag name

    -fq|--fqdn           :  Private registry fqdn/host e.g quay.io

    -tk|--api-token      :  Bearer Token that created by Registry Server Admin from application->oauth-token
 
    -ft|--filter         :  If you want to exclude images or unwanted e.g. chartrepo or tested-images, then
                            pass to script argument like this:
                            $0 -rn ava -cp global- -t name -ft \"existed_image|tested_image\"
    "
    echo "------------------------------------------------------------------------------------------------------------------------"
    exit 0
}
for i in "$@"; do
    case $i in
    -rn | --repo-ns)
        if [ -n "$2" ]; then
            REPO_NS="$2"
            shift 2
            continue
        fi
        ;;
    -cp | --cnf-prefix)
        if [ -n "$2" ]; then
            CNF_PREFIX="$2"
            shift 2
            continue
        fi
        ;;
    -t | --tag-type)
        if [ -n "$2" ]; then
            TAG_TYPE="$2"
            shift 2
            continue
        fi
        ;;
    -fq | --fqdn)
        if [ -n "$2" ]; then
            FQDN="$2"
            shift 2
            continue
        fi
        ;;
    -tk | --api-token)
        if [ -n "$2" ]; then
            API_TOKEN="$2"
            shift 2
            continue
        fi
        ;;
    -ft | --filter)
        if [ -n "$2" ]; then
            FILTER="$2"
            shift 2
            continue
        fi
        ;;
    -h | -\? | --help)
        print_help
        shift #
        ;;
    *)
        # unknown option
        ;;
    esac
done
if [[ -z "$quay_oauth_api_key" ]]; then
      echo "quay_oauth_api_key is not defined then you are using image_list.txt file!!"
      # Skip all the checks below
else
    #Note: tag-type and log-type can be excluded from argument#
    if [[ "$REPO_NS" == "" || "$CNF_PREFIX" == "" ]]; then
        print_help
    fi

    if [[ "$TAG_TYPE" == "" ]]; then
        TAG_TYPE="name"
    fi

    #if filter arg is empty, then we will filter chartrepo
    if [[ "$FILTER" == "" ]]; then
        FILTER="chartrepo"
    fi

    if [[ "$FQDN" == "" ]]; then
        FQDN=$(echo $quay_registry_domain)
    fi

    echo "FQDN: $FQDN"

    if [[ "$API_TOKEN" == "" ]]; then
        API_TOKEN=$(echo ${quay_oauth_api_key})
    fi
fi

#check if requirement files are existed
file_exists() {
    [ -z "${1-}" ] && bye Usage: file_exists name.
    ls "$1" >/dev/null 2>&1
}
# Prints all parameters and exits with the error code.
bye() {
    log "$*"
    exit 1
}

# Prints all parameters to stdout, prepends with a timestamp.
log() {
    printf '%s %s\n' "$(date +"%Y%m%d-%H:%M:%S")" "$*"
}

rename_file() {
    # Check if the filename argument is provided
    if [ -z "$1" ]; then
        log "Usage: rename_file old_filename new_filename"
        return 1
    fi

    # Check if the file exists
    if [ ! -f "$1" ]; then
        log "Error: file '$1' does not exist" >/dev/null 2>&1
        return 1
    fi

    # Check if the new filename argument is provided
    if [ -z "$2" ]; then
        log "Usage: rename_file old_filename new_filename"
        return 1
    fi

    # Rename the file
    mv "$1" "$2"
    log "File '$1' has been renamed to '$2'" >/dev/null 2>&1
    return 0
}

check_tools() {
    if file_exists "$(which python3)" && file_exists "$(which preflight)"; then
        #log "python3 and preflight are installed"
        printf "%-48s \e[1;32m%-24s\e[m\n" "python3 and preflight installed" "OK"
    else
        #bye "python3 and/or preflight are not installed"
        printf "%-48s \e[1;31m%-24s\e[m\n" "python3 and preflight installed" "NOK"
        exit 1
    fi
    file_exists "preflight_scan_csv_to_xlsx_v3.py" || bye "preflight_scan_csv_to_xlsx_v3.py: No such file."
}

check_preflight_version() {
    # Set the minimum Preflight version required
    MIN_PREFLIGHT_VERSION="1.6.11"

    # Check if Preflight is installed and get the version
    PREFLIGHT_VERSION=$(preflight --version | grep -o -E '[0-9]+\.[0-9]+\.[0-9]+')

    # Compare the Preflight version to the minimum version required
    if [ "$(printf '%s\n' "$MIN_PREFLIGHT_VERSION" "$PREFLIGHT_VERSION" | sort -V | head -n1)" != "$MIN_PREFLIGHT_VERSION" ]; then
        printf "%-48s \e[1;31m%-24s\e[m\n" "Check Preflight Minimum version 1.6.11+" "NOK"
        exit 1
    else
        printf "%-48s \e[1;32m%-24s\e[m\n" "Check Preflight Minimum version 1.6.11+" "OK"
    fi
}
#Check if python pandas and openpyxl packages are installed
check_python_packages() {
    if pip3 show pandas &>/dev/null && pip3 show openpyxl &>/dev/null; then
        #log "pandas and openpyxl are installed"
        printf "%-48s \e[1;32m%-24s\e[m\n" "Python Pandas and Openpyxl installed" "OK"
        return 1
    elif pip3 show pandas &>/dev/null; then
        #log "pandas is installed, but openpyxl is not" && bye "openpyxl is not installed!"
        printf "%-48s \e[1;31m%-24s\e[m\n" "Python Openpyxl" "NOK"
        exit 1
    elif pip3 show openpyxl &>/dev/null; then
        #log "openpyxl is installed, but pandas is not" && bye "pandas is not installed!"
        printf "%-48s \e[1;31m%-24s\e[m\n" "Python Pandas" "NOK"
        exit 1
    else
        #log "pandas and openpyxl are not installed" && bye "both pandas and openpyxl are not installed!"
        printf "%-48s \e[1;31m%-24s\e[m\n" "Python Pandas and Openpyxl" "NOK"
        exit 1
    fi
}

check_registry_server_connection() {
    HOST="$1"
    #GOOGLE="${2:-google.com}"
    
    if [[ -z "$quay_oauth_api_key" ]]; then
         HOST="$quay_registry_domain"
    fi

    if command -v nc >/dev/null 2>&1; then
        if nc -zv4 "$HOST" 80 >/dev/null 2>&1; then
            printf "%-48s \e[1;32m%-24s\e[m\n" "$HOST's Connection" "OK"
        else
            printf "%-48s \e[1;31m%-24s\e[m\n" "$HOST's Connection" "NOK"
            exit 1
        fi
    else
        printf "%-48s \e[1;33m%-24s\e[m\n" "$HOST's Connection" "SKIPPED"
    fi
}

check_docker_auth_json_connection() {
    HOST=$1
    
    if [[ -z "$quay_oauth_api_key" ]]; then
         HOST="$quay_registry_domain"
    fi

    cat "$auth_json_path" | grep $HOST >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        #log "Check Docker Authentication to $HOST succeeded!"
        printf "%-48s \e[1;32m%-24s\e[m\n" "Docker Authentication" "OK"
    else
        #log "Check Docker Authentication to $HOST failed!"
        printf "%-48s \e[1;31m%-24s\e[m\n" "Docker Authentication" "NOK"
        exit 1
    fi
}

check_private_registry_server_auth() {
    HOST=$1
    if [[ -z "$quay_oauth_api_key" ]]; then
         HOST="$quay_registry_domain"
    fi
    status_url="https://${HOST}/api/v1/repository?namespace=${REPO_NS}"
    status_code=$(curl -I --silent -o /dev/null -w "%{http_code}" -X GET -H "Authorization: Bearer ${API_TOKEN}" "${status_url}")

    if [ $status_code = "200" ]; then # succeed checking authenatication using Bear API_TOKEN
        #log "Check Private Registry Server to $HOST succeeded"
        printf "%-48s \e[1;32m%-24s\e[m\n" "Registry Server Bearer-Token Access" "OK"
    else
        #log "Check Private Registry Server to $HOST is FAILED, please check your Bear Token manually!"
        printf "%-48s \e[1;31m%-24s\e[m\n" "Registry Server Bearer-Token Access" "NOK"
        exit 1
    fi
}

start_convert_csv_xlsx_format_sort() {
    input_csv=$1
    output_xlsx=$2

    if [ ! -f "$input_csv" ]; then
        log "Input file $input_file does not exist!"
        exit 1
    fi

    python3 preflight_scan_csv_to_xlsx_v3.py $input_csv $output_xlsx
    if [ $? -eq 0 ]; then
        log "Successfully Converted from $input_csv to $output_xlsx!" #>/dev/null 2>&1
    else
        log "Failed to Convert from $input_csv $output_xlsx!!!"
        exit 1
    fi
}

start_container_images_scan() {
    # Preflight ENV settings
    export PFLT_JUNIT="true"
    export PFLT_LOGLEVEL=debug
    export PFLT_LOGFILE=/tmp/preflight.log

    printf "%s\n" "Please be patient while scanning images..."
    count=0
    total_time=0
    total_seconds=0

    for ((j = 0; j < ${#ImageLists[*]}; j++)); do
        start_time=$(date +%s.%N)
        
            unset hasModFilesMap
        declare -A hasModFilesMap
        
        hasModStatus=""
        hasModFiles=""

        find "$(pwd)/artifacts/" -type f -delete
        if [[ -z "$quay_oauth_api_key" ]]; then
            image_details="${ImageLists[$j]}"
            repo_imgname_tag=$(echo $image_details | cut -d'/' -f2-)
            img_name=$(echo ${image_details} | rev | cut -d '/' -f1 | rev | cut -d':' -f1)
            inspect_url="$image_details"
        else
            image_url="https://${FQDN}/api/v1/repository/${REPO_NS}/${ImageLists[$j]}"

            if [[ "${TAG_TYPE}" == "name" ]]; then
                tag_type_flag=".name + \":\" + .tags[].name"
            else # digest
                tag_type_flag=".name + \"@\" + .tags[].manifest_digest"
            fi

            image_details=$(curl --silent -X GET -H "Authorization: Bearer ${API_TOKEN}" "${image_url}" | jq -r "$tag_type_flag" | head -n1)
            tag=$(echo $image_details | cut -d ':' -f2)
            inspect_url="${FQDN}/${REPO_NS}/${ImageLists[$j]}:$tag"
            img_name=$(echo ${ImageLists[$j]} | rev | cut -d '/' -f1 | rev )
            repo_imgname_tag="$img_name:$tag"
        fi

        printf "\n%s\n" "Scanning the following image: ${repo_imgname_tag}"
        printf "%s\n" "================================================================================"        

        # Since this script is using preflight to do a quick image scan, the certification-project-id is dummy
        result_output=$(preflight check container "$inspect_url" --certification-project-id 63ec090760bb63386e44a33e \
            -d "${auth_json_path}" 2>&1 |
            awk 'match($0, /check=([^ ]+)/, c) && match($0, /result=([^ ]+)/, r) {print c[1] "," r[1]}')

        
        printf "%-20s %-25s %-10s\n" "Image Name" "Test Case" "Status"
        printf "%s\n" "------------------------------------------------------"

        console_output=($(printf "%s\n" "$result_output" | awk -v img="$img_name" '{print img "," $0}'))

        for line in "${console_output[@]}"; do
            image=$(printf "%s\n" "$line" | awk -F',' '{print $1}')
            testcase=$(printf "%s\n" "$line" | awk -F',' '{print $2}')
            status=$(printf "%s\n" "$line" | awk -F',' '{print $3}')

            if [ "$hasModStatus" = "FAILED" ]; then
                hasModFiles="${hasModFilesMap[$testcase]}"
            else
                hasModFiles=""
            fi
            if [[ "$testcase" != "HasModifiedFiles" ]]; then
                 hasModFiles=""
            fi

            if [ "$status" = "FAILED" ]; then
                printf "%-20s %-25s \e[1;31m%-10s\e[m\n" "${image}" "${testcase}" "${status}"
            elif [ "$status" = "PASSED" ]; then
                printf "%-20s %-25s \e[1;32m%-10s\e[m\n" "${image}" "${testcase}" "${status}"
            else
                printf "%-20s %-25s \e[1;33m%-10s\e[m\n" "${image}" "${testcase}" "NOT_APP"
            fi

            # Check for HasModifiedFiles is failed and save file debug lines
            if [[ "$testcase" = "HasModifiedFiles" && "$status" = "FAILED" ]]; then
                if [ -n "${hasModFilesMap[$testcase]}" ]; then
                    hasModFilesMap[$testcase]+="$(cat /tmp/preflight.log | grep -o 'file=[^ ]*' | cut -d= -f2 | tr '\n' ':' | sed 's/:$//')"
                else
                    hasModFilesMap[$testcase]="$(cat /tmp/preflight.log | grep -o 'file=[^ ]*' | cut -d= -f2 | tr '\n' ':' | sed 's/:$//')"
                fi
                hasModStatus="FAILED"
            fi
        done

        for line in "${console_output[@]}"; do
            image=$(printf "%s\n" "$line" | awk -F',' '{print $1}')
            testcase=$(printf "%s\n" "$line" | awk -F',' '{print $2}')
            status=$(printf "%s\n" "$line" | awk -F',' '{print $3}' | sed 's/ERROR/NOT_APP/g')
            if [ "$hasModStatus" = "FAILED" ]; then
                hasModFiles="${hasModFilesMap[$testcase]}"
            else
                hasModFiles=""
            fi

            printf "%s,%s,%s,%s,%s\n" "${image}" "${tag}" "${hasModFiles}" "${testcase}" "${status}"
        done >> $preflight_image_scan_result_csv

        verdict_status=$(cat /tmp/preflight.log | awk 'match($0, /result: ([^"]+)/, r) {print "Verdict: " r[1]}')
        vstatus=$(echo "$verdict_status" | awk '{print $2}')
        if [[ "$vstatus" =~ "FAILED" ]]; then
            printf "Verdict: \e[1;31m%-10s\e[m\n" "${vstatus}"
        elif [[ "$vstatus" =~ "PASSED" ]]; then
            printf "Verdict: \e[1;32m%-10s\e[m\n" "${vstatus}"
        else
            printf "Verdict: \e[1;33m%-10s\e[m\n" "NOT_APP"
        fi

        touch /tmp/preflight.log

        end_time=$(date +%s.%N)
        printf "Time elapsed: %.3f seconds\n" $(echo "$end_time - $start_time" | bc)

        elapsed_time=$(echo "$end_time - $start_time" | bc)
        total_seconds=$(echo "$total_seconds + $elapsed_time" | bc)
        count=$((count + 1))
    done

    printf "%s\n" "------------------------------------------------------"
    total_time=$(date -u -d "@$total_seconds" '+%Hh:%Mm:%Ss')

    printf "Total Number Images Scanned: %s\n" "$count"
    printf "Total Time Scanned: %s\n" "$total_time"
    printf "%s\n" "------------------------------------------------------"
}

# Define the function to check and add an extra empty line
check_and_add_empty_line() {
    local file_to_check="$1"

    # Check if the last line of the file is empty
    if [ -n "$(tail -c 1 "$file_to_check")" ]; then
        # If not, add an extra empty line
        echo >> "$file_to_check"
        echo "Added an extra empty line to $file_to_check"
    else
        echo "The last line of $file_to_check is already empty."
    fi
}


###############################Main Function###################################
printf "\n%s\n" "Checking the pre-requirements steps..........."
printf "%s\n" "========================================================"
printf "%-46s %-10s\n" "Pre-Requirements Checking" "Status"
printf "%s\n" "---------------------------------------------------------"
#check preflight and python3 exist
check_tools

#check preflight minimum version 1.6.11+
check_preflight_version

#check registry server is reachable
check_registry_server_connection $FQDN

#Check Private Registry Server authentication
check_private_registry_server_auth $FQDN

#Check python pandas and openpyxl packages are installed
check_python_packages

#check docker authentication to private registry server has been login
check_docker_auth_json_connection $FQDN

printf "%s\n" "======================================================="

if [[ -z "$quay_oauth_api_key" ]]; then
    # Define the array
    ImageLists=()

    # Define the file to check
    file_to_check="image_list.txt"

    # Call the function to check and add an extra empty line
    check_and_add_empty_line "$file_to_check"

    # Read each line from image_list.txt and add it to the array
    while IFS= read -r line; do
    if [ -n "$line" ]; then
        ImageLists+=("$line")
        echo $line
    fi
    done < image_list.txt
else
    #Get all images based user's criteria and filters from QAUY via REST API#
    readarray -t _ImageLists <<<$(curl --silent -X GET -H "Authorization: Bearer ${API_TOKEN}" "https://${FQDN}/api/v1/repository?namespace=${REPO_NS}" | jq -r '.repositories[].name' | egrep ${CNF_PREFIX} | egrep -v ${FILTER})
fi

if [ -z $_ImageLists ]; then
    log "There is no image in the array list"
    log "Please check with curl cmd manually to see if this image responded to REST API or not!!!"
    exit 1
fi

#some cases where new images are not responded via REST API then add an exception here
#new_images=('ava-core/global-upf-ava' 'ava-core/global-upf-avu')
ImageLists=("${_ImageLists[@]}") # "${new_images[@]}")

#check if exist csv is existed and rename it
rename_file $preflight_image_scan_result_csv "${preflight_image_scan_result_csv}_saved"

#Print header for CSV
printf "%s\n" "Image Name,Image Tag,Has Modified Files,Test Case,Status" | tee $preflight_image_scan_result_csv >/dev/null
#Start to using Quay REST API and Preflight to do quick snapshot testing
start_container_images_scan

#Start convert csv to xlsx and sort/format only-if panda/openpyxl packages are installed
start_convert_csv_xlsx_format_sort $preflight_image_scan_result_csv "images_scan_results.xlsx"
```
## Contents of CSV to XLSX Conversion Python Script
```python
import argparse
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import PatternFill, Font, Alignment
import io

def convert_csv_xlsx_sort_and_format(input_file: str, output_file: str):
    # Read the CSV file using Pandas
    df = pd.read_csv(input_file)

    # Sort the DataFrame by status and test case name
    df = df.sort_values(by=['Status', 'Test Case'], key=lambda x: x.map({'FAILED': 0, 'NOT_APP': 1, 'PASSED': 2}))

    # Create an Excel workbook using openpyxl
    wb = Workbook()
    ws = wb.active

    # Set column alignment
    alignment = Alignment(horizontal='center', vertical='center')
    for col in ws.columns:
        for cell in col:
            cell.alignment = alignment

    # Set column widths
    ws.column_dimensions['A'].width = 20
    ws.column_dimensions['B'].width = 30
    ws.column_dimensions['C'].width = 40
    ws.column_dimensions['D'].width = 30
    ws.column_dimensions['E'].width = 20

    # Write the data to the worksheet
    for r in dataframe_to_rows(df, index=False, header=True):
        ws.append(r)

    # Set text wrap for column C
    for cell in ws['C']:
        cell.alignment = Alignment(wrap_text=True)  # Enable text wrap for column C

    # Set the cell background color for the data rows
    for row in ws.iter_rows(min_row=2, min_col=5, max_col=5):  # Assuming 'Status' column is in column D
        for cell in row:
            if cell.value == 'PASSED':
                cell.font = Font(color='006400')  # Dark green font for 'PASSED'
            elif cell.value == 'FAILED':
                cell.font = Font(color='FF0000')  # Red font for 'FAILED'
            elif cell.value == 'NOT_APP':
                cell.font = Font(color='FFA500')  # Dark orange font for 'NOT_APP' (FFA500 is the hexadecimal color for dark orange)

    # Set column alignment
    for col in ws.columns:
        if col[0].value == 'Status' or col[0].value == 'Image Tag':
            for cell in col:
                cell.alignment = Alignment(horizontal='center', vertical='center')
        else:
            for cell in col:
                cell.alignment = Alignment(horizontal='left', vertical='center')

    # Set the cell background color and font for the header row
    header_fill = PatternFill(start_color='ADD8E6', end_color='ADD8E6', fill_type='solid')
    header_font = Font(bold=True, color='000000')
    header_alignment = Alignment(horizontal='center', vertical='center')

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment

    # Save the workbook
    wb.save(output_file)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Sort and format a CSV file and save as Excel workbook')
    parser.add_argument('input_file', type=str, help='Path to input CSV file')
    parser.add_argument('output_file', type=str, help='Path to output Excel file')
    args = parser.parse_args()
    convert_csv_xlsx_sort_and_format(args.input_file, args.output_file)
```
## Start Container Images Preflight Scan Automation With Quay RESTAPI
```shellSession
$ bash quick_scan_container_images_online_offline.sh --repo-ns xxxxxxx_5gc --cnf-prefix "busybox|simple"

Checking the pre-requirements steps...........
========================================================
Pre-Requirements Checking                      Status    
---------------------------------------------------------
python3 and preflight installed                  OK                      
quay.xxxxxxx.bos2.lab's Connection               OK                      
Registry Server Bearer-Token Access              OK                      
Python Pandas and Openpyxl installed             OK                      
Docker Authentication                            OK                      
=======================================================

Please be patient while scanning images...

Scaning the following image: rel-core/global-nf-busybox
======================================================
Image Name           Test Case                 Status    
------------------------------------------------------
global-nf-busybox    HasLicense                FAILED    
global-nf-busybox    HasUniqueTag              PASSED    
global-nf-busybox    LayerCountAcceptable      PASSED    
global-nf-busybox    HasNoProhibitedPackages   ERROR     
global-nf-busybox    HasRequiredLabel          FAILED    
global-nf-busybox    RunAsNonRoot              FAILED    
global-nf-busybox    HasModifiedFiles          ERROR     
global-nf-busybox    BasedOnUbi                FAILED    
======================================================
Verdict: FAILED    
Time elapsed: 2.533 seconds

Scaning the following image: rel-nv/cn-mongo/mdbm/simplecert
======================================================
Image Name           Test Case                 Status    
------------------------------------------------------
simplecert           HasLicense                FAILED    
simplecert           HasUniqueTag              PASSED    
simplecert           LayerCountAcceptable      PASSED    
simplecert           HasNoProhibitedPackages   ERROR     
simplecert           HasRequiredLabel          FAILED    
simplecert           RunAsNonRoot              PASSED    
simplecert           HasModifiedFiles          ERROR     
simplecert           BasedOnUbi                FAILED    
======================================================
Verdict: FAILED    
Time elapsed: 6.189 seconds
Total Number Images Scanned: 2
20230410-15:54:30 Successfully Converted from preflight_image_scan_result.csv to images_scan_results.xlsx!
```

- **Images Scan Console Output:** 
![Images Scan Console Output](img/images_scan_console_output.png "Images Scan Console Output")

- **New Images Scan with Debug**
![Images Scan XLSX Conversion Output](img/new-conversion-output.png "Images Scan XLSX Conversion New Output")

- **Images Scan XSLX Output:**   
![Images Scan XLSX Conversion Output](img/images_scan_xlsx_conversion_ouput.png "Images Scan XLSX Conversion Output")

## Start Container Images Preflight Scan Automation Without Quay RESTAPI
When Partner do not have the priviledge to access Quay or private registry RESTAPI, they can dump the following format to a image_list.txt then the script it will read from this file and using preflight to scan images automatic.
Of course, there are some mandatory parameters that need to be defined before such as auth.json and registry-fqdn.  
**image_list.txt:**
```shellSession
quay.ava.bos2.lab/ava_5gc/ava-core/univ-smf-nec:v1
quay.ava.bos2.lab/ava_5gc/ava-core/univ-smf-nad:v1
quay.ava.bos2.lab/ava_5gc/ava-core/univ-nrf-att:v1
```
