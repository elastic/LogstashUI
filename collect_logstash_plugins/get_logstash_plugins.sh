#!/bin/bash

PLUGIN_DIR="/usr/share/logstash/vendor/bundle/jruby/3.1.0/gems"
OUTPUT="logstash_plugin_params.csv"

echo "type,name,param,validate,default,required" > "$OUTPUT"

for plugin_path in "$PLUGIN_DIR"/logstash-*; do
  plugin_name=$(basename "$plugin_path")
  
  if [[ "$plugin_name" =~ logstash-(input|filter|output)-(.+) ]]; then
    type="${BASH_REMATCH[1]}"
    name="${BASH_REMATCH[2]}"
  else
    continue
  fi

  find "$plugin_path" -name '*.rb' | while read -r rb_file; do
    grep -E "config\s+:[:a-zA-Z0-9_]+.*:validate\s*=>" "$rb_file" | while read -r line; do
      param=$(echo "$line" | grep -oP 'config\s+:\K[a-zA-Z0-9_]+')
      validate=$(echo "$line" | grep -oP ':validate\s*=>\s*:\K[a-zA-Z0-9_]+')
      default=$(echo "$line" | grep -oP ':default\s*=>\s*\K[^,} ]+' || echo "")
      required=$(echo "$line" | grep -q ':required\s*=>\s*true' && echo "true" || echo "false")

      echo "$type,$name,$param,$validate,$default,$required" >> "$OUTPUT"
    done
  done
done

echo "Plugin parameter summary written to $OUTPUT"
python3 logstash_plugin_formatter.py
