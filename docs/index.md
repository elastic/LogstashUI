---
layout: default
title: LogstashUI Documentation
description: A modern web-based interface for managing and monitoring your Logstash instances and pipelines
---

<style>
/* Premium inset gradient divider */
hr.nav-divider {
    border: none;
    height: 1px;
    margin: 0.375rem 1.25rem;
    background: linear-gradient(
        to right,
        transparent,
        rgba(148, 163, 184, 0.08) 20%,
        rgba(148, 163, 184, 0.18) 50%,
        rgba(148, 163, 184, 0.08) 80%,
        transparent
    );
    position: relative;
}

hr.nav-divider::after {
    content: '';
    display: block;
    height: 1px;
    margin-top: 1px;
    background: linear-gradient(
        to right,
        transparent,
        rgba(0, 0, 0, 0.12) 20%,
        rgba(0, 0, 0, 0.18) 50%,
        rgba(0, 0, 0, 0.12) 80%,
        transparent
    );
}

.hero-section {
    text-align: center;
    margin-bottom: 4rem;
    padding-top: 2rem;
}

.hero-logo {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    margin-bottom: 1rem;
}

.logo-container {
    position: relative;
    width: 4rem;
    height: 4rem;
}

.logo-glow {
    position: absolute;
    inset: 0;
    width: 4rem;
    height: 4rem;
    background: rgba(168, 85, 247, 0.15);
    border-radius: 9999px;
    filter: blur(1rem);
}

.logo-img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    position: relative;
    z-index: 10;
}

.hero-title {
    font-size: 3rem;
    font-weight: bold;
    color: white;
}

.hero-description {
    font-size: 1.25rem;
    color: #d1d5db;
    max-width: 48rem;
    margin: 0 auto 2rem;
}

.btn-group {
    display: flex;
    justify-content: center;
    gap: 1rem;
    flex-wrap: wrap;
}

.btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    border-radius: 0.5rem;
    font-weight: 500;
    text-decoration: none;
    transition: all 0.2s;
}

.btn-primary {
    background: #9333ea;
    color: white;
}

.btn-primary:hover {
    background: #7e22ce;
}

.btn-secondary {
    background: #374151;
    color: white;
}

.btn-secondary:hover {
    background: #4b5563;
}

.feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1.5rem;
    margin-bottom: 4rem;
}

.feature-card {
    background: rgba(31, 41, 55, 0.5);
    backdrop-filter: blur(8px);
    border: 1px solid #374151;
    border-radius: 0.5rem;
    padding: 1.5rem;
    transition: border-color 0.2s;
}

.feature-card:hover {
    border-color: #3b82f6;
}

.feature-icon {
    width: 3rem;
    height: 3rem;
    border-radius: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 1rem;
}

.feature-icon.blue { background: rgba(59, 130, 246, 0.2); }
.feature-icon.green { background: rgba(34, 197, 94, 0.2); }
.feature-icon.purple { background: rgba(168, 85, 247, 0.2); }
.feature-icon.yellow { background: rgba(234, 179, 8, 0.2); }

.feature-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: white;
    margin-bottom: 0.5rem;
}

.feature-description {
    color: #9ca3af;
}

.content-card {
    background: rgba(31, 41, 55, 0.5);
    backdrop-filter: blur(8px);
    border: 1px solid #374151;
    border-radius: 0.5rem;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}

.code-block {
    background: #111827;
    border: 1px solid #374151;
    border-radius: 0.5rem;
    padding: 1rem;
    overflow-x: auto;
    margin: 1rem 0;
}

.code-block code {
    color: #10b981;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
}

.resource-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 1rem;
}

.resource-link {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem;
    background: rgba(31, 41, 55, 0.5);
    border: 1px solid #374151;
    border-radius: 0.5rem;
    text-decoration: none;
    transition: background 0.2s;
}

.resource-link:hover {
    background: rgba(55, 65, 81, 0.5);
}

.resource-icon {
    width: 2.5rem;
    height: 2.5rem;
    border-radius: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
}

.resource-icon.gray { background: rgba(107, 114, 128, 0.2); }
.resource-icon.blue { background: rgba(59, 130, 246, 0.2); }
.resource-icon.green { background: rgba(34, 197, 94, 0.2); }
.resource-icon.red { background: rgba(239, 68, 68, 0.2); }

.resource-content {
    flex: 1;
}

