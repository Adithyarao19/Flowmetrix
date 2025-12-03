# FlowMetrix: CI/CD Observability for Jenkins

**Unlock the data hidden in your pipelines. Turn build logs into SRE insights.**

---


)<img width="1914" height="861" alt="Screenshot 2025-11-25 165442" src="https://github.com/user-attachments/assets/7ee25dc7-0e06-4a76-a2b0-d1be755b23dc" />

*(A screenshot of the Grafana dashboard showing build trends and stage durations)*

## The Problem it Solves

Jenkins is the engine of CI/CD, but it's often a black box.
- **Developers** ask: "Why did my build take twice as long today?"
- **DevOps Engineers** ask: "Which specific stage is our biggest bottleneck?"
- **SREs** ask: "What is our P95 build time and failure rate over the last month?"

Jenkins has the data, but it's buried in HTML logs. You can't easily graph it, alert on it, or spot long-term trends. **FlowMetrix solves this.**

## What is FlowMetrix?

FlowMetrix is a lightweight, containerized exporter that connects to your Jenkins instance. It doesn't just look at pass/fail status; it deeply analyzes pipeline structures to extract rich metrics on every single stage.

It converts this data into Prometheus format, making it instantly visualized in Grafana.

### Key Metrics
- 📊 **Pipeline Duration (P95, Avg):** Track build times over time.
- ⏱️ **Stage-Level Duration:** Pinpoint the exact stage (e.g., "Docker Build," "Unit Tests") slowing you down.
- ✅ **Success/Failure Rates:** Monitor build stability and throughput.
- 📉 **Failure Attribution:** See which stages fail most frequently.

## Architecture

The project uses a modern, decoupled architecture designed for reliability and simplicity.

[Jenkins API] <- (polls) -> [**FlowMetrix Exporter** (Python)] <- (scrapes) -> [**Prometheus** (TSDB)] -> [**Grafana** (UI)]

1.  **FlowMetrix Exporter:** A custom Python application that polls the Jenkins Workflow API for new builds. It intelligently processes only new data to remain stateless and efficient.
2.  **Prometheus:** A time-series database that scrapes metrics from the exporter every 30 seconds.
3.  **Grafana:** A powerful visualization platform pre-configured with a beautiful dashboard to make sense of the Prometheus data.
4.  **Docker Compose:** Orchestrates the entire stack with a single command.

## Quick Start

Get the full stack running locally in under 5 minutes.

### Prerequisites
* Docker and Docker Compose installed.
* A running Jenkins instance (local or remote).
* A Jenkins job (must be a **Pipeline** type) to monitor.

### Setup Steps

1.  **Clone the repository:**
    
   

2.  **Create your configuration file:**
    Create a `.env` file in the root directory and add your Jenkins details. **Do not commit this file.**
    ```bash
    # .env
    JENKINS_URL=[http://host.docker.internal:8080](http://host.docker.internal:8080)  # Use host.docker.internal for local Jenkins
    JENKINS_USER=your-username
    JENKINS_TOKEN=your-api-token-here           # Generate in Jenkins User Settings
    JOBS_TO_MONITOR=my-pipeline-job             # Comma-separated list of job names
    ```

3.  **Launch the stack:**
    ```bash
    docker-compose up -d --build
    ```

### Accessing the Dashboards

Give the system about a minute to initialize. Once a new build runs in Jenkins, data will appear.

* **Grafana Dashboard:** [http://localhost:3001](http://localhost:3001) (Login: `admin` / `admin`)
* **Prometheus Targets:** [http://localhost:9090/targets](http://localhost:9090/targets) (Check system health)
* **Raw Metrics:** [http://localhost:8000/metrics](http://localhost:8000/metrics) (Debug the exporter)

## How It Works (Under the Hood)

The core is the `flowmetrix.py` script. It uses the `python-jenkins` library to connect to Jenkins. It's designed to be robust:

* **Smart Polling:** On startup, it checks the last completed build number and only processes *new* builds from that point on.
* **Stage Analysis:** It queries the Jenkins Workflow API (`/wfapi/describe`) to get a JSON breakdown of every stage in a build, calculating precise durations for each.
* **Prometheus Client:** It uses the official Python Prometheus client to expose standard counter, gauge, and histogram metrics.

## Contributing

Ideas and pull requests are welcome! This is a great starting point for building more advanced CI/CD analytics.

## License

This project is open-source and available under the [MIT License](LICENSE).
