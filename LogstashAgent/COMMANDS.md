```

# Build
docker build -t logstashagent:latest .

# Build with no cache
docker build --no-cache -t logstashagent:latest .

# Minimal generic run
docker run -p 9600:9600 -p 9449:9449 -p 9500:9500 logstashagent:latest

# Run when we're hosting LogstashUI as a runserver app locally
docker run -p 9600:9600 -p 9449:9449 -p 9500:9500 -e LOGSTASH_URL=http://localhost:8080 logstashagent:latest
```