.resource-title {
    color: white;
    font-weight: 600;
    margin-bottom: 0.25rem;
}

.resource-desc {
    color: #9ca3af;
    font-size: 0.875rem;
}

section {
    margin-bottom: 4rem;
}

h2 {
    font-size: 2rem;
    font-weight: bold;
    color: white;
    margin-bottom: 1.5rem;
}

h3 {
    font-size: 1.5rem;
    font-weight: 600;
    color: white;
    margin-bottom: 1rem;
}

ul, ol {
    color: #d1d5db;
    margin-left: 1.5rem;
    margin-bottom: 1rem;
}

li {
    margin-bottom: 0.5rem;
}

p {
    color: #d1d5db;
    margin-bottom: 1rem;
}

code {
    background: #1f2937;
    padding: 0.2rem 0.4rem;
    border-radius: 0.25rem;
    font-size: 0.875rem;
    color: #e5e7eb;
}

pre code {
    background: transparent;
    padding: 0;
}

strong {
    color: white;
}
</style>

<div class="hero-section">
    <div class="hero-logo">
        <div class="logo-container">
            <div class="logo-glow"></div>
            <img src="https://raw.githubusercontent.com/elastic/LogstashUI/main/src/logstashui/Site/static/images/LogstashIcon.png" 
                 alt="Logstash UI" 
                 class="logo-img">
        </div>
        <h1 class="hero-title">LogstashUI</h1>
    </div>
    <p class="hero-description">
        A modern web-based interface for managing and monitoring your Logstash instances and pipelines
    </p>
    <div class="btn-group">
        <a href="#getting-started" class="btn btn-primary">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11a1 1 0 10-2 0v2H7a1 1 0 100 2h2v2a1 1 0 102 0v-2h2a1 1 0 100-2h-2V7z" clip-rule="evenodd"/>
            </svg>
            Get Started
        </a>
        <a href="https://github.com/elastic/LogstashUI" target="_blank" rel="noopener noreferrer" class="btn btn-secondary">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
            View on GitHub
        </a>
    </div>
</div>

## Getting Started

<div class="content-card">
    <p>
        LogstashUI provides an intuitive interface for managing Logstash pipelines, monitoring performance, and configuring SNMP devices. 
        Get up and running in minutes with our streamlined installation process.
    </p>
    <div class="code-block">
        <p style="font-size: 0.875rem; color: #9ca3af; margin-bottom: 0.5rem;">Quick install with Docker:</p>
        <pre><code>docker pull elastic/logstashui:latest
docker run -p 8000:8000 elastic/logstashui:latest</code></pre>
    </div>
    <p>
        Visit <code>http://localhost:8000</code> to access the interface.
    </p>
</div>

## Features

<div class="feature-grid">
    <div class="feature-card">
        <div class="feature-icon blue">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="#60a5fa" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
        </div>
        <h3 class="feature-title">Pipeline Management</h3>
        <p class="feature-description">Create, edit, and manage Logstash pipelines with an intuitive visual editor and text-based configuration options.</p>
    </div>

    <div class="feature-card">
        <div class="feature-icon green">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="#4ade80" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
        </div>
        <h3 class="feature-title">Real-time Monitoring</h3>
        <p class="feature-description">Monitor pipeline metrics, performance, and health in real-time across all your Logstash instances.</p>
    </div>

    <div class="feature-card">
        <div class="feature-icon purple">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="#c084fc" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
            </svg>
        </div>
        <h3 class="feature-title">SNMP Integration</h3>
        <p class="feature-description">Configure SNMP devices, profiles, and credentials for comprehensive network monitoring.</p>
    </div>

    <div class="feature-card">
        <div class="feature-icon yellow">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="#facc15" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
            </svg>
        </div>
        <h3 class="feature-title">Grok Debugger</h3>
        <p class="feature-description">Test and debug Grok patterns with an integrated debugger to ensure your log parsing works correctly.</p>
    </div>
</div>

## Installation

### Prerequisites

<div class="content-card">
    <ul>
        <li>Docker and Docker Compose (recommended)</li>
        <li>Python 3.9+ (for manual installation)</li>
        <li>Elasticsearch cluster (for centralized pipeline management)</li>
        <li>Logstash 8.x+ instances</li>
    </ul>
</div>

### Docker Installation (Recommended)

