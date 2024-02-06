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

Scaning the following image: rel-core/univ-box
======================================================
Image Name           Test Case                 Status    
------------------------------------------------------
univ-box    HasLicense                FAILED    
univ-box    HasUniqueTag              PASSED    
univ-box    LayerCountAcceptable      PASSED    
univ-box    HasNoProhibitedPackages   ERROR     
univ-box    HasRequiredLabel          FAILED    
univ-box    RunAsNonRoot              FAILED    
univ-box    HasModifiedFiles          ERROR     
univ-box    BasedOnUbi                FAILED    
======================================================
Verdict: FAILED    
Time elapsed: 2.533 seconds

Scaning the following image: rel-nv/cn-mongo/mdbm/notsimple
======================================================
Image Name           Test Case                 Status    
------------------------------------------------------
notsimple           HasLicense                FAILED    
notsimple           HasUniqueTag              PASSED    
notsimple           LayerCountAcceptable      PASSED    
notsimple           HasNoProhibitedPackages   ERROR     
notsimple           HasRequiredLabel          FAILED    
notsimple           RunAsNonRoot              PASSED    
notsimple           HasModifiedFiles          ERROR     
notsimple           BasedOnUbi                FAILED    
======================================================
Verdict: FAILED    
Time elapsed: 6.189 seconds
Total Number Images Scanned: 2
20230410-15:54:30 Successfully Converted from preflight_image_scan_result.csv to images_scan_results.xlsx!
```

- **Images Scan Console Output:** 
<!-- ![Images Scan Console Output](img/images_scan_console_output.png "Images Scan Console Output") -->

- **New Images Scan with Debug**
<!-- ![Images Scan XLSX Conversion Output](img/new-conversion-output.png "Images Scan XLSX Conversion New Output") -->

- **Images Scan XSLX Output:**   
<!-- ![Images Scan XLSX Conversion Output](img/images_scan_xlsx_conversion_ouput.png "Images Scan XLSX Conversion Output") -->

## Start Container Images Preflight Scan Automation Without Quay RESTAPI
When Partner do not have the priviledge to access Quay or private registry RESTAPI, they can dump the following format to a image_list.txt then the script it will read from this file and using preflight to scan images automatic.
Of course, there are some mandatory parameters that need to be defined before such as auth.json and registry-fqdn.  
**image_list.txt:**
```shellSession
quay.ava.lab/ava_5gc/ava-core/univ-smf-nec:v1
quay.ava.lab/ava_5gc/ava-core/univ-smf-nad:v1
quay.ava.lab/ava_5gc/ava-core/univ-nrf-att:v1
```
- How to run this script with image_list.txt  
Run it without any argument like this  
```shellSession
$ bash quick_scan_container_images_online_offline.sh
```
