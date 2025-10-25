import json

f = open("enriched_plugins.json")
z = json.loads(f.read())
f.close()


newdict = {
    "input": {},
    "filter": {},
    "output": {},
    "codec": {}
}


for section in z:
    if section == "integrations":
        continue
    for plugin in z[section]:
        newdict[section][plugin] = [option for option in z[section][plugin]['options']]


print(json.dumps(newdict, indent=4))