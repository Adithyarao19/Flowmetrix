import os
import time
import logging
from collections import defaultdict
import jenkins
import requests  # Standard library for HTTP requests
from prometheus_client import start_http_server, Counter, Histogram, Gauge

# --- Environment Variables ---
JENKINS_URL = os.environ.get('JENKINS_URL', 'http://localhost:8080')
JENKINS_USER = os.environ.get('JENKINS_USER')
JENKINS_TOKEN = os.environ.get('JENKINS_TOKEN')
JOBS_TO_MONITOR = os.environ.get('JOBS_TO_MONITOR', 'my-pipeline-job').split(',')
POLL_INTERVAL = int(os.environ.get('POLL_INTERVAL', 60))
LISTEN_PORT = int(os.environ.get('LISTEN_PORT', 8000))

# --- Prometheus Metrics Definitions ---
BUILD_COUNTER = Counter(
    'flowmetrix_pipeline_build_total',
    'Total number of pipeline builds',
    ['job_name', 'status', 'branch']
)
BUILD_DURATION = Histogram(
    'flowmetrix_pipeline_build_duration_seconds',
    'Histogram of pipeline build durations in seconds',
    ['job_name', 'branch'],
    buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600, float("inf")]
)
STAGE_DURATION = Histogram(
    'flowmetrix_pipeline_stage_duration_seconds',
    'Histogram of pipeline stage durations in seconds',
    ['job_name', 'stage_name', 'branch', 'status'],
    buckets=[5, 10, 30, 60, 120, 300, 600, 1200, float("inf")]
)
LAST_PROCESSED_BUILD = Gauge(
    'flowmetrix_last_processed_build_number',
    'The last build number processed by the exporter',
    ['job_name']
)

# --- Jenkins Collector Class ---
class JenkinsCollector:
    def __init__(self, jenkins_server, job_names):
        self.server = jenkins_server
        self.job_names = job_names
        self.last_processed_builds = defaultdict(int)
        self._initialize_state()

    def _initialize_state(self):
        logging.info("Initializing collector state...")
        for job_name in self.job_names:
            try:
                job_info = self.server.get_job_info(job_name, fetch_all_builds=False)
                last_build_number = job_info.get('lastCompletedBuild', {}).get('number', 0)
                if last_build_number == 0:
                     last_build_number = job_info.get('lastBuild', {}).get('number', 0)
                
                self.last_processed_builds[job_name] = last_build_number
                logging.info(f"Initial state for '{job_name}': last processed build is {last_build_number}")
            except jenkins.NotFoundException:
                logging.error(f"Job '{job_name}' not found on Jenkins. Skipping initial state for this job.")
            except Exception as e:
                logging.error(f"Error initializing state for '{job_name}': {e}")

    def get_branch_name(self, build_info):
        for action in build_info.get('actions', []):
            if 'lastBuiltRevision' in action:
                revision = action.get('lastBuiltRevision', {})
                if 'branch' in revision:
                    return revision['branch'][0].get('name', 'unknown').replace('refs/remotes/origin/', '').replace('refs/heads/', '')
            
            if 'parameters' in action:
                for param in action.get('parameters', []):
                    if param.get('name', '').lower() in ['branch', 'git_branch']:
                        return param.get('value', 'unknown')
        
        for action in build_info.get('actions', []):
             if action.get('_class') == 'jenkins.plugins.git.GitTagAction':
                 return action.get('tags', [{}])[0].get('name', 'unknown')

        return 'unknown'

    def collect(self):
        logging.info("Collector.collect() called. Checking for new builds...")
        
        for job_name in self.job_names:
            try:
                job_info = self.server.get_job_info(job_name, fetch_all_builds=False)
                last_build_number = job_info.get('lastCompletedBuild', {}).get('number', 0)
                last_processed = self.last_processed_builds[job_name]

                if last_build_number <= last_processed:
                    logging.info(f"No new completed builds for '{job_name}'. Last processed: {last_processed}")
                    continue

                logging.info(f"Found new builds for '{job_name}'. Processing from {last_processed + 1} to {last_build_number}")

                for build_number in range(last_processed + 1, last_build_number + 1):
                    try:
                        self.process_build(job_name, build_number)
                        self.last_processed_builds[job_name] = build_number
                    except requests.exceptions.RequestException as e:
                        logging.warning(f"Network or API error while fetching build {job_name} #{build_number}: {e}")
                        break 
                    except Exception as e:
                        logging.error(f"Failed to process build {job_name} #{build_number} unexpectedly: {e}", exc_info=True)
                        # Break to avoid getting stuck on a failing build forever in a tight loop
                        break

            except jenkins.NotFoundException:
                logging.error(f"Job '{job_name}' not found during collection. Please check JOBS_TO_MONITOR.")
            except jenkins.JenkinsException as e:
                logging.error(f"Jenkins API error for job '{job_name}': {e}")
            except requests.exceptions.RequestException as e:
                logging.error(f"Network error connecting to Jenkins for job '{job_name}': {e}")
            except Exception as e:
                logging.error(f"An unexpected error occurred during collection for '{job_name}': {e}")

    def process_build(self, job_name, build_number):
        logging.info(f"Processing {job_name} #{build_number}...")
        
        # --- FIX STARTS HERE ---
        # 1. Construct the full URL securely
        # self.server.server contains the base URL like 'http://host:8080/'
        base_url = self.server.server.rstrip('/')
        api_url = f"{base_url}/job/{job_name}/{build_number}/wfapi/describe"
        
        # 2. Create a Request object (Required by python-jenkins library)
        req = requests.Request(method='GET', url=api_url)
        
        # 3. Send the request using python-jenkins (Handles Auth & Crumbs)
        response = self.server.jenkins_request(req)
        
        # 4. Parse the JSON response
        # raise_for_status() checks for 404/500 errors
        response.raise_for_status()
        build_info = response.json()
        # --- FIX ENDS HERE ---

        status = build_info.get('status', 'UNKNOWN')
        branch = self.get_branch_name(build_info)
        duration_sec = build_info.get('durationMillis', 0) / 1000.0

        BUILD_COUNTER.labels(job_name=job_name, status=status, branch=branch).inc()
        BUILD_DURATION.labels(job_name=job_name, branch=branch).observe(duration_sec)

        for stage in build_info.get('stages', []):
            stage_name = stage.get('name', 'Unnamed Stage')
            stage_status = stage.get('status', 'UNKNOWN')
            stage_duration_sec = stage.get('durationMillis', 0) / 1000.0

            STAGE_DURATION.labels(
                job_name=job_name,
                stage_name=stage_name,
                branch=branch,
                status=stage_status
            ).observe(stage_duration_sec)
        
        LAST_PROCESSED_BUILD.labels(job_name=job_name).set(build_number)
        logging.info(f"Successfully processed {job_name} #{build_number}")

