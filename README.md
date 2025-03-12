# quick_scan_container_images_parallel
The purpose of this script is to streamline the Preflight scanning for container images, whether Quay RESTAPI is utilized or offline e.g. prepare a list of images in a file with URL. Another benefit for this script is that it can scan your container images in parallel. 

With the latest Preflight releases, the scanning capability has been enhanced to detect changes or removals of original UBI-based image files within multiple layers of Docker images. This scanning process serves as a preliminary check before submission to the backend, ensuring that all criteria are met.

The script produces test case results, which are initially displayed in the console and then exported to both CSV then convert to XLSX automatically. 

## Pre-Requisites
- Clone this github repo then use the scripts  
- Login to Private Registry Server with  
  `podman login -u xxx quay.io`
- To access to Quay.io Or Private Registry via REST API, it requires oauth and bear token
- Push images to Quay Repository with specific Organization
- Python3 + Pandas and Openpyxl using `pip3 install pandas openpyxl`   
  if `pip3` is not installed yet then `sudo dnf install python3-pip -y`
- netcat (nc) rpm installed if not there it will skip the connectivity checking
- bc rpm is also needed for check time
  sudo dnf install bc -y
- Install preflight 
```shellSession
wget https://github.com/redhat-openshift-ecosystem/openshift-preflight/releases/download/1.12.0/preflight-linux-amd64
chmod +x preflight-linux-amd64
sudo mv preflight-linux-amd64 /usr/local/bin/preflight
```

## Script Usage
```shellSession
$ python3 quick_scan_container_images_parallel.py -h
usage: quick_scan_container_images_parallel.py [-h] [-rn REPO_NS] [-cp CNF_PREFIX] [-t TAG_TYPE] [-at API_TOKEN] [-d AUTH_JSON] [-img IMG_FILE] -fq FQDN [-ft FILTER] [-p PARALLEL]

Scan container images (API-based or Offline) using preflight in parallel and convert CSV to XLSX.

options:
  -h, --help            show this help message and exit
  -rn REPO_NS, --repo-ns REPO_NS
                        Repository namespace (e.g., ava or avareg_5gc)
  -cp CNF_PREFIX, --cnf-prefix CNF_PREFIX
                        CNF image prefix (e.g., 'global-' or 'global|non-global')
  -t TAG_TYPE, --tag-type TAG_TYPE
                        Image tag type: 'name' (default) or 'digest'
  -at API_TOKEN, --api-token API_TOKEN
                        API token (Bearer Token)
  -d AUTH_JSON, --auth-json AUTH_JSON
                        Path to Docker authentication JSON file
  -img IMG_FILE, --img-file IMG_FILE
                        Text file with a list of images (one per line)
  -fq FQDN, --fqdn FQDN
                        Fully-qualified domain name of your registry (e.g., quay.io)
  -ft FILTER, --filter FILTER
                        Filter to exclude images (e.g., 'existed_image|tested_image')
  -p PARALLEL, --parallel PARALLEL
                        Number of images to scan in parallel (default 1)
```
## Start Container Images Using Preflight With API-Based
```shellSession
$ python3 quick_scan_container_images_parallel.py -rn xxxxxxx_5gc -d auth.json -at xxxxxx -fq quay.io -cp "busybox|simple"

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

Scaning the following image: rel-test/univ-box
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

Scaning the following image: rel-test/mongo/mdbm/notsimple
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

## Start Container Images Scan Using Preflight (Offline)
When Partner do not have the priviledge to access Quay or private registry RESTAPI, if you are on disconnected environment, you can prepare a list container images with URL to any filename e.g. image_list.txt.
If images private, then provide auth.json otherwise you can exclude from argument. 
**image_list.txt:**
```shellSession
quay.ava.lab/ava_5gc/ava-core/univ-smf-nec:v1
quay.ava.lab/ava_5gc/ava-core/univ-smf-nad:v1
quay.ava.lab/ava_5gc/ava-core/univ-nrf-att:v1
```
- How to run this script without Quay/Registry API (Offline)  
```shellSession
With Auth.json:
$ python3 quick_scan_container_images_parallel.py -img image-test.txt -fq quay.io -d ./auth.json

Without Docker Authentication:
$ python3 quick_scan_container_images_parallel.py -img image-test.txt -fq quay.io
```

- Output for offline
```shellSession
python3 preflight_quickscan.py -img image_list.txt -fq quay.io -p 4

Checking pre-requisite steps...
========================================================
Pre-Requisites                                 Status    
---------------------------------------------------------
python3 and preflight installed                  OK                      
bc utility installed                             OK                      
Preflight version check (>=1.6.11)               OK                      
quay.io connection                               OK                      
Python Pandas and Openpyxl installed             OK                      
=======================================================
20250311-21:11:18 File 'preflight_image_scan_result.csv' has been renamed to 'preflight_image_scan_result.csv_saved'
20250311-21:11:18 Scan the following image: quay.io/avu0/nginx-118:1-42 in parallel
20250311-21:11:18 Scan the following image: quay.io/avu0/ying-nginx-oneshot1-8080:1-24 in parallel
20250311-21:11:18 Scan the following image: quay.io/avu0/ying-nginx-oneshot2-8080:1-24 in parallel
20250311-21:11:18 Scan the following image: quay.io/avu0/auto-publish-ubi8-nginx-demo1:v121 in parallel
20250311-21:11:44 Scan the following image: quay.io/avu0/ubi8-micro-busybox:non-root in parallel
20250311-21:11:44 Scan the following image: quay.io/avu0/ying-nginx-oneshot1-8081:1-24 in parallel

