```

docker build -t logstashagent:latest .
docker build --no-cache -t logstashagent:latest .


docker run -p 9600:9600 -p 9449:9449 -p 9500:9500 logstashagent:latest
```