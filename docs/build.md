# There are a few different ways to run this project

--- 
## Using docker compose
> Use this mode with defaults when you want to run LogstashUI and you're okay with less performant simulations. Note: You can change simulation.mode to 'host' to use a non-running instance of Logstash that is installed on the host.
```bash
docker compose up -d
```
--- 

## Running locally (For Development)

### Running LogstashUI

#### Linux
```bash
cd logstashui/logstashui
LOGSTASH_CONFIG=../logstashui.example.yml python manage.py runserver 0.0.0.0:8080
```
#### Windows
```bash
cd logstashui/logstashui
$env:LOGSTASH_CONFIG="../logstashui.yml"
python manage.py runserver 0.0.0.0:8080
```
### Running the simulation agent
```bash
cd logstashui/logstashagent
docker build --no-cache -t logstashagent:latest . --build-arg LOGSTASH_CONFIG=../logstashui.example.yml
docker run -p 9600:9600 -p 9449:9449 -p 9500:9500 -e LOGSTASH_URL=http://localhost:8080 logstashagent:latest

```