# --- Main Execution ---
def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info(f"Starting FlowMetrix Exporter...")
    logging.info(f"Connecting to Jenkins at {JENKINS_URL}")
    logging.info(f"Monitoring jobs: {JOBS_TO_MONITOR}")
    
    if not all([JENKINS_USER, JENKINS_TOKEN]):
        logging.error("JENKINS_USER and JENKINS_TOKEN environment variables must be set.")
        exit(1)

    try:
        server = jenkins.Jenkins(JENKINS_URL, username=JENKINS_USER, password=JENKINS_TOKEN, timeout=10)
        version = server.get_version() 
        logging.info(f"Successfully connected to Jenkins version {version}")
    except jenkins.JenkinsException as e:
        logging.error(f"Failed to connect to Jenkins due to API error. DETAIL: {e}", exc_info=True)
        exit(1)
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to connect to Jenkins due to network error: {e}", exc_info=True)
        exit(1)
    except Exception as e:
        logging.error(f"An unexpected error occurred while connecting to Jenkins: {e}", exc_info=True)
        exit(1)

    collector = JenkinsCollector(server, JOBS_TO_MONITOR)

    try:
        start_http_server(LISTEN_PORT)
        logging.info(f"Prometheus exporter started on port {LISTEN_PORT}")
    except Exception as e:
        logging.error(f"Failed to start Prometheus HTTP server on port {LISTEN_PORT}: {e}")
        exit(1)

    logging.info("Starting main collection loop...")
    while True:
        try:
            collector.collect()
        except Exception as e:
            logging.error(f"Unhandled exception in main loop: {e}")
        logging.info(f"Collection cycle complete. Sleeping for {POLL_INTERVAL} seconds.")
        time.sleep(POLL_INTERVAL)

if __name__ == '__main__':
    main()