<div class="content-card">
    <div class="code-block">
        <pre><code>git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI
docker-compose up -d</code></pre>
    </div>
    <p>
        The application will be available at <code>http://localhost:8000</code>
    </p>
</div>

### Manual Installation

<div class="content-card">
    <div class="code-block">
        <pre><code>git clone https://github.com/elastic/LogstashUI.git
cd LogstashUI
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver</code></pre>
    </div>
    <p>
        Access the application at <code>http://localhost:8000</code>
    </p>
</div>

## Configuration

### Environment Variables

<div class="content-card">
    <p>Configure LogstashUI using environment variables or a <code>.env</code> file:</p>
    <div class="code-block">
        <pre><code># Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/logstashui

# Security
SECRET_KEY=your-secret-key-here
DEBUG=False

# Elasticsearch Connection
ELASTICSEARCH_HOST=https://localhost:9200
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=changeme</code></pre>
    </div>
</div>

### Adding Connections

<div class="content-card">
    <p>LogstashUI supports two types of connections:</p>
    <ul>
        <li><strong>Elasticsearch (Centralized Management):</strong> Manage pipelines stored in Elasticsearch</li>
        <li><strong>Logstash Agent:</strong> Direct connection to Logstash instances with agent-based management</li>
    </ul>
    <p>
        Navigate to <strong>Connection Manager</strong> in the UI to add and configure your connections.
    </p>
</div>

## Contributing

<div class="content-card">
    <p>
        We welcome contributions from the community! Whether it's bug fixes, new features, or documentation improvements, 
        your help makes LogstashUI better for everyone.
    </p>
    <h3>How to Contribute</h3>
    <ol>
        <li>Fork the repository on GitHub</li>
        <li>Create a new branch for your feature or bugfix</li>
        <li>Make your changes and commit with clear messages</li>
        <li>Push to your fork and submit a pull request</li>
        <li>Wait for review and address any feedback</li>
    </ol>
    <div class="btn-group" style="justify-content: flex-start; margin-top: 1.5rem;">
        <a href="https://github.com/elastic/LogstashUI" target="_blank" rel="noopener noreferrer" class="btn btn-secondary">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
            View Repository
        </a>
        <a href="https://github.com/elastic/LogstashUI/issues/new?template=issue.md" target="_blank" rel="noopener noreferrer" class="btn btn-primary">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Report an Issue
        </a>
    </div>
</div>

## Resources

<div class="resource-grid">
    <a href="https://github.com/elastic/LogstashUI" target="_blank" rel="noopener noreferrer" class="resource-link">
        <div class="resource-icon gray">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="#d1d5db" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
        </div>
        <div class="resource-content">
            <div class="resource-title">GitHub Repository</div>
            <div class="resource-desc">Source code and issue tracking</div>
        </div>
    </a>

    <a href="https://www.elastic.co/guide/en/logstash/current/index.html" target="_blank" rel="noopener noreferrer" class="resource-link">
        <div class="resource-icon blue">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#60a5fa" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
            </svg>
        </div>
        <div class="resource-content">
            <div class="resource-title">Logstash Documentation</div>
            <div class="resource-desc">Official Elastic documentation</div>
        </div>
    </a>

    <a href="https://discuss.elastic.co/c/logstash/14" target="_blank" rel="noopener noreferrer" class="resource-link">
        <div class="resource-icon green">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#4ade80" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
        </div>
        <div class="resource-content">
            <div class="resource-title">Community Forums</div>
            <div class="resource-desc">Get help from the community</div>
        </div>
    </a>

    <a href="https://github.com/elastic/LogstashUI/issues/new?template=issue.md" target="_blank" rel="noopener noreferrer" class="resource-link">
        <div class="resource-icon red">
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="#f87171" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
        </div>
        <div class="resource-content">
            <div class="resource-title">Report an Issue</div>
            <div class="resource-desc">Found a bug? Let us know</div>
        </div>
    </a>
</div>

---

<div style="text-align: center; padding: 2rem 0; border-top: 1px solid #374151; margin-top: 4rem;">
    <p style="color: #9ca3af; font-size: 0.875rem;">
        Copyright © Elasticsearch B.V. Licensed under the Elastic License.
    </p>
    <p style="color: #6b7280; font-size: 0.75rem; margin-top: 0.5rem;">
        LogstashUI is an open-source project maintained by the Elastic community.
    </p>
</div>