Scanning image: avu0/ying-nginx-oneshot1-8080:1-24
================================================================================
Image Name                           Test Case                  Status    
-------------------------------------------------------------------------------
ying-nginx-oneshot1-8080       HasLicense                       PASSED      
ying-nginx-oneshot1-8080       HasUniqueTag                     PASSED      
ying-nginx-oneshot1-8080       LayerCountAcceptable             PASSED      
ying-nginx-oneshot1-8080       HasNoProhibitedPackages          PASSED      
ying-nginx-oneshot1-8080       HasRequiredLabel                 PASSED      
ying-nginx-oneshot1-8080       RunAsNonRoot                     PASSED      
ying-nginx-oneshot1-8080       HasModifiedFiles                 PASSED      
ying-nginx-oneshot1-8080       BasedOnUbi                       PASSED      
Verdict: PASSED
Time elapsed: 26.124 seconds

Scanning image: avu0/nginx-118:1-42
================================================================================
Image Name                           Test Case                  Status    
-------------------------------------------------------------------------------
nginx-118                      HasLicense                       FAILED      
nginx-118                      HasUniqueTag                     PASSED      
nginx-118                      LayerCountAcceptable             PASSED      
nginx-118                      HasNoProhibitedPackages          PASSED      
nginx-118                      HasRequiredLabel                 PASSED      
nginx-118                      RunAsNonRoot                     PASSED      
nginx-118                      HasModifiedFiles                 PASSED      
nginx-118                      BasedOnUbi                       PASSED      
Verdict: FAILED
Time elapsed: 26.816 seconds

Scanning image: avu0/auto-publish-ubi8-nginx-demo1:v121
================================================================================
Image Name                           Test Case                  Status    
-------------------------------------------------------------------------------
auto-publish-ubi8-nginx-demo1  HasLicense                       PASSED      
auto-publish-ubi8-nginx-demo1  HasUniqueTag                     PASSED      
auto-publish-ubi8-nginx-demo1  LayerCountAcceptable             PASSED      
auto-publish-ubi8-nginx-demo1  HasNoProhibitedPackages          PASSED      
auto-publish-ubi8-nginx-demo1  HasRequiredLabel                 PASSED      
auto-publish-ubi8-nginx-demo1  RunAsNonRoot                     PASSED      
auto-publish-ubi8-nginx-demo1  HasModifiedFiles                 PASSED      
auto-publish-ubi8-nginx-demo1  BasedOnUbi                       PASSED      
Verdict: PASSED
Time elapsed: 28.524 seconds

Scanning image: avu0/ying-nginx-oneshot2-8080:1-24
================================================================================
Image Name                           Test Case                  Status    
-------------------------------------------------------------------------------
ying-nginx-oneshot2-8080       HasLicense                       PASSED      
ying-nginx-oneshot2-8080       HasUniqueTag                     PASSED      
ying-nginx-oneshot2-8080       LayerCountAcceptable             PASSED      
ying-nginx-oneshot2-8080       HasNoProhibitedPackages          PASSED      
ying-nginx-oneshot2-8080       HasRequiredLabel                 PASSED      
ying-nginx-oneshot2-8080       RunAsNonRoot                     PASSED      
ying-nginx-oneshot2-8080       HasModifiedFiles                 PASSED      
ying-nginx-oneshot2-8080       BasedOnUbi                       PASSED      
Verdict: PASSED
Time elapsed: 29.539 seconds

Scanning image: avu0/ubi8-micro-busybox:non-root
================================================================================
Image Name                           Test Case                  Status    
-------------------------------------------------------------------------------
ubi8-micro-busybox             HasLicense                       PASSED      
ubi8-micro-busybox             HasUniqueTag                     PASSED      
ubi8-micro-busybox             LayerCountAcceptable             PASSED      
ubi8-micro-busybox             HasNoProhibitedPackages          PASSED      
ubi8-micro-busybox             HasRequiredLabel                 PASSED      
ubi8-micro-busybox             RunAsNonRoot                     PASSED      
ubi8-micro-busybox             HasModifiedFiles                 PASSED      
ubi8-micro-busybox             BasedOnUbi                       PASSED      
Verdict: PASSED
Time elapsed: 20.693 seconds

Scanning image: avu0/ying-nginx-oneshot1-8081:1-24
================================================================================
Image Name                           Test Case                  Status    
-------------------------------------------------------------------------------
ying-nginx-oneshot1-8081       HasLicense                       PASSED      
ying-nginx-oneshot1-8081       HasUniqueTag                     PASSED      
ying-nginx-oneshot1-8081       LayerCountAcceptable             PASSED      
ying-nginx-oneshot1-8081       HasNoProhibitedPackages          PASSED      
ying-nginx-oneshot1-8081       HasRequiredLabel                 PASSED      
ying-nginx-oneshot1-8081       RunAsNonRoot                     PASSED      
ying-nginx-oneshot1-8081       HasModifiedFiles                 PASSED      
ying-nginx-oneshot1-8081       BasedOnUbi                       PASSED      
Verdict: PASSED
Time elapsed: 41.518 seconds
------------------------------------------------------------------------------
Total Images Scanned: 6
Total Scan Time: 00h:01m:08s
------------------------------------------------------------------------------

20250311-21:12:26 Converted preflight_image_scan_result.csv to images_scan_results.xlsx successfully!
```
